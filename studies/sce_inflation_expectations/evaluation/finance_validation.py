"""Offline cross-month Q1 evaluation with design-weighted sample centers.

The preparation audit does not open current outcomes. Completed-run evaluation
uses raw reference bins and the same frozen scorer as model answers. Generic
parsing, reply/action audits and metrics are shared; no evaluator is patched.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
from pathlib import Path
import re

import duckdb
import numpy as np
import pandas as pd

from . import cognition as common
from .behavior_comparison import history_baselines, previous_month
from .metrics import quantile, wasserstein1
from ..household_finance_input import RESEARCH_LINE, render_household_finance_block, validate_household_finance_record
from ..prior_belief_experiment import message_hash
from ..revision_format_runtime import DIRECT, REPLY_MARKER, previous_answer
from ..scoring.sce_q9_frozen import provenance

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / 'outputs/sce_behavior_mechanism_audit_20261014_v3/reference_with_controls_private.parquet'
ARMS = ('baseline', 'financial_facts')
BASELINES = ('copy_previous', 'history_anchor_half')
MONTHS = (202206, 202306, 202410, 202509)
REPEATS = (1, 2)
N = 48
PRIMARY = 'q9_center_mae_pp'
SEED = 20261017
REF = 'sce_inflation_expectations.household_finance_decision'


def _protocol(protocol, manifest):
    expected = {'id': 'sce-household-finance-crossmonth-v1', 'research_line': RESEARCH_LINE,
                'months': list(MONTHS), 'arms': list(ARMS), 'n_per_month': N,
                'generation_repeats': list(REPEATS), 'planned_calls': 768,
                'primary_metric': PRIMARY, 'primary_weight': 'design_survey_weight',
                'primary_contrast': 'financial_facts minus baseline',
                'model': 'deepseek-flash', 'temperature': .5, 'max_tokens': 1024,
                'thinking': 'disabled', 'retry_max': 0}
    for key, value in expected.items():
        if protocol.get(key) != value:
            raise ValueError(f'Cross-month protocol mismatch: {key}')
    if (any(type(v) is not int for v in protocol['months'] + protocol['generation_repeats'])
            or type(protocol['n_per_month']) is not int or type(protocol['planned_calls']) is not int
            or type(manifest.get('planned_calls')) is not int or manifest['planned_calls'] != 768):
        raise ValueError('Invalid cross-month integer counts')


def audit_prepared(folder: Path):
    """Validate frozen inputs and exact treatment difference without reading truth."""
    folder = Path(folder).resolve()
    manifest, protocol = (common._read_json(folder / name) for name in ('manifest.json', 'protocol.json'))
    _protocol(protocol, manifest)
    protocol_hash = common.sha(folder / 'protocol.json')
    if manifest.get('protocol_sha256') != protocol_hash:
        raise ValueError('Protocol hash mismatch')
    required = {'protocol.json', 'evaluation_links_private.json'}
    for month in MONTHS:
        required.update(f'{month}/{name}.json' for name in ('population', 'environment', 'past_private', 'household_finance_payloads'))
        required.update(f'{month}/{prefix}_{arm}.json' for prefix in ('preview', 'simulation') for arm in ARMS)
    declared = manifest.get('prepared_file_sha256')
    if not isinstance(declared, dict) or not required.issubset(declared):
        raise ValueError('Required prepared inputs are not pinned')
    verified = common._verify_declared_hashes(folder, declared, 'prepared')
    links = common._read_json(folder / 'evaluation_links_private.json')
    if not isinstance(links, list) or len(links) != N * len(MONTHS):
        raise ValueError('Expected 192 selected respondent-months')
    for month in MONTHS:
        rows = [row for row in links if row.get('month') == month]
        if (len(rows) != N or len({row['agent_id'] for row in rows}) != N
                or len({row['userid'] for row in rows}) != N):
            raise ValueError('Duplicate or missing selected respondent')
        for row in rows:
            w, raw, pi = (row.get(key) for key in ('design_survey_weight', 'survey_weight', 'inclusion_probability'))
            if (not isinstance(row['agent_id'], str) or not row['agent_id']
                    or type(row['userid']) is not int or not all(common.finite(v) for v in (w, raw, pi))
                    or w <= 0 or raw <= 0 or not 0 < pi <= 1
                    or not np.isclose(w, raw / pi, rtol=1e-10, atol=1e-10)):
                raise ValueError('Invalid design weight/inclusion probability')
    records, previews = {}, {}
    source_hashes = manifest.get('source_sha256', {})
    used_digests = set()
    for month in MONTHS:
        ids = {row['agent_id'] for row in links if row['month'] == month}
        records[month] = common._read_json(folder / str(month) / 'household_finance_payloads.json')
        if not isinstance(records[month], dict) or set(records[month]) != ids:
            raise ValueError('Financial payload roster mismatch')
        past = common._read_json(folder / str(month) / 'past_private.json')
        if not isinstance(past, dict) or set(past) != ids:
            raise ValueError('Past-record roster mismatch')
        for agent, record in records[month].items():
            validate_household_finance_record(record)
            if record['target_month'] != month:
                raise ValueError('Financial payload target mismatch')
            used_digests.update(record[f'{period}_source_sha256'] for period in ('current', 'previous')
                                if record[f'{period}_source_sha256'] is not None)
        for arm in ARMS:
            previews[month, arm] = common._validate_preview(folder, month, arm, ids)
            cfg = common._read_json(folder / str(month) / f'simulation_{arm}.json')
            args = cfg.get('decision_args', {})
            bundle = args.get('household_finance_bundle', {})
            if (cfg.get('decision_ref') != REF or bundle.get('arm') != arm
                    or args.get('household_finance_payloads_sha256') != common.sha(folder / str(month) / 'household_finance_payloads.json')
                    or bundle.get('messages_sha256') != {agent: row['prompt_sha256'] for agent, row in previews[month, arm].items()}):
                raise ValueError('Simulation provider/payload/frozen message mismatch')
        for agent in ids:
            base = previews[month, 'baseline'][agent]['messages']
            if (len(base) != 1 or base[0].get('role') != 'user'
                    or not isinstance(base[0].get('content'), str)
                    or base[0]['content'].count(REPLY_MARKER) != 1
                    or not base[0]['content'].endswith(DIRECT)
                    or 'Publication timing for the same information above:' not in base[0]['content']):
                raise ValueError('Latest dated/direct/prior baseline required')
            prior = previous_answer(base)
            frozen_prior = past[agent].get('prior', {})
            if (prior != {key: frozen_prior.get(key) for key in ('point_pct', 'q9')}
                    or str(frozen_prior.get('source_month', '')).replace('-', '') != str(previous_month(month))):
                raise ValueError('Prompt prior differs from frozen past record or strict prior month')
            block = render_household_finance_block('financial_facts', records[month][agent])
            expected = [{'role': 'user', 'content': base[0]['content'].replace(REPLY_MARKER, block.rstrip() + '\n\n' + REPLY_MARKER, 1)}]
            if previews[month, 'financial_facts'][agent]['messages'] != expected:
                raise ValueError('Facts preview changes more than the exact Q1 insertion')
    if not used_digests.issubset(set(source_hashes.values())):
        raise ValueError('Q1 source hashes absent from source manifest')
    pinned = {name for name, digest in source_hashes.items() if digest in used_digests}
    reference_name = str(REFERENCE.resolve().relative_to(ROOT.resolve()))
    pinned.add(reference_name)
    verified_sources = common._verify_declared_hashes(ROOT, source_hashes, 'evaluation source', pinned)
    expected_jobs = {(month, arm, repeat) for month in MONTHS for arm in ARMS for repeat in REPEATS}
    jobs = manifest.get('jobs', [])
    if (len(jobs) != len(expected_jobs)
            or {(job.get('month'), job.get('arm'), job.get('repeat')) for job in jobs} != expected_jobs
            or len({job.get('run_id') for job in jobs}) != len(jobs)):
        raise ValueError('Expected exactly 16 unique registered jobs')
    return {'folder': folder, 'manifest': manifest, 'protocol': protocol, 'protocol_sha256': protocol_hash,
            'links': links, 'records': records, 'previews': previews,
            'source_sha256': {**verified_sources, **verified}, 'prepared_file_count': len(verified)}


def _audit_job(prepared, job):
    """Audit one cell's original calls and actions using shared legal parsing."""
    month, arm, repeat = job['month'], job['arm'], job['repeat']
    if not isinstance(job.get('run_id'), str) or not re.fullmatch(r'[A-Za-z0-9._-]+', job['run_id']):
        raise ValueError('Unsafe run identifier')
    directory = common._safe_relative(ROOT / 'outputs/local_runs', job['run_id'])
    paths = [directory / name for name in ('run_manifest.json', 'study.duckdb', 'llm_calls.jsonl', 'frozen_preview.json', 'household_finance_payloads.json')]
    if any(not path.is_file() for path in paths):
        raise ValueError(f'Missing completed-run evidence: {job["run_id"]}')
    run = common._read_json(paths[0])
    expected = {'status': 'completed', 'run_id': job['run_id'], 'month': month, 'arm': arm, 'repeat': repeat,
                'llm_kind': 'openai', 'n': N, 'new_api_calls': N,
                'actual_input_hashes_match': True, 'protocol_sha256': prepared['protocol_sha256']}
    if any(run.get(key) != value for key, value in expected.items()) or run.get('cost', {}).get('call_count') != N:
        raise ValueError('Completed run manifest/call-count mismatch')
    payload_hash = common.sha(prepared['folder'] / str(month) / 'household_finance_payloads.json')
    if (run.get('household_finance_payloads_sha256') != payload_hash or common.sha(paths[4]) != payload_hash
            or common.sha(paths[3]) != common.sha(prepared['folder'] / str(month) / f'preview_{arm}.json')):
        raise ValueError('Run frozen inputs differ from prepared inputs')
    calls = [json.loads(line) for line in paths[2].read_text().splitlines() if line.strip()]
    previews = prepared['previews'][month, arm]
    if len(calls) != N or len({call['agent_id'] for call in calls}) != N or {call['agent_id'] for call in calls} != set(previews):
        raise ValueError('Original-call roster/cardinality mismatch')
    db = duckdb.connect(str(paths[1]), read_only=True)
    try:
        rows = db.execute("SELECT agent_id,action_payload FROM panel WHERE step=1 AND action_kind='sce_answer'").fetchall()
    finally:
        db.close()
    if len(rows) != N or len({str(agent) for agent, _ in rows}) != N or {str(agent) for agent, _ in rows} != set(previews):
        raise ValueError('DuckDB action roster/cardinality mismatch')
    payloads = {str(agent): json.loads(raw) if isinstance(raw, str) else raw for agent, raw in rows}
    results = {}
    p = prepared['protocol']
    for call in calls:
        agent = call['agent_id']; preview = previews[agent]; action = payloads[agent]
        request = {'run_id': job['run_id'], 'attempt_idx': 0, 'target_month': f'{month // 100:04d}-{month % 100:02d}',
                   'requested_model': p['model'], 'temperature': p['temperature'], 'max_tokens': p['max_tokens'],
                   'extra_body': {'thinking': {'type': p['thinking']}}, 'prompt_version': 'sce-q8-q9-household-finance-v1',
                   'prompt_sha256': preview['prompt_sha256'], 'prompt_text': json.dumps(preview['messages'], ensure_ascii=False)}
        metadata = {'household_finance_arm': arm, 'household_finance_payloads_sha256': payload_hash,
                    'actual_messages_sha256': preview['prompt_sha256'], 'research_line': RESEARCH_LINE}
        if any(call.get(k) != v for k, v in request.items()) or any(action.get(k) != v for k, v in metadata.items()):
            raise ValueError('Call/action metadata differs from frozen request')
        raw = call.get('raw_response_text') or ''
        if hashlib.sha256(raw.encode()).hexdigest() != call.get('raw_response_sha256'):
            raise ValueError('Original reply hash mismatch')
        parsed, error = common._audit_raw_reply(raw, call, action, arm)
        bins = common._action_bins(action)
        scored = common._score_bins(bins) if action['validation_status'] == 'valid' else {
            'mean': None, 'iqr': None, 'zero_deflation': None, 'scorer_status': 'invalid_response'}
        results[agent] = {**scored, 'q9_bins': bins, 'point': common._float_or_none(action.get('point_pct')) if parsed is not None else None,
                          'validation_status': action['validation_status'], 'response_parsed': parsed is not None, 'parse_error': error}
    hashes = {str(path.relative_to(ROOT)): common.sha(path) for path in paths}
    return results, hashes, float(run['cost'].get('estimated_cost_usd', 0))


