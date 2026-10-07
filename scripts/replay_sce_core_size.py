"""Subsample completed LLM Core responses. No new answers, calls or actual truth.

Reference = same month's 300-Core expanded LLM distribution, NOT actual SCE.
Stability can coexist with systematically wrong and homogeneous responses.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

import numpy as np

from check_sce_core_size import ROOT, build_expansion, describe, metrics, sha
from _sce_core_size_statistics.scoring.sce_q9_frozen import score_q9_frozen


def rows(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]


def bins(payload):
    return tuple(payload[f"q9_bin{i}"] for i in range(1, 11))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--full-package", type=Path, required=True)
    ap.add_argument("--expansion", type=Path, required=True)
    ap.add_argument("--sizes", default="100,150,200,300")
    ap.add_argument("--repeats", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    sizes = sorted(set(map(int, args.sizes.split(","))))
    if args.repeats < 1 or min(sizes) < 1:
        raise ValueError("positive sizes/repeats required")
    population = json.loads((args.full_package / "population.json").read_text())
    weights = {r["agent_id"]: r["survey_weight"] for r in rows(args.full_package / "analysis_weights.jsonl")}
    meta = json.loads((args.expansion / "summary.json").read_text())
    records = rows(args.expansion / "core_answers_original.jsonl")
    original = {r["agent_id"]: r["action_payload"] for r in records}
    if len(original) != len(records) or max(sizes) > len(original):
        raise ValueError("duplicate Core or size exceeds original Core")
    target = meta["target"]
    full_target = json.loads((args.full_package / "environment.json").read_text())["provider_args"]["targets"]
    if full_target != [target] or meta["source_llm_kind"] != "openai":
        raise ValueError("mismatched population/E or not completed real LLM expansion")
    values = {}
    # Reuse archived fitted means only after checking every joint donor payload
    # against the original response. No actual-person questionnaire is read.
    for row in rows(args.expansion / "normal_answers.jsonl"):
        donor, p = row["donor_agent_id"], row["payload"]
        if bins(p) != bins(original[donor]) or p["point_pct"] != original[donor]["point_pct"]:
            raise ValueError("archived donor does not match original Core")
        value = float(p["q9_project_density_mean"])
        if donor in values and values[donor] != value:
            raise ValueError("inconsistent archived fitted means")
        values[donor] = value
    fitted_missing = 0
    for uid, p in original.items():
        if p["validation_status"] != "valid" or p["target_month"] != target["target_month"] or p["as_of"] != target["as_of"]:
            raise ValueError("invalid or mismatched original response")
        if uid not in values:
            values[uid] = score_q9_frozen(bins(p)).mean
            fitted_missing += 1
        if values[uid] is None or not np.isfinite(values[uid]):
            raise ValueError("uncounted invalid donor; stop instead of filling it")
    reference_plan = build_expansion(population, original, values, weights, prior_strength=meta["coverage"]["prior_strength"])
    reference_ids = list(reference_plan.donor_ids)
    reference_x = [values[u] for u in reference_ids]
    reference_w = reference_plan.atom_weights()
    draw_results = []
    ids = sorted(original)
    for repeat in range(args.repeats):
        ranks = {u: np.random.default_rng(np.random.SeedSequence([args.seed + repeat, int(u.removeprefix("sce_u"))])).random() for u in ids}
        order = sorted(ids, key=lambda u: (ranks[u], u))
        for size in sizes:
            core = order[:size]
            plan = build_expansion(population, core, core, weights, prior_strength=meta["coverage"]["prior_strength"])
            x = [values[u] for u in plan.donor_ids]
            report = plan.report()
            draw_results.append({"core_n": size, "repeat": repeat,
                "core_ids_sha256": hashlib.sha256(json.dumps(core).encode()).hexdigest(),
                "normal_without_fine_support_weight_fraction": report["normal_without_fine_support_weight_fraction"],
                "vs_full_core_expansion": metrics(x, plan.atom_weights(), reference_x, reference_w)})
    summary = {"target": target, "source_run_id": meta["source_run_id"], "original_core_n": len(ids),
        "purpose": "completed_LLM_subsampling_stability_not_accuracy", "repeats": args.repeats, "seed": args.seed,
        "model_api_calls": 0, "actual_SCE_answers_read": False, "missing_archived_means_recomputed": fitted_missing,
        "by_size": {str(n): {key: describe([r["vs_full_core_expansion"][key] for r in draw_results if r["core_n"] == n])
                              for key in draw_results[0]["vs_full_core_expansion"]} for n in sizes},
        "inputs_sha256": {str(p): sha(p) for p in [args.full_package / "population.json", args.full_package / "analysis_weights.jsonl",
            args.expansion / "summary.json", args.expansion / "core_answers_original.jsonl", args.expansion / "normal_answers.jsonl"]},
        "code_sha256": {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), ROOT / "scripts/check_sce_core_size.py",
            ROOT / "studies/sce_inflation_expectations/core_normal.py", ROOT / "studies/sce_inflation_expectations/evaluation/metrics.py",
            ROOT / "studies/sce_inflation_expectations/scoring/sce_q9_frozen.py", ROOT / "studies/sce_inflation_expectations/scoring/beta_fit_kernel.py",
            ROOT / "studies/sce_inflation_expectations/scoring/sce_q9.py"]},
        "limitations": ["Reuses one stochastic answer per original Core; does not estimate LLM repeat-call uncertainty",
            "Conditional on original 300-Core frame; not the entire population's behavioral coverage",
            "Reference is simulated distribution, not actual survey accuracy", "Overlapping draws; p95 is not a confidence interval"]}
    out = ROOT / "outputs" / ("sce_core_size_replay_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    (out / "draw_metrics.jsonl").write_text("".join(json.dumps(r, allow_nan=False) + "\n" for r in draw_results))
    print(out)


if __name__ == "__main__":
    main()
