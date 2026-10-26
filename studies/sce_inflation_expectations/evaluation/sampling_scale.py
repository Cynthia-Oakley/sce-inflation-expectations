"""Finite-frame sampling experiment; no model client or new simulation answers.

Reproduce the actual eligible->192->96 age/income design. The finite SCE wave
is held fixed: these intervals measure selection variability, not uncertainty
about the US population, future months, or the LLM's response to unseen people.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

from .metrics import quantile
from .reference_validation import score
from ..reference_population_preparation import sample_strata

ROOT = Path(__file__).resolve().parents[3]
MONTHS = (202009, 202109, 202206, 202312, 202410, 202503)
REFERENCE = ROOT/'outputs/sce_reference_validation_trial_20261017_v2'
TRUTH = ROOT/'outputs/sce_behavior_mechanism_audit_20261014_v3/reference_with_controls_private.parquet'
CASES = ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1/cases_private.json'
CURRENT = ROOT/'outputs/sce_price_background_evaluation_20261021_v1/cases_private.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def precision(errors):
    e = np.asarray(errors, float)
    return {'mean_absolute_deviation_pp': float(np.abs(e).mean()),
            'rmse_pp': float(np.sqrt(np.mean(e**2))),
            'signed_bias_pp': float(e.mean()),
            'signed_deviation_central_95_pp': np.quantile(e, [.025, .975]).tolist(),
            'absolute_deviation_p50_pp': float(np.median(np.abs(e))),
            'absolute_deviation_p90_pp': float(np.quantile(np.abs(e), .9)),
            'absolute_deviation_p95_pp': float(np.quantile(np.abs(e), .95))}


def median(records, weight_key='weight'):
    usable = [r for r in records if r['mean'] is not None and np.isfinite(r['mean'])]
    return quantile([r['mean'] for r in usable], [r[weight_key] for r in usable], .5)


def run(out, draws=1000, seed=20261021):
    began = perf_counter()
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs') or draws < 100:
        raise ValueError('Fresh ignored output and >=100 sampling draws required')
    sources = {str(p.relative_to(ROOT)): sha(p) for p in (TRUTH, CASES, CURRENT)}
    saved = json.loads(CASES.read_text())
    current = [r for r in json.loads(CURRENT.read_text()) if r['repeat'] == 1]
    # Existing exact-bin scores are reused; only previously uncached vectors fit.
    cache = {}
    for r in saved:
        cache[tuple(r['real']['q9_bins'])] = r['real']['q9_mean']
    fields = ['date', 'userid', 'weight', '_AGE_CAT', '_HH_INC_CAT',
              *[f'Q9_bin{i}' for i in range(1, 11)]]
    frame = pd.read_parquet(TRUTH, columns=fields, filters=[('date', 'in', list(MONTHS))])
    inc = {'Under 50k': 'under_50k', '50k to 100k': '50k_to_100k', 'Over 100k': 'over_100k'}
    monthly, trajectories, counts = [], {n: [] for n in (48, 96, 192)}, Counter()
    for month in MONTHS:
        path = REFERENCE/str(month)/'eligible_ids_private.json'
        sources[str(path.relative_to(ROOT))] = sha(path)
        eligible = set(json.loads(path.read_text()))
        rows, full = [], []
        for r in frame[frame.date.eq(month)].to_dict('records'):
            bins = tuple(float(r[f'Q9_bin{i}']) for i in range(1, 11))
            if bins not in cache:
                cache[bins] = score(bins)['mean']; counts['uncached_bin_vectors_fit'] += 1
            else:
                counts['cached_row_hits'] += 1
            mean, weight = cache[bins], float(r['weight'])
            if not np.isfinite(weight) or weight <= 0:
                continue
            record = {'agent_id': f"sce_u{int(r['userid'])}", 'mean': mean, 'weight': weight,
                      'attributes': {'age_group': r['_AGE_CAT'] or 'unknown',
                                     'household_income_band': inc.get(r['_HH_INC_CAT'], 'unknown')}}
            full.append(record)
            if int(r['userid']) in eligible:
                rows.append(record)
        if len(rows) != len(eligible):
            raise ValueError('Eligible frame mismatch')
        # Match archived allocation counts before using the reconstructed frame.
        archived = json.loads((REFERENCE/str(month)/'sampling_private.json').read_text())
        _, _, check = sample_strata(rows, month, 192, 20261017)
        if check['stratum_N'] != archived['stratum_N'] or check['stratum_n'] != archived['stratum_n']:
            raise ValueError('Archived stratum allocation differs')
        center, full_center = median(rows), median(full)
        old_center = json.loads((ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1/summary.json').read_text())['wave_centers'][str(month)]
        if abs(center-old_center['eligible_returners']['center_pp']) > 1e-8 or abs(full_center-old_center['full_wave']['center_pp']) > 1e-8:
            raise ValueError('Frozen-score wave center differs from existing evaluation')
        errors = {n: [] for n in trajectories}
        by_id = {r['agent_id']: r for r in rows}
        for draw in range(draws):
            selected, pi1, _ = sample_strata(rows, month, 192, seed+2*draw)
            parent = [by_id[aid] for aid in sorted(selected)]
            for n in trajectories:
                if n == 192:
                    chosen, pi2 = selected, {aid: 1. for aid in selected}
                else:
                    chosen, pi2, _ = sample_strata(parent, month, n, seed+2*draw+1)
                sample = [{**by_id[aid], 'design_weight': by_id[aid]['weight']/pi1[aid]/pi2[aid]}
                          for aid in sorted(chosen)]
                errors[n].append(median(sample, 'design_weight')-center)
        for n in trajectories:
            trajectories[n].append(np.asarray(errors[n]))
        actual = [r for r in current if r['month'] == month and r['real']['q9_mean'] is not None]
        w = np.asarray([r['design_survey_weight'] for r in actual])
        actual_center = quantile([r['real']['q9_mean'] for r in actual], w, .5)
        monthly.append({'month': month, 'eligible_frame_n': len(rows),
                        'eligible_scorable_n': sum(r['mean'] is not None for r in rows),
                        'eligible_center_pp': center, 'full_wave_center_pp': full_center,
                        'eligible_minus_full_wave_pp': center-full_center,
                        'current_scorable_n': len(actual), 'current_weight_ess': float(w.sum()**2/(w@w)),
                        'current_center_pp': actual_center, 'current_minus_eligible_pp': actual_center-center,
                        'sampling': {str(n): precision(errors[n]) for n in trajectories}})
        print('Sampling complete:', month, 'eligible', len(rows), flush=True)
    pooled = {str(n): precision(np.concatenate(errors)) for n, errors in trajectories.items()}
    # Draws are independent across month by month-specific SeedSequence. Not a
    # cluster interval for repeated respondents or a confidence interval for MAE.
    six_month = {str(n): {'mean_of_month_absolute_sampling_deviations_pp':
                         precision(np.mean(np.abs(np.stack(errors)), axis=0))}
                 for n, errors in trajectories.items()}
    result = {'status': 'finite_frame_sampling_diagnostic_complete',
              'completed_at_utc': datetime.now(timezone.utc).isoformat(),
              'new_api_calls': 0, 'new_simulation_answers': 0,
              'draws_per_month': draws, 'seed': seed, 'months': list(MONTHS),
              'design': 'eligible frame -> age/income stratified192 -> stratified48/96; survey_weight/(pi1*pi2); missing current Q9 excluded after selection, never redraw',
              'target': 'weighted median of frozen-fitted Q9 individual means within fixed eligible-returner frame',
              'monthly': monthly, 'pooled_equal_month': pooled, 'six_month_average_sampling_deviation': six_month,
              'fitting': dict(counts), 'source_sha256': sources,
              'implementation_sha256': sha(Path(__file__)), 'seconds': perf_counter()-began,
              'limits': ['Finite observed SCE frames held fixed; not US population sampling uncertainty.',
                         'Does not measure model error on new people: no new simulated answers.',
                         'Same-person model/truth comparisons share sample-composition variation, which can cancel.',
                         'Percentile ranges of repeated sampling errors, not confidence intervals for model MAE.',
                         'Selected six development months do not measure out-of-period generalization.',
                         'Only one original sample roster and two LLM generations in the actual trial.']}
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    return result
