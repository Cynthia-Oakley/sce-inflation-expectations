#!/usr/bin/env python3
"""Six-cell (education x employment-attachment) grid support + Core512 allocation.

Offline support analysis for the full-period coverage window
(2019-01..2026-09, per outputs/sce_fullperiod_data_20261021_v1/coverage.json),
continuing docs/workstreams/20261019_advisor_followup/stratification_draft.md.

Grid: three education bands (high_school / some_college / college) x two
employment-attachment states (attached = employed|on_leave, not_attached =
unemployed|retired|disabled|student|homemaker|other). Anyone with an unknown
education or an unclassifiable employment answer goes to a separate "unknown"
pool and is never silently defaulted. Inside not_attached the original
employment labels stay visible (a retiree and an unemployed respondent are not
the same economic identity).

For every month with public micro data the FULL monthly respondent frame is
used (no prior-validity or adjacent-returner filter, no outcome screen):
per-cell N, survey-weighted share and ESS = (sum w)^2 / sum w^2, plus
age/income/region weighted margins, entrant share and the not_attached
internal breakdown. Months without micro data (ready_no_micro) are labelled
"synthetic_framework": no grid is computed and nothing is presented as a real
full-survey distribution.

Core allocation proposal (512 distinct Core per month, counts only — no one is
selected here): floor of FLOOR_N per primary cell + unknown pool capped at
min(N_unknown, FLOOR_N), remainder by survey-weight mass with largest-remainder
apportionment under frame caps. See core_allocation_proposal.json for the full
rule set, fallbacks and the computable inclusion probability.

Discipline: no cell is collapsed to one representative person; no model error
is used to pick cells; this design is a candidate for the FINAL full-volume
configuration only and does not modify any existing experiment population,
weight or frozen manifest. No API calls; no existing file is modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

COVERAGE = REPO_ROOT / "outputs/sce_fullperiod_data_20261021_v1/coverage.json"
MICRO_FILES = [
    "data/raw/sce_p_sources/micro_2017_2019.xlsx",
    "data/raw/sce_audit_20260928/micro_2020_2024.xlsx",
    "data/raw/sce_micro_refresh_20261021/micro_latest.xlsx",
]
# Existing age x income design support, kept as reference (item 3).
REFERENCE_OUTPUTS = [
    "outputs/sce_sampling_scale_20261021_v1/summary.json",
    "outputs/sce_stratification_support_20261019_v1/summary.json",
]

OUT_DIR = REPO_ROOT / "outputs/sce_population_grid_20261022_v1"
TARGET_CORE_N = 512
FLOOR_N = 24  # per primary cell; see MINIMUM_RATIONALE below.

EDUCATION_MAP = {"High School": "high_school", "Some College": "some_college",
                 "College": "college"}
EDU_BANDS = ["high_school", "some_college", "college"]
ATTACHMENT = ["attached", "not_attached"]
PRIMARY_CELLS = [f"{e}|{w}" for e in EDU_BANDS for w in ATTACHMENT]
UNKNOWN_CELL = "unknown"
ALL_CELLS = PRIMARY_CELLS + [UNKNOWN_CELL]

# Q10 dummies, questionnaire p.11-12; priority order as in build_sce_population.py.
EMPLOYMENT_CODE_MAP = {1: "employed", 2: "employed", 3: "unemployed",
                       4: "unemployed", 5: "on_leave", 7: "retired",
                       6: "disabled", 8: "student", 9: "homemaker", 10: "other"}
EMPLOYMENT_PRIORITY = [1, 2, 3, 4, 5, 7, 6, 8, 9, 10]
ATTACHED = {"employed", "on_leave"}
NOT_ATTACHED_JOBS = ["unemployed", "retired", "disabled", "student",
                     "homemaker", "other"]

MINIMUM_RATIONALE = [
    "Floor 24 is derived for the 512-Core design, not copied from the draft's "
    "12-of-192 dev floor: (1) observed frame ESS/N ~= 0.94 in these monthly "
    "frames, so n=24 implies expected ESS ~= 22 > 2x the draft display screen "
    "(n>=10, ESS>=10); (2) worst-case within-cell proportion SE at n=24 is "
    "sqrt(0.25/24) ~= 10.2pp vs 14.4pp at n=12; (3) the floor consumes 6*24="
    "144/512 = 28% of the sample (draft: 72/192 = 37.5%), leaving 72% for "
    "population-mass proportional allocation, which dominates national "
    "aggregate precision at the 512 scale; (4) empirically floor 24 <= the "
    "minimum observed primary-cell frame N (36) in all 82 micro months, so the "
    "floor is feasible without forced fallback in practice (fallbacks are "
    "still specified and used for the unknown pool).",
]

MARGIN_FIELDS = {"age_group": "_AGE_CAT", "household_income_band": "_HH_INC_CAT",
                 "region": "_REGION_CAT"}
INCOME_MAP = {"Under 50k": "under_50k", "50k to 100k": "50k_to_100k",
              "Over 100k": "over_100k"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def effective_sample_size(weights) -> float:
    """ESS = (sum w)^2 / sum w^2 over valid positive weights; 0 when empty."""
    ws = [float(w) for w in weights
          if isinstance(w, (int, float)) and pd.notna(w) and float(w) > 0]
    if not ws:
        return 0.0
    s = sum(ws)
    return s * s / sum(w * w for w in ws)


def classify_employment(q10: dict) -> str | None:
    """First Q10 code in priority order; None when nothing selected."""
    selected = [i for i in range(1, 11) if q10.get(f"Q10_{i}") == 1]
    for code in EMPLOYMENT_PRIORITY:
        if code in selected:
            return EMPLOYMENT_CODE_MAP[code]
    return None


def assign_cell(edu_raw, employment: str | None) -> tuple[str, str]:
    """Return (cell, unknown_reason). reason: '', 'education_missing', '
    employment_unclassified', 'both'."""
    edu = EDUCATION_MAP.get(edu_raw) if isinstance(edu_raw, str) else None
    if edu is None:
        return UNKNOWN_CELL, ("both" if employment is None else "education_missing")
    work = ("attached" if employment in ATTACHED
            else "not_attached" if employment in NOT_ATTACHED_JOBS else None)
    if work is None:
        return UNKNOWN_CELL, "employment_unclassified"
    return f"{edu}|{work}", ""


