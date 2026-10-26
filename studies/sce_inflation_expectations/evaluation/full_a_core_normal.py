"""Offline evaluation of a sealed Core + Normal full-frame A82 expansion.

The evaluator opens the frozen all-wave truth only after it has verified the
prediction package and its completion status. It never selects tau from human
answers and never refits Q9 densities. Model and observed distributions are
scored with the project's shared weighted empirical-CDF metrics.
"""
from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path

from .metrics import compare_distributions, distribution_summary, headline_errors
from ..experiments.frozen_batch import ROOT, dump, read_json, sha


PREDICTION = ROOT / 'outputs/sce_full_a_core_normal_prediction_20261026_v2'
TRUTH = ROOT / 'outputs/sce_monthly_fine_full_truth_20261023_v3'
BASELINE = ROOT / 'outputs/sce_full_a_t0_analysis_20261026_v1'
DEFAULT_OUT = ROOT / 'outputs/sce_full_a_core_normal_evaluation_20261026_v3'
TAUS = ('0', '8', '24')
EXPECTED_MONTHS = tuple(str(201901 + (i // 12) * 100 + i % 12) for i in range(82))
NATIONAL_FIT_BOUNDS = ('2019-01', '2022-12')
NATIONAL_TEST_BOUNDS = ('2023-01', '2025-10')


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _month_key(value):
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str):
        raise ValueError('Month must be YYYYMM, YYYY-MM, or an integer YYYYMM')
    key = value.replace('-', '')
    if len(key) != 6 or not key.isdigit() or key[-2:] not in {f'{m:02d}' for m in range(1, 13)}:
        raise ValueError('Invalid month: ' + value)
    return key


def _verify_hash_map(folder, mapping, *, required=()):
    folder = Path(folder).resolve()
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError('Nonempty files_sha256 mapping required')
    if not set(required) <= set(mapping):
        raise ValueError('Required files are not covered by files_sha256')
    for name, digest in mapping.items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder):
            raise ValueError('Manifest path escaped its package: ' + name)
        if not isinstance(digest, str) or sha(path) != digest:
            raise ValueError('Frozen file changed or missing: ' + name)


def _validate_summary_matches_observed(recorded, observed, *, month, field):
    """Ensure the frozen A82 baseline describes this exact full-wave target."""
    for key in ('n_valid', 'n_excluded'):
        if recorded.get(key) != observed.get(key):
            raise ValueError(f'Baseline full-wave support differs for {month} {field} ({key})')
    for key in ('weight_sum', 'ess', 'median_pp', 'mean_pp', 'q25_pp', 'q75_pp',
                'iqr_pp', 'std_pp', 'share_below_zero', 'share_above_eight'):
        a, b = recorded.get(key), observed.get(key)
        if not (_finite(a) and _finite(b) and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9)):
            raise ValueError(f'Baseline full-wave target statistic differs for {month} {field} ({key})')


def score_atom_distribution(atoms, masses, value_key, observed, observed_weights):
    """Score atom records against a fixed target using the shared metrics.

    Zero-mass atoms may carry a null value (used by the Core-actual-only
    sensitivity). Every positive-mass atom must have a finite value.
    """
    if not isinstance(atoms, list) or not isinstance(masses, list) or len(atoms) != len(masses):
        raise ValueError('Atom and mass arrays must be equally sized lists')
    values, weights = [], []
    for index, (atom, mass) in enumerate(zip(atoms, masses)):
        if not isinstance(atom, dict) or not _finite(mass) or mass < 0:
            raise ValueError(f'Invalid atom/mass at index {index}')
        value = atom.get(value_key)
        if mass > 0:
            if not _finite(value):
                raise ValueError(f'Positive mass has no finite {value_key} at index {index}')
            values.append(float(value))
            weights.append(float(mass))
    if not weights:
        raise ValueError('Prediction has no positive mass')
    result = compare_distributions(values, weights, observed, observed_weights)
    # This is a distribution of weighted donor atoms, not a person-level
    # effective sample size. Keep the distinction explicit in persisted output.
    simulated = result['simulated']
    simulated['valid_donor_atoms'] = simulated.pop('n_valid')
    simulated.pop('n_excluded', None)
    simulated['effective_atom_mass_size_not_person_ess'] = simulated.pop('ess')
    return result


def _checked_masses(atoms, masses, *, expected_total=None, maximum_total=None, label):
    if not isinstance(atoms, list) or not isinstance(masses, list) or len(atoms) != len(masses):
        raise ValueError(label + ' atom and mass arrays must align')
    if any(not isinstance(atom, dict) for atom in atoms):
        raise ValueError(label + ' atoms must be objects')
    if any(not _finite(value) or value < 0 for value in masses):
        raise ValueError(label + ' masses must be finite and nonnegative')
    total = float(sum(masses))
    if total <= 0:
        raise ValueError(label + ' masses must have positive total')
    if expected_total is not None and not math.isclose(
            total, expected_total, rel_tol=1e-9, abs_tol=1e-6):
        raise ValueError(label + ' mass does not conserve population_mass')
    if maximum_total is not None and total > maximum_total + max(1e-6, maximum_total * 1e-9):
        raise ValueError(label + ' mass exceeds population_mass')
    return total


