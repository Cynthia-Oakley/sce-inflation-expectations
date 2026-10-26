from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OFFICIAL = ROOT.parent / 'socioverse2_repo'
if str(OFFICIAL) not in sys.path:
    sys.path.append(str(OFFICIAL))
import studies
studies.__path__ = [str(ROOT / 'studies'), *studies.__path__]

from studies.sce_inflation_expectations.evaluation.full_a_personal import (
    action_view, validate_completed_view, _verify_files)


PRIOR = {'point': 8., 'mean': 7., 'iqr': 4., 'zero_deflation': .1,
         'q9_bins': [10.] * 10}


def action(q8=True, q9=True):
    return {'arm': 'T0', 'repeat': 1,
            'effective_q8': -2. if q8 else None,
            'effective_q9_bins': [0., 0., 0., 0., 0., 50., 50., 0., 0., 0.] if q9 else None,
            'field_updated': {'q8': q8, 'q9': q9},
            'needs_initial_fallback': {'q8': not q8, 'q9': not q9}}


def test_q8_is_independent_and_negative_point_is_legal():
    op, raw, counts = action_view(action(q9=False), PRIOR, {})
    assert op['point'] == raw['point'] == -2.
    assert op['mean'] == 7. and raw['mean'] is None
    assert counts == {'q9_retained_input': 1}


def test_q9_remains_valid_when_q8_needs_prior_fallback():
    a = action(q8=False)
    cache = {tuple(a['effective_q9_bins']): {'mean': 2., 'iqr': 1., 'zero_deflation': 0.}}
    op, raw, counts = action_view(a, PRIOR, cache)
    assert op['point'] == 8. and raw['point'] is None
    assert op['mean'] == raw['mean'] == 2.
    assert counts == {'q8_retained_input': 1}


def test_unsuccessful_density_fit_uses_declared_initial_scalar_not_human_value():
    a = action()
    cache = {tuple(a['effective_q9_bins']): {'mean': None, 'iqr': None, 'zero_deflation': None}}
    op, raw, counts = action_view(a, PRIOR, cache)
    assert op['mean'] == PRIOR['mean']
    assert raw['mean'] is None and raw['point'] == -2.
    assert counts == {'density_fit_fallback': 1}
    assert op['evaluation_only_input_scalar_fallback'] is True


@pytest.mark.parametrize('change', ['nonfinite_point', 'bad_bins', 'inconsistent_flags', 'wrong_arm'])
def test_rejects_inconsistent_overlay(change):
    a = action()
    if change == 'nonfinite_point':
        a['effective_q8'] = float('nan')
    elif change == 'bad_bins':
        a['effective_q9_bins'][0] = -1.
    elif change == 'inconsistent_flags':
        a['needs_initial_fallback']['q8'] = True
    else:
        a['arm'] = 'T1'
    with pytest.raises(ValueError):
        action_view(a, PRIOR, {})


@pytest.mark.parametrize('receipt', [
    {'status': 'completed', 'actual_model_results': False},
    {'status': 'incomplete', 'actual_model_results': True},
    {'status': 'completed', 'actual_model_results': True, 'unknown': 1},
    {'status': 'completed', 'actual_model_results': True, 'unknown_intents': 1},
    {'status': 'completed', 'actual_model_results': True, 'not_attempted': 1},
])
def test_incomplete_or_engineering_run_rejected_before_targets_or_manifest(tmp_path, receipt):
    (tmp_path / 'receipt.json').write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='before truth access'):
        validate_completed_view(tmp_path)
    assert not (tmp_path / 'manifest.json').exists()


def test_hash_verifier_rejects_escape_even_if_hash_would_match(tmp_path):
    from studies.sce_inflation_expectations.experiments.frozen_batch import sha
    sibling = tmp_path / 'outside.json'
    sibling.write_text('{}')
    inside = tmp_path / 'inside'
    inside.mkdir()
    with pytest.raises(ValueError, match='escaped'):
        _verify_files(inside, {'../outside.json': sha(sibling)})


def test_fallback_does_not_mutate_original_prior():
    before = deepcopy(PRIOR)
    op, _, _ = action_view(action(q8=False, q9=False), PRIOR, {})
    op['q9_bins'][0] = 99.
    assert PRIOR == before