def _truth(links):
    """Evaluation-only projection: selected people's history and current raw answers."""
    ids = sorted({row['userid'] for row in links})
    fields = ['date', 'userid', 'Q8v2part2', *[f'Q9_bin{i}' for i in range(1, 11)]]
    db = duckdb.connect()
    try:
        frame = db.execute(f'SELECT {",".join(fields)} FROM read_parquet(?) WHERE userid IN ({",".join("?" for _ in ids)}) AND date<=?',
                           [str(REFERENCE), *ids, max(MONTHS)]).df()
    finally:
        db.close()
    if frame.duplicated(['date', 'userid']).any():
        raise ValueError('Reference has duplicate respondent-months')
    history = {(row['month'], row['userid']): row for row in history_baselines(frame, links, coefficient=.5)}
    lookup = {(int(row['date']), int(row['userid'])): row for row in frame.to_dict('records')}
    result = {}
    for link in links:
        month, uid = link['month'], link['userid']
        if (month, uid) not in lookup or (previous_month(month), uid) not in lookup:
            raise ValueError('Reference omits selected current or immediately prior row')
        current, previous = lookup[month, uid], lookup[previous_month(month), uid]
        def bins(row):
            return [common._float_or_none(row[f'Q9_bin{i}']) for i in range(1, 11)]
        actual_bins, prior_bins = bins(current), bins(previous)
        def score(values):
            return common._score_bins(values) if all(common.finite(v) for v in values) else {
                'mean': None, 'iqr': None, 'zero_deflation': None}
        actual, prior = score(actual_bins), score(prior_bins)
        point = common._float_or_none(current['Q8v2part2'])
        real = {'q9_mean': actual['mean'], 'q9_iqr': actual['iqr'], 'q9_zero_deflation': actual['zero_deflation'],
                'q9_bins': actual_bins, 'q8_point': point if point is not None and abs(point) <= 100 else None,
                'q8_excluded_outside_100': point is not None and abs(point) > 100,
                'previous_q9_mean': prior['mean'], 'previous_q9_bins': prior_bins,
                'previous_q8_point': common._float_or_none(previous['Q8v2part2']) if common.finite(previous['Q8v2part2']) and abs(previous['Q8v2part2']) <= 100 else None}
        result[month, link['agent_id']] = (real, history[month, uid])
    return result


