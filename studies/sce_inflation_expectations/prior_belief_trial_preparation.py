"""Prepare a disclosed A-line prior intervention and initialization inventory.

No network, credential lookup, model provider or paid execution entry point.
The source microdata and candidate messages remain in ignored local outputs.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance

from .prior_belief_preparation import (
    ARMS, MATCH, MONTHS, MARKER, PRIOR_MARKER, add_prior, derangement, dump, eligible_previous,
    entry_inventory, load_reference, matched_entry_pool, month_offset, prior_record,
    sha, signed_point, summarize_panel,
)
from .scoring.sce_q9_frozen import provenance, score_q9_frozen

SEED = 20261013
AGES = ("Under 40", "40 to 60", "Over 60")


def _priority(month, aid, label):
    return hashlib.sha256(f"{SEED}|{month}|{aid}|{label}".encode()).hexdigest()


def _summary(values):
    x = np.asarray(values, float)
    return {"n": len(x), "median_pp": float(np.median(x)),
            "cross_person_IQR_pp": float(np.quantile(x, .75) - np.quantile(x, .25))}


def _metric(pred, real):
    pred, real = np.asarray(pred, float), np.asarray(real, float)
    if len(pred) != len(real) or not np.isfinite(pred).all() or not np.isfinite(real).all():
        raise ValueError("Paired finite baseline arrays required")
    if not len(pred):
        return {"n": 0, "status": "no_valid_evaluation_pairs"}
    return {"n": len(pred), "center_absolute_error_pp": float(abs(np.median(pred) - np.median(real))),
            "individual_MAE_pp": float(np.mean(abs(pred - real))),
            "W1_pp": float(wasserstein_distance(pred, real)),
            "predicted_cross_person_IQR_pp": _summary(pred)["cross_person_IQR_pp"],
            "real_cross_person_IQR_pp": _summary(real)["cross_person_IQR_pp"]}


def prepare(root, out, reference_cache=None):
    root, out = Path(root).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(root / "outputs"):
        raise ValueError("Use a fresh ignored output directory")
    protected = json.loads((root / "docs/sources/sol_handoff_protected_files_20261010.json").read_text())["files_sha256"]
    if any(sha(root / p) != h for p, h in protected.items()):
        raise ValueError("Protected pending work changed")
    scorer = provenance()
    if not scorer["live_matches_pinned"]:
        raise ValueError("Frozen scorer drift")
    out.mkdir(parents=True)
    frame, panel_summary = summarize_panel(load_reference(root, out, reference_cache), MONTHS)
    frame.to_parquet(out / "labeled_reference_private.parquet", index=False)
    index = {(int(r["date"]), int(r["userid"])): r for r in frame.to_dict("records")}
    source = root / "outputs/sce_confidence_trial_20261011_v1"
    old_plan = json.loads((source / "trial_manifest.json").read_text())
    used = {"trial_manifest.json", "evaluation_links_private.json"}

    def frozen(name):
        path = source / name
        if name != "trial_manifest.json" and sha(path) != old_plan["prepared_file_sha256"][name]:
            raise ValueError("Frozen P/E or preview changed: " + name)
        used.add(name)
        return json.loads(path.read_text())

    links = frozen("evaluation_links_private.json")
    selection, cases, initialization, support, baselines = [], [], [], [], {}
    months = {}
    for month in MONTHS:
        part = out / month
        part.mkdir()
        population = frozen(f"{month}/population.json")
        frozen(f"{month}/environment.json")
        frozen(f"{month}/simulation_national_confidence.json")
        originals = {p["agent_id"]: p for p in frozen(f"{month}/preview_national_confidence.json")}
        profiles = {p["agent_id"]: p["attributes"] for p in population["personas"]}
        mapping = {r["agent_id"]: int(r["source_agent_id"].removeprefix("sce_u"))
                   for r in links if r["month"] == month}
        cutoff = datetime.fromisoformat(old_plan["metadata"][month]["as_of"])
        eligible, statuses, previous = [], Counter(), {}
        for aid in sorted(profiles):
            row = index[(int(month), mapping[aid])]
            statuses[row["panel_status"]] += 1
            old = index.get((month_offset(month, -1), mapping[aid]))
            if eligible_previous(row, old, int(month), cutoff.date()):
                eligible.append(aid)
                previous[aid] = old
        selected = []
        for age in AGES:
            group = [a for a in eligible if profiles[a].get("age_group") == age]
            group.sort(key=lambda a: _priority(month, a, "sample"))
            if len(group) < 4:
                raise ValueError("Fewer than four previous-Q9-supported people in an age group")
            selected.extend(group[:4])
        selected.sort()
        perm = derangement(selected, SEED + int(month))
        eligibility_by_age = dict(Counter(profiles[a].get("age_group", "unknown") for a in eligible))
        original_rows = frame.loc[frame.date.eq(int(month))]
        pool = entry_inventory(frame, int(month))
        lag_pool = entry_inventory(frame, int(month), month_offset(month, -10))
        pool.to_parquet(part / "historical_entrant_donor_bank_private.parquet", index=False)
        fresh = [a for a in profiles if index[(int(month), mapping[a])]["panel_status"] == "entry_tenure_1"]
        for aid in sorted(fresh):
            current = index[(int(month), mapping[aid])]
            donors, keys = matched_entry_pool(pool, current)
            rec = {"target_month": month, "agent_id": aid, "matching_fields": keys,
                   "donor_n": len(donors), "status": "unknown" if keys is None else "synthetic_initial_belief_candidate",
                   "research_line": "A_historical_donor_preparation_only", "b_pit_approved": False}
            if keys is not None:
                donors = donors.sort_values(["date", "userid"])
                weights = donors.weight.to_numpy(float)
                rng = np.random.default_rng(int(_priority(month, aid, "initialization")[:16], 16))
                donor = donors.iloc[rng.choice(len(donors), p=weights / weights.sum())].to_dict()
                rec.update({"donor_reference_month": int(donor["date"]), "joint_belief": prior_record(donor),
                            "transport_assumption": "Historical entrant conditional distribution retained without macro-level shifting",
                            "not_the_new_respondent_actual_answer": True})
            initialization.append(rec)
        for aid in sorted(profiles):
            current = index[(int(month), mapping[aid])]
            donors, keys = matched_entry_pool(pool, current)
            support.append({"month": month, "agent_id": aid, "matching_fields": keys, "donor_n": len(donors)})
        previews = {a: [] for a in ARMS}
        for n, aid in enumerate(selected, 1):
            sid = f"prior_{month}_{n:03d}"
            row = index[(int(month), mapping[aid])]
            old, shuffled = previous[aid], previous[perm[aid]]
            base = originals[aid]["messages"]
            # Recalculate the exact content hash used in the original trial.
            old_hash = hashlib.sha256(json.dumps(base, ensure_ascii=False).encode()).hexdigest()
            if old_hash != originals[aid]["prompt_sha256"]:
                raise ValueError("Original message hash is not reproducible")
            selection.append({"month": month, "agent_id": sid, "base_agent_id": aid,
                              "source_userid": mapping[aid], "permuted_base_agent_id": perm[aid]})
            previous_payloads = {"own_previous": prior_record(old), "permuted_previous": prior_record(shuffled)}
            variants = {"no_prior": base}
            for arm in ARMS[1:]:
                variants[arm], block = add_prior(base, previous_payloads[arm], int(month))
                if variants[arm][0]["content"].replace(block, "", 1) != base[0]["content"]:
                    raise ValueError("Common P/E or question changed")
                if variants[arm][0]["content"].split(MARKER, 1)[1] != base[0]["content"].split(MARKER, 1)[1]:
                    raise ValueError("Questionnaire changed")
            for arm in ARMS:
                messages = variants[arm]
                text = json.dumps(messages, ensure_ascii=False)
                if any(term in text for term in [aid, sid, f"sce_u{mapping[aid]}", "Q9_mean", '"weight"', '"userid"']):
                    raise ValueError("Internal identity or evaluation field in message")
                if (PRIOR_MARKER in messages[0]["content"]) != (arm != "no_prior"):
                    raise ValueError("Prior assignment mismatch")
                digest = hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()
                previews[arm].append({"agent_id": sid, "messages": messages, "prompt_sha256": digest})
                for repeat in (1, 2):
                    cases.append({"case_id": f"{sid}_{arm}_r{repeat}", "target_month": month,
                                  "agent_id": sid, "arm": arm, "repeat": repeat, "messages": messages,
                                  "prompt_sha256": digest, "research_line": "A_observed_prior_conditional_update"})
        for arm in ARMS:
            dump(part / f"preview_{arm}.json", previews[arm])
        selected_statuses = Counter(index[(int(month), mapping[a])]["panel_status"] for a in selected)
        prior_values, actual_values, scored_priors, scored_actual = [], [], [], []
        q8_pred, q8_real = [], []
        for aid in selected:
            now = index[(int(month), mapping[aid])]
            old = previous[aid]
            if np.isfinite(now["Q9_mean"]) and np.isfinite(old["Q9_mean"]):
                prior_values.append(float(old["Q9_mean"])); actual_values.append(float(now["Q9_mean"]))
            if now["raw_prior_valid"]:
                a = score_q9_frozen([old[f"Q9_bin{i}"] for i in range(1, 11)])
                b = score_q9_frozen([now[f"Q9_bin{i}"] for i in range(1, 11)])
                if a.mean is not None and b.mean is not None and np.isfinite(a.mean) and np.isfinite(b.mean):
                    scored_priors.append(a.mean); scored_actual.append(b.mean)
            p, r = signed_point(old["Q8v2part2"]), signed_point(now["Q8v2part2"])
            if p is not None and r is not None:
                q8_pred.append(p); q8_real.append(r)
        baselines[month] = {"official_derived_q9_personal_means_prior_persistence": _metric(prior_values, actual_values),
                           "same_frozen_scorer_raw_prior_persistence": _metric(scored_priors, scored_actual),
                           "q8_prior_persistence": _metric(q8_pred, q8_real) if q8_real else None,
                           "scope": "Equal-weight selected returning sample, not national headline or B forecast"}
        selected_dates = [index[(int(month), mapping[a])]["survey_date"] for a in selected]
        months[month] = {"as_of": cutoff.isoformat(), "original_sample_n": len(profiles),
            "original_sample_status_counts": dict(statuses), "valid_adjacent_prior_n": len(eligible),
            "eligible_by_age": eligibility_by_age, "selected_n": len(selected),
            "selected_age_counts": dict(Counter(profiles[a]["age_group"] for a in selected)),
            "selected_status_counts": dict(selected_statuses),
            "selected_current_surveys_before_E_cutoff_n": sum(d.date() < cutoff.date() for d in selected_dates if pd.notna(d)),
            "selected_current_date_unknown_n": sum(pd.isna(d) for d in selected_dates),
            "target_new_entrant_n": int(original_rows.panel_status.eq("entry_tenure_1").sum()),
            "historical_entrant_12m_bank_n": len(pool), "original_48_new_entrant_n": len(fresh),
            "initialization_match_level_counts": dict(Counter("+".join(r["matching_fields"]) if r["matching_fields"] is not None else "unknown" for r in support if r["month"] == month)),
            "b_lag_screen_candidate_bank_n": len(lag_pool), "b_historical_version_certified": False}
        print("Prepared prior inputs", month, len(eligible), "eligible;", len(selected), "selected", flush=True)
    dump(out / "selection_links_private.json", selection)
    dump(out / "entry_initialization_candidates_private.json", initialization)
    dump(out / "entry_matching_support_private.json", support)
    (out / "candidate_cases_private.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in cases))
    for month in MONTHS:
        ids = [r for r in selection if r["month"] == month]
        if sorted(r["base_agent_id"] for r in ids) != sorted(r["permuted_base_agent_id"] for r in ids):
            raise ValueError("Permutation changes prior inventory")
    ledger = {"status": "historical_B_not_certified", "micro_release_rule": "Official core microdata lag is nine months",
        "official_rule_url": "https://www.newyorkfed.org/microeconomics/sce/sce-faq",
        "rule_is_not_a_first_release_timestamp": True,
        "lag_screen": "target minus 10 observation months, conservative candidate inventory only",
        "original_workbook_version": "Current downloaded bytes, not demonstrated historical vintages",
        "eligible_historical_B_input_files": [],
        "same_person_t_minus_1_is_unavailable_in_historical_B": True,
        "prospective_use": "Current files can be snapshotted for a future forecast after documented current availability; this does not certify past cutoffs",
        "per_month": {m: {"as_of": months[m]["as_of"], "candidate_latest_observation": month_offset(m, -10),
                          "candidate_bank_n": months[m]["b_lag_screen_candidate_bank_n"], "published_at": None,
                          "vintage_certified": False, "gate": "unknown_historical_version"} for m in MONTHS}}
    dump(out / "b_availability_ledger.json", ledger)
    summary = {"status": "offline_inputs_and_inventory_completed_no_simulation", "new_api_calls": 0,
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(), "research_line": "A_observed_prior_conditional_update",
        "months": months, "panel": panel_summary, "n_respondent_months": len(selection), "arms": list(ARMS),
        "candidate_requests": len(cases), "repeats": [1, 2], "sampling_seed": SEED,
        "proposed_model": "deepseek-flash; exact current provider/version to verify before paid run", "proposed_temperature": .5,
        "prior_representation": "Verbatim t-1 Q8 signed point (optional) and raw ten-bin probabilities; controlled reminder",
        "no_target_answer_based_sampling": True, "own_prior_permutation_fixed_points": 0,
        "shared_messages_questionnaire_and_PE_preserved": True,
        "baseline_diagnostics": baselines, "scorer": scorer, "B_availability": ledger,
        "initialization_candidates": {"n": len(initialization), "supported_n": sum(r["matching_fields"] is not None for r in initialization),
                                     "joint_empirical_donor_used": True, "current_target_answer_used": False, "runtime_connected": False},
        "limitations": ["Previously examined development periods; no blind holdout registered.",
            "Four per age group are a mechanism probe, not a nationally representative sample.",
            "Current E is a fixed information treatment; some actual respondents answered before its cutoff.",
            "Exact prior reminder is an information intervention, not proof of natural memory.",
            "Equal-weight permutation preserves the stock of priors, not a survey-weighted stock.",
            "Initialization is a historical conditional donor candidate; no regime shift correction, no certified historical B vintage.",
            "Own prior persistence can improve levels without reproducing learning or rational updates.",
            "Two repeats are candidate generations, not two new populations or provider-controlled random seeds."],
        "next_gates": ["Review the full prior reminder and initialization assumptions", "Implement and validate an isolated runner",
                       "Confirm sending scope including real t-1 answers and a new specific budget", "Register a separate holdout before tuning"],
        "source_sha256": {str((source / p).relative_to(root)): sha(source / p) for p in sorted(used)},
        "code_sha256": {str(p.relative_to(root)): sha(p) for p in [Path(__file__), root / 'studies/sce_inflation_expectations/prior_belief_preparation.py', root / 'scripts/prepare_sce_prior_trial.py']},
        "output_file_sha256": {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()}}
    dump(out / "summary.json", summary)
    print(json.dumps({"output": str(out), "people_months": len(selection), "candidate_requests": len(cases), "new_api_calls": 0}))
    return summary
