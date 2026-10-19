"""Distinguish repeat noise from persistent between-person output differences."""
from collections import defaultdict
import numpy as np
from .cognition import finite


def variance_components(values):
    x = np.asarray(values, float)
    if x.ndim != 2 or min(x.shape) < 2 or not np.isfinite(x).all():
        raise ValueError('Finite balanced person-by-repeat matrix required')
    means = x.mean(axis=1)
    within_sample = float(x.var(axis=1, ddof=1).mean())
    between_sample = float(means.var(ddof=1))
    return {'within_person_repeat_variance_pp2': within_sample,
        'between_person_repeat_mean_variance_pp2': between_sample,
        'noise_adjusted_between_variance_pp2': between_sample-within_sample/x.shape[1],
        'pooled_population_variance_pp2': float(x.var()),
        'between_means_population_variance_pp2': float(means.var()),
        'within_person_population_variance_pp2': float(x.var(axis=1).mean())}


def dispersion_readout(cases, protocol):
    people = defaultdict(list)
    for row in cases: people[row['month'], row['userid']].append(row)
    result = []
    for field, actual in [('mean', 'q9_mean'), ('point', 'q8_point')]:
        for month in protocol['months']:
            selected = [sorted(rows, key=lambda r:r['repeat']) for (m,u),rows in people.items() if m == month
                and len(rows) == len(protocol['generation_repeats'])
                and {r['repeat'] for r in rows} == set(protocol['generation_repeats'])
                and all(finite(r['real'][actual]) and all(finite(r['arms'][a][field]) for a in protocol['arms']) for r in rows)]
            if len(selected) < 2: continue
            result.append({'month': month, 'question': 'Q9_density_mean' if field == 'mean' else 'Q8_point',
                'common_people': len(selected), 'repeats': len(protocol['generation_repeats']),
                'real_between_person_variance_pp2': float(np.var([r[0]['real'][actual] for r in selected], ddof=1)),
                'arms': {a:variance_components([[r['arms'][a][field] for r in rows] for rows in selected]) for a in protocol['arms']}})
    return {'cells': result, 'weight': 'equal_people; separate from survey-weighted accuracy',
        'identity': 'pooled population variance = variance of person repeat means + average within-person population variance',
        'noise_adjustment': 'sample variance of person repeat means minus mean within-person sample variance / R; negative estimates retained',
        'limits': 'Four repeats estimate API variability, not real human repeat variability. Stable between differences are not automatically correct personal predictions.'}
