"""Past-only initialization preflight, not an LLM accuracy evaluation."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .metrics import distribution_summary, quantile, wasserstein1
from ..experiments.state_continuity import ROOT, month_index
from ..experiments.state_continuity_inputs import (
    FRAME, HISTORY_COLUMNS, BINS, anonymous_id, dump, finite_point, sha,
)
from ..population.entry_initialization import EntryConfig, belief_preview, build_options, calibrate, draw, score_past
from ..prior_belief_preparation import valid_bins
from ..scoring.sce_q9_frozen import provenance

DELIVERY = ROOT / 'outputs/sce_fullperiod_data_20261021_v1'
PILOT = ROOT / 'outputs/sce_state_continuity_history_20261022_v1'


def previous_month(month):
    y, zero_m = divmod(month_index(month) - 1, 12)
    return y * 100 + zero_m + 1


def frame_diagnostics():
    """82 waves' support only: current answer columns are never loaded as recipients."""
    current = pd.read_parquet(FRAME, columns=['date', 'tenure', '_AGE_CAT', '_EDU_CAT', '_HH_INC_CAT'])
    result = []
    for month in sorted(current.date.unique()):
        if month < 201901:
            continue
        entrants = current.loc[current.date.eq(month) & current.tenure.eq(1)]
        # Physical past filter; no target answers read by this support calculation.
        pool = pd.read_parquet(FRAME, columns=HISTORY_COLUMNS + ['weight'],
                               filters=[('date', '==', previous_month(month))])
        legal = pool.apply(lambda r: finite_point(r.Q8v2part2) is not None
                           and valid_bins([r[k] for k in BINS]), axis=1)
        pool = pool.loc[pool.tenure.eq(1) & legal & np.isfinite(pool.weight) & pool.weight.gt(0)]
        counts = {}
        for name, keys in [('age_education_income', ['_AGE_CAT', '_EDU_CAT', '_HH_INC_CAT']),
                           ('age_income', ['_AGE_CAT', '_HH_INC_CAT']), ('age', ['_AGE_CAT'])]:
            sizes = pool.groupby(keys, dropna=False).size().rename('candidate_n')
            n = entrants.merge(sizes, on=keys, how='left').candidate_n.fillna(0)
            counts[name] = {'no_candidate': int(n.eq(0).sum()), 'fewer_than_five': int(n.lt(5).sum())}
        result.append({'month': int(month), 'entrant_n': len(entrants),
                       'past_joint_legal_entrant_n': len(pool), 'matching_support': counts})
    return result


def boot_bands(previous, n, *, seed, draws=250):
    """Finite-wave, survey-weighted case bootstrap; NOT a national design CI.

    Uniform row resampling, then original survey weights in the estimator.
    Do not sample PPS and then apply the same weight twice.
    """
    rng = np.random.default_rng(seed)
    result, information = {}, {}
    for key, col in [('q8', '_point'), ('q9', '_center')]:
        use = previous.loc[previous[col].notna() & np.isfinite(previous.weight) & previous.weight.gt(0)]
        x, w = use[col].to_numpy(float), use.weight.to_numpy(float)
        if not len(x):
            raise ValueError('Previous reference wave lacks valid values')
        medians = []
        for _ in range(draws):
            j = rng.integers(0, len(x), n)
            medians.append(quantile(x[j], w[j], .5))
        center = quantile(x, w, .5)
        lower, upper = np.quantile(medians, [.025, .975])
        result[key] = [float(min(lower, center)), float(max(upper, center))]
        information[key] = {'past_reference': distribution_summary(x, w),
                            'median_band_pp': result[key], 'resampling_draws': draws,
                            'case_sample_size': n,
                            'interpretation': 'past finite-wave sampling tolerance, not a population confidence interval'}
    return result, information


def mixture_summary(options, previous, *, calibrated):
    output = {}
    for key, col in [('q8', '_point'), ('q9', '_center')]:
        xs, ws = [], []
        for o in options:
            if o['weight'] is None:
                continue
            xs.extend(o[key]); ws.extend(o['weight'] * (o['p'] if calibrated else o['p0']))
        valid = previous[col].notna() & np.isfinite(previous.weight) & previous.weight.gt(0)
        stats = distribution_summary(xs, ws)
        stats['mixture_support_points'] = stats.pop('n_valid')
        stats.pop('ess')  # Expanded donor edges are not independent people.
        recipients = [o for o in options if o['weight'] is not None and np.isfinite(o[key]).all()]
        rw = np.array([o['weight'] for o in recipients])
        stats.update(recipient_n=len(recipients), recipient_weight_ess=float(rw.sum() ** 2 / (rw @ rw)))
        output[key] = dict(stats, w1_to_past_reference_pp=wasserstein1(
            xs, ws, previous.loc[valid, col], previous.loc[valid, 'weight']))
    return output


