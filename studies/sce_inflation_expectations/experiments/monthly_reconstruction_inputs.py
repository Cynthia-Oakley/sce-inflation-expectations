"""Independent monthly A-line inputs over the delivered full respondent frames.

Six-cell SRS, recent hot-deck beliefs and local weights. No current answers,
evaluation files, API client or recursive model histories enter this adapter.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import math

import numpy as np
import pandas as pd

from .state_continuity import ROOT, month_index
from .state_continuity_inputs import FRAME, HISTORY_COLUMNS, BINS, anonymous_id, density_center, finite_point
from .frozen_batch import dump, read_json, sha
from ..population.entry_initialization import EntryConfig, build_options, calibrate, draw
from ..population_stratification import cell_key, allocate_core, EDUCATION, WORK
from ..prior_belief_preparation import valid_bins
from ..scoring.sce_q9_frozen import provenance
from ..evaluation.metrics import quantile, distribution_summary
from ..evaluation.entry_initialization import previous_month, mixture_summary

DELIVERY = ROOT / 'outputs/sce_fullperiod_data_20261021_v1'
GRID = ROOT / 'outputs/sce_population_grid_20261022_v1/core_allocation_proposal.json'
CONTROLS = ROOT / 'outputs/sce_behavior_mechanism_audit_20261014_v3/reference_with_controls_private.parquet'
ARM = 'monthly_reconstruction'


def inventory(delivery=DELIVERY):
    """Coverage readiness is file-level, never inferred from old status names."""
    delivery = Path(delivery)
    coverage = read_json(delivery / 'coverage.json')
    records = []
    for row in coverage['months']:
        month = row['target_month'].replace('-', '')
        files = {name: (delivery / month / name).is_file() for name in
                 ('population.json', 'population_state_private.json', 'sampling_private.json',
                  'belief_state_private.json', 'news_label_index.json', 'environment.json')}
        auxiliary = ROOT / 'outputs/sce_state_continuity_environments_20261022_v1' / month / 'environment.json'
        records.append({'month': month, 'micro_truth_available': row['micro_truth_available'],
                        'files': files, 'auxiliary_environment_available': auxiliary.is_file(),
                        'population_adapter_available': all(files[k] for k in
                          ('population.json', 'population_state_private.json', 'sampling_private.json')),
                        'scope': 'historical_A' if row['micro_truth_available'] else 'separate_synthetic_or_B_rules_required'})
    return records


def choose_core(population, sampling, entry, raw_weights, allocation):
    """Apply registered quotas; stable random priority gives within-cell SRS pi.

    Missing raw survey weights stay missing. Delivered persona.weight and the
    demonstration inclusion_probability_core_k are never treated as authoritative.
    """
    people = {p['agent_id']: p for p in population['personas']}
    priorities = {p['agent_id']: p['stable_priority'] for p in sampling['persons']}
    entries = {p['agent_id']: p for p in entry['persons']}
    if len(people) != len(population['personas']) or not (set(people) == set(priorities) == set(entries) == set(raw_weights)):
        raise ValueError('Unique complete P/sampling/entry/raw-weight identity sets required')
    grouped = defaultdict(list)
    for aid, person in people.items():
        grouped[cell_key(person['attributes'])].append(aid)
    if set(grouped) - set(allocation):
        raise ValueError('Unregistered population grid cells')
    chosen, stats = [], {}
    for cell, quota in allocation.items():
        ids = sorted(grouped[cell], key=lambda aid: (priorities[aid], aid))
        n, N = quota['allocated_n'], quota['frame_n']
        if N != len(ids) or type(n) is not int or not 0 <= n <= N:
            raise ValueError('Registered grid frame/selection count mismatch: ' + cell)
        pi = n / N if N else None
        for aid in ids[:n]:
            person = deepcopy(people[aid]); person['weight'] = 1.
            w = raw_weights[aid]
            ok = type(w) in (int, float) and math.isfinite(w) and w > 0
            chosen.append({'persona': person, 'stratum': cell, 'inclusion_probability': pi,
                           'raw_survey_weight': float(w) if ok else None,
                           'analysis_weight': float(w) / pi if ok else None,
                           'weight_valid': ok, 'survey_entry_status': entries[aid]['survey_entry_status']})
        stats[cell] = {'frame_n': N, 'selected_n': n, 'actual_inclusion_probability': pi}
    return sorted(chosen, key=lambda x: x['persona']['agent_id']), stats


class PastScoreCache:
    """Exact-vector memoization of frozen scores, never forecasts or target statistics."""
    def __init__(self):
        self.values = {}; self.new_fits = 0; self.hits = 0

    def seed(self, folder):
        files = []
        for path in sorted(Path(folder).glob('*_initial_states_private.json')):
            for r in read_json(path):
                bins = tuple(r['q9_bins']); value = r['q9']
                if not valid_bins(bins):
                    raise ValueError('Invalid vector in prior-input score cache')
                if bins in self.values and self.values[bins] != value:
                    raise ValueError('Conflicting deterministic Q9 score cache')
                self.values[bins] = value
            files.append(path)
        return files

    def score(self, past, month):
        if not past.date.lt(int(month)).all():
            raise ValueError('Current/future rows cannot enter scoring or initialization')
        past = past.copy(); past['_point'] = past.Q8v2part2.map(finite_point)
        past['_bins_valid'] = past.apply(lambda r: valid_bins([r[k] for k in BINS]), axis=1)
        centers = []
        for r in past.to_dict('records'):
            if not r['_bins_valid']:
                centers.append(None); continue
            bins = tuple(float(r[k]) for k in BINS)
            if bins not in self.values:
                self.values[bins] = density_center(bins); self.new_fits += 1
            else:
                self.hits += 1
            centers.append(self.values[bins])
        past['_center'] = centers
        past['_age_months'] = month_index(month) - past.date.map(month_index)
        return past


def stratified_bands(previous, allocation, *, seed, draws=250):
    """Past finite-frame SRSWOR using the same registered six-cell rule.

    Draw from the FULL prior wave, then apply field validity and w/pi. Do not
    preselect only scorable people, resample PPS or invent missing weights.
    """
    if previous.duplicated(['date', 'userid']).any():
        raise ValueError('Unique previous-wave identities required')
    previous = previous.copy()
    previous['_cell'] = previous.apply(lambda r: cell_key({'_EDU_CAT': r['_EDU_CAT'], 'employment': r['employment']}), axis=1)
    cell_rows, cell_pi = {}, {}
    for cell, v in allocation.items():
        part = previous.loc[previous._cell.eq(cell)]
        if len(part) != v['frame_n'] or not 0 <= v['allocated_n'] <= len(part):
            raise ValueError('Prior sampling design/frame mismatch: ' + cell)
        if len(part):
            cell_rows[cell] = part; cell_pi[cell] = v['allocated_n'] / len(part)
    rng = np.random.default_rng(seed)
    values = {'q8': [], 'q9': []}
    for _ in range(draws):
        sampled = []
        for cell, part in cell_rows.items():
            n = allocation[cell]['allocated_n']
            if not n:
                continue
            draw_rows = part.iloc[rng.choice(len(part), n, replace=False)].copy()
            draw_rows['_design_weight'] = draw_rows.weight / cell_pi[cell]
            sampled.append(draw_rows)
        sample = pd.concat(sampled, ignore_index=True)
        for key, column in [('q8', '_point'), ('q9', '_center')]:
            valid = sample[column].notna() & np.isfinite(sample._design_weight) & sample._design_weight.gt(0)
            values[key].append(quantile(sample.loc[valid, column], sample.loc[valid, '_design_weight'], .5))
    bands, reference = {}, {}
    for key, col in [('q8', '_point'), ('q9', '_center')]:
        valid = previous[col].notna() & np.isfinite(previous.weight) & previous.weight.gt(0)
        stats = distribution_summary(previous.loc[valid, col], previous.loc[valid, 'weight'])
        low, high = np.quantile(values[key], [.025, .975]); center = stats['median_pp']
        bands[key] = [float(min(low, center)), float(max(high, center))]
        reference[key] = {'past_reference': stats, 'median_band_pp': bands[key],
                          'sampling_draws': draws, 'sampling': 'within-cell SRS without replacement, w/pi',
                          'interpretation': 'past finite-frame design variability, not a national confidence interval'}
    return bands, reference


def prior_grid_allocation(previous, registered=None):
    """Same 512/24 rule for a prior wave outside the target-grid catalogue.

    In particular 2019-01 needs the 2018-12 prior frame. Construct that design
    from past P/weights only rather than shifting the study start or using a
    future grid. Normal in-catalogue months keep the registered allocation.
    """
    if registered is not None:
        return registered['allocation']
    cells = [f'{e}|{w}' for e in EDUCATION for w in WORK] + ['unknown']
    groups = {c: [] for c in cells}
    for r in previous.to_dict('records'):
        c = cell_key({'_EDU_CAT': r['_EDU_CAT'], 'employment': r['employment']})
        groups[c].append(r)
    counts = {c: len(rows) for c,rows in groups.items()}
    masses = {c: sum(float(r['weight']) for r in rows
                    if pd.notna(r['weight']) and np.isfinite(r['weight']) and r['weight'] > 0)
              for c,rows in groups.items()}
    allocation = allocate_core(counts, masses, 512, minimum=24)
    return {c: {'frame_n': counts[c], 'allocated_n': allocation[c]} for c in cells}


def resolve_draw(row, past, uid, month):
    """Bridge to the existing renderer, preserving real history and provenance."""
    own = past.loc[past.userid.eq(uid)].sort_values('date')
    fields = {}
    for key in ('q8', 'q9'):
        synthetic = key in row['synthetic_fields']
        period = row['donor_period'] if synthetic else row['own_observed'][key]['source_period']
        fields[key] = {'source_kind': 'synthetic_donor' if synthetic else 'own_observed',
                       'source_period': period, 'value': row['q8'] if key == 'q8' else row['q9_bins']}
        if month_index(period) >= month_index(month):
            raise ValueError('Resolved belief must strictly precede target')
    history = [{'source_period': int(r.date), 'center': float(r._center)}
               for _, r in own.loc[own._center.notna()].iterrows()]
    day = None
    if fields['q9']['source_kind'] == 'own_observed':
        source = own.loc[own.date.eq(fields['q9']['source_period'])].iloc[-1]
        if pd.notna(source.survey_date):
            day = pd.Timestamp(source.survey_date).date().isoformat()
    observed_day = day is not None
    if day is None:
        day = (pd.Timestamp(f'{int(month)//100}-{int(month)%100:02}-01') - pd.Timedelta(days=1)).date().isoformat()
    return {'fields': fields, 'own_history_centers': history,
            'older_own_memory': row['older_own_memory'],
            'comparison_reference_day': day,
            'comparison_day_source': 'own_observed_survey_day' if observed_day else 'initialization_reference_previous_month_end_not_actual_survey',
            'donor': {'source_period': row['donor_period'], 'matching': row['matching']},
            'synthetic_fields': row['synthetic_fields'],
            'observed_previous_q8': fields['q8']['source_kind'] == 'own_observed' and fields['q8']['source_period'] == previous_month(month),
            'observed_previous_q9': fields['q9']['source_kind'] == 'own_observed' and fields['q9']['source_period'] == previous_month(month)}


def prepare(out, *, months=('202505', '202506', '202507'), delivery=DELIVERY, grid=GRID):
    out, delivery, grid = Path(out).resolve(), Path(delivery).resolve(), Path(grid).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh ignored preparation directory required')
    proposal = read_json(grid)
    if proposal['target_core_n'] != 512 or proposal['minimum_floor'] != 24:
        raise ValueError('Registered 512/24 grid proposal required')
    by_month = {str(r['yyyymm']): r for r in proposal['months']}
    cache = PastScoreCache()
    seeded = cache.seed(ROOT / 'outputs/sce_entry_initialization_preflight_20261022_v2')
    sources = {str(p.relative_to(ROOT)): sha(p) for p in [FRAME, CONTROLS, grid, *seeded]}
    source_files = [Path(__file__), ROOT/'studies/sce_inflation_expectations/population/entry_initialization.py',
                    ROOT/'studies/sce_inflation_expectations/population_stratification.py']
    for path in source_files:
        sources[str(path.relative_to(ROOT))] = sha(path)
    ids = pd.read_parquet(FRAME, columns=['userid']).userid.unique()
    selected, nodes, summary, last_selected = {}, [], [], {}
    out.mkdir(parents=True)
    for month in months:
        print(f'{month}: preparing independent monthly grid and recent beliefs', flush=True)
        registered = by_month[month]
        if registered.get('framework') != 'real_micro_full_frame':
            raise ValueError('Synthetic/no-micro future periods need separate initialization rules')
        files = [delivery/month/name for name in ('population.json', 'sampling_private.json', 'population_state_private.json')]
        pop, sampling, entry = [read_json(p) for p in files]
        sources.update({str(p.relative_to(ROOT)): sha(p) for p in files})
        identity = {anonymous_id(u, entry['anon_salt']): int(u) for u in ids}
        weights = pd.read_parquet(FRAME, columns=['date', 'userid', 'weight'], filters=[('date', '==', int(month))]).set_index('userid').weight
        raw_weights = {p['agent_id']: float(weights.loc[identity[p['agent_id']]]) for p in pop['personas']}
        people, grid_stats = choose_core(pop, sampling, entry, raw_weights, registered['allocation'])
        if len(people) != 512:
            raise ValueError('Exact Core count required')
        selected[month] = people
        chosen_uids = {identity[r['persona']['agent_id']] for r in people}
        # Whitelisted past answers only; no evaluation target or derived target columns.
        past = pd.read_parquet(FRAME, columns=HISTORY_COLUMNS+['weight'], filters=[('date', '<', int(month))])
        recent = (month_index(month) - past.date.map(month_index)).le(3)
        past = cache.score(past.loc[recent | past.userid.isin(chosen_uids)], month)
        controls = pd.read_parquet(CONTROLS, columns=['date', 'userid', 'employment'], filters=[('date', '==', previous_month(month))])
        previous = past.loc[past.date.eq(previous_month(month))].merge(controls, on=['date', 'userid'], validate='one_to_one')
        recipients = []
        for item in people:
            aid = item['persona']['agent_id']; status = item['survey_entry_status']
            recipients.append({'agent_id': aid, 'userid': identity[aid], 'weight': item['analysis_weight'],
                'profile': item['persona']['attributes'],
                'donor_type': 'entrant' if status == 'entrant' else 'returner' if status in {'returning','gap_return'} else 'unknown'})
        options = build_options(past, recipients, month, config=EntryConfig())
        prior_registration = by_month.get(str(previous_month(month)))
        prior_allocation = prior_grid_allocation(previous, prior_registration)
        bands, references = stratified_bands(previous, prior_allocation, seed=20261022+int(month))
        before = mixture_summary(options, previous, calibrated=False)
        calibration = calibrate([o for o in options if o['weight'] is not None], bands)
        after = mixture_summary(options, previous, calibrated=True)
        draws = draw(options, month, 20261022)
        resolved, weight_sidecar, baselines = {}, {}, {}
        for item, row in zip(people, draws):
            aid = item['persona']['agent_id']; uid = identity[aid]
            state = resolve_draw(row, past, uid, month); resolved[aid] = state
            weight_sidecar[aid] = {k: item[k] for k in ('raw_survey_weight', 'analysis_weight', 'weight_valid', 'inclusion_probability', 'stratum')}
            baselines[aid] = {'initial_belief': state['fields'],
                'genuine_previous_q8': state['observed_previous_q8'], 'genuine_previous_q9': state['observed_previous_q9'],
                'survey_entry_status': item['survey_entry_status'], 'stratum': item['stratum'],
                'note': 'Retain assigned starting belief for all; true own-lag baseline only on genuine adjacent history.'}
            core = 'first_core_appearance' if aid not in last_selected else (
                'continued_core' if month_index(month)-month_index(last_selected[aid]) == 1 else 'core_gap_return')
            last_selected[aid] = month
            nodes.append({'month': month, 'agent_id': aid, 'arm': ARM, 'repeat': 1, 'dependency': None,
                          'logical_reuse_key': f'{month}|{aid}|r1|{ARM}', 'source_kind': 'independent_monthly_initialization',
                          'survey_entry_status': item['survey_entry_status'], 'core_entry_status': core})
        dump(out/f'{month}_resolved_private.json', resolved)
        dump(out/f'{month}_weights_private.json', weight_sidecar)
        dump(out/f'{month}_baselines_private.json', baselines)
        dump(out/f'{month}_draws_private.json', draws)
        stats = {'month': month, 'selected_n': len(people), 'grid': grid_stats,
                 'survey_entries': dict(Counter(p['survey_entry_status'] for p in people)),
                 'synthetic_q8': sum('q8' in r['synthetic_fields'] for r in draws),
                 'synthetic_q9': sum('q9' in r['synthetic_fields'] for r in draws),
                 'weight_missing_n': sum(not p['weight_valid'] for p in people),
                 'genuine_previous_q8_n': sum(r['observed_previous_q8'] for r in resolved.values()),
                 'genuine_previous_q9_n': sum(r['observed_previous_q9'] for r in resolved.values()),
                 'calibration': calibration, 'references': references,
                 'initial_mixture_before': before, 'initial_mixture_after': after}
        summary.append(stats)
        print(f'{month}: 512 selected; {stats["synthetic_q9"]} synthetic Q9; {calibration["status"]}', flush=True)
    dump(out/'selected_private.json', selected)
    dump(out/'state_dependencies_private.json', nodes)
    result = {'status': 'monthly_A_inputs_prepared_not_paid_authorized', 'mechanism': ARM,
              'created_at_utc': datetime.now(timezone.utc).isoformat(), 'new_api_calls': 0,
              'months': summary, 'n_per_month': 512, 'repeats': 1,
              'person_months': len(nodes), 'logical_positions': len(nodes),
              'potential_unique_calls_before_prompt_hash': len(nodes),
              'distinct_people': len(last_selected), 'recursive_dependencies': 0,
              'source_sha256': sources, 'scorer': provenance(),
              'score_cache': {'seed_vectors': len(cache.values)-cache.new_fits, 'new_fits': cache.new_fits, 'hits': cache.hits},
              'input_whitelists': {'current': ['delivered persona attributes', 'entry metadata', 'userid/date/weight locally'],
                                   'past': HISTORY_COLUMNS+['weight'], 'prior_grid': ['userid','date','employment']},
              'readiness_inventory': inventory(delivery),
              'limitations': ['A-line current P/weights; no claim of strict-B publication eligibility.',
                             'No current inflation outcomes or evaluation files read.',
                             'One primary generation; this is not an independent robustness experiment.',
                             'Calibration interval describes past finite-wave selection variability, not national inference.',
                             'Missing raw weights retained and flagged; weighted statistics require declared valid support.']}
    dump(out/'summary.json', result)
    dump(out/'score_cache_private.json', [{'q9_bins': list(k), 'center': v} for k,v in cache.values.items()])
    return result
