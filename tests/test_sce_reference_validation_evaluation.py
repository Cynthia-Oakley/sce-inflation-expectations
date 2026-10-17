"""Focused synthetic tests; no current target data or real calls are used."""
import hashlib
import json
from pathlib import Path
import shutil

import duckdb
import numpy as np
import pytest

from studies.sce_inflation_expectations.evaluation import reference_validation as evaluation
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
from studies.sce_inflation_expectations.revision_format_runtime import DIRECT, SHARED

BINS = [0., 0., 5., 15., 30., 25., 15., 7., 3., 0.]


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + '\n')


def read(path):
    return json.loads(path.read_text())


def repin(folder):
    manifest = read(folder / 'manifest.json')
    manifest['prepared_file_sha256'] = {str(path.relative_to(folder)): evaluation.common.sha(path)
                                       for path in folder.rglob('*.json') if path.name != 'manifest.json'}
    dump(folder / 'manifest.json', manifest)


def build_prepared(root):
    folder = root / 'outputs/prepared'; folder.mkdir(parents=True)
    reference = root / 'outputs/reference.parquet'
    # A deliberately non-parquet sentinel proves the prepared audit cannot parse it.
    reference.write_bytes(b'Only hash these synthetic bytes during preparation.')
    protocol = {'id': 'sce-reference-scaleup-v1', 'research_line': evaluation.RESEARCH_LINE,
                'months': list(evaluation.MONTHS), 'old_months': list(evaluation.OLD_MONTHS), 'new_months': list(evaluation.NEW_MONTHS),
                'arms': ['reference'], 'n_per_month': 192, 'generation_repeats': [1, 2], 'planned_calls': 4608,
                'primary_metric': 'q9_center_mae_pp', 'primary_weight': 'design_survey_weight', 'primary_month_scope': 'new_months',
                'model': 'deepseek-flash', 'temperature': .5, 'max_tokens': 1024, 'thinking': 'disabled', 'retry_max': 0}
    dump(folder / 'protocol.json', protocol)
    links, jobs = [], []
    for month in evaluation.MONTHS:
        dest = folder / str(month); dest.mkdir()
        previews, past = [], {}
        ids = [f'person{i:03d}' for i in range(192)]
        for i, agent in enumerate(ids):
            prior = {'point_pct': 2., 'q9': {f'bin{j}': b for j, b in enumerate(BINS, 1)}}
            text = ('Publication timing for the same information above:\nSynthetic dated facts.\nYour earlier survey response\n'
                    + json.dumps(prior) + '\n' + SHARED + DIRECT)
            messages = [{'role': 'user', 'content': text}]
            previews.append({'agent_id': agent, 'messages': messages, 'prompt_sha256': message_hash(messages)})
            past[agent] = {'prior': {**prior, 'source_month': evaluation.previous_month(month)}}
            links.append({'month': month, 'agent_id': agent, 'userid': 1000 + i,
                          'survey_weight': 1 + i / 1000., 'inclusion_probability': .5,
                          'design_survey_weight': 2 * (1 + i / 1000.), 'stratum': 'young|middle',
                          'profile': {'age_group': 'young', 'household_income_band': 'middle'}})
        dump(dest / 'preview_reference.json', previews); dump(dest / 'past_private.json', past)
        dump(dest / 'population.json', {'synthetic': True}); dump(dest / 'environment.json', {'synthetic': True})
        dump(dest / 'eligible_ids_private.json', list(range(1000, 1194)))
        subsets = []
        for seed in range(30):
            permutation = np.random.default_rng(seed + month).permutation(ids).tolist()
            subsets.append({'seed': seed, 'ids_48': permutation[:48], 'ids_96': permutation[:96]})
        dump(dest / 'nested_subsamples_private.json', subsets)
        dump(dest / 'simulation_reference.json', {'decision_ref': evaluation.REF, 'decision_args': {'prompt_version': evaluation.PROMPT,
            'reference_validation_bundle': {'parent': {}, 'messages_sha256': {row['agent_id']: row['prompt_sha256'] for row in previews}}}})
        jobs.extend({'month': month, 'arm': 'reference', 'repeat': repeat, 'run_id': f'synthetic-reference-{month}-{repeat}'} for repeat in (1, 2))
    dump(folder / 'evaluation_links_private.json', links)
    dump(folder / 'manifest.json', {'planned_calls': 4608, 'protocol_sha256': evaluation.common.sha(folder / 'protocol.json'), 'jobs': jobs,
                                    'source_sha256': {str(reference.relative_to(root)): evaluation.common.sha(reference)}})
    repin(folder)
    return root


