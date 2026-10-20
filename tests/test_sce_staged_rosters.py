from copy import deepcopy
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT/'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments import staged_rosters as stages
from studies.sce_inflation_expectations.experiments.procurement_qwen import segments, ordered_ids


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


def protocol():
    return {'months': [202206], 'n_per_month': 3, 'arms': ['a'], 'generation_repeats': [1, 2],
            'roster_segments': {'202206': [{'name': 'gate', 'n': 1, 'phase': 'gate'},
                                          {'name': 'remainder', 'n': 2, 'phase': 'main'}]}}


def test_gate_count_included_not_added_to_total():
    months = [202009, 202109, 202206, 202312, 202410, 202503]
    total = sum(s['n']*3*2 for m in months for s in segments(m))
    gate = sum(s['n']*3*2 for m in months for s in segments(m) if s['phase']=='gate')
    assert total == 3456 and gate == 144 and total-gate == 3312


def test_selection_does_not_depend_on_roster_order():
    assert ordered_ids(['x', 'y', 'z'], 202206) == ordered_ids(['z', 'x', 'y'], 202206)


def test_segment_count_and_old_default():
    p = protocol(); assert sum(stages.expected_cells(p).values()) == 4
    assert stages.job_n(p, {'month': 202206, 'segment': 'gate'}) == 1
    assert stages.job_n({'n_per_month': 96}, {}) == 96
    q = deepcopy(p); q['roster_segments']['202206'][0]['n'] = 2
    with pytest.raises(ValueError, match='sum'):
        stages.expected_cells(q)


def test_duplicate_people_or_changed_prompts_rejected(tmp_path):
    p = protocol(); folder = tmp_path/'202206'
    people = [{'agent_id': x} for x in ['x', 'y', 'z']]
    messages = {r['agent_id']: {'messages': [{'role': 'user', 'content': r['agent_id']}]} for r in people}
    write(folder/'population.json', {'personas': people})
    write(folder/'prompts_a.json', {'rows': messages})
    for name, rows in [('gate', people[:1]), ('remainder', people[1:])]:
        write(folder/name/'population.json', {'personas': rows})
        write(folder/name/'prompts_a.json', {'rows': {r['agent_id']: messages[r['agent_id']] for r in rows}})
    stages.verify_segments(tmp_path, p, [])
    write(folder/'remainder/population.json', {'personas': people[:2]})
    with pytest.raises(ValueError, match='duplicated'):
        stages.verify_segments(tmp_path, p, [])
    write(folder/'remainder/population.json', {'personas': people[1:]})
    changed = deepcopy(messages['y']); changed['messages'][0]['content'] = 'changed'
    write(folder/'remainder/prompts_a.json', {'rows': {'y': changed, 'z': messages['z']}})
    with pytest.raises(ValueError, match='exactly'):
        stages.verify_segments(tmp_path, p, [])


def test_technical_gate_reads_no_truth_and_rejects_wrong_sum(tmp_path):
    p = protocol(); p.update(model='qwen/qwen-2.5-72b-instruct', temperature=.5, max_tokens=1024,
        request_extra_body={'provider': 'locked'}, technical_gate={'planned_calls': 1, 'minimum_valid_fraction': .99})
    job = {'run_id': 'test', 'month': 202206, 'arm': 'a', 'repeat': 1, 'segment': 'gate', 'phase': 'gate'}
    m = {'jobs': [job], 'protocol_sha256': 'hash'}
    audit = tmp_path/'outputs/local_runs/test'
    write(audit/'run_manifest.json', {'status': 'completed', 'llm_kind': 'openai',
        'protocol_sha256': 'hash', 'cost': {'call_count': 1}})
    write(tmp_path/'202206/gate/prompts_a.json', {'rows': {'x': {'prompt_sha256': 'p'}}})
    obj = {'point_pct': 3, 'q9': {f'bin{i}': 10 for i in range(1,11)}}
    call = {'agent_id': 'x', 'error': None, 'returned_model': p['model'], 'returned_provider': 'DeepInfra',
        'attempt_idx': 0, 'extra_body': p['request_extra_body'], 'temperature': .5, 'max_tokens': 1024,
        'prompt_sha256': 'p', 'finish_reason': 'stop', 'raw_response_text': json.dumps(obj)}
    def save(): (audit/'llm_calls.jsonl').write_text(json.dumps(call)+'\n')
    save(); assert stages.technical_gate(tmp_path, m, p, tmp_path)['passed']
    obj['q9']['bin1'] = 11; call['raw_response_text'] = json.dumps(obj); save()
    assert not stages.technical_gate(tmp_path, m, p, tmp_path)['passed']
    assert obj['q9']['bin1'] == 11  # no repair
    call['returned_provider'] = 'unapproved'; save()
    with pytest.raises(ValueError, match='transport'):
        stages.technical_gate(tmp_path, m, p, tmp_path)


def test_main_worker_cannot_bypass_gate(tmp_path, monkeypatch):
    from studies.sce_inflation_expectations.experiments import frozen_batch as batch
    monkeypatch.setattr(batch, 'verify', lambda p: ({'jobs': [{'phase': 'main', 'run_id': 'pending'}]}, {}))
    monkeypatch.setattr(batch, 'authorize', lambda *args: None)
    monkeypatch.setattr(batch, 'technical_gate', lambda *args: {'passed': False})
    with pytest.raises(ValueError, match='cannot bypass'):
        batch.worker(tmp_path, 0, False)


def test_staged_live_dispatch_requires_explicit_phase(tmp_path, monkeypatch):
    from studies.sce_inflation_expectations.experiments import frozen_batch as batch
    monkeypatch.setattr(batch, 'verify', lambda p: ({'jobs': []}, {'roster_segments': {}}))
    monkeypatch.setattr(batch, 'authorize', lambda *args: None)
    with pytest.raises(ValueError, match='explicit gate or main'):
        batch.dispatch(tmp_path, False, 1)