def load(folder):
    prepared = audit_prepared(folder)
    if not provenance()['live_matches_pinned']:
        raise ValueError('Frozen scorer has changed')
    actions, hashes, cost = {}, dict(prepared['source_sha256']), 0.
    for job in prepared['manifest']['jobs']:
        results, verified, estimated = _audit_job(prepared, job)
        actions[job['month'], job['arm'], job['repeat']] = results
        hashes.update(verified); cost += estimated
    # Targets are only opened after every registered real run has been audited.
    truth = _truth(prepared['links'])
    cases = []
    for link in prepared['links']:
        month, agent = link['month'], link['agent_id']
        real, history = truth[month, agent]
        prior = previous_answer(prepared['previews'][month, 'baseline'][agent]['messages'])
        if (not common.finite(real['previous_q9_mean'])
                or not np.allclose([prior['q9'][f'bin{i}'] for i in range(1, 11)], real['previous_q9_bins'], rtol=0, atol=1e-8)
                or common.finite(prior.get('point_pct')) != common.finite(real['previous_q8_point'])
                or (common.finite(prior.get('point_pct')) and not np.isclose(prior['point_pct'], real['previous_q8_point'], rtol=0, atol=1e-8))):
            raise ValueError('Actual prompt prior differs from independently rescored reference')
        for repeat in REPEATS:
            cases.append({**link, 'repeat': repeat, 'real': real,
                          'current_q1_code': prepared['records'][month][agent]['current_q1_code'],
                          'arms': {arm: actions[month, arm, repeat][agent] for arm in ARMS},
                          'baselines': {key: history[key] for key in BASELINES}, 'history_n': history['history_n']})
    return {**prepared, 'cases': cases, 'source_sha256': hashes, 'estimated_run_cost_usd': cost}


