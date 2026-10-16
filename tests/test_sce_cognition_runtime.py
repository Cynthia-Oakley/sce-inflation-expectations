from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from scripts import run_sce_cognition_trial as runner
from studies.sce_inflation_expectations import cognition_runtime as runtime
from studies.sce_inflation_expectations.cognition_input import build_records, render_cognition_block
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
from studies.sce_inflation_expectations.revision_format_runtime import transform as direct_transform


def record():
    return build_records([{'userid': 1, 'month': 202004}], [{
        'userid': 1, 'date': 202003, 'QNUM1': '160', 'QNUM8': '3',
        '_source_path': 'synthetic.xlsx', '_source_sha256': 'a'*64}])[0]


def original(label='low'):
    prior = {'point_pct': 3., 'q9': {f'bin{i}': 10. for i in range(1, 11)}}
    return [{'role': 'user', 'content':
        f"Your score on the survey's numeracy assessment was {label}.\nP/E unchanged\n"
        'Your earlier survey response\n'+json.dumps(prior)+
        '\nQuestion 1 (point estimate): next 12 months\nQuestion 2: same ten ranges\n'
        'Reply with ONLY a JSON object OLD'}]


@pytest.mark.parametrize('label', ['high', 'low'])
def test_only_cognition_block_changes_and_original_label_is_retained(label):
    messages = original(label)
    direct = direct_transform(messages, 'direct')
    assert runtime.transform(messages, 'label_only', record()) == direct
    for arm in ('question_answer', 'faithful_paraphrase'):
        actual = runtime.transform(messages, arm, record())
        block = render_cognition_block(arm, record()).rstrip()+'\n\n'
        assert actual[0]['content'].replace(block, '', 1) == direct[0]['content']
        assert f'numeracy assessment was {label}.' in actual[0]['content']
        assert '160 dollars' in actual[0]['content']
        assert 'point_revision_pp' not in actual[0]['content']
    assert messages == original(label)


def test_whitelist_is_applied_even_in_label_only(tmp_path):
    contaminated = deepcopy(record())
    contaminated['current_q9'] = {'bin1': 100}
    with pytest.raises(ValueError, match='whitelist'):
        runtime.transform(original(), 'label_only', contaminated)
    path = tmp_path/'payloads.json'
    path.write_text(json.dumps({'anon': contaminated}))
    with pytest.raises(ValueError, match='whitelist'):
        runtime.load_payloads(path, runner.sha(path))


def decision(tmp_path, monkeypatch, kind='scripted', raw=None):
    path = tmp_path/'payloads.json'
    path.write_text(json.dumps({'anon': record()}))
    messages = runtime.transform(original(), 'question_answer', record())
    bundle = {'arm': 'question_answer', 'parent': {}, 'messages_sha256': {'anon': message_hash(messages)}}
    monkeypatch.setattr(runtime, 'parent_messages', lambda ob, parent: original())
    d = runtime.CognitionDecision(prompt_version=runtime.PROMPT, llm_kind=kind,
        model='fake-only', max_calls=1, retry_max=0, max_prompt_chars=30000,
        cost_cap_usd=1, price_input_per_mtok=.3, price_output_per_mtok=1.2,
        run_id='test-not-an-api', audit_dir=str(tmp_path), cognition_bundle=bundle,
        cognition_payloads_file=str(path), cognition_payloads_sha256=runner.sha(path))
    ob = SimpleNamespace(agent_id='anon', step=1,
        macro_information={'target_month': '2020-04', 'as_of': '2020-04-20T23:59:59-04:00'},
        local_physical={'profile': {'numeracy': 'low'}})
    if kind == 'openai':
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=raw), finish_reason='stop')],
            model='fake-returned', id='fake-request', system_fingerprint=None,
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=8))
        d.llm = SimpleNamespace(chat=lambda messages: (response, 5.))
    return d, ob, messages


def test_scripted_builds_and_audits_full_input_without_api(tmp_path, monkeypatch):
    d, ob, messages = decision(tmp_path, monkeypatch)
    action = d._decide_scripted([ob])[0]
    logged = json.loads((tmp_path/'scripted_inputs.jsonl').read_text())
    assert logged['messages'] == messages
    assert logged['prompt_sha256'] == message_hash(messages)
    assert logged['new_api_calls'] == d.call_count == 0
    assert action.payload['actual_messages_sha256'] == message_hash(messages)
    assert json.loads((tmp_path/'scripted_decisions.jsonl').read_text())['payload'] == action.payload
    assert not (tmp_path/'llm_calls.jsonl').exists()