def test_overlay_cannot_replace_a_successful_main_field_with_repair(tmp_path, monkeypatch):
    from studies.sce_inflation_expectations.evaluation import full_a_personal as module
    from studies.sce_inflation_expectations.experiments import full_a_personal_terminal as terminal
    from studies.sce_inflation_expectations.experiments.frozen_batch import dump
    run = tmp_path / 'run'
    view = run / 'generation_views/view_0001'
    segment = run / 'main/round_0001/segment_0001'
    segment.mkdir(parents=True)
    view.mkdir(parents=True)
    dump(run / 'protocol.json', {})
    monkeypatch.setattr(terminal, 'checked', lambda *args, **kwargs: ({'input_package': str(tmp_path)}, {}))
    monkeypatch.setattr(terminal, '_validate_input', lambda *args: None)
    raw = json.dumps({'point_pct': 2., 'q9': {f'bin{i}': 10. for i in range(1, 11)}})
    reply = dict(key='k', prompt_sha256='a' * 64, actual_model_results=True,
                 error=None, finish_reason='stop', raw_response_text=raw, api_reported_cost_usd=0.)
    (segment / 'dispatch_private.jsonl').write_text(json.dumps(dict(key='k', prompt_sha256='a' * 64,
                                                                  reserved_usd=.01)) + '\n')
    (segment / 'calls_private.jsonl').write_text(json.dumps(reply) + '\n')
    a = dict(action(), key='k', prompt_sha256='a' * 64, effective_q8=99.,
             effective_q9_bins=[10.] * 10, field_source={'q8': 'repair', 'q9': 'main'})
    (view / 'logical_actions_private.jsonl').write_text(json.dumps(a) + '\n')
    receipt = {'protocol_sha256': module.sha(run / 'protocol.json')}
    with pytest.raises(ValueError, match='preserved raw'):
        module._validate_production_origin(tmp_path, view, receipt)


