"""Offline scale-up evaluation: matched sample, eligible returners and full wave.

Preparation audits never parse current outcomes. All 24 completed real cells are
verified before any target bins are read. Frozen fitting and raw-answer parsing
are shared with prior evaluators without changing their globals.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

import duckdb
import numpy as np

from . import cognition as common
from .behavior_comparison import previous_month
from .finance_validation import _scalar_metrics
from .metrics import quantile
from ..revision_format_runtime import DIRECT, REPLY_MARKER, previous_answer
from ..scoring.sce_q9_frozen import provenance
from ..scoring import sce_q9_frozen as scorer_module

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / 'outputs/sce_behavior_mechanism_audit_20261014_v3/reference_with_controls_private.parquet'
MONTHS = (202003, 202009, 202103, 202109, 202206, 202212, 202306, 202312, 202404, 202410, 202503, 202509)
OLD_MONTHS = (202206, 202306, 202410, 202509)
NEW_MONTHS = tuple(m for m in MONTHS if m not in OLD_MONTHS)
SCOPES = {'new_months': NEW_MONTHS, 'old_months': OLD_MONTHS, 'all_months': MONTHS}
ARMS = ('reference',)
BASELINES = ('copy_previous', 'history_anchor_half')
REPEATS = (1, 2)
N = 192
SEED = 20261017
RESEARCH_LINE = 'A_conditional_returner_reconstruction'
REF = 'sce_inflation_expectations.reference_validation_decision'
PROMPT = 'sce-q8-q9-reference-validation-v1'
SCORER_KEY = hashlib.sha256(json.dumps({
    'pinned': provenance()['pinned_sha256'], 'wrapper': common.sha(Path(scorer_module.__file__))
}, sort_keys=True).encode()).hexdigest()


@lru_cache(maxsize=None)
def _fit_cached(scorer_key, bins):
    if len(bins) != 10 or not all(common.finite(v) for v in bins):
        return {'mean': None, 'iqr': None, 'zero_deflation': None, 'scorer_status': 'missing_bins'}
    return common._score_bins(list(bins))


def score(bins):
    """Same legal/scoring gates for model and human; source-keyed bin dedup."""
    return dict(_fit_cached(SCORER_KEY, tuple(bins)))


def _validate_protocol(protocol, manifest):
    expected = {'id': 'sce-reference-scaleup-v1', 'research_line': RESEARCH_LINE,
                'months': list(MONTHS), 'old_months': list(OLD_MONTHS), 'new_months': list(NEW_MONTHS),
                'arms': list(ARMS), 'n_per_month': N, 'generation_repeats': list(REPEATS),
                'planned_calls': 4608, 'primary_metric': 'q9_center_mae_pp',
                'primary_weight': 'design_survey_weight', 'primary_month_scope': 'new_months',
                'model': 'deepseek-flash', 'temperature': .5, 'max_tokens': 1024, 'thinking': 'disabled', 'retry_max': 0}
    for key, value in expected.items():
        if protocol.get(key) != value:
            raise ValueError(f'Reference scale-up protocol mismatch: {key}')
    if (any(type(v) is not int for v in protocol['months'] + protocol['generation_repeats'])
            or type(protocol['n_per_month']) is not int or type(protocol['planned_calls']) is not int
            or type(manifest.get('planned_calls')) is not int or manifest['planned_calls'] != 4608):
        raise ValueError('Invalid registered integer counts')


def audit_prepared(folder):
    """Hash and roster audit; identifiers are checked locally, never published."""
    folder = Path(folder).resolve()
    manifest, protocol = (common._read_json(folder / name) for name in ('manifest.json', 'protocol.json'))
    _validate_protocol(protocol, manifest)
    protocol_hash = common.sha(folder / 'protocol.json')
    if manifest.get('protocol_sha256') != protocol_hash:
        raise ValueError('Protocol hash mismatch')
    required = {'protocol.json', 'evaluation_links_private.json'}
    names = ('population', 'environment', 'past_private', 'eligible_ids_private', 'nested_subsamples_private', 'preview_reference', 'simulation_reference')
    required.update(f'{month}/{name}.json' for month in MONTHS for name in names)
    declared = manifest.get('prepared_file_sha256')
    if not isinstance(declared, dict) or not required.issubset(declared):
        raise ValueError('Required prepared inputs are not pinned')
    verified = common._verify_declared_hashes(folder, declared, 'prepared')
    source_name = str(REFERENCE.resolve().relative_to(ROOT.resolve()))
    sources = common._verify_declared_hashes(ROOT, manifest.get('source_sha256'), 'evaluation source', {source_name})
    links = common._read_json(folder / 'evaluation_links_private.json')
    if not isinstance(links, list) or len(links) != N * len(MONTHS):
        raise ValueError('Expected exactly 2304 selected person-months')
    previews, eligible, nested = {}, {}, {}
    seed_set = None
    for month in MONTHS:
        selected = [row for row in links if row.get('month') == month]
        ids = {row['agent_id'] for row in selected}
        if len(selected) != N or len(ids) != N or len({row['userid'] for row in selected}) != N:
            raise ValueError('Selected roster has duplicate or missing people')
        for row in selected:
            w, raw, pi = (row.get(key) for key in ('design_survey_weight', 'survey_weight', 'inclusion_probability'))
            if (not isinstance(row['agent_id'], str) or not row['agent_id'] or type(row['userid']) is not int
                    or not isinstance(row.get('stratum'), str) or not row['stratum']
                    or not all(common.finite(v) for v in (w, raw, pi)) or raw <= 0 or w <= 0 or not 0 < pi <= 1
                    or not np.isclose(w, raw / pi, rtol=1e-10, atol=1e-10)):
                raise ValueError('Invalid selected design weight or stratum')
        eligible[month] = common._read_json(folder / str(month) / 'eligible_ids_private.json')
        if (not isinstance(eligible[month], list) or any(type(uid) is not int for uid in eligible[month])
                or len(set(eligible[month])) != len(eligible[month])
                or not {row['userid'] for row in selected}.issubset(set(eligible[month]))):
            raise ValueError('Invalid eligible-returner identifiers')
        nested[month] = common._read_json(folder / str(month) / 'nested_subsamples_private.json')
        draws = nested[month]
        if not isinstance(draws, list) or len(draws) != 30 or any(not isinstance(draw, dict) for draw in draws):
            raise ValueError('Expected thirty prespecified nested samples')
        seeds = {draw.get('seed') for draw in draws}
        if len(seeds) != 30 or any(type(seed) is not int for seed in seeds) or (seed_set is not None and seeds != seed_set):
            raise ValueError('Nested sampling seeds must be unique and identical across months')
        seed_set = seeds
        for draw in draws:
            a, b = draw.get('ids_48'), draw.get('ids_96')
            if (set(draw) != {'seed', 'ids_48', 'ids_96'} or not isinstance(a, list) or not isinstance(b, list)
                    or len(a) != 48 or len(set(a)) != 48 or len(b) != 96 or len(set(b)) != 96
                    or not set(a).issubset(set(b)) or not set(b).issubset(ids)):
                raise ValueError('Nested sets must satisfy 48 subset 96 subset 192')
        previews[month, 'reference'] = common._validate_preview(folder, month, 'reference', ids)
        cfg = common._read_json(folder / str(month) / 'simulation_reference.json')
        args = cfg.get('decision_args', {})
        bundle = args.get('reference_validation_bundle', {})
        if (cfg.get('decision_ref') != REF or args.get('prompt_version') != PROMPT
                or set(bundle) != {'parent', 'messages_sha256'} or not isinstance(bundle['parent'], dict)
                or bundle['messages_sha256'] != {agent: row['prompt_sha256'] for agent, row in previews[month, 'reference'].items()}):
            raise ValueError('Reference provider or exact frozen messages mismatch')
        past = common._read_json(folder / str(month) / 'past_private.json')
        if not isinstance(past, dict) or set(past) != ids:
            raise ValueError('Past-record roster mismatch')
        for agent in ids:
            messages = previews[month, 'reference'][agent]['messages']
            if (len(messages) != 1 or messages[0].get('role') != 'user' or not isinstance(messages[0].get('content'), str)
                    or messages[0]['content'].count(REPLY_MARKER) != 1 or not messages[0]['content'].endswith(DIRECT)
                    or 'Publication timing for the same information above:' not in messages[0]['content']
                    or 'Your household financial circumstances:' in messages[0]['content']):
                raise ValueError('Dated/direct/prior reference without a Q1 block required')
            prior = previous_answer(messages)
            frozen = past[agent].get('prior', {})
            if (prior != {key: frozen.get(key) for key in ('point_pct', 'q9')}
                    or str(frozen.get('source_month', '')).replace('-', '') != str(previous_month(month))):
                raise ValueError('Actual prior differs from frozen immediately previous record')
    jobs = manifest.get('jobs', [])
    expected_jobs = {(m, 'reference', r) for m in MONTHS for r in REPEATS}
    if (len(jobs) != 24 or {(job.get('month'), job.get('arm'), job.get('repeat')) for job in jobs} != expected_jobs
            or len({job.get('run_id') for job in jobs}) != 24):
        raise ValueError('Require exactly 24 unique reference jobs')
    return {'folder': folder, 'manifest': manifest, 'protocol': protocol, 'protocol_sha256': protocol_hash,
            'links': links, 'previews': previews, 'eligible': eligible, 'nested': nested,
            'source_sha256': {**sources, **verified}, 'prepared_file_count': len(verified)}


def _audit_job(prepared, job):
    if not isinstance(job.get('run_id'), str) or not re.fullmatch(r'[A-Za-z0-9._-]+', job['run_id']):
        raise ValueError('Unsafe run identifier')
    month, repeat = job['month'], job['repeat']
    directory = common._safe_relative(ROOT / 'outputs/local_runs', job['run_id'])
    paths = [directory / name for name in ('run_manifest.json', 'study.duckdb', 'llm_calls.jsonl', 'frozen_preview.json')]
    if any(not path.is_file() for path in paths):
        raise ValueError(f'Missing completed-run evidence: {job["run_id"]}')
    run = common._read_json(paths[0])
    expected = {'status': 'completed', 'run_id': job['run_id'], 'month': month, 'arm': 'reference', 'repeat': repeat,
                'llm_kind': 'openai', 'n': N, 'new_api_calls': N, 'actual_input_hashes_match': True,
                'protocol_sha256': prepared['protocol_sha256']}
    if any(run.get(key) != value for key, value in expected.items()) or run.get('cost', {}).get('call_count') != N:
        raise ValueError('Completed run manifest/call-count mismatch')
    if common.sha(paths[3]) != common.sha(prepared['folder'] / str(month) / 'preview_reference.json'):
        raise ValueError('Run frozen preview differs from prepared preview')
    calls = [json.loads(line) for line in paths[2].read_text().splitlines() if line.strip()]
    previews = prepared['previews'][month, 'reference']
    if len(calls) != N or len({call['agent_id'] for call in calls}) != N or {call['agent_id'] for call in calls} != set(previews):
        raise ValueError('Original-call roster/cardinality mismatch')
    db = duckdb.connect(str(paths[1]), read_only=True)
    try:
        rows = db.execute("SELECT agent_id,action_payload FROM panel WHERE step=1 AND action_kind='sce_answer'").fetchall()
    finally:
        db.close()
    if len(rows) != N or len({str(agent) for agent, _ in rows}) != N or {str(agent) for agent, _ in rows} != set(previews):
        raise ValueError('DuckDB action roster/cardinality mismatch')
    actions = {str(agent): json.loads(raw) if isinstance(raw, str) else raw for agent, raw in rows}
    result, p = {}, prepared['protocol']
    for call in calls:
        agent = call['agent_id']; preview = previews[agent]; action = actions[agent]
        request = {'run_id': job['run_id'], 'attempt_idx': 0, 'target_month': f'{month // 100:04d}-{month % 100:02d}',
                   'requested_model': p['model'], 'temperature': p['temperature'], 'max_tokens': p['max_tokens'],
                   'extra_body': {'thinking': {'type': p['thinking']}}, 'prompt_version': PROMPT,
                   'prompt_sha256': preview['prompt_sha256'], 'prompt_text': json.dumps(preview['messages'], ensure_ascii=False)}
        metadata = {'reference_validation_arm': 'reference', 'actual_messages_sha256': preview['prompt_sha256'], 'research_line': RESEARCH_LINE}
        if any(call.get(k) != v for k, v in request.items()) or any(action.get(k) != v for k, v in metadata.items()):
            raise ValueError('Original call or action differs from frozen reference request')
        raw = call.get('raw_response_text') or ''
        if hashlib.sha256(raw.encode()).hexdigest() != call.get('raw_response_sha256'):
            raise ValueError('Original reply hash mismatch')
        parsed, error = common._audit_raw_reply(raw, call, action, 'reference')
        bins = common._action_bins(action)
        fitted = common._score_bins(bins) if action['validation_status'] == 'valid' else {'mean': None, 'iqr': None, 'zero_deflation': None, 'scorer_status': 'invalid_response'}
        result[agent] = {**fitted, 'q9_bins': bins, 'point': common._float_or_none(action.get('point_pct')) if parsed else None,
                         'validation_status': action['validation_status'], 'response_parsed': parsed is not None, 'parse_error': error}
    return result, {str(path.relative_to(ROOT)): common.sha(path) for path in paths}, float(run['cost'].get('estimated_cost_usd', 0))


def _read_truth(prepared):
    """Read full target/prior waves and selected histories only after real completion."""
    months = sorted(set(MONTHS) | {previous_month(m) for m in MONTHS})
    ids = sorted({row['userid'] for row in prepared['links']})
    fields = ['date', 'userid', 'weight', 'Q8v2part2', *[f'Q9_bin{i}' for i in range(1, 11)]]
    db = duckdb.connect()
    try:
        frame = db.execute(f'SELECT {",".join(fields)} FROM read_parquet(?) WHERE date IN ({",".join("?" for _ in months)}) OR (userid IN ({",".join("?" for _ in ids)}) AND date<?)',
                           [str(REFERENCE), *months, *ids, max(MONTHS)]).df()
    finally:
        db.close()
    if frame.duplicated(['date', 'userid']).any():
        raise ValueError('Reference contains duplicate respondent-months')
    lookup = {}
    for record in frame.to_dict('records'):
        bins = [common._float_or_none(record[f'Q9_bin{i}']) for i in range(1, 11)]
        fitted = score(bins)
        point = common._float_or_none(record['Q8v2part2'])
        lookup[int(record['date']), int(record['userid'])] = {
            'q9_mean': fitted['mean'], 'q9_iqr': fitted['iqr'], 'q9_zero_deflation': fitted['zero_deflation'],
            'q9_bins': bins, 'q8_point': point if point is not None and abs(point) <= 100 else None,
            'q8_outside_100': point is not None and abs(point) > 100, 'weight': common._float_or_none(record['weight'])}
    history = {}
    by_person = defaultdict(list)
    for (month, uid), fitted in lookup.items():
        if common.finite(fitted['q9_mean']):
            by_person[uid].append((month, fitted['q9_mean']))
    for link in prepared['links']:
        month, uid = link['month'], link['userid']
        earlier = [value for date, value in by_person[uid] if date < month]
        prior = lookup.get((previous_month(month), uid), {}).get('q9_mean')
        anchor = float(np.mean(earlier)) if len(earlier) >= 2 else None
        history[month, link['agent_id']] = {'history_n': len(earlier), 'copy_previous': prior,
            'history_anchor_half': prior + .5 * (anchor - prior) if common.finite(prior) and anchor is not None else prior}
    centers = {}
    for month in MONTHS:
        def center(date, allowed=None):
            selected = [row for (m, uid), row in lookup.items() if m == date and (allowed is None or uid in allowed)]
            usable = [row for row in selected if common.finite(row['q9_mean']) and common.finite(row['weight']) and row['weight'] > 0]
            return {'center_pp': quantile([row['q9_mean'] for row in usable], [row['weight'] for row in usable], .5) if usable else None,
                    'n_assigned': len(selected), 'n_scorable_positive_weight': len(usable), 'n_excluded': len(selected) - len(usable)}
        eligible_ids = set(prepared['eligible'][month])
        if not eligible_ids.issubset({uid for date, uid in lookup if date == month}):
            raise ValueError('Eligible-returner list is absent from current full wave')
        centers[month] = {'full_wave': center(month), 'eligible_returners': center(month, eligible_ids),
                          'previous_full_wave': center(previous_month(month))}
    return lookup, history, centers


def load(folder):
    prepared = audit_prepared(folder)
    if not provenance()['live_matches_pinned']:
        raise ValueError('Frozen Q9 scorer has changed')
    actions, hashes, cost = {}, dict(prepared['source_sha256']), 0.
    for job in prepared['manifest']['jobs']:
        results, verified, estimated = _audit_job(prepared, job)
        actions[job['month'], job['repeat']] = results
        hashes.update(verified); cost += estimated
    lookup, history, centers = _read_truth(prepared)
    cases = []
    for link in prepared['links']:
        month, agent, uid = link['month'], link['agent_id'], link['userid']
        if (month, uid) not in lookup or (previous_month(month), uid) not in lookup:
            raise ValueError('Selected respondent lacks current or strict previous raw reference')
        current, previous = lookup[month, uid], lookup[previous_month(month), uid]
        if not common.finite(current['weight']) or not np.isclose(link['survey_weight'], current['weight'], rtol=1e-10, atol=1e-10):
            raise ValueError('Selected survey weight differs from the raw reference wave')
        prior = previous_answer(prepared['previews'][month, 'reference'][agent]['messages'])
        if (not common.finite(previous['q9_mean'])
                or not np.allclose([prior['q9'][f'bin{i}'] for i in range(1, 11)], previous['q9_bins'], rtol=0, atol=1e-8)
                or common.finite(prior['point_pct']) != common.finite(previous['q8_point'])
                or (common.finite(prior['point_pct']) and not np.isclose(prior['point_pct'], previous['q8_point'], rtol=0, atol=1e-8))):
            raise ValueError('Prompt prior differs from independently scored strict prior truth')
        real = {**current, 'previous_q9_mean': previous['q9_mean'], 'previous_q9_bins': previous['q9_bins']}
        for repeat in REPEATS:
            cases.append({**link, 'repeat': repeat, 'real': real, 'arms': {'reference': actions[month, repeat][agent]},
                          'baselines': {key: history[month, agent][key] for key in BASELINES}, 'history_n': history[month, agent]['history_n']})
    return {**prepared, 'cases': cases, 'centers': centers, 'source_sha256': hashes, 'estimated_run_cost_usd': cost}


def _support(cases, measure='q9'):
    legal = [row for row in cases if row['arms']['reference']['validation_status'] == 'valid']
    return common._common_person_months(legal, ['reference'], list(REPEATS), measure)


def signed_decomposition(simulated, sampled, eligible, full):
    """A signed telescoping identity, not a decomposition of absolute errors."""
    if not all(common.finite(v) for v in (simulated, sampled, eligible, full)):
        return {'model_minus_sample_pp': None, 'sample_minus_eligible_pp': None, 'eligible_minus_full_pp': None,
                'sum_components_pp': None, 'model_minus_full_pp': None, 'identity_residual_pp': None}
    components = [simulated - sampled, sampled - eligible, eligible - full]
    return {'model_minus_sample_pp': components[0], 'sample_minus_eligible_pp': components[1], 'eligible_minus_full_pp': components[2],
            'sum_components_pp': sum(components), 'model_minus_full_pp': simulated - full,
            'identity_residual_pp': sum(components) - (simulated - full)}


def summarize_cells(cases, centers, support, selected_ids=None, sample_size=N):
    cells = []
    for month in MONTHS:
        allowed = None if selected_ids is None else set(selected_ids[month])
        for repeat in REPEATS:
            assigned = [row for row in cases if row['month'] == month and row['repeat'] == repeat and (allowed is None or row['agent_id'] in allowed)]
            rows = [row for row in assigned if (row['month'], row['userid']) in support]
            # Nested subsets are SRS conditional on the archived 192-person draw.
            # Multiplying by 192/n is a common cell factor, still explicitly kept.
            factor = N / sample_size
            w = np.asarray([row['design_survey_weight'] * factor for row in rows])
            metrics = common._q9_cell_metrics(rows, 'reference', w)
            scalar = {arm: _scalar_metrics(rows, arm, w) for arm in BASELINES}
            target = centers[month]
            full = target['full_wave']['center_pp']; eligible = target['eligible_returners']['center_pp']
            simulated = quantile([row['arms']['reference']['mean'] for row in rows], w, .5) if rows else None
            sampled = quantile([row['real']['q9_mean'] for row in rows], w, .5) if rows else None
            assigned_truth = [row for row in assigned if common.finite(row['real']['q9_mean'])]
            assigned_center = quantile([row['real']['q9_mean'] for row in assigned_truth],
                                       [row['design_survey_weight'] * factor for row in assigned_truth], .5) if assigned_truth else None
            base_centers = {arm: quantile([row['baselines'][arm] for row in rows], w, .5) if rows else None for arm in BASELINES}
            def error(pred, truth):
                return abs(pred - truth) if common.finite(pred) and common.finite(truth) else None
            cells.append({'month': month, 'repeat': repeat, 'sample_size_assigned': len(assigned), 'common_scorable_n': len(rows),
                          'assigned_truth_scorable_n': len(assigned_truth), 'conditional_nested_inclusion_probability': sample_size / N,
                          'simulated_center_pp': simulated, 'matched_sample_truth_center_pp': sampled,
                          'assigned_sample_truth_center_pp': assigned_center, 'eligible_center_pp': eligible, 'full_wave_center_pp': full,
                          'assigned_truth_minus_matched_truth_pp': assigned_center - sampled if common.finite(assigned_center) and common.finite(sampled) else None,
                          'model_metrics_same_sample': metrics, 'scalar_baseline_metrics_same_sample': scalar,
                          'reference_vs_full_wave_center_mae_pp': error(simulated, full),
                          'reference_vs_eligible_center_mae_pp': error(simulated, eligible),
                          'copy_previous_center_mae_pp': error(base_centers['copy_previous'], sampled),
                          'history_anchor_half_center_mae_pp': error(base_centers['history_anchor_half'], sampled),
                          'previous_full_wave_carry_center_mae_pp': error(target['previous_full_wave']['center_pp'], full),
                          'signed_center_decomposition': signed_decomposition(simulated, sampled, eligible, full)})
    return cells


def aggregate_scopes(cells):
    result = {}
    for scope, months in SCOPES.items():
        selected = [row for row in cells if row['month'] in months]
        model, used = common._aggregate_cells([row['model_metrics_same_sample'] for row in selected], common.Q9_METRICS)
        macro_keys = ('reference_vs_full_wave_center_mae_pp', 'reference_vs_eligible_center_mae_pp', 'copy_previous_center_mae_pp',
                      'history_anchor_half_center_mae_pp', 'previous_full_wave_carry_center_mae_pp')
        macro, counts = common._aggregate_cells(selected, macro_keys)
        model = {key: value if used[key] == len(selected) else None for key, value in model.items()}
        macro = {key: value if counts[key] == len(selected) else None for key, value in macro.items()}
        scalar_aggregates = {}
        for arm in BASELINES:
            scalar_cells = [row['scalar_baseline_metrics_same_sample'][arm] for row in selected]
            values, scalar_used = common._aggregate_cells(scalar_cells, tuple(scalar_cells[0]))
            scalar_aggregates[arm] = {'metrics': {key: value if scalar_used[key] == len(selected) else None for key, value in values.items()},
                                      'cells_used_by_metric': scalar_used}
        result[scope] = {'months': list(months), 'n_time_observations': len(months), 'expected_repeat_cells': len(months) * len(REPEATS),
                         'model_metrics_equal_month_repeat_cells': model, 'cells_used_by_metric': used,
                         'macro_center_errors': macro, 'macro_cells_used_by_metric': counts,
                         'scalar_baselines_equal_month_repeat_cells': scalar_aggregates}
    return result


def project_goal_diagnostics(cells):
    """Describe .3pp without turning a favourable overall mean into stability."""
    result = {}
    for scope, months in SCOPES.items():
        result[scope] = {}
        for label, getter in (
                ('matched_sample', lambda c: c['model_metrics_same_sample']['q9_center_mae_pp']),
                ('full_wave', lambda c: c['reference_vs_full_wave_center_mae_pp'])):
            monthly = {}
            by_repeat = {}
            for month in months:
                values = [getter(c) for c in cells if c['month'] == month]
                monthly[str(month)] = float(np.mean(values)) if len(values) == 2 and all(common.finite(v) for v in values) else None
            for repeat in REPEATS:
                values = [getter(c) for c in cells if c['month'] in months and c['repeat'] == repeat]
                by_repeat[str(repeat)] = float(np.mean(values)) if len(values) == len(months) and all(common.finite(v) for v in values) else None
            valid = [v for v in monthly.values() if common.finite(v)]
            result[scope][label] = {'monthly_repeat_average_mae_pp': monthly,
                'months_below_or_equal_point3': sum(v <= .3 for v in valid), 'months_scored': len(valid),
                'months_planned': len(months), 'worst_month_mae_pp': max(valid) if valid else None,
                'separate_generation_mae_pp': by_repeat,
                'note': 'Project goal, not a literature threshold; monthly average over two absolute errors, not error of the average prediction.'}
    return result


def descriptive_groups(cases, support):
    """Prespecified groups with within-cell survey/design weights, no fitting."""
    fields = ('age_group', 'household_income_band', 'numeracy', 'education_group',
              'region', 'housing_tenure', 'employment_status')
    output = {}
    for scope, months in SCOPES.items():
        output[scope] = {}
        selected = [r for r in cases if r['month'] in months and (r['month'], r['userid']) in support]
        for field in fields:
            values = sorted({str(r['profile'].get(field, 'unknown')) for r in selected})
            output[scope][field] = {}
            for value in values:
                cells = []
                for month in months:
                    for repeat in REPEATS:
                        rows = [r for r in selected if r['month'] == month and r['repeat'] == repeat
                                and str(r['profile'].get(field, 'unknown')) == value]
                        if len(rows) < 3:
                            cells.append({'month': month, 'repeat': repeat, 'n': len(rows), 'suppressed': True})
                            continue
                        w = np.asarray([r['design_survey_weight'] for r in rows])
                        cells.append({'month': month, 'repeat': repeat, 'n': len(rows), 'suppressed': False,
                            'model': common._q9_cell_metrics(rows, 'reference', w),
                            'copy_previous': _scalar_metrics(rows, 'copy_previous', w)})
                valid = [c['model'] for c in cells if not c['suppressed']]
                metrics, counts = common._aggregate_cells(valid, common.Q9_METRICS)
                output[scope][field][value] = {'cells': cells, 'descriptive_means_on_reportable_cells': metrics,
                    'cells_used_by_metric': counts, 'cells_planned': len(months)*2,
                    'note': 'Descriptive group association only; suppressed or missing cells not filled. Partial coverage is not the full-period group mean.'}
    return output


def year_block_bootstrap(cells, draws=1000, seed=SEED):
    """First average repeats within month; resample all selected months in a year."""
    if type(draws) is not int or draws < 1:
        raise ValueError('draws must be positive integer')
    monthly = {}
    for month in MONTHS:
        selected = [row for row in cells if row['month'] == month]
        values = {'reference_same_sample_mae_pp': [row['model_metrics_same_sample']['q9_center_mae_pp'] for row in selected],
                  'reference_full_wave_mae_pp': [row['reference_vs_full_wave_center_mae_pp'] for row in selected],
                  'reference_minus_copy_previous_mae_pp': [row['model_metrics_same_sample']['q9_center_mae_pp'] - row['copy_previous_center_mae_pp']
                                                          if common.finite(row['model_metrics_same_sample']['q9_center_mae_pp']) and common.finite(row['copy_previous_center_mae_pp']) else None for row in selected],
                  'reference_minus_full_wave_carry_mae_pp': [row['reference_vs_full_wave_center_mae_pp'] - row['previous_full_wave_carry_center_mae_pp']
                                                            if common.finite(row['reference_vs_full_wave_center_mae_pp']) and common.finite(row['previous_full_wave_carry_center_mae_pp']) else None for row in selected]}
        monthly[month] = {key: float(np.mean(v)) if len(v) == len(REPEATS) and all(common.finite(x) for x in v) else None for key, v in values.items()}
    result = {}
    for scope, months in SCOPES.items():
        years = sorted({month // 100 for month in months})
        rng = np.random.default_rng(seed)
        by_metric = {}
        for key in next(iter(monthly.values())):
            if any(not common.finite(monthly[m][key]) for m in months):
                by_metric[key] = {'interval_95_unadjusted_pp': None, 'draws_used': 0, 'reason': 'Incomplete monthly support; missing months are retained.'}
                continue
            samples = []
            for _ in range(draws):
                blocks = rng.choice(years, size=len(years), replace=True)
                values = [monthly[m][key] for year in blocks for m in months if m // 100 == year]
                samples.append(float(np.mean(values)))
            by_metric[key] = {'point_mean_pp': float(np.mean([monthly[m][key] for m in months])),
                              'interval_95_unadjusted_pp': np.quantile(samples, [.025, .975]).tolist(), 'draws_used': draws}
        result[scope] = {'n_months': len(months), 'n_year_blocks': len(years), 'draws_requested': draws, 'seed': seed,
                         'exploratory_only': True, 'metrics': by_metric,
                         'method': 'Repeats averaged within month; selected months from the same year travel together. Month is the macro unit; 12×192 people are not independent time observations.'}
    return result


def nested_sampling(cases, centers, support, nested):
    seed_set = sorted({draw['seed'] for draws in nested.values() for draw in draws})
    per_seed, monthly = [], []
    for seed in seed_set:
        draws = {month: next(draw for draw in nested[month] if draw['seed'] == seed) for month in MONTHS}
        for size in (48, 96):
            ids = {month: draws[month][f'ids_{size}'] for month in MONTHS}
            cells = summarize_cells(cases, centers, support, ids, size)
            per_seed.append({'seed': seed, 'sample_size': size, 'scopes': aggregate_scopes(cells)})
            monthly.extend({'seed': seed, 'sample_size': size, 'month': row['month'], 'repeat': row['repeat'],
                            'common_scorable_n': row['common_scorable_n'], 'simulated_center_pp': row['simulated_center_pp'],
                            'same_sample_center_mae_pp': row['model_metrics_same_sample']['q9_center_mae_pp'],
                            'full_wave_center_mae_pp': row['reference_vs_full_wave_center_mae_pp']} for row in cells)
    ranges = {}
    for size in (48, 96):
        ranges[str(size)] = {}
        for scope in SCOPES:
            ranges[str(size)][scope] = {}
            for label, source, key in (('same_sample_center_mae_pp', 'model_metrics_equal_month_repeat_cells', 'q9_center_mae_pp'),
                                       ('full_wave_center_mae_pp', 'macro_center_errors', 'reference_vs_full_wave_center_mae_pp')):
                values = [row['scopes'][scope][source][key] for row in per_seed if row['sample_size'] == size]
                finite = [v for v in values if common.finite(v)]
                ranges[str(size)][scope][label] = {'seeds_requested': len(seed_set), 'seeds_scorable': len(finite),
                    'min_q025_median_q975_max_pp': np.quantile(finite, [0, .025, .5, .975, 1]).tolist() if finite else None}
    return {'prespecified_seed_count': len(seed_set), 'by_seed': per_seed, 'monthly_seed_cells': monthly, 'sampling_ranges': ranges,
            'interpretation': 'All thirty prespecified SRS permutations are retained; 48⊂96⊂192 uses the same archived model answers. Conditional inclusion n/192 multiplies inverse design weights; no best seed is selected. Sampling ranges are not model reruns or confidence intervals.'}


def evaluate(folder, out, draws=1000):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to((ROOT / 'outputs').resolve()):
        raise ValueError('Require fresh output directory under outputs')
    loaded = load(folder)
    cases, centers = loaded['cases'], loaded['centers']
    support, point_support = _support(cases), _support(cases, 'q8')
    cells = summarize_cells(cases, centers, support)
    statuses = Counter(row['arms']['reference']['validation_status'] for row in cases)
    scorable = sum(common.finite(row['arms']['reference']['mean']) and common.finite(row['arms']['reference']['iqr']) for row in cases)
    people = [row for row in cases if row['repeat'] == REPEATS[0]]
    model_failed = {(row['month'], row['userid']) for row in cases
                    if row['arms']['reference']['validation_status'] != 'valid'
                    or not common.finite(row['arms']['reference']['mean']) or not common.finite(row['arms']['reference']['iqr'])}
    q8 = []
    for month in MONTHS:
        for repeat in REPEATS:
            rows = common._cell_rows(cases, month, repeat, point_support)
            q8.append({'month': month, 'repeat': repeat, 'n': len(rows), **common._q8_cell_metrics(rows, 'reference', np.asarray([row['design_survey_weight'] for row in rows]))})
    summary = {'status': 'completed_sce_reference_scaleup_evaluation', 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
               'protocol': loaded['protocol'], 'protocol_sha256': loaded['protocol_sha256'], 'evaluation_api_calls': 0,
               'evaluated_llm_calls': 4608, 'primary_month_scope': 'new_months', 'primary_weight': 'design_survey_weight',
               'coverage': {'assigned': len(cases), 'validation_status_counts': dict(statuses), 'valid_fraction': statuses['valid'] / len(cases),
                            'scorable_fraction': scorable / len(cases), 'q9_common_person_months': len(support), 'q8_common_person_months': len(point_support),
                            'human_q9_missing_or_unscorable_person_months': sum(not common.finite(row['real']['q9_mean']) or not common.finite(row['real']['q9_iqr']) for row in people),
                            'any_repeat_model_q9_failure_person_months': len(model_failed), 'assigned_person_months': len(people),
                            'missingness_counts_can_overlap': True},
               'cells': cells, 'scopes': aggregate_scopes(cells), 'wave_centers': {str(m): value for m, value in centers.items()},
               'point3_project_goal_diagnostics': project_goal_diagnostics(cells),
               'prespecified_descriptive_groups': descriptive_groups(cases, support),
               'macro_exploratory_year_block_intervals': year_block_bootstrap(cells, draws, int(loaded['protocol'].get('bootstrap_seed', SEED))),
               'q8_secondary_cells': q8, 'nested_sampling': nested_sampling(cases, centers, support, loaded['nested']),
               'estimated_run_cost_usd_not_provider_bill': loaded['estimated_run_cost_usd'],
               'raw_replies_reconstructed_and_matched': sum(row['arms']['reference']['response_parsed'] for row in cases),
               'scorer_provenance': provenance(), 'fitter_cache': {'scorer_source_key': SCORER_KEY,
                   'hits': _fit_cached.cache_info().hits, 'distinct_bin_vectors': _fit_cached.cache_info().currsize,
                   'scope': 'Process-local source-hash and raw-ten-bin content cache; no approximate bin merging.'},
               'source_sha256': loaded['source_sha256'],
               'evaluator_sha256': {str(Path(__file__).resolve().relative_to(Path(__file__).resolve().parents[3])): common.sha(Path(__file__))},
               'baseline_status': {'copy_previous': 'implemented_same_person_same_support', 'history_anchor_half': 'implemented_strictly_earlier_histories_fixed_half_coefficient',
                                   'previous_full_wave_center_carry': 'implemented_same_frozen_fitter_raw_previous_wave', 'AR1': 'not_implemented'},
               'limitations': ['Primary eight newly added months, previously seen four months and all twelve are reported separately; not an overall project blind test.',
                              'Sample design weights use inverse selection probabilities; full-wave and eligible-returner centers use original survey weights and the same raw-bin frozen approximate scorer.',
                              'Signed center differences telescope; absolute component errors must not be added. Assigned-truth and model-common-support sample centers are both retained.',
                              'Current returner histories are A conditional reconstruction, not B real-time forecasting. Eligible returners differ from the full wave.',
                              'Macro time uncertainty is exploratory with at most six year blocks; micro results are point descriptions.',
                              'Nested 48/96 subsets reuse the 192 outputs and do not add model generations; .213 from old sizing is not a lower bound.',
                              'No Q1 intervention, automatic default upgrade, national forecasting success or confirmed causal mechanism is established by these outputs.']}
    out.mkdir(parents=True)
    for name, value in (('summary.json', summary), ('cases_private.json', cases)):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    return summary
