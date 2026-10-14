"""Read-only audit linking U1 prepared inputs, recorded requests and exports.

Never re-executes a recorded command or invokes a provider. Cost verification
uses the recorded token rates, not a vendor invoice or a fresh pricing lookup.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np

from .behavior_comparison import dump, sha


def message_hash(messages):
    return hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()


def response_bins(reply):
    q9 = reply["q9"]
    return [float(q9[f"bin{i}"]) for i in range(1, 11)] if isinstance(q9, dict) else list(map(float, q9))


def response_values(reply):
    probabilities = np.asarray(response_bins(reply), float)
    point = float(reply["point_pct"])
    if (probabilities.shape != (10,) or not np.isfinite(probabilities).all()
            or (probabilities < 0).any() or (probabilities > 100).any()
            or abs(probabilities.sum()-100) > 1e-6 or not np.isfinite(point)):
        raise ValueError("Raw response is not a legal Q8/Q9 questionnaire")
    return point, probabilities.tolist()


def run(root, trial, exported, out):
    root, trial, exported, out = map(lambda x: Path(x).resolve(), (root, trial, exported, out))
    if out.exists() or not out.is_relative_to(root / "outputs"):
        raise ValueError("Use a fresh ignored audit directory")
    plan = json.loads((trial / "trial_manifest.json").read_text())
    if plan["status"] != "completed_pending_analysis" or len(plan["jobs"]) != 16:
        raise ValueError("Require a completed sixteen-cell real trial")
    for name, h in {**plan["source_sha256"], **plan["code_sha256"]}.items():
        if sha(root / name) != h:
            raise ValueError("Frozen source/code changed: " + name)
    for name, h in plan["prepared_file_sha256"].items():
        if sha(trial / name) != h:
            raise ValueError("Frozen prepared artifact changed: " + name)
    exported_manifest = json.loads((exported / "evaluation_manifest.json").read_text())
    if sha(trial / "trial_manifest.json") != exported_manifest["trial_manifest_sha256"]:
        raise ValueError("Export refers to a different trial manifest")
    answer_file = exported / "evaluation_answers_private.jsonl"
    if sha(answer_file) != exported_manifest["answers_sha256"]:
        raise ValueError("Exported answer file changed")
    records = [json.loads(s) for s in answer_file.read_text().splitlines()]
    key = lambda r: (int(r["month"]), r["agent_id"], r["arm"], int(r["repeat"]))
    answers = {key(r): r for r in records}
    if len(answers) != len(records) or len(records) != 192:
        raise ValueError("Export duplicate/incorrect row count")
    jobs = {(j["month"], j["arm"], j["repeat"]) for j in plan["jobs"]}
    expected = {(m, a, repeat) for m in plan["months"] for a in plan["arms"] for repeat in (1, 2)}
    if jobs != expected or len({j["run_id"] for j in plan["jobs"]}) != 16:
        raise ValueError("Trial cell/run ID mismatch")
    old_trial = root / "outputs/sce_prior_trial_20261013_v2"
    old_links = json.loads((old_trial / "evaluation_links_private.json").read_text())
    roster = {(r["month"], r["agent_id"]): r["prepared_agent_id"] for r in old_links}
    reviewed = root / "outputs/sce_u1_state_preparation_20261013_v2"
    counts = Counter(); models = Counter(); finishes = Counter()
    cost, token_cost, prompt_tokens, completion_tokens = 0., 0., 0, 0
    runs = []; evidence_hashes = {}
    for job in plan["jobs"]:
        if job["exit_code"] != 0:
            raise ValueError("Failed real job")
        m, arm, repeat, run_id = job["month"], job["arm"], job["repeat"], job["run_id"]
        folder = root / "outputs/local_runs" / run_id
        manifest = json.loads((folder / "run_manifest.json").read_text())
        if (manifest["llm_kind"] != "openai" or manifest["n_agents"] != 12
                or manifest["n_steps"] != 1 or manifest["execution_purpose"] != "u1_state_behaviour_trial"):
            raise ValueError("Run is not the registered real U1 cell")
        for name, h in {**manifest["effective_artifact_sha256"], **manifest["source_snapshot_sha256"]}.items():
            if sha(folder / name) != h:
                raise ValueError("Runtime snapshot changed: " + name)
            if name.startswith("source_snapshot/study/"):
                source = "studies/sce_inflation_expectations/" + name.removeprefix("source_snapshot/study/")
                if plan["code_sha256"].get(source) != h:
                    raise ValueError("Executed source not in frozen trial")
            elif name == "source_snapshot/run_sce_local.py":
                if plan["code_sha256"]["scripts/run_sce_local.py"] != h:
                    raise ValueError("Executed entry differs from frozen trial")
        previews = {r["agent_id"]: r for r in json.loads((trial / m / f"preview_{arm}.json").read_text())}
        prepared = {r["agent_id"]: r for r in json.loads((reviewed / m / f"preview_{arm}.json").read_text())}
        calls = [json.loads(s) for s in (folder / "llm_calls.jsonl").read_text().splitlines()]
        if (len(calls) != 12 or len({c["agent_id"] for c in calls}) != 12
                or {c["agent_id"] for c in calls} != set(previews)):
            raise ValueError("Runtime call roster differs")
        with duckdb.connect(str(folder / "study.duckdb"), read_only=True) as db:
            stored = db.execute("SELECT agent_id, action_payload FROM panel WHERE step=1 AND action_kind='sce_answer'").fetchall()
        payloads = {aid: json.loads(value) if isinstance(value, str) else value for aid, value in stored}
        if len(stored) != 12 or set(payloads) != set(previews):
            raise ValueError("Trajectory answer roster differs")
        cell_prompt, cell_completion = 0, 0
        for c in calls:
            aid = c["agent_id"]; preview = previews[aid]
            accepted = prepared[roster[m, aid]]["messages"]
            actual = json.loads(c["prompt_text"])
            if (actual != accepted or actual != preview["messages"]
                    or message_hash(actual) != c["prompt_sha256"]
                    or c["prompt_sha256"] != preview["prompt_sha256"]):
                raise ValueError("Actual API messages differ from accepted preparation")
            if (c["attempt_idx"] != 0 or c["error"] is not None
                    or c["requested_model"] != plan["model"] or c["temperature"] != .5
                    or c["max_tokens"] != 1024 or c["extra_body"] != {"thinking": {"type": "disabled"}}):
                raise ValueError("Actual call/error/settings differ from registered design")
            response = c["raw_response_text"]
            if hashlib.sha256(response.encode()).hexdigest() != c["raw_response_sha256"]:
                raise ValueError("Raw response hash mismatch")
            raw = json.loads(response)
            payload = payloads[aid]
            exported_row = answers[int(m), aid, arm, repeat]
            point, probabilities = response_values(raw)
            kept = [float(payload[f"q9_bin{i}"]) for i in range(1, 11)]
            if (payload["validation_status"] != "valid" or payload["u1_arm"] != arm
                    or payload["research_line"] != plan["research_line"]
                    or payload["u1_messages_sha256"] != c["prompt_sha256"]
                    or not np.allclose(probabilities, kept, rtol=0, atol=1e-8)
                    or not np.allclose(kept, exported_row["q9_probabilities"], rtol=0, atol=1e-8)
                    or abs(point-float(payload["point_pct"])) > 1e-8
                    or abs(point-exported_row["q8_point_pct"]) > 1e-8):
                raise ValueError("Raw model answer, trajectory and export differ")
            cell_prompt += c["usage"]["prompt_tokens"]
            cell_completion += c["usage"]["completion_tokens"]
            models[c["returned_model"]] += 1; finishes[c["finish_reason"]] += 1
            counts["actual_messages_checked"] += 1
            counts["raw_trajectory_export_matches"] += 1
        ledger = json.loads((folder / "cost_ledger.json").read_text())
        estimate = (cell_prompt * ledger["price_input_per_mtok"]
                    + cell_completion * ledger["price_output_per_mtok"]) / 1e6
        if (ledger["call_count"] != 12 or ledger["total_prompt_tokens"] != cell_prompt
                or ledger["total_completion_tokens"] != cell_completion
                or abs(ledger["estimated_cost_usd"] - estimate) > 5.1e-7
                or ledger["estimated_cost_usd"] > job["job_cap_usd"]
                or abs(job["estimated_cost_usd"]-ledger["estimated_cost_usd"]) > 1e-8):
            raise ValueError("Cost ledger/cap does not match recorded token usage")
        cost += ledger["estimated_cost_usd"]; token_cost += estimate
        prompt_tokens += cell_prompt; completion_tokens += cell_completion
        for name in ("run_manifest.json", "llm_calls.jsonl", "study.duckdb", "cost_ledger.json"):
            evidence_hashes[str((folder/name).relative_to(root))] = sha(folder/name)
        runs.append({"run_id": run_id, "month": m, "arm": arm, "repeat": repeat,
                     "calls": 12, "estimated_cost_usd": ledger["estimated_cost_usd"]})
    dry_path = trial / "engineering_check.json"
    dry = json.loads(dry_path.read_text())
    if len(dry) != 8 or any(d["exit_code"] != 0 for d in dry):
        raise ValueError("Missing successful eight-cell engineering receipt")
    for job in (j for j in plan["jobs"] if j["repeat"] == 1):
        folder = root / "outputs/local_runs" / (job["run_id"] + "-engineering")
        recorded = json.loads((folder / "run_manifest.json").read_text())
        ledger = json.loads((folder / "cost_ledger.json").read_text())
        if recorded["llm_kind"] != "scripted" or ledger["call_count"] != 0:
            raise ValueError("Engineering receipt was not zero-call scripted")
    if counts["actual_messages_checked"] != 192 or cost > plan["proposed_simulation_cap_usd"]:
        raise ValueError("Total count/cost cap mismatch")
    result = {"status": "recorded_runtime_and_export_verified",
              "completed_at": datetime.now(timezone.utc).isoformat(), "runs": runs,
              "counts": dict(counts), "engineering_cells_checked": 8,
              "returned_models": dict(models), "finish_reasons": dict(finishes),
              "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
              "recorded_peak_rate_estimate_usd": cost, "token_rate_estimate_unrounded_usd": token_cost,
              "not_vendor_invoice": True, "new_audit_api_calls": 0,
              "evidence_sha256": evidence_hashes,
              "trial_manifest_sha256": sha(trial/"trial_manifest.json"),
              "export_manifest_sha256": sha(exported/"evaluation_manifest.json"),
              "export_answers_sha256": sha(answer_file),
              "auditor_code_sha256": {name: sha(root/name) for name in (
                  "studies/sce_inflation_expectations/evaluation/u1_execution_audit.py",
                  "scripts/audit_sce_u1_execution.py")},
              "limits": ["Verifies local records, not an independent vendor billing or transport audit.",
                         "Requested/returned aliases do not establish immutable model weights or training cutoff.",
                         "Authorization quotation is stored in Kimi's trial manifest; this audit does not extend it to any new calls."]}
    out.mkdir(parents=True);dump(out/"summary.json",result)
    return result
