"""Execute or resume supplemental labels with cumulative, no-retry accounting."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

from .experiments.frozen_batch import ROOT, dump, sha
from .news_mechanism_labels import (
    INPUT_USD_PER_MTOK,
    MAX_TOKENS,
    OUTPUT_USD_PER_MTOK,
    PUBLIC_FIELDS,
    validate_label_payload,
)
from .news_label_trial import dotenv_values

DESTINATION = "https://api.deepseek.com/v1/chat/completions"


def resolve_deepseek_key(environ, dotenv_path):
    dotenv_path = Path(dotenv_path)
    config = dotenv_values(dotenv_path) if dotenv_path.exists() else {}
    key = environ.get("DEEPSEEK_API_KEY") or config.get("DEEPSEEK_API_KEY")
    if key:
        return key
    host = environ.get("SV_LLM_BASE_URL") or config.get("SV_LLM_BASE_URL") or ""
    if host.rstrip("/") not in {"https://api.deepseek.com", "https://api.deepseek.com/v1"}:
        return None
    return environ.get("SV_LLM_API_KEY") or config.get("SV_LLM_API_KEY")


def stamp():
    return datetime.now(timezone.utc).isoformat()


def append(path, value):
    with Path(path).open("a") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")


def rows(path):
    path = Path(path)
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def guarded_payload(row):
    payload = row["payload"]
    if set(payload) != {"model", "temperature", "max_tokens", "response_format", "thinking", "messages"}:
        raise ValueError("unexpected request fields")
    if payload["model"] != "deepseek-flash" or payload["temperature"] != 0 or payload["max_tokens"] != MAX_TOKENS:
        raise ValueError("unregistered model or settings")
    if payload["thinking"] != {"type": "disabled"} or payload["response_format"] != {"type": "json_object"}:
        raise ValueError("unregistered response settings")
    messages = payload["messages"]
    if len(messages) != 2 or [message["role"] for message in messages] != ["system", "user"]:
        raise ValueError("unexpected message structure")
    articles = json.loads(messages[1]["content"])["articles"]
    if not 1 <= len(articles) <= 8 or any(set(article) != set(PUBLIC_FIELDS) for article in articles):
        raise ValueError("public input whitelist or batch size failed")
    if [article["article_id"] for article in articles] != row["article_ids"]:
        raise ValueError("batch article IDs changed")
    bound = len(json.dumps(messages, ensure_ascii=False).encode()) + 512
    expected = (bound * INPUT_USD_PER_MTOK + MAX_TOKENS * OUTPUT_USD_PER_MTOK) / 1e6
    if bound != row["input_token_reservation"] or abs(expected - row["request_usd_reservation"]) > 1e-12:
        raise ValueError("request reservation changed")
    return articles


def recover_ledger(directory, request_by_id, label_mode="supplemental2"):
    directory = Path(directory)
    intents = rows(directory / "intents.jsonl")
    calls = rows(directory / "calls.jsonl")
    intent_ids = [row["batch_id"] for row in intents]
    call_ids = [row["batch_id"] for row in calls]
    if len(intent_ids) != len(set(intent_ids)) or len(call_ids) != len(set(call_ids)):
        raise ValueError("duplicate intent or paid call in ledger")
    if any(batch_id not in request_by_id for batch_id in intent_ids + call_ids):
        raise ValueError("ledger batch outside frozen request scope")
    attempted = set(intent_ids) | set(call_ids)
    call_by_id = {row["batch_id"]: row for row in calls}
    spent = 0.0
    prompt_tokens = 0
    completion_tokens = 0
    for batch_id in attempted:
        call = call_by_id.get(batch_id, {})
        spent += call.get("token_cost_estimate_peak_uncached_usd", request_by_id[batch_id]["request_usd_reservation"])
        usage = call.get("usage") or {}
        prompt_tokens += usage.get("prompt_tokens", 0)
        completion_tokens += usage.get("completion_tokens", 0)
    response_ids = {int(path.stem.split("_")[1]) for path in directory.glob("response_*.json")}
    if not response_ids <= attempted:
        raise ValueError("response has no dispatch intent; manual reconciliation required")
    valid = {}
    for batch_id in sorted(response_ids):
        path = directory / f"response_{batch_id:03d}.json"
        raw = path.read_bytes()
        call = call_by_id.get(batch_id, {})
        if call.get("response_sha256") not in (None, hashlib.sha256(raw).hexdigest()):
            raise ValueError("response hash differs from call ledger")
        try:
            reply = json.loads(raw)
            choice = reply["choices"][0]
            if choice.get("finish_reason") != "stop":
                continue
            inputs = guarded_payload(request_by_id[batch_id])
            valid[batch_id] = validate_label_payload(choice["message"]["content"], inputs, label_mode)
        except (ValueError, TypeError, KeyError, IndexError):
            if not call or call.get("validation") == "pass":
                raise
            continue
    return {
        "attempted": attempted, "valid": valid, "spent_or_reserved_upper_usd": spent,
        "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "errors": sum("error_type" in row for row in calls),
    }


def write_derived_labels(out, recovered):
    out = Path(out)
    lines = []
    for batch_id, labels in sorted(recovered["valid"].items()):
        dump(out / f"labels_{batch_id:03d}.json", labels)
        lines.extend(json.dumps({"batch_id": batch_id, "label": label}, ensure_ascii=False) for label in labels)
    (out / "labels.jsonl").write_text("".join(line + "\n" for line in lines))


def execute(inputs, out, authorization_note=None, resume=False):
    inputs = Path(inputs).resolve()
    out = Path(out).resolve()
    plan = json.loads((inputs / "summary.json").read_text())
    request_path = inputs / "requests_prepared.jsonl"
    if sha(request_path) != plan["request_file_sha256"]:
        raise ValueError("request package hash changed")
    if sha(inputs / "pending_public_articles.json") != plan["pending_articles_sha256"]:
        raise ValueError("public article text package hash changed")
    for relative, expected in plan["source_sha256"].items():
        if sha(ROOT / relative) != expected:
            raise ValueError("source changed: " + relative)
    requests = rows(request_path)
    request_by_id = {row["batch_id"]: row for row in requests}
    for row in requests:
        guarded_payload(row)
        if hashlib.sha256(row["payload"]["messages"][0]["content"].encode()).hexdigest() != plan["system_prompt_sha256"]:
            raise ValueError("system prompt changed")
    ids = [article_id for row in requests for article_id in row["article_ids"]]
    if len(ids) != len(set(ids)) or len(ids) != plan["unique_articles_to_label"]:
        raise ValueError("frozen article scope differs")
    cap = plan["proposed_budget_usd"]
    label_mode = plan.get("label_mode", "supplemental2")
    print(json.dumps({"status": "validated_offline", "articles": len(ids), "batches": len(requests), "cap_usd": cap}), flush=True)
    if not resume and authorization_note is None:
        return {"status": "offline_only", "articles": len(ids), "cap_usd": cap}
    key = resolve_deepseek_key(os.environ, ROOT.parent / "socioverse2_repo/.env")
    if resume:
        if not (out / "authorization.json").exists():
            raise ValueError("resume requires original authorization")
    else:
        if not authorization_note or not key:
            raise ValueError("explicit authorization and DeepSeek credential are required")
        out.mkdir(parents=True, exist_ok=False)
        dump(out / "authorization.json", {"approved": True, "note": authorization_note, "cap_usd": cap,
                                           "request_file_sha256": sha(request_path), "authorized_at_utc": stamp()})
    if not key:
        raise ValueError("DeepSeek credential is required")
    recovered = recover_ledger(out, request_by_id, label_mode)
    state = {"run_id": out.name, "status": "running", "schema": "sce_news_mechanism_label_run/v1",
             "input_request_file_sha256": sha(request_path), "plan_sha256": sha(inputs / "summary.json"),
             "cap_usd": cap, "articles_planned": len(ids), "batches_planned": len(requests),
             "destination": DESTINATION, "label_mode": label_mode, "retry_policy": "none", **recovered}
    for row in requests:
        batch_id = row["batch_id"]
        if batch_id in recovered["attempted"]:
            continue
        if state["spent_or_reserved_upper_usd"] + row["request_usd_reservation"] > cap:
            state["status"] = "budget_stopped"
            break
        state["spent_or_reserved_upper_usd"] += row["request_usd_reservation"]
        state["batches_attempted"] = len(recovered["attempted"]) + 1
        dump(out / "state.json", {key: value for key, value in state.items() if key not in {"attempted", "valid"}})
        append(out / "intents.jsonl", {"batch_id": batch_id, "started_at_utc": stamp(),
                                      "request_usd_reservation": row["request_usd_reservation"],
                                      "request_sha256": hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()})
        audit = {"batch_id": batch_id, "started_at_utc": stamp(), "requested_model": row["payload"]["model"]}
        start = time.monotonic()
        try:
            request = urllib.request.Request(
                DESTINATION, data=json.dumps(row["payload"], ensure_ascii=False).encode(),
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read()
                audit["http_status"] = response.status
                audit["header_request_id"] = response.headers.get("x-request-id")
            (out / f"response_{batch_id:03d}.json").write_bytes(raw)
            reply = json.loads(raw)
            audit.update(response_sha256=hashlib.sha256(raw).hexdigest(), response_id=reply.get("id"),
                         returned_model=reply.get("model"), system_fingerprint=reply.get("system_fingerprint"),
                         usage=reply.get("usage"))
            usage = reply.get("usage") or {}
            prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
            if isinstance(prompt, int) and isinstance(completion, int) and prompt >= 0 and completion >= 0:
                cost = (prompt * INPUT_USD_PER_MTOK + completion * OUTPUT_USD_PER_MTOK) / 1e6
                state["spent_or_reserved_upper_usd"] += cost - row["request_usd_reservation"]
                state["prompt_tokens"] += prompt
                state["completion_tokens"] += completion
                audit["token_cost_estimate_peak_uncached_usd"] = cost
            choice = reply["choices"][0]
            audit["finish_reason"] = choice.get("finish_reason")
            if choice.get("finish_reason") != "stop":
                raise ValueError("incomplete completion")
            labels = validate_label_payload(choice["message"]["content"], guarded_payload(row), label_mode)
            dump(out / f"labels_{batch_id:03d}.json", labels)
            recovered["valid"][batch_id] = labels
            audit["validation"] = "pass"
        except Exception as exc:
            audit["error_type"] = type(exc).__name__
            audit["error_detail"] = str(exc)[:220]
            state["errors"] += 1
            state["status"] = "stopped_on_error"
        audit["finished_at_utc"] = stamp()
        audit["latency_ms"] = round((time.monotonic() - start) * 1000, 1)
        append(out / "calls.jsonl", audit)
        recovered["attempted"].add(batch_id)
        if state["status"] != "running":
            break
        if len(recovered["attempted"]) % 10 == 0:
            print(json.dumps({"attempted": len(recovered["attempted"]), "valid_articles": sum(map(len, recovered["valid"].values())),
                              "spent_or_reserved_upper_usd": state["spent_or_reserved_upper_usd"]}), flush=True)
    write_derived_labels(out, recovered)
    valid_articles = sum(map(len, recovered["valid"].values()))
    if state["status"] == "running":
        state["status"] = "completed" if valid_articles == len(ids) and len(recovered["valid"]) == len(requests) else "incomplete"
    state.update(batches_attempted=len(recovered["attempted"]), batches_valid=len(recovered["valid"]),
                 articles_valid=valid_articles, finished_at_utc=stamp())
    public_state = {key: value for key, value in state.items() if key not in {"attempted", "valid"}}
    dump(out / "state.json", public_state)
    print(json.dumps(public_state, ensure_ascii=False), flush=True)
    return public_state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--authorization-note")
    args = parser.parse_args()
    if args.execute and args.resume:
        parser.error("choose execute or resume")
    execute(args.inputs, args.out, args.authorization_note if args.execute else None, args.resume)


if __name__ == "__main__":
    main()