@pytest.fixture(scope='module')
def template(tmp_path_factory):
    return build_prepared(tmp_path_factory.mktemp('reference-evaluation') / 'repository')


@pytest.fixture
def trial(template, tmp_path, monkeypatch):
    root = tmp_path / 'repository'; shutil.copytree(template, root)
    monkeypatch.setattr(evaluation, 'ROOT', root)
    monkeypatch.setattr(evaluation, 'REFERENCE', root / 'outputs/reference.parquet')
    return root, root / 'outputs/prepared'


def build_one_run(root, folder):
    prepared = evaluation.audit_prepared(folder)
    job = prepared['manifest']['jobs'][0]
    directory = root / 'outputs/local_runs' / job['run_id']; directory.mkdir(parents=True)
    dump(directory / 'run_manifest.json', {'status': 'completed', 'run_id': job['run_id'], 'month': job['month'], 'arm': 'reference',
        'repeat': job['repeat'], 'llm_kind': 'openai', 'n': 192, 'new_api_calls': 192, 'actual_input_hashes_match': True,
        'protocol_sha256': prepared['protocol_sha256'], 'cost': {'call_count': 192, 'estimated_cost_usd': 0.}})
    shutil.copyfile(folder / str(job['month']) / 'preview_reference.json', directory / 'frozen_preview.json')
    db = duckdb.connect(str(directory / 'study.duckdb'))
    db.execute('CREATE TABLE panel(agent_id VARCHAR,step INTEGER,action_kind VARCHAR,action_payload VARCHAR)')
    calls = []
    for agent, preview in prepared['previews'][job['month'], 'reference'].items():
        raw = json.dumps({'point_pct': 2., 'q9': {f'bin{i}': b for i, b in enumerate(BINS, 1)}})
        action = {'validation_status': 'valid', 'point_pct': 2., 'reference_validation_arm': 'reference',
                  'actual_messages_sha256': preview['prompt_sha256'], 'research_line': evaluation.RESEARCH_LINE,
                  **{f'q9_bin{i}': b for i, b in enumerate(BINS, 1)}}
        db.execute("INSERT INTO panel VALUES (?,1,'sce_answer',?)", [agent, json.dumps(action)])
        calls.append({'agent_id': agent, 'run_id': job['run_id'], 'attempt_idx': 0,
                      'target_month': f'{job["month"] // 100:04d}-{job["month"] % 100:02d}', 'requested_model': 'deepseek-flash',
                      'temperature': .5, 'max_tokens': 1024, 'extra_body': {'thinking': {'type': 'disabled'}},
                      'prompt_version': evaluation.PROMPT, 'prompt_sha256': preview['prompt_sha256'],
                      'prompt_text': json.dumps(preview['messages'], ensure_ascii=False), 'raw_response_text': raw,
                      'raw_response_sha256': hashlib.sha256(raw.encode()).hexdigest(), 'error': None})
    db.close(); (directory / 'llm_calls.jsonl').write_text(''.join(json.dumps(call) + '\n' for call in calls))
    return prepared, job, directory


