"""Evaluation-only controls and questionnaire-shape diagnostics on cached scores.

This module imports no runtime, LLM client or density fitter. All regressions
describe already inspected responses; coefficients are not causal mechanisms.
"""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.linalg import lstsq

from .metrics import quantile

FIELDS = ('age_group', 'education_group', 'household_income_band', 'numeracy',
          'region', 'housing_tenure', 'employment_status')
REFERENCES = {'age_group': 'Under 40', 'education_group': 'college',
              'household_income_band': 'under_50k', 'numeracy': 'high',
              'region': 'Northeast', 'housing_tenure': 'owner',
              'employment_status': 'employed'}
ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def probability_features(bins):
    """Q9 order: five inflation bins, then five deflation bins, in percent."""
    p = np.asarray(bins, dtype=float)
    if p.shape != (10,) or not np.isfinite(p).all() or (p < 0).any() or abs(p.sum()-100) > 1e-6:
        raise ValueError('Expected a valid original Q9 response, no repair')
    positive = p[p > 0]/100
    return {'nonzero_bins': int((p > 0).sum()), 'maximum_bin_pct': float(p.max()),
            'zero_deflation': float(p[5:].sum() == 0),
            'deflation_probability_pct': float(p[5:].sum()),
            'entropy_bits': float(-np.sum(positive*np.log2(positive))),
            'all_on_5pct_grid': float(np.allclose(p/5, np.rint(p/5), atol=1e-9, rtol=0)),
            'all_on_10pct_grid': float(np.allclose(p/10, np.rint(p/10), atol=1e-9, rtol=0))}


def load_pairs(evaluation, prepared):
    casepath = evaluation/'cases_private.json'
    records = json.loads(casepath.read_text())
    summary = json.loads((evaluation/'summary.json').read_text())
    declared = json.loads((evaluation/'regression_diagnostic_20261017.json').read_text())
    assert sha(casepath) == declared['source_cases_sha256']
    grouped, past, hashes = defaultdict(list), {}, {}
    for row in records:
        grouped[row['month'], row['userid']].append(row)
    rows = []
    for (month, uid), pair in sorted(grouped.items()):
        pair = sorted(pair, key=lambda p: p['repeat'])
        assert [p['repeat'] for p in pair] == [1, 2]
        if not all(p['arms']['reference']['validation_status'] == 'valid'
                   and all(v is not None and np.isfinite(v) for v in
                           (p['arms']['reference']['mean'], p['real']['q9_mean'],
                            p['real']['q9_iqr'], p['baselines']['copy_previous'])) for p in pair):
            continue
        r = pair[0]
        assert pair[1]['real'] == r['real'] and pair[1]['profile'] == r['profile']
        if month not in past:
            path = prepared/str(month)/'past_private.json'
            expected = summary['source_sha256'][f'{month}/past_private.json']
            assert sha(path) == expected
            past[month] = json.loads(path.read_text())
            hashes[str(month)] = expected
        history = past[month][r['agent_id']]
        state = history['state']
        anchor = state['anchor']
        rows.append({'month': month, 'userid': uid, 'weight': r['design_survey_weight'],
                     **r['profile'], 'prior': r['baselines']['copy_previous'],
                     'prior_q8': history['prior']['point_pct'],
                     'real': r['real']['q9_mean'],
                     'sim': float(np.mean([p['arms']['reference']['mean'] for p in pair])),
                     'anchor_gap': round(anchor, 1)-round(state['center'], 1) if anchor is not None else 0.,
                     'anchor_available': int(anchor is not None),
                     'history_n': state['n_earlier_valid'], 'records': pair})
    for month in sorted({r['month'] for r in rows}):
        mass = sum(r['weight'] for r in rows if r['month'] == month)
        for r in rows:
            if r['month'] == month:
                r['weight'] /= mass
    return rows, summary, {'cases_sha256': sha(casepath), 'summary_sha256': sha(evaluation/'summary.json'),
                           'past_sha256_by_month': hashes}


