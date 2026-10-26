"""Evaluation adapters for the seven-month, five-arm news mechanism trial."""
from __future__ import annotations

import json
from pathlib import Path

from ..experiments.frozen_batch import ROOT, dump, read_json, sha
from . import cognition as shared


def evaluation_inputs(a82_cases, selected_ids, months, repeats):
    selected = [row for row in a82_cases if row["month"] in months and row["agent_id"] in selected_ids]
    expected = {(month, agent_id) for month in months for agent_id in selected_ids}
    if {(row["month"], row["agent_id"]) for row in selected} != expected or len(selected) != len(expected):
        raise ValueError("missing A82 support or duplicate original person-month")
    if any(row["repeat"] != 1 for row in selected):
        raise ValueError("A82 reference must remain its single original generation")
    links, truth = [], []
    for row in selected:
        links.append({
            "month": row["month"], "agent_id": row["agent_id"], "userid": row["userid"],
            "profile": row["profile"], "stratum": row["stratum"],
            "survey_weight": row["survey_weight"], "design_survey_weight": row["survey_weight"],
        })
        for repeat in repeats:
            truth.append({"month": row["month"], "agent_id": row["agent_id"], "repeat": repeat, "real": row["real"]})
    return links, truth, selected


def attach_evaluation(package, a82_path, root=ROOT):
    package = Path(package).resolve()
    a82_path = Path(a82_path).resolve()
    root = Path(root)
    protocol = read_json(package / "protocol.json")
    manifest = read_json(package / "manifest.json")
    if manifest["status"] != "prepared_requires_engine_checks_and_new_authorization":
        raise ValueError("evaluation can attach only once before engine checks")
    prompt_hashes = {str(path.relative_to(package)): sha(path) for path in package.glob("*/prompts_*.json")}
    a82_cases = read_json(a82_path)
    links, truth, selected = [], [], []
    for month in protocol["months"]:
        rows = read_json(package / str(month) / f"prompts_{protocol['arms'][0]}.json")["rows"]
        month_links, month_truth, month_a82 = evaluation_inputs(
            a82_cases, set(rows), [month], protocol["generation_repeats"])
        links.extend(month_links)
        truth.extend(month_truth)
        selected.extend(month_a82)
    dump(package / "evaluation_links_private.json", links)
    dump(package / "a82_reference_private.json", selected)
    truth_dir = package / "evaluation_truth"
    truth_dir.mkdir(exist_ok=False)
    dump(truth_dir / "cases_private.json", truth)
    protocol["evaluation_truth"] = str((truth_dir / "cases_private.json").relative_to(root))
    dump(package / "protocol.json", protocol)
    manifest["protocol_sha256"] = sha(package / "protocol.json")
    manifest["source_sha256"][str(a82_path.relative_to(root))] = sha(a82_path)
    manifest["source_sha256"][protocol["evaluation_truth"]] = sha(truth_dir / "cases_private.json")
    manifest["source_sha256"][str(Path(__file__).resolve().relative_to(root))] = sha(__file__)
    for relative in (
        "studies/sce_inflation_expectations/evaluation/frozen_trial.py",
        "studies/sce_inflation_expectations/evaluation/cognition.py",
        "studies/sce_inflation_expectations/evaluation/metrics.py",
        "studies/sce_inflation_expectations/q9_normalization.py",
    ):
        path = root / relative
        manifest["source_sha256"][relative] = sha(path)
    manifest["evaluation_truth_attached_after_prompt_freeze"] = True
    manifest["prepared_file_sha256"] = {
        str(path.relative_to(package)): sha(path) for path in package.rglob("*.json")
        if path.name not in {"manifest.json", "authorization.json"}}
    if prompt_hashes != {str(path.relative_to(package)): sha(path) for path in package.glob("*/prompts_*.json")}:
        raise ValueError("prompt bytes changed while attaching evaluation")
    manifest["status"] = "prepared_with_evaluation_requires_engine_checks_and_new_authorization"
    dump(package / "manifest.json", manifest)
    dump(package / "authorization.json", {"approved": False, "protocol_sha256": manifest["protocol_sha256"],
        "cap_usd": protocol["budget_cap_usd"], "planned_calls": protocol["planned_calls"],
        "destination": protocol["destination"], "user_confirmation": None})
    return {"evaluation_links": len(links), "truth_rows": len(truth), "a82_original_rows": len(selected),
            "prompt_bytes_unchanged": True, "new_api_calls": 0}


