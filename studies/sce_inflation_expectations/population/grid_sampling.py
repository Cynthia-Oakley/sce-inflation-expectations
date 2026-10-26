"""Outcome-free fine-grid Core sampling and post-stratification contracts.

Opt-in adapter only: frozen six-cell inputs and the Normal expansion are not
modified. Callers must supply a positive-weight population frame, including an
explicit unknown cell where needed; absent/invalid weights are never filled.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import math

from ..population_stratification import allocate_core


def frame_cells(records):
    """Records contain id/cell/weight only; no response is used for allocation."""
    grouped = defaultdict(list)
    seen = set()
    for row in records:
        uid, cell, weight = row['id'], row['cell'], row['weight']
        if uid in seen:
            raise ValueError('Duplicate frame identity')
        if not isinstance(cell, str) or not cell:
            raise ValueError('Explicit nonempty cell required')
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight <= 0:
            raise ValueError('Positive finite population weights required; do not impute missing weights')
        seen.add(uid)
        grouped[cell].append({'id': uid, 'cell': cell, 'weight': float(weight)})
    if not grouped:
        raise ValueError('Empty population frame')
    return dict(grouped)


def plan_core(records, budget, *, minimum):
    """Capped floor plus population-mass allocation; not variance-optimal.

    Every occupied cell must get at least one draw for direct post-stratification.
    A frame cell smaller than its floor is enumerated, without repeated IDs.
    """
    if type(minimum) is not int or minimum < 1:
        raise ValueError('At least one Core per populated cell required')
    grouped = frame_cells(records)
    counts = {k: len(v) for k, v in grouped.items()}
    masses = {k: sum(r['weight'] for r in v) for k, v in grouped.items()}
    quotas = allocate_core(counts, masses, budget, minimum=minimum)
    total = sum(masses.values())
    return {'budget': budget, 'minimum': minimum, 'frame_n': sum(counts.values()),
            'population_weight_total': total,
            'cells': {k: {'frame_n': counts[k], 'population_mass': masses[k],
                          'population_fraction': masses[k]/total, 'selected_n': quotas[k],
                          'inclusion_probability': quotas[k]/counts[k]}
                      for k in sorted(counts)}}


def draw_core(records, plan, *, seed, month):
    """Seeded within-cell SRSWOR and explicit raw/design/calibrated weights.

    w/pi is the design weight. A separate within-cell calibration restores each
    known frame mass exactly, since unequal raw weights can leave finite-draw
    fluctuations. It is a ratio estimator, not a promise of unbiased medians.
    """
    grouped = frame_cells(records)
    if set(grouped) != set(plan['cells']):
        raise ValueError('Plan/frame cells differ')
    if (sum(len(v) for v in grouped.values()) != plan['frame_n']
            or sum(c['selected_n'] for c in plan['cells'].values()) != plan['budget']):
        raise ValueError('Plan total counts or budget differ')
    selected = []
    for cell, rows in grouped.items():
        c = plan['cells'][cell]
        if len(rows) != c['frame_n'] or not math.isclose(sum(r['weight'] for r in rows), c['population_mass']):
            raise ValueError('Plan/frame counts or population weights differ')
        n = c['selected_n']
        if type(n) is not int or not 1 <= n <= len(rows) or not math.isclose(c['inclusion_probability'], n/len(rows)):
            raise ValueError('Invalid quota or inclusion probability')
        ranked = sorted(rows, key=lambda r: (hashlib.sha256(
            f'{seed}:{month}:{r["id"]}'.encode()).digest(), str(r['id'])))
        pick = ranked[:n]
        pi = n/len(rows)
        design_sum = sum(r['weight']/pi for r in pick)
        calibration = c['population_mass']/design_sum
        for r in pick:
            selected.append({**r, 'inclusion_probability': pi,
                             'design_weight': r['weight']/pi,
                             'poststratified_weight': r['weight']/pi*calibration})
    return sorted(selected, key=lambda r: str(r['id']))
