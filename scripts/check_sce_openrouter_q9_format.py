#!/usr/bin/env python3
"""One public-input Qwen Q9 format check using existing routing/billing helpers.

prepare is offline. run requires a frozen approval record and makes one request,
without retries/fallbacks. It does not run or alter the SCE research experiment.
"""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent / "socioverse2_repo"))
import studies
studies.__path__ = [str(ROOT / "studies"), *studies.__path__]
from studies.sce_inflation_expectations.model import validate_sce_bins
from studies.sce_inflation_expectations.model_counterfactual import preflight, request_bound, billing, guarded_payload
from studies.sce_inflation_expectations.news_label_trial import dotenv_values
from studies.sce_inflation_expectations.platform_survey_pilot import write_new, sha, now
from studies.sce_inflation_expectations.output_format_example import FORMAT_VERSION, append_format_example

BASE = "https://openrouter.ai/api/v1"
MODEL = "qwen/qwen-2.5-72b-instruct"
ROUTE = "deepinfra/fp8"


def prepare(folder):
    candidate_file = ROOT / "docs/workstreams/20261020_procurement/native_questionnaire_candidates_v1.json"
    question = json.loads(candidate_file.read_text())["q9_candidate"]
    text = question["question"] + "\nOptions in order:\n" + "\n".join(
        f"bin{i}: {label}" for i, label in enumerate(question["options"], 1))
    row = {"route_candidate": ROUTE, "input_price_per_million": .36, "output_price_per_million": .4,
           "payload": {"model": MODEL, "temperature": .5, "max_tokens": 1024,
                       "response_format": {"type": "json_object"},
                       "provider": {"order": [ROUTE], "allow_fallbacks": False, "require_parameters": True},
                       "messages": [{"role": "user", "content": text}]}}
    row["payload"]["messages"] = append_format_example(
        row["payload"]["messages"], include_point=False, include_reason=False)
    payload = guarded_payload(row)
    metadata = ROOT / "data/raw/mcp_checks/2026-10-20_openrouter_format_free_v1/qwen_endpoints.json"
    preflight(row, json.loads(metadata.read_text()))
    bound = request_bound(payload, .36, .4)
    old_receipt = ROOT / "docs/workstreams/20261019_advisor_followup/qwen_migration_results_v1/run_receipt.json"
    old_reservation = json.loads(old_receipt.read_text())["estimated_usage_cost_usd"]
    completed_format = ROOT / "docs/workstreams/20261020_procurement/openrouter_q9_format_result_v1.json"
    if completed_format.exists():
        old_reservation += json.loads(completed_format.read_text())["api_reported_cost_usd"]
    if bound > .01 or old_reservation + bound > 1.0:
        raise ValueError("Existing cumulative budget or tiny-probe reservation exceeded")
    folder.mkdir(parents=True, exist_ok=False)
    write_new(folder / "row.json", row)
    write_new(folder / "payload.json", payload)
    write_new(folder / "protocol.json", {"purpose": "one public Q9 format check, not fit/model comparison",
        "created_at_utc": now(), "destination": BASE, "model": MODEL, "provider_route": ROUTE,
        "request_count": 1, "automatic_retries": 0, "payload_sha256": sha(folder / "payload.json"),
        "row_sha256": sha(folder / "row.json"), "code_sha256": sha(Path(__file__)),
        "subcap_usd": .01, "prior_openrouter_reserved_usd": old_reservation,
        "original_approved_openrouter_cap_usd": 1.0, "request_reservation_usd": bound,
        "new_input": "public BLS context and Q9 question/ranges; no persona, no SCE records/history/answers",
        "candidate_sha256": sha(candidate_file), "provider_metadata_sha256": sha(metadata),
        "output_format_version": FORMAT_VERSION, "format_example_contains_numeric_answers": False,
        "source_sha256": {str(p.relative_to(ROOT)): sha(p) for p in [
            ROOT / "studies/sce_inflation_expectations/model_counterfactual.py",
            ROOT / "studies/sce_inflation_expectations/model.py",
            ROOT / "studies/sce_inflation_expectations/output_format_example.py"]},
        "limits": "Different model, model-facing prompt and JSON mode from MCP; no causal wrapper comparison or fit claim."})
    return {"status": "prepared_offline", "new_max_requests": 1, "request_reservation_usd": bound}


