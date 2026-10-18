"""Post-hoc profiles of human/model update mismatches, using cached data only.

Three descriptive blocks: prior/public-statistic alignment and P profiles;
measured household state/risk/history; response-format habits. This is not a
classifier, intervention, causal estimate, or replacement for repeat-cell scores.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np

from .response_gap import (ROOT, MONTHS, GROUP_FIELDS, THRESHOLDS, prepare_pairs,
                           finite, direction, ess, quantile)

SOURCE = ROOT / 'outputs/sce_reference_validation_evaluation_20261017_v1'
PREPARED = ROOT / 'outputs/sce_reference_validation_trial_20261017_v2'
TRAITS = ROOT / 'outputs/sce_population_associations_20261015_v1/analysis_frame_private.parquet'
Q2_FOLDER = ROOT / 'outputs/sce_history_mechanism_diagnostic_20261017_v2'
P_FIELDS = tuple(GROUP_FIELDS.values())
HISTORY = ('prior_iqr_pp', 'anchor_gap_pp', 'anchor_available', 'history_n')
FEATURES = ('prior_mean_pp', 'prior_minus_cpi_pp', 'abs_prior_minus_cpi_pp', 'prior_iqr_pp',
            'history_anchor_pp', 'anchor_gap_pp', 'history_n', 'history_cached_sd_pp',
            'prior_zero_deflation', 'prior_active_bins', 'prior_probabilities_multiple_5',
            'prior_point_integer', 'prior_point_multiple_5', 'prior_point_minus_q9_pp',
            'truth_same_bins_as_prior', 'truth_point_same_as_prior', 'truth_point_minus_q9_pp',
            'model_point_minus_q9_pp', 'truth_abs_delta_pp', 'model_abs_delta_pp',
            'model_minus_truth_pp', 'prior_outlook_worse', 'current_outlook_worse',
            'prior_finances_worse', 'current_finances_worse', 'outlook_became_worse',
            'finances_became_worse')
REFERENCES = {'age_group': '40 to 60', 'household_income_band': 'over_100k',
              'education_group': 'college', 'numeracy': 'high', 'region': 'West',
              'housing_tenure': 'owner', 'employment_status': 'employed',
              'financial_risk_prior': '4', 'general_risk_prior': '4',
              'outlook_previous': '3', 'outlook_current': '3',
              'finances_previous': '3', 'finances_current': '3'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def previous(month):
    return month - 1 if month % 100 > 1 else (month // 100 - 1) * 100 + 12


def clean(value, low=None, high=None):
    if not finite(value) or (low is not None and value < low) or (high is not None and value > high):
        return None
    return float(value)


def cat(value):
    if value is None or (isinstance(value, (float, int)) and not finite(value)):
        return 'missing'
    return str(int(value)) if isinstance(value, (float, int)) and int(value) == value else str(value)


def normal_weights(rows):
    w = np.asarray([r['design_survey_weight'] for r in rows], float)
    return w / w.sum()


def equal_month_weights(rows):
    totals = defaultdict(float)
    for r in rows:
        totals[r['month']] += r['design_survey_weight']
    return np.asarray([r['design_survey_weight'] / totals[r['month']] for r in rows])


def load_rows():
    """Hash-verify frozen preparation/cache receipts, then project selected fields."""
    archived = read(SOURCE / 'summary.json')
    cases = read(SOURCE / 'cases_private.json')
    pairs = [r for r in prepare_pairs(cases, months=MONTHS, n_per_month=192) if r['paired_eligible']]
    assert len(pairs) == 2284
    original = {(r['month'], r['userid'], r['repeat']): r for r in cases}
    sources = {str((SOURCE / name).relative_to(ROOT)): sha(SOURCE / name)
               for name in ('cases_private.json', 'summary.json')}
    for receipt_path in (TRAITS.parent / 'summary.json', Q2_FOLDER / 'verification.json'):
        sources[str(receipt_path.relative_to(ROOT))] = sha(receipt_path)
    trait_receipt = read(TRAITS.parent / 'summary.json')
    if sha(TRAITS) != trait_receipt['analysis_frame_sha256']:
        raise ValueError('Cached analysis frame hash differs from its receipt')
    q2_path = Q2_FOLDER / 'q2_selected_private.json'
    if sha(q2_path) != read(Q2_FOLDER / 'verification.json')['Q2_cache_sha256']:
        raise ValueError('Cached selected Q2 hash differs from independent verification')
    sources[str(TRAITS.relative_to(ROOT))] = sha(TRAITS)
    sources[str(q2_path.relative_to(ROOT))] = sha(q2_path)
    q2 = {(r['month'], r['userid']): r['Q2'] for r in read(q2_path)}
    columns = ('date', 'userid', 'Q9_mean', 'tenure', 'financial_change', 'financial_risk', 'general_risk')
    db = duckdb.connect()
    try:
        schema = db.execute('DESCRIBE SELECT * FROM read_parquet(?)', [str(TRAITS)]).fetchall()
        records = db.execute('SELECT ' + ','.join(columns) +
            ' FROM read_parquet(?) WHERE userid IN (SELECT unnest(?)) AND date<=?',
            [str(TRAITS), sorted({r['userid'] for r in pairs}), max(MONTHS)]).fetchall()
    finally:
        db.close()
    traits = {(int(r[0]), int(r[1])): dict(zip(columns, r)) for r in records}
    if len(traits) != len(records):
        raise ValueError('Duplicate identities in cached analysis frame')
    temporal = defaultdict(list)
    for (m, uid), r in traits.items():
        if finite(r['Q9_mean']):
            temporal[uid].append((m, float(r['Q9_mean'])))
    past, cpi = {}, {}
    for m in MONTHS:
        for name in ('past_private.json', 'environment.json'):
            path = PREPARED / str(m) / name
            if sha(path) != archived['source_sha256'][f'{m}/{name}']:
                raise ValueError('Frozen preparation hash mismatch: ' + str(path))
            sources[str(path.relative_to(ROOT))] = sha(path)
        past[m] = read(PREPARED / str(m) / 'past_private.json')
        env = read(PREPARED / str(m) / 'environment.json')
        matches = [s for signals in env['provider_args']['signals_by_step'].values() for s in signals
                   if s.get('role') == 'latest_release' and s['signal_id'].startswith('bls_cpi_u_all_items_yoy')]
        assert len(matches) == 1
        signal = matches[0]
        as_of = env['provider_args']['targets'][0]['as_of']
        assert datetime.fromisoformat(signal['published_at']) <= datetime.fromisoformat(as_of)
        cpi[m] = {k: signal[k] for k in ('value', 'reference_period', 'published_at', 'source_url')}
    rows = []
    for pair in pairs:
        m, uid = pair['month'], pair['userid']
        raw = original[m, uid, 1]
        h = past[m][pair['agent_id']]
        state, p = h['state'], h['prior']
        prior = pair['prior_mean_pp']
        if not np.isclose(prior, state['center'], atol=1e-8, rtol=0):
            raise ValueError('Prepared prior center differs from cached scored prior')
        bins = np.asarray([p['q9'][f'bin{i}'] for i in range(1, 11)], float)
        assert bins.tolist() == raw['real']['previous_q9_bins']
        model = float(np.mean([pair['model_repeats'][str(rep)]['mean'] for rep in (1, 2)]))
        current = traits.get((m, uid), {})
        before = traits.get((previous(m), uid), {})
        history_values = [v for date, v in temporal[uid] if date < m]
        point = clean(p['point_pct'], -100, 100)
        truth_point = clean(raw['real']['q8_point'], -100, 100)
        model_points = [clean(original[m, uid, rep]['arms']['reference']['point'], -100, 100) for rep in (1, 2)]
        model_point = float(np.mean(model_points)) if all(v is not None for v in model_points) else None
        anchor = state.get('anchor')
        row = {**pair, **pair['profile'], 'model_mean_for_profile_pp': model,
               'model_delta_pp': model - prior, 'model_abs_delta_pp': abs(model - prior),
               'truth_abs_delta_pp': abs(pair['truth_delta_pp']), 'model_minus_truth_pp': model - pair['truth_mean_pp'],
               'latest_cpi_yoy_pp': cpi[m]['value'], 'prior_minus_cpi_pp': prior - cpi[m]['value'],
               'abs_prior_minus_cpi_pp': abs(prior - cpi[m]['value']),
               'prior_iqr_pp': state['high'] - state['low'], 'history_anchor_pp': anchor,
               'anchor_gap_pp': anchor - prior if anchor is not None else 0.,
               'anchor_available': int(anchor is not None), 'history_n': state['n_earlier_valid'],
               'history_cached_sd_pp': float(np.std(history_values)) if len(history_values) >= 2 else None,
               'history_cached_n': len(history_values),
               'prior_zero_deflation': int(np.all(bins[5:] == 0)), 'prior_active_bins': int(np.count_nonzero(bins)),
               'prior_probabilities_multiple_5': int(np.allclose(bins / 5, np.round(bins / 5), atol=1e-9, rtol=0)),
               'prior_point_integer': int(abs(point - round(point)) < 1e-9) if point is not None else None,
               'prior_point_multiple_5': int(abs(point / 5 - round(point / 5)) < 1e-9) if point is not None else None,
               'prior_point_minus_q9_pp': point - prior if point is not None else None,
               'truth_same_bins_as_prior': int(np.allclose(bins, raw['real']['q9_bins'], atol=1e-12, rtol=0)),
               'truth_point_same_as_prior': int(abs(truth_point - point) <= 1e-12) if truth_point is not None and point is not None else None,
               'truth_point_minus_q9_pp': truth_point - pair['truth_mean_pp'] if truth_point is not None else None,
               'model_point_minus_q9_pp': model_point - model if model_point is not None else None,
               'financial_risk_prior': clean(before.get('financial_risk'), 1, 7),
               'general_risk_prior': clean(before.get('general_risk'), 1, 7),
               'finances_previous': clean(before.get('financial_change'), 1, 5),
               'finances_current': clean(current.get('financial_change'), 1, 5),
               'outlook_previous': clean(q2.get((previous(m), uid)), 1, 5),
               'outlook_current': clean(q2.get((m, uid)), 1, 5)}
        for name, value in (('prior_outlook_worse', row['outlook_previous']), ('current_outlook_worse', row['outlook_current']),
                            ('prior_finances_worse', row['finances_previous']), ('current_finances_worse', row['finances_current'])):
            row[name] = int(value in (1, 2)) if value is not None else None
        for name, past_field, current_field in (('outlook_became_worse', 'outlook_previous', 'outlook_current'),
                                                ('finances_became_worse', 'finances_previous', 'finances_current')):
            a, b = row[past_field], row[current_field]
            row[name] = int(b < a) if a is not None and b is not None else None
        rows.append(row)
    inventory = {'cached_parquet_schema': [{'name': c[0], 'type': c[1]} for c in schema],
                 'projected_columns': list(columns), 'q2_selected_records': len(q2),
                 'available_nonmissing_person_months': {key: sum(finite(r.get(key)) for r in rows)
                    for key in (*FEATURES, 'financial_risk_prior', 'general_risk_prior', 'outlook_previous',
                                'outlook_current', 'finances_previous', 'finances_current')},
                 'latest_cpi_by_month': cpi,
                 'history_sd_source': 'Cached analysis_frame Q9_mean prior to target date, unweighted within person. '
                 'This is a supplementary historical dispersion proxy and not a refit of frozen main Q9 scores.',
                 'unavailable': ['Direct causes of household financial changes', 'Within-person measured attention to CPI/news',
                                 'Latent personality/optimism traits', 'Verified individual consumption or job/income shocks'],
                 'state_scope': 'Q1 compares finances to 12 months ago; Q2 concerns year-ahead finances. '
                 'Changes in adjacent category responses are not measured one-month financial shocks. '
                 'Current Q1/Q2 are retrospective explanations only, never B inputs.'}
    return rows, sources, inventory


def mask_group(row, name, threshold):
    td, md = direction(row['truth_delta_pp'], threshold), direction(row['model_delta_pp'], threshold)
    definitions = {'all': True, 'truth_stable': td == 'stable', 'truth_up': td == 'up', 'truth_down': td == 'down',
        'truth_stable_model_moves': td == 'stable' and md != 'stable',
        'truth_stable_model_stable': td == 'stable' and md == 'stable',
        'truth_moves_model_stable': td != 'stable' and md == 'stable',
        'truth_moves_model_moves': td != 'stable' and md != 'stable',
        'truth_moves_model_underreacts': td != 'stable' and abs(row['model_delta_pp']) + threshold < abs(row['truth_delta_pp'])}
    return definitions[name]


def summary_cell(rows, all_rows, truth_reference):
    base = {'n': len(rows), 'ess': ess([r['design_survey_weight'] for r in rows]),
            'suppressed': len(rows) < 10}
    base['weak_support_ess_below_10'] = base['ess'] < 10
    if base['suppressed']:
        return base
    base['share_of_same_month_all'] = sum(r['design_survey_weight'] for r in rows) / sum(r['design_survey_weight'] for r in all_rows)
    base['share_of_same_month_truth_stratum'] = sum(r['design_survey_weight'] for r in rows) / sum(r['design_survey_weight'] for r in truth_reference)
    features = {}
    for feature in FEATURES:
        sub = [r for r in rows if finite(r.get(feature))]
        entry = {'n': len(sub), 'ess': ess([r['design_survey_weight'] for r in sub]), 'suppressed': len(sub) < 10}
        entry['weak_support_ess_below_10'] = entry['ess'] < 10
        if not entry['suppressed']:
            w = normal_weights(sub)
            vals = np.asarray([r[feature] for r in sub])
            entry.update(mean=float(w @ vals), median=quantile(vals, w, .5))
            for label, reference in (('same_month_all', all_rows), ('same_month_truth_stratum', truth_reference)):
                ref = [r for r in reference if finite(r.get(feature))]
                entry['mean_difference_vs_' + label] = float(w @ vals) - float(normal_weights(ref) @ np.asarray([r[feature] for r in ref])) if len(ref) >= 10 else None
        features[feature] = entry
    base['features'] = features
    return base


def average_cells(cells):
    reported = [c for c in cells if not c['suppressed']]
    result = {'n_person_months': sum(c['n'] for c in cells), 'n_months_reported': len(reported),
              'months_reported': [c['month'] for c in reported], 'coverage_complete': len(reported) == len(MONTHS),
              'weak_support_months': [c['month'] for c in reported if c['weak_support_ess_below_10']],
              'weighted_share_equal_months': float(np.mean([c['share_of_same_month_all'] for c in reported])) if reported else None,
              'weighted_truth_stratum_share_equal_months': float(np.mean([c['share_of_same_month_truth_stratum'] for c in reported])) if reported else None,
              'features': {}}
    for feature in FEATURES:
        valid = [c['features'][feature] for c in reported if not c['features'][feature]['suppressed']]
        result['features'][feature] = {'n_months_reported': len(valid), 'n_person_months': sum(c['n'] for c in valid),
            **{k: float(np.mean([c[k] for c in valid])) if valid and all(finite(c.get(k)) for c in valid) else None
               for k in ('mean', 'median', 'mean_difference_vs_same_month_all', 'mean_difference_vs_same_month_truth_stratum')}}
    return result


def profile_groups(rows):
    groups = ('all', 'truth_stable', 'truth_up', 'truth_down', 'truth_stable_model_moves',
              'truth_stable_model_stable', 'truth_moves_model_stable', 'truth_moves_model_moves', 'truth_moves_model_underreacts')
    result = {}
    for threshold in THRESHOLDS:
        by_group = {}
        for group in groups:
            monthly = []
            for month in MONTHS:
                full = [r for r in rows if r['month'] == month]
                subset = [r for r in full if mask_group(r, group, threshold)]
                truth_ref = [r for r in full if (direction(r['truth_delta_pp'], threshold) == 'stable')
                             == group.startswith('truth_stable')] if group not in ('all', 'truth_stable', 'truth_up', 'truth_down') else full
                monthly.append({'month': month, **summary_cell(subset, full, truth_ref)})
            by_group[group] = {'monthly': monthly, 'equal_month_overview': average_cells(monthly)}
        result[str(threshold)] = by_group
    return result


def category_rates(rows, threshold=.5):
    """Mismatch rates within P cells, against the same month's truth stratum."""
    result = {}
    specs = {'stable_model_moves': ('truth_stable', 'truth_stable_model_moves'),
             'movers_model_stable': (None, 'truth_moves_model_stable'),
             'movers_model_underreacts': (None, 'truth_moves_model_underreacts')}
    extra_fields = ('finances_previous', 'finances_current', 'outlook_previous', 'outlook_current',
                    'financial_risk_prior', 'general_risk_prior', 'prior_zero_deflation',
                    'prior_probabilities_multiple_5', 'prior_point_multiple_5')
    for name, (population, event) in specs.items():
        result[name] = {}
        for field in (*P_FIELDS, *extra_fields):
            groups = {}
            for label in sorted({cat(r.get(field)) for r in rows}):
                cells = []
                for month in MONTHS:
                    full = [r for r in rows if r['month'] == month
                            and (mask_group(r, population, threshold) if population else direction(r['truth_delta_pp'], threshold) != 'stable')]
                    subset = [r for r in full if cat(r.get(field)) == label]
                    cell = {'month': month, 'n': len(subset), 'ess': ess([r['design_survey_weight'] for r in subset]), 'suppressed': len(subset) < 10}
                    cell['weak_support_ess_below_10'] = cell['ess'] < 10
                    if not cell['suppressed']:
                        w = normal_weights(subset)
                        fw = normal_weights(full)
                        rate = float(w @ [mask_group(r, event, threshold) for r in subset])
                        baseline = float(fw @ [mask_group(r, event, threshold) for r in full])
                        cell.update(mismatch_weighted_rate=rate, same_month_truth_stratum_rate=baseline,
                                    difference_vs_same_month_truth_stratum=rate - baseline)
                    cells.append(cell)
                valid = [c for c in cells if not c['suppressed']]
                groups[label] = {'monthly': cells, 'equal_month_overview': {
                    'n_person_months': sum(c['n'] for c in cells), 'months_reported': [c['month'] for c in valid],
                    'n_months_reported': len(valid), 'coverage_complete': len(valid) == 12,
                    'weak_support_months': [c['month'] for c in valid if c['weak_support_ess_below_10']],
                    **{k: float(np.mean([c[k] for c in valid])) if valid else None for k in
                       ('mismatch_weighted_rate', 'same_month_truth_stratum_rate', 'difference_vs_same_month_truth_stratum')}}}
            result[name][field] = groups
    return result


