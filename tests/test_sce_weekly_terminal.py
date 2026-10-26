import json

import pytest

from studies.sce_inflation_expectations.experiments import full_a_personal_terminal as transport
from studies.sce_inflation_expectations.experiments import weekly_terminal
from studies.sce_inflation_expectations.experiments.weekly_state import advance_state, initialize_state
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash


def fields(q8=2.0, q9=None, *, period=202510):
    return {
        "q8": {"value": q8, "source_period": period, "source_kind": "synthetic_donor"},
        "q9": {"value": q9 or [10.0] * 10, "source_period": period, "source_kind": "synthetic_donor"},
    }


def state_with_one_step(aid="a", cycle="2025-10|2025-11-10"):
    state = initialize_state(aid, cycle, "2025-11-11T00:00:00-05:00", fields(), center=2.0)
    state = advance_state(
        state,
        json.dumps({"point_pct": 4.0, "q9": {f"bin{i}": 10.0 for i in range(1, 11)}}),
        "2025-11-14T23:59:59-05:00",
        center=4.0,
    )
    state["news_memory"] = {
        "seen_article_ids": ["article-nov-1"],
        "month": "2025-11",
        "month_article_ids": ["article-nov-1"],
    }
    return state


def test_release_reset_keeps_same_household_news_memory_and_archives_cycle():
    old = state_with_one_step()
    prior = {"a": {"fields": fields(3.0, period=202510), "center": 3.0}}
    point = {
        "cycle_key": "2025-11|2025-12-08",
        "anchor_known_from": "2025-12-09T00:00:00-05:00",
    }

    result = weekly_terminal.state_before(
        {"a": old}, prior, point, "2025-11-14T23:59:59-05:00"
    )["a"]

    assert result["cycle_key"] == point["cycle_key"]
    assert result["fields"]["q8"]["value"] == 3.0
    assert result["news_memory"] == old["news_memory"]
    assert len(result["cycle_archives"]) == 1
    assert result["last_cutoff"] == old["last_cutoff"]


def test_state_before_rejects_cross_person_and_skipped_predecessor():
    old = state_with_one_step()
    prior = {"a": {"fields": fields(), "center": 2.0}}
    point = {"cycle_key": old["cycle_key"], "anchor_known_from": "2025-11-11T00:00:00-05:00"}

    swapped = {"a": dict(old, agent_id="b")}
    with pytest.raises(ValueError, match="Cross-person or skipped-week"):
        weekly_terminal.state_before(swapped, prior, point, old["last_cutoff"])
    with pytest.raises(ValueError, match="Cross-person or skipped-week"):
        weekly_terminal.state_before({"a": old}, prior, point, "2025-11-07T23:59:59-05:00")


def test_overlay_preserves_valid_main_field_and_repairs_only_allowed_missing_field():
    previous = initialize_state("a", "cycle", "2025-11-01T00:00:00-04:00", fields())
    main = {
        "error": None,
        "finish_reason": "stop",
        "raw_response_text": json.dumps({"point_pct": -3.5, "q9": {}}),
    }
    repair = {
        "error": None,
        "finish_reason": "stop",
        "raw_response_text": json.dumps({
            "point_pct": 99.0,
            "q9": {f"bin{i}": 10.0 for i in range(1, 11)},
        }),
    }

    result = weekly_terminal.overlay(previous, main, repair, ["q9"], "2025-11-21T23:59:59-05:00")

    assert result["fields"]["q8"]["value"] == -3.5
    assert result["fields"]["q9"]["value"] == [10.0] * 10
    assert result["last_response_field_sources"] == {"q8": "main", "q9": "repair"}
    assert result["steps"][-1]["field_updated_from_model"] == {"q8": True, "q9": True}


def test_overlay_retains_same_household_fields_when_main_and_repair_fail():
    previous = initialize_state("a", "cycle", "2025-11-01T00:00:00-04:00", fields())
    main = {"error": "APIConnectionError", "finish_reason": None, "raw_response_text": ""}
    repair = {"error": "APITimeoutError", "finish_reason": None, "raw_response_text": ""}

    result = weekly_terminal.overlay(previous, main, repair, ["q8", "q9"], "2025-11-21T23:59:59-05:00")

    assert result["fields"] == previous["fields"]
    assert result["last_response_field_sources"] == {"q8": "retained_prior", "q9": "retained_prior"}
    assert result["steps"][-1]["field_retained_as_explicit_fallback"] == {"q8": True, "q9": True}
    assert result["steps"][-1]["technical_failure"] is True


def test_overlay_records_only_fields_actually_accepted_by_state():
    previous = initialize_state("a", "cycle", "2025-11-01T00:00:00-04:00", fields())
    main = {
        "error": None,
        "finish_reason": "stop",
        "raw_response_text": json.dumps({
            "point_pct": 101.0,
            "q9": {f"bin{i}": 10.0 for i in range(1, 11)},
        }),
    }

    result = weekly_terminal.overlay(previous, main, None, [], "2025-11-21T23:59:59-05:00")

    assert result["fields"]["q8"] == previous["fields"]["q8"]
    assert result["fields"]["q9"]["value"] == [10.0] * 10
    assert result["last_response_field_sources"] == {"q8": "retained_prior", "q9": "main"}
    assert result["steps"][-1]["field_updated_from_model"] == {"q8": False, "q9": True}


def test_unresolved_intent_reserves_its_fee_and_cannot_be_redispatched(tmp_path):
    messages = [{"role": "user", "content": "frozen prompt"}]
    slot = {
        "key": "weekly|w20251114|a",
        "month": "202511",
        "arm": "weekly",
        "repeat": 1,
        "agent_id": "a",
        "messages": messages,
        "prompt_sha256": message_hash(messages),
        "reserved_usd": 0.01,
    }
    intent = {k: slot[k] for k in ("key", "prompt_sha256", "reserved_usd")}
    accounting = transport.queue.account([intent], [])
    assert accounting["unresolved"] == 1
    assert accounting["spent_or_reserved_usd"] == 0.01

    called = []
    with pytest.raises(ValueError, match="already-dispatched keys"):
        transport._execute_tolerant_segment(
            {"budget_cap_usd": 1.0}, [slot], tmp_path / "segment", lambda _: called.append(True),
            workers=1, max_workers=1, scale_after=1,
            policy={},
            prior_intents=[intent], prior_replies=[],
        )
    assert called == []


def test_budget_guard_does_not_dispatch_when_reservation_exceeds_remaining_cap(tmp_path):
    messages = [{"role": "user", "content": "frozen prompt"}]
    slot = {
        "key": "weekly|w20251114|a",
        "month": "202511",
        "arm": "weekly",
        "repeat": 1,
        "agent_id": "a",
        "messages": messages,
        "prompt_sha256": message_hash(messages),
        "reserved_usd": 0.01,
    }
    calls = []
    result, intents, replies = transport._execute_tolerant_segment(
        {"budget_cap_usd": 0.005}, [slot], tmp_path / "budget_segment", lambda _: calls.append(True),
        workers=1, max_workers=1, scale_after=1,
        policy={},
    )

    assert result["halt_reason"] == "Budget cap reached before dispatch"
    assert intents == replies == []
    assert calls == []
