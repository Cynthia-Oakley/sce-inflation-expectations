"""Independent offline checks and reuse of already-paid baseline responses."""
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .prior_belief_preparation import (
    ARMS, MONTHS, add_prior, dump, eligible_previous, month_offset, prior_record, sha, valid_bins,
)
from .prior_belief_trial_preparation import _metric
from .scoring.sce_q9_frozen import score_q9_frozen


def verify(root, trial, out):
    root, trial, out = (Path(p).resolve() for p in (root, trial, out))
    if out.exists() or not out.is_relative_to(root / "outputs"):
        raise ValueError("Use a fresh ignored verification directory")
    plan = json.loads((trial / "summary.json").read_text())
    for name, h in plan["output_file_sha256"].items():
        if sha(trial / name) != h:
            raise ValueError("Prepared file drift")
    for name, h in {**plan["source_sha256"], **plan["code_sha256"]}.items():
        if sha(root / name) != h:
            raise ValueError("Preparation source or code drift")
    protected = json.loads((root / "docs/sources/sol_handoff_protected_files_20261010.json").read_text())["files_sha256"]
    if any(sha(root / n) != h for n, h in protected.items()):
        raise ValueError("Protected pending files changed")
    cases = [json.loads(s) for s in (trial / "candidate_cases_private.jsonl").read_text().splitlines()]
    selected = json.loads((trial / "selection_links_private.json").read_text())
    index = {(int(r["date"]), int(r["userid"])): r for r in pd.read_parquet(trial / "labeled_reference_private.parquet").to_dict("records")}
    source = root / "outputs/sce_confidence_trial_20261011_v1"
    old_plan = json.loads((source / "trial_manifest.json").read_text())
    source_by_month = {m: {r["agent_id"]: r for r in json.loads((source / m / "preview_national_confidence.json").read_text())} for m in MONTHS}
    links = {(r["month"], r["agent_id"]): r for r in selected}
    originals = {(r["month"], r["base_agent_id"]): r for r in selected}
    checks = Counter()
    if len(cases) != 288 or len({c["case_id"] for c in cases}) != len(cases):
        raise ValueError("Case count or duplicate")
    cells = Counter((c["target_month"], c["arm"], c["repeat"]) for c in cases)
    if len(cells) != 24 or set(cells.values()) != {12}:
        raise ValueError("Arm/repeat/month coverage")
    for c in cases:
        m, sid = c["target_month"], c["agent_id"]
        link = links[(m, sid)]
        base = source_by_month[m][link["base_agent_id"]]["messages"]
        if c["arm"] == "no_prior":
            expected = base
        else:
            donor = link if c["arm"] == "own_previous" else originals[(m, link["permuted_base_agent_id"])]
            row = index[(month_offset(m, -1), donor["source_userid"])]
            expected, _ = add_prior(base, prior_record(row), int(m))
            # Metamorphic test of the actual selector: replace only target
            # answers and weights, then check that prior eligibility is unchanged.
            current = index[(int(m), link["source_userid"])]
            shadow = dict(current)
            shadow["Q8v2part2"], shadow["weight"] = -99.0, 999999.0
            for i in range(1, 11):
                shadow[f"Q9_bin{i}"] = 100.0 if i == 10 else 0.0
            own_row = index[(month_offset(m, -1), link["source_userid"])]
            cutoff = pd.Timestamp(plan["months"][m]["as_of"]).date()
            if not eligible_previous(current, own_row, int(m), cutoff) or not eligible_previous(shadow, own_row, int(m), cutoff):
                raise ValueError("Target answer or weight affected prior selection")
            checks["target_answer_and_weight_selector_mutation"] += 1
            checks["prior_source_calendar_and_person_binding"] += 1
        if c["messages"] != expected:
            raise ValueError("Unexpected P/E, question or prior content")
        digest = hashlib.sha256(json.dumps(c["messages"], ensure_ascii=False).encode()).hexdigest()
        if digest != c["prompt_sha256"]:
            raise ValueError("Message hash drift")
        checks["exact_complete_message_rebuild"] += 1
    reused = {}
    sources = {}
    for m in MONTHS:
        repeated = []
        for repeat in (1, 2):
            job = next(j for j in old_plan["jobs"] if j["month"] == m and j["arm"] == "national_confidence" and j["repeat"] == repeat)
            file = root / "outputs/local_runs" / job["run_id"] / "llm_calls.jsonl"
            sources[str(file.relative_to(root))] = sha(file)
            calls = {c["agent_id"]: c for c in map(json.loads, file.read_text().splitlines())}
            priors, actual, sims, models = [], [], [], Counter()
            n_excluded = 0
            for link in [r for r in selected if r["month"] == m]:
                call = calls[link["base_agent_id"]]
                original = source_by_month[m][link["base_agent_id"]]
                if call["prompt_sha256"] != original["prompt_sha256"] or call["temperature"] != .5:
                    raise ValueError("Old baseline did not use the exact candidate no-prior message")
                if call.get("error") or call["attempt_idx"] != 0:
                    raise ValueError("Old baseline call failure or unexpected retry")
                body = json.loads(call["raw_response_text"])
                response = body if "q9" in body else json.loads(body["choices"][0]["message"]["content"])
                p = [response["q9"][f"bin{i}"] for i in range(1, 11)]
                old = index[(month_offset(m, -1), link["source_userid"])]
                now = index[(int(m), link["source_userid"])]
                current = [now[f"Q9_bin{i}"] for i in range(1, 11)]
                if not valid_bins(p) or not valid_bins(current):
                    n_excluded += 1
                    continue
                scored = [score_q9_frozen(x).mean for x in [list(prior_record(old)["q9"].values()), current, p]]
                if any(x is None or not np.isfinite(x) for x in scored):
                    n_excluded += 1
                    continue
                priors.append(scored[0]); actual.append(scored[1]); sims.append(scored[2])
                models[str(call["returned_model"])] += 1
            repeated.append({"repeat": repeat, "same_valid_people": len(actual), "excluded_n": n_excluded,
                "no_update_personal_prior": _metric(priors, actual),
                "already_run_no_prior_LLM": _metric(sims, actual), "returned_model_counts": dict(models),
                "comparison_scope": "Historical same-message diagnostic; not a newly contemporaneous randomized model experiment"})
        reused[m] = repeated
    matched_payloads_identical = 0
    for r in selected:
        own = prior_record(index[(month_offset(r["month"], -1), r["source_userid"])])
        other = originals[(r["month"], r["permuted_base_agent_id"])]
        alternate = prior_record(index[(month_offset(r["month"], -1), other["source_userid"])])
        matched_payloads_identical += own == alternate
    out.mkdir(parents=True)
    report = {"status": "independent_offline_checks_and_existing_response_reuse_completed", "new_api_calls": 0,
        "preparation": str(trial.relative_to(root)), "preparation_sha256": sha(trial / "summary.json"),
        "candidate_requests_verified": len(cases), "respondent_months": len(selected), "cell_count": len(cells),
        "checks": dict(checks), "protected_files_unchanged": len(protected),
        "own_and_permuted_prior_payloads_identical_n": matched_payloads_identical,
        "reused_original_responses": reused, "existing_call_file_sha256": sources,
        "limitations": ["This verifies preparation and computes existing baselines, not a new simulation effect.",
                        "The main equal-weight sample is age balanced, not a national estimate.",
                        "Historical B inputs remain unapproved; no stateful runtime is connected."]}
    dump(out / "verification.json", report)
    print(json.dumps({"checks": dict(checks), "candidate_requests": len(cases), "new_api_calls": 0}))
    return report