def _supports(cases, measure='q9'):
    legal = [row for row in cases if all(row['arms'][arm]['validation_status'] == 'valid' for arm in ARMS)]
    return common._common_person_months(legal, list(ARMS), list(REPEATS), measure)


def _scalar_metrics(rows, arm, weights):
    if not rows:
        return {key: None for key in ('q9_center_mae_pp', 'q9_center_bias_pp', 'individual_density_mean_mae_pp', 'cross_section_w1_pp', 'cross_person_iqr_pp', 'real_cross_person_iqr_pp')}
    pred = np.asarray([row['baselines'][arm] for row in rows], float)
    real = np.asarray([row['real']['q9_mean'] for row in rows], float)
    return {'q9_center_mae_pp': abs(quantile(pred, weights, .5) - quantile(real, weights, .5)),
            'q9_center_bias_pp': quantile(pred, weights, .5) - quantile(real, weights, .5),
            'individual_density_mean_mae_pp': float(np.average(abs(pred - real), weights=weights)),
            'cross_section_w1_pp': wasserstein1(pred, weights, real, weights),
            'cross_person_iqr_pp': quantile(pred, weights, .75) - quantile(pred, weights, .25),
            'real_cross_person_iqr_pp': quantile(real, weights, .75) - quantile(real, weights, .25)}


