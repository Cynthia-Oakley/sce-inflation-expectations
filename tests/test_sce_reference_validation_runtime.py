"""Synthetic checks for reference prompts, auditing, scope and dispatch gates."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_sce_reference_validation_trial as runner
from studies.sce_inflation_expectations import reference_validation_runtime as runtime
from studies.sce_inflation_expectations import model as model_module
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
from studies.sce_inflation_expectations.revision_format_runtime import transform as direct_transform


def original(label='low'):
    prior = {'point_pct': 3., 'q9': {f'bin{i}': 10. for i in range(1, 11)}}
    return [{'role': 'user', 'content':
        f"Your score on the survey's numeracy assessment was {label}.\nP/E unchanged\n"
        'Your earlier survey response\n'+json.dumps(prior)+
        '\nQuestion 1 (point estimate): next 12 months\nQuestion 2: same ten ranges\n'
        'Reply with ONLY a JSON object OLD'}]


def make_decision(tmp_path, monkeypatch, kind='scripted', raw=None):
    messages = direct_transform(original(), 'direct')
    bundle = {'parent': {'fixed': True}, 'messages_sha256': {'anon': message_hash(messages)}}
    monkeypatch.setattr(runtime, 'parent_messages', lambda ob, parent: original())
    # Replacing the factory prevents provider creation and credential reads even
    # when testing the openai branch; the supplied chat below is an in-memory fake.
    monkeypatch.setattr(model_module, 'SCEOpenAILLM', lambda **kwargs: SimpleNamespace())
    kwargs = dict(prompt_version=runtime.PROMPT, reference_validation_bundle=bundle,
        llm_kind=kind, model='fake-only', max_calls=1, retry_max=0, max_prompt_chars=30000,
        cost_cap_usd=1, price_input_per_mtok=.3, price_output_per_mtok=1.2,
        run_id='synthetic-no-api', audit_dir=str(tmp_path))
    decision = runtime.ReferenceValidationDecision(**kwargs)
    ob = SimpleNamespace(agent_id='anon', step=1,
        macro_information={'target_month': '2020-03', 'as_of': '2020-03-20T23:59:59-04:00'},
        local_physical={'profile': {'numeracy': 'low'}})
    if kind == 'openai':
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=raw), finish_reason='stop')],
            model='fake-returned', id='fake-request', system_fingerprint=None,
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=8))
        decision.llm = SimpleNamespace(chat=lambda messages: (response, 5.))
    return decision, ob, messages, kwargs


@pytest.mark.parametrize('label', ['high', 'low'])
def test_reference_exactly_preserves_direct_without_extra_blocks(label):
    before = original(label)
    messages = runtime.transform(before)
    assert messages == direct_transform(before, 'direct')
    assert before == original(label)
    for forbidden in ('Your household financial circumstances:', 'Your earlier survey responses:',
                      'point_revision_pp', 'financial experiences', 'QNUM', 'frequency'):
        assert forbidden not in messages[0]['content']


def test_scripted_keeps_all_actual_messages_and_metadata_without_payload_file(tmp_path, monkeypatch):
    decision, ob, messages, _ = make_decision(tmp_path, monkeypatch)
    action = decision._decide_scripted([ob])[0]
    logged = json.loads((tmp_path/'scripted_inputs.jsonl').read_text())
    assert logged['messages'] == messages
    assert logged['new_api_calls'] == decision.call_count == 0
    assert logged['prompt_sha256'] == action.payload['actual_messages_sha256'] == message_hash(messages)
    assert action.payload['reference_validation_arm'] == 'reference'
    assert action.payload['research_line'] == 'A_conditional_returner_reconstruction'
    assert json.loads((tmp_path/'scripted_decisions.jsonl').read_text())['payload'] == action.payload
    assert not (tmp_path/'llm_calls.jsonl').exists()
    assert not any('payload' in path.name for path in tmp_path.iterdir())


def test_bundle_prompt_attempt_and_no_retry_guards(tmp_path, monkeypatch):
    decision, ob, messages, kwargs = make_decision(tmp_path, monkeypatch)
    for extra in ('current_q1_code', 'current_q9', 'userid', 'arm', 'items'):
        bundle = {**kwargs['reference_validation_bundle'], extra: 'forbidden'}
        with pytest.raises(ValueError, match='bundle required'):
            runtime.ReferenceValidationDecision(**{**kwargs, 'reference_validation_bundle': bundle})
    for field, value in [('prompt_version', 'other'), ('retry_max', 1)]:
        with pytest.raises(ValueError):
            runtime.ReferenceValidationDecision(**{**kwargs, field: value})
    bad = deepcopy(kwargs['reference_validation_bundle'])
    bad['messages_sha256']['anon'] = 'not-a-hash'
    with pytest.raises(ValueError, match='roster/hash'):
        runtime.ReferenceValidationDecision(**{**kwargs, 'reference_validation_bundle': bad})
    monkeypatch.setattr(runtime, 'parent_messages', lambda ob, parent: original('high'))
    with pytest.raises(ValueError, match='prompt changed'):
        decision.build_llm_messages(ob)
    for actual, attempt in ((messages, 1), (messages+[{'role': 'user', 'content': 'extra'}], 0)):
        with pytest.raises(ValueError, match='Actual request'):
            decision._call_with_audit(ob, {}, actual, attempt)
    assert decision.call_count == 0


def test_fake_response_is_unmapped_and_error_stops_without_retry(tmp_path, monkeypatch):
    raw = json.dumps({'point_pct': -4.5, 'q9': {f'bin{i}': 10 for i in range(1, 11)}})
    decision, ob, messages, _ = make_decision(tmp_path, monkeypatch, 'openai', raw)
    action = decision._decide_openai_one(ob)
    assert action.payload['point_pct'] == -4.5 and action.payload['validation_status'] == 'valid'
    row = json.loads((tmp_path/'llm_calls.jsonl').read_text())
    assert row['raw_response_text'] == raw and json.loads(row['prompt_text']) == messages
    assert not (tmp_path/'response_mapping.jsonl').exists()
    faildir = tmp_path/'fail'
    faildir.mkdir()
    decision, ob, _, _ = make_decision(faildir, monkeypatch, 'openai')
    def fail(messages):
        raise RuntimeError('synthetic provider failure')
    decision.llm.chat = fail
    with pytest.raises(RuntimeError, match='without automatic retry'):
        decision._decide_openai_one(ob)
    assert decision.call_count == 1
    assert decision.cost_summary()['reserved_cost_usd'] > 0
    assert (faildir/'stopped_decisions.jsonl').exists()


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    root = tmp_path/'repo'
    folder = root/'outputs/reference-validation'
    folder.mkdir(parents=True)
    monkeypatch.setattr(runner, 'ROOT', root)
    monkeypatch.setitem(runner._inherited, 'ROOT', root)
    sources = {}
    for name in ('scripts/run_sce_reference_validation_trial.py',
                 'scripts/run_sce_household_finance_trial.py', 'scripts/export_study_runtime.py',
                 'studies/sce_inflation_expectations/reference_validation_runtime.py'):
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('synthetic source')
        sources[name] = runner.sha(path)
    protocol = {'id': runner.PROTOCOL_ID, 'research_line': 'A_conditional_returner_reconstruction',
        'months': list(runner.MONTHS), 'n_per_month': 192, 'arms': ['reference'],
        'generation_repeats': [1, 2], 'model': 'deepseek-flash', 'temperature': .5,
        'max_tokens': 1024, 'retry_max': 0, 'thinking': 'disabled', 'planned_calls': 4608,
        'price_input_per_mtok': .3, 'price_output_per_mtok': 1.2, 'budget_cap_usd': 30}
    runner.dump(folder/'protocol.json', protocol)
    jobs = []
    for month in runner.MONTHS:
        dest = folder/str(month)
        dest.mkdir()
        runner.dump(dest/'population.json', {'personas': [{'agent_id': f'anon-{i}'} for i in range(192)]})
        for name in ('environment.json', 'simulation_reference.json', 'preview_reference.json'):
            runner.dump(dest/name, {})
        for repeat in (1, 2):
            jobs.append({'month': month, 'arm': 'reference', 'repeat': repeat, 'cap_usd': 1.,
                         'run_id': f'reference-validation-{month}-r{repeat}'})
    manifest = {'source_sha256': sources, 'prepared_file_sha256': {}, 'jobs': jobs,
                'planned_calls': 4608, 'proposed_cap_usd': 30}
    freeze(folder, manifest)
    return root, folder, manifest


def freeze(folder, manifest):
    manifest['protocol_sha256'] = runner.sha(folder/'protocol.json')
    manifest['prepared_file_sha256'] = {str(path.relative_to(folder)): runner.sha(path)
        for path in folder.rglob('*.json') if path.name != 'manifest.json'}
    runner.dump(folder/'manifest.json', manifest)


@pytest.mark.parametrize('key,value', [
    ('id', 'old'), ('months', [202003]), ('n_per_month', 48), ('arms', ['baseline']),
    ('generation_repeats', [1]), ('planned_calls', 768), ('model', 'other'),
    ('temperature', .7), ('max_tokens', 2048), ('retry_max', 1), ('thinking', 'enabled'),
    ('price_input_per_mtok', .1), ('price_output_per_mtok', 1.3), ('budget_cap_usd', 40),
])
def test_reference_frozen_scope_and_settings(prepared, key, value):
    _, folder, manifest = prepared
    assert runner.verify(folder) == manifest
    protocol = json.loads((folder/'protocol.json').read_text())
    protocol[key] = value
    runner.dump(folder/'protocol.json', protocol)
    freeze(folder, manifest)
    with pytest.raises(ValueError):
        runner.verify(folder)


def test_reference_cells_hashes_rosters_and_dependencies(prepared):
    root, folder, manifest = prepared
    changed = deepcopy(manifest)
    changed['jobs'][0]['repeat'] = 2
    runner.dump(folder/'manifest.json', changed)
    with pytest.raises(ValueError, match='24 unique'):
        runner.verify(folder)
    runner.dump(folder/'manifest.json', manifest)
    source = root/'scripts/run_sce_household_finance_trial.py'
    source.write_text('changed source')
    with pytest.raises(ValueError, match='source changed'):
        runner.verify(folder)
    source.write_text('synthetic source')
    pop = folder/f'{runner.MONTHS[0]}/population.json'
    value = json.loads(pop.read_text())
    value['personas'].pop()
    runner.dump(pop, value)
    with pytest.raises(ValueError, match='prepared input changed'):
        runner.verify(folder)
    freeze(folder, manifest)
    with pytest.raises(ValueError, match='192 distinct'):
        runner.verify(folder)


def test_reference_dispatch_reuses_new_entry_and_blocks_unapproved_real_run(prepared, monkeypatch):
    _, folder, _ = prepared
    assert runner._inherited['verify'] is runner.verify
    assert runner._inherited['worker'] is runner.worker
    calls = []
    def fake_process(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    monkeypatch.setattr(runner._inherited['subprocess'], 'run', fake_process)
    with pytest.raises(FileNotFoundError, match='authorization.json'):
        runner.dispatch(folder, False, 1)
    assert calls == []
    runner.dispatch(folder, True, 1)
    children = [command for command in calls if 'worker' in command]
    assert len(children) == 24
    assert all(Path(command[2]).name == 'run_sce_reference_validation_trial.py'
               and '--scripted' in command for command in children)
    checks = json.loads((folder/'engineering_checks.json').read_text())
    assert {row['job_index'] for row in checks} == set(range(24))
    assert not (folder/'authorization.json').exists()


def test_reference_existing_job_no_resume_and_worker_failure_stops_unsent(prepared, monkeypatch):
    root, folder, manifest = prepared
    calls = []
    def fake_process(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=int('worker' in command), stdout='', stderr='')
    monkeypatch.setattr(runner._inherited['subprocess'], 'run', fake_process)
    existing = root/'outputs/local_runs'/(manifest['jobs'][0]['run_id']+'-engineering')
    existing.mkdir(parents=True)
    with pytest.raises(ValueError, match='no automatic rerun/resume'):
        runner.dispatch(folder, True, 1)
    assert not any('worker' in command for command in calls)
    existing.rmdir()
    with pytest.raises(RuntimeError, match='no automatic retry'):
        runner.dispatch(folder, True, 1)
    assert sum('worker' in command for command in calls) == 1


def test_reference_authorization_still_requires_all_24_zero_api_receipts(prepared, monkeypatch):
    _, folder, manifest = prepared
    original_read = Path.read_text
    auth = {'approved': True, 'protocol_sha256': manifest['protocol_sha256'],
            'cap_usd': manifest['proposed_cap_usd'], 'planned_calls': 4608}
    def read(path, *args, **kwargs):
        return json.dumps(auth) if path == folder/'authorization.json' else original_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', read)
    runner.dump(folder/'engineering_checks.json', [])
    with pytest.raises(ValueError, match='all offline cells'):
        runner.authorization_gate(folder, manifest)
    auth['planned_calls'] = 768
    with pytest.raises(ValueError, match='specific matching'):
        runner.authorization_gate(folder, manifest)