def allocate_core(counts: dict, masses: dict, total_n: int,
                  floor: int = FLOOR_N, unknown: str = UNKNOWN_CELL) -> dict:
    """Floor-plus-largest-remainder allocation; counts only, never selects.

    Rules: every primary cell gets base = min(floor, N); the unknown pool gets
    base = min(N, floor) (full inclusion when the pool is small; never forced
    above its frame). If sum(base) > total_n the design is infeasible and this
    raises (revise explicitly, never silently drop a cell). The remainder is
    apportioned by survey-weight mass under the frame caps N_cell - base;
    cells that ran under floor because N < floor automatically receive their
    shortfall back through the mass-proportional phase. Deterministic.
    """
    if set(counts) != set(masses):
        raise ValueError("counts and masses must cover the same cells")
    if any(not isinstance(v, int) or v < 0 for v in counts.values()):
        raise ValueError("nonnegative integer frame counts required")
    if any(not (m >= 0) for m in masses.values()):
        raise ValueError("nonnegative masses required")
    if total_n < 0 or floor < 0:
        raise ValueError("nonnegative total_n and floor required")
    base = {k: (min(floor, counts[k]) if k != unknown else min(counts[k], floor))
            for k in counts}
    if sum(base.values()) > total_n:
        raise ValueError(f"floor infeasible: base {sum(base.values())} > {total_n}")
    alloc = dict(base)
    while sum(alloc.values()) < total_n:
        headroom = {k: counts[k] - alloc[k] for k in alloc if alloc[k] < counts[k]}
        if not headroom:
            break  # frame exhausted; report shortfall honestly
        pool_mass = sum(masses[k] for k in headroom)
        if pool_mass <= 0:
            quotas = {k: 1.0 for k in headroom}
        else:
            quotas = {k: (total_n - sum(alloc.values())) * masses[k] / pool_mass
                      for k in headroom}
        adds = {k: min(headroom[k], int(quotas[k])) for k in headroom}
        if not sum(adds.values()):
            adds[max(headroom, key=lambda k: (quotas[k] - int(quotas[k]), k))] = 1
        for k, v in adds.items():
            alloc[k] += v
    return alloc


