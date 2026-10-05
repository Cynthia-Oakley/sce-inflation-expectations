"""Expand a completed single-month Core run; reads NO actual questionnaire truth.

Source Core trajectories remain intact. New Normal records are explicitly
statistical joint-response draws; the main aggregate integrates donor atoms.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.core_normal import build_expansion, atom_summary
from studies.sce_inflation_expectations.scoring.sce_q9_frozen import score_q9_frozen, provenance


def read_json(path):
    return json.loads(path.read_text())


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_packages(full_dir, core_dir):
    full, core = read_json(full_dir / "population.json"), read_json(core_dir / "population.json")
    full_meta, core_meta = read_json(full_dir / "sampling_meta.json"), read_json(core_dir / "sampling_meta.json")
    if any(m["research_line"] != "A_historical_reconstruction" for m in [full_meta, core_meta]):
        raise ValueError("current-month population expansion is implemented for A line only")
    if full_meta["design"] != "census" or full_meta["selected_n"] != full_meta["frame_n"]:
        raise ValueError("need the full current-month population package")
    if (core_meta["design"] not in {"independent_srs", "stable_priority_srs", "census"}
            or core_meta["target_month"] != full_meta["target_month"]
            or core_meta["frame_n"] != full_meta["frame_n"]
            or not np.isclose(core_meta["inclusion_probability"], core_meta["selected_n"] / full_meta["frame_n"])):
        raise ValueError("this estimator requires matching-month equal-probability SRS/census")
    fids = {p["agent_id"]: p for p in full["personas"]}
    if len(fids) != len(full["personas"]) or len({p["agent_id"] for p in core["personas"]}) != len(core["personas"]):
        raise ValueError("duplicate persona ID")
    for p in core["personas"]:
        if p != fids.get(p["agent_id"]):
            raise ValueError("Core profile differs from full current-month profile")
    for p in full["personas"]:
        if p["weight"] != 1:
            raise ValueError("persona weights must be neutral; read the separate analysis sidecar")
    sidecar = read_rows(full_dir / "analysis_weights.jsonl")
    if len(sidecar) != len(fids) or {r["agent_id"] for r in sidecar} != set(fids):
        raise ValueError("full-frame weights mismatch")
    if any(r["target_month"] != full_meta["target_month"] or r["inclusion_probability"] != 1
           or r["analysis_weight"] != r["survey_weight"] for r in sidecar):
        raise ValueError("full-frame weight metadata mismatch")
    return full, core, full_meta, {r["agent_id"]: r["survey_weight"] for r in sidecar}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--full-package", type=Path, required=True)
    ap.add_argument("--core-package", type=Path, required=True)
    ap.add_argument("--prior-strength", type=float, default=5.)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    full, core, meta, weights = validate_packages(args.full_package, args.core_package)
    run = read_json(args.run_dir / "run_manifest.json")
    if run["n_steps"] != 1:
        raise ValueError("first version accepts single-month Core runs only")
    audit = read_json(args.run_dir / "monthly_audit.json")
    if audit["technical_audit"] != "passed" or audit["run_id"] != run["run_id"]:
        raise ValueError("Core run must pass monthly technical audit first")
    for key in ["population", "environment", "simulation"]:
        if sha(args.core_package / f"{key}.json") != run["artifact_sha256"][key]:
            raise ValueError("Core package is not the actual run input")
    env = read_json(args.core_package / "environment.json")
    if env != read_json(args.full_package / "environment.json"):
        raise ValueError("full/Core target environments differ")
    target = env["provider_args"]["targets"][0]
    month = int(target["target_month"].replace("-", ""))
    if month != meta["target_month"]:
        raise ValueError("population/environment month mismatch")
    rows = [r for r in read_rows(args.run_dir / "panel_live.jsonl") if (r.get("action_payload") or {}).get("target_month")]
    core_ids = [p["agent_id"] for p in core["personas"]]
    if len(rows) != len(core_ids) or {r["agent_id"] for r in rows} != set(core_ids):
        raise ValueError("Core answer ID/count mismatch")
    payloads, fits, status = {}, {}, Counter()
    for row in rows:
        p = row["action_payload"]
        if p["target_month"] != target["target_month"] or p["as_of"] != target["as_of"]:
            raise ValueError("Core answer target mismatch")
        bins = tuple(p[f"q9_bin{i}"] for i in range(1, 11))
        if p["validation_status"] != "valid":
            status["invalid_payload"] += 1
            continue
        if (not np.isfinite(p["point_pct"]) or any(not np.isfinite(v) or not 0 <= v <= 100 for v in bins)
                or not np.isclose(sum(bins), 100, atol=1e-6, rtol=0)):
            raise ValueError("invalid payload marked valid")
        if bins not in fits:
            fits[bins] = asdict(score_q9_frozen(bins))
        fit = fits[bins]
        if fit["mean"] is None or not np.isfinite(fit["mean"]):
            status["no_q9_density_donor:" + fit["status"]] += 1
            continue
        status["joint_valid_donor"] += 1
        payloads[row["agent_id"]] = {"point_pct": p["point_pct"], "direction": p["direction"],
                                     "magnitude_pct": p["magnitude_pct"], "q9_project_density_mean": fit["mean"],
                                     **{f"q9_bin{i}": p[f"q9_bin{i}"] for i in range(1, 11)}}
    plan = build_expansion(full, core_ids, payloads.keys(), weights, prior_strength=args.prior_strength)
    masses = plan.atom_weights()
    q8 = [payloads[u]["point_pct"] for u in plan.donor_ids]
    q9 = [payloads[u]["q9_project_density_mean"] for u in plan.donor_ids]
    assignments = plan.sample_normal_donors(seed=args.seed, month=month)
    out_rows = [{"agent_id": u, "target_month": target["target_month"], "as_of": target["as_of"],
                 "role": "normal", "source": "statistical_expansion", "donor_agent_id": donor,
                 "survey_weight": weights[u], "payload": payloads[donor]} for u, donor in assignments.items()]
    core_w = [weights[u] for u in plan.donor_ids]
    realized_ids = list(plan.donor_ids) + list(plan.normal_ids)
    realized_donors = list(plan.donor_ids) + [assignments[u] for u in plan.normal_ids]
    realized_w = [weights[u] for u in realized_ids]
    expected_total = sum(weights[u] for u in set(plan.donor_ids) | set(plan.normal_ids))
    if not np.isclose(masses.sum(), expected_total):
        raise ValueError("expansion weight mass was not conserved")
    result = {"research_line": "A_historical_reconstruction", "source_run_id": run["run_id"], "source_llm_kind": run["llm_kind"], "target": target,
              "seed": args.seed, "paid_calls_by_expansion": 0,
              "core_answer_status_counts": dict(status), "coverage": plan.report(),
              "core_only": {"q8": atom_summary(q8, core_w, point_prediction=True), "q9": atom_summary(q9, core_w)},
              "expanded_integrated": {"q8": atom_summary(q8, masses, point_prediction=True), "q9": atom_summary(q9, masses)},
              "expanded_one_materialized_draw": {
                  "q8": atom_summary([payloads[u]["point_pct"] for u in realized_donors], realized_w, point_prediction=True),
                  "q9": atom_summary([payloads[u]["q9_project_density_mean"] for u in realized_donors], realized_w)},
              "included_target_survey_weight": expected_total,
              "excluded_core_survey_weight": sum(weights[u] for u in set(core_ids) - set(payloads)),
              "scorer": provenance(),
              "notes": ["Only joint-valid Core atoms supply Normal; failed Core remains excluded and counted",
                        "Integrated headline is the exact predictive mixture, not an average of cell medians",
                        "Materialized Normal records copy joint Q8/Q9 values, not donor rationale or persona history",
                        "No actual SCE answers/headline were read; no scientific accuracy claim from scripted inputs",
                        "Donor mass concentration is not full-population respondent ESS"]}
    result["integrated_by_population_cell"] = {}
    for cell in sorted(set(plan.cells.values())):
        group_ids = [u for u in plan.weights if plan.cells[u] == cell]
        group_masses = plan.atom_weights(group_ids)
        result["integrated_by_population_cell"][json.dumps(cell)] = {
            "population_n": len(group_ids), "population_survey_weight": sum(weights[u] for u in group_ids),
            "included_survey_weight": float(group_masses.sum()),
            "q8": atom_summary(q8, group_masses, point_prediction=True),
            "q9": atom_summary(q9, group_masses)}
    out = ROOT / "outputs" / ("core_normal_expansion_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True)
    sources = [Path(__file__), ROOT / "studies/sce_inflation_expectations/core_normal.py",
               ROOT / "studies/sce_inflation_expectations/monthly_analysis.py"]
    sources += list((ROOT / "studies/sce_inflation_expectations/scoring").glob("*.py"))
    snapshot = out / "source_snapshot"; snapshot.mkdir()
    for p in sources:
        (snapshot / p.name).write_bytes(p.read_bytes())
    result["source_code_sha256"] = {str(p.relative_to(ROOT)): sha(p) for p in sources}
    result["inputs_sha256"] = {str(p): sha(p) for p in
        [args.run_dir / "run_manifest.json", args.run_dir / "monthly_audit.json", args.run_dir / "panel_live.jsonl",
         args.full_package / "population.json", args.full_package / "sampling_meta.json", args.full_package / "analysis_weights.jsonl",
         args.full_package / "environment.json", args.core_package / "population.json", args.core_package / "sampling_meta.json",
         args.core_package / "environment.json", args.core_package / "simulation.json"]}
    (out / "normal_answers.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in out_rows))
    (out / "core_answers_original.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(f"Core {len(core_ids)} ({len(payloads)} joint-valid); Normal {len(out_rows)}; zero API calls")
    print(out)


if __name__ == "__main__":
    main()