def _target(full_wave, field):
    rows = [row for row in full_wave
            if _finite(row.get(field)) and _finite(row.get('weight')) and row['weight'] > 0]
    if not rows:
        raise ValueError('No positive-weight finite full-wave observations for ' + field)
    return ([float(row[field]) for row in rows], [float(row['weight']) for row in rows])


def _average(values):
    return float(statistics.mean(values)) if values else None


def _distribution_rollup(rows):
    """Equal-month aggregate of monthly full-wave comparison metrics."""
    return dict(
        n_months=len(rows),
        median_mae_pp=_average([r['median_error_pp'] for r in rows]),
        median_bias_pp=_average([r['median_bias_pp'] for r in rows]),
        mean_w1_pp=_average([r['w1_pp'] for r in rows]),
        median_w1_pp=float(statistics.median(r['w1_pp'] for r in rows)),
        mean_centered_w1_pp=_average([r['centered_w1_pp'] for r in rows]),
        mean_iqr_error_pp=_average([r['iqr_error_pp'] for r in rows]),
        mean_q25_gap_pp=_average([r['simulated']['q25_pp'] - r['observed']['q25_pp'] for r in rows]),
        mean_q75_gap_pp=_average([r['simulated']['q75_pp'] - r['observed']['q75_pp'] for r in rows]),
        mean_predicted_iqr_pp=_average([r['simulated']['iqr_pp'] for r in rows]),
        mean_observed_iqr_pp=_average([r['observed']['iqr_pp'] for r in rows]),
    )


def _yearly_headline(rows):
    result = {}
    for year in sorted({row['month'][:4] for row in rows}):
        block = [row for row in rows if row['month'].startswith(year)]
        result[year] = headline_errors([r['sim_pp'] for r in block],
                                       [r['truth_pp'] for r in block])
    return result


def _national_readout(national_rows, tau_rows):
    """Report fixed-truth macro scores and the same registered 48/34 blend."""
    from .monthly_main_readout import chronological_blend

    scenarios = {'before_t0': national_rows}
    scenarios.update({f'tau_{tau}': rows for tau, rows in tau_rows.items()})
    result = {'scenarios': {}, 'chronological_combinations': {}}
    for name, rows in scenarios.items():
        result['scenarios'][name] = dict(
            all_period=headline_errors([r['sim_pp'] for r in rows], [r['truth_pp'] for r in rows]),
            by_year=_yearly_headline(rows),
            early_48=headline_errors([r['sim_pp'] for r in rows[:48]],
                                     [r['truth_pp'] for r in rows[:48]]),
            late_34=headline_errors([r['sim_pp'] for r in rows[48:]],
                                    [r['truth_pp'] for r in rows[48:]]),
        )
        result['chronological_combinations'][name] = chronological_blend(
            rows, NATIONAL_FIT_BOUNDS, NATIONAL_TEST_BOUNDS)
    result['persistence_anchor'] = dict(
        all_period=headline_errors([r['anchor_pp'] for r in national_rows],
                                   [r['truth_pp'] for r in national_rows]),
        by_year=_yearly_headline([dict(row, sim_pp=row['anchor_pp']) for row in national_rows]),
        early_48=headline_errors([r['anchor_pp'] for r in national_rows[:48]],
                                 [r['truth_pp'] for r in national_rows[:48]]),
        late_34=headline_errors([r['anchor_pp'] for r in national_rows[48:]],
                                [r['truth_pp'] for r in national_rows[48:]]),
    )
    return result


def _numeric_tau(value):
    if type(value) not in (int, float) or not math.isfinite(value) or int(value) != value:
        raise ValueError('selected_tau must be one of the registered numeric taus')
    key = str(int(value))
    if key not in TAUS:
        raise ValueError('selected_tau must be one of ' + ', '.join(TAUS))
    return key