total_all = [0.0]  # set per month; module-level to keep helpers plain


def cell_stats(rows: list[dict]) -> dict:
    ws = [r["weight"] for r in rows
          if isinstance(r["weight"], (int, float)) and pd.notna(r["weight"])
          and float(r["weight"]) > 0]
    wsum = sum(ws)
    n = len(rows)
    ess = effective_sample_size(ws)
    status = ("empty" if n == 0 else
              "sparse" if n < 10 else
              "weak" if ess < 10 else "strong")
    return {"n": n, "n_weight_valid": len(ws),
            "weight_sum": round(wsum, 4),
            "weighted_share": round(wsum / total_all[0], 6) if total_all[0] else None,
            "ess": round(ess, 2), "status": status}


def load_frame() -> pd.DataFrame:
    usecols = (["date", "userid", "tenure", "weight", "_EDU_CAT", "_HH_INC_CAT",
                "_AGE_CAT", "_REGION_CAT"] + [f"Q10_{i}" for i in range(1, 11)])
    frames = []
    for rel in MICRO_FILES:
        df = pd.read_excel(REPO_ROOT / rel, skiprows=1, usecols=usecols)
        df["source_file"] = Path(rel).name
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df = df[df["date"].notna()].copy()
    df["date"] = df["date"].astype(int)
    df["userid"] = df["userid"].astype("int64")
    return df


def month_grid(frame: pd.DataFrame) -> dict:
    total_all[0] = float(frame["weight"].clip(lower=0).fillna(0).sum())
    q10_cols = [f"Q10_{i}" for i in range(1, 11)]
    records = []
    for row in frame.to_dict("records"):
        emp = classify_employment({c: row.get(c) for c in q10_cols})
        cell, reason = assign_cell(row.get("_EDU_CAT"), emp)
        records.append({"cell": cell, "reason": reason, "employment": emp,
                        "weight": row.get("weight"), "tenure": row.get("tenure"),
                        "_AGE_CAT": row.get("_AGE_CAT"),
                        "_HH_INC_CAT": row.get("_HH_INC_CAT"),
                        "_REGION_CAT": row.get("_REGION_CAT")})
    cells = {c: [r for r in records if r["cell"] == c] for c in ALL_CELLS}
    grid = {c: cell_stats(v) for c, v in cells.items()}
    grid[UNKNOWN_CELL]["unknown_reason_counts"] = dict(
        Counter(r["reason"] or "not_unknown" for r in cells[UNKNOWN_CELL]))
    na = [r for c in PRIMARY_CELLS if c.endswith("not_attached")
          for r in cells[c]]
    na_total_w = sum(r["weight"] for r in na
                     if isinstance(r["weight"], (int, float))
                     and pd.notna(r["weight"]) and float(r["weight"]) > 0)
    breakdown = {}
    for job in NOT_ATTACHED_JOBS:
        rows = [r for r in na if r["employment"] == job]
        ws = [r["weight"] for r in rows
              if isinstance(r["weight"], (int, float)) and pd.notna(r["weight"])
              and float(r["weight"]) > 0]
        breakdown[job] = {"n": len(rows),
                          "weighted_share_within_not_attached":
                          round(sum(ws) / na_total_w, 6) if na_total_w else None}
    margins = {}
    for name, col in MARGIN_FIELDS.items():
        cats = {}
        for cat in sorted({r[col] for r in records if isinstance(r[col], str)}):
            rows = [r for r in records if r[col] == cat]
            ws = [r["weight"] for r in rows
                  if isinstance(r["weight"], (int, float)) and pd.notna(r["weight"])
                  and float(r["weight"]) > 0]
            cats[INCOME_MAP.get(cat, cat) if name == "household_income_band"
                 else cat] = {"n": len(rows),
                              "weighted_share": (round(sum(ws) / total_all[0], 6)
                                                 if total_all[0] else None)}
        missing = [r for r in records if not isinstance(r[col], str)]
        cats["missing"] = {"n": len(missing),
                           "weighted_share": None}
        margins[name] = cats
    entrant = [r for r in records
               if isinstance(r["tenure"], (int, float)) and pd.notna(r["tenure"])
               and int(r["tenure"]) == 1]
    return {"cells": grid, "not_attached_breakdown": breakdown,
            "margins": margins, "frame_n": len(records),
            "entrant_n": len(entrant),
            "entrant_share": round(len(entrant) / len(records), 4) if records else None}


