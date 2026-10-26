import hashlib
import json
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
from studies.sce_inflation_expectations.experiments import media_timing_terminal as terminal
from studies.sce_inflation_expectations.experiments.monthly_main_resilient import POLICY
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
from studies.sce_inflation_expectations.evaluation import media_timing as evaluation


RAW = json.dumps({"point_pct": 3.5, "q9": {f"bin{i}": 10 for i in range(1, 11)}})


def _messages(value):
    return [{"role": "user", "content": f"Offline frozen prompt {value}"}]


def _reply(raw=RAW, **overrides):
    row = {"returned_model": "test-model", "returned_provider": "test-provider",
           "raw_response_text": raw, "finish_reason": "stop", "api_reported_cost_usd": 0.001,
           "error": None, "raw_response_sha256": hashlib.sha256(raw.encode()).hexdigest()}
    return dict(row, **overrides)


def _mini_scope(monkeypatch):
    month, aid, repeat = 201905, "a", 1
    monkeypatch.setattr(terminal, "MONTHS", (month,))
    monkeypatch.setattr(terminal, "N_BY_MONTH", {month: 1})
    monkeypatch.setattr(terminal, "REPEATS", (repeat,))
    p = {"planned_calls": 2, "price_input_per_mtok": 0.259, "price_output_per_mtok": 0.8,
         "max_tokens": 1024, "max_prompt_chars": 200}
    prompts = {month: {}}
    prompt_rows = {}
    for arm, value in (("C0", "old-failure"), ("C1", "new-one"),
                       ("T0", "new-two"), ("T1", "new-two")):
        messages = _messages(value)
        digest = message_hash(messages)
        prompts[month][arm, aid] = (messages, digest)
        prompt_rows[arm] = {"messages": messages, "prompt_sha256": digest}
    old_q3 = _messages("old-q3")
    q3_hash = message_hash(old_q3)
    old_q0 = prompts[month]["C0", aid][0]
    old_q0_hash = message_hash(old_q0)
    old_slots = [
        {"key": f"{month}|Q3|{repeat}|{aid}", "month": month, "arm": "Q3", "repeat": repeat,
         "agent_id": aid, "prompt_sha256": q3_hash, "reserved_usd": 0.01},
        {"key": f"{month}|Q0|{repeat}|{aid}", "month": month, "arm": "Q0", "repeat": repeat,
         "agent_id": aid, "prompt_sha256": old_q0_hash, "reserved_usd": 0.01},
    ]
    q3_key, q0_key = old_slots[0]["key"], old_slots[1]["key"]
    old_intents = {slot["key"]: {"key": slot["key"], "prompt_sha256": slot["prompt_sha256"],
                                    "reserved_usd": slot["reserved_usd"]} for slot in old_slots}
    old_replies = {q3_key: _reply(), q0_key: _reply(error="APIConnectionError", finish_reason=None)}
    slots = []
    for arm in ("C1", "T0"):
        messages, digest = prompts[month][arm, aid]
        key = f"{month}|{arm}|{repeat}|{aid}"
        byte_count = len(json.dumps(messages, ensure_ascii=False).encode("utf-8"))
        slots.append({"key": key, "month": month, "arm": arm, "repeat": repeat,
                      "agent_id": aid, "prompt_sha256": digest, "messages": messages,
                      "reserved_usd": terminal.reserve(p, byte_count)})
    new_by_key = {slot["key"]: slot for slot in slots}
    positions = [
        {"month": month, "arm": "O0", "repeat": repeat, "agent_id": aid,
         "prompt_sha256": q3_hash, "status": "reuse_exact_success", "source_key": q3_key},
        {"month": month, "arm": "C0", "repeat": repeat, "agent_id": aid,
         "prompt_sha256": old_q0_hash, "status": "hold_old_attempted_failure", "source_key": q0_key},
        {"month": month, "arm": "C1", "repeat": repeat, "agent_id": aid,
         "prompt_sha256": prompts[month]["C1", aid][1], "status": "new_request",
         "new_request_key": f"{month}|C1|{repeat}|{aid}"},
        {"month": month, "arm": "T0", "repeat": repeat, "agent_id": aid,
         "prompt_sha256": prompts[month]["T0", aid][1], "status": "new_request",
         "new_request_key": f"{month}|T0|{repeat}|{aid}"},
        {"month": month, "arm": "T1", "repeat": repeat, "agent_id": aid,
         "prompt_sha256": prompts[month]["T1", aid][1], "status": "reuse_same_new_prompt",
         "new_request_key": f"{month}|T0|{repeat}|{aid}"},
    ]
    return p, prompts, prompt_rows, old_slots, old_intents, old_replies, slots, new_by_key, positions


