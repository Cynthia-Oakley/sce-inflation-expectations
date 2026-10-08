import copy
import hashlib
import json
import pytest

from studies.sce_inflation_expectations.model_counterfactual import preflight
from studies.sce_inflation_expectations.model_followup import followup_rows, prior_ledger, ancestor_successes


def row():
    return {'case_id': 'test', 'route_candidate': 'deepinfra/fp8',
            'input_price_per_million': .36, 'output_price_per_million': .40,
            'payload': {'model': 'qwen/qwen-2.5-72b-instruct',
                        'messages': [{'role': 'user', 'content': 'frozen input'}],
                        'provider': {'order': ['deepinfra/fp8'], 'allow_fallbacks': False,
                                     'require_parameters': True}}}


def endpoint():
    return {'tag': 'deepinfra/fp8', 'status': -2, 'uptime_last_30m': 91.0,
            'pricing': {'prompt': '0.00000036', 'completion': '0.00000040'},
            'supported_parameters': ['response_format', 'temperature', 'max_tokens']}


def test_degraded_opt_in_and_old_default():
    e = endpoint(); d = {'data': {'endpoints': [e]}}
    with pytest.raises(ValueError): preflight(row(), d)
    assert preflight(row(), d, allow_degraded=True)['status'] == -2
    for status in [-1, -3, -5, -10, 999]:
        e['status'] = status
        with pytest.raises(ValueError): preflight(row(), d, allow_degraded=True)


def test_degraded_still_requires_uptime_price_and_json():
    for uptime in [None, 79.9, float('nan'), 101, True]:
        e = endpoint(); e['uptime_last_30m'] = uptime
        with pytest.raises(ValueError): preflight(row(), {'data': {'endpoints': [e]}}, allow_degraded=True)
    e = endpoint(); e['pricing']['prompt'] = '0.000001'
    with pytest.raises(ValueError): preflight(row(), {'data': {'endpoints': [e]}}, allow_degraded=True)
    e = endpoint(); e['supported_parameters'] = ['temperature', 'max_tokens']
    with pytest.raises(ValueError): preflight(row(), {'data': {'endpoints': [e]}}, allow_degraded=True)


def test_fixed_case_substitutions_do_not_change_messages():
    rows = [dict(row(), case_id=f'case_{i}') for i in range(40)]
    before = copy.deepcopy(rows)
    result = followup_rows(rows, ['meta-llama/llama-3.3-70b-instruct'])
    assert rows == before and len(result) == 40
    assert all(r['payload']['messages'] == before[i]['payload']['messages'] for i, r in enumerate(result))
    assert all(r['payload']['provider']['order'] == ['deepinfra/turbo'] for r in result)
    with pytest.raises(ValueError): followup_rows(rows, ['meta-llama/llama-3.1-70b-instruct'])
    with pytest.raises(ValueError): followup_rows(rows[:-1], ['qwen/qwen-2.5-72b-instruct'])


def test_prior_cost_and_duplicate_success_audit():
    calls = [{'case_id':'one', 'requested_model':'old', 'answer':{}, 'billing':{'charged_or_reserved_usd':.03}},
             {'case_id':'two', 'requested_model':'old', 'error':'invalid_bins', 'billing':{'charged_or_reserved_usd':.01}}]
    summary = {'status':'complete', 'paid_attempts':2, 'valid_answers':1, 'total_charged_or_reserved_usd':.04}
    spent, by_model, done = prior_ledger(summary, calls)
    assert spent == .04 and by_model == {'old':.04} and done == {('one', 'old')}
    summary['total_charged_or_reserved_usd'] = 0
    with pytest.raises(ValueError): prior_ledger(summary, calls)


def test_followup_ledger_keeps_prior_run_cost():
    calls = [{'case_id':'two', 'requested_model':'new', 'answer':{},
              'billing':{'charged_or_reserved_usd':.01}}]
    summary = {'status':'complete', 'paid_attempts':1, 'valid_answers':1,
               'prior_cost_usd':.04, 'total_charged_or_reserved_usd':.05,
               'models':{'new':{'charged_or_reserved_usd':.03}}}
    spent, by_model, done = prior_ledger(summary,calls)
    assert spent == .05 and by_model == {'new':.03} and done == {('two','new')}
    summary['prior_cost_usd'] = -.04
    with pytest.raises(ValueError): prior_ledger(summary,calls)


def test_ancestor_successes_are_pinned(tmp_path):
    folder=tmp_path/'outputs'/'parent';folder.mkdir(parents=True)
    summary=folder/'run_summary.json';summary.write_text('{}')
    calls=folder/'llm_calls.jsonl';calls.write_text(json.dumps({'case_id':'one','requested_model':'old','answer':{}})+'\n')
    child={'prior_run_hashes':{str(p.relative_to(tmp_path)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [summary,calls]}}
    assert ancestor_successes(child,tmp_path)=={('one','old')}
    calls.write_text('')
    with pytest.raises(ValueError):ancestor_successes(child,tmp_path)