def build_support(coverage: dict, df: pd.DataFrame) -> dict:
    months_out = []
    for m in coverage["months"]:
        key = m["target_month"]
        yyyymm = int(key.replace("-", ""))
        if not m["micro_truth_available"]:
            months_out.append({"target_month": key, "yyyymm": yyyymm,
                               "status": m["status"],
                               "framework": "synthetic_framework",
                               "note": ("no public micro data for this month; "
                                        "grid NOT computed from real respondents. "
                                        "A synthetic frame (e.g. whole-row donors "
                                        "from a past wave) must be assembled "
                                        "separately and must not be presented as "
                                        "the real full-survey distribution."),
                               "grid": None})
            continue
        frame = df[df["date"] == yyyymm]
        if frame.empty:
            raise ValueError(f"coverage claims micro for {key} but frame is empty")
        mg = month_grid(frame)
        months_out.append({"target_month": key, "yyyymm": yyyymm,
                           "status": m["status"],
                           "framework": "real_micro_full_frame",
                           "micro_source_file": sorted(set(frame["source_file"])),
                           "grid": mg})
    return months_out


def build_proposal(months_out: list[dict]) -> dict:
    table = []
    for g in months_out:
        row = {"target_month": g["target_month"], "yyyymm": g["yyyymm"],
               "status": g["status"], "framework": g["framework"]}
        if g["grid"] is None:
            row["allocation"] = None
            row["note"] = ("apply the same floor+mass rule to the assembled "
                           "synthetic frame; compute the cell table on that "
                           "frame's actual N before any run; do not claim real "
                           "full-survey distribution")
            table.append(row)
            continue
        counts = {c: g["grid"]["cells"][c]["n"] for c in ALL_CELLS}
        masses = {c: g["grid"]["cells"][c]["weight_sum"] for c in ALL_CELLS}
        alloc = allocate_core(counts, masses, TARGET_CORE_N, floor=FLOOR_N)
        shortfall = [c for c in PRIMARY_CELLS if 0 < counts[c] < FLOOR_N]
        row["allocation"] = {
            c: {"frame_n": counts[c], "allocated_n": alloc[c],
                "within_cell_inclusion_probability_if_srs":
                round(alloc[c] / counts[c], 6) if counts[c] else None}
            for c in ALL_CELLS}
        row["allocated_total"] = sum(alloc.values())
        row["frame_total"] = sum(counts.values())
        row["cells_below_floor"] = shortfall
        table.append(row)
    return table


