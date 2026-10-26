from copy import deepcopy
import json

import pytest

from studies.sce_inflation_expectations.experiments import monthly_main_repair_followup as follow
from studies.sce_inflation_expectations.state_continuity_runtime import advance_state
from test_sce_monthly_main_repair import position
from test_sce_state_continuity_execution import reply


def example(tmp_path, monkeypatch, usable=True):
    previous = tmp_path / 'prior'; previous.mkdir()
    out = tmp_path / 'next'; out.mkdir(); calls = out / 'calls'; calls.mkdir()
    pos = position(); old = deepcopy(pos['state_after'])
    pos['state_after']['fields']['q9'] = deepcopy(pos['state_before']['fields']['q9'])
    pos['state_after']['transition']['field_updated_from_model']['q9'] = False
    pos['state_after']['transition']['field_retained_as_explicit_fallback']['q9'] = True
    pos['manual_repair'] = dict(reuse_key='one', accepted_fields=['q8'])
    new = advance_state(pos['state_before'], reply(point=99)['raw_response_text'], '202505',
                        '2025-05-15T23:59:59-04:00')
    row = dict(reuse_key='one', state_after=new, prompt_sha256='same', finish_reason='stop',
               error=None if usable else 'APIConnectionError')
    def dump(path, value):path.write_text(json.dumps(value))
    dump(previous / 'positions_private.jsonl', pos)
    for name in ('calls_private.jsonl', 'dispatch_private.jsonl', 'manual_repair_calls_private.jsonl'):
        dump(previous / name, dict(original=name))
    dump(previous / 'receipt.json', dict(attempts=1, logical_positions=1, original_api_attempts=1,
         manual_repair_api_attempts=1, physical_api_attempts=2, repaired_q8=1, repaired_q9=0,
         reported_cost_usd=.12, spent_or_reserved_usd=.14, actual_model_results=True))
    dump(previous / 'manifest.json', dict(files_sha256={}))
    dump(calls / 'calls_private.jsonl', row)
    dump(calls / 'receipt.json', dict(status='completed', attempts=1, actual_model_results=True,
         reported_cost_usd=.01, spent_or_reserved_usd=.015))
    dump(calls / 'manifest.json', {})
    dump(out / 'targets_private.json', [dict(reuse_key='one', fields=['q9'])])
    monkeypatch.setattr(follow.base, 'checked', lambda f:dict(original_main=str(previous),
                       original_total_cap_usd=40, protocol_sha256='pinned'))
    return out, pos, old


def test_followup_counts_all_three_physical_rounds_without_duplicating_people(tmp_path, monkeypatch):
    out, _, _ = example(tmp_path, monkeypatch)
    receipt = follow.materialize(out)
    assert receipt['attempts'] == receipt['logical_positions'] == 1
    assert receipt['physical_api_attempts'] == 3
    assert receipt['manual_repair_api_attempts'] == 2
    assert receipt['last_manual_repair_api_attempts'] == 1
    assert receipt['reported_cost_usd'] == pytest.approx(.13)
    assert receipt['spent_or_reserved_usd'] == pytest.approx(.155)
    assert receipt['repaired_q8'] == 1 and receipt['this_repair_q8'] == 0
    assert receipt['repaired_q9'] == receipt['this_repair_q9'] == 1
    assert receipt['remaining_q8'] == receipt['remaining_q9'] == 0


def test_followup_preserves_good_q8_previous_provenance_and_raw_archives(tmp_path, monkeypatch):
    out, before, old = example(tmp_path, monkeypatch)
    follow.materialize(out)
    [merged] = list(follow.base.records(out / 'combined/positions_private.jsonl'))
    assert merged['state_after']['fields']['q8'] == old['fields']['q8']
    assert merged['manual_repair_history'] == [before['manual_repair']]
    assert merged['manual_repair']['accepted_fields'] == ['q9']
    for name in ('calls_private.jsonl', 'dispatch_private.jsonl', 'manual_repair_calls_private.jsonl',
                 'residual_repair_calls_private.jsonl'):
        assert (out / 'combined' / name).exists()
    assert len(list(follow.base.records(out / 'combined/positions_private.jsonl'))) == 1


def test_another_connection_failure_preserves_existing_answer_and_missing_flag(tmp_path, monkeypatch):
    out, pos, _ = example(tmp_path, monkeypatch, usable=False)
    receipt = follow.materialize(out)
    [merged] = list(follow.base.records(out / 'combined/positions_private.jsonl'))
    assert receipt['remaining_q9'] == 1 and receipt['this_repair_q9'] == 0
    assert merged['state_after'] == pos['state_after']


def test_refuses_engineering_output_as_real_followup(tmp_path, monkeypatch):
    out, _, _ = example(tmp_path, monkeypatch)
    path = out / 'calls/receipt.json'; receipt = json.loads(path.read_text())
    receipt['actual_model_results'] = False; path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='actual follow-up'):
        follow.materialize(out)
