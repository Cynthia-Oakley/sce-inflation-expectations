"""Export completed U1 state/guided runs to the registered comparison schema.

Reads the sixteen real run directories of a completed U1 trial, extracts Q8/Q9
from each stored action payload, and writes evaluation_answers_private.jsonl
plus evaluation_manifest.json exactly as codex_comparison_input_spec.md and the
v2 protocol require. Failures are kept as null rows; nothing is dropped.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.confidence_trial import check_frozen, dump, sha
from studies.sce_inflation_expectations.lifetime_analysis import point_value
from studies.sce_inflation_expectations.u1_state_experiment import LINE, PROMPT_VERSION
from studies.sce_inflation_expectations.belief_state_preparation import ARMS, MONTHS

MODEL = "deepseek-flash"
TEMPERATURE = 0.5


def run_answers(run_dir):
    import duckdb
    db = run_dir / "study.duckdb"
    if not db.exists():
        raise ValueError(f"missing store: {db}")
    con = duckdb.connect(str(db), read_only=True)
    try:
        rows = con.execute(
            "SELECT agent_id, action_payload FROM panel "
            "WHERE step = 1 AND action_kind = 'sce_answer'").fetchall()
    finally:
        con.close()
    out = {}
    for agent_id, payload in rows:
        if isinstance(payload, str):
            payload = json.loads(payload)
        out[agent_id] = payload
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    trial, out = args.trial.resolve(), args.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT / "outputs"):
        raise ValueError("fresh ignored output directory required")
    plan = json.loads((trial / "trial_manifest.json").read_text())
    if (plan.get("status") != "completed_pending_analysis" or len(plan.get("jobs", [])) != 16
            or any(j.get("exit_code") != 0 for j in plan["jobs"])):
        raise ValueError("completed sixteen-job U1 trial required")
    check_frozen(ROOT, trial, plan)
    records, run_ids, returned_models = [], [], Counter()
    total_calls = total_errors = 0
    estimated_cost = 0.0
    for job in plan["jobs"]:
        month, arm, repeat, run_id = job["month"], job["arm"], job["repeat"], job["run_id"]
        if arm not in ARMS or month not in MONTHS or repeat not in (1, 2):
            raise ValueError("unregistered job cell")
        run_ids.append(run_id)
        run_dir = ROOT / "outputs" / "local_runs" / run_id
        calls = [json.loads(s) for s in (run_dir / "llm_calls.jsonl").read_text().splitlines()]
        if len(calls) != 12:
            raise ValueError(f"{run_id}: expected twelve recorded calls")
        total_calls += len(calls)
        total_errors += sum(bool(c["error"]) for c in calls)
        for c in calls:
            returned_models[c.get("returned_model")] += 1
        ledger = json.loads((run_dir / "cost_ledger.json").read_text())
        estimated_cost += ledger["estimated_cost_usd"]
        previews = {p["agent_id"]: p for p in json.loads(
            (trial / month / f"preview_{arm}.json").read_text())}
        answers = run_answers(run_dir)
        if set(answers) != set(previews) or len(answers) != 12:
            raise ValueError(f"{run_id}: stored answers do not match the roster")
        for agent_id, payload in sorted(answers.items()):
            if payload.get("u1_arm") != arm or payload.get("research_line") != LINE:
                raise ValueError(f"{run_id}: payload arm/line mismatch for {agent_id}")
            if payload.get("u1_messages_sha256") != previews[agent_id]["prompt_sha256"]:
                raise ValueError(f"{run_id}: payload prompt hash mismatch for {agent_id}")
            if payload.get("prompt_version") != PROMPT_VERSION:
                raise ValueError(f"{run_id}: unexpected prompt version")
            valid_q9 = payload.get("validation_status") == "valid"
            bins = [payload.get(f"q9_bin{i}") for i in range(1, 11)]
            q9 = [float(b) for b in bins] if valid_q9 else None
            if q9 is not None and (len(q9) != 10 or abs(sum(q9) - 100.0) > 1e-6
                                   or any(b < 0 or b > 100 for b in q9)):
                raise ValueError(f"{run_id}: legal-valid answer with illegal bins")
            records.append({"month": int(month), "agent_id": agent_id, "repeat": repeat,
                            "arm": arm, "q8_point_pct": point_value(payload),
                            "q9_probabilities": q9})
    if len(records) != 192:
        raise ValueError("192 answer rows required")
    keys = [(r["month"], r["agent_id"], r["repeat"], r["arm"]) for r in records]
    if len(set(keys)) != 192:
        raise ValueError("duplicate answer rows")
    out.mkdir(parents=True)
    text = "".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n"
                   for r in sorted(records, key=lambda r: (r["month"], r["arm"], r["repeat"], r["agent_id"])))
    (out / "evaluation_answers_private.jsonl").write_text(text, encoding="utf-8")
    manifest = {
        "answers_sha256": sha(out / "evaluation_answers_private.jsonl"),
        "research_line": LINE,
        "months": [int(m) for m in MONTHS],
        "repeats": [1, 2],
        "arms": list(ARMS),
        "model_requested": MODEL,
        "temperature": TEMPERATURE,
        "run_ids": run_ids,
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "trial_folder": str(trial.relative_to(ROOT)),
        "trial_manifest_sha256": sha(trial / "trial_manifest.json"),
        "recorded_calls": total_calls,
        "request_errors": total_errors,
        "null_q8_rows": sum(r["q8_point_pct"] is None for r in records),
        "null_q9_rows": sum(r["q9_probabilities"] is None for r in records),
        "returned_model_counts": dict(returned_models),
        "estimated_cost_usd_sum_peak_rates": round(estimated_cost, 6),
        "cost_note": "self-recorded peak-rate estimate from per-run cost_ledger.json; not a vendor bill",
    }
    dump(out / "evaluation_manifest.json", manifest)
    print(json.dumps({k: manifest[k] for k in ("recorded_calls", "request_errors",
          "null_q8_rows", "null_q9_rows", "estimated_cost_usd_sum_peak_rates")}))


if __name__ == "__main__":
    main()