def summarize(cases, support, weighted=True):
    result = {}
    for arm in (*ARMS, *BASELINES):
        cells = []
        for month in MONTHS:
            for repeat in REPEATS:
                rows = common._cell_rows(cases, month, repeat, support)
                w = np.asarray([row['design_survey_weight'] if weighted else 1. for row in rows])
                metrics = common._q9_cell_metrics(rows, arm, w) if arm in ARMS else _scalar_metrics(rows, arm, w)
                cells.append({'month': month, 'repeat': repeat, 'n': len(rows), **metrics})
        keys = tuple(key for key in cells[0] if key not in ('month', 'repeat', 'n'))
        aggregate, used = common._aggregate_cells(cells, keys)
        result[arm] = {'aggregate_equal_month_repeat_cells': aggregate, 'cells': cells, 'cells_used_by_metric': used}
    return result


def group_cells(cases, support):
    """Design-weighted subgroup descriptions; sparse groups never change support."""
    dimensions = {'q1': None, 'age': 'age_group', 'numeracy': 'numeracy',
                  'income': 'household_income_band', 'region': 'region'}
    output = []
    for month in MONTHS:
        for repeat in REPEATS:
            rows = common._cell_rows(cases, month, repeat, support)
            assigned = [row for row in cases if row['month'] == month and row['repeat'] == repeat]
            for dimension, field in dimensions.items():
                def label(row):
                    if field is not None:
                        return str(row.get('profile', {}).get(field) or 'missing')
                    code = row.get('current_q1_code')
                    return 'worse' if code in (1, 2) else 'same' if code == 3 else 'better' if code in (4, 5) else 'missing'
                assigned_counts = Counter(label(row) for row in assigned)
                groups = {}
                for name in sorted(assigned_counts):
                    subset = [row for row in rows if label(row) == name]
                    group = {'n_assigned': assigned_counts[name], 'n_common': len(subset),
                             'reported': len(subset) >= 3, 'real_center_pp': None, 'arms': {}}
                    if len(subset) >= 3:
                        weights = np.asarray([row['design_survey_weight'] for row in subset])
                        real = np.asarray([row['real']['q9_mean'] for row in subset])
                        group['real_center_pp'] = quantile(real, weights, .5)
                        for arm in ARMS:
                            pred = np.asarray([row['arms'][arm]['mean'] for row in subset])
                            center = quantile(pred, weights, .5)
                            group['arms'][arm] = {'model_center_pp': center,
                                'q9_center_mae_pp': abs(center - group['real_center_pp']),
                                'individual_density_mean_mae_pp': float(np.average(abs(pred - real), weights=weights)),
                                'cross_section_w1_pp': wasserstein1(pred, weights, real, weights)}
                    else:
                        group['suppression_reason'] = 'Fewer than 3 common people in this month-repeat group.'
                    groups[name] = group
                gaps = []
                for left, right in combinations(sorted(groups), 2):
                    a, b = groups[left], groups[right]
                    gap = {'left': left, 'right': right, 'reported': a['reported'] and b['reported'],
                           'real_median_gap_pp': None, 'arms': {}}
                    if gap['reported']:
                        real_gap = a['real_center_pp'] - b['real_center_pp']
                        gap['real_median_gap_pp'] = real_gap
                        for arm in ARMS:
                            pred_gap = a['arms'][arm]['model_center_pp'] - b['arms'][arm]['model_center_pp']
                            gap['arms'][arm] = {'model_median_gap_pp': pred_gap,
                                'signed_deviation_from_real_gap_pp': pred_gap - real_gap,
                                'absolute_deviation_from_real_gap_pp': abs(pred_gap - real_gap)}
                    else:
                        gap['suppression_reason'] = 'At least one group has fewer than 3 common people.'
                    gaps.append(gap)
                output.append({'month': month, 'repeat': repeat, 'dimension': dimension,
                               'weight': 'design_survey_weight', 'descriptive_only': True,
                               'groups': groups, 'median_group_gaps': gaps})
    return output


