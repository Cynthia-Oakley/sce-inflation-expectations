import hashlib
import json

from studies.sce_inflation_expectations.news_mechanism_labels import build_requests
from studies.sce_inflation_expectations.news_mechanism_label_runner import (
    guarded_payload,
    recover_ledger,
    resolve_deepseek_key,
)


def article(article_id="a1"):
    return {"article_id": article_id, "headline": "H", "abstract": "A", "snippet": "",
            "source": "NYT", "section_name": "Business", "news_desk": "Business"}


def test_guarded_payload_checks_ids_whitelist_and_reservation():
    row = build_requests([article()])[0]
    assert guarded_payload(row) == [article()]
    row["request_usd_reservation"] = 0
    try:
        guarded_payload(row)
    except ValueError as exc:
        assert "reservation" in str(exc)
    else:
        raise AssertionError("changed reservation was accepted")


def test_recovery_preserves_unknown_intent_and_never_resends(tmp_path):
    rows = build_requests([article("a1"), article("a2")], batch_size=1)
    request_by_id = {row["batch_id"]: row for row in rows}
    intent = {"batch_id": 1, "request_usd_reservation": rows[0]["request_usd_reservation"]}
    (tmp_path / "intents.jsonl").write_text(json.dumps(intent) + "\n")
    (tmp_path / "calls.jsonl").write_text("")
    recovered = recover_ledger(tmp_path, request_by_id)
    assert recovered["attempted"] == {1}
    assert recovered["valid"] == {}
    assert recovered["spent_or_reserved_upper_usd"] == rows[0]["request_usd_reservation"]


def test_recovery_uses_actual_cost_and_restores_valid_label_batch(tmp_path):
    row = build_requests([article()])[0]
    raw = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content":
        '{"labels":[{"article_id":"a1","tone":"neutral","persistence":"undetermined"}]}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()
    response_path = tmp_path / "response_001.json"
    response_path.write_bytes(raw)
    (tmp_path / "intents.jsonl").write_text(json.dumps({"batch_id": 1}) + "\n")
    call = {"batch_id": 1, "response_sha256": hashlib.sha256(raw).hexdigest(),
            "token_cost_estimate_peak_uncached_usd": 0.000009, "validation": "pass"}
    (tmp_path / "calls.jsonl").write_text(json.dumps(call) + "\n")
    (tmp_path / "labels_001.json").write_text(json.dumps([
        {"article_id": "a1", "tone": "neutral", "persistence": "undetermined"}
    ]))
    recovered = recover_ledger(tmp_path, {1: row})
    assert recovered["attempted"] == {1}
    assert recovered["valid"][1][0]["tone"] == "neutral"
    assert recovered["spent_or_reserved_upper_usd"] == 0.000009


def test_deepseek_key_uses_environment_then_existing_dotenv(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("DEEPSEEK_API_KEY=from-file\n")
    assert resolve_deepseek_key({"DEEPSEEK_API_KEY": "from-env"}, dotenv) == "from-env"
    assert resolve_deepseek_key({}, dotenv) == "from-file"
    assert resolve_deepseek_key({}, tmp_path / "missing") is None


def test_deepseek_key_accepts_only_registered_sv_host(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("SV_LLM_API_KEY=sv-key\nSV_LLM_BASE_URL=https://api.deepseek.com/v1\n")
    assert resolve_deepseek_key({}, dotenv) == "sv-key"
    assert resolve_deepseek_key({"SV_LLM_API_KEY": "sv-env", "SV_LLM_BASE_URL": "https://api.deepseek.com"}, dotenv) == "sv-env"
    assert resolve_deepseek_key({"SV_LLM_API_KEY": "wrong-host", "SV_LLM_BASE_URL": "https://example.com"}, dotenv) is None
    empty = tmp_path / "empty"
    empty.write_text("SV_LLM_API_KEY=wrong-host\nSV_LLM_BASE_URL=https://example.com\n")
    assert resolve_deepseek_key({}, empty) is None


def test_recovery_keeps_failed_response_attempted_without_reparsing_or_retry(tmp_path):
    row = build_requests([article()])[0]
    raw = b'{"choices": []}'
    (tmp_path / "response_001.json").write_bytes(raw)
    (tmp_path / "intents.jsonl").write_text(json.dumps({"batch_id": 1}) + "\n")
    call = {"batch_id": 1, "response_sha256": hashlib.sha256(raw).hexdigest(), "error_type": "ValueError"}
    (tmp_path / "calls.jsonl").write_text(json.dumps(call) + "\n")
    recovered = recover_ledger(tmp_path, {1: row})
    assert recovered["attempted"] == {1}
    assert recovered["valid"] == {}
    assert recovered["spent_or_reserved_upper_usd"] == row["request_usd_reservation"]


def test_recovery_revalidates_deterministic_format_repairs_without_new_call(tmp_path):
    row = build_requests([article()], label_mode="slim4_mechanism6")[0]
    content = json.dumps({"a1": {"article_id": "a1", "decision": "keep", "topics": ["living_prices"],
        "scope": "us_national", "tone": "alarming", "persistence": "uncertain"}})
    raw = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": content}}]}).encode()
    (tmp_path / "response_001.json").write_bytes(raw)
    (tmp_path / "intents.jsonl").write_text(json.dumps({"batch_id": 1}) + "\n")
    call = {"batch_id": 1, "response_sha256": hashlib.sha256(raw).hexdigest(), "error_type": "ValueError"}
    (tmp_path / "calls.jsonl").write_text(json.dumps(call) + "\n")
    recovered = recover_ledger(tmp_path, {1: row}, "slim4_mechanism6")
    assert recovered["attempted"] == {1}
    assert recovered["valid"][1][0]["tone"] == "alarming"