def prior_groups(cases, month):
    rows = [row for row in cases if row["month"] == month]
    values = {row["agent_id"]: row["real"].get("previous_q9_mean") for row in rows}
    finite = [(value, agent_id) for agent_id, value in values.items() if shared.finite(value)]
    finite.sort()
    groups = {}
    for rank, (_, agent_id) in enumerate(finite):
        groups[agent_id] = ("low", "middle", "high")[min(2, rank * 3 // len(finite))]
    groups.update({agent_id: "missing" for agent_id in values if agent_id not in groups})
    return groups


def diagnostic_strata(cases, contexts_by_month, months, repeats, arms):
    result = {}
    prior_by_month = {month: prior_groups(cases, month) for month in months}
    for arm in arms:
        groups = {"news_tier": {}, "prior_expectation": {}}
        for tier in (4, 8, 16, 32):
            subset = [row for row in cases if contexts_by_month[row["month"]][arm][row["agent_id"]]["news_count"] == tier]
            support9 = shared._common_person_months(subset, [arm], repeats, "q9")
            support8 = shared._common_person_months(subset, [arm], repeats, "q8")
            groups["news_tier"][str(tier)] = shared._summarize_arm(subset, arm, months, repeats, support9, support8)
        for label in ("low", "middle", "high", "missing"):
            subset = [row for row in cases if prior_by_month[row["month"]][row["agent_id"]] == label]
            support9 = shared._common_person_months(subset, [arm], repeats, "q9")
            support8 = shared._common_person_months(subset, [arm], repeats, "q8")
            groups["prior_expectation"][label] = shared._summarize_arm(subset, arm, months, repeats, support9, support8)
        if arm == "Q2":
            groups["fox_exposure"] = {}
            for label, received in (("received_fox", True), ("no_fox", False)):
                subset = [row for row in cases if any(source.startswith("Fox") for source in contexts_by_month[row["month"]][arm][row["agent_id"]]["sources"]) == received]
                support9 = shared._common_person_months(subset, [arm], repeats, "q9")
                support8 = shared._common_person_months(subset, [arm], repeats, "q8")
                groups["fox_exposure"][label] = shared._summarize_arm(subset, arm, months, repeats, support9, support8)
        result[arm] = groups
    return result


def compare_with_a82(evaluation_dir, package, out):
    evaluation_dir, package, out = Path(evaluation_dir), Path(package), Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / "outputs"):
        raise ValueError("fresh comparison output required")
    evaluated = read_json(evaluation_dir / "summary.json")
    cases = read_json(evaluation_dir / "cases_private.json")
    protocol = read_json(package / "protocol.json")
    months = protocol["months"]
    contexts = {month: read_json(package / str(month) / "contexts_private.json") for month in months}
    a82 = []
    for row in read_json(package / "a82_reference_private.json"):
        a82.append({**row, "survey_weight": row["survey_weight"],
                    "arms": {"A82": row["arms"]["monthly_reconstruction"]}})
    support9 = shared._common_person_months(a82, ["A82"], [1], "q9")
    support8 = shared._common_person_months(a82, ["A82"], [1], "q8")
    result = {
        "schema": "sce_media_mechanism_v3_comparison/v1", "new_api_calls": 0,
        "new_arms": evaluated["arms"], "A82_original_single_generation": shared._summarize_arm(a82, "A82", months, [1], support9, support8),
        "comparison_note": "A82 is one archived generation. New arms are reported separately by month and repeat; no synthetic A82 repeat two.",
        "registered_comparisons": [["A82", "R0"], ["R0", "Q0"], ["Q0", "Q1"], ["Q0", "Q2"], ["Q0", "Q3"]],
        "stratified_descriptive": diagnostic_strata(cases, contexts, months, protocol["generation_repeats"], protocol["arms"]),
        "coverage": evaluated["coverage"], "source_evaluation": str(evaluation_dir.resolve().relative_to(ROOT)),
    }
    out.mkdir(parents=True)
    dump(out / "summary.json", result)
    return result
