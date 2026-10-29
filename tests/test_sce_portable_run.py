"""Own-key wiring is tested with injected transport, never a paid model."""
import json
from pathlib import Path

import pytest

from studies.sce_inflation_expectations.submission_tools import portable_run as p

DATA = Path(__file__).resolve().parents[1] / "outputs/sce_portable_runtime_20261029_v2"


def reply(point=3.2):
    return dict(raw_response_text=json.dumps(dict(point_pct=point,
        q9={f"bin{i}": (100 if i == 4 else 0) for i in range(1, 11)})),
        returned_model=p.MODEL, returned_provider="SiliconFlow", finish_reason="stop",
        api_reported_cost_usd=0)


@pytest.fixture
def data():
    if not (DATA / "index.json").exists():
        pytest.skip("Local frozen input exporter integration fixture is not built")
    return DATA


def test_plan_does_not_read_credentials(data, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    plan = p.plan(data)
    assert plan["new_API_calls"] == 0 and not plan["credentials_read"]
    assert plan["maximum_main_requests"] == 16
    with pytest.raises(ValueError):
        p.plan(data, scope="full", people=2)
    with pytest.raises(ValueError):
        p.plan(data, tasks=["A", "A"])
    reordered = p.plan(data, tasks=["monthly", "B"])
    assert [r["task"] for r in reordered["tasks"]] == ["B", "monthly"]


def test_fresh_smoke_all_tasks_and_resume(data, tmp_path):
    calls = []
    def send(messages):
        calls.append(messages)
        return reply()
    out = tmp_path / "fresh"
    result = p.execute(data, out, budget_usd=1, sender=send, workers=2, cool=lambda _: None)
    assert result["answers"] == 16
    assert len(calls) == 14  # two freshly generated B roots reused, no archived root
    assert not result["actual_model_results"] and not result["evaluation_opened"]
    before = len(calls)
    again = p.execute(data, out, budget_usd=1, sender=send, workers=2, resume=True)
    assert again["answers"] == 16 and len(calls) == before
    with pytest.raises(ValueError, match="Resume"):
        p.execute(data, out, budget_usd=2, sender=send, resume=True)


@pytest.mark.parametrize("task", ["monthly", "weekly"])
def test_changed_current_answer_changes_following_prompt(data, task):
    index = p.load_index(data)
    first = p.checked_wave(data, index["waves"][task][0])
    second = p.checked_wave(data, index["waves"][task][1])
    selected = sorted(first["rows"])[:1]
    before, _ = p.render_wave(task, first, selected)
    key = f"{task}|{first['period']}|{selected[0]}"
    a = reply(2); b = reply(9)
    a.update(actual_model_results=False); b.update(actual_model_results=False)
    after_a, _ = p.advance(task, before, {key: a}, {}, first, selected)
    after_b, _ = p.advance(task, before, {key: b}, {}, first, selected)
    predecessor = first.get("point", {}).get("cutoff", first["period"])
    # The second weekly point is a public-release reset; choose a same-cycle
    # next point to verify that it really carries a freshly changed answer.
    if task == "weekly":
        first = second
        second = p.checked_wave(data, index["waves"][task][2])
        before, _ = p.render_wave(task, first, selected, after_a, predecessor)
        key = f"{task}|{first['period']}|{selected[0]}"
        after_a, _ = p.advance(task, before, {key: a}, {}, first, selected)
        after_b, _ = p.advance(task, before, {key: b}, {}, first, selected)
        predecessor = first["point"]["cutoff"]
    _, ma = p.render_wave(task, second, selected, after_a, predecessor)
    _, mb = p.render_wave(task, second, selected, after_b, predecessor)
    assert ma != mb
    assert '"point_pct": 9' in mb[selected[0]][0]["content"]


def test_budget_stops_before_dispatch(data, tmp_path):
    def never(_):
        raise AssertionError("No network may be attempted beyond budget")
    r = p.execute(data, tmp_path / "tiny", budget_usd=1e-9, sender=never, workers=1)
    assert r["status"] == "stopped_data_preserved"
    assert r["receipt"]["attempts"] == 0


def test_live_requires_confirmation_before_reading_key(data, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="confirm-paid"):
        p.execute(data, tmp_path / "not_authorized", budget_usd=1)
    assert not (tmp_path / "not_authorized").exists()


def test_unknown_intent_is_never_resent(data, tmp_path):
    from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
    out = tmp_path / "interrupted"; (out / "segments/segment_000000").mkdir(parents=True)
    slot = dict(key="test|1", messages=[dict(role="user", content="x")], month="202511",
        arm="B", repeat=1, agent_id="x", reserved_usd=.01)
    slot["prompt_sha256"] = message_hash(slot["messages"])
    (out / "segments/segment_000000/dispatch_private.jsonl").write_text(json.dumps(dict(
        key=slot["key"], prompt_sha256=slot["prompt_sha256"], reserved_usd=.01)) + "\n")
    def never(_):
        raise AssertionError("Unknown request was resent")
    receipt, _ = p._run_slots(out, [slot], never, p.protocol(1), 1, True, lambda _: None)
    assert receipt["unresolved"] == 1 and receipt["attempts"] == 1


def test_known_bad_q9_repairs_once_preserving_successful_q8(data, tmp_path):
    calls = []
    def send(messages):
        calls.append(messages)
        result = reply(2)
        if len(calls) == 1:
            result["raw_response_text"] = '{"point_pct":2,"q9":{"bin1":100}}'
        elif len(calls) > 32:
            result = reply(9)
        return result
    out = tmp_path / "one_repair"
    result = p.execute(data, out, tasks=["B"], people=32, periods=1,
        budget_usd=1, sender=send, workers=1)
    assert result["receipt"]["attempts"] == 33
    answers = [json.loads(line) for line in (out / "answers.jsonl").read_text().splitlines()]
    repaired = [a for a in answers if a["field_sources"]["q9"] == "repair"]
    assert len(repaired) == 1 and repaired[0]["q8"] == 2
    assert repaired[0]["field_sources"]["q8"] == "main"


def test_tiny_smoke_can_repair_one_failed_call(data, tmp_path):
    calls = []
    def send(messages):
        calls.append(messages)
        r = reply()
        if len(calls) == 1:
            r["raw_response_text"] = "{}"
        return r
    result = p.execute(data, tmp_path / "tiny_repair", tasks=["B"], people=2,
        periods=1, budget_usd=1, workers=1, sender=send)
    assert result["status"] == "fresh_generation_complete"
    assert result["receipt"]["attempts"] == 3 and len(calls) == 3


def test_initial_gate_can_use_each_known_technical_repair_once(data, tmp_path):
    calls = []
    def send(messages):
        calls.append(messages)
        r = reply()
        if len(calls) <= 2:
            r["raw_response_text"] = "{}"
        return r
    result = p.execute(data, tmp_path / "gate_repair", tasks=["B"], people=34,
        periods=1, budget_usd=1, workers=1, sender=send)
    assert result["status"] == "fresh_generation_complete"
    assert result["receipt"]["attempts"] == 36 and len(calls) == 36


def test_real_sdk_request_contract_uses_own_key_and_fixed_route(monkeypatch):
    import httpx
    client = httpx.Client
    observed = []
    def handle(request):
        assert request.url == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer unit-test-key"
        body = json.loads(request.content)
        assert body["provider"]["order"] == [p.ROUTE]
        assert body["provider"]["allow_fallbacks"] is False
        assert body["temperature"] == .5 and body["max_tokens"] == 1024
        assert body["reasoning"] == {"enabled": False}
        assert body["response_format"] == {"type": "json_object"}
        observed.append(body)
        return httpx.Response(200, json=dict(id="mock-request", object="chat.completion", created=0,
            model=p.MODEL, provider="SiliconFlow", choices=[dict(index=0, finish_reason="stop",
                message=dict(role="assistant", content=reply()["raw_response_text"]))],
            usage=dict(prompt_tokens=10, completion_tokens=10, total_tokens=20, cost=.00001)))
    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-test-key")
    class MockClient(client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handle), **kwargs)
    monkeypatch.setattr(httpx, "Client", MockClient)
    result = p.make_sender(p.protocol(1))([dict(role="user", content="test fixture")])
    assert result["request_id"] == "mock-request" and len(observed) == 1
    assert "unit-test-key" not in json.dumps(result)