def _metadata_rows(summary):
    months = summary.get('months')
    if not isinstance(months, list) or len(months) != 82:
        raise ValueError('Prediction summary must register 82 month objects')
    result = {}
    for row in months:
        if not isinstance(row, dict):
            raise ValueError('Prediction month metadata must be objects')
        month = _month_key(row.get('month'))
        if month in result:
            raise ValueError('Duplicate prediction month metadata: ' + month)
        required_ints = ('target_frame_n', 'weighted_frame_n', 'missing_weight_n',
                         'core_n', 'normal_n', 'weighted_normal_n',
                         'valid_q9_model_donors', 'valid_q8_model_donors',
                         'excluded_personal_date_Core_now_statistical_Normal')
        for key in required_ints:
            if type(row.get(key)) is not int or row[key] < 0:
                raise ValueError('Invalid prediction month count: ' + key)
        if row['target_frame_n'] != row['core_n'] + row['normal_n']:
            raise ValueError('Core and Normal counts do not cover target_frame_n for ' + month)
        if row['weighted_normal_n'] > row['normal_n']:
            raise ValueError('weighted_normal_n exceeds normal_n for ' + month)
        for key in ('valid_q9_model_donors', 'valid_q8_model_donors'):
            if row[key] > row['core_n']:
                raise ValueError(key + ' exceeds core_n for ' + month)
        if row['excluded_personal_date_Core_now_statistical_Normal'] > row['normal_n']:
            raise ValueError('Out-of-month Core reclassified as Normal exceeds normal_n for ' + month)
        if row['weighted_frame_n'] > row['target_frame_n']:
            raise ValueError('weighted_frame_n exceeds target_frame_n for ' + month)
        if row['missing_weight_n'] > row['target_frame_n']:
            raise ValueError('missing_weight_n exceeds target_frame_n for ' + month)
        if row['weighted_frame_n'] + row['missing_weight_n'] != row['target_frame_n']:
            raise ValueError('Weighted and missing-weight rows do not cover target_frame_n for ' + month)
        if not _finite(row.get('population_mass')) or row['population_mass'] <= 0:
            raise ValueError('Positive finite population_mass required for ' + month)
        support = row.get('tau_support')
        if not isinstance(support, dict) or set(support) != set(TAUS):
            raise ValueError('All tau_support audit records are required for ' + month)
        for tau in TAUS:
            arm = support[tau]
            if not isinstance(arm, dict) or not {'q9', 'q8'} <= set(arm):
                raise ValueError('Q9/Q8 tau_support records required for ' + month + '/' + tau)
            for field in ('q9', 'q8'):
                values = arm[field]
                if (not isinstance(values, dict)
                        or not _finite(values.get('parent_population_fraction'))
                        or not _finite(values.get('unsupported_local_population_fraction'))):
                    raise ValueError('Parent/local unsupported fractions required for '
                                     + month + '/' + tau + '/' + field)
                if any(not 0 <= values[key] <= 1 for key in (
                        'parent_population_fraction', 'unsupported_local_population_fraction')):
                    raise ValueError('Tau support fractions must lie in [0, 1] for '
                                     + month + '/' + tau + '/' + field)
        result[month] = row
    if tuple(sorted(result)) != EXPECTED_MONTHS:
        raise ValueError('Prediction metadata must cover the registered all-82-month scope')
    if sum(row['target_frame_n'] for row in result.values()) != 98382:
        raise ValueError('The registered Core + Normal scope must cover 98,382 frame person-months')
    return result


