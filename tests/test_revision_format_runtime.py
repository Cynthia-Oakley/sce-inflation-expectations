import json
from types import SimpleNamespace

import pytest

from studies.sce_inflation_expectations.belief_revision import answer_to_revision
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
from studies.sce_inflation_expectations.revision_format_runtime import (
    ARMS, PROMPT, SHARED, REPLY_MARKER, RevisionFormatDecision,
    decode_revision, previous_answer, transform,
)


def prior():
    return {'point_pct': 3., 'q9': {f'bin{i}': 80. if i == 4 else 20. if i == 5 else 0. for i in range(1, 11)}}


def prompt(p=None):
    p = prior() if p is None else p
    return [{'role': 'user', 'content': 'P E timing\nYour earlier survey response\n'+json.dumps(p)+
             '\nQuestion 1 next 12 months\nQuestion 2 ten ranges\nReply with ONLY a JSON object OLD'}]


def test_same_information_and_shared_instruction_across_arms():
    original = prompt()
    a, b = [transform(original, arm) for arm in ARMS]
    prefix = original[0]['content'].split(REPLY_MARKER)[0]+SHARED
    assert a[0]['content'].startswith(prefix) and b[0]['content'].startswith(prefix)
    assert previous_answer(a) == previous_answer(b) == prior()
    assert 'OLD' not in b[0]['content']
    assert 'point_revision_pp' in b[0]['content'] and 'point_revision_pp' not in a[0]['content']
    assert 'OLD' in original[0]['content']


def test_missing_point_has_explicit_absolute_branch_no_q9_mean_imputation():
    p = {**prior(), 'point_pct': None}
    msgs = transform(prompt(p), 'revision')
    contract = msgs[0]['content'].split(SHARED)[1]
    assert 'point_revision_pp' not in contract
    assert 'Your previous point' in contract
    obj = {'point_pct': 7., 'q9_revision_pp': dict.fromkeys(p['q9'], 0.)}
    restored = decode_revision(json.dumps(obj), p)
    assert restored['point_pct'] == 7. and restored['q9'] == p['q9']
    with pytest.raises(ValueError, match='absolute'):
        decode_revision(json.dumps({**obj, 'point_revision_pp': 1.}), p)


def test_revision_can_move_far_and_rejects_invalid_mass_without_repair():
    current = {'point_pct': -4.5, 'q9': dict.fromkeys(prior()['q9'], 10.)}
    change = answer_to_revision(prior(), current)
    restored = decode_revision(json.dumps(change), prior())
    assert restored['point_pct'] == -4.5 and restored['q9'] == current['q9']
    change['q9_revision_pp']['bin1'] -= 1
    with pytest.raises(ValueError, match='sum to zero'):
        decode_revision(json.dumps(change), prior())


def fake_decision(tmp_path, raw):
    messages = transform(prompt(), 'revision')
    d = RevisionFormatDecision(prompt_version=PROMPT, llm_kind='openai', model='fake-only',
        max_calls=1, retry_max=0, max_prompt_chars=30000, cost_cap_usd=1,
        price_input_per_mtok=.3, price_output_per_mtok=1.2,
        run_id='test-not-an-api', audit_dir=str(tmp_path),
        revision_format_bundle={'arm': 'revision', 'messages_sha256': {'anon': message_hash(messages)}})
    d.build_llm_messages = lambda ob: messages
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=raw), finish_reason='stop')],
        model='fake-returned', id='fake-request', system_fingerprint=None,
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=8))
    d.llm = SimpleNamespace(chat=lambda msgs: (response, 5.))
    ob = SimpleNamespace(agent_id='anon', step=1, macro_information={'target_month': '2021-05', 'as_of': '2021-05-21T23:59:59-04:00'})
    return d, ob


def test_original_reply_retained_and_reconstructed_answer_drives_action(tmp_path):
    obj = {'point_revision_pp': 1.5, 'q9_revision_pp': dict.fromkeys(prior()['q9'], 0), 'reason': 'same facts'}
    raw = json.dumps(obj)
    d, ob = fake_decision(tmp_path, raw)
    a = d._decide_openai_one(ob)
    assert a.payload['point_pct'] == 4.5 and a.payload['validation_status'] == 'valid'
    assert a.payload['q9_bin4'] == 80 and a.payload['q9_bin5'] == 20
    assert d.call_count == 1
    log = json.loads((tmp_path/'llm_calls.jsonl').read_text())
    assert log['raw_response_text'] == raw and log['returned_model'] == 'fake-returned'
    mapped = json.loads((tmp_path/'response_mapping.jsonl').read_text())
    assert mapped['reconstructed_answer']['point_pct'] == 4.5
    assert log['raw_response_sha256'] == mapped['raw_response_sha256']


def test_invalid_revision_is_counted_invalid_without_retry(tmp_path):
    obj = {'point_revision_pp': 1, 'q9_revision_pp': dict.fromkeys(prior()['q9'], 5)}
    d, ob = fake_decision(tmp_path, json.dumps(obj))
    a = d._decide_openai_one(ob)
    assert a.payload['validation_status'] == 'invalid'
    assert 'sum to zero' in a.payload['revision_mapping_error']
    assert d.call_count == 1