def test_full_82_month_evaluation_adapter_with_hand_calculated_fixtures(tmp_path, monkeypatch):
    """Synthetic fixtures only: exercise every month and both macro splits, no fits/API."""
    from studies.sce_inflation_expectations.evaluation import full_a_personal as module
    from studies.sce_inflation_expectations.experiments.frozen_batch import dump, sha
    root = tmp_path
    monkeypatch.setattr(module, 'ROOT', root)
    # This hand-calculated statistics fixture is intentionally smaller than
    # the real 41,970-row production run. Strict production-origin checks have
    # separate runtime tests and are never disabled by the real CLI.
    monkeypatch.setattr(module, '_validate_production_origin', lambda *args: None)
    monkeypatch.setattr(module, 'validate_completed_view',
                        lambda path: (json.loads((path / 'receipt.json').read_text()),
                                      json.loads((path / 'manifest.json').read_text())))
    code_snapshot = root / 'evaluation_source.py'
    code_snapshot.write_bytes(module.Path(module.__file__).read_bytes())
    monkeypatch.setattr(module, '__file__', str(code_snapshot))
    assembly = root / 'old_assembly'
    monkeypatch.setattr(module, 'OLD_ASSEMBLY', assembly)
    inputs, view = root / 'inputs', root / 'view'
    truth, old = root / 'truth', root / 'old'
    for p in (inputs, view, truth, old / 'evaluation', old / 'readout', root / 'outputs'):
        p.mkdir(parents=True)
    months = [str(201901 + (i // 12) * 100 + i % 12) for i in range(82)]
    bins = action()['effective_q9_bins']
    prior_bins = [0., 0., 0., 0., 0., 0., 100., 0., 0., 0.]
    human_bins = [0., 0., 0., 0., 0., 100., 0., 0., 0., 0.]
    prior = dict(mean=3., iqr=1., point=3., zero_deflation=0., q9_bins=prior_bins)
    model_old = dict(mean=4., iqr=1., point=4., zero_deflation=0., q9_bins=prior_bins)
    files, sources, targets, actions, old_cases, national, full = {}, {}, [], [], [], [], {}
    for month in months:
        folder = inputs / month
        folder.mkdir()
        prompt_file = folder / 'prompts.json'
        weight_file = folder / 'weights_private.json'
        dump(prompt_file, {'month': month, 'rows': {'p': {'messages': [], 'prompt_sha256': 'a' * 64}}})
        dump(weight_file, {'p': {'analysis_weight': 1., 'stratum': 'test_cell'}})
        original_weights = root / 'outputs/sce_monthly_fine_full_inputs_20261023_v2' / f'{month}_weights_private.json'
        original_weights.parent.mkdir(exist_ok=True, parents=True)
        dump(original_weights, {'p': {'poststratified_weight': 1., 'stratum': 'test_cell'}})
        sources[str(original_weights.relative_to(root))] = sha(original_weights)
        for path in (prompt_file, weight_file):
            files[str(path.relative_to(inputs))] = sha(path)
        state_file = assembly / 'prompts' / month / 'initial_states_private.json'
        state_file.parent.mkdir(parents=True)
        dump(state_file, {'p': {'fields': {'q8': {'value': 3.}, 'q9': {'value': prior_bins}}}})
        sources[str(state_file.relative_to(root))] = sha(state_file)
        real = dict(q9_mean=2.5, q9_iqr=1., q9_zero_deflation=0., q9_bins=human_bins,
                    q8_point=2.5, previous_q9_mean=3., previous_q9_bins=prior_bins, previous_q8_point=3.)
        targets.append(dict(month=int(month), agent_id='p', real=real, monthly_past_reference=prior,
                            genuinely_observed_previous_q9=True, genuinely_observed_previous_q8=True,
                            profile={'education_group': 'college', 'numeracy': 'High', 'age_group': '35-54',
                                     'household_income_band': 'middle', 'region': 'Northeast'},
                            stratum='test_cell', initial_q9_provenance='own_adjacent'))
        old_cases.append(dict(month=int(month), agent_id='p', survey_entry_status='returning',
                              arms={module.ARM: model_old}))
        actions.append(dict(action(), effective_q8=2., month=month, agent_id='p', prompt_sha256='a' * 64))
        national.append(dict(month=month[:4] + '-' + month[4:], sim_pp=4., anchor_pp=3., truth_pp=2.5))
        full[month] = [dict(q9_mean=2.5, q8_point=2.5, weight=1.)]
    dump(inputs / 'summary.json', {'status': 'ready', 'source_sha256': sources})
    files['summary.json'] = sha(inputs / 'summary.json')
    dump(inputs / 'manifest.json', {'files_sha256': files})
    logical = view / 'logical_actions_private.jsonl'
    logical.write_text(''.join(json.dumps(r) + '\n' for r in actions))
    dump(view / 'receipt.json', dict(status='completed', actual_model_results=True,
        input_manifest_sha256=sha(inputs / 'manifest.json'), planned_calls=82))
    dump(view / 'manifest.json', {'files_sha256': {
        'receipt.json': sha(view / 'receipt.json'), 'logical_actions_private.jsonl': sha(logical)}})
    dump(truth / 'truth_private.json', targets)
    dump(truth / 'full_wave_private.json', full)
    dump(truth / 'manifest.json', dict(truth_sha256=sha(truth / 'truth_private.json'),
                                      full_wave_sha256=sha(truth / 'full_wave_private.json')))
    dump(truth / 'scoring_cache_private.json', [dict(bins=bins, score=dict(mean=2., iqr=1., zero_deflation=0.))])
    dump(truth / 'cache_receipt.json', dict(cache_sha256=sha(truth / 'scoring_cache_private.json'),
                                           scorer=module.provenance()))
    dump(old / 'evaluation/cases_private.json', old_cases)
    dump(old / 'readout/summary.json', {'official_national': {'monthly': national}})
    monkeypatch.setattr(module, 'OLD_CASES_SHA256', sha(old / 'evaluation/cases_private.json'))
    monkeypatch.setattr(module, 'OLD_READOUT_SHA256', sha(old / 'readout/summary.json'))
    out = root / 'outputs' / 'evaluation'
    result = module.evaluate(inputs, view, out, truth=truth, old_result=old, workers=1)
    summary = json.loads((out / 'summary.json').read_text())
    assert result['person_months'] == 82 and result['new_q9_density_fits'] == 0
    assert summary['official_national']['model']['mae_pp'] == pytest.approx(.5)
    combo = summary['official_national']['chronological_combinations']['mae']
    assert len(combo['fit_months']) == 48 and len(combo['evaluation_months']) == 34
    assert combo['simulation_weight'] == pytest.approx(.5)
    assert combo['evaluation']['mae_pp'] == pytest.approx(0.)
    assert summary['full_wave_center_errors']['q8_point']['mae_pp'] == pytest.approx(.5)