def evaluate(prediction=PREDICTION, out=DEFAULT_OUT, *, truth=TRUTH, baseline=BASELINE):
    """Evaluate a sealed prediction package without making API calls or fits."""
    prediction, out, truth, baseline = map(
        lambda path: Path(path).resolve(), (prediction, out, truth, baseline))
    outputs_root = (ROOT / 'outputs').resolve()
    if not out.is_relative_to(outputs_root) or out.exists():
        raise ValueError('Fresh ignored evaluation output directory under outputs/ required')
    for name, folder in (('prediction', prediction), ('truth', truth), ('baseline', baseline)):
        if not folder.is_relative_to(outputs_root) or not folder.is_dir():
            raise ValueError(name + ' input must be a frozen directory under outputs/')
        if out == folder or folder.is_relative_to(out) or out.is_relative_to(folder):
            raise ValueError('Evaluation output cannot overlap a frozen input directory')

    # Prediction generation must be sealed before evaluation opens truth.
    prediction_manifest = read_json(prediction / 'manifest.json')
    prediction_summary_path = prediction / 'summary.json'
    prediction_summary = read_json(prediction_summary_path)
    if prediction_summary.get('status') != 'completed_full_a_core_normal_prediction':
        raise ValueError('Completed Core + Normal prediction package required before truth access')
    if (prediction_summary.get('new_api_calls') != 0
            or prediction_summary.get('new_q9_density_fits', 0) != 0
            or prediction_summary.get('new_q9_fits', 0) != 0
            or prediction_summary.get('target_answers_read') is not False):
        raise ValueError('Prediction must use zero new API calls and zero Q9 density refits')
    metadata = _metadata_rows(prediction_summary)
    selected_tau = _numeric_tau(prediction_summary.get('selected_tau'))
    aggregate_counts = {
        'total_frame_n': sum(row['target_frame_n'] for row in metadata.values()),
        'total_weighted_frame_n': sum(row['weighted_frame_n'] for row in metadata.values()),
        'total_core_n': sum(row['core_n'] for row in metadata.values()),
        'total_normal_n': sum(row['normal_n'] for row in metadata.values()),
    }
    expected_counts = dict(total_frame_n=98382, total_weighted_frame_n=98352,
                           total_core_n=41970, total_normal_n=56412)
    if aggregate_counts != expected_counts:
        raise ValueError('The all-wave scope must match the registered frame/Core/Normal counts')
    if (any(prediction_summary.get(key) != value for key, value in aggregate_counts.items())
            or sum(row['missing_weight_n'] for row in metadata.values()) != 30):
        raise ValueError('Summary-wide frame counts do not match the 82 monthly records')
    required_prediction_files = {'summary.json', 'parameter_selection.json'} | {
        f'{month}/atoms_private.json' for month in EXPECTED_MONTHS}
    _verify_hash_map(prediction, prediction_manifest.get('files_sha256'),
                     required=required_prediction_files)
    prediction_manifest_sha = sha(prediction / 'manifest.json')
    selection_path = prediction / 'parameter_selection.json'
    selection = read_json(selection_path)
    if (selection.get('status') != 'frozen_by_early_model_only_holdout'
            or selection.get('late_period_used_for_selection') is not False
            or _numeric_tau(selection.get('selected_tau')) != selected_tau):
        raise ValueError('Tau must match its frozen early-only, no-human-target selection record')
    candidates = selection.get('candidates')
    if (not isinstance(candidates, list)
            or any(not isinstance(row, dict) for row in candidates)
            or {_numeric_tau(row.get('tau')) for row in candidates} != set(TAUS)
            or any(not _finite(row.get('center_mae_pp')) for row in candidates)):
        raise ValueError('All registered tau candidate scores are required in the frozen selection record')

    # Verify frozen target and the previous A82 readout before scoring.
    truth_manifest = read_json(truth / 'manifest.json')
    full_wave_path = truth / 'full_wave_private.json'
    if sha(full_wave_path) != truth_manifest.get('full_wave_sha256'):
        raise ValueError('Frozen full-wave truth changed')
    baseline_manifest = read_json(baseline / 'manifest.json')
    _verify_hash_map(baseline, baseline_manifest.get('files_sha256'), required={'summary.json'})
    baseline_summary = read_json(baseline / 'summary.json')
    if baseline_summary.get('status') != 'completed_full_a_personal_evaluation':
        raise ValueError('Completed frozen full-A T0 baseline required')
    full_wave = read_json(full_wave_path)
    if not isinstance(full_wave, dict) or tuple(sorted(full_wave)) != EXPECTED_MONTHS:
        raise ValueError('Frozen all-wave human truth must contain the same 82 months')
    baseline_month_rows = baseline_summary.get('full_wave_monthly', [])
    baseline_months = {_month_key(row.get('month')): row for row in baseline_month_rows}
    if len(baseline_month_rows) != 82 or set(baseline_months) != set(EXPECTED_MONTHS):
        raise ValueError('A82 T0 baseline must contain all 82 full-wave monthly readouts')
    baseline_national_rows = baseline_summary.get('official_national', {}).get('monthly', [])
    baseline_national = {_month_key(row.get('month')): row for row in baseline_national_rows}
    if len(baseline_national_rows) != 82 or set(baseline_national) != set(EXPECTED_MONTHS):
        raise ValueError('A82 T0 baseline must contain all 82 fixed national references')

    # Check that the same frozen all-wave target feeds both sides of the
    # before/after distribution comparison. This prevents support drift.
    observed_by_month = {}
    for month in EXPECTED_MONTHS:
        wave = full_wave[month]
        if not isinstance(wave, list) or not wave:
            raise ValueError('Empty/malformed full-wave truth for ' + month)
        baseline_fields = baseline_months[month].get('fields', {})
        observed_by_month[month] = {}
        for field in ('q9_mean', 'q8_point'):
            values, weights = _target(wave, field)
            observed = distribution_summary(values, weights)
            recorded = baseline_fields.get(field, {}).get('observed')
            if not isinstance(recorded, dict):
                raise ValueError('A82 baseline has no observed full-wave distribution for ' + month)
            _validate_summary_matches_observed(recorded, observed, month=month, field=field)
            observed_by_month[month][field] = (values, weights, observed)

    per_month = []
    national_before = []
    national_by_tau = {tau: [] for tau in TAUS}
    for month in EXPECTED_MONTHS:
        metadata_row = metadata[month]
        population_mass = float(metadata_row['population_mass'])
        atom_path = prediction / month / 'atoms_private.json'
        atoms_doc = read_json(atom_path)
        if not isinstance(atoms_doc, dict):
            raise ValueError('Per-month prediction atoms must be an object: ' + month)
        if atoms_doc.get('month') is not None and _month_key(atoms_doc['month']) != month:
            raise ValueError('Month label mismatch in atoms file: ' + month)
        q9_atoms, q8_atoms = atoms_doc.get('q9_atoms'), atoms_doc.get('q8_atoms')
        if not isinstance(q9_atoms, list) or not isinstance(q8_atoms, list):
            raise ValueError('Both q9_atoms and q8_atoms are required for ' + month)
        q9_target, q9_weights, q9_observed = observed_by_month[month]['q9_mean']
        q8_target, q8_weights, q8_observed = observed_by_month[month]['q8_point']
        scores = {'q9_mean': {}, 'q8_point': {}}
        masses_by_tau = {}
        by_tau = atoms_doc.get('by_tau')
        if not isinstance(by_tau, dict) or set(by_tau) != set(TAUS):
            raise ValueError('by_tau must contain exactly 0, 8 and 24 for ' + month)
        for tau in TAUS:
            arm = by_tau[tau]
            if not isinstance(arm, dict):
                raise ValueError('Invalid tau arm for ' + month + '/' + tau)
            q9_mass, q8_mass = arm.get('q9_mass'), arm.get('q8_mass')
            q9_total = _checked_masses(q9_atoms, q9_mass, expected_total=population_mass,
                                       label=f'{month} tau={tau} Q9')
            q8_total = _checked_masses(q8_atoms, q8_mass, expected_total=population_mass,
                                       label=f'{month} tau={tau} Q8')
            if not math.isclose(q9_total, q8_total, rel_tol=1e-12, abs_tol=1e-6):
                raise ValueError('Q9 and Q8 tau mass totals differ for ' + month + '/' + tau)
            scores['q9_mean'][tau] = score_atom_distribution(
                q9_atoms, q9_mass, 'q9_mean', q9_target, q9_weights)
            scores['q8_point'][tau] = score_atom_distribution(
                q8_atoms, q8_mass, 'q8', q8_target, q8_weights)
            masses_by_tau[tau] = dict(q9=q9_total, q8=q8_total)

        actual_only = atoms_doc.get('core_actual_only')
        if not isinstance(actual_only, dict) or not {'q9_mass', 'q8_mass'} <= set(actual_only):
            raise ValueError('core_actual_only Q9/Q8 masses required for ' + month)
        actual_q9_total = _checked_masses(q9_atoms, actual_only['q9_mass'],
                                          maximum_total=population_mass,
                                          label=month + ' Core actual-only Q9')
        actual_q8_total = _checked_masses(q8_atoms, actual_only['q8_mass'],
                                          maximum_total=population_mass,
                                          label=month + ' Core actual-only Q8')
        scores['q9_mean']['core_actual_only'] = score_atom_distribution(
            q9_atoms, actual_only['q9_mass'], 'q9_mean', q9_target, q9_weights)
        scores['q8_point']['core_actual_only'] = score_atom_distribution(
            q8_atoms, actual_only['q8_mass'], 'q8', q8_target, q8_weights)

        base_fields = baseline_months[month]['fields']
        before = {field: base_fields[field] for field in ('q9_mean', 'q8_point')}
        baseline_q9_median = before['q9_mean']['simulated']['median_pp']
        if not math.isclose(baseline_q9_median, baseline_national[month]['sim_pp'],
                            rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError('Full-wave and fixed-national A82 T0 centers differ for ' + month)
        for tau in TAUS:
            q9_median = scores['q9_mean'][tau]['simulated']['median_pp']
            national_by_tau[tau].append(dict(baseline_national[month], sim_pp=q9_median))
        national_before.append(dict(baseline_national[month], sim_pp=baseline_q9_median))
        month_row = dict(
            month=month,
            frame=dict(target_frame_n=metadata_row['target_frame_n'],
                       weighted_frame_n=metadata_row['weighted_frame_n'],
                       missing_weight_n=metadata_row['missing_weight_n'],
                       core_n=metadata_row['core_n'], normal_n=metadata_row['normal_n'],
                       weighted_normal_n=metadata_row['weighted_normal_n'],
                       population_mass=population_mass),
            quality=dict(
                valid_q9_model_donors=metadata_row['valid_q9_model_donors'],
                valid_q8_model_donors=metadata_row['valid_q8_model_donors'],
                excluded_personal_date_Core_now_statistical_Normal=(
                    metadata_row['excluded_personal_date_Core_now_statistical_Normal']),
                selected_tau_support={
                    field: {
                        'parent_population_fraction': (
                            metadata_row['tau_support'][selected_tau][field]['parent_population_fraction']),
                        'unsupported_local_population_fraction': (
                            metadata_row['tau_support'][selected_tau][field]['unsupported_local_population_fraction']),
                    }
                    for field in ('q9', 'q8')
                },
            ),
            selected_tau=selected_tau,
            fields=dict(
                q9_mean=dict(observed=q9_observed, before=before['q9_mean'],
                             expanded_by_tau=scores['q9_mean'],
                             core_actual_only=scores['q9_mean']['core_actual_only'],
                             mass_by_tau={tau: masses_by_tau[tau]['q9'] for tau in TAUS},
                             core_actual_only_mass=actual_q9_total),
                q8_point=dict(observed=q8_observed, before=before['q8_point'],
                              expanded_by_tau=scores['q8_point'],
                              core_actual_only=scores['q8_point']['core_actual_only'],
                              mass_by_tau={tau: masses_by_tau[tau]['q8'] for tau in TAUS},
                              core_actual_only_mass=actual_q8_total),
            ),
            normal_expansion=dict(
                selected_tau_median_shift_pp=(
                    scores['q9_mean'][selected_tau]['simulated']['median_pp']
                    - before['q9_mean']['simulated']['median_pp']),
                selected_tau_q8_median_shift_pp=(
                    scores['q8_point'][selected_tau]['simulated']['median_pp']
                    - before['q8_point']['simulated']['median_pp']),
            ),
        )
        per_month.append(month_row)

    # Summarize equal-month full-wave errors, with the exact same human target
    # for before, all three taus and the Core-actual-only sensitivity.
    full_wave_summary = {}
    for field in ('q9_mean', 'q8_point'):
        base_rows = [row['fields'][field]['before'] for row in per_month]
        full_wave_summary[field] = dict(
            observed_distribution=dict(
                mean_median_pp=_average([row['fields'][field]['observed']['median_pp']
                                         for row in per_month]),
                mean_iqr_pp=_average([row['fields'][field]['observed']['iqr_pp']
                                      for row in per_month])),
            before_t0=_distribution_rollup(base_rows),
            expanded_by_tau={tau: _distribution_rollup(
                [row['fields'][field]['expanded_by_tau'][tau] for row in per_month])
                for tau in TAUS},
            core_actual_only=_distribution_rollup(
                [row['fields'][field]['core_actual_only'] for row in per_month]),
        )
        for tau in TAUS:
            expanded = full_wave_summary[field]['expanded_by_tau'][tau]
            base = full_wave_summary[field]['before_t0']
            full_wave_summary[field].setdefault('normal_expansion_delta_by_tau', {})[tau] = dict(
                median_mae_change_pp=expanded['median_mae_pp'] - base['median_mae_pp'],
                median_bias_change_pp=expanded['median_bias_pp'] - base['median_bias_pp'],
                mean_w1_change_pp=expanded['mean_w1_pp'] - base['mean_w1_pp'],
                mean_iqr_error_change_pp=expanded['mean_iqr_error_pp'] - base['mean_iqr_error_pp'],
            )

    national = _national_readout(national_before, national_by_tau)
    by_year_micro = {}
    for year in sorted({month[:4] for month in EXPECTED_MONTHS}):
        rows = [row for row in per_month if row['month'].startswith(year)]
        year_entry = {'n_months': len(rows), 'fields': {}}
        for field in ('q9_mean', 'q8_point'):
            year_entry['fields'][field] = dict(
                before_t0=_distribution_rollup([r['fields'][field]['before'] for r in rows]),
                expanded_by_tau={tau: _distribution_rollup(
                    [r['fields'][field]['expanded_by_tau'][tau] for r in rows]) for tau in TAUS},
                core_actual_only=_distribution_rollup(
                    [r['fields'][field]['core_actual_only'] for r in rows]),
            )
        by_year_micro[year] = year_entry
    normal_change_selected = dict(
        selected_tau=selected_tau,
        national_mae_change_pp=(
            national['scenarios'][f'tau_{selected_tau}']['all_period']['mae_pp']
            - national['scenarios']['before_t0']['all_period']['mae_pp']),
        national_rmse_change_pp=(
            national['scenarios'][f'tau_{selected_tau}']['all_period']['rmse_pp']
            - national['scenarios']['before_t0']['all_period']['rmse_pp']),
        national_bias_change_pp=(
            national['scenarios'][f'tau_{selected_tau}']['all_period']['bias_pp']
            - national['scenarios']['before_t0']['all_period']['bias_pp']),
        full_wave_q9_median_mae_change_pp=(
            full_wave_summary['q9_mean']['expanded_by_tau'][selected_tau]['median_mae_pp']
            - full_wave_summary['q9_mean']['before_t0']['median_mae_pp']),
        full_wave_q9_mean_w1_change_pp=(
            full_wave_summary['q9_mean']['expanded_by_tau'][selected_tau]['mean_w1_pp']
            - full_wave_summary['q9_mean']['before_t0']['mean_w1_pp']),
        full_wave_q9_mean_iqr_error_change_pp=(
            full_wave_summary['q9_mean']['expanded_by_tau'][selected_tau]['mean_iqr_error_pp']
            - full_wave_summary['q9_mean']['before_t0']['mean_iqr_error_pp']),
    )

    public_rows = []
    for row in per_month:
        month = row['month']
        q9 = row['fields']['q9_mean']
        q8 = row['fields']['q8_point']
        chosen_q9 = q9['expanded_by_tau'][selected_tau]
        chosen_q8 = q8['expanded_by_tau'][selected_tau]
        nat = baseline_national[month]
        public_rows.append(dict(
            month=month,
            target_frame_n=row['frame']['target_frame_n'],
            weighted_frame_n=row['frame']['weighted_frame_n'],
            missing_weight_n=row['frame']['missing_weight_n'],
            core_n=row['frame']['core_n'],
            normal_n=row['frame']['normal_n'],
            weighted_normal_n=row['frame']['weighted_normal_n'],
            valid_q9_model_donors=row['quality']['valid_q9_model_donors'],
            valid_q8_model_donors=row['quality']['valid_q8_model_donors'],
            excluded_personal_date_Core_now_statistical_Normal=(
                row['quality']['excluded_personal_date_Core_now_statistical_Normal']),
            selected_tau_q9_parent_population_fraction=(
                row['quality']['selected_tau_support']['q9']['parent_population_fraction']),
            selected_tau_q9_unsupported_local_population_fraction=(
                row['quality']['selected_tau_support']['q9']['unsupported_local_population_fraction']),
            selected_tau_q8_parent_population_fraction=(
                row['quality']['selected_tau_support']['q8']['parent_population_fraction']),
            selected_tau_q8_unsupported_local_population_fraction=(
                row['quality']['selected_tau_support']['q8']['unsupported_local_population_fraction']),
            population_mass=row['frame']['population_mass'],
            selected_tau=selected_tau,
            before_model_pp=q9['before']['simulated']['median_pp'],
            expanded_model_pp=chosen_q9['simulated']['median_pp'],
            truth_pp=nat['truth_pp'],
            baseline_pp=nat['anchor_pp'],
            before_q9_w1_pp=q9['before']['w1_pp'],
            expanded_q9_w1_pp=chosen_q9['w1_pp'],
            truth_q9_iqr_pp=q9['observed']['iqr_pp'],
            before_q9_iqr_pp=q9['before']['simulated']['iqr_pp'],
            expanded_q9_iqr_pp=chosen_q9['simulated']['iqr_pp'],
            before_q9_iqr_error_pp=q9['before']['iqr_error_pp'],
            expanded_q9_iqr_error_pp=chosen_q9['iqr_error_pp'],
            before_q9_median_gap_pp=q9['before']['median_bias_pp'],
            expanded_q9_median_gap_pp=chosen_q9['median_bias_pp'],
            before_q8_model_pp=q8['before']['simulated']['median_pp'],
            expanded_q8_model_pp=chosen_q8['simulated']['median_pp'],
            truth_q8_iqr_pp=q8['observed']['iqr_pp'],
            before_q8_w1_pp=q8['before']['w1_pp'],
            expanded_q8_w1_pp=chosen_q8['w1_pp'],
            before_q8_iqr_pp=q8['before']['simulated']['iqr_pp'],
            expanded_q8_iqr_pp=chosen_q8['simulated']['iqr_pp'],
            before_q8_iqr_error_pp=q8['before']['iqr_error_pp'],
            expanded_q8_iqr_error_pp=chosen_q8['iqr_error_pp'],
            **{f'tau_{tau}_q9_pp': q9['expanded_by_tau'][tau]['simulated']['median_pp']
               for tau in TAUS},
            **{f'tau_{tau}_q8_pp': q8['expanded_by_tau'][tau]['simulated']['median_pp']
               for tau in TAUS},
        ))

    yearly_rows = []
    for year in sorted(by_year_micro):
        micro = by_year_micro[year]
        before_macro = national['scenarios']['before_t0']['by_year'][year]
        expanded_macro = national['scenarios'][f'tau_{selected_tau}']['by_year'][year]
        row = dict(
            year=year,
            n_months=micro['n_months'],
            selected_tau=selected_tau,
            before_national_mae_pp=before_macro['mae_pp'],
            before_national_rmse_pp=before_macro['rmse_pp'],
            before_national_bias_pp=before_macro['bias_pp'],
            expanded_national_mae_pp=expanded_macro['mae_pp'],
            expanded_national_rmse_pp=expanded_macro['rmse_pp'],
            expanded_national_bias_pp=expanded_macro['bias_pp'],
            anchor_national_mae_pp=national['persistence_anchor']['by_year'][year]['mae_pp'],
        )
        for field, prefix in (('q9_mean', 'q9'), ('q8_point', 'q8')):
            before = micro['fields'][field]['before_t0']
            chosen = micro['fields'][field]['expanded_by_tau'][selected_tau]
            row.update({
                f'before_{prefix}_median_mae_pp': before['median_mae_pp'],
                f'expanded_{prefix}_median_mae_pp': chosen['median_mae_pp'],
                f'before_{prefix}_w1_pp': before['mean_w1_pp'],
                f'expanded_{prefix}_w1_pp': chosen['mean_w1_pp'],
                f'before_{prefix}_iqr_error_pp': before['mean_iqr_error_pp'],
                f'expanded_{prefix}_iqr_error_pp': chosen['mean_iqr_error_pp'],
                **{f'tau_{tau}_{prefix}_median_mae_pp':
                   micro['fields'][field]['expanded_by_tau'][tau]['median_mae_pp']
                   for tau in TAUS},
                **{f'tau_{tau}_{prefix}_w1_pp':
                   micro['fields'][field]['expanded_by_tau'][tau]['mean_w1_pp']
                   for tau in TAUS},
            })
        yearly_rows.append(row)

    result = dict(
        status='completed_full_a_core_normal_evaluation',
        new_api_calls=0,
        new_q9_density_fits=0,
        selected_tau=int(selected_tau),
        tau_selection_record=dict(
            status=selection['status'], selected_tau=int(selected_tau),
            target=selection.get('target'), development=selection.get('development'),
            late_period_used_for_selection=selection['late_period_used_for_selection'],
            loss=selection.get('loss'), candidates=candidates,
            sha256=sha(selection_path),
        ),
        prediction_status=prediction_summary['status'],
        month_count=len(per_month),
        target_frame_n_total=sum(row['frame']['target_frame_n'] for row in per_month),
        weighted_frame_n_total=sum(row['frame']['weighted_frame_n'] for row in per_month),
        missing_weight_n_total=sum(row['frame']['missing_weight_n'] for row in per_month),
        weighted_normal_n_total=sum(row['frame']['weighted_normal_n'] for row in per_month),
        valid_q9_model_donors_total=sum(row['quality']['valid_q9_model_donors'] for row in per_month),
        valid_q8_model_donors_total=sum(row['quality']['valid_q8_model_donors'] for row in per_month),
        excluded_personal_date_Core_now_statistical_Normal_total=sum(
            row['quality']['excluded_personal_date_Core_now_statistical_Normal']
            for row in per_month),
        prediction_quality=prediction_summary['quality'],
        population_mass_total=float(sum(row['frame']['population_mass'] for row in per_month)),
        national=national,
        full_wave_distribution=full_wave_summary,
        full_wave_distribution_by_year=by_year_micro,
        normal_expansion_change_selected_tau=normal_change_selected,
        monthly=per_month,
        limits=[
            'Expanded Q9/Q8 rows are weighted statistical predictions; Normal expansion creates no independent LLM answers.',
            'All before/after Q9 and Q8 W1/IQR comparisons use the same month-specific full-wave valid human distribution.',
            'Selected tau is read from the sealed prediction package and is not selected or changed using human target answers.',
            'National truth and persistence anchors are fixed from the original A82 T0 evaluation; 48/34 combinations are retrospective summaries.',
            'Full-wave human distributions and national targets are evaluation-only and never used to build predictions.',
            'Core-actual-only is an auxiliary sensitivity that excludes prior-retained or density-fit-fallback Core Q9 mass; it does not replace the frozen T0 before comparison.',
            'This evaluation performs no API calls, Q9 density refits, or Normal-answer generation.',
        ],
    )

    out.mkdir(parents=True, exist_ok=False)
    dump(out / 'summary.json', result)
    with (out / 'monthly_public.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(public_rows[0]))
        writer.writeheader()
        writer.writerows(public_rows)
    with (out / 'yearly.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(yearly_rows[0]))
        writer.writeheader()
        writer.writerows(yearly_rows)
    source_sha256 = {
        str((prediction / 'manifest.json').relative_to(ROOT)): prediction_manifest_sha,
        str(prediction_summary_path.relative_to(ROOT)): sha(prediction_summary_path),
        str((truth / 'manifest.json').relative_to(ROOT)): sha(truth / 'manifest.json'),
        str(full_wave_path.relative_to(ROOT)): sha(full_wave_path),
        str((baseline / 'manifest.json').relative_to(ROOT)): sha(baseline / 'manifest.json'),
        str((baseline / 'summary.json').relative_to(ROOT)): sha(baseline / 'summary.json'),
        **{str((prediction / rel).relative_to(ROOT)): digest
           for rel, digest in prediction_manifest['files_sha256'].items()
           if rel != 'summary.json'},
        str(Path(__file__).relative_to(ROOT)): sha(__file__),
        str(Path(__file__).with_name('metrics.py').relative_to(ROOT)):
            sha(Path(__file__).with_name('metrics.py')),
        str(Path(__file__).with_name('monthly_main_readout.py').relative_to(ROOT)):
            sha(Path(__file__).with_name('monthly_main_readout.py')),
    }
    dump(out / 'manifest.json', dict(
        status=result['status'],
        new_api_calls=0,
        source_sha256=source_sha256,
        files_sha256={name: sha(out / name)
                      for name in ('summary.json', 'monthly_public.csv', 'yearly.csv')},
    ))
    return dict(status=result['status'], month_count=len(per_month),
                selected_tau=int(selected_tau), new_api_calls=0,
                output=str(out.relative_to(ROOT)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prediction', type=Path, default=PREDICTION)
    parser.add_argument('--truth', type=Path, default=TRUTH)
    parser.add_argument('--baseline', type=Path, default=BASELINE)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    import json
    print(json.dumps(evaluate(args.prediction, args.out, truth=args.truth,
                              baseline=args.baseline), ensure_ascii=False))


if __name__ == '__main__':
    main()