def bootstrap(cases, support, draws=1000, seed=SEED):
    """Conditional person-cluster interval for weighted nonlinear center errors."""
    if type(draws) is not int or draws < 1:
        raise ValueError('draws must be positive integer')
    cells = [common._cell_rows(cases, month, repeat, support) for month in MONTHS for repeat in REPEATS]
    people = sorted({row['userid'] for rows in cells for row in rows})
    index = {uid: i for i, uid in enumerate(people)}
    rng = np.random.default_rng(seed)
    samples, attempts = [], 0
    while all(cells) and len(samples) < draws and attempts < draws * 20:
        attempts += 1
        counts = np.bincount(rng.integers(len(people), size=len(people)), minlength=len(people))
        differences = []
        for rows in cells:
            w = np.asarray([counts[index[row['userid']]] * row['design_survey_weight'] for row in rows])
            if w.sum() == 0:
                break
            real = quantile([row['real']['q9_mean'] for row in rows], w, .5)
            errors = {arm: abs(quantile([row['arms'][arm]['mean'] for row in rows], w, .5) - real) for arm in ARMS}
            differences.append(errors['financial_facts'] - errors['baseline'])
        if len(differences) == len(cells):
            samples.append(float(np.mean(differences)))
    return {'interval_95_unadjusted_pp': np.quantile(samples, [.025, .975]).tolist() if samples else None,
            'draws_requested': draws, 'draws_used': len(samples), 'empty_cell_draws': attempts - len(samples), 'seed': seed,
            'exploratory_only': True, 'scope': 'Respondent clusters retain all months/repeats; design weights remain fixed. Conditional on these four selected months; not a time-population interval.'}


