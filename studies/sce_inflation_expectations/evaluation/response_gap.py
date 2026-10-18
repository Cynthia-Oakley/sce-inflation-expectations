"""Zero-call, post-hoc diagnostics of archived SCE person/repeat pairs.

This module reads already fitted numbers only. It never imports a scorer,
provider, runner, or a source of current survey outcomes. The original two
generation cells remain the units for primary descriptive metrics; averaging a
person's two generated means is reserved for the labelled regression diagnostic.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

from .metrics import quantile, wasserstein1

ROOT = Path(__file__).resolve().parents[3]
MONTHS = (202003, 202009, 202103, 202109, 202206, 202212,
          202306, 202312, 202404, 202410, 202503, 202509)
OLD_MONTHS = (202206, 202306, 202410, 202509)
SCOPES = {'new_months': tuple(m for m in MONTHS if m not in OLD_MONTHS),
          'old_months': OLD_MONTHS, 'all_months': MONTHS}
GROUP_FIELDS = {'age': 'age_group', 'income': 'household_income_band',
                'education': 'education_group', 'numeracy': 'numeracy',
                'region': 'region', 'housing': 'housing_tenure',
                'employment': 'employment_status'}
THRESHOLDS = (.25, .5, 1.)
MIN_CELL_N = 10
REPEATS = (1, 2)
PRIOR_BANDS = ('below_2', '2_to_below_4', '4_to_below_8', '8_or_above')


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and bool(np.isfinite(value))


def _weights(values):
    w = np.asarray(values, dtype=float)
    if w.ndim != 1 or not len(w) or not np.isfinite(w).all() or np.any(w <= 0):
        raise ValueError('Require nonempty finite positive person weights')
    return w / w.sum()


def _mean(values, weights):
    return float(np.dot(np.asarray(values, dtype=float), _weights(weights)))


def ess(weights):
    if not len(weights):
        return 0.
    w = _weights(weights)
    return float(1. / np.dot(w, w))


def direction(delta, threshold=.5):
    """Stable includes both boundaries; the threshold uses percentage points."""
    if not finite(delta) or not finite(threshold) or threshold <= 0:
        raise ValueError('Finite change and positive finite threshold required')
    return 'stable' if abs(delta) <= threshold else ('up' if delta > 0 else 'down')


def prior_band(prior):
    if not finite(prior):
        raise ValueError('Prior must be finite')
    return PRIOR_BANDS[0 if prior < 2 else 1 if prior < 4 else 2 if prior < 8 else 3]


def mse_identity(predicted, truth, weights):
    """The additive weighted squared-error identity; not a causal decomposition."""
    p, y = np.asarray(predicted, float), np.asarray(truth, float)
    w = _weights(weights)
    if p.shape != y.shape or p.shape != w.shape or not np.isfinite(p).all() or not np.isfinite(y).all():
        raise ValueError('Require equally sized finite paired predictions and truth')
    error = p - y
    bias = float(w @ error)
    mse = float(w @ (error ** 2))
    variance = float(w @ ((error - bias) ** 2))
    return {'individual_mean_mse_pp2': mse, 'mean_error_squared_pp2': bias ** 2,
            'centered_error_variance_pp2': variance,
            'mse_identity_residual_pp2': mse - bias ** 2 - variance}


def prepare_pairs(cases, *, months=None, n_per_month=None):
    """One row per assigned person-month, retaining exclusions and both repeats."""
    grouped = defaultdict(dict)
    agents = defaultdict(set)
    for row in cases:
        month, uid, repeat = row.get('month'), row.get('userid'), row.get('repeat')
        if type(month) is not int or type(uid) is not int or type(repeat) is not int or repeat not in REPEATS:
            raise ValueError('Invalid month/userid/repeat identity')
        key = month, uid
        if repeat in grouped[key]:
            raise ValueError('Duplicate person-month-repeat')
        if not isinstance(row.get('agent_id'), str) or not row['agent_id']:
            raise ValueError('Missing private agent identity')
        if row['agent_id'] in agents[month, repeat]:
            raise ValueError('Duplicate agent identity within month-repeat')
        agents[month, repeat].add(row['agent_id'])
        grouped[key][repeat] = row
    if months is not None and {m for m, _ in grouped} != set(months):
        raise ValueError('Assigned month roster differs from registered months')
    if n_per_month is not None and any(sum(m == month for m, _ in grouped) != n_per_month for month in months):
        raise ValueError('Assigned person count differs from registered count')
    result = []
    for (month, uid), repeat_rows in sorted(grouped.items()):
        if set(repeat_rows) != set(REPEATS):
            raise ValueError('Every assigned person-month requires exactly two archived repeats')
        first, second = (repeat_rows[r] for r in REPEATS)
        for field in ('agent_id', 'profile', 'real', 'baselines', 'design_survey_weight',
                      'survey_weight', 'inclusion_probability', 'stratum'):
            if first.get(field) != second.get(field):
                raise ValueError(f'Inconsistent paired repeat field: {field}')
        w, survey, pi = (first.get(k) for k in ('design_survey_weight', 'survey_weight', 'inclusion_probability'))
        if (not all(finite(v) for v in (w, survey, pi)) or w <= 0 or survey <= 0 or not 0 < pi <= 1
                or not np.isclose(w, survey / pi, rtol=1e-10, atol=1e-10)):
            raise ValueError('Invalid design survey weight or inclusion probability')
        real = first['real']
        prior = real.get('previous_q9_mean')
        if first['baselines'].get('copy_previous') != prior:
            raise ValueError('Copy baseline differs from archived personal prior')
        human_bad = not all(finite(real.get(k)) for k in ('q9_mean', 'q9_iqr'))
        prior_bad = not finite(prior)
        invalid_repeats = [r for r in REPEATS if repeat_rows[r]['arms']['reference'].get('validation_status') != 'valid'
                           or not all(finite(repeat_rows[r]['arms']['reference'].get(k)) for k in ('mean', 'iqr'))]
        model = {str(r): {k: repeat_rows[r]['arms']['reference'].get(k)
                         for k in ('mean', 'iqr', 'validation_status', 'scorer_status')}
                 for r in REPEATS}
        valid = not human_bad and not prior_bad and not invalid_repeats
        result.append({'month': month, 'userid': uid, 'agent_id': first['agent_id'],
                       'profile': first['profile'], 'stratum': first.get('stratum'),
                       'design_survey_weight': w, 'survey_weight': survey, 'inclusion_probability': pi,
                       'truth_mean_pp': real.get('q9_mean'), 'truth_density_iqr_pp': real.get('q9_iqr'),
                       'prior_mean_pp': prior, 'model_repeats': model, 'paired_eligible': valid,
                       'human_q9_missing_or_unscorable': human_bad, 'prior_missing_or_unscorable': prior_bad,
                       'invalid_model_repeats': invalid_repeats,
                       'truth_delta_pp': real['q9_mean'] - prior if not human_bad and not prior_bad else None,
                       'model_delta_pp_by_repeat': {str(r): model[str(r)]['mean'] - prior
                           if finite(model[str(r)]['mean']) and not prior_bad else None for r in REPEATS},
                       'prior_level_exploratory_band': prior_band(prior) if not prior_bad else None,
                       'normalized_month_weight': None, 'equal_month_person_weight': None})
    valid_by_month = defaultdict(list)
    for row in result:
        if row['paired_eligible']:
            valid_by_month[row['month']].append(row)
    for rows in valid_by_month.values():
        for row, weight in zip(rows, _weights([r['design_survey_weight'] for r in rows])):
            row['normalized_month_weight'] = float(weight)
            row['equal_month_person_weight'] = float(weight / len(valid_by_month))
    return result


def _mean_metrics(records):
    """Equal cell averages; absent values are explicit and never filled with zero."""
    keys = sorted({k for record in records for k in record})
    return {k: float(np.mean([r[k] for r in records]))
            if records and all(finite(r.get(k)) for r in records) else None for k in keys}


def _distribution_metrics(pred, truth, prior, weights, density_iqr=None, truth_density_iqr=None):
    p, y, prior, w = (np.asarray(a, float) for a in (pred, truth, prior, _weights(weights)))
    dp, dy = p - prior, y - prior
    center = quantile(p, w, .5)
    target_center = quantile(y, w, .5)
    mean = float(w @ p)
    delta_mean = float(w @ dp)
    result = {'q9_center_pp': center, 'q9_weighted_mean_pp': mean,
              'q9_center_bias_pp': center - target_center,
              'q9_center_mae_pp': abs(center - target_center),
              'individual_density_mean_bias_pp': float(w @ (p - y)),
              'individual_density_mean_mae_pp': float(w @ abs(p - y)),
              'cross_section_w1_pp': wasserstein1(p, w, y, w),
              'cross_person_iqr_pp': quantile(p, w, .75) - quantile(p, w, .25),
              'cross_person_sd_pp': float(np.sqrt(w @ ((p - mean) ** 2))),
              'real_cross_person_iqr_pp': quantile(y, w, .75) - quantile(y, w, .25),
              'delta_w1_pp': wasserstein1(dp, w, dy, w),
              'delta_weighted_mean_pp': delta_mean, 'delta_median_pp': quantile(dp, w, .5),
              'delta_q25_pp': quantile(dp, w, .25), 'delta_q75_pp': quantile(dp, w, .75),
              'delta_iqr_pp': quantile(dp, w, .75) - quantile(dp, w, .25),
              'delta_abs_mean_pp': float(w @ abs(dp)),
              'delta_abs_median_pp': quantile(abs(dp), w, .5),
              'delta_exact_zero_share': float(w @ (abs(dp) <= 1e-12)),
              'delta_sd_pp': float(np.sqrt(w @ ((dp - delta_mean) ** 2))),
              **mse_identity(p, y, w)}
    result['cross_person_iqr_gap_pp'] = result['cross_person_iqr_pp'] - result['real_cross_person_iqr_pp']
    absolute = abs(dp)
    bins = (('le_0_25', absolute <= .25), ('0_25_to_0_5', (absolute > .25) & (absolute <= .5)),
            ('0_5_to_1', (absolute > .5) & (absolute <= 1)),
            ('1_to_2', (absolute > 1) & (absolute <= 2)), ('above_2', absolute > 2))
    for label, mask in bins:
        result[f'update_abs_{label}_share'] = float(w @ mask)
    for threshold in THRESHOLDS:
        key = str(threshold).replace('.', '_')
        result[f'update_stable_at_{key}_share'] = float(w @ (absolute <= threshold))
        result[f'update_up_at_{key}_share'] = float(w @ (dp > threshold))
        result[f'update_down_at_{key}_share'] = float(w @ (dp < -threshold))
    if density_iqr is not None:
        d, td = np.asarray(density_iqr, float), np.asarray(truth_density_iqr, float)
        result.update(individual_density_iqr_mean_pp=float(w @ d),
                      individual_density_iqr_bias_pp=float(w @ (d - td)),
                      individual_density_iqr_mae_pp=float(w @ abs(d - td)))
    return result


def summarize_slice(assigned):
    rows = [r for r in assigned if r['paired_eligible']]
    w = [r['design_survey_weight'] for r in rows]
    base = {'n_assigned': len(assigned), 'n': len(rows), 'ess': ess(w),
            'suppressed': len(rows) < MIN_CELL_N}
    if base['suppressed']:
        return base
    truth, prior, tiqr = ([r[k] for r in rows] for k in ('truth_mean_pp', 'prior_mean_pp', 'truth_density_iqr_pp'))
    models = []
    for repeat in REPEATS:
        pred = [r['model_repeats'][str(repeat)]['mean'] for r in rows]
        iqr = [r['model_repeats'][str(repeat)]['iqr'] for r in rows]
        models.append({'repeat': repeat, 'metrics': _distribution_metrics(pred, truth, prior, w, iqr, tiqr)})
    return {**base,
            'truth': _distribution_metrics(truth, truth, prior, w, tiqr, tiqr),
            'model_repeat_cells': models,
            'model_average_of_repeat_metrics': _mean_metrics([m['metrics'] for m in models]),
            'copy_previous': _distribution_metrics(prior, truth, prior, w)}


def _scope_slice(cells, months):
    selected = [c for c in cells if c['month'] in months]
    reported = [c for c in selected if not c['suppressed']]
    return {'months_planned': list(months), 'months_reported': [c['month'] for c in reported],
            'n_months_reported': len(reported), 'n_person_months': sum(c['n'] for c in selected),
            'n_person_months_in_reportable_cells': sum(c['n'] for c in reported),
            'monthly_ess': {str(c['month']): c['ess'] for c in selected},
            'truth': _mean_metrics([c['truth'] for c in reported]),
            'model_average_of_month_repeat_metrics': _mean_metrics([c['model_average_of_repeat_metrics'] for c in reported]),
            'copy_previous': _mean_metrics([c['copy_previous'] for c in reported]),
            'coverage_complete': len(reported) == len(months)}


def _label(row, field):
    value = row['profile'].get(field)
    return 'missing' if value is None or str(value).strip() == '' else str(value)


def grouped_diagnostics(pairs):
    monthly, scopes = {}, {}
    for dimension, field in GROUP_FIELDS.items():
        monthly[dimension], scopes[dimension] = {}, {}
        for label in sorted({_label(r, field) for r in pairs}):
            monthly[dimension][label] = [dict(month=month, **summarize_slice(
                [r for r in pairs if r['month'] == month and _label(r, field) == label])) for month in MONTHS]
            scopes[dimension][label] = {scope: _scope_slice(monthly[dimension][label], months)
                                       for scope, months in SCOPES.items()}
    return {'fields': GROUP_FIELDS, 'monthly': monthly, 'scopes': scopes,
            'interpretation': 'Same paired support in truth/model/copy; within month-group weights renormalized. '
            'Cells with n<10 expose only support/ESS and suppression. Scope means use reportable months equally; '
            'incomplete coverage is not a complete-period group mean. Missing profile is a distinct label.'}


def update_cell(rows, threshold):
    """Conditional on an observed truth bucket, describe each model repeat."""
    weights = [r['design_survey_weight'] for r in rows]
    base = {'n': len(rows), 'ess': ess(weights), 'suppressed': len(rows) < MIN_CELL_N}
    if base['suppressed']:
        return base
    w = _weights(weights)
    dy = np.asarray([r['truth_delta_pp'] for r in rows])
    truth_buckets = np.asarray([direction(float(d), threshold) for d in dy])
    copy_error = abs(dy)
    repeat_cells = []
    for repeat in REPEATS:
        dm = np.asarray([r['model_delta_pp_by_repeat'][str(repeat)] for r in rows])
        mb = np.asarray([direction(float(d), threshold) for d in dm])
        error = abs(dm - dy)
        metrics = {'model_stable_share': float(w @ (mb == 'stable')),
                   'model_excessive_movement_share': float(w @ (abs(dm) > abs(dy) + threshold)),
                   'model_reverse_direction_share': float(w @ (((truth_buckets == 'up') & (mb == 'down'))
                                                               | ((truth_buckets == 'down') & (mb == 'up')))),
                   'model_direction_disagreement_share': float(w @ (mb != truth_buckets)),
                   'model_moves_while_truth_stable_share': float(w @ ((truth_buckets == 'stable') & (mb != 'stable'))),
                   'model_person_mae_pp': float(w @ error), 'copy_person_mae_pp': float(w @ copy_error),
                   'model_minus_copy_person_mae_pp': float(w @ (error - copy_error)),
                   'model_worse_than_copy_share': float(w @ (error > copy_error + 1e-12)),
                   'model_better_than_copy_share': float(w @ (error < copy_error - 1e-12)),
                   'model_ties_copy_share': float(w @ (abs(error - copy_error) <= 1e-12)),
                   'truth_abs_update_mean_pp': float(w @ abs(dy)), 'model_abs_update_mean_pp': float(w @ abs(dm)),
                   'truth_delta_mean_pp': float(w @ dy), 'model_delta_mean_pp': float(w @ dm)}
        for tb in ('stable', 'up', 'down'):
            for model_bucket in ('stable', 'up', 'down'):
                metrics[f'truth_{tb}__model_{model_bucket}_share'] = float(w @ ((truth_buckets == tb) & (mb == model_bucket)))
        repeat_cells.append({'repeat': repeat, 'metrics': metrics})
    return {**base, 'model_repeat_cells': repeat_cells,
            'average_of_repeat_metrics': _mean_metrics([c['metrics'] for c in repeat_cells])}


def update_diagnostics(pairs):
    valid = [r for r in pairs if r['paired_eligible']]
    by_threshold = {}
    for threshold in THRESHOLDS:
        groups = {}
        for bucket in ('all', 'stable', 'up', 'down'):
            cells = []
            for month in MONTHS:
                rows = [r for r in valid if r['month'] == month
                        and (bucket == 'all' or direction(r['truth_delta_pp'], threshold) == bucket)]
                cells.append({'month': month, **update_cell(rows, threshold)})
            scopes = {}
            for scope, months in SCOPES.items():
                selected = [c for c in cells if c['month'] in months]
                reportable = [c for c in selected if not c['suppressed']]
                scopes[scope] = {'months_planned': list(months), 'months_reported': [c['month'] for c in reportable],
                                 'n_person_months': sum(c['n'] for c in selected),
                                 'n_months_reported': len(reportable),
                                 'coverage_complete': len(reportable) == len(months),
                                 'metrics': _mean_metrics([c['average_of_repeat_metrics'] for c in reportable])}
            groups[bucket] = {'monthly': cells, 'scopes': scopes}
        by_threshold[str(threshold)] = groups
    return {'thresholds_pp': list(THRESHOLDS), 'by_threshold': by_threshold,
            'definition': {'stable': '|delta|<=threshold; boundaries included',
                           'up': 'delta>threshold', 'down': 'delta<-threshold',
                           'excessive_movement': '|model delta|>|truth delta|+threshold',
                           'reverse_direction': 'truth and model both outside stable bucket, opposite signs',
                           'rates_denominator': 'Within reported month/truth bucket, renormalized person design weights',
                           'magnitude_histogram': '[0,.25],(.25,.5],(.5,1],(1,2],(2,infinity) pp; in main and demographic metrics'},
            'interpretation': 'Truth-defined stable/up/down buckets are post-hoc error localization only; '
            'unavailable as a prospective updating strategy. Low copy error in the truth-stable group is '
            'partly guaranteed by its definition; bucket-level model/copy comparisons cannot select an '
            'implementable policy or establish advance recognition. Two repeat rates are averaged after computing each cell.'}


def _regression_cell(rows):
    w = _weights([r['design_survey_weight'] for r in rows])
    prior = np.asarray([r['prior_mean_pp'] for r in rows])
    truth = np.asarray([r['truth_mean_pp'] for r in rows])
    model = np.asarray([np.mean([r['model_repeats'][str(rep)]['mean'] for rep in REPEATS]) for r in rows])
    pc, yc, mc = (values - float(w @ values) for values in (prior, truth, model))
    varp, vary, varm = (float(w @ (values ** 2)) for values in (pc, yc, mc))
    cy, cm = float(w @ (pc * yc)), float(w @ (pc * mc))
    return {'n': len(rows), 'ess': ess(w), 'prior_variance_pp2': varp,
            'truth_current_variance_pp2': vary, 'model_two_repeat_mean_current_variance_pp2': varm,
            'truth_prior_covariance_pp2': cy, 'model_prior_covariance_pp2': cm,
            'truth_current_on_prior_slope': cy / varp if varp > 0 else None,
            'model_two_repeat_mean_current_on_prior_slope': cm / varp if varp > 0 else None,
            'truth_delta_on_prior_slope': cy / varp - 1 if varp > 0 else None,
            'model_two_repeat_mean_delta_on_prior_slope': cm / varp - 1 if varp > 0 else None,
            'model_to_truth_person_sd_ratio': float(np.sqrt(varm / vary)) if vary > 0 else None}


def regression_diagnostics(pairs):
    valid = [r for r in pairs if r['paired_eligible']]
    monthly = [{'month': m, **_regression_cell([r for r in valid if r['month'] == m])} for m in MONTHS]
    scopes = {}
    for scope, months in SCOPES.items():
        cells = [c for c in monthly if c['month'] in months]
        prior_variance = float(np.mean([c['prior_variance_pp2'] for c in cells]))
        scopes[scope] = {'months': list(months), 'monthly_equal_weight_means': _mean_metrics([
            {k: v for k, v in c.items() if k not in ('month', 'n', 'ess')} for c in cells]),
            'pooled_month_demeaned_slopes': {
                'truth_current_on_prior': float(np.mean([c['truth_prior_covariance_pp2'] for c in cells])) / prior_variance if prior_variance > 0 else None,
                'model_two_repeat_mean_current_on_prior': float(np.mean([c['model_prior_covariance_pp2'] for c in cells])) / prior_variance if prior_variance > 0 else None},
            'n_person_months': sum(c['n'] for c in cells)}
    return {'monthly': monthly, 'scopes': scopes,
            'method': 'Within each month subtract the design-weighted prior/current means; '
            'regress current truth or the mean of two model generations on prior. '
            'Pooled slopes use sum(month covariance)/sum(month prior variance) with each month total weight 1. '
            'Mean monthly slopes are separately labelled. The two-generation person mean is used only here; '
            'it replaces none of the primary cell metrics.',
            'interpretation': 'Descriptive persistence and cross-person compression; no causal update coefficient. '
            'One-year forecast horizons overlap by eleven months.'}


def coverage_diagnostics(pairs):
    def one(rows):
        valid = [r for r in rows if r['paired_eligible']]
        humans = sum(r['human_q9_missing_or_unscorable'] for r in rows)
        models = sum(bool(r['invalid_model_repeats']) for r in rows)
        return {'assigned_person_months': len(rows), 'paired_person_months': len(valid),
                'excluded_person_months': len(rows) - len(valid),
                'human_q9_missing_or_unscorable_person_months': humans,
                'prior_missing_or_unscorable_person_months': sum(r['prior_missing_or_unscorable'] for r in rows),
                'any_repeat_model_q9_failure_person_months': models,
                'human_and_model_failure_overlap_person_months': sum(r['human_q9_missing_or_unscorable'] and bool(r['invalid_model_repeats']) for r in rows),
                'assigned_design_weight_ess': ess([r['design_survey_weight'] for r in rows]),
                'paired_design_weight_ess': ess([r['design_survey_weight'] for r in valid]),
                'excluded_design_weight_share_of_assigned': sum(r['design_survey_weight'] for r in rows if not r['paired_eligible']) / sum(r['design_survey_weight'] for r in rows)}
    monthly = {str(m): one([r for r in pairs if r['month'] == m]) for m in MONTHS}
    identities = {}
    for label, rows in (('assigned', pairs), ('paired', [r for r in pairs if r['paired_eligible']])):
        counts = Counter(r['userid'] for r in rows)
        identities[label] = {'unique_userids': len(counts),
                             'userids_observed_in_multiple_selected_months': sum(n > 1 for n in counts.values()),
                             'person_months_from_repeated_userids': sum(n for n in counts.values() if n > 1),
                             'selected_months_per_userid_frequency': dict(sorted(Counter(counts.values()).items())),
                             'maximum_selected_months_per_userid': max(counts.values())}
    total = {'assigned_person_months': len(pairs), 'paired_person_months': sum(r['paired_eligible'] for r in pairs),
             'human_q9_missing_or_unscorable_person_months': sum(r['human_q9_missing_or_unscorable'] for r in pairs),
             'prior_missing_or_unscorable_person_months': sum(r['prior_missing_or_unscorable'] for r in pairs),
             'any_repeat_model_q9_failure_person_months': sum(bool(r['invalid_model_repeats']) for r in pairs)}
    return {'total': total, 'monthly': monthly, 'identity_coverage': identities,
            'duplicate_person_month_repeat_rows': 0, 'duplicate_person_month_identities_after_pairing': 0,
            'note': 'Duplicate rows/roster inconsistencies fail before analysis. Repeated userids across months '
            'are genuine coverage, not independent new persons. ESS is reported within month; '
            'no pooled ESS is presented as an independent sample size. Exclusion reasons can overlap.'}


def reconcile(monthly, source_summary):
    checks = []
    old = {(c['month'], c['repeat']): c for c in source_summary['cells']}
    keys = ('q9_center_mae_pp', 'q9_center_bias_pp', 'individual_density_mean_mae_pp',
            'cross_section_w1_pp', 'cross_person_iqr_pp', 'real_cross_person_iqr_pp')
    for month_cell in monthly:
        for repeat_cell in month_cell['model_repeat_cells']:
            month, repeat = month_cell['month'], repeat_cell['repeat']
            source = old[month, repeat]
            if source['common_scorable_n'] != month_cell['n']:
                raise ValueError('Support mismatch against archived evaluation')
            for role, current, previous in (
                    ('model', repeat_cell['metrics'], source['model_metrics_same_sample']),
                    ('copy_previous', month_cell['copy_previous'], source['scalar_baseline_metrics_same_sample']['copy_previous'])):
                for key in keys + (('delta_w1_pp', 'individual_density_mean_bias_pp', 'individual_density_iqr_mae_pp') if role == 'model' else ()):
                    residual = current[key] - previous[key]
                    checks.append({'month': month, 'repeat': repeat, 'role': role,
                                   'metric': key, 'absolute_residual': abs(residual)})
                    if not np.isclose(current[key], previous[key], rtol=1e-10, atol=1e-10):
                        raise ValueError(f'Archived evaluation reconciliation failed: {month}/{repeat}/{role}/{key}')
    return {'passed': True, 'n_cell_metric_checks': len(checks),
            'max_absolute_residual': max(c['absolute_residual'] for c in checks),
            'checks': checks,
            'method': 'Same common paired support, positive design weights, archived weighted empirical '
            'left-CDF median/W1 conventions; every original month-repeat model/copy metric is checked.'}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def support_audit(summary):
    """Report ESS warning flags without suppressing adequately sized n cells.

    ESS is common to truth, copy, and both repeat estimates in each slice.
    A scope average has no independent pooled-person ESS; its month cells
    retain these flags instead.
    """
    cells = []

    def add(kind, row, **identity):
        cells.append({'kind': kind, **identity, 'month': row['month'],
                      'n': row['n'], 'ess': row['ess'],
                      'metrics_suppressed_n_below_10': row.get('suppressed', row['n'] < MIN_CELL_N),
                      'weak_support_ess_below_10': row['ess'] < 10})

    for row in summary['monthly']:
        add('overall', row)
    for dimension, groups in summary['demographics']['monthly'].items():
        for label, rows in groups.items():
            for row in rows:
                add('demographic', row, dimension=dimension, label=label)
    for band, rows in summary['prior_levels']['monthly'].items():
        for row in rows:
            add('prior_level', row, label=band)
    for threshold, groups in summary['updates']['by_threshold'].items():
        for bucket, group in groups.items():
            for row in group['monthly']:
                add('truth_update_bucket', row, threshold_pp=float(threshold), label=bucket)
    for row in summary['regressions']['monthly']:
        add('person_regression', row)
    return {'ess_warning_threshold': 10, 'n_suppression_threshold': MIN_CELL_N,
            'n_support_cells': len(cells),
            'n_weak_support_cells_with_reported_metrics': sum(c['weak_support_ess_below_10']
                and not c['metrics_suppressed_n_below_10'] for c in cells),
            'cells': cells,
            'interpretation': 'ESS<10 is flagged as weak support even if n>=10; metrics are retained '
            'for those cells. n<10 metrics are suppressed. Each support row is shared by truth, copy '
            'and both model repeat cells; model repetitions never increase n or ESS.'}


def update_details(pairs):
    """Supplement selection shares and absolute/zero update distributions."""
    valid = [r for r in pairs if r['paired_eligible']]
    result = {}
    for threshold in THRESHOLDS:
        groups = {}
        for bucket in ('all', 'stable', 'up', 'down'):
            monthly = []
            for month in MONTHS:
                all_rows = [r for r in valid if r['month'] == month]
                rows = [r for r in all_rows if bucket == 'all' or direction(r['truth_delta_pp'], threshold) == bucket]
                weights = [r['design_survey_weight'] for r in rows]
                cell = {'month': month, 'n': len(rows), 'ess': ess(weights),
                        'weak_support_ess_below_10': ess(weights) < 10,
                        'suppressed': len(rows) < MIN_CELL_N}
                if cell['suppressed']:
                    monthly.append(cell)
                    continue
                w = _weights(weights)
                dy = np.asarray([r['truth_delta_pp'] for r in rows])

                def movement(delta):
                    return {'abs_update_mean_pp': float(w @ abs(delta)),
                            'abs_update_median_pp': quantile(abs(delta), w, .5),
                            'exact_zero_update_share': float(w @ (abs(delta) <= 1e-12))}

                repeat_cells = [{'repeat': rep, 'metrics': movement(np.asarray([
                    r['model_delta_pp_by_repeat'][str(rep)] for r in rows]))} for rep in REPEATS]
                cell.update(truth_bucket_weight_share=sum(weights) / sum(r['design_survey_weight'] for r in all_rows),
                            truth=movement(dy), copy_previous=movement(np.zeros(len(rows))),
                            model_repeat_cells=repeat_cells,
                            model_average_of_repeat_metrics=_mean_metrics([c['metrics'] for c in repeat_cells]))
                monthly.append(cell)
            scopes = {}
            for scope, months in SCOPES.items():
                reportable = [c for c in monthly if c['month'] in months and not c['suppressed']]
                scopes[scope] = {'months_planned': list(months), 'months_reported': [c['month'] for c in reportable],
                                 'n_person_months': sum(c['n'] for c in monthly if c['month'] in months),
                                 'truth_bucket_weight_share_equal_months': float(np.mean([c['truth_bucket_weight_share'] for c in reportable])) if reportable else None,
                                 'truth': _mean_metrics([c['truth'] for c in reportable]),
                                 'copy_previous': _mean_metrics([c['copy_previous'] for c in reportable]),
                                 'model_average_of_month_repeat_metrics': _mean_metrics([c['model_average_of_repeat_metrics'] for c in reportable])}
            groups[bucket] = {'monthly': monthly, 'scopes': scopes}
        result[str(threshold)] = groups
    return {'by_threshold': result,
            'method': 'Shares are design-weighted within month then averaged equally over months. '
            'Model absolute-change medians, means and zero rates are computed per repeat first. '
            'Exact zero is |delta|<=1e-12 pp, distinct from threshold stability and distinct from zero deflation probability.',
            'selection_caveat': 'Groups use observed human current-minus-prior changes. Low copy error in the '
            'stable group partly follows by definition (it cannot exceed the stability threshold). '
            'Differences across groups are post-hoc localization, not a deployable rule, advance recognition, '
            'or causal evidence for when to use the model.'}


def analyze(source, out):
    source, out = Path(source).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to((ROOT / 'outputs').resolve()):
        raise ValueError('Require a fresh private output directory under outputs')
    cases_path, summary_path = (source / name for name in ('cases_private.json', 'summary.json'))
    cases = json.loads(cases_path.read_text())
    previous = json.loads(summary_path.read_text())
    protocol = previous['protocol']
    if (tuple(protocol['months']) != MONTHS or protocol['n_per_month'] != 192
            or tuple(protocol['generation_repeats']) != REPEATS
            or previous.get('primary_weight') != 'design_survey_weight' or len(cases) != 4608):
        raise ValueError('Unexpected source protocol or archived case count')
    pairs = prepare_pairs(cases, months=MONTHS, n_per_month=192)
    n_valid = sum(r['paired_eligible'] for r in pairs)
    if n_valid != previous['coverage']['q9_common_person_months'] or n_valid != 2284:
        raise ValueError('Unexpected paired support; this diagnostic expects the frozen 2284 person-months')
    monthly = [{'month': m, **summarize_slice([r for r in pairs if r['month'] == m])} for m in MONTHS]
    reconciliation = reconcile(monthly, previous)
    prior_monthly = {band: [{'month': m, **summarize_slice([r for r in pairs if r['month'] == m
                        and r['prior_level_exploratory_band'] == band])} for m in MONTHS] for band in PRIOR_BANDS}
    summary = {'status': 'completed_offline_response_gap_diagnostic',
               'completed_at_utc': datetime.now(timezone.utc).isoformat(),
               'evaluation_api_calls': 0, 'refitted_bin_vectors': 0,
               'primary_weight': 'design_survey_weight', 'sparse_cell_minimum_n': MIN_CELL_N,
               'primary_month_scope': 'new_months', 'monthly': monthly,
               'scopes': {scope: _scope_slice(monthly, months) for scope, months in SCOPES.items()},
               'demographics': grouped_diagnostics(pairs), 'updates': update_diagnostics(pairs),
               'prior_levels': {'thresholds_pp': [2, 4, 8], 'threshold_status': 'exploratory_not_frozen_design',
                                'bands': {'below_2': 'prior<2', '2_to_below_4': '2<=prior<4',
                                          '4_to_below_8': '4<=prior<8', '8_or_above': 'prior>=8'},
                                'monthly': prior_monthly,
                                'scopes': {band: {scope: _scope_slice(cells, months) for scope, months in SCOPES.items()}
                                           for band, cells in prior_monthly.items()}},
               'regressions': regression_diagnostics(pairs), 'coverage': coverage_diagnostics(pairs),
               'reconciliation': reconciliation,
               'source_sha256': {str(cases_path.relative_to(ROOT)): _sha(cases_path),
                                 str(summary_path.relative_to(ROOT)): _sha(summary_path)},
               'analysis_sha256': {str(Path(__file__).resolve().relative_to(ROOT)): _sha(__file__),
                                  'scripts/analyze_sce_response_gap.py': _sha(ROOT / 'scripts/analyze_sce_response_gap.py'),
                                  'tests/test_sce_response_gap.py': _sha(ROOT / 'tests/test_sce_response_gap.py')},
               'method': ['Input is the archived fitted case file, not freshly read current targets or refitted raw probabilities.',
                          'Each person-month is paired on month/userid and requires valid Q9 means/IQRs in both model repeats, '
                          'finite current human Q9 mean/IQR and prior mean; exclusions retained privately.',
                          'Use design survey weight=survey weight/inclusion probability, normalized within month '
                          '(or month/group). Months receive equal weight; repetitions never multiply the person count.',
                          'Compute each model repeat cell first; average its metrics within month, then average months. '
                          'The model mean across repetitions is used only in the separate person regression.',
                          'Signed center bias is weighted-median model minus weighted-median human; person bias is '
                          'weighted mean of paired model-human errors. Center MAE is the absolute cell median error.',
                          'Individual density IQR describes within-person uncertainty; cross-person IQR describes '
                          'dispersion of fitted means. The scalar copy baseline has no copied density IQR in these inputs.',
                          'Weighted MSE equals cell mean-error squared plus cell centered-error variance. '
                          'Scope MSE/components average the cell identities; MAE is not additively decomposed.',
                          'n<10 monthly group cells have support/ESS only. Reportable-month means retain missing '
                          'coverage labels; no sparse cell is imputed.',
                          'Truth-defined update groups are retrospective localization. Prior level bands are exploratory.'],
               'limitations': ['Descriptive post-hoc A conditional historical reconstruction using actual personal priors; '
                               'no causal or independent blind-test claim.',
                               'The 12 selected months are separate reconstructions, not an autonomous consecutive trajectory '
                               'or a B forecast; no national prediction claim.',
                               'No uncertainty interval is inferred from 4608 generated rows; repeated people and '
                               'two generations are not independent persons or independent time observations.',
                               'This analysis does not change prompts, calibration, scorer, prior outputs, or selected months.']}
    out.mkdir(parents=True)
    for name, value in (('summary.json', summary), ('paired_frame_private.json', pairs),
                        ('support_audit.json', support_audit(summary)), ('update_details.json', update_details(pairs))):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    return summary
