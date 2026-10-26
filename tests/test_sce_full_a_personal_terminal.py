"""Offline fault/resume/repair checks for the full-A local Terminal runner."""
import hashlib
import json
import math
from pathlib import Path
import sys
from threading import Lock

import pytest

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = ROOT.parent / "socioverse2_repo"
if str(OFFICIAL) not in sys.path:
    sys.path.append(str(OFFICIAL))
import studies
studies.__path__ = [str(ROOT / "studies"), *studies.__path__]

from studies.sce_inflation_expectations.experiments import frozen_message_queue as queue
from studies.sce_inflation_expectations.experiments import full_a_personal_terminal as terminal
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash


RAW = json.dumps({"point_pct": 3.5, "q9": {f"bin{i}": 10 for i in range(1, 11)}})
Q8_ONLY = json.dumps({"point_pct": 4.25, "q9": {"bin1": 100}})


class APIConnectionError(Exception):
    pass


class UpstreamError(Exception):
    status_code = 502


class UnauthorizedError(Exception):
    status_code = 401


class RetryAfterResponse:
    headers = {"Retry-After": "17"}


class RetryAfterUpstreamError(Exception):
    status_code = 503
    response = RetryAfterResponse()


def _messages(value):
    return [{"role": "user", "content": f"frozen terminal prompt {value}"}]


