"""Four-dimensional monthly sampling, independent of all survey outcomes."""
from collections import defaultdict
import math

import numpy as np

from .grid_sampling import plan_core, draw_core
from ..evaluation.metrics import quantile, distribution_summary

GRID_VERSION = 'education_numeracy_age_income_54_v1'
PROFILE_KEYS = ('education', 'numeracy', 'age', 'income')


def profile(attributes):
    edu = attributes.get('education_group', attributes.get('_EDU_CAT'))
    edu = {'High School': 'high_school', 'Some College': 'some_college', 'College': 'college'}.get(edu, edu)
    num = attributes.get('numeracy', attributes.get('_NUM_CAT'))
    num = {'high': 'High', 'low': 'Low'}.get(num, num)
    age = attributes.get('age_group', attributes.get('_AGE_CAT'))
    age = {'Under 40': 'under_40', '40 to 60': '40_60', 'Over 60': 'over_60'}.get(age, age)
    inc = attributes.get('household_income_band', attributes.get('_HH_INC_CAT'))
    inc = {'Under 50k': 'under_50k', '50k to 100k': '50k_100k', '50k_to_100k': '50k_100k', 'Over 100k': 'over_100k'}.get(inc, inc)
    valid = [('education', edu, {'high_school','some_college','college'}),
             ('numeracy', num, {'High','Low'}), ('age', age, {'under_40','40_60','over_60'}),
             ('income', inc, {'under_50k','50k_100k','over_100k'})]
    return {k: value if value in allowed else None for k, value, allowed in valid}


def cell(attributes):
    p = profile(attributes)
    return '|'.join(p[k] for k in PROFILE_KEYS) if all(p[k] is not None for k in PROFILE_KEYS) else 'unknown'


def positive_weight(w):
    return type(w) in (int, float) and math.isfinite(w) and w > 0


def records(population, weights):
    """Retain all source P; declare the positive-weight sampling support."""
    result = []; excluded = []
    for person in population['personas']:
        aid = person['agent_id']; w = weights[aid]
        if not positive_weight(w):
            excluded.append(aid); continue
        result.append({'id': aid, 'cell': cell(person['attributes']), 'weight': float(w)})
    return result, excluded


def prior_bands(previous, *, budget=512, minimum=8, seed, draws=250):
    """Same-design P-only allocation; apply field validity after selection.

    These are past-wave finite-design median tolerances, not national confidence
    intervals. Original unknown weights are excluded, never replaced by one.
    """
    if previous.duplicated(['date','userid']).any() or previous.date.nunique() != 1:
        raise ValueError('Exactly one unique-identity previous wave required')
    rows = previous.to_dict('records')
    good = [r for r in rows if positive_weight(r['weight'])]
    rr = [{'id':str(int(r['userid'])), 'cell':cell(r), 'weight':float(r['weight'])} for r in good]
    plan = plan_core(rr, budget, minimum=minimum)
    indexed = {str(int(r['userid'])):r for r in good}
    grouped = defaultdict(list)
    for r in rr: grouped[r['cell']].append(r['id'])
    rng = np.random.default_rng(seed); medians = {'q8':[], 'q9':[]}
    for _ in range(draws):
        picked = []
        for c in sorted(grouped):
            ids = grouped[c]; setting = plan['cells'][c]
            chosen = rng.choice(ids, setting['selected_n'], replace=False)
            design = [indexed[u]['weight']/setting['inclusion_probability'] for u in chosen]
            factor = setting['population_mass']/sum(design)
            picked.extend((indexed[u], w*factor) for u, w in zip(chosen, design))
        for name, key in [('q8','_point'),('q9','_center')]:
            available = [(r[key],w) for r,w in picked if r[key] is not None and np.isfinite(r[key])]
            if not available: raise ValueError('No valid past field after outcome-free sampling')
            medians[name].append(quantile([v for v,w in available], [w for v,w in available], .5))
    bands = {}; references = {}
    for name, key in [('q8','_point'),('q9','_center')]:
        available = [r for r in good if r[key] is not None and np.isfinite(r[key])]
        stats = distribution_summary([r[key] for r in available], [r['weight'] for r in available])
        low, high = np.quantile(medians[name], [.025,.975]); center = stats['median_pp']
        bands[name] = [float(min(low,center)),float(max(high,center))]
        references[name] = {'past_reference':stats, 'median_band_pp':bands[name], 'sampling_draws':draws,
                            'grid_version':GRID_VERSION, 'sampling':'within-cell SRSWOR with post-stratified weights',
                            'interpretation':'past finite-frame design variability; not national confidence interval'}
    return bands, references, plan