def design(rows, numeric=(), categories=()):
    columns, names, references = [], [], {}
    for month in sorted({r['month'] for r in rows}):
        columns.append([float(r['month'] == month) for r in rows]); names.append(f'month={month}')
    for key in numeric:
        columns.append([r[key] for r in rows]); names.append(key)
    for key in categories:
        values = [str(r.get(key)) if r.get(key) is not None else 'unknown' for r in rows]
        levels = sorted(set(values)); reference = REFERENCES[key]
        if reference not in levels:
            reference = levels[0]
        references[key] = reference
        for level in levels:
            if level != reference:
                columns.append([float(v == level) for v in values]); names.append(f'{key}={level}')
    return np.asarray(columns, dtype=float).T, names, references


def regression(x, y, weight, names):
    y, w = np.asarray(y, float), np.asarray(weight, float)
    b, _, rank, _ = lstsq(x*np.sqrt(w)[:, None], y*np.sqrt(w), lapack_driver='gelsy')
    residual = y-x@b
    sse = np.average(residual**2, weights=w)
    tss = np.average((y-np.average(y, weights=w))**2, weights=w)
    return {'n': len(y), 'rank': int(rank), 'columns': len(names),
            'r2_in_sample': float(1-sse/tss), 'residual_rmse_pp': float(np.sqrt(sse)),
            'coefficients': {name: float(v) for name, v in zip(names, b) if not name.startswith('month=')}}, b


