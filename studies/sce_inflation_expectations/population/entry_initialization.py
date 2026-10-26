"""Recent, joint hot-deck beliefs; optional soft calibration of donor probabilities.

No API or current outcomes. Existing frozen initializers are unchanged. This is
an A-line input adapter: a past observation date alone proves no B-line release
eligibility. Real answers and analysis weights are never modified.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import softmax

from ..experiments.state_continuity import month_index
from ..experiments.state_continuity_inputs import BINS, density_center, finite_point
from ..prior_belief_preparation import valid_bins


@dataclass(frozen=True)
class EntryConfig:
    windows: tuple[int, ...] = (1, 3)
    min_candidates: int = 5
    min_donor_ess: float = 3.0
    max_own_age_months: int = 3
    max_probability_ratio: float = 4.0
    seed: int = 20261022

    def __post_init__(self):
        if (self.windows != (1, 3) or self.min_candidates < 1
                or self.min_donor_ess < 1 or self.max_own_age_months < 1
                or self.max_probability_ratio <= 1):
            raise ValueError('Invalid recent-donor configuration')

    def dictionary(self):
        return asdict(self)


def score_past(past, month):
    """Score only whitelisted, physically past rows with the frozen Q9 scorer."""
    if not past.date.lt(int(month)).all():
        raise ValueError('Current/future outcomes cannot enter initialization')
    past = past.copy()
    past['_point'] = past.Q8v2part2.map(finite_point)
    past['_bins_valid'] = past.apply(lambda r: valid_bins([r[k] for k in BINS]), axis=1)
    past['_center'] = [density_center(tuple(float(r[k]) for k in BINS))
                       if r['_bins_valid'] else None for r in past.to_dict('records')]
    past['_age_months'] = month_index(month) - past.date.map(month_index)
    return past


def donor_candidates(past, month, profile, *, donor_type='entrant', config=None):
    """Previous month before three months; within each, relax matching in order.

    Survey weights enter the *draw probability* once. A selected donor's survey
    weight is never copied onto the recipient's evaluation weight.
    """
    config = config or EntryConfig()
    if not past.date.lt(int(month)).all():
        raise ValueError('Current/future rows in donor pool')
    if donor_type not in {'entrant', 'returner', 'unknown'}:
        raise ValueError('Explicit entrant/returner/unknown pool required')
    pool = past.loc[past._point.notna() & past._bins_valid & past._center.notna()
                    & np.isfinite(past.weight) & past.weight.gt(0)]
    if donor_type == 'entrant':
        pool = pool.loc[pool.tenure.eq(1)]
    elif donor_type == 'returner':
        pool = pool.loc[pool.tenure.gt(1)]
    edu = {'high_school': 'High School', 'some_college': 'Some College', 'college': 'College'}
    inc = {'under_50k': 'Under 50k', '50k_to_100k': '50k to 100k', 'over_100k': 'Over 100k'}
    match = [('_AGE_CAT', profile.get('age_group')),
             ('_EDU_CAT', edu.get(profile.get('education_group'))),
             ('_HH_INC_CAT', inc.get(profile.get('household_income_band')))]
    for window in config.windows:
        recent = pool.loc[pool._age_months.between(1, window)]
        for indexes in ((0, 1, 2), (0, 2), (0,), ()):
            subset, columns = recent, []
            for i in indexes:
                column, value = match[i]
                if value not in (None, 'unknown'):
                    subset = subset.loc[subset[column].eq(value)]
                    columns.append(column)
            w = subset.weight.to_numpy(float)
            ess = float(w.sum() ** 2 / (w @ w)) if len(w) else 0.
            if len(subset) >= config.min_candidates and ess >= config.min_donor_ess:
                subset = subset.sort_values(['date', 'userid'])
                w = subset.weight.to_numpy(float)
                return subset, w / w.sum(), {
                    'window_months': window, 'matched_columns': columns,
                    'candidate_n': len(subset), 'candidate_ess': ess,
                    'donor_type': donor_type, 'max_age_months': int(subset._age_months.max()),
                }
    raise ValueError('No sufficiently supported donor within three months; explicit exception required')


def build_options(past, recipients, month, *, config=None):
    """Retain recent own fields independently; never pretend stale answers are lag one.

    Older own observations stay in the memory sidecar. A missing/really stale
    field receives a recent synthetic value, labeled as such. The joint pair is
    drawn together when both fields are synthetic.
    """
    config = config or EntryConfig()
    if not past.date.lt(int(month)).all():
        raise ValueError('Current/future outcomes cannot enter own history')
    options = []
    for person in recipients:
        uid = person['userid']
        own = past.loc[past.userid.eq(uid)].sort_values('date')
        fixed, older = {}, {}
        for key, usable, column in [('q8', own._point.notna(), '_point'),
                                    ('q9', own._bins_valid, '_center')]:
            eligible = own.loc[usable]
            if len(eligible):
                row = eligible.iloc[-1]
                info = {'source_period': int(row.date), 'age_months': int(row._age_months),
                        'value': float(row[column]) if pd.notna(row[column]) else None,
                        'q9_bins': [float(row[k]) for k in BINS] if key == 'q9' else None}
                if row._age_months <= config.max_own_age_months:
                    fixed[key] = info
                else:
                    older[key] = info
        needs = [k for k in ('q8', 'q9') if k not in fixed]
        if needs:
            subset, p, meta = donor_candidates(
                past.loc[past.userid.ne(uid)], month, person['profile'],
                donor_type=person['donor_type'], config=config)
            q8, q9 = subset._point.to_numpy(float), subset._center.to_numpy(float)
            bins = subset[BINS].to_numpy(float)
            ids, periods = subset.userid.to_numpy(int), subset.date.to_numpy(int)
        else:
            p = np.ones(1); q8 = np.zeros(1); q9 = np.zeros(1)
            bins = np.zeros((1, 10)); ids = np.full(1, uid); periods = np.zeros(1, int)
            meta = {'window_months': None, 'matched_columns': [], 'candidate_n': 0,
                    'candidate_ess': None, 'donor_type': None, 'max_age_months': None}
        if 'q8' in fixed:
            q8 = np.full(len(p), fixed['q8']['value'])
        if 'q9' in fixed:
            q9 = np.full(len(p), np.nan if fixed['q9']['value'] is None else fixed['q9']['value'])
            bins = np.tile(fixed['q9']['q9_bins'], (len(p), 1))
        options.append({'agent_id': person['agent_id'],
                        'weight': float(person['weight']) if person['weight'] is not None else None,
                        'q8': q8, 'q9': q9, 'bins': bins, 'donor_ids': ids,
                        'donor_periods': periods, 'p0': p, 'p': p.copy(),
                        'fixed': fixed, 'older_own_memory': older, 'synthetic_fields': needs,
                        'matching': meta, 'donor_type': person['donor_type']})
    return options


def calibrate(options, bands, *, max_ratio=4.):
    """Bounded four-parameter probability tilt; targets are PAST median bands.

    A median is in [L,U] when F(L-) <= .5 <= F(U). Real fields contribute fixed
    CDF mass. Minimize remaining squared violations, with a tiny KL tie-breaker.
    Each recipient still selects an actual donor; expected individual numeric
    values are never substituted for the joint stochastic draw.
    """
    if max_ratio <= 1 or set(bands) != {'q8', 'q9'}:
        raise ValueError('Both past median bands and a ratio cap >1 required')
    features, normalizers = [], np.zeros(4)
    for o in options:
        cols = []
        for measure in ('q8', 'q9'):
            lo, hi = bands[measure]
            if not np.isfinite([lo, hi]).all() or lo > hi:
                raise ValueError('Invalid past calibration band')
            x = o[measure]; valid = np.isfinite(x)
            if valid.any() and not valid.all():
                raise ValueError('Scorability must not vary across donor options')
            cols.extend([(x < lo).astype(float), (x <= hi).astype(float)])
            if valid.all():
                start = 0 if measure == 'q8' else 2
                normalizers[start:start+2] += o['weight']
        features.append(np.stack(cols, axis=1))
    if (normalizers <= 0).any():
        raise ValueError('No valid calibration support')
    weights = np.array([o['weight'] for o in options], float)
    if not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError('Positive recipient weights required')
    signs = np.array([1., -1., 1., -1.])

    def evaluate(theta):
        mass, kl, probabilities = np.zeros(4), 0., []
        for o, f in zip(options, features):
            p = softmax(np.log(o['p0']) + f @ theta)
            probabilities.append(p)
            mass += o['weight'] * (p @ f)
            kl += o['weight'] * float(p @ np.log(p / o['p0']))
        cdf = mass / normalizers
        violation = np.maximum(signs * (cdf - .5), 0)
        return float(violation @ violation + 1e-7 * kl / weights.sum()), cdf, probabilities

    before_loss, before, _ = evaluate(np.zeros(4))
    # Feature range across candidates <= sum(abs(theta)) <= log(max_ratio),
    # hence every normalized p/p0 stays between 1/max_ratio and max_ratio.
    bound = np.log(max_ratio) / 4
    result = minimize(lambda t: evaluate(t)[0], np.zeros(4), method='L-BFGS-B',
                      bounds=[(-bound, bound)] * 4,
                      options={'maxiter': 150, 'ftol': 1e-14, 'gtol': 1e-9})
    theta = result.x if result.fun <= before_loss else np.zeros(4)
    _, after, probabilities = evaluate(theta)
    low, high = 1., 1.
    for o, p in zip(options, probabilities):
        o['p'] = p
        ratio = p / o['p0']; low = min(low, float(ratio.min())); high = max(high, float(ratio.max()))
        if ratio.min() < 1 / max_ratio - 1e-9 or ratio.max() > max_ratio + 1e-9:
            raise ValueError('Probability ratio safeguard failed')
    before_v = np.maximum(signs * (before - .5), 0)
    after_v = np.maximum(signs * (after - .5), 0)
    return {'status': ('already_in_band' if before_v.max() <= 1e-6 else
                       'soft_constraint_met' if after_v.max() <= 1e-6 else 'soft_constraint_unmet'),
            'optimizer_success': bool(result.success), 'theta': theta.tolist(),
            'cdf_before': before.tolist(), 'cdf_after': after.tolist(),
            'max_cdf_violation_before': float(before_v.max()),
            'max_cdf_violation_after': float(after_v.max()),
            'min_probability_ratio': low, 'max_probability_ratio': high,
            'band_definition': 'F(L-) <= 0.5 <= F(U), separately Q8 and frozen Q9 center',
            'no_current_targets': True}


def draw(options, month, seed, *, calibrated=True):
    """Stable per-person stream; fixed donor draw preserves joint synthetic Q8/Q9."""
    rows = []
    for o in options:
        h = hashlib.sha256(f'{seed}|{month}|{o["agent_id"]}|recent-entry'.encode()).digest()
        rng = np.random.default_rng(int.from_bytes(h[:8], 'little'))
        j = int(rng.choice(len(o['p']), p=o['p'] if calibrated else o['p0']))
        rows.append({'agent_id': o['agent_id'], 'weight': o['weight'],
                     'q8': float(o['q8'][j]),
                     'q9': float(o['q9'][j]) if np.isfinite(o['q9'][j]) else None,
                     'q9_bins': o['bins'][j].tolist(),
                     'synthetic_fields': o['synthetic_fields'], 'own_observed': o['fixed'],
                     'older_own_memory': o['older_own_memory'],
                     'donor_userid_private': int(o['donor_ids'][j]) if o['synthetic_fields'] else None,
                     'donor_period': int(o['donor_periods'][j]) if o['synthetic_fields'] else None,
                     'matching': o['matching']})
    return rows


def belief_preview(row, month):
    """Short input wording; no donor identity, weight, invented history or targets."""
    label = lambda p: f'{int(p)//100}-{int(p)%100:02}'
    lines = ['Earlier belief state (expectations, not measured inflation):']
    for key in ('q8', 'q9'):
        synthetic = key in row['synthetic_fields']
        period = row['donor_period'] if synthetic else row['own_observed'][key]['source_period']
        if month_index(period) >= month_index(month):
            raise ValueError('Belief preview must be strictly past')
        origin = ('assigned synthetic starting belief based on similar respondents; not your actual survey answer'
                  if synthetic else 'your own earlier survey answer')
        lines.append(f'- {key.upper()}, source {label(period)}: {origin}.')
        lines.append(str(row['q8']) if key == 'q8' else str(dict(zip([f'bin{i}' for i in range(1, 11)], row['q9_bins']))))
    lines.append('Use this earlier view as a starting point. Consider retaining or revising it in light of the information available today.')
    return '\n'.join(lines) + '\n'
