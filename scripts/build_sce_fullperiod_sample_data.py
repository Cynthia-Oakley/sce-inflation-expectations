#!/usr/bin/env python3
"""Build the phase-2 sample-month P/E delivery for the SCE full-period workstream:
2019-06 (historical, micro truth), 2023-03 (entrant peak 172, complete news
labels), 2026-06 (recent, no micro truth -> synthetic frame + aggregate-only
evaluation truth).

Writes into outputs/sce_fullperiod_data_20261021_v1/<YYYYMM>/:
  population.json                PopulationBundle, schema-validated, FULL frame
  population_state_private.json  anon ids, entry status, tenure, P-field provenance
  belief_state_private.json      source_kind / prior answers / donor assignments
  sampling_private.json          strata, weights, stable priorities (no Core pick)
  news_label_index.json          window news pool + label status
  evaluation_truth/              micro truth (2 months) / aggregate-only (2026-06)
plus delivery-root sources.json and README.md.

Anonymization: agent_id = "sce_" + sha256(f"{userid}|{SALT}")[:16]; the salt is
stored only in population_state_private.json. Raw userids never appear in ANY
delivered file (population, private states, sampling, news, evaluation truth).

Key conventions (docs/workstreams/20261021_fullperiod/kimi_data_contract_v2.md):
- persona attributes use ONLY the existing whitelist (profile categories,
  Q10 employment, Q43 housing carried forward from the respondent's own entry
  answer, never from the future), same mappings as scripts/build_sce_population.py.
- persona weight = the survey weight (evaluation weight lives in a sidecar).
- entrant_n / survey_entry_status: tenure==1 == first observed appearance
  (verified in phase 1: 106,351/106,351 consecutive pairs increment by 1;
  tenure==1 always coincides with first appearance). First appearances with
  tenure>1 are left_boundary (joined before 2017-01).
- New-entrant initial beliefs: donors drawn from STRICTLY PAST first-time
  participants (tenure==1, month < target), matched on age x education x
  income (fallbacks recorded), preserving the donor's joint Q8 x Q9 vector;
  seeded, no target-month median calibration, no global-mean assignment.
- 2026-06 synthetic frame: whole-row donors from the 2025-10 wave (latest
  local micro, published_at unverified -> pit_risk_unverified), PPS draw by
  survey weight, N=1300, joint structure preserved by construction.

Offline only; no existing file modified.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_sce_population as bp  # noqa: E402  (maps/helpers; main is guarded)
import build_sce_evaluation_truth as bet  # noqa: E402  (quantile helpers)
from studies.sce_inflation_expectations.news_selection_trial import (  # noqa: E402
    RULE_FILE, RecallRules)
from studies.sce_inflation_expectations.coverage_preparation import (  # noqa: E402
    previous_month)

OUT_DIR = REPO_ROOT / "outputs/sce_fullperiod_data_20261021_v1"
STUDY_ID = "sce_inflation_expectations"

MICRO_FILES = [
    ("data/raw/sce_p_sources/micro_2017_2019.xlsx", "micro_2017_2019.xlsx"),
    ("data/raw/sce_audit_20260928/micro_2020_2024.xlsx", "micro_2020_2024.xlsx"),
    ("data/raw/sce_audit_20260928/micro_latest.xlsx", "micro_latest.xlsx"),
]
LABEL_GLOBS = ["outputs/sce_*label*/labels.jsonl",
               "outputs/sce_expanded_news_run_20261014_v1/part_*/labels.jsonl"]
CHART_AUDIT = REPO_ROOT / "data/raw/sce_audit_20260928/chart.xlsx"
CHART_REFRESH = REPO_ROOT / "data/raw/sce_micro_refresh_20261021/chart.xlsx"

REAL_TARGETS = {"201906": 201906, "202303": 202303}
SYNTH_TARGET = "202606"
SYNTH_SOURCE_WAVE = 202510
SYNTH_N = 1300

ANON_SALT = "sce-fullperiod-anon-v1-20261021"
PRIORITY_SALT = "sce-fullperiod-priority-v1-20261021"
DONOR_SEED = 20261021
PRIORITY_SEED = 20261021

USECOLS = (["date", "userid", "tenure", "weight", "Q8v2", "Q8v2part2", "Q9_mean"]
           + [f"Q9_bin{i}" for i in range(1, 11)]
           + [f"Q10_{i}" for i in range(1, 11)]
           + ["Q43", "D3", "survey_date",
              "_AGE_CAT", "_EDU_CAT", "_HH_INC_CAT", "_REGION_CAT", "_NUM_CAT",
              "_STATE"])


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def agent_id_for(userid: int) -> str:
    return "sce_" + hashlib.sha256(f"{int(userid)}|{ANON_SALT}".encode()).hexdigest()[:16]


def syn_id_for(donor_uid: int, draw_index: int) -> str:
    return "syn_" + hashlib.sha256(
        f"{int(donor_uid)}|{draw_index}|{ANON_SALT}".encode()).hexdigest()[:16]


def stable_priority(agent_id: str) -> int:
    h = hashlib.sha256(f"{agent_id}|{PRIORITY_SALT}".encode()).hexdigest()
    return int(h[:16], 16)


def month_step(yyyymm: int) -> int:
    return yyyymm // 100 * 12 + yyyymm % 100


def load_micro() -> pd.DataFrame:
    frames = []
    for rel, name in MICRO_FILES:
        df = pd.read_excel(REPO_ROOT / rel, skiprows=1, usecols=USECOLS)
        df["source_file"] = name
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df = df[df["date"].notna()].copy()
    df["date"] = df["date"].astype(int)
    df["userid"] = df["userid"].astype("int64")
    return df


def q8_q9_summary(row) -> dict:
    """Current口径 (scripts/build_sce_evaluation_truth.py, fix 2026-10-03):
    Q8v2 = direction code (1 up / 2 down), Q8v2part2 = signed numeric point.
    Q8/Q9 validity masks are independent."""
    q8p = row.get("Q8v2part2")
    q8p = float(q8p) if isinstance(q8p, (int, float)) and not pd.isna(q8p) else None
    q8d = row.get("Q8v2")
    q8d = int(q8d) if isinstance(q8d, (int, float)) and not pd.isna(q8d) else None
    q9m = row.get("Q9_mean")
    q9m = float(q9m) if isinstance(q9m, (int, float)) and not pd.isna(q9m) else None
    bins = []
    for i in range(1, 11):
        v = row.get(f"Q9_bin{i}")
        v = float(v) if isinstance(v, (int, float)) and not pd.isna(v) else None
        bins.append(v)
    q9_valid = q9m is not None and all(b is not None for b in bins)
    return {
        "q8_direction_code": q8d,                       # 1=up, 2=down
        "q8_direction": {1: "up", 2: "down"}.get(q8d),
        "q8_point_pct": q8p,                            # signed numeric point
        "q8_valid": q8p is not None,
        "q9_mean": q9m,
        "q9_bins": bins,                                # bin1..bin10, percent
        "q9_valid": q9_valid,
    }


def build_persona(row, housing, ref_month: int, synthetic: bool) -> dict:
    attrs: dict = {}
    age = row["_AGE_CAT"]
    if isinstance(age, str):
        attrs["age_group"] = age
    edu = row["_EDU_CAT"]
    if isinstance(edu, str) and edu in bp.EDUCATION_MAP:
        attrs["education_group"] = bp.EDUCATION_MAP[edu]
    inc = row["_HH_INC_CAT"]
    if isinstance(inc, str) and inc in bp.INCOME_MAP:
        attrs["household_income_band"] = bp.INCOME_MAP[inc]
    region = row["_REGION_CAT"]
    if isinstance(region, str):
        attrs["region"] = region
    state = row["_STATE"]
    if isinstance(state, str):
        attrs["state"] = state
    num = row["_NUM_CAT"]
    if isinstance(num, str) and num in bp.NUMERACY_MAP:
        attrs["numeracy"] = bp.NUMERACY_MAP[num]
    emp = bp._employment_code(row)
    if emp is not None:
        attrs["employment_status"] = emp
    if housing is not None:
        attrs["housing_tenure"] = housing
    w = row.get("weight")
    weight = float(w) if isinstance(w, (int, float)) and not pd.isna(w) else 1.0
    return {
        "agent_id": row["_agent_id"],
        "attributes": attrs,
        "group_key": None,
        "weight": weight,
        "init_state": {"target_month": "", "direction": "", "point_pct": 0.0,
                       "q9_valid": False, "synthetic": synthetic},
    }


def p_provenance(row, housing_src, ref_month: int, source_file: str,
                 synthetic: bool, donor_info=None) -> dict:
    prov = {}
    for field, col in [("age_group", "_AGE_CAT"), ("education_group", "_EDU_CAT"),
                       ("household_income_band", "_HH_INC_CAT"),
                       ("region", "_REGION_CAT"), ("state", "_STATE"),
                       ("numeracy", "_NUM_CAT")]:
        prov[field] = {"source_column": col, "source_period": ref_month,
                       "source_file": source_file, "synthetic": synthetic}
    prov["employment_status"] = {"source_column": "Q10_1..Q10_10 (priority-coded)",
                                 "source_period": ref_month, "source_file": source_file,
                                 "synthetic": synthetic}
    if housing_src is not None:
        prov["housing_tenure"] = {"source_column": "Q43 (own entry answer, carried forward)",
                                  "source_period": housing_src[1],
                                  "source_file": source_file, "synthetic": synthetic,
                                  "info_age_months": housing_src[2],
                                  "moved_since_answer": housing_src[3]}
    else:
        prov["housing_tenure"] = {"source_column": "Q43", "source_period": None,
                                  "synthetic": synthetic, "missing": True}
    if donor_info:
        prov["donor"] = donor_info
    return prov


def month_dir(target: str) -> Path:
    return OUT_DIR / target


def prev_yyyymm_of(yyyymm: int) -> int:
    y, m = yyyymm // 100, yyyymm % 100
    return (y * 100 + m - 1) if m > 1 else (y - 1) * 100 + 12


def build_real_month(target: str, yyyymm: int, df: pd.DataFrame,
                     q43_by_user: dict, d3_by_user: dict,
                     coverage_as_of: str) -> None:
    frame = df[df["date"] == yyyymm].copy()
    frame["_agent_id"] = frame["userid"].map(agent_id_for)
    by_user_all = df[df["date"] < yyyymm].groupby("userid")["date"].agg(set).to_dict()
    prev_yyyymm = prev_yyyymm_of(yyyymm)

    personas, private_rows, belief_rows = [], [], []
    entry_status_counts: Counter[str] = Counter()
    donor_pool_cache: dict | None = None

    for _, row in frame.iterrows():
        uid = int(row["userid"])
        aid = row["_agent_id"]
        tenure = row["tenure"]
        past = by_user_all.get(uid, set())
        first_ever = len(past) == 0
        if first_ever and tenure == 1:
            entry_status = "entrant"
        elif first_ever:
            entry_status = "left_boundary"
        elif prev_yyyymm in past:
            entry_status = "returning"
        else:
            # appeared before, but not in the immediately previous month
            entry_status = "gap_return"
        if not isinstance(tenure, (int, float)) or pd.isna(tenure):
            entry_status = "unknown"
        entry_status_counts[entry_status] += 1

        housing, src_m, info_age, moved = bp._housing_carry_forward(
            q43_by_user, d3_by_user, uid, yyyymm)
        housing_src = (housing, src_m, info_age, moved) if housing is not None else None

        personas.append(build_persona(row, housing, yyyymm, synthetic=False))
        private_rows.append({
            "agent_id": aid,
            "survey_entry_status": entry_status,
            "survey_tenure": int(tenure) if isinstance(tenure, (int, float)) and not pd.isna(tenure) else None,
            "core_entry_status": None,
            "p_field_provenance": p_provenance(
                row, housing_src, yyyymm,
                str(row["source_file"]), synthetic=False),
        })

        # ---- belief state ----
        hist = df[(df["userid"] == uid) & (df["date"] < yyyymm)]
        hist_valid = [r for _, r in hist.iterrows()
                      if q8_q9_summary(r)["q8_valid"] or q8_q9_summary(r)["q9_valid"]]
        available_history_n = len(hist_valid)
        prev_rows = hist[hist["date"] == prev_yyyymm]
        if len(prev_rows):
            src_row = prev_rows.iloc[-1]
            belief_rows.append({
                "agent_id": aid,
                "source_kind": "observed_previous",
                "source_period": prev_yyyymm,
                "published_at": None,
                "as_of": coverage_as_of,
                "available_history_n": available_history_n,
                "q8_q9": q8_q9_summary(src_row),
            })
        elif hist_valid:
            src_row = hist_valid[-1]
            belief_rows.append({
                "agent_id": aid,
                "source_kind": "observed_older",
                "source_period": int(src_row["date"]),
                "published_at": None,
                "as_of": coverage_as_of,
                "available_history_n": available_history_n,
                "q8_q9": q8_q9_summary(src_row),
            })
        else:
            # entrant / left boundary with no observable past answers: donor
            if donor_pool_cache is None:
                donor_pool_cache = build_donor_pool(df, yyyymm)
            donor, depth = draw_donor(row, donor_pool_cache, yyyymm)
            d_summary = q8_q9_summary(donor["row"])
            belief_rows.append({
                "agent_id": aid,
                "source_kind": "donor_initial",
                "source_period": int(donor["row"]["date"]),
                "published_at": None,
                "as_of": coverage_as_of,
                "available_history_n": 0,
                "q8_q9": d_summary,
                "donor": {
                    "donor_agent_id": donor["agent_id"],
                    "donor_period": int(donor["row"]["date"]),
                    "match_variables": ["age_group", "education_group",
                                        "household_income_band"],
                    "match_depth": depth,
                    "donor_pool_range": donor_pool_cache["range"],
                    "donor_pool_n": donor_pool_cache["n"],
                    "note": ("donor is a strictly-past first-time participant; "
                             "joint Q8xQ9 vector preserved; NOT the respondent's "
                             "own past answer; no target-month calibration"),
                },
            })

    write_month(target, personas, private_rows, belief_rows, frame,
                entry_status_counts, synthetic=False, source_note={
                    "kind": "real_micro",
                    "source_files": sorted(set(frame["source_file"])),
                    "coverage_row": coverage_row(target),
                })


def build_donor_pool(df: pd.DataFrame, yyyymm: int) -> dict:
    pool = df[(df["date"] < yyyymm) & (df["tenure"] == 1)].copy()
    pool["_agent_id"] = pool["userid"].map(agent_id_for)
    months = sorted(pool["date"].unique())
    return {"df": pool, "range": [int(months[0]), int(months[-1])],
            "n": int(len(pool))}


def draw_donor(row, pool_cache: dict, yyyymm: int):
    pool = pool_cache["df"]
    age, edu, inc = row["_AGE_CAT"], row["_EDU_CAT"], row["_HH_INC_CAT"]
    levels = [
        ("exact_age_edu_income", (pool["_AGE_CAT"] == age)
         & (pool["_EDU_CAT"] == edu) & (pool["_HH_INC_CAT"] == inc)),
        ("fallback_age_income", (pool["_AGE_CAT"] == age)
         & (pool["_HH_INC_CAT"] == inc)),
        ("fallback_age", pool["_AGE_CAT"] == age),
        ("fallback_global", pd.Series(True, index=pool.index)),
    ]
    rng = random.Random(f"{DONOR_SEED}|{yyyymm}|{int(row['userid'])}")
    for depth, mask in levels:
        cand = pool[mask]
        if len(cand) == 0:
            continue
        pick = cand.iloc[rng.randrange(len(cand))]
        return {"row": pick, "agent_id": pick["_agent_id"]}, depth
    raise ValueError("donor pool empty")


def build_synth_month(target: str, df: pd.DataFrame, q43_by_user: dict,
                      d3_by_user: dict, coverage_as_of: str) -> None:
    wave = df[df["date"] == SYNTH_SOURCE_WAVE].copy()
    wave["_agent_id"] = wave["userid"].map(agent_id_for)
    weights = wave["weight"].astype(float).clip(lower=0).fillna(1.0)
    rng = random.Random(f"{DONOR_SEED}|{target}|synthetic")
    probs = weights / weights.sum()
    drawn_idx = rng.choices(range(len(wave)), weights=probs, k=SYNTH_N)
    scale = SYNTH_N / weights.sum()

    personas, private_rows, belief_rows = [], [], []
    for i, di in enumerate(drawn_idx):
        row = wave.iloc[di]
        uid = int(row["userid"])
        donor_aid = row["_agent_id"]
        aid = syn_id_for(uid, i)
        row = row.copy()
        row["_agent_id"] = aid
        housing, src_m, info_age, moved = bp._housing_carry_forward(
            q43_by_user, d3_by_user, uid, SYNTH_SOURCE_WAVE)
        housing_src = (housing, src_m, info_age, moved) if housing is not None else None
        persona = build_persona(row, housing, SYNTH_SOURCE_WAVE, synthetic=True)
        persona["weight"] = round(float(row["weight"]) * scale, 6)
        personas.append(persona)
        private_rows.append({
            "agent_id": aid,
            "survey_entry_status": "synthetic_frame",
            "survey_tenure": None,
            "core_entry_status": None,
            "synthetic": True,
            "donor_agent_id": donor_aid,
            "donor_wave": SYNTH_SOURCE_WAVE,
            "pit_risk": "pit_risk_unverified",
            "p_field_provenance": p_provenance(
                row, housing_src, SYNTH_SOURCE_WAVE, str(row["source_file"]),
                synthetic=True,
                donor_info={"donor_agent_id": donor_aid,
                            "donor_wave": SYNTH_SOURCE_WAVE,
                            "draw": "PPS by survey weight, whole-row donor "
                                    "(joint structure preserved)"}),
        })
        belief_rows.append({
            "agent_id": aid,
            "source_kind": "simulated_previous",
            "source_period": None,
            "published_at": None,
            "as_of": coverage_as_of,
            "available_history_n": None,
            "q8_q9": None,
            "initialization_rule": (
                "2026-06 has no public micro truth. Initial beliefs are NOT "
                "pre-filled: the runner is to simulate each agent's previous-"
                "month belief state (source_kind stays simulated_previous until "
                "the Codex-side previous-period state is attached). Synthetic "
                "population frame is drawn from the 2025-10 wave (latest local "
                "micro; wave publication date unverified -> pit_risk_unverified). "
                "Only pre-as_of macro margins may calibrate; the 2026-06 target "
                "itself must not be used."),
        })

    write_month(target, personas, private_rows, belief_rows,
                pd.DataFrame({"weight": [p["weight"] for p in personas]}),
                Counter({"synthetic_frame": SYNTH_N}),
                synthetic=True, source_note={
                    "kind": "synthetic_frame",
                    "donor_wave": SYNTH_SOURCE_WAVE,
                    "draw": "PPS by survey weight with whole-row donors",
                    "pit_risk": "pit_risk_unverified",
                    "coverage_row": coverage_row(target),
                })


def coverage_row(target: str) -> dict:
    cov = json.loads((OUT_DIR / "coverage.json").read_text())
    key = f"{target[:4]}-{target[4:]}"
    return next(m for m in cov["months"] if m["target_month"] == key)


def write_month(target: str, personas, private_rows, belief_rows, frame_df,
                entry_status_counts, synthetic: bool, source_note: dict) -> None:
    from socioverse.schemas import PopulationBundle
    mdir = month_dir(target)
    mdir.mkdir(parents=True, exist_ok=True)
    cov = source_note["coverage_row"]
    as_of = cov["as_of"]

    bundle = {
        "study_id": STUDY_ID,
        "personas": personas,
        "interaction": {"kind": "none", "edges": None, "adjacency_ref": None},
        "propagation": "independent",
        "provider_ref": "sce_inflation_expectations.population",
        "provider_args": {
            "source": "frbny_sce_public_microdata_fullperiod_sample",
            "p_version": f"p_fullframe_{target}_{'synthetic' if synthetic else 'real'}_v1",
            "target_month": target,
            "as_of": as_of,
            "household_head": True,
            "normalized_weight": 1.0,
            "sampling": {
                "frame_n": len(personas),
                "actual_n": len(personas),
                "synthetic_n": len(personas) if synthetic else 0,
                "design": ("full monthly respondent frame (no subsampling); "
                           "Core selection deliberately NOT made here (frozen by "
                           "Codex); stable priorities in sampling_private.json"),
                "seed": PRIORITY_SEED,
                "source_note": source_note,
            },
            "anonymization": {
                "agent_id": "sce_|syn_ + sha256(userid|draw|salt)[:16]",
                "salt_location": "population_state_private.json (private)",
                "raw_userid_in_delivery": False,
            },
        },
        "materialized_count": len(personas),
    }
    PopulationBundle.model_validate(bundle)
    (mdir / "population.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n")

    priv = {
        "target_month": target,
        "as_of": as_of,
        "anon_salt": ANON_SALT,
        "salt_note": ("agent_id = sce_/syn_ + sha256(f\"{userid}|{salt}\")[:16]; "
                      "raw userids are never written to the delivery; this salt "
                      "is the only link and stays in this private file"),
        "entry_status_counts": dict(entry_status_counts),
        "core_entry_status": None,
        "core_note": "Core512 selection is frozen by Codex; nothing pre-selected.",
        "persons": private_rows,
    }
    (mdir / "population_state_private.json").write_text(
        json.dumps(priv, ensure_ascii=False, indent=2) + "\n")

    belief = {
        "target_month": target,
        "as_of": as_of,
        "conventions": {
            "q8": ("Q8v2 = direction code (1 up / 2 down); Q8v2part2 = signed numeric "
                   "point prediction (build_sce_evaluation_truth.py fix 20261003)"),
            "q9": "Q9_bin1..10 + official Q9_mean; validity mask independent of Q8",
            "published_at": ("null everywhere: historical SCE wave publication dates "
                             "are not verified"),
            "donor_rule": ("donor_initial donors are strictly-past first-time "
                           "participants (tenure==1, month < target), matched on "
                           f"age x education x income with recorded fallbacks; "
                           f"seed {DONOR_SEED} per (month, userid); joint Q8xQ9 "
                           "vector preserved; no target-month median calibration"),
        },
        "donor_seed": DONOR_SEED,
        "persons": belief_rows,
    }
    (mdir / "belief_state_private.json").write_text(
        json.dumps(belief, ensure_ascii=False, indent=2) + "\n")

    # ---- sampling_private.json ----
    strata_def = ["age_group", "education_group", "household_income_band"]
    per_person, cells = [], defaultdict(lambda: [0, 0.0])
    for p, pr in zip(personas, private_rows):
        a = p["attributes"]
        cell = "|".join(str(a.get(k, "missing")) for k in strata_def)
        cells[cell][0] += 1
        cells[cell][1] += p["weight"]
        per_person.append({
            "agent_id": p["agent_id"],
            "stratum": cell,
            "survey_weight": p["weight"],
            "stable_priority": stable_priority(p["agent_id"]),
            "synthetic": bool(p["init_state"].get("synthetic", False)),
        })
    wsum = sum(p["survey_weight"] for p in per_person) or 1.0
    K = 512
    for p in per_person:
        p["inclusion_probability_core_k"] = round(
            min(1.0, K * p["survey_weight"] / wsum), 8)
        p["evaluation_weight_sidecar"] = round(
            p["survey_weight"] / wsum * len(per_person), 8)
    sampling = {
        "target_month": target,
        "frame_n": len(per_person),
        "synthetic_n": sum(1 for p in per_person if p["synthetic"]),
        "strata_definition": strata_def,
        "strata": [{"stratum": k, "n": v[0],
                    "weight_sum": round(v[1], 4),
                    "N_share": round(v[0] / len(per_person), 6)}
                   for k, v in sorted(cells.items())],
        "weights": {
            "survey_weight": "FRBNY SCE respondent weight (persona.weight); "
                             "model side whitelist unchanged",
            "evaluation_weight_sidecar": "w_i / sum(w) * frame_n (diagnostics "
                                         "only; not a model input)",
        },
        "stable_priority": {
            "algorithm": "stable_priority = int(sha256("
                         "f\"{agent_id}|{PRIORITY_SALT}\")[:16], 16)",
            "salt": PRIORITY_SALT,
            "seed": PRIORITY_SEED,
            "properties": ("deterministic per agent_id; identical across months "
                           "for the same anon id; independent of frame size -> "
                           "Core selection is reproducible and frame-size "
                           "invariant; sorted order defines the draw sequence"),
        },
        "core_selection": "NOT performed (frozen by Codex)",
        "persons": per_person,
    }
    (mdir / "sampling_private.json").write_text(
        json.dumps(sampling, ensure_ascii=False, indent=2) + "\n")
    print(f"{target}: personas={len(personas)} "
          f"entry={dict(entry_status_counts)} synthetic={synthetic}")


def load_labels() -> dict[str, dict]:
    labels = {}
    for g in LABEL_GLOBS:
        for p in sorted(REPO_ROOT.glob(g)):
            for line in p.read_text().splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                row = rec.get("label", rec)
                labels[row["article_id"]] = row
    return labels


def build_news_index(target: str, labels: dict[str, dict], rules,
                     coverage_as_of: str) -> None:
    from scripts.build_sce_fullperiod_coverage import build_news_pool_tolerant
    y, m = target[:4], target[4:]
    rows, counts = build_news_pool_tolerant(
        REPO_ROOT, f"{y}-{m}", coverage_as_of, rules)
    pool = [{
        "article_id": r["article_id"],
        "pub_date": r["pub_date"][:10],
        "source_month": r["source_month"],
        "matched_keywords": r["new_hits"],
        "label": labels.get(r["article_id"]),
    } for r in rows if r["new_hits"]]
    pool.sort(key=lambda r: (r["pub_date"], r["article_id"]))
    idx = {
        "target_month": f"{y}-{m}",
        "as_of": coverage_as_of,
        "window": [previous_month(f"{y}-{m}"), f"{y}-{m}"],
        "selection": ("coverage_preparation.build_news_pool logic "
                      "(keyword recall rules v1.2); label = LLM label when present "
                      "in the union of outputs/sce_*label*/labels.jsonl + "
                      "outputs/sce_expanded_news_run_20261014_v1 parts"),
        "n_selected": len(pool),
        "n_labeled": sum(1 for r in pool if r["label"] is not None),
        "n_missing_labels": sum(1 for r in pool if r["label"] is None),
        "pool": pool,
    }
    (month_dir(target) / "news_label_index.json").write_text(
        json.dumps(idx, ensure_ascii=False, indent=2) + "\n")
    print(f"{target}: news pool={idx['n_selected']} "
          f"labeled={idx['n_labeled']} missing={idx['n_missing_labels']}")


def build_evaluation_truth(target: str, yyyymm: int | None, df: pd.DataFrame,
                           synthetic: bool) -> None:
    tdir = month_dir(target) / "evaluation_truth"
    tdir.mkdir(parents=True, exist_ok=True)
    if synthetic:
        from openpyxl import load_workbook
        wb = load_workbook(CHART_REFRESH, read_only=True, data_only=True)
        chart = {int(r[0]): list(r) for r in
                 wb["Inflation expectations"].iter_rows(min_row=5, values_only=True)
                 if isinstance(r[0], (int, float))}
        wb.close()
        row = chart[yyyymm]
        payload = {
            "manifest": {
                "status": "aggregate_only_no_micro",
                "source": "data/raw/sce_micro_refresh_20261021/chart.xlsx",
                "source_sha256": sha(CHART_REFRESH),
                "source_manifest": "data/raw/sce_micro_refresh_20261021/manifest.json",
                "extracted_at_utc": datetime.now(timezone.utc).isoformat(),
                "layer": "evaluation_only",
                "isolation": ("evaluation truth lives ONLY under evaluation_truth/; "
                              "input loaders must not read this directory"),
                "note": ("2026-06 has no public micro truth: only the official "
                         "national headline medians are delivered. No synthetic "
                         "material is passed off as truth."),
            },
            "monthly_official_aggregate": {
                "month": yyyymm,
                "official_density_median": float(row[1]),
                "official_point_median": float(row[7]),
                "series": "FRBNY SCE chart.xlsx 'Inflation expectations' "
                          "(Median one-year-ahead inflation expectations; Median "
                          "point prediction)",
            },
            "per_person": None,
        }
        (tdir / "aggregate_only.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        print(f"{target}: evaluation_truth aggregate-only "
              f"density={row[1]:.3f} point={row[7]:.3f}")
        return

    frame = df[df["date"] == yyyymm].copy()
    frame["_agent_id"] = frame["userid"].map(agent_id_for)
    per_person = []
    q8_vals, q9_vals = [], []
    for _, r in frame.iterrows():
        s = q8_q9_summary(r)
        w = float(r["weight"]) if isinstance(r["weight"], (int, float)) and not pd.isna(r["weight"]) else None
        per_person.append({
            "agent_id": r["_agent_id"],
            "weight": w,
            "q8_direction_code": s["q8_direction_code"],
            "q8_point_pct": s["q8_point_pct"],
            "q8_valid": s["q8_valid"],
            "q9_mean": s["q9_mean"],
            "q9_bins": s["q9_bins"],
            "q9_valid": s["q9_valid"],
        })
        if w and w > 0:
            if s["q8_valid"]:
                q8_vals.append((s["q8_point_pct"], w))
            if s["q9_valid"] and s["q9_mean"] is not None:
                q9_vals.append((s["q9_mean"], w))
    from studies.sce_inflation_expectations.scoring.sce_q9 import (
        weighted_empirical_quantile)
    official = _official_chart_row(CHART_AUDIT, yyyymm)
    monthly = {
        "n_respondents": int(len(frame)),
        "q8point_interp_median": (bet._interpolated_weighted_quantile(
            [q for q, _ in q8_vals], [w for _, w in q8_vals]) if q8_vals else None),
        "q9_mean_weighted_median": (weighted_empirical_quantile(
            [q for q, _ in q9_vals], [w for _, w in q9_vals], 0.5) if q9_vals else None),
        "n_with_weight_q8": len(q8_vals),
        "n_with_weight_q9_mean": len(q9_vals),
        "official_point_median": official[7] if official else None,
        "official_density_median": official[1] if official else None,
    }
    micro_path = next(REPO_ROOT / p for p, n in MICRO_FILES
                      if n == frame["source_file"].iloc[0])
    payload = {
        "manifest": {
            "source": str(micro_path.relative_to(REPO_ROOT)),
            "source_sha256": sha(micro_path),
            "chart": "data/raw/sce_audit_20260928/chart.xlsx",
            "chart_sha256": sha(CHART_AUDIT),
            "extracted_at_utc": datetime.now(timezone.utc).isoformat(),
            "months": [yyyymm],
            "n_per_person_rows": len(per_person),
            "layer": "evaluation_only",
            "isolation": ("evaluation truth lives ONLY under evaluation_truth/; "
                          "input loaders must not read this directory; target-month "
                          "SCE answers were never part of E inputs"),
            "field_fix_20261003": bet.__doc__.splitlines()[9],
            "note": "per_person uses anonymized agent_id (no raw userid)",
        },
        "monthly_full_sample": {str(yyyymm): monthly},
        "per_person": per_person,
    }
    (tdir / "micro_truth.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"{target}: evaluation_truth per_person={len(per_person)} "
          f"point={monthly['q8point_interp_median']} "
          f"(official {monthly['official_point_median']})")


def _official_chart_row(chart_path: Path, yyyymm: int):
    from openpyxl import load_workbook
    wb = load_workbook(chart_path, read_only=True, data_only=True)
    chart = {int(r[0]): list(r) for r in
             wb["Inflation expectations"].iter_rows(min_row=5, values_only=True)
             if isinstance(r[0], (int, float))}
    wb.close()
    return chart.get(yyyymm)


def main() -> int:
    print("loading micro data (3 xlsx, pandas)...", flush=True)
    df = load_micro()
    print(f"  rows={len(df)} months={df['date'].min()}..{df['date'].max()}")

    q43 = df[df["Q43"].notna()][["userid", "date", "Q43"]]
    q43_by_user = {int(u): dict(zip(g["date"], g["Q43"])) for u, g in q43.groupby("userid")}
    d3 = df[df["D3"].notna()][["userid", "date", "D3"]]
    d3_by_user = {int(u): dict(zip(g["date"], g["D3"])) for u, g in d3.groupby("userid")}

    labels = load_labels()
    rules = RecallRules(json.loads(RULE_FILE.read_text()))

    for target, yyyymm in REAL_TARGETS.items():
        cov = coverage_row(target)
        build_real_month(target, yyyymm, df, q43_by_user, d3_by_user, cov["as_of"])
        build_news_index(target, labels, rules, cov["as_of"])
        build_evaluation_truth(target, yyyymm, df, synthetic=False)

    cov = coverage_row(SYNTH_TARGET)
    build_synth_month(SYNTH_TARGET, df, q43_by_user, d3_by_user, cov["as_of"])
    build_news_index(SYNTH_TARGET, labels, rules, cov["as_of"])
    build_evaluation_truth(SYNTH_TARGET, 202606, df, synthetic=True)

    write_sources_and_readme(df)
    return 0


def write_sources_and_readme(df: pd.DataFrame) -> None:
    cov = json.loads((OUT_DIR / "coverage.json").read_text())
    total_label_gap = sum(m["news_labels_missing"] or 0 for m in cov["months"])
    sources = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "delivery": "outputs/sce_fullperiod_data_20261021_v1",
        "sample_targets": ["2019-06", "2023-03", "2026-06"],
        "sources": {
            "sce_micro": {
                "paths": [p for p, _ in MICRO_FILES],
                "sha256": {p: sha(REPO_ROOT / p) for p, _ in MICRO_FILES},
                "url": "https://www.newyorkfed.org/microeconomics/sce (frbny-sce-data.xlsx)",
                "fetched_at": "see data/raw/*/manifest.json where present; local copies",
                "conversion": ("pandas read_excel(skiprows=1); date->YYYYMM int; "
                               "persona whitelist attributes only; Q43 own-entry "
                               "carry-forward"),
                "gaps": ("historical wave published_at dates NOT verified "
                         "(micro_published_at=null everywhere); 2025-10 ref BLS "
                         "releases cancelled (shutdown); micro coverage ends "
                         "2025-10 -> 2026-06 synthetic frame"),
            },
            "sce_chart": {
                "paths": ["data/raw/sce_audit_20260928/chart.xlsx",
                          "data/raw/sce_micro_refresh_20261021/chart.xlsx"],
                "sha256": {"data/raw/sce_audit_20260928/chart.xlsx": sha(CHART_AUDIT),
                           "data/raw/sce_micro_refresh_20261021/chart.xlsx": sha(CHART_REFRESH)},
                "url": "https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/data/frbny-sce-data.xlsx",
                "use": "official national headline medians (evaluation layer only)",
            },
            "bls_initial_releases": {
                "path": "data/raw/bls_initial_releases/",
                "url": "https://www.bls.gov/news.release/archives/",
                "conversion": ("archived first-release PDFs + backfilled manifests; "
                               "CPI components re-extracted for refs missing from "
                               "components_cpi.jsonl (shadow file under "
                               "_build_support/)"),
                "gaps": ("refs 2018-06..2018-11 first releases were backfilled by the "
                         "main line (2026-10-21) with manifests; 2019-06 history is "
                         "now complete for CPI y/y and unemployment (11/11 refs). "
                         "Remaining 2019-06 gaps, all recorded in "
                         "201906/environment.json data_gaps: energy y/y @2018-10 "
                         "(custom font dropped a digit glyph -> unrecoverable) and "
                         "@2019-03; shelter y/y @2019-03; latest-ref food-at-home "
                         "y/y @2019-05; gasoline levels 2018-06..2018-11 and latest "
                         "ref y/y (EIA weekly series starts 2018-12, no 2018-05 "
                         "mean). ref 2025-10 remains permanently cancelled (data "
                         "never collected) -> 2026-06 history gap at 2025-10 for "
                         "BLS series (gasoline unaffected)"),
            },
            "eia_gasoline": {
                "paths": ["data/raw/eia_gasoline/gasoline_retail_regular_weekly.csv",
                          "data/raw/eia_gasoline_support/20261007T085903Z/gasoline_retail_regular_consolidated.csv"],
                "url": "https://fred.stlouisfed.org/series/GASREGW",
                "published_at": ("CONVENTION: last weekly observation + 3 days "
                                 "(conservative assumption, vintage_unverified)"),
                "vintage": "current_snapshot_unverified",
            },
            "nyt_archive": {
                "path": "data/raw/nyt_archive/",
                "url": "https://developer.nytimes.com/docs/archive-product/1/overview",
                "conversion": ("metadata-only archive cache; event selection per "
                               "scripts/build_nyt_events.py tiers; M-1 months "
                               "recomputed from raw cache (shadow ledger) because "
                               "events_ledger.jsonl covers only 2020-10..2021-12"),
            },
            "news_labels": {
                "paths": LABEL_GLOBS,
                "gaps": (f"total selected-but-unlabeled across all 93 target "
                         f"windows: {total_label_gap} (see coverage_summary.md); "
                         "missing labels do NOT block environment builds"),
            },
            "acs_margins": {
                "status": "MISSING",
                "note": ("ACS marginal distributions for external margin checks "
                         "were NOT sourced in this delivery (declared gap, not "
                         "fabricated)"),
            },
        },
        "reproduce_no_keys": [
            "python scripts/build_sce_fullperiod_coverage.py",
            "python scripts/build_sce_fullperiod_sample_environments.py",
            "python scripts/build_sce_fullperiod_sample_data.py",
            "pytest tests/test_sce_fullperiod_data.py -q",
        ],
    }
    (OUT_DIR / "sources.json").write_text(
        json.dumps(sources, ensure_ascii=False, indent=2) + "\n")

    readme = f"""# SCE full-period sample delivery (2019-06 / 2023-03 / 2026-06)

