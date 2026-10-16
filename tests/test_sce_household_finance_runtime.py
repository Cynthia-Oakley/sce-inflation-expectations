"""Offline tests: the model client is replaced before every simulated API call."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from studies.sce_inflation_expectations import household_finance_runtime as runtime
from studies.sce_inflation_expectations import model as model_module
from studies.sce_inflation_expectations.household_finance_input import (
    ARMS, RESEARCH_LINE, SCHEMA_VERSION, PERSPECTIVE_SENTENCE, render_household_finance_block,
)
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
from studies.sce_inflation_expectations.revision_format_runtime import transform as direct_transform


def record():
    return {'schema_version': SCHEMA_VERSION, 'research_line': RESEARCH_LINE,
        'target_month': 202004, 'current_q1_code': 2, 'current_q1_source_month': 202004,
        'previous_q1_code': 3, 'previous_q1_source_month': 202003,
        'current_source_sha256': 'a'*64, 'previous_source_sha256': 'a'*64}


def original(label='low'):
    prior = {'point_pct': 3., 'q9': {f'bin{i}': 10. for i in range(1, 11)}}
    return [{'role': 'user', 'content':
        f"Your score on the survey's numeracy assessment was {label}.\nP/E unchanged\n"
        'Your earlier survey response\n'+json.dumps(prior)+
        '\nQuestion 1 (point estimate): next 12 months\nQuestion 2: same ten ranges\n'
        'Reply with ONLY a JSON object OLD'}]


@pytest.mark.parametrize('label', ['high', 'low'])
def test_baseline_exact_and_only_the_finance_block_differs(label):
    messages = original(label)
    before = deepcopy(messages)
    direct = direct_transform(messages, 'direct')
    assert runtime.transform(messages, 'baseline', record()) == direct
    for arm in ARMS[1:]:
        actual = runtime.transform(messages, arm, record())
        block = render_household_finance_block(arm, record())
        assert actual[0]['content'].replace(block, '', 1) == direct[0]['content']
        assert f'numeracy assessment was {label}.' in actual[0]['content']
        assert actual[0]['content'].count('Reply with ONLY a JSON object') == 1
        assert 'point_revision_pp' not in actual[0]['content']
    facts = runtime.transform(messages, 'financial_facts', record())[0]['content']
    perspective = runtime.transform(messages, 'financial_perspective', record())[0]['content']
    assert perspective.replace(PERSPECTIVE_SENTENCE+'\n\n', '', 1) == facts
    assert messages == before


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_decision(tmp_path, monkeypatch, *, kind='scripted', raw=None, arm='financial_facts'):
    path = tmp_path/'payloads.json'
    path.write_text(json.dumps({'anon': record()}))
    messages = runtime.transform(original(), arm, record())
    bundle = {'arm': arm, 'parent': {'same': 'parent'}, 'messages_sha256': {'anon': message_hash(messages)}}
    def parent(ob, parent_bundle):
        assert parent_bundle == {'same': 'parent'}
        return original()
    monkeypatch.setattr(runtime, 'parent_messages', parent)
    kwargs = dict(prompt_version=runtime.PROMPT, llm_kind=kind,
        model='fake-only', max_calls=1, retry_max=0, max_prompt_chars=30000,
        cost_cap_usd=1, price_input_per_mtok=.3, price_output_per_mtok=1.2,
        run_id='test-not-an-api', audit_dir=str(tmp_path), household_finance_bundle=bundle,
        household_finance_payloads_file=str(path), household_finance_payloads_sha256=sha(path))
    # Ensure even construction cannot create a provider client or use credentials.
    monkeypatch.setattr(model_module, 'SCEOpenAILLM', lambda **kwargs: SimpleNamespace())
    d = runtime.HouseholdFinanceDecision(**kwargs)
    ob = SimpleNamespace(agent_id='anon', step=1,
        macro_information={'target_month': '2020-04', 'as_of': '2020-04-20T23:59:59-04:00'},
        local_physical={'profile': {'numeracy': 'low'}})
    if kind == 'openai':
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=raw), finish_reason='stop')],
            model='fake-returned', id='fake-request', system_fingerprint=None,
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=8))
        d.llm = SimpleNamespace(chat=lambda messages: (response, 5.))
    return d, ob, messages, kwargs


@pytest.mark.parametrize('arm', ARMS)
def test_scripted_audits_all_actual_messages_with_zero_api_calls(tmp_path, monkeypatch, arm):
    d, ob, messages, _ = make_decision(tmp_path, monkeypatch, arm=arm)
    action = d._decide_scripted([ob])[0]
    logged = json.loads((tmp_path/'scripted_inputs.jsonl').read_text())
    assert logged['messages'] == messages
    assert logged['prompt_sha256'] == message_hash(messages)
    assert logged['new_api_calls'] == d.call_count == 0
    assert action.payload['actual_messages_sha256'] == message_hash(messages)
    assert action.payload['household_finance_arm'] == arm
    assert json.loads((tmp_path/'scripted_decisions.jsonl').read_text())['payload'] == action.payload
    assert not (tmp_path/'llm_calls.jsonl').exists()


def test_payload_and_actual_request_hashes_target_and_attempt_are_enforced(tmp_path, monkeypatch):
    d, ob, messages, _ = make_decision(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='payload file changed'):
        runtime.load_payloads(tmp_path/'payloads.json', '0'*64)
    bad = deepcopy(record())
    bad['current_q9'] = 999
    path = tmp_path/'contaminated.json'
    path.write_text(json.dumps({'anon': bad}))
    with pytest.raises(ValueError, match='whitelist'):
        runtime.load_payloads(path, sha(path))
    with pytest.raises(ValueError, match='whitelist'):
        runtime.transform(original(), 'baseline', bad)
    changed = deepcopy(d.records)
    changed['anon'].update(target_month=202005, current_q1_source_month=202005, previous_q1_source_month=202004)
    with pytest.raises(ValueError, match='target month'):
        runtime.build_messages(ob, d.bundle, changed)
    monkeypatch.setattr(runtime, 'parent_messages', lambda ob, parent: original('high'))
    with pytest.raises(ValueError, match='prompt changed'):
        d.build_llm_messages(ob)
    for altered_messages, attempt in ((messages, 1), (messages+[{'role': 'user', 'content': 'extra'}], 0)):
        with pytest.raises(ValueError, match='Actual request'):
            d._call_with_audit(ob, {}, altered_messages, attempt)
    assert d.call_count == 0


def test_constructor_rejects_retry_prompt_and_roster_before_provider_use(tmp_path, monkeypatch):
    _, _, _, kwargs = make_decision(tmp_path, monkeypatch)
    for field, value, match in [('retry_max', 1, 'no automatic retries'),
                               ('prompt_version', 'other', 'mismatch')]:
        with pytest.raises(ValueError, match=match):
            runtime.HouseholdFinanceDecision(**{**kwargs, field: value})
    bundle = deepcopy(kwargs['household_finance_bundle'])
    bundle['messages_sha256']['other'] = 'b'*64
    with pytest.raises(ValueError, match='roster differs'):
        runtime.HouseholdFinanceDecision(**{**kwargs, 'household_finance_bundle': bundle})


def test_fake_api_preserves_absolute_answer_and_original_evidence(tmp_path, monkeypatch):
    raw = json.dumps({'point_pct': -4.5, 'q9': {f'bin{i}': 10 for i in range(1, 11)}, 'reason': 'same facts'})
    d, ob, messages, _ = make_decision(tmp_path, monkeypatch, kind='openai', raw=raw)
    action = d._decide_openai_one(ob)
    assert action.payload['point_pct'] == -4.5
    assert action.payload['validation_status'] == 'valid'
    assert action.payload['household_finance_arm'] == 'financial_facts'
    logged = json.loads((tmp_path/'llm_calls.jsonl').read_text())
    assert logged['raw_response_text'] == raw
    assert logged['prompt_sha256'] == message_hash(messages)
    assert json.loads(logged['prompt_text']) == messages
    assert d.call_count == 1
    assert not (tmp_path/'response_mapping.jsonl').exists()


def test_fake_invalid_response_is_kept_without_repair_or_retry(tmp_path, monkeypatch):
    raw = json.dumps({'point_pct': 1, 'q9': {f'bin{i}': 5 for i in range(1, 11)}})
    d, ob, _, _ = make_decision(tmp_path, monkeypatch, kind='openai', raw=raw)
    action = d._decide_openai_one(ob)
    assert action.payload['validation_status'] == 'invalid'
    assert action.payload['q9_sum'] == 50 and d.call_count == 1
    assert json.loads((tmp_path/'llm_calls.jsonl').read_text())['raw_response_text'] == raw


def test_fake_provider_error_stops_after_one_audited_attempt(tmp_path, monkeypatch):
    d, ob, _, _ = make_decision(tmp_path, monkeypatch, kind='openai')
    def fail(messages):
        raise RuntimeError('synthetic provider failure')
    d.llm.chat = fail
    with pytest.raises(RuntimeError, match='without automatic retry'):
        d._decide_openai_one(ob)
    assert d.call_count == 1 and d.cost_summary()['reserved_cost_usd'] > 0
    assert 'synthetic provider failure' in json.loads((tmp_path/'llm_calls.jsonl').read_text())['error']
    assert (tmp_path/'stopped_decisions.jsonl').exists()
