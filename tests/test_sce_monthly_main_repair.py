from copy import deepcopy
import json

import pytest

from studies.sce_inflation_expectations.experiments import monthly_main_repair as repair
from studies.sce_inflation_expectations.state_continuity_runtime import advance_state
from test_sce_state_continuity_execution import fixture, reply


def position():
    p, nodes, inputs = fixture()
    initial = inputs['202505', 'a'][1]
    raw = reply(point=17)['raw_response_text']
    good = advance_state(initial, raw, '202505', '2025-05-15T23:59:59-04:00')
    return dict(nodes[0], reuse_key='one', state_before=initial, state_after=good,
                response_error=None, finish_reason='stop', prompt_sha256='same')


def test_only_technical_failures_selected_not_shape_or_normalization():
    pos = position()
    row = dict(pos, error=None, technical_usable=True,
               density_fit_fallback=True, scorer_status='two_nonadjacent')
    row['state_after']['transition']['q9_proportional_normalization'] = True
    assert repair.failed_fields(row) == []
    row['state_after']['transition']['field_updated_from_model']['q9'] = False
    assert repair.failed_fields(row) == ['q9']
    row['error'] = 'APIConnectionError'
    assert repair.failed_fields(row) == ['q8', 'q9']


def test_auth_or_unknown_errors_require_review():
    with pytest.raises(ValueError):
        repair.failed_fields(dict(error='UnauthorizedError'))
    with pytest.raises(ValueError):
        repair.failed_fields(dict(error='InternalServerError', error_http_status=503))


def test_q9_repair_preserves_original_successful_q8_and_input():
    pos = position(); pos['state_after']['fields']['q9'] = deepcopy(pos['state_before']['fields']['q9'])
    t = pos['state_after']['transition']; t['field_updated_from_model']['q9'] = False
    t['field_retained_as_explicit_fallback']['q9'] = True
    new = advance_state(pos['state_before'], reply(point=99)['raw_response_text'], '202505',
                        '2025-05-15T23:59:59-04:00')
    raw = dict(reuse_key='one', state_after=new, error=None, finish_reason='stop')
    before = deepcopy(pos)
    result = repair.overlay(pos, raw, dict(fields=['q9']))
    assert result['state_after']['fields']['q8']['value'] == 17
    assert result['state_after']['fields']['q9'] == new['fields']['q9']
    assert all(result['state_after']['transition']['field_updated_from_model'].values())
    assert result['manual_repair']['accepted_fields'] == ['q9']
    assert pos == before


@pytest.mark.parametrize('error,finish', [('APIConnectionError', None), (None, 'length')])
def test_failed_or_truncated_repair_does_not_change_good_fields(error, finish):
    pos = position(); before = deepcopy(pos)
    raw = dict(reuse_key='one', state_after=pos['state_after'], error=error, finish_reason=finish)
    result = repair.overlay(pos, raw, dict(fields=['q8', 'q9']))
    assert result['state_after'] == before['state_after']
    assert result['manual_repair']['accepted_fields'] == []


def test_partial_success_is_retained_without_inventing_valid_q9():
    pos = position(); initial = pos['state_before']
    pos.update(state_after=advance_state(initial, '', '202505', '2025-05-15T23:59:59-04:00'),
               response_error='APIConnectionError', finish_reason=None)
    new = advance_state(initial, '{"point_pct": 8}', '202505', '2025-05-15T23:59:59-04:00')
    result = repair.overlay(pos, dict(reuse_key='one', state_after=new, error=None, finish_reason='stop'),
                            dict(fields=['q8', 'q9']))
    assert result['state_after']['fields']['q8']['value'] == 8
    assert result['state_after']['transition']['field_updated_from_model'] == dict(q8=True, q9=False)


def test_extra_budget_is_bounded_with_original_unknown_fees_preserved():
    p, _, _ = fixture(); p['budget_cap_usd'] = 40
    b = repair.budget(dict(spent_or_reserved_usd=30.1, reported_cost_usd=28.9), p, 361)
    assert b['repair_cap_usd'] < 2 and b['combined_max_accounted_usd'] < 40
    assert b['original_accounted_usd'] == 30.1
    with pytest.raises(ValueError):
        repair.budget(dict(spent_or_reserved_usd=39.9, reported_cost_usd=28.9), p, 361)


def test_field_overlay_keeps_one_person_not_two_and_counts_physical_calls(tmp_path, monkeypatch):
    original = tmp_path / 'original'; original.mkdir()
    out = tmp_path / 'repair'; out.mkdir(); calls = out / 'calls'; calls.mkdir()
    pos = position(); pos['state_after'] = advance_state(pos['state_before'], '', '202505',
                                                       '2025-05-15T23:59:59-04:00')
    pos['response_error'] = 'APIConnectionError'
    new = dict(reuse_key='one', state_after=position()['state_after'], error=None,
               finish_reason='stop', prompt_sha256='same')
    def write(path, obj):
        path.write_text(json.dumps(obj))
    write(original / 'positions_private.jsonl', pos)
    for path, row in ((original / 'calls_private.jsonl', {'raw': 'original'}),
                      (original / 'dispatch_private.jsonl', {'raw': 'intent'}),
                      (calls / 'calls_private.jsonl', new)):
        write(path, row)
    write(original / 'receipt.json', dict(logical_positions=1, attempts=1,
          reported_cost_usd=.1, spent_or_reserved_usd=.2, actual_model_results=True, status='completed'))
    write(calls / 'receipt.json', dict(attempts=1, reported_cost_usd=.01, spent_or_reserved_usd=.02,
                                      status='completed', actual_model_results=True))
    write(calls / 'manifest.json', {}); write(original / 'manifest.json', {})
    write(out / 'targets_private.json', [dict(reuse_key='one', fields=['q8', 'q9'])])
    monkeypatch.setattr(repair, 'checked', lambda f:dict(original_main=str(original),
         original_total_cap_usd=40, protocol_sha256='frozen'))
    result = repair.materialize(out)
    assert len(list(repair.records(out / 'combined/positions_private.jsonl'))) == 1
    assert result['attempts'] == 1 and result['physical_api_attempts'] == 2
    assert result['manual_repair_api_attempts'] == 1
    assert result['reported_cost_usd'] == pytest.approx(.11)
    assert result['spent_or_reserved_usd'] == pytest.approx(.22)
    assert result['remaining_q8'] == result['remaining_q9'] == 0
    assert (original / 'positions_private.jsonl').read_text() == json.dumps(pos)