def controls(rows):
    w = [r['weight'] for r in rows]
    yreal = np.array([r['real'] for r in rows]); ysim = np.array([r['sim'] for r in rows])
    reports, identity_residual = {}, 0.
    specifications = {'month_only': ((), ()),
                      'month_prior': (('prior',), ()),
                      'month_prior_history': (('prior', 'anchor_gap', 'anchor_available', 'history_n'), ()),
                      'month_prior_history_P': (('prior', 'anchor_gap', 'anchor_available', 'history_n'), FIELDS)}
    for key, (numeric, categories) in specifications.items():
        x, names, references = design(rows, numeric, categories)
        real, br = regression(x, yreal, w, names)
        sim, bs = regression(x, ysim, w, names)
        gap, bg = regression(x, ysim-yreal, w, names)
        identity_residual = max(identity_residual, float(np.max(abs((bs-br)-bg))))
        reports[key] = {'truth': real, 'model': sim, 'model_minus_truth': gap,
                        'reference_levels': references}
    full = reports['month_prior_history_P']
    leave_year_out = {}
    for year in sorted({r['month']//100 for r in rows}):
        selected = [r for r in rows if r['month']//100 != year]
        x, names, references = design(selected, *specifications['month_prior_history_P'])
        fit, _ = regression(x, [r['sim']-r['real'] for r in selected],
                            [r['weight'] for r in selected], names)
        leave_year_out[str(year)] = fit['coefficients']
    coefficient_ranges = {}
    for name, coefficient in full['model_minus_truth']['coefficients'].items():
        values = [r[name] for r in leave_year_out.values() if name in r]
        coefficient_ranges[name] = {'coefficient': coefficient,
                                    'leave_one_year_out_min': min(values),
                                    'leave_one_year_out_max': max(values)}
    support = {field: {level: {'n_person_months': sum(str(r.get(field)) == level for r in rows),
                               'n_months': len({r['month'] for r in rows if str(r.get(field)) == level})}
                       for level in sorted({str(r.get(field)) for r in rows})} for field in FIELDS}
    return {'specifications': reports, 'gap_coefficient_sensitivity': coefficient_ranges,
            'categorical_support': support,
            'coefficient_linearity_max_abs_error': identity_residual,
            'interpretation': 'Same design fitted separately to real/model/error. Difference in coefficients describes conditional under/overrepresentation, not an identified human update parameter. Leave-year ranges are sensitivity, not confidence intervals. No p-values or causal claims.'}


def shape_summary(rows):
    cells = []
    for month in sorted({r['month'] for r in rows}):
        a = [r for r in rows if r['month'] == month]
        w = np.array([r['weight'] for r in a]); w /= w.sum()
        for repeat in (1, 2):
            row = {'month': month, 'repeat': repeat, 'n': len(a)}
            for label in ('real', 'model'):
                records = [r['records'][repeat-1] for r in a]
                bins = [r['real']['q9_bins'] if label == 'real' else r['arms']['reference']['q9_bins'] for r in records]
                features = [probability_features(p) for p in bins]
                row[label] = {key: float(np.average([f[key] for f in features], weights=w)) for key in features[0]}
                row[label]['mean_probabilities_pct'] = np.average(np.asarray(bins), axis=0, weights=w).tolist()
                key = 'q9_iqr' if label == 'real' else 'iqr'
                row[label]['mean_personal_density_iqr_pp'] = float(np.average(
                    [r['real'][key] if label == 'real' else r['arms']['reference'][key] for r in records], weights=w))
                previous_bins = [r['real']['previous_q9_bins'] for r in records]
                row[label]['exact_same_raw_bins_as_previous_share'] = float(np.average(
                    [np.allclose(p, q, atol=1e-12, rtol=0) for p, q in zip(bins, previous_bins)], weights=w))
                means = [r['real']['q9_mean'] if label == 'real' else r['arms']['reference']['mean'] for r in records]
                previous_means = [r['baselines']['copy_previous'] for r in records]
                row[label]['exact_same_fitted_mean_as_previous_share'] = float(np.average(
                    np.isclose(means, previous_means, atol=1e-12, rtol=0), weights=w))
            cells.append(row)
    aggregate = {}
    for label in ('real', 'model'):
        aggregate[label] = {key: np.mean([c[label][key] for c in cells], axis=0).tolist()
                            for key in cells[0][label]}
    return {'cells': cells, 'all_months_equal_weight': aggregate,
            'bin_order': ['>12%', '8–12%', '4–8%', '2–4%', '0–2%', '-2–0%', '-4–-2%', '-8–-4%', '-12–-8%', '<-12%'],
            'interpretation': 'Filling-style diagnostics. More nonzero bins or entropy do not prove greater real uncertainty. Raw probabilities and fitted personal IQR are separate.'}


def environment_summary(prepared, months):
    result = []
    for month in months:
        path = prepared/str(month)/'environment.json'
        env = json.loads(path.read_text())['provider_args']
        signals = [s for step in env['signals_by_step'].values() for s in step if s.get('role') != 'history']
        values = {}
        for prefix, key in [('bls_cpi_u_all_items_yoy', 'cpi_yoy'),
                            ('bls_cpi_u_all_items_mom', 'cpi_mom'),
                            ('bls_unemployment_rate', 'unemployment'),
                            ('bls_cpi_food_at_home_yoy', 'food_at_home_yoy'),
                            ('bls_cpi_energy_yoy', 'energy_yoy')]:
            matched = [s for s in signals if s['signal_id'].startswith(prefix)]
            assert len(matched) == 1
            s = matched[0]
            values[key] = {field: s.get(field) for field in ('value', 'unit', 'reference_period', 'published_at', 'source_url')}
        result.append({'month': month, 'target': env['targets'][0], 'stored_latest_signals': values,
                       'source_sha256': sha(path)})
    return result


def q8_crosscheck(rows):
    """Separate point-response check on Q9 support, with explicit extra exclusions."""
    cells, prior_slopes = [], []
    for month in sorted({r['month'] for r in rows}):
        a = [r for r in rows if r['month'] == month
             and r['prior_q8'] is not None and np.isfinite(r['prior_q8'])
             and abs(r['prior_q8']) <= 100
             and all(p['real']['q8_point'] is not None and np.isfinite(p['real']['q8_point'])
                     and abs(p['real']['q8_point']) <= 100
                     and p['arms']['reference']['point'] is not None
                     and np.isfinite(p['arms']['reference']['point'])
                     and abs(p['arms']['reference']['point']) <= 100 for p in r['records'])]
        w = np.array([r['weight'] for r in a]); w /= w.sum()
        real = np.array([r['records'][0]['real']['q8_point'] for r in a])
        prior = np.array([r['prior_q8'] for r in a])
        models = [np.array([r['records'][i]['arms']['reference']['point'] for r in a]) for i in (0, 1)]
        row = {'month': month, 'n': len(a), 'excluded_from_q9_common_support_n': sum(r['month'] == month for r in rows)-len(a)}
        for name, vectors in [('truth', [real]), ('model', models), ('copy_previous', [prior])]:
            row[name] = {'center_mae_pp': float(np.mean([abs(quantile(v, w, .5)-quantile(real, w, .5)) for v in vectors])),
                         'person_mae_pp': float(np.mean([np.average(abs(v-real), weights=w) for v in vectors])),
                         'cross_person_iqr_pp': float(np.mean([quantile(v, w, .75)-quantile(v, w, .25) for v in vectors]))}
        denominator = float(np.average((prior-np.average(prior, weights=w))**2, weights=w))
        if denominator > 0:
            prior_slopes.append({name: float(np.average((prior-np.average(prior, weights=w))*(v-np.average(v, weights=w)), weights=w)/denominator)
                                 for name, v in [('truth', real), ('model', np.mean(models, axis=0))]})
        cells.append(row)
    return {'n_person_months': sum(r['n'] for r in cells), 'cells': cells,
            'all_months_equal_weight': {name: {key: float(np.mean([c[name][key] for c in cells])) for key in cells[0][name]}
                                        for name in ('truth', 'model', 'copy_previous')},
            'mean_of_monthly_slopes_on_prior': {name: float(np.mean([s[name] for s in prior_slopes])) for name in ('truth', 'model')},
            'interpretation': 'Q8 only, additional finite <=100 and prior-point support within the Q9-common sample. No pooling Q8 and Q9, no automatic equality with the earlier Q8 evaluation support.'}


def run(evaluation, prepared, out):
    evaluation, prepared, out = map(Path, (evaluation, prepared, out))
    if out.exists():
        raise ValueError('Use a fresh output directory; frozen results are immutable')
    rows, original, sources = load_pairs(evaluation, prepared)
    results = {'status': 'posthoc_cached_scores_no_new_api_or_density_fitting',
               'completed_at_utc': datetime.now(timezone.utc).isoformat(),
               'n_person_months': len(rows), 'new_api_calls': 0,
               'months': sorted({r['month'] for r in rows}),
               'weights': 'design-survey normalized within month, equal month mass',
               'regression_model_response': 'Mean of two valid model generations per person-month, used only for diagnostics, not the original primary cell errors.',
               'controls': controls(rows), 'probability_shape': shape_summary(rows),
               'q8_secondary_crosscheck': q8_crosscheck(rows),
               'environment': environment_summary(prepared, sorted({r['month'] for r in rows})),
               'source_sha256': sources, 'module_sha256': sha(__file__),
               'limits': ['Retrospective conditional reconstruction of eligible returners; not national or strict prospective B.',
                          'No per-person true psychology–belief joint data inferred from other surveys.',
                          'Only twelve selected months and two model generations; no guarantee for unobserved periods.',
                          'Same respondents can recur; numerical sensitivity is not independent validation.',
                          'Environment table reports stored audited release facts; actual prompt audit separately checks what is shown.',
                          'Conditional P coefficients may reflect omitted variables and survey measurement; do not turn them into fixed inflation add-ons.']}
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'out': str(out), 'n': len(rows), 'shape': results['probability_shape']['all_months_equal_weight'],
                      'gap_control_r2': results['controls']['specifications']['month_prior_history_P']['model_minus_truth']['r2_in_sample']}, ensure_ascii=False))
    return results