def compare(metrics, interval, coverage_ok):
    baseline, facts = (metrics[arm]['aggregate_equal_month_repeat_cells'] for arm in ARMS)
    changes = {key: facts[key] - baseline[key] if common.finite(facts.get(key)) and common.finite(baseline.get(key)) else None
               for key in baseline if key in facts}
    monthly = []
    for month in MONTHS:
        values = {}
        for arm in ARMS:
            cells = [cell for cell in metrics[arm]['cells'] if cell['month'] == month]
            values[arm] = float(np.mean([cell[PRIMARY] for cell in cells])) if all(common.finite(cell[PRIMARY]) for cell in cells) else None
        monthly.append({'month': month, 'baseline_center_mae_pp': values['baseline'], 'facts_center_mae_pp': values['financial_facts'],
                        'facts_minus_baseline_pp': values['financial_facts'] - values['baseline'] if all(common.finite(v) for v in values.values()) else None})
    nonworse = sum(common.finite(row['facts_minus_baseline_pp']) and row['facts_minus_baseline_pp'] <= 0 for row in monthly)
    complete = all(metrics[arm]['cells_used_by_metric'][PRIMARY] == len(MONTHS) * len(REPEATS) for arm in ARMS)
    macro = bool(coverage_ok and complete and common.finite(changes[PRIMARY]) and changes[PRIMARY] < 0 and nonworse >= 3)
    micro_keys = ('individual_density_mean_mae_pp', 'cross_section_w1_pp')
    tradeoff = any(common.finite(changes[key]) and changes[key] > 0 for key in micro_keys)
    micro_complete = all(common.finite(changes[key]) for key in micro_keys)
    ci = interval.get('interval_95_unadjusted_pp')
    return {'primary_metric_difference_pp': changes[PRIMARY], 'metric_point_changes': changes,
            'monthly_center_errors': monthly, 'nonworse_month_count': int(nonworse), **interval,
            'macro_replication_screen': macro, 'micro_tradeoff': tradeoff,
            'no_overall_upgrade': bool(not macro or tradeoff or not micro_complete),
            'exploratory_center_interval_upper_below_zero': bool(ci is not None and ci[1] < 0),
            'interpretation': 'Macro screen only; any positive personal-MAE or W1 change is retained as a tradeoff and prevents an overall upgrade. No 0.2pp tolerance or causal claim.'}


