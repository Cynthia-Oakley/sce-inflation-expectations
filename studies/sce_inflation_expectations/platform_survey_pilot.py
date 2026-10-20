"""One bounded official population-survey compatibility probe, not an SCE trial.

No survey microdata, model fitting, automatic retry, or replacement of the
project's individual-input simulation route. Full MCP content is retained.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
TOOL = "run_user_pool_distribution_simulation"
HOST = "mcp.socioverse.fudan-disc.com"


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def bin_labels():
    # Read the existing questionnaire constant without importing the LLM engine.
    tree = ast.parse((Path(__file__).parent / "model.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "Q9_BIN_LABELS" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError("Missing frozen Q9 labels")


def check_request(request, schema):
    """Bounded checks for this exact request, not a general JSON Schema engine."""
    properties = schema["properties"]
    if set(request) - set(properties) or set(schema["required"]) - set(request):
        raise ValueError("Unknown or missing MCP arguments")
    for field, value in request.items():
        spec = properties[field]
        kind = spec.get("type")
        expected = {"integer": int, "boolean": bool, "string": str, "object": dict, "array": list}
        if kind in expected and type(value) is not expected[kind]:
            raise ValueError(f"Wrong type: {field}")
        if kind == "integer" and not spec.get("minimum", value) <= value <= spec.get("maximum", value):
            raise ValueError(f"Out of schema range: {field}")
    if (request["distributions"] != {"GENDER": {"Female": 50, "Male": 50}} or
        request["seed"] != 20261020 or request["prompt_language"] != "en" or
        request["sampling_mode"] != "preserve_joint" or request["max_workers"] != 2 or
        len(request["questionnaire"]) != 1):
        raise ValueError("Unexpected pilot sampling/questionnaire scope")
    question = request["questionnaire"][0]
    if set(question) != {"question", "options"} or not isinstance(question["question"], str) or question["options"] != []:
        raise ValueError("Unexpected open-text carrier")


def prepare(folder):

    evidence = ROOT / "data/raw/mcp_checks/2026-10-20_procurement_free_v1/evidence.json"
    cache = json.loads(evidence.read_text())
    schema = next(t["inputSchema"] for t in cache["tools"] if t["name"] == TOOL)
    price_path = ROOT / "outputs/sce_procurement_price_views_20261020_v3/category_prices.json"
    price = json.loads(price_path.read_text())["202206"]["food_at_home"]
    bins = "\n".join(f"bin{i}: {label}" for i, label in enumerate(bin_labels(), 1))
    question = (
        "Please answer as the household respondent described by your assigned profile. "
        "The survey date is June 10, 2022. Consider only information available by that date.\n"
        "Public background: the BLS release of June 10, 2022 reports that US food-at-home "
        f"prices in May 2022 increased {price['yoy_nsa_percent']}% from May 2021 and "
        f"{price['mom_nsa_percent']}% from April 2022 (both not seasonally adjusted). "
        "This describes one price category, not the future overall inflation rate.\n\n"
        "Q8: What do you expect the overall inflation or deflation rate to be over the "
        "next 12 months? Give a signed percentage: positive for inflation, negative "
        "for deflation.\n"
        "Q9: What is the percent chance that the overall inflation or deflation rate "
        "over the next 12 months falls in each of the following ten ranges?\n"
        f"{bins}\n"
        "Each probability must be between 0 and 100 and the ten probabilities must "
        "sum to 100. Return a single JSON object, with no surrounding explanation: "
        '{"point_pct": NUMBER, "q9": {"bin1": NUMBER, "bin2": NUMBER, '
        '"bin3": NUMBER, "bin4": NUMBER, "bin5": NUMBER, "bin6": NUMBER, '
        '"bin7": NUMBER, "bin8": NUMBER, "bin9": NUMBER, "bin10": NUMBER}}.'
    )
    request = {"platform_id": "nemotron_usa", "distributions": {"GENDER": {"Female": 50, "Male": 50}},
               "user_count": 10, "questionnaire": [{"question": question, "options": []}],
               "prompt_language": "en", "max_workers": 2, "seed": 20261020,
               "allow_virtual_users": False, "sampling_mode": "preserve_joint"}
    check_request(request, schema)
    folder.mkdir(parents=True, exist_ok=False)
    write_new(folder / "request.json", request)
    write_new(folder / "tool_schema.json", schema)
    protocol = {"created_at_utc": now(), "purpose": "technical compatibility only; no fit claim",
                "tool": TOOL, "destination_host": HOST, "expected_server_model": "gpt-4o-mini",
                "request_sha256": sha(folder / "request.json"), "request_count": 1,
                "user_count": 10, "automatic_retries": 0, "unit_price_usd_email": "0.004",
                "estimated_usd_email": "0.040", "budget_cap_usd": "0.10",
                "remote_budget_enforcement": False, "remote_internal_retries": "not exposed",
                "price_note": "Organizer email rate, not a verified current invoice. No remote budget parameter.",
                "billing_evidence": "docs/LOCAL_RUNTIME_ACCEPTANCE.md",
                "credential_source": "official gen_mcp_json.load_env, user_pool_survey_mcp",
                "input_scope": "public BLS price fact and questionnaire only; no SCE person/history/answers",
                "population": "platform Nemotron-Personas-USA synthetic pool; CC-BY-4.0; not SCE",
                "pool_attribution": "NVIDIA, https://huggingface.co/datasets/nvidia/Nemotron-Personas-USA",
                "sampling_note": "50/50 gender for compatibility only; not nationally representative",
                "questionnaire_note": "Q8/Q9 in one open-text carrier, not the original survey UI; support unknown",
                "time_boundary_note": "Historical role play, not a blind forecast; training knowledge not excluded",
                "sources": {"capability_path": str(evidence.relative_to(ROOT)), "capability_sha256": sha(evidence),
                            "prices_path": str(price_path.relative_to(ROOT)), "prices_sha256": sha(price_path),
                            "price_fact": price},
                "code_sha256": sha(Path(__file__))}
    write_new(folder / "protocol.json", protocol)
    write_new(folder / "readiness.json", {"protocol_sha256": sha(folder / "protocol.json"),
        "request_schema_valid": True, "supported_gender_labels_checked_free": True,
        "per_person_raw_answers_supported": "advertised, not yet demonstrated",
        "open_text_and_q9_supported": "not yet demonstrated", "paid_calls": 0,
        "estimated_usd_email": "0.040", "budget_cap_usd": "0.10"})
    return {"status": "prepared_no_paid_calls", "folder": str(folder), "people": 10,
            "estimated_usd": "0.040", "cap_usd": "0.10", "protocol_sha256": sha(folder / "protocol.json")}


def validate_approval(folder):
    protocol = json.loads((folder / "protocol.json").read_text())
    request = json.loads((folder / "request.json").read_text())
    authorization = json.loads((folder / "authorization.json").read_text())
    if (authorization.get("approved") is not True or
        authorization.get("protocol_sha256") != sha(folder / "protocol.json") or
        not authorization.get("user_confirmation")):
        raise ValueError("Explicit approval for this exact protocol is required")
    cap = Decimal(protocol["budget_cap_usd"])
    reservation = Decimal(protocol["unit_price_usd_email"]) * request["user_count"]
    if (Decimal(authorization["cap_usd"]) < cap or cap > Decimal("0.10") or reservation > cap or
        protocol["automatic_retries"] != 0 or protocol["request_count"] != 1 or
        protocol["tool"] != TOOL or protocol["destination_host"] != HOST or
        protocol["user_count"] != 10 or request["user_count"] != 10 or
        request["platform_id"] != "nemotron_usa" or request["allow_virtual_users"] is not False or
        protocol["request_sha256"] != sha(folder / "request.json") or
        protocol["code_sha256"] != sha(Path(__file__))):
        raise ValueError("Pilot scope, hash, or budget mismatch")
    return protocol, request


def execute(folder):
    # Importing only after authorization keeps prepare/offline work network-free.
    protocol, request = validate_approval(folder)
    from scripts import check_mcp_free_capabilities as transport
    from scripts.run_sce_event_probe import sanitize

    env = transport.gen_mcp_json.load_env()
    url_var, key_var = transport.gen_mcp_json.SERVICES["user_pool_survey_mcp"]
    endpoint, key = env.get(url_var, ""), env.get(key_var, "")
    parts = urlsplit(endpoint)
    if parts.scheme != "https" or parts.hostname != HOST or not key:
        raise ValueError("Unexpected destination or missing credential")
    write_new(folder / "execution_started.json", {"at_utc": now(), "no_resume": True,
              "protocol_sha256": sha(folder / "protocol.json")})
    transport.TIMEOUT = 180
    client = transport.McpHttpClient(endpoint, key)
    client.initialize()
    capability = client.call_tool("get_user_pool_simulation_capabilities", {})
    write_new(folder / "runtime_capabilities.json", sanitize(capability, key))
    actual_model = capability.get("llm", {}).get("model")
    if actual_model != protocol["expected_server_model"] or capability.get("llm", {}).get("mock_enabled") is not False:
        raise ValueError("Server model/config changed; stop before paid call")
    write_new(folder / "paid_attempt_started.json", {"at_utc": now(), "respondents_reserved": 10,
              "reservation_usd_email_rate": protocol["estimated_usd_email"], "automatic_retries": 0})
    try:
        # call_tool() truncates non-JSON text: rpc() retains ALL content blocks/JSONL.
        response = sanitize(client.rpc("tools/call", {"name": TOOL, "arguments": request}), key)
        write_new(folder / "raw_response.json", response)
        status = "tool_error_no_retry" if response.get("isError") else "response_received_needs_answer_validation"
        result = {"status": status, "finished_at_utc": now(), "paid_tool_attempts": 1,
                  "requested_respondents": 10, "server_configured_model": actual_model,
                  "raw_sha256": sha(folder / "raw_response.json"), "automatic_retries": 0,
                  "estimated_usd_email_rate_not_invoice": protocol["estimated_usd_email"],
                  "actual_charge_usd": None, "model_per_response_identity_verified": False}
    except Exception as exc:
        result = {"status": "transport_or_local_failure_no_retry", "finished_at_utc": now(),
                  "paid_tool_attempts": 1, "error_type": type(exc).__name__,
                  "http_status": getattr(exc, "code", None), "may_have_been_billed": True,
                  "automatic_retries": 0}
    write_new(folder / "completion.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "run"])
    parser.add_argument("--folder", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.folder.resolve()) if args.mode == "prepare" else execute(args.folder.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