def fit(rows, outcome, numeric, categorical=P_FIELDS, *, leave_year=True):
    used = [r for r in rows if finite(r.get(outcome)) and all(finite(r.get(k)) for k in numeric)]
    if len(used) < 10:
        return {'n': len(used), 'suppressed': True}
    w = equal_month_weights(used)
    names, columns = ['intercept'], [np.ones(len(used))]
    for key in numeric:
        values = np.asarray([r[key] for r in used], float)
        if np.ptp(values) > 1e-12:
            names.append(key); columns.append(values)
    levels, references = {}, {}
    for key in ('month', *categorical):
        labels = sorted({cat(r.get(key)) for r in used})
        ref = REFERENCES.get(key, labels[0])
        if ref not in labels:
            ref = labels[0]
        references[key] = ref
        for label in labels:
            if label != ref:
                name = key + '=' + label
                names.append(name); columns.append(np.asarray([cat(r.get(key)) == label for r in used], float))
                levels[name] = [r for r in used if cat(r.get(key)) == label]
    # One missing person can induce identical "missing" dummies in several
    # entry traits. Keep one nuisance column and name its aliases explicitly.
    # Those aliases have no separately identified coefficients.
    patterns, keep, aliases = {}, [], {}
    for index, values in enumerate(columns):
        pattern = np.ascontiguousarray(values, dtype=float).tobytes()
        if pattern in patterns:
            aliases[names[index]] = names[patterns[pattern]]
        else:
            patterns[pattern] = index
            keep.append(index)
    names, columns = [names[i] for i in keep], [columns[i] for i in keep]
    x, y = np.column_stack(columns), np.asarray([r[outcome] for r in used])
    wx = x * np.sqrt(w)[:, None]
    beta, _, rank, singular = np.linalg.lstsq(wx, y * np.sqrt(w), rcond=None)
    residual = y - x @ beta
    totals = defaultdict(float)
    for r, weight in zip(used, w):
        totals[r['month']] += weight
    centers = {m: sum(weight * r[outcome] for r, weight in zip(used, w) if r['month'] == m) / totals[m] for m in totals}
    variance = float(sum(weight * (r[outcome] - centers[r['month']]) ** 2 for r, weight in zip(used, w)))
    sse = float(w @ (residual ** 2))
    coefficients = {}
    for name, value in zip(names, beta):
        if name == 'intercept' or name.startswith('month='):
            continue
        support = levels.get(name, used)
        n = len(support)
        coefficients[name] = {'estimate': float(value) if n >= 10 else None, 'n_support': n,
                              'support_below_10': n < 10}
    result = {'n': len(used), 'n_months': len(totals), 'n_unique_userids': len({r['userid'] for r in used}),
              'numeric': list(numeric), 'categorical': list(categorical), 'categorical_references': references,
              'rank': int(rank), 'columns': len(names), 'full_rank': bool(rank == len(names)),
              'identical_columns_kept_as_nuisance_aliases': aliases,
              'condition_number': float(singular[0] / singular[-1]) if singular[-1] > 0 else None,
              'r2_within_month': 1. - sse / variance if variance > 0 else None,
              'weighted_rmse_pp_or_binary_units': float(np.sqrt(sse / w.sum())),
              'coefficients': coefficients,
              'monthly_support': {str(m): {'n': sum(r['month'] == m for r in used),
                  'ess': ess([r['design_survey_weight'] for r in used if r['month'] == m])} for m in totals}}
    if leave_year:
        fits = {str(year): fit([r for r in rows if r['month'] // 100 != year], outcome, numeric,
                               categorical, leave_year=False) for year in sorted({r['month'] // 100 for r in used})}
        sensitivity = {}
        for name in coefficients:
            values = [f.get('coefficients', {}).get(name, {}).get('estimate') for f in fits.values()]
            good = [v for v in values if finite(v)]
            sensitivity[name] = {'n_leave_year_fits': len(good), 'minimum': min(good) if good else None,
                                  'maximum': max(good) if good else None,
                                  'positive_count': sum(v > 0 for v in good), 'negative_count': sum(v < 0 for v in good)}
        result['leave_one_year_out'] = sensitivity
    return result


def regression_blocks(rows):
    stable = [r for r in rows if direction(r['truth_delta_pp'], .5) == 'stable']
    movers = [r for r in rows if direction(r['truth_delta_pp'], .5) != 'stable']
    for r in rows:
        r['stable_model_moves_binary'] = float(abs(r['model_delta_pp']) > .5)
        r['mover_model_stable_binary'] = float(abs(r['model_delta_pp']) <= .5)
    common = ('prior_mean_pp', *HISTORY)
    alignment = {outcome: {
        'month_only': fit(stable, outcome, ('prior_minus_cpi_pp',), ()),
        'month_P': fit(stable, outcome, ('prior_minus_cpi_pp',)),
        'month_P_history': fit(stable, outcome, ('prior_minus_cpi_pp', *HISTORY))}
        for outcome in ('model_delta_pp', 'model_minus_truth_pp')}
    alignment['mismatch_probability_stable'] = fit(stable, 'stable_model_moves_binary',
        ('abs_prior_minus_cpi_pp', *common))
    alignment['mismatch_probability_movers'] = fit(movers, 'mover_model_stable_binary',
        ('abs_prior_minus_cpi_pp', *common))
    state_fits = {}
    for population, subset in (('all', rows), ('truth_stable', stable), ('truth_moves', movers)):
        base = fit(subset, 'model_minus_truth_pp', common)
        blocks = {'base_month_prior_history_P': base,
                  'prior_risk_and_outlook': fit(subset, 'model_minus_truth_pp', common,
                      (*P_FIELDS, 'financial_risk_prior', 'general_risk_prior', 'finances_previous', 'outlook_previous')),
                  'current_finances_outlook_posthoc': fit(subset, 'model_minus_truth_pp', common,
                      (*P_FIELDS, 'finances_current', 'outlook_current')),
                  'history_volatility_complete_cases': fit(subset, 'model_minus_truth_pp', (*common, 'history_cached_sd_pp'))}
        volatility_base = fit([r for r in subset if finite(r.get('history_cached_sd_pp'))], 'model_minus_truth_pp', common)
        for key, record in blocks.items():
            if key == 'base_month_prior_history_P':
                continue
            comparator = volatility_base if key == 'history_volatility_complete_cases' else base
            record['r2_increment_vs_same_support_base'] = record['r2_within_month'] - comparator['r2_within_month']
            record['same_support_comparator_n'] = comparator['n']
        state_fits[population] = blocks
    reporting_fields = ('prior_zero_deflation', 'prior_active_bins', 'prior_probabilities_multiple_5',
                        'prior_point_multiple_5', 'prior_point_minus_q9_pp')
    reporting = {}
    for name, subset, outcome in (('stable_mismatch_probability', stable, 'stable_model_moves_binary'),
                                   ('mover_model_stable_probability', movers, 'mover_model_stable_binary')):
        complete = [r for r in subset if all(finite(r.get(k)) for k in reporting_fields)]
        base = fit(complete, outcome, (*common, 'abs_prior_minus_cpi_pp'))
        full = fit(complete, outcome, (*common, 'abs_prior_minus_cpi_pp', *reporting_fields))
        full['r2_increment_vs_same_support_base'] = full['r2_within_month'] - base['r2_within_month']
        reporting[name] = {'same_support_base': base, 'reporting_added': full}
    return {'1_prior_public_alignment': alignment, '2_household_state_history': state_fits,
            '3_reporting_habits': reporting,
            'identification_notes': ['With month fixed effects, prior-minus-monthly-CPI and prior give '
                'identical slopes; these data cannot identify a special causal role for CPI or news.',
                'The model-minus-prior outcome shares prior with the gap regressor, creating mathematical coupling. '
                'Model-minus-truth is additionally reported, but selection into a truth-stable group also uses prior; '
                'neither regression identifies causal correction of abnormal priors.',
                'All coefficient tables are descriptive WLS with within-estimation-sample month totals equal. '
                'Binary outcome coefficients are probability point differences, not fitted deployment probabilities.',
                'Leave-one-year-out ranges are sign sensitivity across six already viewed years, not confidence intervals '
                'or independent validation; sparse categories and correlated traits limit interpretation.',
                'Q1/Q2 current values are same-survey reports, allowing reverse association/shared shocks; '
                'no current state is used to train a deployable classifier.',
                'Numeracy and other P labels may contribute conditionally; raw group errors do not establish absence '
                'of a model response to those labels.']}


def p_compositions(rows):
    """Within-profile P composition and the same-month reference composition."""
    output = {}
    for group in ('truth_stable_model_moves', 'truth_stable_model_stable',
                  'truth_moves_model_stable', 'truth_moves_model_moves'):
        output[group] = {}
        for field in P_FIELDS:
            output[group][field] = {}
            for label in sorted({cat(r.get(field)) for r in rows}):
                cells = []
                for month in MONTHS:
                    full = [r for r in rows if r['month'] == month]
                    reference = [r for r in full if (direction(r['truth_delta_pp'], .5) == 'stable') == group.startswith('truth_stable')]
                    selected = [r for r in full if mask_group(r, group, .5)]
                    subset = [r for r in selected if cat(r.get(field)) == label]
                    c = {'month': month, 'n': len(subset), 'ess': ess([r['design_survey_weight'] for r in subset]),
                         'suppressed': len(subset) < 10}
                    c['weak_support_ess_below_10'] = c['ess'] < 10
                    if not c['suppressed']:
                        share = sum(r['design_survey_weight'] for r in subset) / sum(r['design_survey_weight'] for r in selected)
                        ref_share = sum(r['design_survey_weight'] for r in reference if cat(r.get(field)) == label) / sum(r['design_survey_weight'] for r in reference)
                        all_share = sum(r['design_survey_weight'] for r in full if cat(r.get(field)) == label) / sum(r['design_survey_weight'] for r in full)
                        c.update(composition_share=share, same_month_truth_stratum_share=ref_share,
                                 difference_vs_same_month_truth_stratum=share - ref_share,
                                 same_month_all_share=all_share, difference_vs_same_month_all=share - all_share)
                    cells.append(c)
                reportable = [c for c in cells if not c['suppressed']]
                output[group][field][label] = {'monthly': cells, 'equal_month_overview': {
                    'n_person_months': sum(c['n'] for c in cells), 'months_reported': [c['month'] for c in reportable],
                    'weak_support_months': [c['month'] for c in reportable if c['weak_support_ess_below_10']],
                    **{key: float(np.mean([c[key] for c in reportable])) if reportable else None for key in (
                        'composition_share', 'same_month_truth_stratum_share', 'difference_vs_same_month_truth_stratum',
                        'same_month_all_share', 'difference_vs_same_month_all')}}}
    return output


def limited_checks(rows):
    """Interior-prior sensitivity and a short parallel Q8 point-answer check."""
    interior = [r for r in rows if 0 <= r['prior_mean_pp'] <= 10]
    groups = {}
    for group in ('truth_stable_model_moves', 'truth_stable_model_stable', 'truth_moves_model_stable'):
        monthly = []
        for month in MONTHS:
            full = [r for r in interior if r['month'] == month]
            selected = [r for r in full if mask_group(r, group, .5)]
            ref = [r for r in full if (direction(r['truth_delta_pp'], .5) == 'stable') == group.startswith('truth_stable')]
            monthly.append({'month': month, **summary_cell(selected, full, ref)})
        groups[group] = {'monthly': monthly, 'equal_month_overview': average_cells(monthly)}
    stable = [r for r in interior if abs(r['truth_delta_pp']) <= .5]
    gap_fit = fit(stable, 'model_minus_truth_pp', ('prior_minus_cpi_pp', *HISTORY))
    q8_rows = []
    for row in rows:
        if all(finite(row.get(k)) for k in ('prior_point_minus_q9_pp', 'truth_point_minus_q9_pp', 'model_point_minus_q9_pp')):
            prior = row['prior_mean_pp'] + row['prior_point_minus_q9_pp']
            truth = row['truth_mean_pp'] + row['truth_point_minus_q9_pp']
            model = row['model_mean_for_profile_pp'] + row['model_point_minus_q9_pp']
            q8_rows.append({**row, 'q8_truth_delta': truth - prior, 'q8_model_delta': model - prior})
    q8 = []
    for month in MONTHS:
        full = [r for r in q8_rows if r['month'] == month]
        stable_q8 = [r for r in full if abs(r['q8_truth_delta']) <= .5]
        movers_q8 = [r for r in full if abs(r['q8_truth_delta']) > .5]
        record = {'month': month, 'n': len(full), 'ess': ess([r['design_survey_weight'] for r in full])}
        for name, sub, event in (('truth_stable', stable_q8, lambda r: abs(r['q8_model_delta']) > .5),
                                  ('truth_moves', movers_q8, lambda r: abs(r['q8_model_delta']) <= .5)):
            cell = {'n': len(sub), 'ess': ess([r['design_survey_weight'] for r in sub]), 'suppressed': len(sub) < 10}
            cell['weak_support_ess_below_10'] = cell['ess'] < 10
            if not cell['suppressed']:
                w = normal_weights(sub)
                cell.update(mismatch_rate=float(w @ [event(r) for r in sub]),
                            truth_abs_delta_mean_pp=float(w @ [abs(r['q8_truth_delta']) for r in sub]),
                            model_abs_delta_mean_pp=float(w @ [abs(r['q8_model_delta']) for r in sub]))
            record[name] = cell
        q8.append(record)
    return {'interior_prior_0_to_10pp': {'status': 'limited_sensitivity_only_primary_tails_retained',
                'n_person_months': len(interior), 'profiles': groups, 'truth_stable_error_gap_regression': gap_fit},
            'q8_point_answer_check': {'n_person_months': len(q8_rows), 'monthly': q8,
                'equal_month_overview': {name: {
                    'n_person_months': sum(c[name]['n'] for c in q8),
                    **{key: float(np.mean([c[name][key] for c in q8 if not c[name]['suppressed']])) for key in
                       ('mismatch_rate', 'truth_abs_delta_mean_pp', 'model_abs_delta_mean_pp')}}
                    for name in ('truth_stable', 'truth_moves')},
                'note': 'Uses finite Q8 point values within -100..100 and means the two model points only for '
                'this profile check. Q8 and fitted Q9 are distinct answers; thresholds coincide in pp but '
                'their eligible group memberships need not agree.'},
            'mechanism_scope': 'Bayesian common-signal updating can predict more movement under a less precise '
                'prior. Actual respondents may not have seen the shared signal, may already know it, may use '
                'different horizons/consumption signals, or may repeat/hear/round the survey differently. '
                'Prior density IQR is only a proxy for precision, not calibrated inverse-variance information.'}


def analyze(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to((ROOT / 'outputs').resolve()):
        raise ValueError('Require a fresh private output directory under outputs')
    rows, sources, inventory = load_rows()
    profiles = profile_groups(rows)
    rates = category_rates(rows)
    regressions = regression_blocks(rows)
    summary = {'status': 'completed_posthoc_update_mismatch_profiles',
               'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'new_api_calls': 0,
               'refitted_bin_vectors': 0, 'n_person_months': len(rows), 'n_months': 12,
               'weights': 'Person design survey weights normalized inside month/slice; scope overviews average '
               'reportable monthly statistics equally. n<10 suppressed; ESS<10 explicitly weak support.',
               'model_mean_scope': 'Mean of two generation Q9 means is used only for post-hoc profile localization '
               'and descriptive regressions. Archived primary two-repeat cell evaluations are not changed.',
               'groups_definition': {'truth_stable_model_moves': '|truth-prior|<=tau and |mean(model repeats)-prior|>tau',
                   'truth_moves_model_stable': '|truth-prior|>tau and |mean(model repeats)-prior|<=tau',
                   'truth_moves_model_underreacts': '|truth-prior|>tau and |model mean-prior|+tau<|truth-prior|'},
               'profiles_by_threshold': profiles, 'category_mismatch_rates_at_0_5pp': rates,
               'P_compositions_at_0_5pp': p_compositions(rows), 'limited_checks': limited_checks(rows),
               'regressions': regressions, 'source_inventory': inventory,
               'source_sha256': sources,
               'analysis_sha256': {str(Path(__file__).relative_to(ROOT)): sha(__file__),
                   'scripts/analyze_sce_update_mismatch_profiles.py': sha(ROOT / 'scripts/analyze_sce_update_mismatch_profiles.py')},
               'limits': ['At most three exploratory descriptive blocks, using previously viewed A historical reconstructions. '
                   'No causal, national, independent-blind-test or B forecast claim.',
                   'Truth-defined groups are outcome-selected. Low copy error in stable groups partly follows from '
                   'their definition; no rule to identify them in advance has been learned.',
                   'Subgroup share/rate differences are raw same-month comparisons. Conditional coefficients '
                   'do not prove how a label affects model generation without an intervention.',
                   'CPI is realized recent annual inflation, while Q9 is a forward one-year belief; disagreement '
                   'with CPI is not itself irrationality or an error.',
                   'Counts are person-months, with repeated identities across months and paired model generations. '
                   'No independence-based standard error or significance threshold is claimed.']}
    payloads = {name: json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
                for name, value in (('summary.json', summary), ('profile_frame_private.json', rows))}
    out.mkdir(parents=True)
    for name, payload in payloads.items():
        with (out / name).open('x') as stream:
            stream.write(payload)
    return summary
