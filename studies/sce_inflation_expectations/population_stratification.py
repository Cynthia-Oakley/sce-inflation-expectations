"""Six-cell draft: education x employment attachment, without outcome inputs."""
import math

EDUCATION = ('high_school', 'some_college', 'college')
WORK = ('attached', 'not_attached')
LABELS = {'High School': 'high_school', 'Some College': 'some_college', 'College': 'college'}
NONWORK = {'unemployed', 'retired', 'disabled', 'student', 'homemaker', 'other'}


def cell_key(attributes):
    education = attributes.get('education_group', attributes.get('_EDU_CAT'))
    education = LABELS.get(education, education)
    job = attributes.get('employment_status', attributes.get('employment'))
    work = 'attached' if job in {'employed', 'on_leave'} else 'not_attached' if job in NONWORK else None
    if education not in EDUCATION or work is None:
        return 'unknown'
    return education+'|'+work


def allocate_core(counts, masses, n, minimum=12):
    """Draft minimum-plus-proportional allocation; within-cell SRS has known pi.

    This produces counts only, never selects respondents or changes inputs.
    Unknown is a separate cell. Impossible coverage is reported, not hidden.
    """
    if set(counts) != set(masses) or type(n) is not int or type(minimum) is not int or minimum < 0:
        raise ValueError('Matching cells and integer allocation parameters required')
    if any(type(v) is not int or v < 0 for v in counts.values()):
        raise ValueError('Nonnegative frame counts required')
    if any(not math.isfinite(masses[k]) or masses[k] < 0 or (counts[k] > 0 and masses[k] <= 0) for k in counts):
        raise ValueError('Positive finite mass for every populated cell required')
    if not 0 <= n <= sum(counts.values()):
        raise ValueError('Requested size exceeds frame')
    result = {k: min(minimum, counts[k]) for k in sorted(counts)}
    if sum(result.values()) > n:
        raise ValueError('Size cannot meet minimums; revise design explicitly')
    while sum(result.values()) < n:
        remaining = n-sum(result.values())
        available = [k for k in result if result[k] < counts[k]]
        total = sum(masses[k] for k in available)
        quotas = {k: remaining*masses[k]/total for k in available}
        adds = {k: min(counts[k]-result[k], int(quotas[k])) for k in available}
        if not sum(adds.values()):
            adds[max(available, key=lambda k: (quotas[k], k))] = 1
        for k, v in adds.items():
            result[k] += v
    return result