def test_prepared_audit_uses_no_current_target_answers(trial, monkeypatch):
    _, folder = trial
    monkeypatch.setattr(evaluation, '_read_truth', lambda *_: pytest.fail('preparation opened targets'))
    prepared = evaluation.audit_prepared(folder)
    assert len(prepared['links']) == 2304
    assert len(prepared['previews']) == 12
    assert all(len(rows) == 30 for rows in prepared['nested'].values())


def test_complete_single_cell_audits_original_192_replies_and_actions(trial):
    root, folder = trial
    prepared, job, _ = build_one_run(root, folder)
    result, hashes, cost = evaluation._audit_job(prepared, job)
    assert len(result) == 192
    assert all(row['validation_status'] == 'valid' and row['response_parsed'] for row in result.values())
    assert len(hashes) == 4
    assert cost == 0


@pytest.mark.parametrize('kind', ['raw', 'action', 'model', 'count', 'preview'])
def test_raw_evidence_tampering_is_rejected(trial, kind):
    root, folder = trial
    prepared, job, directory = build_one_run(root, folder)
    if kind in ('raw', 'model'):
        path = directory / 'llm_calls.jsonl'; calls = [json.loads(line) for line in path.read_text().splitlines()]
        calls[0]['raw_response_text' if kind == 'raw' else 'requested_model'] = 'changed'
        path.write_text(''.join(json.dumps(call) + '\n' for call in calls))
    elif kind == 'action':
        db = duckdb.connect(str(directory / 'study.duckdb'))
        agent, raw = db.execute('SELECT agent_id,action_payload FROM panel LIMIT 1').fetchone()
        action = json.loads(raw); action['point_pct'] = 100
        db.execute('UPDATE panel SET action_payload=? WHERE agent_id=?', [json.dumps(action), agent]); db.close()
    elif kind == 'count':
        path = directory / 'run_manifest.json'; data = read(path); data['cost']['call_count'] = 193; dump(path, data)
    else:
        path = directory / 'frozen_preview.json'; path.write_text(path.read_text() + ' ')
    with pytest.raises(ValueError):
        evaluation._audit_job(prepared, job)


def test_any_missing_real_cell_prevents_all_current_truth_loading(trial, monkeypatch):
    _, folder = trial
    monkeypatch.setattr(evaluation, '_read_truth', lambda *_: pytest.fail('partial runs opened current outcomes'))
    with pytest.raises(ValueError, match='Missing completed-run evidence'):
        evaluation.load(folder)


def test_non_nested_sample_is_rejected_after_hash_repin(trial):
    _, folder = trial
    path = folder / '202003/nested_subsamples_private.json'; rows = read(path)
    outside = next(f'person{i:03d}' for i in range(192) if f'person{i:03d}' not in rows[0]['ids_96'])
    rows[0]['ids_48'][0] = outside; dump(path, rows); repin(folder)
    with pytest.raises(ValueError, match='48 subset 96 subset 192'):
        evaluation.audit_prepared(folder)


def test_signed_decomposition_is_not_absolute_error_addition():
    result = evaluation.signed_decomposition(2., 8., 4., 5.)
    assert [result[key] for key in ('model_minus_sample_pp', 'sample_minus_eligible_pp', 'eligible_minus_full_pp')] == [-6, 4, -1]
    assert result['sum_components_pp'] == result['model_minus_full_pp'] == -3
    assert result['identity_residual_pp'] == 0
    assert sum(abs(result[key]) for key in ('model_minus_sample_pp', 'sample_minus_eligible_pp', 'eligible_minus_full_pp')) == 11


