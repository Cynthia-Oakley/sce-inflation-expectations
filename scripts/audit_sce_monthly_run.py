"""Audit a monthly P/E run and form weighted diagnostic summaries, no APIs.

This command reads analysis weights/survey dates only AFTER the simulation.
It never reads actual Q8/Q9 answers; its summaries alone are not an accuracy test.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.monthly_analysis import date_group, weighted_summary
from studies.sce_inflation_expectations.scoring.sce_q9_frozen import score_q9_frozen, provenance


def read_rows(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--package-dir", type=Path, required=True)
    args = ap.parse_args()
    run, package = args.run_dir, args.package_dir
    manifest = json.loads((run / "run_manifest.json").read_text())
    pop = json.loads((package / "population.json").read_text())
    env = json.loads((package / "environment.json").read_text())
    weights = read_rows(package / "analysis_weights.jsonl")
    dates = read_rows(package / "survey_dates.jsonl")
    expected = {p["agent_id"]: p for p in pop["personas"]}
    if len({r["agent_id"] for r in weights}) != len(weights) or len({r["agent_id"] for r in dates}) != len(dates):
        raise ValueError("duplicate analysis key")
    if {r["agent_id"] for r in weights} != set(expected) or {r["agent_id"] for r in dates} != set(expected):
        raise ValueError("analysis sidecars do not match population")
    for key in ["population", "environment", "simulation"]:
        if sha(package / f"{key}.json") != manifest["artifact_sha256"][key]:
            raise ValueError("run input hash differs from monthly package")
    for key, digest in manifest["effective_artifact_sha256"].items():
        if sha(run / key) != digest:
            raise ValueError("effective run input changed")
    for key, digest in manifest.get("source_snapshot_sha256", {}).items():
        if sha(run / key) != digest:
            raise ValueError("executed source snapshot changed")
    model_snapshot = run / "source_snapshot/study/model.py"
    if model_snapshot.exists() and sha(model_snapshot) != manifest["model_code_sha256_self_reported"]:
        raise ValueError("source snapshot differs from executed model's self-reported hash")
    observations = read_rows(run / "observations.jsonl")
    if len(observations) != len(expected) or {r["agent_id"] for r in observations} != set(expected):
        raise ValueError("observation count/id mismatch")
    target = env["provider_args"]["targets"][0]
    for r in observations:
        ob = r["observation"]
        raw = json.dumps(ob, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if hashlib.sha256(raw.encode()).hexdigest() != r["observation_sha256"]:
            raise ValueError("observation checksum failure")
        if ob["local_physical"]["profile"] != {**expected[r["agent_id"]]["attributes"], "weight": 1}:
            raise ValueError("actual profile differs from monthly P or contains non-neutral weights")
        info = ob["macro_information"]
        if any(info[k] != target[k] for k in ["target_month", "as_of"]):
            raise ValueError("actual target mismatch")
        for key, envkey in [("signals", "signals_by_step"), ("events", "events_by_step")]:
            if info[key] != env["provider_args"][envkey]["0"]:
                raise ValueError("actual E differs from monthly input")
    answers = [r for r in read_rows(run / "panel_live.jsonl") if (r.get("action_payload") or {}).get("target_month")]
    if len(answers) != len(expected) or {r["agent_id"] for r in answers} != set(expected):
        raise ValueError("answer count/id mismatch")
    by_weight = {r["agent_id"]: r["analysis_weight"] for r in weights}
    by_date = {r["agent_id"]: r["survey_date"] for r in dates}
    fit_cache, records = {}, []
    for r in answers:
        p = r["action_payload"]
        if p["target_month"] != target["target_month"]:
            raise ValueError("answer target mismatch")
        bins = tuple(p[f"q9_bin{i}"] for i in range(1, 11))
        if p["validation_status"] == "valid":
            if any(not 0 <= v <= 100 for v in bins) or abs(sum(bins) - 100) > 1e-6:
                raise ValueError("invalid bins labelled valid")
            if bins not in fit_cache:
                fit_cache[bins] = asdict(score_q9_frozen(bins))
            fit = fit_cache[bins]
        else:
            fit = {"mean": None, "status": "invalid_answer"}
        records.append({"agent_id": r["agent_id"], "group": date_group(by_date[r["agent_id"]], target["as_of"]),
                        "weight": by_weight[r["agent_id"]], "q8": p["point_pct"] if p["validation_status"] == "valid" else None,
                        "q9": fit["mean"], "score_status": fit["status"], "validation_status": p["validation_status"]})
    summaries = {}
    for group in ["all", "after_cutoff", "before_cutoff", "same_day_time_unknown", "unknown_date"]:
        sub = [r for r in records if group == "all" or r["group"] == group]
        if sub:
            summaries[group] = {"n": len(sub), "q8": weighted_summary([r["q8"] for r in sub], [r["weight"] for r in sub], interpolate_median=True),
                                "q9_project_density_mean": weighted_summary([r["q9"] for r in sub], [r["weight"] for r in sub])}
    result = {"run_id": manifest["run_id"], "audited_at_utc": datetime.now(timezone.utc).isoformat(),
              "target": target, "llm_kind": manifest["llm_kind"], "technical_audit": "passed",
              "observations_verified": len(observations), "answer_rows": len(answers),
              "source_snapshot_files_verified": len(manifest.get("source_snapshot_sha256", {})),
              "answer_status_counts": dict(Counter(r["validation_status"] for r in records)),
              "fit_status_counts": dict(Counter(r["score_status"] for r in records)), "summaries": summaries,
              "scorer_provenance": provenance(), "analysis_inputs_sha256": {name: sha(package / name) for name in ["analysis_weights.jsonl", "survey_dates.jsonl"]},
              "notes": ["Simulation diagnostics only; no real-answer accuracy evaluated",
                        "Scorer is project's frozen approximation, not NY Fed official headline",
                        "All-wave dates before/same-day cutoff are descriptive; after-cutoff is the main aligned personal comparison set",
                        "Analysis weights/dates were not passed into B"]}
    out = run / "monthly_audit.json"
    if out.exists():
        raise ValueError("audit already exists; preserve prior evidence")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: result[k] for k in ["run_id", "technical_audit", "observations_verified", "answer_status_counts", "fit_status_counts"]}))
    print(out)


if __name__ == "__main__":
    main()
