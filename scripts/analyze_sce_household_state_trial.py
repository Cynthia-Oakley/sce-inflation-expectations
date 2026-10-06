#!/usr/bin/env python3
"""Evaluate a completed Q1 paired trial offline; no network or new simulation."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid
import duckdb
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.household_state_analysis import density, distribution, paired_metrics


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trial", type=Path, required=True)
    ap.add_argument("--truth", type=Path, default=ROOT / "data/evaluation/sce_truth_main2021.json")
    a = ap.parse_args()
    plan_path = a.trial.resolve() / "trial_manifest.json"
    plan = json.loads(plan_path.read_text())
    if plan["status"] != "completed" or any(r["status"] != "completed" for r in plan["records"]):
        ap.error("requires completed genuine LLM trial; scripted is not a treatment test")
    truth = {(str(r["date"]), f"sce_u{int(r['userid'])}"): r for r in json.loads(a.truth.read_text())["per_person"]}
    result = {"trial_id": plan["trial_id"], "months": {}, "sources": {str(plan_path): sha(plan_path), str(a.truth): sha(a.truth), str(Path(__file__)): sha(__file__)}}
    person_rows = []
    for month in plan["metadata"]:
        folder = a.trial.resolve() / month
        bundle = json.loads((folder / "household_state.json").read_text())
        states = bundle["state_by_id"]
        ids = set(states)
        bins_by_arm = {}
        for arm in ("baseline", "q1_state"):
            matches = [r for r in plan["records"] if r["month"] == month and r["arm"] == arm]
            if len(matches) != 1:
                raise ValueError("duplicate/missing trial cell")
            run_dir = Path(matches[0]["output_dir"])
            manifest_path = run_dir / "run_manifest.json"
            run = json.loads(manifest_path.read_text())
            if run["run_id"] != matches[0]["run_id"] or run["llm_kind"] != "openai" or run["n_agents"] != 50:
                raise ValueError("genuine run metadata mismatch")
            for name, h in run["effective_artifact_sha256"].items():
                if sha(run_dir / name) != h:
                    raise ValueError("changed effective run input")
            with duckdb.connect(str(run["store_path"]), read_only=True) as db:
                answers = db.execute("SELECT agent_id, action_payload FROM panel WHERE step = 1 ORDER BY agent_id").fetchall()
            if {aid for aid, _ in answers} != ids or len(answers) != len(ids):
                raise ValueError("answer coverage mismatch")
            bins_by_arm[arm] = {}
            for aid, payload in answers:
                p = json.loads(payload) if isinstance(payload, str) else payload
                bins_by_arm[arm][aid] = [p.get(f"q9_bin{i}") for i in range(1, 11)] if p["validation_status"] == "valid" else [None] * 10
            result["sources"][str(manifest_path)] = sha(manifest_path)
            result["sources"][str(run["store_path"])] = sha(run["store_path"])
        month_rows, statuses = [], Counter()
        for aid in sorted(ids):
            real = truth[(month, aid)]
            fits = {"real": density([real.get(f"Q9_bin{i}") for i in range(1, 11)]),
                    **{arm: density(bins_by_arm[arm][aid]) for arm in ("baseline", "q1_state")}}
            statuses.update(f"{arm}:{f['status']}" for arm, f in fits.items())
            row = {"month": month, "agent_id": aid, "Q1": states[aid]["financial_change_12m_code"],
                   **{arm: f["mean"] for arm, f in fits.items()},
                   "individual_uncertainty_iqr": {arm: f["iqr"] for arm, f in fits.items()}}
            month_rows.append(row)
        metrics = paired_metrics(month_rows)
        common = [r for r in month_rows if all(r[k] is not None for k in ("real", "baseline", "q1_state"))]
        metrics["individual_uncertainty_iqr_summary"] = {arm: distribution([r["individual_uncertainty_iqr"][arm] for r in common if r["individual_uncertainty_iqr"][arm] is not None]) for arm in ("real", "baseline", "q1_state")}
        metrics["fitting_status_counts"] = dict(statuses)
        result["months"][month] = metrics
        person_rows.extend(month_rows)
    result["both_months_support_expansion"] = all(m["development_signal_both_primary_and_group_improve"] for m in result["months"].values())
    result["limitations"] = ["Development months; no blind-test or causal claim", "Q1-balanced sample; no national headline", "10 per group; no power or significance claim", "Fixed project approximate Q9 scorer used for both sides", "Single generation per condition; generation noise not quantified"]
    folder = ROOT / "outputs" / ("sce_q1_analysis_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    folder.mkdir(exist_ok=False)
    (folder / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    (folder / "paired_evaluation.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in person_rows))
    print("ANALYSIS_DIR=" + str(folder))
    print(json.dumps({m: {"n": x["n_complete_pairs"], "MAE": {arm: x["arms"][arm]["MAE_pp"] for arm in ("baseline", "q1_state")}} for m, x in result["months"].items()}))


if __name__ == "__main__":
    main()