def evaluate(folder, out, draws=1000):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to((ROOT / 'outputs').resolve()):
        raise ValueError('Require fresh output directory under outputs')
    loaded = load(folder)
    cases = loaded['cases']
    support, point_support = _supports(cases), _supports(cases, 'q8')
    coverage = {}
    for arm in ARMS:
        statuses = Counter(row['arms'][arm]['validation_status'] for row in cases)
        scorable = sum(common.finite(row['arms'][arm]['mean']) and common.finite(row['arms'][arm]['iqr']) for row in cases)
        coverage[arm] = {'assigned': N * len(MONTHS) * len(REPEATS), 'validation_status_counts': dict(statuses),
                         'valid_fraction': statuses['valid'] / len(cases), 'scorable_fraction': scorable / len(cases)}
    coverage_ok = all(item['valid_fraction'] >= .99 and item['scorable_fraction'] >= .99 for item in coverage.values())
    weighted, equal = summarize(cases, support), summarize(cases, support, False)
    interval = bootstrap(cases, support, draws, int(loaded['protocol'].get('bootstrap_seed', SEED))) if coverage_ok else {
        'interval_95_unadjusted_pp': None, 'draws_requested': draws, 'draws_used': 0, 'reason': 'Below 99% valid/scorable; accuracy descriptive.'}
    q8 = {}
    for arm in ARMS:
        cells = []
        for month in MONTHS:
            for repeat in REPEATS:
                rows = common._cell_rows(cases, month, repeat, point_support)
                cells.append({'month': month, 'repeat': repeat, **common._q8_cell_metrics(rows, arm, np.asarray([row['design_survey_weight'] for row in rows]))})
        q8[arm] = {'cells': cells, 'aggregate_equal_month_repeat_cells': common._aggregate_cells(cells, common.Q8_METRICS)[0]}
    people = [row for row in cases if row['repeat'] == REPEATS[0]]
    summary = {'status': 'completed_sce_household_finance_crossmonth_evaluation', 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
               'protocol': loaded['protocol'], 'protocol_sha256': loaded['protocol_sha256'], 'primary_metric': PRIMARY,
               'primary_weight': 'design_survey_weight', 'evaluation_api_calls': 0, 'evaluated_llm_calls': 768,
               'coverage': coverage, 'validity_gate_passed': coverage_ok,
               'common_support': {'assigned_person_months': len(people), 'q9_person_months': len(support), 'q8_person_months': len(point_support),
                                  'human_q9_unscorable_person_months': sum(not common.finite(row['real']['q9_mean']) or not common.finite(row['real']['q9_iqr']) for row in people),
                                  'any_model_q9_failure_person_months': sum(any(row['arms'][arm]['validation_status'] != 'valid' or not common.finite(row['arms'][arm]['mean']) or not common.finite(row['arms'][arm]['iqr']) for row in cases if row['month'] == selected['month'] and row['userid'] == selected['userid'] for arm in ARMS) for selected in people),
                                  'human_q8_excluded_outside_100_person_months': sum(row['real']['q8_excluded_outside_100'] for row in people),
                                  'definition': 'All two arms and both repeats legal/scorable on the same truth; missing/invalid responses stay in assigned coverage.'},
               'design_weighted': weighted, 'equal_person_auxiliary': equal, 'q8_design_weighted_secondary': q8,
               'group_cells': group_cells(cases, support),
               'facts_minus_baseline': compare(weighted, interval, coverage_ok),
               'estimated_run_cost_usd_not_bill': loaded['estimated_run_cost_usd'], 'scorer_provenance': provenance(),
               'source_sha256': loaded['source_sha256'], 'prepared_file_count_verified': loaded['prepared_file_count'],
               'evaluator_sha256': {str(Path(__file__).resolve().relative_to(Path(__file__).resolve().parents[3])): common.sha(Path(__file__)),
                                    'shared_cognition_evaluator': common.sha(Path(common.__file__))},
               'raw_replies_reconstructed_and_matched': sum(row['arms'][arm]['response_parsed'] for row in cases for arm in ARMS),
               'individual_update_mae_identity': 'Against the same real prior, |(model-current - prior) - (real-current - prior)| equals |model-current - real-current|; one item of evidence.',
               'scalar_baselines': 'Copy the same real previous belief; history-anchor=.5 previous+.5 mean of strictly earlier scored personal answers if >=2 histories, otherwise copy previous. Scalar baselines do not invent probability bins or individual uncertainty.',
               'weighting': 'Model and matched human use the identical selected-person design_survey_weight within each month/repeat; eight cell metrics get equal weight. Equal-person sensitivity is auxiliary. Spearman is unweighted descriptive correlation.',
               'limitations': ['Four old-framework evaluation months not used to tune Q1; not an overall project blind test.',
                              'Selected 48-person stratified returner samples, not national estimates.',
                              'Current Q1 is contemporaneous A conditional reconstruction, not causal Q1 effects or B real-time forecasts.',
                              'Intervals resample respondents conditional on four months; no inference to a time population or confirmed mechanism.',
                              'All worsening monthly or micro metrics are retained; previous pilot failure is not reversed by this macro screen.']}
    out.mkdir(parents=True)
    for name, value in (('summary.json', summary), ('cases_private.json', cases)):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    return summary
