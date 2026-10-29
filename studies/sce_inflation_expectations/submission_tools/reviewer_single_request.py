"""Preview a shareable frozen input; make one paid request only when confirmed.

Standalone companion for the proposed input layer. It does not regenerate a
recursive chain or alter archived results. Default operation reads no API key.
"""
import argparse
import gzip
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path


MODEL = "deepseek/deepseek-v3.2"
DESTINATION = "https://openrouter.ai/api/v1"
ROUTE = "siliconflow/fp8"
CAP_USD = .01


def read(path):
    return json.loads(Path(path).read_text())


def write(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def list_inputs(candidate, *, run=None, period=None, limit=10):
    """List anonymous complete samples without credentials or a model client."""
    if not 1 <= limit <= 1000:
        raise ValueError("List limit must be between 1 and 1000")
    candidate = Path(candidate).resolve()
    manifest = read(candidate / ("manifest.json" if (candidate / "manifest.json").exists() else "candidate_manifest.json"))
    name = manifest.get("complete_prompt_file", "complete_news_free_prompts.jsonl.gz")
    path = candidate / name
    if path.name != name or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != manifest["files"][name]["sha256"]:
        raise ValueError("Complete prompt collection changed")
    selected = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if (run is None or row["run"] == run) and (period is None or row["period"] == period):
                selected.append({k: row[k] for k in ("run", "period", "household", "original_prompt_sha256")})
                if len(selected) == limit:
                    break
    return dict(status="offline_complete_input_listing", samples=selected, new_API_calls=0, credentials_read=False)


def load(candidate, *, run=None, period=None, household=None):
    candidate = Path(candidate).resolve()
    manifest = read(candidate / ("manifest.json" if (candidate / "manifest.json").exists() else "candidate_manifest.json"))
    for name in ("one_complete_prompt_example.json", "generation_settings.json"):
        path = candidate / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != manifest["files"][name]["sha256"]:
            raise ValueError("Frozen candidate file changed")
    sample = read(candidate / "one_complete_prompt_example.json")
    if any(v is not None for v in (run, period, household)):
        if not all(v is not None for v in (run, period, household)):
            raise ValueError("Select all three of run, period and household")
        name = manifest.get("complete_prompt_file", "complete_news_free_prompts.jsonl.gz")
        path = candidate / name
        if path.name != name or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != manifest["files"][name]["sha256"]:
            raise ValueError("Complete prompt collection changed")
        sample = None
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if (row["run"], row["period"], row["household"]) == (run, period, household):
                    if sample is not None:
                        raise ValueError("Duplicate complete input")
                    sample = row
        if sample is None:
            raise ValueError("No complete input for this selection; only exact complete messages can be sent")
    settings = read(candidate / "generation_settings.json")
    messages = sample["messages"]
    if (sample.get("ready_for_exact_single_request") is not True or sample.get("withheld")
            or not isinstance(messages, list) or not messages):
        raise ValueError("A complete original input is required; placeholders cannot be sent")
    encoded = json.dumps(messages, ensure_ascii=False).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    if digest != sample["original_prompt_sha256"] or digest != sample["delivered_prompt_sha256"]:
        raise ValueError("Messages no longer match the archived input hash")
    extra = {"provider": {"order": [ROUTE], "allow_fallbacks": False, "require_parameters": True,
                          "max_price": {"prompt": .259, "completion": .8}}, "reasoning": {"enabled": False}}
    if (settings["model"] != MODEL or settings["destination"] != DESTINATION or settings["route"] != ROUTE
            or settings["expected_provider"] != "SiliconFlow" or settings["temperature"] != .5
            or settings["max_tokens"] != 1024 or settings["response_format"] != "json_object"
            or settings["request_extra_body"] != extra):
        raise ValueError("Frozen model, provider, format and price limits are required")
    reserve = ((len(encoded) + 1024) * .259 + 1024 * .8) / 1e6
    if not math.isfinite(reserve) or reserve > CAP_USD:
        raise ValueError("Single-request conservative reservation exceeds one cent")
    return sample, settings, reserve


def send_once(messages, settings, key):
    import httpx
    from openai import OpenAI
    with OpenAI(base_url=DESTINATION, api_key=key, max_retries=0,
                http_client=httpx.Client(timeout=120, follow_redirects=False)) as client:
        reply = client.chat.completions.create(model=MODEL, messages=messages,
            temperature=.5, max_tokens=1024, response_format={"type": "json_object"},
            extra_body=settings["request_extra_body"])
    choice = reply.choices[0] if reply.choices else None
    usage = reply.usage
    return dict(response_text=choice.message.content if choice else None,
                finish_reason=choice.finish_reason if choice else None,
                model=reply.model, provider=getattr(reply, "provider", None),
                usage={k: getattr(usage, k, None) for k in ("prompt_tokens", "completion_tokens", "total_tokens", "cost")})


def run(candidate, *, confirm_paid=False, out=None, sender=None, selection=None):
    sample, settings, reserve = load(candidate, **(selection or {}))
    if not confirm_paid:
        return dict(status="offline_input_preview", model=MODEL, provider="SiliconFlow",
                    original_prompt_sha256=sample["original_prompt_sha256"], messages=sample["messages"],
                    planned_calls_if_confirmed=1, new_API_calls=0, credentials_read=False,
                    conservative_reservation_usd=reserve,
                    scope="Preview of a historical conditional input; no generation performed")
    if out is None:
        raise ValueError("A fresh --out directory is required for a paid request")
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError("Do not overwrite or automatically retry an existing request")
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ValueError("Supply your own OPENROUTER_API_KEY in this Terminal session")
    out.mkdir(parents=True)
    write(out / "input.json", sample)
    record = dict(status="intent_saved_before_dispatch", started_at_utc=datetime.now(timezone.utc).isoformat(),
        planned_calls=1, api_attempts=1, automatic_retries=0, provider_fallbacks=0,
        conservative_reservation_usd=reserve, local_cap_usd=CAP_USD,
        original_prompt_sha256=sample["original_prompt_sha256"],
        execution_kind="live_provider" if sender is None else "injected_sender_test",
        actual_model_results=False,
        scope="One conditional historical input with archived prior; not a newly recursive simulation")
    write(out / "intent.json", record)
    try:
        reply = (sender or send_once)(sample["messages"], settings, key)
    except Exception as exc:
        # Exception strings may contain headers or endpoint information. Never copy them.
        record.update(status="request_failed_no_retry", error_type=type(exc).__name__,
                      outcome_may_have_been_billed=sender is None)
    else:
        # Only allowlisted response fields are archived. Credentials/request IDs are not.
        reply = {k: reply.get(k) for k in ("response_text", "finish_reason", "model", "provider", "usage")}
        usage = reply.get("usage") or {}
        reply["usage"] = {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens", "cost")}
        if key in json.dumps(reply, ensure_ascii=False):
            record.update(status="credential_echo_not_saved_no_retry")
        else:
            write(out / "response.json", reply)
            identity_ok = reply["model"] == MODEL and reply["provider"] == "SiliconFlow"
            fee = reply["usage"].get("cost")
            valid_fee = type(fee) in (int, float) and math.isfinite(fee) and fee >= 0
            record.update(status="model_reply_saved" if identity_ok else "provider_identity_mismatch_no_retry",
                          actual_model_results=sender is None, provider_identity_verified=identity_ok,
                          reported_cost_usd=fee if valid_fee else None,
                          spent_or_reserved_usd=fee if valid_fee else reserve)
            if valid_fee and fee > min(reserve + 1e-9, CAP_USD):
                record["status"] = "reported_cost_anomaly_no_retry"
    record["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    write(out / "receipt.json", record)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--confirm-paid", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--run", choices=("A", "B", "monthly", "weekly"))
    parser.add_argument("--period")
    parser.add_argument("--household")
    parser.add_argument("--list", action="store_true", help="List complete sample keys without reading an API key")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if args.list:
        if args.confirm_paid or args.household or args.out:
            parser.error("Listing is offline; omit paid, household and output options")
        result = list_inputs(args.candidate_dir, run=args.run, period=args.period, limit=args.limit)
    else:
        result = run(args.candidate_dir, confirm_paid=args.confirm_paid, out=args.out,
                     selection=dict(run=args.run, period=args.period, household=args.household))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] not in ("offline_input_preview", "offline_complete_input_listing", "model_reply_saved"):
        raise SystemExit(1)
