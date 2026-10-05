"""Same-person development analysis: actual answers are read only after the run.

Q9 compares simulated and real raw bins scored by the SAME frozen approximation.
The full-wave official density headline is a reference, not this panel's accuracy
target. Date groups preserve the distinction between early and aligned answers.
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

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.monthly_analysis import date_group, paired_metrics
from studies.sce_inflation_expectations.scoring.sce_q9_frozen import score_q9_frozen, provenance


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--truth", type=Path, default=ROOT / "data/evaluation/sce_truth_main2021.json")
    ap.add_argument("--profile-cache", type=Path, required=True,
                    help="local profile parquet made by prepare_sce_monthly_inputs.py (survey dates only read)")
    ap.add_argument("--profile-manifest", type=Path, required=True,
                    help="monthly-input manifest carrying source SHA and local-derived-cache SHA")
    args = ap.parse_args()
    truth = json.loads(args.truth.read_text())
    profile_meta = json.loads(args.profile_manifest.read_text())
    if truth["manifest"]["source_sha256"] != profile_meta["source_sha256"]:
        raise ValueError("truth and survey dates originate from different microdata files")
    if hashlib.sha256(args.profile_cache.read_bytes()).hexdigest() != profile_meta["local_derived_cache_sha256"]:
        raise ValueError("profile cache checksum differs from its build manifest")
    date_frame = pd.read_parquet(args.profile_cache, columns=["date", "userid", "survey_date"])
    if date_frame.duplicated(["date", "userid"]).any():
        raise ValueError("duplicate survey-date key")
    dates = {(int(r.date), int(r.userid)): (None if pd.isna(r.survey_date) else str(r.survey_date))
             for r in date_frame.itertuples(index=False)}
    keyed_truth = {(int(r["date"]), int(r["userid"])): r for r in truth["per_person"]}
    if len(keyed_truth) != len(truth["per_person"]):
        raise ValueError("duplicate truth key")
    obs = rows(args.run_dir / "observations.jsonl")
    cutoff = {}
    for r in obs:
        info = r["observation"]["macro_information"]
        cutoff[(info["target_month"], r["agent_id"])] = info["as_of"]
    answer_rows = [r for r in rows(args.run_dir / "panel_live.jsonl") if (r.get("action_payload") or {}).get("target_month")]
    records, fits, seen = [], {}, set()
    def fit(bins):
        key = json.dumps(bins)
        if key not in fits:
            fits[key] = asdict(score_q9_frozen(bins))
        return fits[key]
    print("Scoring development answers; no API calls", flush=True)
    for r in answer_rows:
        p = r["action_payload"]
        month = int(p["target_month"].replace("-", ""))
        key = (month, int(r["agent_id"].removeprefix("sce_u")))
        if key in seen:
            raise ValueError("duplicate simulated answer key")
        seen.add(key)
        if key not in keyed_truth or (p["target_month"], r["agent_id"]) not in cutoff:
            raise ValueError("missing matching actual questionnaire or observation")
        gt = keyed_truth[key]
        good = p["validation_status"] == "valid"
        sim = fit([p[f"q9_bin{i}"] for i in range(1, 11)]) if good else {"mean": None, "status": "invalid_answer"}
        real = fit([gt[f"Q9_bin{i}"] for i in range(1, 11)])
        records.append({"month": month, "weight": gt["weight"],
                        "group": date_group(dates.get(key), cutoff[(p["target_month"], r["agent_id"])]),
                        "sim_q8": p["point_pct"] if good else None, "real_q8": gt["Q8v2part2"],
                        "sim_q9": sim["mean"], "real_q9": real["mean"],
                        "sim_fit_status": sim["status"], "real_fit_status": real["status"]})
    monthly = {}
    for month in sorted({r["month"] for r in records}):
        subset = [r for r in records if r["month"] == month]
        groups = {}
        for group in ["all", "after_cutoff", "before_cutoff", "same_day_time_unknown", "unknown_date"]:
            sub = [r for r in subset if group == "all" or r["group"] == group]
            if sub:
                w = [r["weight"] for r in sub]
                groups[group] = {"n_records": len(sub),
                                 "q8": paired_metrics([r["sim_q8"] for r in sub], [r["real_q8"] for r in sub], w, point_prediction=True),
                                 "q9_project_density_mean": paired_metrics([r["sim_q9"] for r in sub], [r["real_q9"] for r in sub], w)}
        monthly[str(month)] = {"groups": groups,
                               "official_full_wave_reference_only": truth["monthly_full_sample"][str(month)]}
    manifest = json.loads((args.run_dir / "run_manifest.json").read_text())
    result = {"run_id": manifest["run_id"], "llm_kind": manifest["llm_kind"], "matched_records": len(records),
              "generated_utc": datetime.now(timezone.utc).isoformat(), "monthly": monthly,
              "fit_status_counts": {"simulated": dict(Counter(r["sim_fit_status"] for r in records)),
                                    "real": dict(Counter(r["real_fit_status"] for r in records))},
              "scorer_provenance": provenance(),
              "inputs_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in
                                [("truth", args.truth), ("profile_cache", args.profile_cache), ("profile_manifest", args.profile_manifest),
                                 ("observations", args.run_dir / "observations.jsonl"), ("panel_live", args.run_dir / "panel_live.jsonl")]},
              "notes": ["Same observed person/month only; weights normalize within each comparison set",
                        "Q8 and Q9 actual-answer masks are independent; invalid simulated payloads excluded and counted",
                        "A selected panel is not a representative national prediction", "after_cutoff is the time-aligned personal comparison group",
                        "Scripted results validate analysis plumbing only; cannot validate LLM behavior"]}
    out = args.run_dir / ("evaluation_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    out.mkdir()
    sources = [Path(__file__), ROOT / "studies/sce_inflation_expectations/monthly_analysis.py"] + list((ROOT / "studies/sce_inflation_expectations/scoring").glob("*.py"))
    (out / "source_snapshot").mkdir()
    for src in sources:
        (out / "source_snapshot" / src.name).write_bytes(src.read_bytes())
    (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(f"Matched {len(records)} records; real LLM calls made by evaluator: 0")
    print(out)


if __name__ == "__main__":
    main()