Phase-2 sample of the full-period data contract
(`docs/workstreams/20261021_fullperiod/kimi_data_contract_v2.md`).
`coverage.json` (phase 1, 93 months) sits in this directory unchanged.

## Layout

- `201906/`, `202303/`, `202606/` — one directory per sample month:
  - `population.json` — PopulationBundle (official schema validated), FULL monthly
    frame (201906: 1330, 202303: 1254 personas; 202606: 1300 synthetic), persona
    weight = survey weight, attributes whitelist-only, anonymized agent ids.
  - `population_state_private.json` — anon salt, survey_entry_status
    (entrant/returning/gap_return/left_boundary), tenure, P-field provenance.
  - `belief_state_private.json` — source_kind (observed_previous / observed_older /
    donor_initial / simulated_previous), Q8 (Q8v2/Q8v2part2 口径) + Q9 10-bin
    summaries, donor registrations (pool range/n, match depth, seed).
  - `sampling_private.json` — strata n/N, survey weights, evaluation-weight
    sidecar, stable priority numbers (algorithm+salt, reproducible, frame-size
    invariant). Core NOT pre-selected.
  - `environment.json` (+`external_events.json`) — EnvironmentBundle (official
    schema validated), E v2 timing (as_of = ref CPI release day 23:59:59 ET).
  - `news_label_index.json` — window news pool with per-article label status.
  - `evaluation_truth/` — micro truth (201906, 202303) or aggregate-only
    (202606, `aggregate_only_no_micro`). Isolated from inputs by convention;
    input loaders must not read it.
