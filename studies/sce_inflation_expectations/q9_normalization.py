"""Explicit, user-authorized proportional Q9 postprocessing; raw replies stay raw."""
import json
import math

POLICY = 'proportional_nonnegative_v1'


def response_point(raw):
    try:
        obj = json.loads(raw); value = obj.get('point_pct')
    except (ValueError, TypeError, AttributeError):
        return None
    return value if type(value) in (int, float) and math.isfinite(value) else None


def normalize_bins(bins):
    if (not isinstance(bins, list) or len(bins) != 10
            or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in bins)):
        raise ValueError('Ten finite nonnegative numeric probabilities required')
    try:
        total = math.fsum(bins)
    except OverflowError as exc:
        raise ValueError('Finite positive sum required') from exc
    if not math.isfinite(total) or total <= 0:
        raise ValueError('Finite positive sum required')
    normalized = [float(v)/total*100 for v in bins]
    if not math.isclose(math.fsum(normalized), 100, rel_tol=0, abs_tol=1e-9):
        raise ValueError('Normalized sum check failed')
    return {'raw_bins': list(bins), 'raw_sum': total, 'bins': normalized,
            'applied': total != 100, 'policy': POLICY}


def response_view(raw):
    """Strict original shape; no missing-field imputation, fences or key remapping."""
    obj = json.loads(raw)
    if not isinstance(obj, dict) or not isinstance(obj.get('q9'), dict):
        raise ValueError('Original nested q9 object required')
    if set(obj['q9']) != {f'bin{i}' for i in range(1, 11)}:
        raise ValueError('Exactly ten original bins required')
    point = obj.get('point_pct')
    if type(point) not in (int, float) or not math.isfinite(point):
        raise ValueError('Finite numeric original Q8 required')
    return {**normalize_bins([obj['q9'][f'bin{i}'] for i in range(1, 11)]), 'point': point}