def manual_cases():
    cases, centers = [], {}
    for index, month in enumerate(evaluation.MONTHS):
        centers[month] = {'full_wave': {'center_pp': 5.}, 'eligible_returners': {'center_pp': 4.}, 'previous_full_wave': {'center_pp': 3.}}
        for repeat in evaluation.REPEATS:
            for person, real, pred, weight in zip((1, 2, 3), (0., 4., 10.), (2., 6., 12.), (8., 1., 1.)):
                scored = {'mean': pred + index, 'iqr': 1., 'zero_deflation': 0., 'q9_bins': list(BINS), 'validation_status': 'valid'}
                cases.append({'month': month, 'repeat': repeat, 'agent_id': f'p{person}', 'userid': person, 'design_survey_weight': weight,
                              'real': {'q9_mean': real, 'q9_iqr': 1., 'q9_zero_deflation': 0., 'q9_bins': list(BINS), 'previous_q9_mean': 0.},
                              'arms': {'reference': scored}, 'baselines': {'copy_previous': 0., 'history_anchor_half': 1.}})
    return cases, centers


def test_weighted_centers_distinguish_sample_eligible_full_and_scope_months():
    cases, centers = manual_cases(); support = {(row['month'], row['userid']) for row in cases}
    cells = evaluation.summarize_cells(cases, centers, support)
    first = cells[0]
    assert first['simulated_center_pp'] == 2
    assert first['matched_sample_truth_center_pp'] == 0
    assert first['eligible_center_pp'] == 4
    assert first['full_wave_center_pp'] == 5
    assert first['signed_center_decomposition']['identity_residual_pp'] == 0
    scopes = evaluation.aggregate_scopes(cells)
    assert scopes['new_months']['n_time_observations'] == 8
    assert scopes['old_months']['n_time_observations'] == 4
    assert scopes['all_months']['n_time_observations'] == 12
    assert scopes['all_months']['model_metrics_equal_month_repeat_cells']['q9_center_mae_pp'] == pytest.approx(7.5)
    assert scopes['new_months']['months'] == list(evaluation.NEW_MONTHS)
    assert scopes['all_months']['scalar_baselines_equal_month_repeat_cells']['copy_previous']['metrics']['individual_density_mean_mae_pp'] == pytest.approx(1.4)