def assignment_sensitivity(options, month, bands, seed, draws=100):
    summaries = {}
    for calibrated in (False, True):
        medians = {'q8': [], 'q9': []}
        for k in range(draws):
            rows = draw(options, month, seed + k, calibrated=calibrated)
            for key in medians:
                valid = [r for r in rows if r[key] is not None and r['weight'] is not None]
                medians[key].append(quantile([r[key] for r in valid], [r['weight'] for r in valid], .5))
        summaries['soft_calibrated' if calibrated else 'recent_only'] = {
            key: {'assignment_seed_draws': draws, 'median_across_assignments_pp': float(np.median(values)),
                  'central_95_assignment_range_pp': np.quantile(values, [.025, .975]).tolist(),
                  'share_in_past_band': float(np.mean((np.array(values) >= bands[key][0])
                                                       & (np.array(values) <= bands[key][1])))}
            for key, values in medians.items()}
    return summaries


def prepare(out, *, months=('202505', '202506', '202507'), sizes=(96, 512), seed=20261022):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh ignored output directory required')
    config = EntryConfig(seed=seed)
    sources = {str(FRAME.relative_to(ROOT)): sha(FRAME)}
    for source in [Path(__file__), ROOT / 'studies/sce_inflation_expectations/population/entry_initialization.py',
                   ROOT / 'scripts/prepare_sce_entry_initialization.py']:
        sources[str(source.relative_to(ROOT))] = sha(source)
    # UID-only file access is used to map existing anonymous P to its past records.
    uids = pd.read_parquet(FRAME, columns=['userid']).userid.unique()
    units, missing_weight_rows = [], []
    out.mkdir(parents=True)
    for month in months:
        print(f'Preparing past-only entry options for {month}', flush=True)
        folder = DELIVERY / month
        files = [folder / name for name in ('population.json', 'sampling_private.json', 'population_state_private.json')]
        pop, sampling, state = [json.loads(p.read_text()) for p in files]
        sources.update({str(p.relative_to(ROOT)): sha(p) for p in files})
        mapping = {anonymous_id(u, state['anon_salt']): int(u) for u in uids}
        sidecar = {r['agent_id']: r for r in sampling['persons']}
        entries = {r['agent_id']: r for r in state['persons']}
        people = sorted(pop['personas'], key=lambda p: (sidecar[p['agent_id']]['stable_priority'], p['agent_id']))
        # Current P and evaluation weights only; no target answer columns.
        weights = pd.read_parquet(FRAME, columns=['userid', 'weight'], filters=[('date', '==', int(month))]).set_index('userid').weight
        uid_set = [mapping[p['agent_id']] for p in people[:max(sizes)]]
        past = pd.read_parquet(FRAME, columns=HISTORY_COLUMNS + ['weight'], filters=[('date', '<', int(month))])
        ages = month_index(month) - past.date.map(month_index)
        # Score all recent rows, plus only the latest valid older own rows needed.
        recent = past.loc[ages.le(3)]
        own = past.loc[past.userid.isin(uid_set)]
        older_indexes = set()
        for usable in [own.Q8v2part2.map(lambda x: finite_point(x) is not None),
                       own.apply(lambda r: valid_bins([r[k] for k in BINS]), axis=1)]:
            older_indexes.update(own.loc[usable].sort_values('date').groupby('userid').tail(1).index)
        past = score_past(past.loc[past.index.isin(set(recent.index) | older_indexes)], month)
        previous = past.loc[past.date.eq(previous_month(month))]
        for n in sizes:
            if n < 1 or n > len(people):
                raise ValueError('Probe size exceeds the delivered frame')
            selected = people[:n]
            recipients = []
            for p in selected:
                aid = p['agent_id']; uid = mapping[aid]; w = weights.loc[uid]
                valid_weight = np.isfinite(w) and w > 0
                if not valid_weight:
                    missing_weight_rows.append({'month': month, 'agent_id': aid})
                status = entries[aid]['survey_entry_status']
                donor_type = 'entrant' if status == 'entrant' else 'returner' if status in {'returning', 'gap_return'} else 'unknown'
                recipients.append({'agent_id': aid, 'userid': uid,
                                   'weight': float(w) * len(people) / n if valid_weight else None,
                                   'profile': p['attributes'], 'donor_type': donor_type})
            options = build_options(past, recipients, month, config=config)
            bands, references = boot_bands(previous, n, seed=seed + int(month))
            before = mixture_summary(options, previous, calibrated=False)
            calibration = calibrate([o for o in options if o['weight'] is not None], bands,
                                    max_ratio=config.max_probability_ratio)
            after = mixture_summary(options, previous, calibrated=True)
            fixed = draw(options, month, seed)
            dump(out / f'{month}_n{n}_initial_states_private.json', fixed)
            preview = next((row for row in fixed if len(row['synthetic_fields']) == 2), None)
            if preview:
                (out / f'{month}_n{n}_preview.txt').write_text(belief_preview(preview, month))
            synthetic = [o for o in options if o['synthetic_fields']]
            reuse = Counter(r['donor_userid_private'] for r in fixed if r['synthetic_fields'])
            old_path = PILOT / f'{month}_resolved_private.json'
            old = json.loads(old_path.read_text()) if old_path.exists() and n == 96 else None
            old_ages = [month_index(month) - month_index(f['source_period'])
                        for aid, person in (old or {}).items() for f in person['fields'].values()
                        if f['source_kind'] == 'synthetic_donor']
            if old is not None:
                sources[str(old_path.relative_to(ROOT))] = sha(old_path)
            unit = {'month': month, 'probe_n': n, 'survey_entrants': sum(r['donor_type'] == 'entrant' for r in recipients),
                    'raw_weight_valid_n': sum(o['weight'] is not None for o in options),
                    'raw_weight_missing_n': sum(o['weight'] is None for o in options),
                    'synthetic_people': len(synthetic),
                    'synthetic_q8_n': sum('q8' in o['synthetic_fields'] for o in options),
                    'synthetic_q9_n': sum('q9' in o['synthetic_fields'] for o in options),
                    'distinct_donors_in_assignment': len(reuse),
                    'max_donor_reuse_in_assignment': max(reuse.values(), default=0),
                    'retained_older_memory_n': sum(bool(o['older_own_memory']) for o in options),
                    'matching_levels': dict(Counter('+'.join(o['matching']['matched_columns']) or 'global' for o in synthetic)),
                    'window_counts': dict(Counter(str(o['matching']['window_months']) for o in synthetic)),
                    'min_candidate_n': min((o['matching']['candidate_n'] for o in synthetic), default=None),
                    'min_candidate_ess': min((o['matching']['candidate_ess'] for o in synthetic), default=None),
                    'max_new_donor_age_months': max((month_index(month) - month_index(r['donor_period']) for r in fixed if r['donor_period']), default=None),
                    'old_synthetic_field_age_months': {'n_fields': len(old_ages), 'min': min(old_ages) if old_ages else None,
                                                      'median': float(np.median(old_ages)) if old_ages else None,
                                                      'max': max(old_ages) if old_ages else None},
                    'references': references, 'recent_mixture': before, 'calibrated_mixture': after,
                    'calibration': calibration,
                    'assignment_sensitivity': assignment_sensitivity(options, month, bands, seed)}
            # Verify untouched real fields in the delivered illustrative assignment.
            for o, row in zip(options, fixed):
                for key, own_field in o['fixed'].items():
                    if key == 'q8' and row['q8'] != own_field['value']:
                        raise ValueError('A real Q8 field was changed')
                    if key == 'q9' and row['q9_bins'] != own_field['q9_bins']:
                        raise ValueError('A real Q9 field was changed')
            units.append(unit)
            print(f'{month} n={n}: {len(synthetic)} synthetic; {calibration["status"]}', flush=True)
    support = frame_diagnostics()
    summary = {'schema_version': 1, 'completed_at': datetime.now(timezone.utc).isoformat(),
               'new_api_calls': 0, 'new_model_answers': 0,
               'status': 'offline_A_initialization_preflight_not_final_run_freeze',
               'config': config.dictionary(), 'source_sha256': sources, 'scorer': provenance(),
               'missing_raw_weight_person_months': len({(r['month'], r['agent_id']) for r in missing_weight_rows}),
               'units': units, 'historical_support': support,
               'cautions': ['No current inflation outcomes loaded for recipients or calibration.',
                            '512 is a stable-priority SRS support probe, not the final six-cell allocation.',
                            'Expected mixture calibration does not guarantee every finite assignment is in band.',
                            'Bootstrap bands measure conditional past-wave sampling variation, not national design uncertainty.',
                            'Missing raw-weight people are initialized and retained, but omitted from weighted calibration/statistics; no default weight one.',
                            'Recent raw microdata are A-only until release eligibility is established for B.',
                            'Population projection and strict-B lagged-micro updating remain separate tasks.',
                            'This tests initialization fidelity, not improvement in simulated answers.']}
    dump(out / 'summary.json', summary)
    return summary
