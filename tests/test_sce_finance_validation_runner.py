"""Synthetic-only checks for the isolated cross-month runner and its gates."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_sce_finance_validation_trial as runner


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    root = tmp_path/'repo'
    folder = root/'outputs/new-validation'
    folder.mkdir(parents=True)
    monkeypatch.setattr(runner, 'ROOT', root)
    monkeypatch.setitem(runner._inherited, 'ROOT', root)
    sources = {}
    for name in ('scripts/run_sce_finance_validation_trial.py',
                 'scripts/run_sce_household_finance_trial.py', 'scripts/export_study_runtime.py'):
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('synthetic source: '+name)
        sources[name] = runner.sha(path)
    protocol = {'id': runner.PROTOCOL_ID, 'research_line': 'A_conditional_returner_reconstruction',
        'months': list(runner.MONTHS), 'n_per_month': 48, 'arms': list(runner.ARMS),
        'generation_repeats': [1, 2], 'model': 'deepseek-flash', 'temperature': .5,
        'max_tokens': 1024, 'retry_max': 0, 'thinking': 'disabled', 'planned_calls': 768,
        'price_input_per_mtok': .3, 'price_output_per_mtok': 1.2, 'budget_cap_usd': 20}
    runner.dump(folder/'protocol.json', protocol)
    jobs = []
    for month in runner.MONTHS:
        dest = folder/str(month)
        dest.mkdir()
        runner.dump(dest/'population.json', {'personas': [{'agent_id': f'anon-{i}'} for i in range(48)]})
        for name in ('environment.json', 'household_finance_payloads.json',
                     *(f'simulation_{arm}.json' for arm in runner.ARMS),
                     *(f'preview_{arm}.json' for arm in runner.ARMS)):
            runner.dump(dest/name, {})
        for arm in runner.ARMS:
            for repeat in (1, 2):
                jobs.append({'month': month, 'arm': arm, 'repeat': repeat,
                    'cap_usd': 1., 'run_id': f'new-validation-{month}-{arm}-r{repeat}'})
    manifest = {'source_sha256': sources, 'prepared_file_sha256': {}, 'jobs': jobs,
                'planned_calls': 768, 'proposed_cap_usd': 20}
    freeze(folder, manifest)
    return root, folder, manifest


def freeze(folder, manifest):
    manifest['protocol_sha256'] = runner.sha(folder/'protocol.json')
    manifest['prepared_file_sha256'] = {str(path.relative_to(folder)): runner.sha(path)
        for path in folder.rglob('*.json') if path.name != 'manifest.json'}
    runner.dump(folder/'manifest.json', manifest)


def test_isolated_inheritance_binds_new_verifier_and_child_entry(prepared):
    _, folder, manifest = prepared
    assert runner.worker.__globals__ is runner.dispatch.__globals__ is runner._inherited
    assert runner._inherited['verify'] is runner.verify
    assert Path(runner._inherited['__file__']).name == 'run_sce_finance_validation_trial.py'
    assert runner.verify(folder) == manifest
    assert not (folder/'authorization.json').exists()


@pytest.mark.parametrize('key,value', [
    ('id', 'sce-household-finance-pilot-v1'), ('research_line', 'B'),
    ('months', [202206, 202306, 202410, 202510]), ('n_per_month', 24),
    ('arms', ['baseline', 'financial_perspective']), ('generation_repeats', [1]),
    ('planned_calls', 576), ('price_input_per_mtok', .1), ('price_output_per_mtok', 1.3),
    ('model', 'other'), ('temperature', .7), ('max_tokens', 2048), ('retry_max', 1),
    ('thinking', 'enabled'), ('budget_cap_usd', 30), ('protocol_id', 'wrong'), ('repeats', [1]),
])
def test_frozen_crossmonth_scope_is_required_even_after_rehash(prepared, key, value):
    _, folder, manifest = prepared
    protocol = json.loads((folder/'protocol.json').read_text())
    protocol[key] = value
    runner.dump(folder/'protocol.json', protocol)
    freeze(folder, manifest)
    with pytest.raises(ValueError):
        runner.verify(folder)


@pytest.mark.parametrize('mutation', ['duplicate', 'missing', 'extra', 'month', 'repeat'])
def test_exactly_sixteen_unique_cells_required(prepared, mutation):
    _, folder, manifest = prepared
    if mutation == 'duplicate':
        manifest['jobs'][0].update({k: manifest['jobs'][1][k] for k in ('month', 'arm', 'repeat')})
    elif mutation == 'missing':
        manifest['jobs'].pop()
    elif mutation == 'extra':
        manifest['jobs'].append({**manifest['jobs'][0], 'run_id': 'extra-cell'})
    elif mutation == 'month':
        manifest['jobs'][0]['month'] = 202205
    else:
        manifest['jobs'][0]['repeat'] = True
    runner.dump(folder/'manifest.json', manifest)
    with pytest.raises(ValueError, match='16 unique'):
        runner.verify(folder)


def test_hashes_input_rosters_and_frozen_dependencies_are_enforced(prepared):
    root, folder, manifest = prepared
    source = root/'scripts/run_sce_household_finance_trial.py'
    original = source.read_text()
    source.write_text(original+' changed')
    with pytest.raises(ValueError, match='source changed'):
        runner.verify(folder)
    source.write_text(original)
    pop = folder/f'{runner.MONTHS[0]}/population.json'
    original_pop = pop.read_text()
    pop.write_text('{}')
    with pytest.raises(ValueError, match='prepared input changed'):
        runner.verify(folder)
    pop.write_text(original_pop)
    value = json.loads(original_pop)
    value['personas'][0] = value['personas'][1]
    runner.dump(pop, value)
    freeze(folder, manifest)
    with pytest.raises(ValueError, match='48 distinct'):
        runner.verify(folder)
    pop.write_text(original_pop)
    freeze(folder, manifest)
    del manifest['source_sha256']['scripts/run_sce_household_finance_trial.py']
    runner.dump(folder/'manifest.json', manifest)
    with pytest.raises(ValueError, match='Both runner sources'):
        runner.verify(folder)


def test_unfrozen_preview_is_rejected(prepared):
    _, folder, manifest = prepared
    del manifest['prepared_file_sha256'][f'{runner.MONTHS[0]}/preview_baseline.json']
    runner.dump(folder/'manifest.json', manifest)
    with pytest.raises(ValueError, match='runtime inputs and previews'):
        runner.verify(folder)


def fake_processes(monkeypatch, *, fail_worker=False):
    calls = []
    def invoke(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=int(fail_worker and 'worker' in command), stdout='', stderr='')
    monkeypatch.setattr(runner._inherited['subprocess'], 'run', invoke)
    return calls


def test_real_run_blocks_before_export_or_credentials_without_authorization(prepared, monkeypatch):
    _, folder, _ = prepared
    calls = fake_processes(monkeypatch)
    with pytest.raises(FileNotFoundError, match='authorization.json'):
        runner.dispatch(folder, False, 1)
    assert calls == []
    assert not (folder/'real_dispatch.json').exists()


def test_dry_dispatch_uses_new_entry_for_all_sixteen_cells(prepared, monkeypatch):
    _, folder, _ = prepared
    calls = fake_processes(monkeypatch)
    runner.dispatch(folder, True, 1)
    children = [command for command in calls if 'worker' in command]
    assert len(children) == 16
    assert all(Path(command[2]).name == 'run_sce_finance_validation_trial.py'
               and '--scripted' in command for command in children)
    checks = json.loads((folder/'engineering_checks.json').read_text())
    assert {row['job_index'] for row in checks} == set(range(16))
    assert all(row['exit_code'] == 0 for row in checks)
    assert not (folder/'authorization.json').exists()


def test_existing_jobs_never_auto_resume_and_failure_stops_unsent_jobs(prepared, monkeypatch):
    root, folder, manifest = prepared
    calls = fake_processes(monkeypatch, fail_worker=True)
    existing = root/'outputs/local_runs'/(manifest['jobs'][0]['run_id']+'-engineering')
    existing.mkdir(parents=True)
    with pytest.raises(ValueError, match='no automatic rerun/resume'):
        runner.dispatch(folder, True, 1)
    assert not any('worker' in command for command in calls)
    existing.rmdir()
    with pytest.raises(RuntimeError, match='no automatic retry'):
        runner.dispatch(folder, True, 1)
    assert sum('worker' in command for command in calls) == 1
    checks = json.loads((folder/'engineering_checks.json').read_text())
    assert len(checks) == 1 and checks[0]['exit_code'] == 1


def test_authorization_requires_sixteen_matching_zero_api_receipts_before_credentials(prepared, monkeypatch):
    root, folder, manifest = prepared
    # Supply synthetic authorization through an in-memory read; never create an
    # authorization.json file, even in this temporary fixture.
    original_read = Path.read_text
    auth = {'approved': True, 'protocol_sha256': manifest['protocol_sha256'],
            'cap_usd': manifest['proposed_cap_usd'], 'planned_calls': 768}
    def read(path, *args, **kwargs):
        return json.dumps(auth) if path == folder/'authorization.json' else original_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', read)
    runner.dump(folder/'engineering_checks.json', [])
    with pytest.raises(ValueError, match='all offline cells'):
        runner.authorization_gate(folder, manifest)
    checks = []
    for index, job in enumerate(manifest['jobs']):
        audit = root/'outputs/local_runs'/(job['run_id']+'-engineering')
        audit.mkdir(parents=True)
        runner.dump(audit/'run_manifest.json', {
            'protocol_sha256': manifest['protocol_sha256'], 'status': 'completed',
            'llm_kind': 'scripted', 'cost': {'call_count': 0}, 'actual_input_hashes_match': True})
        checks.append({'job_index': index, 'run_id': job['run_id'], 'exit_code': 0})
    runner.dump(folder/'engineering_checks.json', checks)
    # Stop at the credential stage after proving all receipts are accepted.
    from studies.sce_inflation_expectations import news_label_trial
    def credential_boundary(path):
        raise RuntimeError('synthetic credential boundary reached')
    monkeypatch.setattr(news_label_trial, 'dotenv_values', credential_boundary)
    with pytest.raises(RuntimeError, match='credential boundary'):
        runner.authorization_gate(folder, manifest)
    bad_receipt = root/'outputs/local_runs'/(manifest['jobs'][-1]['run_id']+'-engineering')/'run_manifest.json'
    value = json.loads(bad_receipt.read_text())
    value['cost']['call_count'] = 1
    runner.dump(bad_receipt, value)
    with pytest.raises(ValueError, match='verified zero-API'):
        runner.authorization_gate(folder, manifest)
    auth['planned_calls'] = 576
    with pytest.raises(ValueError, match='specific matching'):
        runner.authorization_gate(folder, manifest)