def summarise(months_out: list[dict]) -> dict:
    s = {"micro_months": 0, "synthetic_framework_months": 0}
    per_cell = {c: {"n_min": None, "n_min_month": None, "ess_min": None,
                    "ess_min_month": None, "sparse_months": [], "weak_months": []}
                for c in ALL_CELLS}
    for g in months_out:
        if g["grid"] is None:
            s["synthetic_framework_months"] += 1
            continue
        s["micro_months"] += 1
        for c, st in g["grid"]["cells"].items():
            p = per_cell[c]
            if p["n_min"] is None or st["n"] < p["n_min"]:
                p["n_min"], p["n_min_month"] = st["n"], g["target_month"]
            if st["ess"] > 0 and (p["ess_min"] is None or st["ess"] < p["ess_min"]):
                p["ess_min"], p["ess_min_month"] = st["ess"], g["target_month"]
            if st["status"] == "sparse":
                p["sparse_months"].append(g["target_month"])
            elif st["status"] == "weak":
                p["weak_months"].append(g["target_month"])
    s["per_cell"] = per_cell
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT_DIR,
                    help="fresh output directory (must not exist)")
    args = ap.parse_args(argv)
    out: Path = args.out
    if out.exists():
        sys.exit(f"fresh output required: {out} already exists")

    coverage = json.loads(COVERAGE.read_text())
    print("loading micro data (3 xlsx, full monthly frames)...", flush=True)
    df = load_frame()
    print(f"  rows={len(df)} months={df['date'].min()}..{df['date'].max()}", flush=True)

    months_out = build_support(coverage, df)
    summary = summarise(months_out)

    grid_def = {
        "cells": PRIMARY_CELLS, "unknown_pool": UNKNOWN_CELL,
        "education_mapping": {"source": "_EDU_CAT",
                              "map": EDUCATION_MAP,
                              "missing_rule": "missing/non-mapped _EDU_CAT -> unknown pool"},
        "employment_mapping": {
            "source": "Q10_1..Q10_10 dummies (questionnaire p.11-12), first "
                      "code in priority order",
            "priority": EMPLOYMENT_PRIORITY,
            "code_map": {str(k): v for k, v in EMPLOYMENT_CODE_MAP.items()},
            "attached": sorted(ATTACHED),
            "not_attached_original_labels_kept": NOT_ATTACHED_JOBS,
            "note": ("not_attached merges unemployed/retired/disabled/student/"
                     "homemaker/other for this coarse grid only; the internal "
                     "breakdown is reported separately and the labels are not "
                     "treated as one economic identity")},
        "ess_definition": "ESS = (sum w)^2 / sum w^2 over rows with valid positive "
                          "survey weight; weighted_share = cell weight sum / month "
                          "weight sum",
        "cell_status": "empty: N=0; sparse: N<10; weak: ESS<10; strong otherwise "
                       "(display screen only, not a power guarantee)"}

    support = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "scripts/build_sce_population_grid.py",
        "status": "grid_support_only_not_applied",
        "new_api_calls": 0,
        "coverage_source": str(COVERAGE.relative_to(REPO_ROOT)),
        "micro_sources": [{"path": p, "sha256": sha256(REPO_ROOT / p)}
                          for p in MICRO_FILES],
        "grid_definition": grid_def,
        "discipline": [
            "full monthly respondent frame; no prior-validity, adjacent-returner "
            "or outcome screen",
            "no cell is collapsed to one representative person",
            "no model error used to select or rank cells",
            "unknown and sparse cells reported explicitly, never imputed",
            "candidate design for the FINAL full-volume configuration only; no "
            "existing experiment population, weight or frozen manifest changed",
            "no one is selected here; only counts and probabilities"],
        "months": months_out,
        "summary": summary,
    }

    proposal = {
        "generated_at_utc": support["generated_at_utc"],
        "target_core_n": TARGET_CORE_N,
        "minimum_floor": FLOOR_N,
        "minimum_rationale": MINIMUM_RATIONALE,
        "allocation_rule": [
            f"1. base: each primary cell gets min({FLOOR_N}, frame N); the "
            f"unknown pool gets min(frame N, {FLOOR_N}) (full inclusion when "
            "small; never forced, never above its frame)",
            "2. remainder = 512 - base total, apportioned by survey-weight "
            "mass (cell weight sum) with deterministic largest-remainder "
            "rounding, under the per-cell caps frame N - base",
            "3. cells with frame N below the floor are fully taken (pi=1 for "
            "everyone in them); their unused floor slots flow back through the "
            "mass-proportional remainder",
            "4. if base total exceeds 512 the design is declared infeasible "
            "and revised explicitly (never silently drop a cell); if the whole "
            "frame is exhausted before 512, report the shortfall honestly",
            "5. unknown pool is always reported as its own line and never "
            "merged into a primary cell"],
        "fallback_rules": [
            "missing/empty cell (N=0): allocation 0, flagged, no imputation",
            "tiny cell (0 < N < floor): take all N, flag in cells_below_floor",
            "unknown pool N=0: 0",
            "no post-draw reshuffling to make margins look better; changing "
            "the draw after seeing results voids the recorded pi"],
        "inclusion_probability": {
            "within_cell_draw": ("simple random sampling without replacement "
                                 "inside each cell; pi_i = n_cell / N_cell for "
                                 "every member of the cell"),
            "design_weight": ("analysis weight = original survey weight / pi_i "
                              "(Horvitz-Thompson style); both the survey weight "
                              "and pi are recorded per person"),
            "stable_draw_option": ("stable_priority_srs as in "
                                   "studies/sce_inflation_expectations/monthly_population.py: "
                                   "a fixed pseudorandom priority per anonymized "
                                   "agent id; the lowest n_cell priorities form "
                                   "the cell draw. Marginal pi stays n_cell/N_cell "
                                   "and adjacent months share the ranking, so the "
                                   "panel overlap follows the survey rotation "
                                   "instead of a forced panel intersection"),
            "cross_month_warning": ("monthly frames change with the SCE survey "
                                    "rotation; monthly pi is simple, but a joint "
                                    "multi-month inclusion probability is NOT "
                                    "simple. Do not apply the within-cell SRS "
                                    "formula to joint cross-month selection; "
                                    "survey-panel entry/exit and computational "
                                    "subsample entry/exit are tracked separately"),
            "anonymization": ("only anonymized agent ids are carried into any "
                              "draw; raw userids never leave the private state "
                              "files; no respondent list is emitted by this "
                              "analysis")},
        "reference_age_x_income_design": {
            "paths": REFERENCE_OUTPUTS,
            "what_six_cell_improves": [
                "adds the employment-attachment dimension the age x income "
                "strata lack, separating retirees/unemployed/homemakers rather "
                "than letting them blend inside age x income cells",
                "with 512 Core the floor (24/cell) is feasible in all 82 micro "
                "months: minimum primary-cell frame N = 36 > floor",
                "coarser 6+1 grid keeps per-cell n high (ESS ~ 0.94 x N frames), "
                "so weighted national aggregates stay precise"],
            "what_it_sacrifices": [
                "within-cell age and income heterogeneity is no longer "
                "stratified: margins are reported as diagnostics but not "
                "controlled (the reference design bounds age x income cells "
                "directly)",
                "a 3x2 grid cannot support fine age x income x education "
                "interactions; the old age x income within-cell variance "
                "diagnostics do not transfer to the new cells",
                "the not_attached pool mixes several distinct economic states; "
                "only the coarse cell is guaranteed support"]},
        "months": build_proposal(months_out),
    }

    out.mkdir(parents=True)
    (out / "population_grid_support.json").write_text(
        json.dumps(support, ensure_ascii=False, indent=2) + "\n")
    (out / "core_allocation_proposal.json").write_text(
        json.dumps(proposal, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {out/'population_grid_support.json'}")
    print(f"wrote {out/'core_allocation_proposal.json'}")
    print(f"micro months={summary['micro_months']} "
          f"synthetic_framework months={summary['synthetic_framework_months']}")
    for c, p in summary["per_cell"].items():
        print(f"  {c:26s} N_min={p['n_min']} ({p['n_min_month']}) "
              f"ESS_min={p['ess_min']} ({p['ess_min_month']}) "
              f"sparse={len(p['sparse_months'])} weak={len(p['weak_months'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
