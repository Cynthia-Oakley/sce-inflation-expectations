"""Adopted random 3/8/20 article quotas on arbitrary full monthly frames."""
import math

from .evaluation.heterogeneous_news import stable_uniform


def random_quantities(agent_ids, seed=20261022):
    """Largest-remainder 48:28:20 allocation; no P attributes or outcomes.

    Compute once on the full frame, then subset Core. This preserves a person's
    quantity when only the Core size changes. For multiples of 96, assignment
    equals the earlier uniform-six-class allocator on the SAME identity frame.
    """
    ids = list(map(str, agent_ids)); n = len(ids)
    if n < 1 or len(set(ids)) != n:
        raise ValueError('Unique nonempty full monthly identity frame required')
    base = {3: n*48/96, 8: n*28/96, 20: n*20/96}
    counts = {level: math.floor(q) for level,q in base.items()}
    for level in sorted(base, key=lambda k: (-(base[k]-counts[k]), k))[:n-sum(counts.values())]:
        counts[level] += 1
    ordered = sorted((min(int(stable_uniform(seed, aid, 'class')*6), 5),
                      stable_uniform(seed, aid, 'tie'), aid) for aid in ids)
    levels = [level for level in (3,8,20) for _ in range(counts[level])]
    return {aid: level for (_,_,aid),level in zip(ordered, levels)}