def execute(folder):
    p = json.loads((folder / "protocol.json").read_text())
    a = json.loads((folder / "authorization.json").read_text())
    if a.get("approved") is not True or a.get("protocol_sha256") != sha(folder / "protocol.json") or not a.get("user_confirmation"):
        raise ValueError("Explicit approval missing")
    for field, file in [("payload_sha256", "payload.json"), ("row_sha256", "row.json")]:
        if sha(folder / file) != p[field]: raise ValueError("Frozen input changed")
    if sha(Path(__file__)) != p["code_sha256"]: raise ValueError("Probe source changed")
    for name, digest in p["source_sha256"].items():
        if sha(ROOT / name) != digest: raise ValueError("Shared source changed")
    payload = json.loads((folder / "payload.json").read_text())
    row = json.loads((folder / "row.json").read_text())
    bound = request_bound(payload, .36, .4)
    if (payload != guarded_payload(row) or payload["model"] != MODEL or row["route_candidate"] != ROUTE or
        p["destination"] != BASE or p["request_count"] != 1 or p["automatic_retries"] != 0 or
        bound > .01 or p["prior_openrouter_reserved_usd"] + bound > 1.0):
        raise ValueError("Scope/budget mismatch")
    key = os.environ.get("OPENROUTER_API_KEY") or dotenv_values(ROOT.parent / "socioverse2_repo/.env").get("OPENROUTER_API_KEY")
    if not key: raise ValueError("OpenRouter credential missing")
    write_new(folder / "execution_started.json", {"at_utc": now(), "requests": 1, "automatic_retries": 0})
    import httpx
    started = time.perf_counter()
    summary = {"paid_attempts": 1, "automatic_retries": 0, "q9_valid": False, "actual_charge_usd": None}
    reply = {}
    try:
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            response = client.post(BASE + "/chat/completions", headers={"Authorization": "Bearer " + key}, json=payload)
        summary["http_status"] = response.status_code
        if response.status_code != 200: raise RuntimeError("non_200_response_no_retry")
        reply = response.json()
        # Do not persist credentials in any unexpectedly echoed response text.
        reply = json.loads(json.dumps(reply, ensure_ascii=False).replace(key, "<redacted>"))
        write_new(folder / "raw_response.json", reply)
        summary.update(returned_model=reply.get("model"), returned_provider=reply.get("provider"))
        if reply.get("model") != MODEL or reply.get("provider") != "DeepInfra":
            raise ValueError("Locked model/provider mismatch")
        choice = reply["choices"][0]
        content = choice["message"]["content"]
        obj = json.loads(content)
        q9 = obj["q9"]
        bins = [q9[f"bin{i}"] for i in range(1, 11)]
        if not all(type(v) in (float, int) and math.isfinite(v) for v in bins):
            raise ValueError("Ten finite numeric probabilities required")
        valid, error, total = validate_sce_bins(bins)
        summary.update(q9_valid=valid, q9_error=error, probabilities=bins, probability_sum=total,
                       finish_reason=choice.get("finish_reason"), original_content=content)
        summary["status"] = "valid_q9_format_only" if valid and choice.get("finish_reason") == "stop" else "invalid_or_incomplete_no_retry"
    except Exception as exc:
        summary.update(status="failed_or_unusable_no_retry", error_type=type(exc).__name__)
    summary.update(elapsed_seconds=round(time.perf_counter() - started, 3), finished_at_utc=now(),
                   billing=billing(reply, row, bound), request_reservation_usd=bound,
                   protocol_sha256=sha(folder / "protocol.json"), normalization=False,
                   fit_metrics=None, output_scope="public formatting check; not same-person GPT comparison")
    write_new(folder / "inspection.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "run"])
    parser.add_argument("--folder", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.folder.resolve()) if args.mode == "prepare" else execute(args.folder.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
