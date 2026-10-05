"""Offline expansion diagnostic with real Core answers as oracle response atoms.

Checks the statistical expansion alone; NOT a simulation or LLM accuracy test.
Normal truth is used only after the expansion plan has been constructed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.core_normal import build_expansion, distribution_errors


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_trials(trials):
    result = {}
    for question in ["q8", "q9"]:
        result[question] = {}
        for key in ["median_absolute_error_pp", "mean_bias_pp", "std_bias_pp", "wasserstein_1_pp"]:
            values = np.array([r[question][key] for r in trials])
            result[question][key] = {"mean": float(values.mean()), "p95": float(np.quantile(values, .95))}
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--full-inputs", type=Path, default=ROOT / "outputs/monthly_inputs_20261005T044205Z_53cbc7e5")
    ap.add_argument("--truth", type=Path, default=ROOT / "data/evaluation/dev_full_20261005T045330Z_947a818f/truth.json")
    ap.add_argument("--sizes", default="300,500")
    ap.add_argument("--prior-strengths", default="0,5,20")
    ap.add_argument("--repeats", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    if args.repeats < 1:
        raise ValueError("need positive repeats")
    sizes, strengths = list(map(int, args.sizes.split(","))), list(map(float, args.prior_strengths.split(",")))
    truth = json.loads(args.truth.read_text())
    manifest = json.loads((args.full_inputs / "manifest.json").read_text())
    if truth["manifest"]["source_sha256"] != manifest["source_sha256"]:
        raise ValueError("profile frame and evaluation truth sources differ")
    results, inputs = {}, {"truth": sha(args.truth), "full_manifest": sha(args.full_inputs / "manifest.json")}
    for month in [202105, 202106]:
        folder = args.full_inputs / "all" / str(month)
        population = json.loads((folder / "population.json").read_text())
        ids = sorted(p["agent_id"] for p in population["personas"])
        weights = {r["agent_id"]: r["survey_weight"] for r in
                   [json.loads(s) for s in (folder / "analysis_weights.jsonl").read_text().splitlines()]}
        inputs[f"population_{month}"] = sha(folder / "population.json")
        inputs[f"weights_{month}"] = sha(folder / "analysis_weights.jsonl")
        gt = {f"sce_u{r['userid']}": r for r in truth["per_person"] if r["date"] == month}
        if set(gt) != set(ids):
            raise ValueError("need complete monthly evaluation truth")
        valid = {u for u, r in gt.items() if r["Q8v2part2"] is not None and r["Q9_mean"] is not None
                 and np.isfinite(r["Q8v2part2"]) and abs(r["Q8v2part2"]) <= 100 and np.isfinite(r["Q9_mean"])}
        targets = sorted(valid)
        real_values = {"q8": [gt[u]["Q8v2part2"] for u in targets], "q9": [gt[u]["Q9_mean"] for u in targets]}
        rw = [weights[u] for u in targets]
        monthly = {"frame_n": len(ids), "joint_valid_truth_n": len(valid), "designs": {}}
        for size in sizes:
            if not 1 <= size <= len(ids):
                raise ValueError("sample size out of monthly frame range")
            rng = np.random.default_rng(np.random.SeedSequence([args.seed, month, size]))
            baseline, expanded = [], {str(k): [] for k in strengths}
            support = {str(k): [] for k in strengths}
            for repeat in range(args.repeats):
                # Selection sees IDs only; outcome validity is checked after selection.
                core_ids = [ids[i] for i in rng.choice(len(ids), size, replace=False)]
                donor_ids = sorted(set(core_ids) & valid)
                vals = {"q8": [gt[u]["Q8v2part2"] for u in donor_ids], "q9": [gt[u]["Q9_mean"] for u in donor_ids]}
                cw = [weights[u] for u in donor_ids]
                baseline.append({q: distribution_errors(vals[q], cw, real_values[q], rw, point_prediction=q == "q8") for q in vals})
                for strength in strengths:
                    plan = build_expansion(population, core_ids, donor_ids, weights, prior_strength=strength)
                    masses = plan.atom_weights(target_ids=valid)
                    expanded[str(strength)].append({q: distribution_errors(vals[q], masses, real_values[q], rw, point_prediction=q == "q8") for q in vals})
                    coverage = plan.report()
                    support[str(strength)].append(coverage["normal_without_fine_support_weight_fraction"])
            monthly["designs"][str(size)] = {"core_only": summarize_trials(baseline),
                "expansion": {k: {**summarize_trials(v), "mean_normal_weight_without_fine_support": float(np.mean(support[k]))}
                              for k, v in expanded.items()}}
            print(f"Offline oracle diagnostic {month}, Core n={size}, {args.repeats} draws complete", flush=True)
        results[str(month)] = monthly
    out = ROOT / "outputs" / ("core_normal_diagnostic_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True)
    sources = [Path(__file__), ROOT / "studies/sce_inflation_expectations/core_normal.py", ROOT / "studies/sce_inflation_expectations/monthly_analysis.py"]
    snapshot = out / "source_snapshot"; snapshot.mkdir()
    for p in sources:
        (snapshot / p.name).write_bytes(p.read_bytes())
    payload = {"purpose": "oracle_response_expansion_diagnostic_not_LLM_simulation", "seed": args.seed,
               "repeats": args.repeats, "core_sizes": sizes, "prior_strengths": strengths,
               "chosen_strength": None, "model_api_calls": 0, "inputs_sha256": inputs,
               "source_code_sha256": {str(p.relative_to(ROOT)): sha(p) for p in sources}, "months": results,
               "limitations": ["Uses official individual Q9_mean to isolate sampling/expansion; not frozen raw-bin fit validation",
                               "Common joint-valid target set; outcome masks applied only in evaluation after plan construction",
                               "Real Core answers are oracle inputs here, never future production inputs",
                               "Sensitivity grid describes behavior; no best seed/strength selected or frozen",
                               "Only two development months; no subgroup power or posterior interval claim"]}
    (out / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(out)


if __name__ == "__main__":
    main()
