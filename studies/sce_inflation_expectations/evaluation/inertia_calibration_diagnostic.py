"""Offline fixed-weight aggregate calibration; original Q9 answers stay untouched."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ARMS = ('no_prior', 'own_previous', 'permuted_previous')
WEIGHTS = (0., .2, .4, .6, .8, 1.)
MAIN_WEIGHT = .4


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def blend(predicted, anchor, weight):
    if not np.isfinite([predicted, anchor, weight]).all() or not 0 <= weight <= 1:
        raise ValueError('finite values and weight in [0,1] required')
    return float(weight * anchor + (1 - weight) * predicted)


def forecast_metrics(predicted, observed):
    p, y = np.asarray(predicted, float), np.asarray(observed, float)
    if p.shape != y.shape or p.ndim != 1 or not len(p) or not np.isfinite(p).all() or not np.isfinite(y).all():
        raise ValueError('matched finite scalar forecasts required')
    error = p - y
    return {'mae_pp': float(np.abs(error).mean()), 'rmse_pp': float(np.sqrt((error**2).mean())),
            'bias_pp': float(error.mean()), 'error_variance_pp_squared_ddof0': float(np.var(error, ddof=0))}


def latest_public_release(releases, as_of):
    cutoff = datetime.fromisoformat(as_of)
    if cutoff.tzinfo is None:
        raise ValueError('timezone-aware cutoff required')
    available = [r for r in releases if datetime.fromisoformat(r['published_date'] + 'T23:59:59').replace(
        tzinfo=ZoneInfo('America/New_York')) <= cutoff]
    if not available:
        raise ValueError('no published SCE anchor before cutoff')
    return max(available, key=lambda r: r['reference_period'])


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--analysis', type=Path, required=True)
    parser.add_argument('--public-ledger', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    trial, analysis, ledger_file, out = (p.resolve() for p in (args.trial, args.analysis, args.public_ledger, args.out))
    if out.exists() or not out.is_relative_to(root / 'outputs'):
        raise ValueError('fresh ignored output directory required')
    s = json.loads((analysis / 'summary.json').read_text())
    if s['status'] != 'completed_offline_analysis' or s['actual_calls'] != 288:
        raise ValueError('requires completed original 288-answer trial')
    if sha(trial / 'trial_manifest.json') != s['trial_manifest_sha256']:
        raise ValueError('trial manifest changed')
    from ..confidence_trial import check_frozen
    check_frozen(root, trial, json.loads((trial / 'trial_manifest.json').read_text()))
    releases = json.loads(ledger_file.read_text())['headline_releases']
    if len({r['reference_period'] for r in releases}) != len(releases):
        raise ValueError('one first release per survey period required')
    raw = json.loads((analysis / 'paired_evaluation_private.json').read_text())
    cells, source_hashes = [], {}
    for month, record in s['months'].items():
        as_of = record['metadata']['as_of']
        available = latest_public_release(releases, as_of)
        target = next(r for r in releases if r['reference_period'] == month[:4] + '-' + month[4:])
        for r in (available, target):
            path = root / r['source_file']
            if sha(path) != r['source_sha256']:
                raise ValueError('public first-release evidence changed')
            source_hashes[r['source_file']] = r['source_sha256']
        for repeat, measures in record['repeats'].items():
            q9 = measures['Q9']
            selected = [r for r in raw if r['month'] == month and r['repeat'] == int(repeat) and r['measure'] == 'Q9'
                        and all(isinstance(r.get(k), (int, float)) and np.isfinite(r[k]) for k in ('real', 'own_prior') + ARMS)]
            if len(selected) != q9['n_common']:
                raise ValueError('common sample differs from original evaluation')
            variants = {}
            for weight in WEIGHTS:
                key = f'{weight:.1f}'
                variants[key] = {
                    'same_sample': {a: blend(q9['arms'][a]['distribution']['median_pp'], q9['prior_persistence_common_sample']['distribution']['median_pp'], weight) for a in ARMS},
                    'public_anchor_reference': {a: blend(q9['arms'][a]['distribution']['median_pp'], available['value_pp'], weight) for a in ARMS}}
            # No post-calibration individual answers exist. Record the original
            # distribution, plus a mathematical shift check, not synthetic Q9.
            variance = {a: float(np.var([r[a] for r in selected], ddof=0)) for a in ('real', 'own_prior') + ARMS}
            for a in ARMS:
                values = np.asarray([r[a] for r in selected])
                delta = variants['0.4']['same_sample'][a] - q9['arms'][a]['distribution']['median_pp']
                if not np.isclose(np.var(values + delta, ddof=0), variance[a], atol=1e-10):
                    raise ValueError('uniform translation variance identity failed')
            cells.append({'month': month, 'repeat': int(repeat), 'n_common': len(selected), 'as_of': as_of,
                'same_sample_truth_pp': q9['real']['median_pp'],
                'same_sample_anchor_pp': q9['prior_persistence_common_sample']['distribution']['median_pp'],
                'public_truth_pp': target['value_pp'], 'public_truth_source': target['source_url'],
                'public_anchor': {k: available[k] for k in ('reference_period', 'value_pp', 'published_date', 'source_url')},
                'variants': variants, 'raw_within_period_variance_pp_squared_ddof0': variance,
                'raw_within_period_IQR_pp': {'real': q9['real']['cross_person_iqr_pp'], 'own_prior': q9['prior_persistence_common_sample']['distribution']['cross_person_iqr_pp'],
                                          **{a: q9['arms'][a]['distribution']['cross_person_iqr_pp'] for a in ARMS}}})
    result = {'status': 'completed_offline_fixed_weight_diagnostic', 'new_api_calls': 0, 'cost_usd': 0,
        'main_history_weight': MAIN_WEIGHT, 'fixed_sensitivity_weights': list(WEIGHTS), 'weight_selection_performed': False,
        'original_trial': str(trial.relative_to(root)), 'original_analysis': str(analysis.relative_to(root)),
        'n_periods': len(s['months']), 'repetitions_per_period': 2, 'scopes': {}, 'cells': cells,
        'aggregation_rule': 'equal periods and equal generations; generations are not independent months',
        'personal_answers_or_simulation_configuration_changed': False,
        'source_sha256': {str((analysis / 'summary.json').relative_to(root)): sha(analysis / 'summary.json'),
            str((analysis / 'paired_evaluation_private.json').relative_to(root)): sha(analysis / 'paired_evaluation_private.json'),
            str(ledger_file.relative_to(root)): sha(ledger_file), **source_hashes},
        'limitations': ['Four examined development periods and age-balanced 12-person frames, not representative national estimates or holdout.',
            'Public-anchor reference compares this small-sample scalar to national truth; its population estimand differs from same-sample metrics.',
            'The original observed-prior treatment used real t-1 microdata; using PIT public anchors does not turn this run into strict forecast B.',
            'Only headline predictions are blended, not personal probabilities; the mixture is not the direct median of unchanged simulated Q9 answers.',
            'Two-generation variance is a rough conditional diagnostic, not a precise estimate of model uncertainty.',
            '0.4 is a borrowed fixed sensitivity setting, not a trained SCE parameter. No best weight is selected on these observations.']}
    for scope, truth_key, anchor_key in (('same_sample', 'same_sample_truth_pp', 'same_sample_anchor_pp'),
                                        ('public_anchor_reference', 'public_truth_pp', None)):
        truth = [c[truth_key] for c in cells]
        anchor = [c[anchor_key] if anchor_key else c['public_anchor']['value_pp'] for c in cells]
        block = {'target_description': 'same selected real respondents, same frozen scorer and empirical median' if anchor_key else 'official national first-release headline; nonrepresentative small-sample reference only',
                 'persistence': forecast_metrics(anchor, truth), 'weights': {}}
        for w in WEIGHTS:
            key = f'{w:.1f}'
            block['weights'][key] = {a: forecast_metrics([c['variants'][key][scope][a] for c in cells], truth) for a in ARMS}
        # Average the two scalar generations BEFORE scoring as a separate
        # sensitivity, not quietly replacing the original per-generation results.
        block['average_two_generations_before_scoring'] = {}
        for w in (0., MAIN_WEIGHT):
            key = f'{w:.1f}'
            block['average_two_generations_before_scoring'][key] = {}
            for a in ARMS:
                predictions, yy = [], []
                for m in s['months']:
                    rr = [c for c in cells if c['month'] == m]
                    if len(rr) != 2 or rr[0][truth_key] != rr[1][truth_key]:
                        raise ValueError('generation samples differ; do not average silently')
                    predictions.append(np.mean([c['variants'][key][scope][a] for c in rr]))
                    yy.append(rr[0][truth_key])
                block['average_two_generations_before_scoring'][key][a] = forecast_metrics(predictions, yy)
        result['scopes'][scope] = block
    result['heterogeneity'] = {'method': 'average within-period descriptive population variance, ddof=0, percent-point-squared; same unmodified personal Q9 means',
        'mean_variance_pp_squared': {a: float(np.mean([c['raw_within_period_variance_pp_squared_ddof0'][a] for c in cells])) for a in ('real', 'own_prior') + ARMS},
        'mean_IQR_pp': {a: float(np.mean([c['raw_within_period_IQR_pp'][a] for c in cells])) for a in ('real', 'own_prior') + ARMS},
        'post_headline_calibration_personal_variance_change': 0.0}
    result['two_generation_variance'] = {'description': 'average across four periods of sample variance over the two scalar generations (ddof=1); fixed historical anchor',
        'raw_pp_squared': {a: float(np.mean([np.var([c['variants']['0.0']['same_sample'][a] for c in cells if c['month'] == m], ddof=1) for m in s['months']])) for a in ARMS},
        'calibrated_04_multiplier': (1 - MAIN_WEIGHT)**2}
    result['two_generation_variance']['calibrated_04_pp_squared'] = {a: (1 - MAIN_WEIGHT)**2 * v for a, v in result['two_generation_variance']['raw_pp_squared'].items()}
    result['code_sha256'] = {str(Path(__file__).relative_to(root)): sha(__file__), 'scripts/analyze_sce_inertia_calibration.py': sha(root / 'scripts/analyze_sce_inertia_calibration.py')}
    out.mkdir(parents=True)
    (out / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'same_sample_04': result['scopes']['same_sample']['weights']['0.4'],
                      'public_reference_04': result['scopes']['public_anchor_reference']['weights']['0.4'],
                      'heterogeneity': result['heterogeneity'], 'new_api_calls': 0}))


if __name__ == '__main__':
    main()
