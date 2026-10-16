"""Synthetic completed-run evidence only; these tests never call an API."""
import importlib.util
import json
from pathlib import Path
import shutil

import duckdb
import numpy as np
import pytest

from studies.sce_inflation_expectations.evaluation import household_finance as finance
from studies.sce_inflation_expectations.household_finance_input import render_household_finance_block
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
from studies.sce_inflation_expectations.revision_format_runtime import REPLY_MARKER

_spec = importlib.util.spec_from_file_location('synthetic_cognition_fixture', Path(__file__).with_name('test_sce_cognition_evaluation.py'))
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)


def _dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _json(path):
    return json.loads(path.read_text())


def _repin(folder):
    manifest = _json(folder / 'manifest.json')
    manifest['protocol_sha256'] = finance.sha(folder / 'protocol.json')
    manifest['prepared_file_sha256'] = {
        str(path.relative_to(folder)): finance.sha(path)
        for path in folder.rglob('*.json') if path.name != 'manifest.json'
    }
    _dump(folder / 'manifest.json', manifest)


def _convert_trial(root, folder):
    """Reuse generic raw/DuckDB fixture generation, never its evaluator globals."""
    parent = root / 'outputs' / 'parent'
    parent.mkdir()
    shutil.copyfile(folder / 'evaluation_links_private.json', parent / 'evaluation_links_private.json')
    protocol = _json(folder / 'protocol.json')
    protocol.update(id='sce-household-finance-pilot-v1', research_line=finance.RESEARCH_LINE, arms=list(finance.ARMS),
                    primary_metric=finance.PRIMARY_METRIC, primary_contrast='financial_facts minus baseline',
                    model='deepseek-flash', temperature=.5, max_tokens=1024, thinking='disabled', retry_max=0,
                    secondary_contrasts=['financial_perspective minus financial_facts', 'financial_perspective minus baseline'])
    _dump(folder / 'protocol.json', protocol)
    mapping = dict(zip(('label_only', 'question_answer', 'faithful_paraphrase'), finance.ARMS))
    source_hash = finance.sha(root / 'outputs/truth.json')
    for month in finance.MONTHS:
        dest = folder / str(month)
        (parent / str(month)).mkdir()
        baseline = _json(dest / 'preview_label_only.json')
        _dump(parent / str(month) / 'preview_label_only.json', baseline)
        records = {}
        for index, row in enumerate(baseline):
            code = 2 if index < 6 else 3 if index < 18 else 4
            records[row['agent_id']] = {
                'schema_version': 'sce_household_finance_input_v1', 'research_line': finance.RESEARCH_LINE,
                'target_month': month, 'current_q1_code': code, 'current_q1_source_month': month,
                'previous_q1_code': 3, 'previous_q1_source_month': finance._previous_month(month),
                'current_source_sha256': source_hash, 'previous_source_sha256': source_hash,
            }
        _dump(dest / 'household_finance_payloads.json', records)
        for name in ('population', 'environment'):
            _dump(dest / f'{name}.json', {'synthetic': True})
        for arm in finance.ARMS:
            previews = []
            for row in baseline:
                block = render_household_finance_block(arm, records[row['agent_id']])
                messages = [{'role': 'user', 'content': row['messages'][0]['content'].replace(REPLY_MARKER, block + REPLY_MARKER, 1)}]
                previews.append({'agent_id': row['agent_id'], 'messages': messages, 'prompt_sha256': message_hash(messages)})
            _dump(dest / f'preview_{arm}.json', previews)
            _dump(dest / f'simulation_{arm}.json', {
                'decision_ref': finance.REF, 'decision_args': {
                    'household_finance_bundle': {'arm': arm},
                    'household_finance_payloads_sha256': finance.sha(dest / 'household_finance_payloads.json'),
                },
            })
        for old in mapping:
            (dest / f'preview_{old}.json').unlink()
    manifest = _json(folder / 'manifest.json')
    for path in parent.rglob('*.json'):
        manifest['source_sha256'][str(path.relative_to(root))] = finance.sha(path)
    for job in manifest['jobs']:
        job['arm'] = mapping[job['arm']]
        run = root / 'outputs/local_runs' / job['run_id']
        dest = folder / str(job['month'])
        preview_file = dest / f"preview_{job['arm']}.json"
        previews = {row['agent_id']: row for row in _json(preview_file)}
        payload_hash = finance.sha(dest / 'household_finance_payloads.json')
        run_manifest = _json(run / 'run_manifest.json')
        run_manifest.update(arm=job['arm'], protocol_sha256=finance.sha(folder / 'protocol.json'),
                            household_finance_payloads_sha256=payload_hash,
                            new_api_calls=24, actual_input_hashes_match=True)
        _dump(run / 'run_manifest.json', run_manifest)
        shutil.copyfile(preview_file, run / 'frozen_preview.json')
        shutil.copyfile(dest / 'household_finance_payloads.json', run / 'household_finance_payloads.json')
        calls = [json.loads(line) for line in (run / 'llm_calls.jsonl').read_text().splitlines()]
        for call in calls:
            preview = previews[call['agent_id']]
            call.update(prompt_sha256=preview['prompt_sha256'], prompt_text=json.dumps(preview['messages'], ensure_ascii=False),
                        requested_model='deepseek-flash', temperature=.5, max_tokens=1024,
                        extra_body={'thinking': {'type': 'disabled'}}, prompt_version='sce-q8-q9-household-finance-v1')
        (run / 'llm_calls.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in calls))
        db = duckdb.connect(str(run / 'study.duckdb'))
        for agent_id, raw in db.execute('SELECT agent_id, action_payload FROM panel').fetchall():
            action = json.loads(raw)
            action.pop('cognition_arm')
            action.update(household_finance_arm=job['arm'], household_finance_payloads_sha256=payload_hash,
                          research_line=finance.RESEARCH_LINE, actual_messages_sha256=previews[agent_id]['prompt_sha256'])
            db.execute('UPDATE panel SET action_payload=? WHERE agent_id=?', [json.dumps(action), agent_id])
        db.close()
    _dump(folder / 'manifest.json', manifest)
    _repin(folder)
    return parent


@pytest.fixture(scope='module')
def template(tmp_path_factory):
    root = tmp_path_factory.mktemp('finance-fixture') / 'repository'
    _, folder = _fixture._build_trial(root, root / 'outputs/prepared')
    _convert_trial(root, folder)
    return root


@pytest.fixture
def trial(template, tmp_path, monkeypatch):
    root = tmp_path / 'repository'
    shutil.copytree(template, root)
    monkeypatch.setattr(finance, 'ROOT', root)
    monkeypatch.setattr(finance, 'PARENT', root / 'outputs/parent')
    monkeypatch.setattr(finance, 'TRUTH', root / 'outputs/truth.json')
    monkeypatch.setattr(finance, 'REFERENCE', root / 'outputs/reference.parquet')
    return root, root / 'outputs/prepared'


def test_complete_synthetic_evidence_and_exploratory_mean_metric(trial):
    root, folder = trial
    summary = finance.evaluate(folder, root / 'outputs/evaluation', draws=1000)
    assert summary['evaluation_api_calls'] == 0
    assert summary['raw_replies_reconstructed_and_matched'] == 576
    assert summary['common_support']['q9_common_scorable_person_months'] == 96
    assert summary['primary_metric'] == 'individual_density_mean_mae_pp'
    assert summary['primary_contrast'] == 'financial_facts minus baseline'
    assert summary['individual_update_mae_identity']['independent_evidence'] is False
    assert len(summary['paired_contrasts']) == 3
    assert all(item['draws_used'] == 1000 for item in summary['paired_contrasts'].values())
    assert summary['financial_group_descriptions']['aggregate_over_reportable_equal_month_repeat_cells']['worse_minus_same']['cells_reported'] == 8
    assert (root / 'outputs/evaluation/cases_private.json').is_file()
    assert 'userid' not in json.dumps(summary)


@pytest.mark.parametrize('artifact', ['raw_reply', 'action', 'run_manifest', 'run_payload', 'frozen_preview', 'request_model'])
def test_completed_evidence_tampering_is_rejected(trial, artifact):
    root, folder = trial
    job = _json(folder / 'manifest.json')['jobs'][0]
    run = root / 'outputs/local_runs' / job['run_id']
    if artifact in ('raw_reply', 'request_model'):
        path = run / 'llm_calls.jsonl'
        calls = [json.loads(line) for line in path.read_text().splitlines()]
        if artifact == 'raw_reply':
            calls[0]['raw_response_text'] += ' changed'
        else:
            calls[0]['requested_model'] = 'different-model'
        path.write_text(''.join(json.dumps(row) + '\n' for row in calls))
    elif artifact == 'action':
        db = duckdb.connect(str(run / 'study.duckdb'))
        agent, raw = db.execute('SELECT agent_id, action_payload FROM panel LIMIT 1').fetchone()
        payload = json.loads(raw)
        payload['point_pct'] += 7
        db.execute('UPDATE panel SET action_payload=? WHERE agent_id=?', [json.dumps(payload), agent])
        db.close()
    elif artifact == 'run_manifest':
        path = run / 'run_manifest.json'
        data = _json(path); data['cost']['call_count'] = 25; _dump(path, data)
    else:
        path = run / ('household_finance_payloads.json' if artifact == 'run_payload' else 'frozen_preview.json')
        path.write_text(path.read_text() + ' ')
    with pytest.raises(ValueError):
        finance.load(folder)


def test_payload_time_error_rejected_even_when_prepared_hash_repinned(trial):
    _, folder = trial
    path = folder / '202004/household_finance_payloads.json'
    records = _json(path)
    next(iter(records.values()))['previous_q1_source_month'] = 202004
    _dump(path, records); _repin(folder)
    with pytest.raises(ValueError, match='Q1 code/time/source-hash'):
        finance.load(folder)


def test_preview_drift_rejected_even_when_prepared_hash_repinned(trial):
    _, folder = trial
    path = folder / '202004/preview_financial_facts.json'
    rows = _json(path)
    rows[0]['messages'][0]['content'] = rows[0]['messages'][0]['content'].replace('future 12-month', 'future 24-month')
    rows[0]['prompt_sha256'] = message_hash(rows[0]['messages'])
    _dump(path, rows); _repin(folder)
    with pytest.raises(ValueError, match='Exact registered financial insertion'):
        finance.load(folder)


def test_invalid_calls_keep_assigned_counts_and_fail_gate(trial):
    root, folder = trial
    _fixture._patch_one_call_invalid(folder, root)
    summary = finance.evaluate(folder, root / 'outputs/invalid', draws=20)
    assert summary['coverage']['baseline']['planned'] == 192
    assert summary['coverage']['baseline']['valid_n'] == 190
    assert summary['common_support']['q9_common_scorable_person_months'] == 94
    assert summary['common_support']['q8_common_person_months'] == 94
    assert summary['primary_continuation_gate']['pilot_continuation_gate_passed'] is False
    assert summary['paired_contrasts']['financial_facts_minus_baseline']['interval_95_unadjusted_pp'] is None


def test_sparse_group_suppresses_gap_only_and_update_mae_identity(trial):
    _, folder = trial
    loaded = finance.load(folder)
    cases = loaded['cases']
    support = finance._common_person_months(cases, [1, 2], 'q9')
    for row in cases:
        if row['current_q1_code'] == 4 and row['userid'] % 24 != 0:
            row['financial_group'] = 'same'
        previous = row['real']['previous_q9_mean']
        for arm in finance.ARMS:
            current = row['arms'][arm]['mean']
            real = row['real']['q9_mean']
            assert abs((current - previous) - (real - previous)) == pytest.approx(abs(current - real))
    grouped = finance._financial_group_descriptions(cases, loaded['months'], loaded['repeats'], support)
    assert len(support) == 96
    assert all(cell['contrasts']['better_minus_same']['reported'] is False for cell in grouped['cells'])
    assert all(cell['contrasts']['worse_minus_same']['reported'] is True for cell in grouped['cells'])


def test_bootstrap_uses_mean_mae_equal_cells_and_person_clusters():
    cases = []
    for month, people, delta in ((202004, [1, 2], 1), (202105, [1, 2, 3, 4], 3)):
        for repeat in (1, 2):
            for person in people:
                cases.append({'month': month, 'repeat': repeat, 'userid': person,
                              'real': {'q9_mean': 0},
                              'arms': {'baseline': {'mean': 10}, 'financial_facts': {'mean': 10 - delta},
                                       'financial_perspective': {'mean': 10 - 2 * delta}}})
    support = {(row['month'], row['userid']) for row in cases}
    intervals = finance._paired_cluster_bootstrap(cases, [202004, 202105], [1, 2], support, 1000, 7)
    assert intervals['financial_facts_minus_baseline']['interval_95_unadjusted_pp'] == pytest.approx([-2, -2])
    assert intervals['financial_perspective_minus_baseline']['interval_95_unadjusted_pp'] == pytest.approx([-4, -4])
    assert intervals == finance._paired_cluster_bootstrap(cases, [202004, 202105], [1, 2], support, 1000, 7)
    assert intervals['financial_facts_minus_baseline']['empty_cell_draws'] > 0


@pytest.mark.parametrize('failure', ['coverage', 'cells', 'primary_interval', 'center', 'w1', 'draws'])
def test_continuation_gate_requires_every_registered_guardrail(failure):
    comparison = {'interval_95_unadjusted_pp': [-2, -1], 'draws_requested': 1000, 'draws_used': 1000,
                  'other_metric_point_changes': {'q9_center_mae_pp': 0, 'cross_section_w1_pp': 0}}
    if failure == 'draws':
        comparison['draws_used'] = 999
    if failure == 'primary_interval':
        comparison['interval_95_unadjusted_pp'] = [-2, 0]
    if failure == 'center':
        comparison['other_metric_point_changes']['q9_center_mae_pp'] = .001
    if failure == 'w1':
        comparison['other_metric_point_changes']['cross_section_w1_pp'] = .001
    gate = finance._pilot_gates({'financial_facts_minus_baseline': comparison},
                                failure != 'coverage', failure != 'cells')
    assert gate['financial_facts_minus_baseline']['pilot_continuation_gate_passed'] is False


def test_repeated_generations_do_not_narrow_bootstrap_as_new_people():
    cases = []
    for month in (202004, 202105):
        for repeat in (1, 2):
            for person in (1, 2):
                cases.append({'month': month, 'repeat': repeat, 'userid': person,
                              'real': {'q9_mean': 0},
                              'arms': {'baseline': {'mean': 4 if person == 2 else 0},
                                       'financial_facts': {'mean': 2 if person == 2 else 0},
                                       'financial_perspective': {'mean': 1 if person == 2 else 0}}})
    support = {(row['month'], row['userid']) for row in cases}
    result = finance._paired_cluster_bootstrap(cases, [202004, 202105], [1, 2], support, 1000, 17)
    # Each draw samples two real people once and carries their four records.
    # Sampling person 1 twice gives 0; sampling person 2 twice gives -2.
    assert result['financial_facts_minus_baseline']['interval_95_unadjusted_pp'] == [-2, 0]


def test_human_missingness_is_reported_separately_from_model_failures(trial):
    _, folder = trial
    loaded = finance.load(folder)
    cases = loaded['cases']
    for row in cases:
        if row['month'] == 202004 and row['agent_id'] == 'person000':
            row['real']['q9_mean'] = None
    support = finance._common_person_months(cases, [1, 2], 'q9')
    missingness = finance._support_missingness(cases, [1, 2], support, set())
    assert len(support) == 95
    assert missingness['human_q9_missing_or_unscorable_person_months'] == 1
    assert missingness['any_model_q9_invalid_or_unscorable_person_months'] == 0


def test_continuation_screen_can_pass_with_all_guardrails_satisfied():
    comparison = {'interval_95_unadjusted_pp': [-2, -1], 'draws_requested': 1000, 'draws_used': 1000,
                  'other_metric_point_changes': {'q9_center_mae_pp': 0, 'cross_section_w1_pp': -.1}}
    gate = finance._pilot_gates({'financial_facts_minus_baseline': comparison}, True, True)
    assert gate['financial_facts_minus_baseline']['pilot_continuation_gate_passed'] is True
