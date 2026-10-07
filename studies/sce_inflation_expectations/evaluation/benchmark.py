"""Long-span retrospective benchmarks under separate reconstruction/forecast contracts."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import calendar
import numpy as np
from zoneinfo import ZoneInfo

from .baselines import ar1_forecast, arx_direct_forecast, conditional_donor_distribution, sticky_information_agent
from .metrics import compare_distributions, headline_errors, paired_month_mae_interval, quantile

TZ = ZoneInfo('America/New_York')


def shift_month(month, count):
    year, number = map(int, month.split('-'))
    absolute = year * 12 + number - 1 + count
    return f'{absolute // 12:04d}-{absolute % 12 + 1:02d}'


def month_distance(later, earlier):
    ly, lm = map(int, later.split('-'))
    ey, em = map(int, earlier.split('-'))
    return (ly - ey) * 12 + lm - em


def cutoff_for(target, policy, cpi_calendar):
    if policy == 'previous_month_end':
        year, month = map(int, shift_month(target, -1).split('-'))
        day = calendar.monthrange(year, month)[1]
    elif policy == 'current_month_cpi_release_day_end':
        row = next(r for r in cpi_calendar if r['target_month'] == target)
        year, month, day = map(int, row['published_date'].split('-'))
    else:
        raise ValueError(f'Unknown cutoff: {policy}')
    return datetime(year, month, day, 23, 59, 59, tzinfo=TZ)


def available_rows(rows, cutoff):
    """Date-only evidence is conservatively available at the end of its release day."""
    return sorted([r for r in rows if datetime.fromisoformat(r['published_date']).replace(
        hour=23, minute=59, second=59, tzinfo=TZ) <= cutoff], key=lambda r: r['reference_period'])


def macro_feature(target, policy, inputs):
    cutoff = cutoff_for(target, policy, inputs['cpi_calendar'])
    y = available_rows(inputs['headline_releases'], cutoff)
    cpi = available_rows(inputs['cpi_first_releases'], cutoff)
    if not y or not cpi:
        return None
    return [y[-1]['value_pp'], cpi[-1]['value']], cpi[-1]


def forecast_benchmarks(inputs, protocol):
    rows, skipped = [], []
    releases = inputs['headline_releases']
    targets = [r for r in releases if protocol['evaluation_start'] <= r['reference_period'] <= protocol['evaluation_end']]
    for policy in protocol['forecast_cutoffs']:
        for target in targets:
            month = target['reference_period']
            cutoff = cutoff_for(month, policy, inputs['cpi_calendar'])
            history = available_rows(releases, cutoff)
            if not history or any(r['reference_period'] >= month for r in history):
                raise ValueError(f'Target/future answer leaked into {month} history')
            if len(history) < protocol['minimum_training_observations']:
                raise ValueError(f'Too little headline warmup at {month}')
            # Missing reference months would invalidate AR recursion and rolling means.
            if any(month_distance(b['reference_period'], a['reference_period']) != 1
                   for a, b in zip(history, history[1:])):
                raise ValueError('Gapped headline training history')
            values = [r['value_pp'] for r in history]
            horizon = month_distance(month, history[-1]['reference_period'])
            ar, parameters = ar1_forecast(values, horizon)
            predictions = {'persistence': (values[-1], {}),
                           'mean12': (float(np.mean(values[-protocol['rolling_mean_months']:])), {}),
                           'ar1_expanding': (ar, parameters)}
            for rate in protocol['sticky_agent_update_probabilities']:
                predictions[f'sticky_agent_{rate:g}'] = (sticky_information_agent(
                    values, update_probability=rate, n_agents=protocol['simple_agent_n'], seed=protocol['seed']),
                    {'update_probability_per_release': rate})
            feature = macro_feature(month, policy, inputs)
            training_x, training_y, training_months = [], [], []
            for past in history:
                if past['reference_period'] < protocol['evaluation_start']:
                    continue
                f = macro_feature(past['reference_period'], policy, inputs)
                if f is not None:
                    training_x.append(f[0])
                    training_y.append(past['value_pp'])
                    training_months.append(past['reference_period'])
            if feature is not None:
                predictions['cpi_as_expectation'] = (feature[0][1], {'cpi_reference_period': feature[1]['reference_period']})
                if len(training_y) >= protocol['minimum_training_observations']:
                    arx, param = arx_direct_forecast(training_x, training_y, feature[0])
                    param.update(training_first=training_months[0], training_last=training_months[-1],
                                 cpi_reference_period=feature[1]['reference_period'])
                    predictions['arx_sce_cpi'] = (arx, param)
            for name in ['cpi_as_expectation', 'arx_sce_cpi']:
                if name not in predictions:
                    skipped.append(dict(policy=policy, target_month=month, method=name,
                                        reason='macro_history_unavailable_or_fewer_than_12_released_training_pairs'))
            for method, (value, param) in predictions.items():
                if not np.isfinite(value):
                    raise ValueError('Nonfinite forecast must not enter the benchmark')
                rows.append(dict(policy=policy, target_month=month, as_of=cutoff.isoformat(),
                                 method=method, prediction_pp=float(value), truth_pp=target['value_pp'],
                                 chart_truth_pp=target['chart_snapshot_value_pp'],
                                 last_known_sce_month=history[-1]['reference_period'],
                                 last_known_sce_release_date=history[-1]['published_date'],
                                 observation_horizon=horizon, n_training=len(history),
                                 parameters=param, error_pp=float(value - target['value_pp'])))
    return rows, skipped


def summarize_forecasts(rows, protocol):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row['policy'], row['method'])].append(row)
    result = []
    for (policy, method), data in sorted(grouped.items()):
        data.sort(key=lambda r: r['target_month'])
        metrics = headline_errors([r['prediction_pp'] for r in data], [r['truth_pp'] for r in data])
        chart = headline_errors([r['prediction_pp'] for r in data], [r['chart_truth_pp'] for r in data])
        base = {r['target_month']: r for r in grouped[(policy, 'persistence')]}
        interval = paired_month_mae_interval([r['error_pp'] for r in data],
                    [base[r['target_month']]['error_pp'] for r in data],
                    block_length=min(protocol['bootstrap']['circular_block_length'], len(data)),
                    draws=protocol['bootstrap']['draws'], seed=protocol['seed'])
        annual = {year: headline_errors([r['prediction_pp'] for r in data if r['target_month'].startswith(year)],
                                        [r['truth_pp'] for r in data if r['target_month'].startswith(year)])
                  for year in sorted({r['target_month'][:4] for r in data})}
        result.append(dict(policy=policy, method=method, first_month=data[0]['target_month'],
                           last_month=data[-1]['target_month'], primary=metrics,
                           chart_snapshot_sensitivity=chart, annual=annual,
                           matched_persistence=headline_errors([base[r['target_month']]['prediction_pp'] for r in data],
                                                               [r['truth_pp'] for r in data]),
                           paired_mae_vs_persistence=interval))
    return result


def reconstruction_benchmarks(micro, protocol):
    """A-line only: retrospective population cells and historical official-derived means."""
    frames = {f'{int(m) // 100}-{int(m) % 100:02d}': frame for m, frame in micro.groupby('date')}
    rows, diagnostics = [], []
    for month in sorted(frames):
        if not protocol['evaluation_start'] <= month <= protocol['evaluation_end']:
            continue
        prior = frames[shift_month(month, -1)]
        current = frames[month]
        def valid(frame):
            return frame[np.isfinite(frame['Q9_mean']) & np.isfinite(frame['weight']) & (frame['weight'] > 0)].copy()
        p, t = valid(prior), valid(current)
        fields = protocol['reconstruction_conditional_fields']
        def cells(frame):
            return [tuple(str(x).strip() if x is not None and str(x).strip() not in ('', 'nan', '<NA>') else 'unknown' for x in row)
                    for row in frame[fields].to_numpy()]
        pc, tc = cells(p), cells(t)
        px, pw, tx, tw = p['Q9_mean'].to_numpy(), p['weight'].to_numpy(), t['Q9_mean'].to_numpy(), t['weight'].to_numpy()
        cx, cw, cell_distributions, fallback = conditional_donor_distribution(px, pw, pc, tc, tw,
                    minimum_donors=protocol['reconstruction_minimum_donor_count'])
        constraint = quantile(tx, tw, .5)
        for method, x, w, conditional, constrained in [
            ('prior_distribution', px, pw, False, False),
            ('population_conditional', cx, cw, True, False),
            ('prior_known_median', px, pw, False, True),
            ('conditional_known_median', cx, cw, True, True)]:
            shift = constraint - quantile(x, w, .5) if constrained else 0.
            comparison = compare_distributions(x + shift, w, tx, tw)
            group_errors, group_masses = [], []
            for cell in sorted(set(tc), key=str):
                mask = np.array([c == cell for c in tc])
                if mask.sum() < protocol['reconstruction_minimum_donor_count']:
                    continue
                gx, gw = cell_distributions[cell] if conditional else (px, pw)
                group_errors.append(abs(quantile(gx + shift, gw, .5) - quantile(tx[mask], tw[mask], .5)))
                group_masses.append(float(tw[mask].sum()))
            # Uncertainty is left at its historical conditional distribution, not broadened ad hoc.
            ux, uw = p['Q9_iqr'].to_numpy(), pw
            if conditional:
                ux, uw, _, _ = conditional_donor_distribution(ux, pw, pc, tc, tw,
                              minimum_donors=protocol['reconstruction_minimum_donor_count'])
            uncertainty_error = abs(quantile(ux, uw, .5) - quantile(t['Q9_iqr'].to_numpy(), tw, .5))
            rows.append(dict(target_month=month, method=method, line='A_retrospective_reconstruction',
                             scoring_version='official_provided_derived_values_latest_snapshot',
                             output_scope='distribution_of_personal_means_and_uncertainties_not_raw_Q9',
                             known_constraint='current_micro_weighted_median' if constrained else None,
                             group_median_error_pp=float(np.average(group_errors, weights=group_masses)),
                             group_mass_coverage=float(sum(group_masses) / tw.sum()),
                             uncertainty_median_error_pp=float(uncertainty_error), **comparison))
        diagnostics.append(dict(target_month=month, total_rows=len(current), valid_mean_rows=len(t),
                                excluded_mean_rows=len(current)-len(t), donor_month=shift_month(month,-1),
                                fallback_cells=[str(c) for c in fallback]))
    return rows, diagnostics


def summarize_reconstruction(rows):
    result = []
    names = ['w1_pp', 'centered_w1_pp', 'median_error_pp', 'iqr_error_pp',
             'group_median_error_pp', 'uncertainty_median_error_pp']
    for method in sorted({r['method'] for r in rows}):
        selected = [r for r in rows if r['method'] == method]
        result.append(dict(method=method, n_months=len(selected),
                           metrics={k: float(np.mean([r[k] for r in selected])) for k in names},
                           annual={year: {k: float(np.mean([r[k] for r in selected if r['target_month'].startswith(year)]))
                                          for k in names} for year in sorted({r['target_month'][:4] for r in selected})}))
    return result
