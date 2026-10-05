"""A-line monthly SCE profile frames; questionnaire outcomes never select agents.

PopulationBundle weights are neutral. Survey and sampling weights are emitted
as a separate analysis sidecar. These retrospectively observed monthly profiles
are NOT valid B-line forecast inputs without a distinct availability contract.
"""
from __future__ import annotations

from collections import Counter
from math import isfinite

import numpy as np
import pandas as pd

STUDY_ID = "sce_inflation_expectations"
PROFILE_COLUMNS = ["date", "userid", "Q43", "D3", "_AGE_CAT", "_EDU_CAT",
                   "_HH_INC_CAT", "_REGION_CAT", "_NUM_CAT", "_STATE"] + [f"Q10_{i}" for i in range(1, 11)]
ATTRIBUTE_KEYS = {"age_group", "education_group", "household_income_band", "region",
                  "state", "numeracy", "employment_status", "housing_tenure"}
EMPLOYMENT = {1: "employed", 2: "employed", 3: "unemployed", 4: "unemployed",
              5: "on_leave", 6: "disabled", 7: "retired", 8: "student", 9: "homemaker", 10: "other"}
EMPLOYMENT_PRIORITY = [1, 2, 3, 4, 5, 7, 6, 8, 9, 10]
CATEGORY_MAPS = {
    "_EDU_CAT": ("education_group", {"High School": "high_school", "Some College": "some_college", "College": "college"}),
    "_HH_INC_CAT": ("household_income_band", {"Under 50k": "under_50k", "50k to 100k": "50k_to_100k", "Over 100k": "over_100k"}),
    "_NUM_CAT": ("numeracy", {"High": "high", "Low": "low"}),
}


def _month_index(month):
    month = int(month)
    if not 1 <= month % 100 <= 12:
        raise ValueError("invalid YYYYMM")
    return month // 100 * 12 + month % 100 - 1


def build_monthly_population(profiles, month, *, n=None, seed=42, design="independent_srs"):
    """Select current-month rows using only profile fields; return P and metadata.

    n=None selects the complete wave. A fixed size uses simple random sampling
    without replacement. independent_srs uses a month-specific RNG; stable_priority_srs
    assigns each userid a fixed pseudorandom priority, then selects the lowest n
    among the current wave. Its marginal inclusion probability remains n/N,
    while adjacent waves share the ranking. There is no panel-intersection
    requirement, no outcome trimming and no search for a favourable seed.
    """
    _month_index(month)
    if design not in {"independent_srs", "stable_priority_srs"}:
        raise ValueError("unsupported monthly sampling design")
    # Physically discard all nonwhitelisted columns before selecting or mapping.
    frame = profiles.loc[:, PROFILE_COLUMNS].copy()
    frame = frame[frame.date <= month].sort_values(["userid", "date"])
    current = frame[frame.date == month].sort_values("userid").reset_index(drop=True)
    if current.empty or current.userid.isna().any() or current.userid.duplicated().any():
        raise ValueError("monthly population needs nonempty unique userids")
    total = len(current)
    size = total if n is None else int(n)
    if not 1 <= size <= total:
        raise ValueError(f"need 1..{total} people, requested {size}")
    if size == total:
        chosen = current
    elif design == "stable_priority_srs":
        priority = [np.random.default_rng(np.random.SeedSequence([seed, int(uid)])).random()
                    for uid in current.userid]
        chosen = (current.assign(_sampling_priority=priority)
                  .sort_values(["_sampling_priority", "userid"]).head(size)
                  .drop(columns="_sampling_priority").sort_values("userid"))
    else:
        rng = np.random.default_rng(np.random.SeedSequence([seed, int(month)]))
        chosen = current.iloc[np.sort(rng.choice(total, size, replace=False))]
    housing = frame[frame.Q43.notna()].groupby("userid", sort=False).tail(1).set_index("userid")
    moves = frame[frame.D3 == 1].groupby("userid").date.max().to_dict()
    personas, housing_audit, multi_select = [], [], 0
    for row in chosen.to_dict("records"):
        uid = int(row["userid"])
        attrs = {}
        for source, target in [("_AGE_CAT", "age_group"), ("_REGION_CAT", "region"), ("_STATE", "state")]:
            if isinstance(row[source], str) and row[source].strip():
                attrs[target] = row[source]
        for source, (target, mapping) in CATEGORY_MAPS.items():
            if row[source] in mapping:
                attrs[target] = mapping[row[source]]
        selected = [code for code in EMPLOYMENT_PRIORITY if row[f"Q10_{code}"] == 1]
        if selected:
            attrs["employment_status"] = EMPLOYMENT[selected[0]]
        multi_select += int(len(selected) > 1)
        ha = {"agent_id": f"sce_u{uid}", "status": "unobserved"}
        if uid in housing.index:
            h = housing.loc[uid]
            src = int(h["date"])
            moved = moves.get(uid, src) > src
            code = {1: "owner", 2: "renter", 3: "other"}.get(int(h.Q43))
            ha.update(source_month=src, age_months=_month_index(month) - _month_index(src),
                      status="moved_since_answer" if moved else "own_past_or_current_answer")
            # An entry answer does not establish current housing after a move.
            if code is not None and not moved:
                attrs["housing_tenure"] = code
        housing_audit.append(ha)
        personas.append({"agent_id": f"sce_u{uid}", "attributes": attrs, "weight": 1.0,
                         "group_key": None, "init_state": {"target_month": "", "direction": "", "point_pct": 0.0, "q9_valid": False}})
    meta = {"research_line": "A_historical_reconstruction", "target_month": int(month),
            "design": "census" if size == total else design,
            "seed": seed, "frame_n": total, "selected_n": size,
            "inclusion_probability": size / total, "panel_intersection_required": False,
            "profile_reference_month": int(month), "housing_audit": housing_audit,
            "employment_multi_select_n": multi_select,
            "attribute_counts": {key: dict(Counter(p["attributes"].get(key, "unknown") for p in personas)) for key in sorted(ATTRIBUTE_KEYS)},
            "limitations": ["Q43 is entry-only; past own answer carried forward, omitted after a recorded move",
                            "Current-month retrospective P; not B-line forecast P", "Independent monthly runs do not validate longitudinal memory"]}
    bundle = {"study_id": STUDY_ID, "personas": personas,
              "interaction": {"kind": "none", "edges": None, "adjacency_ref": None},
              "propagation": "independent", "provider_ref": f"{STUDY_ID}.population",
              "provider_args": {"source": "frbny_sce_monthly_profile_frame",
                                "research_line": meta["research_line"], "target_month": int(month),
                                "sampling_design": meta["design"], "seed": seed}, "materialized_count": size}
    return bundle, meta


def build_analysis_weights(population, sampling_meta, survey_weights):
    """Attach evaluation weights AFTER selection; no answers or weights enter P."""
    month = sampling_meta["target_month"]
    frame = survey_weights[survey_weights.date == month]
    if frame.userid.duplicated().any():
        raise ValueError("duplicate survey weight key")
    by_id = frame.set_index("userid").weight.to_dict()
    probability = sampling_meta["inclusion_probability"]
    rows = []
    for p in population["personas"]:
        uid = int(p["agent_id"].removeprefix("sce_u"))
        weight = float(by_id[uid])
        if not isfinite(weight) or weight <= 0:
            raise ValueError("survey weights must be positive finite numbers")
        rows.append({"agent_id": p["agent_id"], "target_month": month,
                     "survey_weight": weight, "inclusion_probability": probability,
                     "analysis_weight": weight / probability})
    return rows