def _slots(n=40):
    slots = []
    messages = {}
    for i in range(n):
        month = 201901 + (i // 10)
        aid = f"aid-{i:03d}"
        prompt = _messages(i)
        digest = message_hash(prompt)
        key = f"{month}|T0|1|{aid}"
        messages[key] = prompt
        slots.append({"key": key, "month": month, "arm": "T0", "repeat": 1,
            "agent_id": aid, "prompt_sha256": digest, "reserved_usd": 0.01,
            "prompt_bytes": 100, "prompt_chars": len(prompt[0]["content"])})
    return slots, messages


def _protocol(n=40, cap=10.0):
    return {"planned_calls": n, "budget_cap_usd": cap,
        "input_package_path": "/unused/fake-inputs", "model": "test-model",
        "expected_provider": "test-provider", "max_tokens": 1024,
        "technical_gate": {"initial_attempts": 32, "minimum_normal_returns": 16,
                           "minimum_format_ratio": 0.95, "maximum_probe_attempts": 32}}


def _policy():
    policy = terminal._policy()
    policy.update(initial_workers=4, max_workers=8, min_workers=1,
        scale_up_after_completed=4, batch_slots=16, cooldown_seconds=[0],
        max_total_cooldown_seconds=10, max_unhealthy_recoveries=5,
        no_progress_recovery_limit=3, healthy_segment_min_successes=8,
        healthy_segment_min_ratio=.95)
    return policy


def _sender_result(raw=RAW):
    return {"returned_model": "test-model", "returned_provider": "test-provider",
        "raw_response_text": raw, "finish_reason": "stop",
        "api_reported_cost_usd": 0.0001}


def _install_materializer(monkeypatch, messages):
    def materialize(_input, metadata):
        return [{**{k: row[k] for k in ("key", "month", "arm", "repeat", "agent_id",
                                        "prompt_sha256", "reserved_usd")},
                 "messages": messages[row["key"]]} for row in metadata]
    monkeypatch.setattr(terminal, "_materialize", materialize)


def test_main_transport_failure_is_recorded_once_then_repair_runs_once(monkeypatch, tmp_path):
    slots, messages = _slots()
    _install_materializer(monkeypatch, messages)
    p, policy = _protocol(), _policy()
    failed_key = slots[35]["key"]
    lock = Lock()
    sent = []
    cooled = []
    failed = False

    def sender(prompt):
        nonlocal failed
        with lock:
            sent.append(message_hash(prompt))
            if message_hash(prompt) == message_hash(messages[failed_key]) and not failed:
                failed = True
                raise APIConnectionError("offline synthetic transport loss")
        return _sender_result()

    main = terminal.run_main_segments(p, slots, tmp_path, sender, policy,
                                      cool=lambda *args: cooled.append(args))
    main_i, main_r = queue.archive(tmp_path / "main")
    assert main["status"] == "completed"
    assert main["actual_model_results"] is False
    assert len(main_i) == len(main_r) == len(slots)
    assert cooled == []
    assert len(sent) == len(set(sent))
    assert sum(row["key"] == failed_key for row in main_r) == 1
    assert next(row for row in main_r if row["key"] == failed_key)["error"] == "APIConnectionError"

    repair, repair_i, repair_r, targets = terminal.run_repair_segments(
        p, slots, tmp_path, main_i, main_r, sender, policy, cool=lambda *_args: None)
    assert repair["status"] == "completed"
    assert repair["actual_model_results"] is False
    assert set(targets) == {failed_key}
    assert len(repair_i) == len(repair_r) == 1
    assert repair_i[0]["key"] == "repair1|" + failed_key
    assert sent.count(message_hash(messages[failed_key])) == 2


def test_unknown_main_intent_is_reserved_and_never_resent_on_resume(monkeypatch, tmp_path):
    slots, messages = _slots()
    _install_materializer(monkeypatch, messages)
    main_root = tmp_path / "main" / "round_0001" / "segment_0001"
    main_root.mkdir(parents=True)
    key = slots[0]["key"]
    (main_root / "dispatch_private.jsonl").write_text(json.dumps({
        "key": key, "prompt_sha256": slots[0]["prompt_sha256"],
        "reserved_usd": slots[0]["reserved_usd"], "at_utc": queue.now()}) + "\n")
    (main_root / "calls_private.jsonl").write_text("")
    p, policy = _protocol(), _policy()
    sent = []

    def sender(prompt):
        sent.append(message_hash(prompt))
        return _sender_result()

    result = terminal.run_main_segments(p, slots, tmp_path, sender, policy,
                                       cool=lambda *_args: None)
    intents, replies = queue.archive(tmp_path / "main")
    assert result["status"] == "stopped_unresolved_unknown_intents"
    assert len(intents) == len(slots)
    assert len(replies) == len(slots) - 1
    assert messages[key] not in sent
    assert message_hash(messages[key]) not in sent
    assert queue.account(intents, replies)["unknown_fee_reservation_usd"] == pytest.approx(slots[0]["reserved_usd"])


def test_partial_repair_overlay_preserves_successful_main_q8(monkeypatch, tmp_path):
    slots, messages = _slots()
    _install_materializer(monkeypatch, messages)
    p, policy = _protocol(), _policy()
    partial_key = slots[34]["key"]
    partial_sent = 0

    def sender(prompt):
        nonlocal partial_sent
        if prompt == messages[partial_key]:
            partial_sent += 1
            return _sender_result(Q8_ONLY if partial_sent == 1 else RAW)
        return _sender_result()

    main = terminal.run_main_segments(p, slots, tmp_path, sender, policy,
                                      cool=lambda *_args: None)
    main_i, main_r = queue.archive(tmp_path / "main")
    assert main["status"] == "completed"
    assert queue.fields(next(row for row in main_r if row["key"] == partial_key)) == {"q8": True, "q9": False}
    repair, repair_i, repair_r, targets = terminal.run_repair_segments(
        p, slots, tmp_path, main_i, main_r, sender, policy, cool=lambda *_args: None)
    assert repair["status"] == "completed"
    assert targets[partial_key]["fields"] == ["q9"]
    (tmp_path / "protocol.json").write_text(json.dumps({"test": True}))
    (tmp_path / "config.json").write_text(json.dumps({"input_manifest_sha256": "b" * 64}))
    view = terminal.write_logical_overlay(tmp_path, p, slots, main_i, main_r,
        repair_i, repair_r, main, repair)
    assert view["generation_completed"] is True
    rows = [json.loads(line) for line in (Path(view["path"]) / "logical_actions_private.jsonl").read_text().splitlines()]
    row = next(item for item in rows if item["key"] == partial_key)
    assert row["effective_q8"] == 4.25
    assert row["field_source"] == {"q8": "main", "q9": "repair"}
    assert row["field_updated"] == {"q8": True, "q9": True}
    assert sum(row["effective_q9_bins"]) == pytest.approx(100.0)
    assert row["main"]["raw_response_sha256"] != row["repair"]["raw_response_sha256"]


def test_interrupted_repair_resumes_only_never_dispatched_target(monkeypatch, tmp_path):
    slots, messages = _slots()
    _install_materializer(monkeypatch, messages)
    p, policy = _protocol(), _policy()
    failed_keys = {slots[34]["key"], slots[36]["key"]}
    failed_once = set()

    def main_sender(prompt):
        key = next(key for key, value in messages.items() if value == prompt)
        if key in failed_keys and key not in failed_once:
            failed_once.add(key)
            raise APIConnectionError("synthetic main transport error")
        return _sender_result()

    main = terminal.run_main_segments(p, slots, tmp_path, main_sender, policy,
                                      cool=lambda *_args: None)
    main_i, main_r = queue.archive(tmp_path / "main")
    assert main["status"] == "completed"

    first, second = sorted(failed_keys)
    repair_segment = tmp_path / "repair" / "round_0001" / "segment_0001"
    repair_segment.mkdir(parents=True)
    repair_key = "repair1|" + first
    (repair_segment / "dispatch_private.jsonl").write_text(json.dumps({
        "key": repair_key, "prompt_sha256": next(s["prompt_sha256"] for s in slots if s["key"] == first),
        "reserved_usd": next(s["reserved_usd"] for s in slots if s["key"] == first),
        "at_utc": queue.now()}) + "\n")
    (repair_segment / "calls_private.jsonl").write_text("")

    repaired = []

    def repair_sender(prompt):
        repaired.append(message_hash(prompt))
        return _sender_result()

    result, intents, replies, targets = terminal.run_repair_segments(
        p, slots, tmp_path, main_i, main_r, repair_sender, policy, cool=lambda *_args: None)
    assert result["status"] == "stopped_unresolved_unknown_intents"
    assert set(targets) == failed_keys
    assert len(intents) == 2 and len(replies) == 1
    assert repaired == [message_hash(messages[second])]

    # A second resume is safe and makes no more requests: the unknown intent
    # remains reserved and the other target already has its single reply.
    again, again_i, again_r, _ = terminal.run_repair_segments(
        p, slots, tmp_path, main_i, main_r, repair_sender, policy, cool=lambda *_args: None)
    assert again["status"] == "stopped_unresolved_unknown_intents"
    assert len(again_i) == 2 and len(again_r) == 1
    assert repaired == [message_hash(messages[second])]


def test_shared_budget_cap_includes_unknown_main_reservations_and_stops_repairs(monkeypatch, tmp_path):
    slots, messages = _slots()
    _install_materializer(monkeypatch, messages)
    # 32 known successes cost $0.0032; eight transport failures reserve $0.08.
    # The remaining $0.0003 is too small for even one $0.01 repair reservation.
    p, policy = _protocol(cap=0.0835), _policy()
    fail_keys = {row["key"] for row in slots[32:]}

    def sender(prompt):
        key = next(key for key, value in messages.items() if value == prompt)
        if key in fail_keys:
            raise APIConnectionError("synthetic transport loss")
        return _sender_result()

    main = terminal.run_main_segments(p, slots, tmp_path, sender, policy,
                                      cool=lambda *_args: None)
    main_i, main_r = queue.archive(tmp_path / "main")
    main_account = queue.account(main_i, main_r)
    assert main["status"] == "completed"
    assert main_account["spent_or_reserved_usd"] == pytest.approx(0.0832)
    repair, repair_i, repair_r, targets = terminal.run_repair_segments(
        p, slots, tmp_path, main_i, main_r, sender, policy, cool=lambda *_args: None)
    assert repair["status"] == "stopped_budget_guard"
    assert len(targets) == 8
    assert repair_i == repair_r == []
    assert main_account["spent_or_reserved_usd"] <= p["budget_cap_usd"]


def test_isolated_recoveries_can_exceed_old_lifetime_15_limit_but_cooldown_is_bounded(tmp_path):
    policy = _policy()
    policy.update(cooldown_seconds=[0], max_total_cooldown_seconds=2)
    transport = {"error": "APIConnectionError", "fatal": True}
    receipt = {"halt_reason": "APIConnectionError"}
    sender = type("Sender", (), {"retry_after_s": 0.0})()
    mostly_healthy = [{"error": None} for _ in range(19)] + [transport]
    for _ in range(20):
        okay, reason = terminal._recover_after_segment(
            tmp_path, sender, mostly_healthy, receipt, policy,
            stage="main", cool=lambda *_args: None)
        assert okay and reason is None
    state = json.loads((tmp_path / "recovery_limits.json").read_text())
    assert state["recovery_cycles"] == 20

    policy["cooldown_seconds"] = [1]
    policy["max_total_cooldown_seconds"] = 2
    policy["healthy_segment_min_successes"] = 0
    policy["healthy_segment_min_ratio"] = .95
    for expected_total in (1, 2):
        okay, reason = terminal._recover_after_segment(
            tmp_path, sender, mostly_healthy, receipt, policy,
            stage="main", cool=lambda *_args: None)
        assert okay and reason is None
        state = json.loads((tmp_path / "recovery_limits.json").read_text())
        assert state["total_cooldown_seconds"] == expected_total
    okay, reason = terminal._recover_after_segment(
        tmp_path, sender, mostly_healthy, receipt, policy,
        stage="main", cool=lambda *_args: None)
    assert not okay and reason == "total_cooldown_cap_reached"


def test_tolerant_segment_continues_after_isolated_502_without_cooldown(tmp_path):
    slots, messages = _slots(4)
    ready = [{**slot, "messages": messages[slot["key"]]} for slot in slots]
    p = _protocol(4)
    p["expected_provider"] = "test-provider"
    policy = _policy()

    def sender(prompt):
        if prompt == messages[slots[1]["key"]]:
            raise UpstreamError("synthetic 502")
        return _sender_result()

    result, intents, replies = terminal._execute_tolerant_segment(
        p, ready, tmp_path / "segment", sender, workers=2, max_workers=2,
        scale_after=8, policy=policy)
    assert result["status"] == "completed"
    assert result["actual_model_results"] is False
    assert result["halt_reason"] is None
    assert len(intents) == len(replies) == 4
    assert next(row for row in replies if row["key"] == slots[1]["key"])["error_http_status"] == 502


def test_tolerant_segment_stops_after_three_consecutive_transport_errors(tmp_path):
    slots, messages = _slots(8)
    ready = [{**slot, "messages": messages[slot["key"]]} for slot in slots]
    p = _protocol(8)
    p["expected_provider"] = "test-provider"
    policy = _policy()

    def sender(_prompt):
        raise APIConnectionError("synthetic consecutive transport errors")

    result, intents, replies = terminal._execute_tolerant_segment(
        p, ready, tmp_path / "segment", sender, workers=1, max_workers=1,
        scale_after=8, policy=policy)
    assert result["halt_reason"] == "consecutive_transport_failure_limit"
    assert len(intents) == len(replies) == 3


def test_tolerant_segment_stops_when_rolling_32_has_at_least_eight_errors(tmp_path):
    slots, messages = _slots(32)
    ready = [{**slot, "messages": messages[slot["key"]]} for slot in slots]
    p = _protocol(32)
    p["expected_provider"] = "test-provider"
    policy = _policy()
    error_hashes = {message_hash(messages[slots[i]["key"]]) for i in range(0, 32, 4)}

    def sender(prompt):
        if message_hash(prompt) in error_hashes:
            raise APIConnectionError("synthetic spaced transport errors")
        return _sender_result()

    result, intents, replies = terminal._execute_tolerant_segment(
        p, ready, tmp_path / "segment", sender, workers=1, max_workers=1,
        scale_after=32, policy=policy)
    assert result["halt_reason"] == "rolling_32_transport_failure_limit"
    assert len(intents) == len(replies) == 32
    assert sum(bool(row["error"]) for row in replies) == 8


def test_tolerant_segment_stops_immediately_on_401_and_reserves_unknown_fee(tmp_path):
    slots, messages = _slots(4)
    ready = [{**slot, "messages": messages[slot["key"]]} for slot in slots]
    p = _protocol(4)
    p["expected_provider"] = "test-provider"
    policy = _policy()

    def sender(_prompt):
        raise UnauthorizedError("synthetic authorization error")

    p["budget_cap_usd"] = slots[0]["reserved_usd"]
    result, intents, replies = terminal._execute_tolerant_segment(
        p, ready, tmp_path / "segment", sender, workers=1, max_workers=1,
        scale_after=4, policy=policy)
    account = queue.account(intents, replies)
    assert result["halt_reason"] == "hard_provider_or_account_error"
    assert len(intents) == len(replies) == 1
    assert replies[0]["error_http_status"] == 401
    assert account["unknown_fee_reservation_usd"] == pytest.approx(slots[0]["reserved_usd"])


def test_sender_metadata_cannot_promote_engineering_fixture_to_actual_results(tmp_path):
    slots, messages = _slots(1)
    ready = [{**slots[0], "messages": messages[slots[0]["key"]]}]
    p = _protocol(1)
    p["expected_provider"] = "test-provider"

    def fake_sender(_prompt):
        return {**_sender_result(), "actual_model_results": True}

    result, _intents, replies = terminal._execute_tolerant_segment(
        p, ready, tmp_path / "segment", fake_sender, workers=1, max_workers=1,
        scale_after=1, policy=_policy())
    assert result["actual_model_results"] is False
    assert replies[0]["actual_model_results"] is False


@pytest.mark.parametrize(("error", "expected_reason"), [
    (type("RateLimitError", (Exception,), {"status_code": 429}), "http_429_cooldown"),
    (RetryAfterUpstreamError, "retry_after_cooldown"),
])
def test_tolerant_segment_stops_for_429_or_explicit_retry_after(tmp_path, error, expected_reason):
    slots, messages = _slots(4)
    ready = [{**slot, "messages": messages[slot["key"]]} for slot in slots]
    p = _protocol(4)
    p["expected_provider"] = "test-provider"
    policy = _policy()

    def sender(_prompt):
        raise error("synthetic throttling response")

    wrapped = terminal.queue.safe_sender(sender)
    result, intents, replies = terminal._execute_tolerant_segment(
        p, ready, tmp_path / expected_reason, wrapped, workers=1, max_workers=1,
        scale_after=4, policy=policy)
    assert result["halt_reason"] == expected_reason
    assert len(intents) == len(replies) == 1
    if error is RetryAfterUpstreamError:
        assert wrapped.retry_after_s == 17


def test_prepare_input_validation_is_offline_and_requires_manifest_ready(monkeypatch, tmp_path):
    month = 201901
    monkeypatch.setattr(terminal, "MONTHS", (month,))
    monkeypatch.setattr(terminal, "EXPECTED_PERSON_MONTHS", 1)
    monkeypatch.setattr(terminal, "RAW_PER_MONTH", 512)
    monkeypatch.setattr(terminal, "EXPECTED_EXCLUSIONS", 511)
    monkeypatch.setattr(terminal, "_safe_output_path", lambda path: Path(path).resolve())
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(terminal, "live_sender", lambda *_args: pytest.fail("prepare accessed live sender"))
    month_dir = tmp_path / str(month)
    month_dir.mkdir()
    prompts = {"month": month, "rows": {"aid": {"messages": _messages("offline"),
        "prompt_sha256": message_hash(_messages("offline"))}}}
    (month_dir / "prompts.json").write_text(json.dumps(prompts))
    for name in ("contexts_private.json", "weights_private.json"):
        (month_dir / name).write_text(json.dumps({"aid": {"private": True}}))
    roster = {"aid": {"agent_id": "aid", "eligible": True}}
    roster.update({f"excluded-{i}": {"agent_id": f"excluded-{i}", "eligible": False}
                   for i in range(511)})
    (month_dir / "roster_private.json").write_text(json.dumps({"month": month, "frame_n": 512,
        "eligible_n": 1, "excluded_n": 511, "rows": roster}))
    serialized = json.dumps(prompts["rows"]["aid"]["messages"], ensure_ascii=False)
    estimated_tokens = math.ceil(len(serialized) / 4)
    input_cost = estimated_tokens * terminal.PRICE_INPUT_PER_MTOK / 1e6
    output_cost = 300 * terminal.PRICE_OUTPUT_PER_MTOK / 1e6
    (tmp_path / "summary.json").write_text(json.dumps({"status": "ready", "months": [month],
        "rows_by_month": {str(month): 1}, "eligible_total": 1,
        "estimated_input_tokens_char_div_4": estimated_tokens,
        "estimated_output_tokens_assumed_per_prompt": 300,
        "estimated_input_cost_usd": input_cost, "estimated_output_cost_usd": output_cost,
        "estimated_total_cost_usd": input_cost + output_cost,
        "prompt_characters_max": len(prompts["rows"]["aid"]["messages"][0]["content"]),
        "prompt_utf8_bytes_max": len(prompts["rows"]["aid"]["messages"][0]["content"].encode())}))
    (tmp_path / "exclusions.json").write_text(json.dumps({"rows": [{"aid": str(i)}
        for i in range(terminal.EXPECTED_EXCLUSIONS)]}))
    files = ["summary.json", "exclusions.json", *(f"{month}/{name}" for name in terminal.INPUT_FILES)]
    (tmp_path / "manifest.json").write_text(json.dumps({"files_sha256": {
        **{name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() for name in files},
        "base_label_overlay.json": "a" * 64}}))
    result = terminal._validate_input(tmp_path)
    assert len(result[5]) == 1
    assert result[4]["status"] == "ready"

    summary = json.loads((tmp_path / "summary.json").read_text())
    summary["status"] = "draft"
    (tmp_path / "summary.json").write_text(json.dumps(summary))
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["files_sha256"]["summary.json"] = hashlib.sha256((tmp_path / "summary.json").read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="not marked ready"):
        terminal._validate_input(tmp_path)


@pytest.fixture(scope="module")
def real_historical_import_context():
    inputs = ROOT / "outputs/sce_full_a_personal_inputs_20261025_v1"
    validated = terminal._validate_input(inputs)
    plan, source_hashes = terminal._build_historical_import_plan(validated[0], validated[5])
    return validated[5], plan, source_hashes


def test_historical_import_plan_pins_only_full_successes_and_protects_gate(real_historical_import_context):
    slots, plan, hashes = real_historical_import_context
    assert len(slots) == 41970
    assert plan["candidate_count"] == 189
    assert plan["eligible_import_count"] == 182
    assert plan["ineligible_candidate_count"] == 7
    assert plan["ineligible_reason_counts"] == {"no_direct_v4_raw_reply": 7}
    assert plan["first_64_imports"] == 0
    assert {row["source_stage"] for row in plan["rows"]} == {"main", "repair"}
    assert sum(row["source_stage"] == "main" for row in plan["rows"]) == 179
    assert sum(row["source_stage"] == "repair" for row in plan["rows"]) == 3
    assert all(row["source_reply_path"] in hashes for row in plan["rows"])
    assert all(row["source_raw_response_sha256"] for row in plan["rows"])
    assert sum(row["source_api_reported_cost_usd"] or 0 for row in plan["rows"]) == pytest.approx(.122813158)


def test_gate_then_historical_import_is_resumable_and_cost_separate(real_historical_import_context,
                                                                     monkeypatch, tmp_path):
    _real_slots, plan, _source_hashes = real_historical_import_context
    live_slots, messages = _slots(64)
    imported_slots = []
    for item in plan["rows"]:
        month, _arm, _repeat, aid = item["key"].split("|", 3)
        imported_slots.append({"key": item["key"], "month": int(month), "arm": "T0", "repeat": 1,
            "agent_id": aid, "prompt_sha256": item["prompt_sha256"], "reserved_usd": .01,
            "prompt_bytes": 100, "prompt_chars": 100})
    slots = [*live_slots, *imported_slots]
    _install_materializer(monkeypatch, messages)
    fake_send = lambda _messages: pytest.fail("the isolated segment writer must not call a sender")

    def offline_segment(protocol, selected, out, _send, **_kwargs):
        out = Path(out)
        out.mkdir(parents=True, exist_ok=False)
        intents, replies = [], []
        for slot in selected:
            intent = {"key": slot["key"], "prompt_sha256": slot["prompt_sha256"],
                "reserved_usd": slot["reserved_usd"], "at_utc": queue.now()}
            row = {key: slot[key] for key in ("key", "month", "arm", "repeat", "agent_id", "prompt_sha256")}
            row.update(error=None, fatal=False, raw_response_text=RAW, finish_reason="stop",
                api_reported_cost_usd=.0001, request_reservation_usd=slot["reserved_usd"],
                actual_model_results=False, returned_model=protocol["model"],
                returned_provider=protocol["expected_provider"],
                raw_response_sha256=hashlib.sha256(RAW.encode()).hexdigest())
            intents.append(intent); replies.append(row)
        for name, rows in (("dispatch_private.jsonl", intents), ("calls_private.jsonl", replies)):
            (out / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
        terminal.dump(out / "receipt.json", {"status": "completed", "actual_model_results": False})
        terminal.dump(out / "manifest.json", {"files_sha256": {
            name: queue.sha(out / name) for name in ("dispatch_private.jsonl", "calls_private.jsonl", "receipt.json")}})
        return {"halt_reason": None}, intents, replies

    monkeypatch.setattr(terminal, "_execute_tolerant_segment", offline_segment)
    protocol, policy = _protocol(len(slots)), _policy()
    protocol.update(model="deepseek/deepseek-v3.2", expected_provider="SiliconFlow")
    main = terminal.run_main_segments(protocol, slots, tmp_path / "run", fake_send, policy,
        engineering_only=False, historical_import_plan=plan, cool=lambda *_args: None)
    resumed = terminal.run_main_segments(protocol, slots, tmp_path / "run", fake_send, policy,
        engineering_only=False, historical_import_plan=plan, cool=lambda *_args: None)
    intents, replies = queue.archive(tmp_path / "run" / "main")
    imported = [row for row in replies if row.get("execution_kind") == "historical_import"]
    assert main["status"] == "completed"
    assert main["technical_gate"]["initial_attempts"] == 32
    assert main["actual_model_results"] is False
    assert main["new_api_calls"] == 64
    assert main["historical_import_rows"] == 182
    assert resumed["status"] == "completed"
    assert resumed["new_api_calls"] == 64
    assert resumed["historical_import_rows"] == 182
    assert len(intents) == len(replies) == len(slots)
    assert len(imported) == 182
    assert all(row["api_reported_cost_usd"] == 0 and row["actual_model_results"] is True for row in imported)
    assert sum(row["historical_source"]["api_reported_cost_usd"] for row in imported) == pytest.approx(.122813158)
    segment_kinds = [json.loads((p / "manifest.json").read_text()).get("segment_kind")
                     for p in sorted((tmp_path / "run" / "main").glob("round_*/segment_*"))]
    assert segment_kinds[0] is None
    assert segment_kinds[1] == "historical_import"
    assert all(kind is None for kind in segment_kinds[2:])


def test_engineering_only_completion_never_enters_research_evaluation():
    assert not terminal._evaluation_allowed({"generation_completed": True,
                                             "actual_model_results": False})
    assert not terminal._evaluation_allowed({"generation_completed": False,
                                             "actual_model_results": True})
    assert terminal._evaluation_allowed({"generation_completed": True,
                                         "actual_model_results": True})


def test_engineering_replay_marker_blocks_live_run_before_credential_lookup(tmp_path, monkeypatch):
    (tmp_path / "engineering_only_replay.json").write_text("{}")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="permanently excluded from live"):
        terminal.run(tmp_path, confirm=True)