def test_actual_message_and_payload_hashes_are_enforced(tmp_path, monkeypatch):
    d, ob, _ = decision(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime, 'parent_messages', lambda ob, parent: original('high'))
    with pytest.raises(ValueError, match='prompt changed'):
        d.build_llm_messages(ob)
    with pytest.raises(ValueError, match='payload file changed'):
        runtime.load_payloads(tmp_path/'payloads.json', '0'*64)
    altered = deepcopy(d.records)
    altered['anon']['target_month'] = 202005
    with pytest.raises(ValueError, match='target month'):
        runtime.build_messages(ob, d.bundle, altered)


def test_original_absolute_reply_is_preserved_and_never_remapped(tmp_path, monkeypatch):
    raw = json.dumps({'point_pct': -4.5, 'q9': {f'bin{i}': 10 for i in range(1, 11)}, 'reason': 'same facts'})
    d, ob, messages = decision(tmp_path, monkeypatch, 'openai', raw)
    action = d._decide_openai_one(ob)
    assert action.payload['point_pct'] == -4.5
    assert action.payload['validation_status'] == 'valid'
    assert d.call_count == 1
    logged = json.loads((tmp_path/'llm_calls.jsonl').read_text())
    assert logged['raw_response_text'] == raw
    assert logged['prompt_sha256'] == message_hash(messages)
    assert json.loads(logged['prompt_text']) == messages
    assert not (tmp_path/'response_mapping.jsonl').exists()


def test_invalid_reply_is_retained_without_retry_or_probability_repair(tmp_path, monkeypatch):
    raw = json.dumps({'point_pct': 1, 'q9': {f'bin{i}': 5 for i in range(1, 11)}})
    d, ob, _ = decision(tmp_path, monkeypatch, 'openai', raw)
    action = d._decide_openai_one(ob)
    assert d.call_count == 1
    assert action.payload['validation_status'] == 'invalid'
    assert action.payload['q9_sum'] == 50
    assert json.loads((tmp_path/'llm_calls.jsonl').read_text())['raw_response_text'] == raw


def test_api_error_stops_after_one_audited_attempt(tmp_path, monkeypatch):
    d, ob, messages = decision(tmp_path, monkeypatch, 'openai')
    def fail(messages):
        raise RuntimeError('synthetic provider failure')
    d.llm.chat = fail
    with pytest.raises(RuntimeError, match='without automatic retry'):
        d._decide_openai_one(ob)
    assert d.call_count == 1
    assert d.cost_summary()['reserved_cost_usd'] > 0
    assert 'synthetic provider failure' in json.loads((tmp_path/'llm_calls.jsonl').read_text())['error']
    assert (tmp_path/'stopped_decisions.jsonl').exists()
    with pytest.raises(ValueError, match='Actual request'):
        d._call_with_audit(ob, {}, messages+[{'role': 'user', 'content': 'changed'}], 0)


def manifest_folder(tmp_path):
    protocol = {'model': 'deepseek-flash', 'temperature': .5, 'max_tokens': 1024,
                'retry_max': 0, 'thinking': 'disabled', 'planned_calls': 1}
    runner.dump(tmp_path/'protocol.json', protocol)
    m = {'source_sha256': {}, 'prepared_file_sha256': {'protocol.json': runner.sha(tmp_path/'protocol.json')},
         'protocol_sha256': runner.sha(tmp_path/'protocol.json'), 'planned_calls': 1, 'proposed_cap_usd': 3,
         'jobs': [{'month': 202004, 'arm': 'label_only', 'repeat': 1, 'cap_usd': .1, 'run_id': 'synthetic'}]}
    runner.dump(tmp_path/'manifest.json', m)
    return m


def test_runner_verifies_frozen_inputs_and_rejects_unapproved_paid_scope(tmp_path):
    m = manifest_folder(tmp_path)
    assert runner.verify(tmp_path) == m
    runner.dump(tmp_path/'authorization.json', {'approved': False})
    with pytest.raises(ValueError, match='specific matching'):
        runner.authorization_gate(tmp_path, m)
    (tmp_path/'protocol.json').write_text('{}')
    with pytest.raises(ValueError, match='prepared input changed'):
        runner.verify(tmp_path)


def test_runner_rejects_missing_engineering_receipts_before_credentials(tmp_path):
    m = manifest_folder(tmp_path)
    runner.dump(tmp_path/'authorization.json', {'approved': True, 'protocol_sha256': m['protocol_sha256'],
        'planned_calls': 1, 'cap_usd': 3})
    runner.dump(tmp_path/'engineering_checks.json', [])
    with pytest.raises(ValueError, match='all offline cells'):
        runner.authorization_gate(tmp_path, m)
