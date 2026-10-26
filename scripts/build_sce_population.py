#!/usr/bin/env python3
"""Build a real-population Persona bundle by sampling U.S. respondents from the
FRBNY SCE public micro data (SocioVerse Challenge 2026, sce_inflation_expectations).

Sampling design (panel mode, the default):

- Keep records whose ``date`` (YYYYMM) is one of the target months.
- Keep only ``userid`` present in ALL target months, so the same simulated agent
  answers across months (persistent agent_id, SCE-style rotating panel).
- Draw ``n`` userids without replacement from the sorted intersection pool with
  ``random.Random(seed)``. If the pool is smaller than ``n`` the script fails
  loudly with the available count (never silently relaxes the panel rule).

P whitelist contract (docs/T02_PE_ACCEPTANCE.md, extended by this task with the
employment/housing questionnaire columns):

- persona attributes come ONLY from: ``_AGE_CAT``, ``_EDU_CAT``, ``_HH_INC_CAT``,
  ``_REGION_CAT``, ``_NUM_CAT`` (numeracy High/Low — NOT household size),
  ``_STATE``, employment (Q10 dummies, questionnaire p.11-12) and housing tenure
  (Q43, questionnaire p.32). Q43 is asked of NEW ENTRANTS ONLY (questionnaire
  p.27: Q32-Q47 are asked of new respondents); each userid has exactly one Q43
  answer on record (verified 2026-10-03: 8,536 userids, one answer each, never
  changed). The persona therefore carries the respondent's own entry answer
  forward — never borrowed from a FUTURE month. Source month, information age
  and D3 moves since the answer are recorded in the sampling metadata
  (carry-forward at or before the current month covers 99.64% of 2021
  person-months; B-line populations must additionally require the source
  record's availability date <= as_of).
- ``tenure`` in the micro file is the respondent's SCE PANEL tenure in months
  (methodology paper: "During their twelve-month tenure ... each group ..."),
  not a housing variable. It is recorded in the sampling metadata only and is
  NOT a persona attribute.
- ``weight``, ``Q8v2``, ``Q9_*`` and every other answer column NEVER enter the
  persona attributes (evaluation layer only). Persona weight is fixed at 1.0.

Outputs (same SocioVerse2 PopulationBundle shape as population/population.json):

- <out>                         PopulationBundle JSON (self-validated before write)
- <stem>.roster.jsonl           per-agent step-0 roster rows (init state)
- <stem>.sampling_meta.json     seed, source hashes, pool sizes, distributions

Example:
    python scripts/build_sce_population.py --months 202105,202106 --n 100 --seed 42 \
        --out studies/sce_inflation_expectations/population/population_real100.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = REPO_ROOT / "data" / "raw" / "sce_audit_20260928" / "micro_2020_2024.xlsx"
DEFAULT_OUT = (REPO_ROOT / "studies" / "sce_inflation_expectations" / "population"
               / "population_real100.json")
STUDY_ID = "sce_inflation_expectations"

PROFILE_COLS = ["_AGE_CAT", "_EDU_CAT", "_HH_INC_CAT", "_REGION_CAT", "_NUM_CAT", "_STATE"]
Q10_COLS = [f"Q10_{i}" for i in range(1, 11)]
READ_COLS = ["date", "userid", "tenure", "Q43", "D3"] + PROFILE_COLS + Q10_COLS

# Q10 "What is your current employment situation?" (questionnaire.pdf p.11-12).
# Multi-select dummies Q10_1..Q10_10; first matching code in this priority order wins.
EMPLOYMENT_CODE_MAP = {
    1: "employed",      # Working full-time (for someone or self-employed)
    2: "employed",      # Working part-time (for someone or self-employed)
    3: "unemployed",    # Not working, but would like to work
    4: "unemployed",    # Temporarily laid off
    5: "on_leave",      # On sick or other leave
    7: "retired",       # Retiree or early retiree
    6: "disabled",      # Permanently disabled or unable to work
    8: "student",       # Student, at school or in training
    9: "homemaker",     # Homemaker
    10: "other",        # Other
}
EMPLOYMENT_PRIORITY = [1, 2, 3, 4, 5, 7, 6, 8, 9, 10]

# Q43 "Do you (or your spouse/partner) own or rent your current primary residence?"
# (questionnaire.pdf p.32).
HOUSING_CODE_MAP = {1: "owner", 2: "renter", 3: "other"}

EDUCATION_MAP = {"High School": "high_school", "Some College": "some_college",
                 "College": "college"}
INCOME_MAP = {"Under 50k": "under_50k", "50k to 100k": "50k_to_100k",
              "Over 100k": "over_100k"}
NUMERACY_MAP = {"High": "high", "Low": "low"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _employment_code(row) -> str | None:
    selected = [i for i in range(1, 11) if row[f"Q10_{i}"] == 1]
    for code in EMPLOYMENT_PRIORITY:
        if code in selected:
            return EMPLOYMENT_CODE_MAP[code]
    return None


def _month_index(yyyymm: int) -> int:
    return (int(yyyymm) // 100) * 12 + int(yyyymm) % 100


def _housing_carry_forward(q43_by_user: dict, d3_by_user: dict, userid,
                           ref_month: int) -> tuple[str | None, int | None, int | None, bool | None]:
    """Return (housing_code, source_month, info_age_months, moved_since_answer).

    Q43 is asked of new entrants only, so the respondent's own entry answer is
    carried forward: the most recent own answer at or before ``ref_month``.
    Future answers are never used. ``moved_since_answer`` flags any D3==1
    (moved) record strictly between the answer month and ``ref_month``.
    """
    hist = q43_by_user.get(userid)
    if not hist:
        return None, None, None, None
    past = [m for m in hist if m <= ref_month]
    if not past:
        return None, None, None, None
    src = max(past)
    moved = any(v == 1 for m, v in d3_by_user.get(userid, {}).items()
                if src < m <= ref_month)
    return (HOUSING_CODE_MAP.get(int(hist[src])), src,
            _month_index(ref_month) - _month_index(src), moved)


def _load_frame(data_path: Path):
    import pandas as pd

    if not data_path.exists():
        sys.exit(f"micro data not found: {data_path}")
    df = pd.read_excel(data_path, skiprows=1, usecols=READ_COLS)
    df["userid"] = df["userid"].astype(int)
    return df


def build_from_frame(df, months: list[int], n: int, seed: int,
                     data_path: Path | None = None) -> tuple[dict, list[dict], dict]:

    months_by_user = df[df["date"].isin(months)].groupby("userid")["date"].nunique()
    pool = sorted(int(u) for u in months_by_user[months_by_user == len(months)].index)
    per_month = {int(m): int((df["date"] == m).sum()) for m in months}
    if len(pool) < n:
        sys.exit(f"panel pool too small: need {n} userids present in ALL months "
                 f"{months}, only {len(pool)} available (per-month rows: {per_month}). "
                 "Lower --n or widen --months; refusing to relax the panel rule.")

    q43 = df[df["Q43"].notna()][["userid", "date", "Q43"]]
    q43_by_user = {int(u): dict(zip(g["date"], g["Q43"])) for u, g in q43.groupby("userid")}
    d3 = df[df["D3"].notna()][["userid", "date", "D3"]]
    d3_by_user = {int(u): dict(zip(g["date"], g["D3"])) for u, g in d3.groupby("userid")}
    ref_month = months[0]  # personas are static; per-month re-anchoring is D046 future work

    drawn = random.Random(seed).sample(pool, n)
    base = df[df["date"] == months[0]].set_index("userid")

    personas, roster = [], []
    borrow_counts: Counter[str] = Counter()
    housing_prov: list[dict] = []
    dist: dict[str, Counter] = {k: Counter() for k in
                                ["age_group", "education_group", "household_income_band",
                                 "region", "state", "numeracy", "employment_status",
                                 "housing_tenure"]}
    for uid in drawn:
        row = base.loc[uid]
        attrs: dict = {}
        age = row["_AGE_CAT"]
        if isinstance(age, str):
            attrs["age_group"] = age           # "Under 40" / "40 to 60" / "Over 60"
            dist["age_group"][attrs["age_group"]] += 1
        edu = row["_EDU_CAT"]
        if isinstance(edu, str) and edu in EDUCATION_MAP:
            attrs["education_group"] = EDUCATION_MAP[edu]
            dist["education_group"][attrs["education_group"]] += 1
        inc = row["_HH_INC_CAT"]
        if isinstance(inc, str) and inc in INCOME_MAP:
            attrs["household_income_band"] = INCOME_MAP[inc]
            dist["household_income_band"][attrs["household_income_band"]] += 1
        region = row["_REGION_CAT"]
        if isinstance(region, str):
            attrs["region"] = region
            dist["region"][region] += 1
        state = row["_STATE"]
        if isinstance(state, str):
            attrs["state"] = state
            dist["state"][state] += 1
        num = row["_NUM_CAT"]
        if isinstance(num, str) and num in NUMERACY_MAP:
            attrs["numeracy"] = NUMERACY_MAP[num]   # _NUM_CAT = numeracy, NOT household size
            dist["numeracy"][attrs["numeracy"]] += 1
        emp = _employment_code(row)
        if emp is not None:
            attrs["employment_status"] = emp
            dist["employment_status"][emp] += 1
        housing, src_month, info_age, moved = _housing_carry_forward(
            q43_by_user, d3_by_user, uid, ref_month)
        if housing is not None:
            attrs["housing_tenure"] = housing
            dist["housing_tenure"][housing] += 1
            borrow_counts["own_answer_le_base_month"] += 1
            housing_prov.append({"userid": uid, "source_month": int(src_month),
                                 "info_age_months": int(info_age),
                                 "moved_since_answer": bool(moved)})
        else:
            borrow_counts["missing"] += 1

        agent_id = f"sce_u{uid}"
        personas.append({
            "agent_id": agent_id,
            "attributes": attrs,
            "group_key": None,
            "weight": 1.0,
            "init_state": {"target_month": "", "direction": "", "point_pct": 0.0,
                           "q9_valid": False},
        })
        roster.append({
            "agent_id": agent_id,
            "step": 0,
            "state": {"target_month": "", "direction": "", "magnitude_pct": 0.0,
                      "point_pct": 0.0, "q9_valid": False,
                      "validation_status": "not_answered", "q9_sum": 0.0,
                      "e_snapshot_id": "", "reason": "",
                      **{f"q9_bin{i}": 0.0 for i in range(1, 11)}},
            "action_kind": None,
            "action_payload": {},
        })

    meta = {
        "study_id": STUDY_ID,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "target_months": months,
        "panel_mode": True,
        "n_sampled": n,
        "candidate_pool": {"per_month_rows": per_month, "panel_intersection": len(pool)},
        "sampled_userids": drawn,
        "source_files": ([{"path": str(data_path.relative_to(REPO_ROOT)),
                           "sha256": _sha256(data_path),
                           "rows_total": int(len(df))}] if data_path else []),
        "whitelist_note": ("persona attributes use only profile categorical columns "
                           "(_AGE_CAT/_EDU_CAT/_HH_INC_CAT/_REGION_CAT/_NUM_CAT/_STATE), "
                           "Q10 employment dummies and Q43 housing tenure; weight, Q8v2, "
                           "Q9_* and all other answer columns never enter attributes"),
        "field_mappings": {
            "employment_status": {"source": "Q10_1..Q10_10 dummies",
                                  "questionnaire": "Q10, questionnaire.pdf p.11-12",
                                  "code_map": {str(k): v for k, v in EMPLOYMENT_CODE_MAP.items()},
                                  "multi_select_priority": EMPLOYMENT_PRIORITY},
            "housing_tenure": {"source": "Q43, asked of new entrants only "
                               "(questionnaire p.27/p.32); own entry answer "
                               "carried forward, never from future months",
                               "questionnaire": "Q43, questionnaire.pdf p.32",
                               "code_map": {str(k): v for k, v in HOUSING_CODE_MAP.items()},
                               "ref_month": ref_month,
                               "coverage": dict(borrow_counts),
                               "provenance": housing_prov,
                               "b_line_note": ("B-line builds must additionally require the "
                                               "source record's availability date <= as_of")},
            "numeracy": {"source": "_NUM_CAT (derived numeracy category; NOT household size)"},
            "tenure_column": ("micro-data 'tenure' = SCE panel tenure in months "
                              "(methodology.pdf); recorded here, not a persona attribute"),
        },
        "attribute_distributions": {k: dict(sorted(v.items())) for k, v in dist.items()},
        "panel_tenure_months_distribution": dict(
            sorted(Counter(int(x) for x in df[df["userid"].isin(drawn)]
                           .groupby("userid")["tenure"].max()).items())),
    }
    bundle = {
        "study_id": STUDY_ID,
        "personas": personas,
        "interaction": {"kind": "none", "edges": None, "adjacency_ref": None},
        "propagation": "independent",
        "provider_ref": "sce_inflation_expectations.population",
        "provider_args": {
            "source": "frbny_sce_public_microdata_2020_2024",
            "p_version": f"p_real{n}_{'m'.join(str(m) for m in months)}_seed{seed}_v1",
            "household_head": True,
            "normalized_weight": 1.0,
            "sampling": {k: meta[k] for k in ("seed", "target_months", "panel_mode",
                                              "n_sampled", "candidate_pool")},
        },
        "materialized_count": len(personas),
    }
    return bundle, roster, meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--months", default="202105,202106",
                    help="comma-separated YYYYMM target months (default 202105,202106)")
    ap.add_argument("--n", type=int, default=100, help="panel size to draw (default 100)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA, help="micro xlsx path")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="population JSON output")
    args = ap.parse_args(argv)

    months = [int(m) for m in args.months.split(",") if m.strip()]
    if not months:
        sys.exit("--months must list at least one YYYYMM")
    df = _load_frame(args.data)
    bundle, roster, meta = build_from_frame(df, months, args.n, args.seed,
                                            data_path=args.data)

    from socioverse.schemas import PopulationBundle
    PopulationBundle.model_validate(bundle)  # hard gate before writing

    out: Path = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    stem = out.with_suffix("")
    out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (stem.parent / f"{stem.name.replace('population_', 'roster_')}.jsonl").open(
            "w", encoding="utf-8") as fh:
        for row in roster:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    meta_path = stem.parent / f"{stem.name}.sampling_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    print(f"wrote {out} ({len(bundle['personas'])} personas), roster + {meta_path.name}")
    print(f"panel pool {meta['candidate_pool']['panel_intersection']} "
          f"(months {months}), housing coverage: {meta['field_mappings']['housing_tenure']['coverage']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