- `sources.json` — sources, hashes, conversions, gaps, no-key reproduce commands.
- `_build_support/` — shadow component extraction + NYT ledger used by the
  environment build (audit trail).

## Known gaps (honest list)

- 2019-06 environment: history is complete (11/11 refs) for CPI y/y and
  unemployment after the main line backfilled the 2018-06..2018-11 first
  releases (the 2018-10 CPI uses a custom font; its y/y was recovered by
  decoding the +0x1D-encoded Table A, page evidence in the signal quote).
  Remaining 2019-06 gaps, all recorded in `environment.json` data_gaps:
  energy y/y @2018-10 (the font dropped one digit glyph — unrecoverable,
  handed off) and @2019-03; shelter y/y @2019-03 (PDF layout); latest-ref
  food-at-home y/y @2019-05; gasoline level history 2018-06..2018-11 and
  latest-ref gasoline y/y (EIA weekly series starts 2018-12, no 2018-05
  mean available).
- 2026-06 environment history has a single-ref gap at 2025-10 for BLS series
  (CPI y/y, unemployment, components): October 2025 data were never collected
  (federal shutdown; stated verbatim in the 2025-11 releases). Gasoline record
  for 2025-10 IS present (EIA unaffected).
- 2023-03 environment missing one component-history value (shelter y/y,
  ref 2022-09; not extractable from the archived PDF text/tables).
- Historical SCE wave published_at dates are unverified (null everywhere).
- EIA gasoline published_at is a documented convention (last weekly obs + 3d).
- News labels: total selected-but-unlabeled = {total_label_gap} across the 93
  target windows (coverage_summary.md); per-sample-month gaps are recorded in
  each `news_label_index.json`.
- 2026-06 has no micro truth: population is synthetic (2025-10-wave donors,
  pit_risk_unverified) and evaluation truth is aggregate-only.
- ACS margin distributions not sourced (declared gap).

## Reproduce (no keys)

```bash
{chr(10).join('    ' + c for c in sources['reproduce_no_keys'])}
```
"""
    (OUT_DIR / "README.md").write_text(readme)
    print("wrote sources.json + README.md")


if __name__ == "__main__":
    sys.exit(main())