def test_year_blocks_keep_months_together_and_average_repeats_first():
    cases, centers = manual_cases(); support = {(row['month'], row['userid']) for row in cases}
    cells = evaluation.summarize_cells(cases, centers, support)
    # Both observations in a year have the same error; the 6-block interval
    # must match a direct year bootstrap, rather than treating 24 cells as time N.
    for row in cells:
        row['model_metrics_same_sample']['q9_center_mae_pp'] = float(row['month'] // 100 - 2020)
    result = evaluation.year_block_bootstrap(cells, 1000, 11)
    rng = np.random.default_rng(11)
    expected = [float(np.mean(rng.choice(np.arange(6.), size=6, replace=True))) for _ in range(1000)]
    interval = result['all_months']['metrics']['reference_same_sample_mae_pp']['interval_95_unadjusted_pp']
    assert interval == pytest.approx(np.quantile(expected, [.025, .975]).tolist())
    assert result['all_months']['n_year_blocks'] == 6
    assert result['all_months']['n_months'] == 12
    assert result == evaluation.year_block_bootstrap(cells, 1000, 11)


def test_full_wave_and_eligible_centers_rescore_raw_bins_not_official_means(tmp_path, monkeypatch):
    reference = tmp_path / 'raw_reference.parquet'
    db = duckdb.connect()
    db.execute('CREATE TABLE reference(date BIGINT,userid BIGINT,weight DOUBLE,Q8v2part2 DOUBLE,Q9_mean DOUBLE,'
               + ','.join(f'Q9_bin{i} DOUBLE' for i in range(1, 11)) + ')')
    high = list(BINS); high[4] -= 10; high[3] += 10
    for month in evaluation.MONTHS:
        for date in (evaluation.previous_month(month), month):
            for uid, weight, bins in ((1, 1., BINS), (2, 2., BINS), (3, 20., high)):
                db.execute('INSERT INTO reference VALUES (' + ','.join('?' for _ in range(15)) + ')',
                           [date, uid, weight, 2., 99999., *bins])
    db.execute(f"COPY reference TO '{reference}' (FORMAT PARQUET)"); db.close()
    monkeypatch.setattr(evaluation, 'REFERENCE', reference)
    prepared = {'links': [{'month': month, 'agent_id': 'one', 'userid': 1} for month in evaluation.MONTHS],
                'eligible': {month: [1, 2] for month in evaluation.MONTHS}}
    lookup, history, centers = evaluation._read_truth(prepared)
    for month in evaluation.MONTHS:
        assert centers[month]['full_wave']['center_pp'] == pytest.approx(evaluation.score(high)['mean'])
        assert centers[month]['eligible_returners']['center_pp'] == pytest.approx(evaluation.score(BINS)['mean'])
        assert centers[month]['full_wave']['n_scorable_positive_weight'] == 3
        assert centers[month]['eligible_returners']['n_scorable_positive_weight'] == 2
        assert lookup[month, 1]['q9_mean'] != 99999.
        assert history[month, 'one']['copy_previous'] == pytest.approx(evaluation.score(BINS)['mean'])


def test_nested_sampling_reports_all_seeds_and_conditional_weighting():
    cases, centers = [], {}
    nested = {}
    ids = [f'p{i:03d}' for i in range(192)]
    for month in evaluation.MONTHS:
        centers[month] = {'full_wave': {'center_pp': 4.}, 'eligible_returners': {'center_pp': 3.}, 'previous_full_wave': {'center_pp': 2.}}
        nested[month] = []
        for seed in range(30):
            permutation = np.random.default_rng(seed + month).permutation(ids).tolist()
            nested[month].append({'seed': seed, 'ids_48': permutation[:48], 'ids_96': permutation[:96]})
        for repeat in (1, 2):
            for person, agent in enumerate(ids):
                real = person / 30.
                cases.append({'month': month, 'repeat': repeat, 'agent_id': agent, 'userid': person,
                              'design_survey_weight': 1. + (person % 7),
                              'real': {'q9_mean': real, 'q9_iqr': 1., 'q9_zero_deflation': 0., 'q9_bins': list(BINS), 'previous_q9_mean': 0.},
                              'arms': {'reference': {'mean': real + 1., 'iqr': 1., 'zero_deflation': 0., 'q9_bins': list(BINS)}},
                              'baselines': {'copy_previous': 0., 'history_anchor_half': 1.}})
    support = {(row['month'], row['userid']) for row in cases}
    result = evaluation.nested_sampling(cases, centers, support, nested)
    assert result['prespecified_seed_count'] == 30
    assert len(result['by_seed']) == 60
    assert {row['seed'] for row in result['by_seed']} == set(range(30))
    assert len(result['monthly_seed_cells']) == 30 * 2 * 24
    assert result['sampling_ranges']['48']['new_months']['same_sample_center_mae_pp']['seeds_scorable'] == 30
    # Constant shift preserves the same-weighted-sample median error under any subset.
    assert result['sampling_ranges']['96']['all_months']['same_sample_center_mae_pp']['min_q025_median_q975_max_pp'] == pytest.approx([1.] * 5)
    selected = {month: nested[month][0]['ids_48'] for month in evaluation.MONTHS}
    cells = evaluation.summarize_cells(cases, centers, support, selected, 48)
    assert all(cell['sample_size_assigned'] == 48 and cell['conditional_nested_inclusion_probability'] == .25 for cell in cells)


def test_human_bin_cache_uses_identical_model_validation_and_fitter_gate():
    bins = list(BINS)
    bins[4] -= .2  # Inside the established runtime sum tolerance, not 1e-6.
    expected = evaluation.common._score_bins(bins)
    assert evaluation.score(bins) == expected
    before = evaluation._fit_cached.cache_info().hits
    assert evaluation.score(bins) == expected
    assert evaluation._fit_cached.cache_info().hits == before + 1