def test_prompt_hash_change_and_duplicate_requests_are_rejected(monkeypatch):
    p, prompts, _rows, old_slots, _old_intents, _old_replies, slots, _by_key, _positions = _mini_scope(monkeypatch)
    changed = [dict(slot) for slot in slots]
    changed[0]["prompt_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="prompt hash mismatch"):
        terminal._validate_slots(changed, p, prompts, old_slots)

    duplicated = [dict(slot) for slot in slots]
    duplicated.append(dict(slots[0]))
    p["planned_calls"] = len(duplicated)
    with pytest.raises(ValueError, match="Duplicate same-repeat request|Duplicate new request key"):
        terminal._validate_slots(duplicated, p, prompts, old_slots)


def test_bad_logical_mapping_is_rejected(monkeypatch):
    p, prompts, _rows, old_slots, old_intents, old_replies, slots, by_key, positions = _mini_scope(monkeypatch)
    mapped = terminal._validate_positions(positions, p, prompts, by_key, old_slots, old_intents, old_replies)
    assert len(mapped) == 5
    broken = [dict(row) for row in positions]
    broken[2]["new_request_key"] = "201905|C1|1|other-agent"
    with pytest.raises(ValueError, match="exact frozen request|same month/repeat/respondent"):
        terminal._validate_positions(broken, p, prompts, by_key, old_slots, old_intents, old_replies)


def test_exact_old_answer_mapping_and_failed_old_attempt_stays_missing(monkeypatch):
    p, prompts, _rows, old_slots, old_intents, old_replies, slots, by_key, positions = _mini_scope(monkeypatch)
    terminal._validate_positions(positions, p, prompts, by_key, old_slots, old_intents, old_replies)
    success = evaluation._action_for_position(positions[0], old_replies, {})
    assert success["source_archive"] == "old_v3"
    assert success["source_key"] == positions[0]["source_key"]
    assert success["validation_status"] == "valid"

    failure = evaluation._action_for_position(positions[1], old_replies, {
        "201905|C1|1|a": _reply(),
    })
    assert failure["source_archive"] == "old_v3"
    assert failure["source_key"] == positions[1]["source_key"]
    assert failure["validation_status"] == "invalid"
    assert failure["mean"] is None


def test_queue_fake_reply_completes_offline_and_keeps_engineering_label(tmp_path):
    model, provider = "test-model", "test-provider"
    p = {"model": model, "expected_provider": provider, "budget_cap_usd": 1.0, "planned_calls": 40}
    slots = []
    for i in range(40):
        messages = _messages(i)
        slots.append({"key": f"201905|C0|1|{i}", "month": 201905, "arm": "C0", "repeat": 1,
            "agent_id": str(i), "messages": messages, "prompt_sha256": message_hash(messages), "reserved_usd": 0.01})
    policy = dict(POLICY, initial_workers=8, max_workers=16, min_workers=2,
        scale_up_after_completed=32, healthy_segment_min_successes=2)
    sent = []
    lock = Lock()
    raw = json.dumps({"point_pct": 3.0, "q9": {f"bin{i}": 10 for i in range(1, 11)}})

    def fake_send(messages):
        with lock:
            sent.append(message_hash(messages))
        return {"returned_model": model, "returned_provider": provider, "raw_response_text": raw,
                "finish_reason": "stop", "api_reported_cost_usd": 0.001}

    round_dir = tmp_path / "round_0001"
    round_dir.mkdir()
    receipt = queue.run_segments(p, slots, tmp_path, round_dir, fake_send, policy, engineering_only=True)
    intents, replies = queue.archive(tmp_path)
    with pytest.raises(ValueError, match="Engineering-only or unlabelled replies"):
        evaluation._validate_new_archive(tmp_path, {"slot_by_key": {slot["key"]: slot for slot in slots}}, p)
    assert receipt["status"] == "completed"
    assert len(sent) == len(set(sent)) == len(intents) == len(replies) == 40
    assert all(row["actual_model_results"] is False for row in replies)
    segment_receipts = [json.loads(path.read_text()) for path in round_dir.glob("segment_*/receipt.json")]
    assert segment_receipts and all(row["actual_model_results"] is False for row in segment_receipts)
    assert receipt["spent_or_reserved_usd"] <= p["budget_cap_usd"]
    assert (tmp_path / "technical_gate.json").exists()


def test_evaluator_rejects_unlabelled_failure_before_truth_access(monkeypatch, tmp_path):
    key = "201905|C0|1|a"
    intent = {"key": key, "prompt_sha256": "a" * 64, "reserved_usd": 0.01}
    failure = {"key": key, "prompt_sha256": "a" * 64, "actual_model_results": False,
               "error": "APIConnectionError", "finish_reason": None}
    monkeypatch.setattr(queue, "archive", lambda _folder: ([intent], [failure]))
    with pytest.raises(ValueError, match="Engineering-only or unlabelled replies"):
        evaluation._validate_new_archive(tmp_path, {"slot_by_key": {key: intent}},
                                         {"planned_calls": 1, "model": "test-model",
                                          "expected_provider": "test-provider"})


def test_q8_support_is_independent_from_q9_support():
    cases = []
    month = 201905
    all_arms = [*terminal.REFERENCE_ARMS, *terminal.ARMS]
    for aid in (1, 2):
        for repeat in (1, 2):
            real = {"q8_point": 3.0, "q9_mean": 3.0, "q9_iqr": 2.0,
                    "q9_zero_deflation": 0.0, "q9_bins": [10] * 10}
            arm_rows = {}
            for arm in all_arms:
                valid_q9 = not (aid == 2 and arm == "O0")
                arm_rows[arm] = {"point": 3.2, "mean": 3.2 if valid_q9 else None,
                    "iqr": 2.0 if valid_q9 else None,
                    "zero_deflation": 0.0 if valid_q9 else None,
                    "q9_bins": [10] * 10 if valid_q9 else [], "validation_status": "valid" if valid_q9 else "invalid"}
            arm_rows["copy_previous"] = {"point": 3.0, "mean": 3.0, "iqr": 2.0,
                "zero_deflation": 0.0, "q9_bins": [10] * 10, "validation_status": "valid"}
            cases.append({"month": month, "userid": aid, "repeat": repeat, "real": real,
                          "survey_weight": 1.0, "arms": arm_rows})
    supports = evaluation._build_supports(cases, [1, 2])
    assert supports["all_five_q9"] == {(month, 1)}
    assert supports["all_five_q8"] == {(month, 1), (month, 2)}
    assert supports["four_new_arms_q9"] == {(month, 1), (month, 2)}
    assert supports["pair_o0_c0_q9"] == {(month, 1)}
    assert supports["primary_c0_t0_q9"] == {(month, 1), (month, 2)}


def test_technical_gate_separates_transport_from_format_failures():
    network_mixed = [_reply() for _ in range(30)] + [
        _reply(error="APIConnectionError", finish_reason=None),
        _reply(error="APIConnectionError", finish_reason=None),
    ]
    passed = terminal.technical_gate_result(network_mixed)
    assert passed["attempted"] == 32
    assert passed["normal_returns"] == 30
    assert passed["format_ratio"] == 1.0
    assert passed["passed"] is True

    malformed = json.dumps({"point_pct": 3.0, "q9": {f"bin{i}": 10 for i in range(1, 10)}})
    format_mixed = [_reply() for _ in range(30)] + [_reply(raw=malformed), _reply(raw=malformed)]
    failed = terminal.technical_gate_result(format_mixed)
    assert failed["normal_returns"] == 32
    assert failed["format_ratio"] < 0.95
    assert failed["passed"] is False


def test_repair_targets_only_new_technical_failures_and_rejects_second_attempt():
    slots = [{"key": "201905|C1|1|a", "prompt_sha256": "a" * 64,
              "reserved_usd": 0.01, "month": 201905, "arm": "C1", "repeat": 1,
              "agent_id": "a", "messages": _messages("new")}]
    main = [{"key": slots[0]["key"], "prompt_sha256": "a" * 64, "actual_model_results": True,
             "error": "APIConnectionError", "finish_reason": None, "api_reported_cost_usd": None}]
    policy = dict(POLICY)
    targets = terminal._repair_targets(main, {slots[0]["key"]: slots[0]}, policy)
    assert set(targets) == {slots[0]["key"]}
    assert targets[slots[0]["key"]]["fields"] == ["q8", "q9"]
    # The held old Q0 failure in the 2×2 mapping is not part of the main-new slot index.
    assert "201905|Q0|1|a" not in targets

    duplicated_intents = [
        {"key": "repair1|" + slots[0]["key"], "prompt_sha256": "a" * 64, "reserved_usd": 0.01},
        {"key": "repair1|" + slots[0]["key"], "prompt_sha256": "a" * 64, "reserved_usd": 0.01},
    ]
    with pytest.raises(ValueError, match="duplicate|Duplicate"):
        terminal._validate_repair_ledger_shape(duplicated_intents, [],
            {slots[0]["key"]: slots[0]}, main,
            {"planned_calls": 1, "model": "test-model", "expected_provider": "test-provider"})


def test_partial_repair_overlay_preserves_successful_main_field():
    main_raw = json.dumps({"point_pct": 3.25, "q9": {"bin1": 10}})
    repair_raw = json.dumps({"point_pct": 9.75, "q9": {f"bin{i}": 10 for i in range(1, 11)}})
    main = _reply(raw=main_raw, prompt_sha256="a" * 64)
    repair = _reply(raw=repair_raw, prompt_sha256="a" * 64)
    main_action = evaluation.old_eval.model_action(main)
    fields = queue.fields(main)
    assert fields == {"q8": True, "q9": False}
    target = {"fields": ["q9"]}
    merged = evaluation._overlay_action(main_action, main, repair, target)
    assert merged["point"] == 3.25
    assert merged["field_sources"] == {"q8": "main", "q9": "repair"}
    assert merged["repair_accepted_fields"] == ["q9"]
    assert merged["validation_status"] == "valid"


def test_repair_budget_guard_includes_main_reservation(tmp_path):
    message = _messages("repair-budget")
    digest = message_hash(message)
    slot = {"key": "201905|C1|1|a", "prompt_sha256": digest,
            "reserved_usd": 0.01, "month": 201905, "arm": "C1", "repeat": 1,
            "agent_id": "a", "messages": message}
    main_intent = {"key": slot["key"], "prompt_sha256": digest, "reserved_usd": 0.01}
    main_reply = {"key": slot["key"], "prompt_sha256": digest, "actual_model_results": True,
                  "error": "APIConnectionError", "finish_reason": None, "api_reported_cost_usd": None}
    p = {"planned_calls": 1, "budget_cap_usd": 0.015, "model": "test-model",
         "expected_provider": "test-provider"}
    sent = []
    result, intents, replies, targets = terminal.run_repair_segments(
        p, [slot], tmp_path, [main_intent], [main_reply],
        lambda _messages: sent.append("sent"), dict(POLICY), cool=lambda *_a, **_kw: None)
    assert result["status"] == "stopped_budget_guard"
    assert not sent
    assert not intents and not replies
    assert len(targets) == 1


def test_repair_network_recovery_dispatches_only_unattempted_keys(tmp_path):
    slots, main_intents, main_replies = [], [], []
    for index in range(20):
        messages = _messages(index)
        digest = message_hash(messages)
        key = f"201905|C1|1|{index}"
        slots.append({"key": key, "month": 201905, "arm": "C1", "repeat": 1,
                      "agent_id": str(index), "prompt_sha256": digest, "messages": messages,
                      "reserved_usd": 0.01})
        main_intents.append({"key": key, "prompt_sha256": digest, "reserved_usd": 0.01})
        main_replies.append({"key": key, "prompt_sha256": digest, "actual_model_results": True,
                             "error": "APIConnectionError", "finish_reason": None,
                             "api_reported_cost_usd": None})
    p = {"planned_calls": len(slots), "budget_cap_usd": 1.0, "model": "test-model",
         "expected_provider": "test-provider"}
    digest_to_key = {slot["prompt_sha256"]: slot["key"] for slot in slots}
    sent, lock = [], Lock()
    failed_once = set()

    class APIConnectionError(Exception):
        pass

    def sender(messages):
        digest = message_hash(messages)
        with lock:
            sent.append(digest)
            if digest not in failed_once:
                failed_once.add(digest)
                if len(failed_once) == 1:
                    raise APIConnectionError("offline recoverable failure")
        return {"returned_model": "test-model", "returned_provider": "test-provider",
                "raw_response_text": RAW, "finish_reason": "stop", "api_reported_cost_usd": 0.001}

    result, intents, replies, targets = terminal.run_repair_segments(
        p, slots, tmp_path, main_intents, main_replies, sender,
        dict(POLICY, initial_workers=16, max_workers=32, max_total_recoveries=5),
        cool=lambda *_a, **_kw: None)
    assert result["status"] == "completed"
    assert len(targets) == len(intents) == len(replies) == len(slots)
    assert len(sent) == len(set(sent)) == len(slots)
    assert set(digest_to_key) == set(sent)
    assert all(row["key"].startswith("repair1|") for row in replies)


def test_well_spaced_network_errors_reset_unhealthy_streak_but_continuous_errors_stop(tmp_path):
    policy = dict(POLICY, healthy_segment_min_successes=100, healthy_segment_min_ratio=0.95,
                  max_total_recoveries=20, max_unhealthy_recoveries=2,
                  cooldown_seconds=[0], max_total_cooldown_seconds=20)
    class APIConnectionError(Exception):
        pass
    transport = {"error": "APIConnectionError", "fatal": True}
    receipt = {"halt_reason": "APIConnectionError"}
    healthy_segment = [_reply() for _ in range(130)] + [transport]
    for _ in range(5):
        ok, reason = terminal._cool_after_recoverable(
            tmp_path, type("Sender", (), {"retry_after_s": 0.0})(), healthy_segment,
            receipt, policy, cool=lambda *_a, **_kw: None, stage="main")
        assert ok and reason is None
    state = json.loads((tmp_path / "main_scheduler_status.json").read_text())
    assert state["recovery_cycles"] == 5
    assert state["unhealthy_recoveries"] == 1

    consecutive_dir = tmp_path / "consecutive"
    consecutive_dir.mkdir()
    all_bad = [transport]
    assert terminal._cool_after_recoverable(consecutive_dir,
        type("Sender", (), {"retry_after_s": 0.0})(), all_bad, receipt, policy,
        cool=lambda *_a, **_kw: None, stage="main")[0]
    assert terminal._cool_after_recoverable(consecutive_dir,
        type("Sender", (), {"retry_after_s": 0.0})(), all_bad, receipt, policy,
        cool=lambda *_a, **_kw: None, stage="main")[0]
    ok, reason = terminal._cool_after_recoverable(consecutive_dir,
        type("Sender", (), {"retry_after_s": 0.0})(), all_bad, receipt, policy,
        cool=lambda *_a, **_kw: None, stage="main")
    assert not ok and reason == "bounded_recovery_limit_reached"


def test_repair_archive_rejects_engineering_rows_including_error_responses(tmp_path, monkeypatch):
    message = _messages("engineering-repair")
    digest = message_hash(message)
    slot = {"key": "201905|C1|1|a", "month": 201905, "arm": "C1", "repeat": 1,
            "agent_id": "a", "prompt_sha256": digest, "messages": message, "reserved_usd": 0.01}
    main = [{"key": slot["key"], "prompt_sha256": digest, "actual_model_results": True,
             "error": "APIConnectionError", "finish_reason": None}]
    repair_key = "repair1|" + slot["key"]
    intent = {"key": repair_key, "prompt_sha256": digest, "reserved_usd": 0.01}
    reply = {"key": repair_key, "month": 201905, "arm": "C1", "repeat": 1, "agent_id": "a",
             "prompt_sha256": digest, "actual_model_results": False, "error": "APIConnectionError",
             "finish_reason": None}
    monkeypatch.setattr(queue, "archive", lambda _folder: ([intent], [reply]))
    (tmp_path / "repair").mkdir()
    ctx = {"slot_by_key": {slot["key"]: slot}, "slots": [slot]}
    with pytest.raises(ValueError, match="Engineering-only or unlabelled repair replies"):
        evaluation._validate_repair_archive(tmp_path, ctx,
            {"planned_calls": 1, "model": "test-model", "expected_provider": "test-provider"}, main)


def test_evaluator_uses_o0_exact_archive_and_writes_month_repeat_support(tmp_path, monkeypatch):
    month, aid = 201905, "a"
    p = {"months": [month], "generation_repeats": [1, 2], "arms": list(terminal.ARMS),
         "reference_arms": ["O0"], "model": "test-model", "expected_provider": "test-provider",
         "planned_calls": 4, "budget_cap_usd": 1.0}
    positions, new_slots, old_intents, old_replies, new_intents, new_replies = {}, [], {}, {}, [], {}
    for repeat in (1, 2):
        old_q3_key = f"{month}|Q3|{repeat}|{aid}"
        old_c0_key = f"{month}|Q0|{repeat}|{aid}"
        old_intents[old_q3_key] = {"key": old_q3_key, "prompt_sha256": "a" * 64, "reserved_usd": 0.01}
        old_intents[old_c0_key] = {"key": old_c0_key, "prompt_sha256": "b" * 64, "reserved_usd": 0.01}
        old_replies[old_q3_key] = _reply(key=old_q3_key, prompt_sha256="a" * 64)
        old_replies[old_c0_key] = _reply(key=old_c0_key, prompt_sha256="b" * 64)
        positions[month, "O0", repeat, aid] = {"month": month, "arm": "O0", "repeat": repeat,
            "agent_id": aid, "prompt_sha256": "a" * 64, "status": "reuse_exact_success", "source_key": old_q3_key}
        positions[month, "C0", repeat, aid] = {"month": month, "arm": "C0", "repeat": repeat,
            "agent_id": aid, "prompt_sha256": "b" * 64, "status": "reuse_exact_success", "source_key": old_c0_key}
        for arm in ("C1", "T0"):
            key = f"{month}|{arm}|{repeat}|{aid}"
            slot = {"key": key, "month": month, "arm": arm, "repeat": repeat, "agent_id": aid,
                    "prompt_sha256": ("c" if arm == "C1" else "d") * 64, "messages": _messages(key),
                    "reserved_usd": 0.01}
            new_slots.append(slot)
            new_intents.append({"key": key, "prompt_sha256": slot["prompt_sha256"], "reserved_usd": 0.01})
            new_replies[key] = _reply(key=key, prompt_sha256=slot["prompt_sha256"])
            positions[month, arm, repeat, aid] = {**slot, "status": "new_request", "new_request_key": key}
        positions[month, "T1", repeat, aid] = {"month": month, "arm": "T1", "repeat": repeat,
            "agent_id": aid, "prompt_sha256": "d" * 64, "status": "reuse_same_new_prompt",
            "new_request_key": f"{month}|T0|{repeat}|{aid}"}

    real = {"q8_point": 3.0, "q9_mean": 3.0, "q9_iqr": 2.0, "q9_zero_deflation": 0.0,
            "q9_bins": [10] * 10, "previous_q8_point": 2.5, "previous_q9_mean": 2.5,
            "previous_q9_bins": [10] * 10}
    link = {"month": month, "agent_id": aid, "userid": 1, "design_survey_weight": 1.0,
            "survey_weight": 1.0, "profile": {}, "stratum": "test"}
    ctx = {"protocol": p, "positions": positions, "slots": new_slots,
           "slot_by_key": {slot["key"]: slot for slot in new_slots}}
    monkeypatch.setattr(terminal, "checked", lambda _folder: (
        {"package": str(tmp_path / "package"), "protocol_sha256": "synthetic"}, p))
    monkeypatch.setattr(terminal, "_package_context", lambda *_a, **_kw: ctx)
    monkeypatch.setattr(evaluation, "_validate_old_archive", lambda *_a: (old_intents, old_replies))
    monkeypatch.setattr(evaluation, "_validate_new_archive", lambda *_a: (
        new_intents, list(new_replies.values()), new_replies))
    monkeypatch.setattr(evaluation, "_validate_repair_archive", lambda *_a: ([], [], {}, {}))
    monkeypatch.setattr(evaluation, "_evaluation_truth", lambda *_a: (
        {(month, aid): link}, {(month, aid, repeat): real for repeat in (1, 2)},
        {"evaluation_package": "injected", "evaluation_package_manifest_sha256": "0" * 64}))
    monkeypatch.setattr(evaluation, "ROOT", tmp_path)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "config.json").write_text(json.dumps({"protocol_sha256": "synthetic"}))
    (run_dir / "generation_receipt.json").write_text(json.dumps({
        "protocol_sha256": "synthetic", "main_complete": True,
        "main": {"status": "completed", "technical_gate": {"passed": True}},
        "repair": {"status": "not_needed"}}))
    out = tmp_path / "outputs" / "evaluation"
    result = evaluation.evaluate(run_dir, out)
    summary = json.loads((out / "summary.json").read_text())
    cases = json.loads((out / "cases_private.json").read_text())
    assert result["new_api_calls"] == 0
    assert summary["support"]["all_five_common_support"]["q9_person_months"] == 1
    assert summary["support"]["all_five_common_support"]["q8_person_months"] == 1
    assert cases[0]["arms"]["O0"]["source_key"] == f"{month}|Q3|1|{aid}"
    assert cases[0]["arms"]["O0"]["source_archive"] == "old_v3"
    assert cases[0]["arms"]["T1"]["source_key"] == f"{month}|T0|1|{aid}"
    assert "by_month" in summary["support_summaries"]["all_five_common_support"]["summaries"]["O0"]

