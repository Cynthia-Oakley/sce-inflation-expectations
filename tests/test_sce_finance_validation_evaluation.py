"""Synthetic-only tests for weighted Q1 replication and evidence auditing."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil

import duckdb
import numpy as np
import pytest

from studies.sce_inflation_expectations.evaluation import finance_validation as evaluation
from studies.sce_inflation_expectations.household_finance_input import render_household_finance_block
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
from studies.sce_inflation_expectations.revision_format_runtime import DIRECT, REPLY_MARKER, SHARED

BINS = [0., 0., 5., 15., 30., 25., 15., 7., 3., 0.]


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def read(path):
    return json.loads(path.read_text())


def repin(folder):
    manifest = read(folder / 'manifest.json')
    manifest['protocol_sha256'] = evaluation.common.sha(folder / 'protocol.json')
    manifest['prepared_file_sha256'] = {str(path.relative_to(folder)): evaluation.common.sha(path)
                                        for path in folder.rglob('*.json') if path.name != 'manifest.json'}
    dump(folder / 'manifest.json', manifest)


def build_fixture(root):
    folder = root / 'outputs/prepared'; folder.mkdir(parents=True)
    source = root / 'outputs/financial_source.json'; dump(source, {'synthetic': True})
    digest = evaluation.common.sha(source)
    reference = root / 'outputs/reference.parquet'
    rows = []
    for month in evaluation.MONTHS:
        for date in (evaluation.previous_month(month), month):
            for person in range(48):
                bins = list(BINS)
                if date == month:
                    bins[4] -= person % 3; bins[3] += person % 3
                rows.append((date, 1000 + person, 2., *bins))
    # A null current answer remains an assigned case, and has no model failure.
    first = next(i for i, row in enumerate(rows) if row[:2] == (202206, 1000))
    rows[first] = (202206, 1000, 2., *([None] * 10))
    db = duckdb.connect()
    columns = 'date BIGINT,userid BIGINT,Q8v2part2 DOUBLE,' + ','.join(f'Q9_bin{i} DOUBLE' for i in range(1, 11))
    db.execute(f'CREATE TABLE reference ({columns})')
    db.executemany('INSERT INTO reference VALUES (' + ','.join('?' for _ in range(13)) + ')', rows)
    db.execute(f"COPY reference TO '{reference}' (FORMAT PARQUET)"); db.close()
    protocol = {'id': 'sce-household-finance-crossmonth-v1', 'research_line': evaluation.RESEARCH_LINE,
                'months': list(evaluation.MONTHS), 'arms': list(evaluation.ARMS), 'n_per_month': 48,
                'generation_repeats': [1, 2], 'planned_calls': 768, 'primary_metric': 'q9_center_mae_pp',
                'primary_weight': 'design_survey_weight', 'primary_contrast': 'financial_facts minus baseline',
                'model': 'deepseek-flash', 'temperature': .5, 'max_tokens': 1024, 'thinking': 'disabled', 'retry_max': 0}
    dump(folder / 'protocol.json', protocol)
    links, jobs = [], []
    for month in evaluation.MONTHS:
        dest = folder / str(month); dest.mkdir()
        payloads, past, base = {}, {}, []
        for person in range(48):
            agent = f'p{person:03d}'
            links.append({'month': month, 'agent_id': agent, 'userid': 1000 + person,
                          'survey_weight': 1 + person / 100., 'inclusion_probability': .5,
                          'design_survey_weight': 2 * (1 + person / 100.), 'profile': {'numeracy': 'high' if person < 30 else 'low'}})
            payloads[agent] = {'schema_version': 'sce_household_finance_input_v1', 'research_line': evaluation.RESEARCH_LINE,
                               'target_month': month, 'current_q1_code': 2 if person < 12 else 3,
                               'current_q1_source_month': month, 'current_source_sha256': digest,
                               'previous_q1_code': 3, 'previous_q1_source_month': evaluation.previous_month(month), 'previous_source_sha256': digest}
            prior = {'point_pct': 2., 'q9': {f'bin{i}': b for i, b in enumerate(BINS, 1)}}
            past[agent] = {'prior': {**prior, 'source_month': evaluation.previous_month(month)}}
            text = ('Publication timing for the same information above:\nSynthetic dated facts.\nYour earlier survey response\n'
                    + json.dumps(prior) + '\n' + SHARED + DIRECT)
            messages = [{'role': 'user', 'content': text}]
            base.append({'agent_id': agent, 'messages': messages, 'prompt_sha256': message_hash(messages)})
        dump(dest / 'past_private.json', past); dump(dest / 'household_finance_payloads.json', payloads)
        dump(dest / 'population.json', {'synthetic': True}); dump(dest / 'environment.json', {'synthetic': True})
        for arm in evaluation.ARMS:
            previews = []
            for row in base:
                block = render_household_finance_block(arm, payloads[row['agent_id']])
                messages = [{'role': 'user', 'content': row['messages'][0]['content'].replace(REPLY_MARKER, block + REPLY_MARKER, 1)}]
                previews.append({'agent_id': row['agent_id'], 'messages': messages, 'prompt_sha256': message_hash(messages)})
            dump(dest / f'preview_{arm}.json', previews)
            sidecar_hash = evaluation.common.sha(dest / 'household_finance_payloads.json')
            dump(dest / f'simulation_{arm}.json', {'decision_ref': evaluation.REF, 'decision_args': {
                'household_finance_payloads_sha256': sidecar_hash,
                'household_finance_bundle': {'arm': arm, 'messages_sha256': {row['agent_id']: row['prompt_sha256'] for row in previews}}}})
            for repeat in evaluation.REPEATS:
                run_id = f'synthetic-{month}-{arm}-{repeat}'
                jobs.append({'month': month, 'arm': arm, 'repeat': repeat, 'run_id': run_id})
                directory = root / 'outputs/local_runs' / run_id; directory.mkdir(parents=True)
                dump(directory / 'run_manifest.json', {'status': 'completed', 'run_id': run_id, 'month': month, 'arm': arm,
                     'repeat': repeat, 'n': 48, 'llm_kind': 'openai', 'new_api_calls': 48, 'actual_input_hashes_match': True,
                     'protocol_sha256': evaluation.common.sha(folder / 'protocol.json'), 'household_finance_payloads_sha256': sidecar_hash,
                     'cost': {'call_count': 48, 'estimated_cost_usd': 0.}})
                shutil.copyfile(dest / 'household_finance_payloads.json', directory / 'household_finance_payloads.json')
                shutil.copyfile(dest / f'preview_{arm}.json', directory / 'frozen_preview.json')
                db = duckdb.connect(str(directory / 'study.duckdb'))
                db.execute('CREATE TABLE panel(agent_id VARCHAR,step INTEGER,action_kind VARCHAR,action_payload VARCHAR)')
                calls = []
                for preview in previews:
                    bins = list(BINS); shift = 4. if arm == 'baseline' else 2.
                    bins[4] -= shift; bins[5] += shift
                    raw = json.dumps({'point_pct': 2., 'q9': {f'bin{i}': b for i, b in enumerate(bins, 1)}})
                    action = {'validation_status': 'valid', 'point_pct': 2., 'household_finance_arm': arm,
                              'household_finance_payloads_sha256': sidecar_hash, 'actual_messages_sha256': preview['prompt_sha256'],
                              'research_line': evaluation.RESEARCH_LINE, **{f'q9_bin{i}': b for i, b in enumerate(bins, 1)}}
                    db.execute("INSERT INTO panel VALUES (?,1,'sce_answer',?)", [preview['agent_id'], json.dumps(action)])
                    calls.append({'run_id': run_id, 'agent_id': preview['agent_id'], 'attempt_idx': 0,
                                  'target_month': f'{month // 100:04d}-{month % 100:02d}', 'requested_model': 'deepseek-flash',
                                  'temperature': .5, 'max_tokens': 1024, 'extra_body': {'thinking': {'type': 'disabled'}},
                                  'prompt_version': 'sce-q8-q9-household-finance-v1', 'prompt_sha256': preview['prompt_sha256'],
                                  'prompt_text': json.dumps(preview['messages'], ensure_ascii=False), 'raw_response_text': raw,
                                  'raw_response_sha256': hashlib.sha256(raw.encode()).hexdigest(), 'error': None})
                db.close(); (directory / 'llm_calls.jsonl').write_text(''.join(json.dumps(call) + '\n' for call in calls))
    dump(folder / 'evaluation_links_private.json', links)
    dump(folder / 'manifest.json', {'protocol_sha256': evaluation.common.sha(folder / 'protocol.json'), 'planned_calls': 768, 'jobs': jobs,
                                   'source_sha256': {str(source.relative_to(root)): digest, str(reference.relative_to(root)): evaluation.common.sha(reference)}})
    repin(folder)
    return root


@pytest.fixture(scope='module')
def template(tmp_path_factory):
    return build_fixture(tmp_path_factory.mktemp('finance-validation') / 'repository')


@pytest.fixture
def trial(template, tmp_path, monkeypatch):
    root = tmp_path / 'repository'; shutil.copytree(template, root)
    monkeypatch.setattr(evaluation, 'ROOT', root)
    monkeypatch.setattr(evaluation, 'REFERENCE', root / 'outputs/reference.parquet')
    return root, root / 'outputs/prepared'


def test_prepared_audit_never_reads_current_truth(trial, monkeypatch):
    _, folder = trial
    monkeypatch.setattr(evaluation, '_truth', lambda *_: pytest.fail('preparation opened targets'))
    audited = evaluation.audit_prepared(folder)
    assert len(audited['links']) == 192
    assert len(audited['previews']) == 8


def test_complete_synthetic_run_rescores_raw_truth_and_all_calls(trial):
    root, folder = trial
    summary = evaluation.evaluate(folder, root / 'outputs/evaluation', draws=40)
    assert summary['evaluation_api_calls'] == 0
    assert summary['raw_replies_reconstructed_and_matched'] == 768
    assert summary['common_support']['q9_person_months'] == 191
    assert summary['common_support']['human_q9_unscorable_person_months'] == 1
    assert summary['common_support']['any_model_q9_failure_person_months'] == 0
    assert len(summary['facts_minus_baseline']['monthly_center_errors']) == 4
    assert summary['facts_minus_baseline']['draws_used'] == 40
    assert set(summary['design_weighted']) == {*evaluation.ARMS, *evaluation.BASELINES}
    assert 'userid' not in json.dumps(summary)
    assert summary['facts_minus_baseline']['exploratory_only'] is True


@pytest.mark.parametrize('kind', ['raw_hash', 'action', 'call_count', 'model', 'payload_copy'])
def test_original_evidence_tampering_rejected_before_truth(trial, monkeypatch, kind):
    root, folder = trial
    monkeypatch.setattr(evaluation, '_truth', lambda *_: pytest.fail('failed evidence opened targets'))
    job = read(folder / 'manifest.json')['jobs'][0]; directory = root / 'outputs/local_runs' / job['run_id']
    if kind in ('raw_hash', 'model'):
        path = directory / 'llm_calls.jsonl'; calls = [json.loads(line) for line in path.read_text().splitlines()]
        calls[0]['raw_response_text' if kind == 'raw_hash' else 'requested_model'] = 'changed'
        path.write_text(''.join(json.dumps(call) + '\n' for call in calls))
    elif kind == 'action':
        db = duckdb.connect(str(directory / 'study.duckdb'))
        agent, raw = db.execute('SELECT agent_id,action_payload FROM panel LIMIT 1').fetchone()
        action = json.loads(raw); action['point_pct'] = 17
        db.execute('UPDATE panel SET action_payload=? WHERE agent_id=?', [json.dumps(action), agent]); db.close()
    elif kind == 'call_count':
        path = directory / 'run_manifest.json'; data = read(path); data['cost']['call_count'] = 49; dump(path, data)
    else:
        path = directory / 'household_finance_payloads.json'; path.write_text(path.read_text() + ' ')
    with pytest.raises(ValueError):
        evaluation.load(folder)


def test_bad_design_weight_rejected_even_after_repin(trial):
    _, folder = trial
    path = folder / 'evaluation_links_private.json'; rows = read(path)
    rows[0]['design_survey_weight'] += 1; dump(path, rows); repin(folder)
    with pytest.raises(ValueError, match='design weight'):
        evaluation.audit_prepared(folder)


def test_facts_must_be_exact_single_insertion_even_after_repin(trial):
    _, folder = trial
    path = folder / '202206/preview_financial_facts.json'; rows = read(path)
    rows[0]['messages'][0]['content'] = rows[0]['messages'][0]['content'].replace('Synthetic dated facts.', 'Different public news.')
    rows[0]['prompt_sha256'] = message_hash(rows[0]['messages']); dump(path, rows)
    cfgpath = folder / '202206/simulation_financial_facts.json'; cfg = read(cfgpath)
    cfg['decision_args']['household_finance_bundle']['messages_sha256'][rows[0]['agent_id']] = rows[0]['prompt_sha256']; dump(cfgpath, cfg); repin(folder)
    with pytest.raises(ValueError, match='exact Q1 insertion'):
        evaluation.audit_prepared(folder)


def manual_cases():
    cases = []
    for month in evaluation.MONTHS:
        for repeat in evaluation.REPEATS:
            for person, real, base, facts, weight in zip((1, 2, 3), (0, 4, 10), (2, 6, 12), (8, 4, 2), (8, 1, 1)):
                scored = {'iqr': 1., 'zero_deflation': 0., 'q9_bins': list(BINS), 'validation_status': 'valid'}
                cases.append({'month': month, 'repeat': repeat, 'userid': person, 'design_survey_weight': weight,
                              'real': {'q9_mean': real, 'q9_iqr': 1., 'q9_zero_deflation': 0., 'q9_bins': list(BINS), 'previous_q9_mean': 0},
                              'arms': {'baseline': {**scored, 'mean': base}, 'financial_facts': {**scored, 'mean': facts}},
                              'baselines': {'copy_previous': 0., 'history_anchor_half': 1.}})
    return cases


def test_weighting_can_reverse_center_conclusion_and_months_stay_equal():
    cases = manual_cases(); support = {(r['month'], r['userid']) for r in cases}
    weighted = evaluation.summarize(cases, support)
    equal = evaluation.summarize(cases, support, False)
    assert weighted['baseline']['aggregate_equal_month_repeat_cells']['q9_center_mae_pp'] == 2
    assert weighted['financial_facts']['aggregate_equal_month_repeat_cells']['q9_center_mae_pp'] == 8
    assert equal['baseline']['aggregate_equal_month_repeat_cells']['q9_center_mae_pp'] == 2
    assert equal['financial_facts']['aggregate_equal_month_repeat_cells']['q9_center_mae_pp'] == 0
    assert weighted['baseline']['aggregate_equal_month_repeat_cells']['individual_density_mean_mae_pp'] == 2


def test_macro_screen_keeps_any_micro_worsening_as_tradeoff():
    metrics = {}
    for arm, errors in (('baseline', [2, 2, 2, 2]), ('financial_facts', [1, 1, 1, 3])):
        metrics[arm] = {'aggregate_equal_month_repeat_cells': {'q9_center_mae_pp': np.mean(errors),
                         'individual_density_mean_mae_pp': 2.001 if arm == 'financial_facts' else 2., 'cross_section_w1_pp': 1.},
                        'cells': [{'month': m, 'repeat': r, 'q9_center_mae_pp': error} for m, error in zip(evaluation.MONTHS, errors) for r in evaluation.REPEATS],
                        'cells_used_by_metric': {'q9_center_mae_pp': 8}}
    result = evaluation.compare(metrics, {'interval_95_unadjusted_pp': [-1, .1]}, True)
    assert result['macro_replication_screen'] is True
    assert result['nonworse_month_count'] == 3
    assert result['micro_tradeoff'] is True
    assert result['no_overall_upgrade'] is True
    assert result['exploratory_center_interval_upper_below_zero'] is False
    metrics['financial_facts']['cells'][0]['q9_center_mae_pp'] = 3
    metrics['financial_facts']['cells'][1]['q9_center_mae_pp'] = 3
    assert evaluation.compare(metrics, {}, True)['macro_replication_screen'] is False


def test_person_cluster_bootstrap_is_reproducible_and_preserves_repeats():
    cases = manual_cases(); support = {(row['month'], row['userid']) for row in cases}
    first = evaluation.bootstrap(cases, support, 1000, 31)
    assert first == evaluation.bootstrap(cases, support, 1000, 31)
    assert first['draws_used'] == 1000
    assert first['interval_95_unadjusted_pp'] == pytest.approx([-2, 6])


def test_sparse_group_descriptions_suppress_only_groups_and_gaps():
    cases = manual_cases()
    # Exactly three people form the first group, and two form the second.
    expanded = []
    for row in cases:
        for copy in range(1 if row['userid'] == 1 else 2):
            item = dict(row, userid=row['userid'] * 10 + copy,
                        current_q1_code=2 if row['userid'] < 3 else 4,
                        profile={'numeracy': 'high' if row['userid'] < 3 else 'low'})
            expanded.append(item)
    support = {(row['month'], row['userid']) for row in expanded}
    result = evaluation.group_cells(expanded, support)
    cell = next(cell for cell in result if cell['dimension'] == 'q1')
    assert cell['groups']['worse']['n_common'] == 3
    assert cell['groups']['worse']['reported'] is True
    assert cell['groups']['better']['n_common'] == 2
    assert cell['groups']['better']['reported'] is False
    assert cell['median_group_gaps'][0]['reported'] is False
    assert len(support) == 20  # Five people × four months; full support stays intact.
