"""SCE one-year Q9 density scoring, with explicit fit status.

The rule families follow Armantier et al. (2017), Appendix C. The article does
not specify every optimization choice for generalized beta fitting, so beta
results are a documented research replication, not an official implementation.
All inflation rates and returned moments are in percentage points.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Sequence


# Questionnaire order: +12 or more, +8..12, ..., -8..-12, -12 or less.
BIN_BOUNDS = (
    (12.0, float("inf")), (8.0, 12.0), (4.0, 8.0),
    (2.0, 4.0), (0.0, 2.0), (-2.0, 0.0),
    (-4.0, -2.0), (-8.0, -4.0), (-12.0, -8.0),
    (float("-inf"), -12.0),
)
TAIL_LIMIT = 38.0  # Appendix C's bound for open-ended beta support.


@dataclass(frozen=True)
class DensityScore:
    status: str
    family: str | None = None
    mean: float | None = None
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    iqr: float | None = None
    prob_deflation: float | None = None
    fit_loss: float | None = None


def _uniform(left: float, right: float) -> DensityScore:
    width = right - left
    return DensityScore(
        "ok", "uniform", (left + right) / 2,
        left + width / 4, (left + right) / 2, left + width * 3 / 4,
        width / 2, min(1.0, max(0.0, (0.0 - left) / width)), 0.0,
    )


def _triangle_quantile(q: float, left: float, right: float) -> float:
    width = right - left
    return left + width * sqrt(q / 2) if q <= 0.5 else right - width * sqrt((1 - q) / 2)


def _triangle_cdf(x: float, left: float, right: float) -> float:
    if x <= left:
        return 0.0
    if x >= right:
        return 1.0
    mid = (left + right) / 2
    if x <= mid:
        return 2 * ((x - left) / (right - left)) ** 2
    return 1 - 2 * ((right - x) / (right - left)) ** 2


def _triangle(positive: list[int], probabilities: list[float]) -> DensityScore:
    # Numeric left/right order is the reverse of questionnaire bin order.
    right_index, left_index = positive
    if left_index != right_index + 1:
        return DensityScore("two_nonadjacent")
    left_bin, right_bin = BIN_BOUNDS[left_index], BIN_BOUNDS[right_index]
    crossing = left_bin[1]
    left_mass = probabilities[left_index] / 100
    if left_mass <= 0 or left_mass >= 1:
        return DensityScore("invalid_probabilities")

    if left_index == 9:  # Open negative tail: anchor at the inner closed bin's right edge.
        anchor_left = False
    elif right_index == 0:  # Open positive tail: anchor at the inner closed bin's left edge.
        anchor_left = True
    else:
        left_width = left_bin[1] - left_bin[0]
        right_width = right_bin[1] - right_bin[0]
        if left_width == right_width:
            anchor_left = left_mass >= 0.5
        else:
            narrow_left = left_width < right_width
            narrow_mass = left_mass if narrow_left else 1 - left_mass
            anchor_left = narrow_left if narrow_mass > 0.40 else not narrow_left

    if anchor_left:
        left = left_bin[0]
        distance = crossing - left
        width = (distance * sqrt(2 / left_mass) if left_mass <= 0.5
                 else distance / (1 - sqrt((1 - left_mass) / 2)))
        right = left + width
    else:
        right = right_bin[1]
        distance = right - crossing
        width = (distance * sqrt(2 / (1 - left_mass)) if left_mass >= 0.5
                 else distance / (1 - sqrt(left_mass / 2)))
        left = right - width
    if not isfinite(left) or not isfinite(right) or left < -TAIL_LIMIT or right > TAIL_LIMIT:
        return DensityScore("triangle_support_out_of_bounds")
    q25, q50, q75 = (_triangle_quantile(q, left, right) for q in (0.25, 0.5, 0.75))
    return DensityScore("ok", "triangle", (left + right) / 2, q25, q50, q75,
                        q75 - q25, _triangle_cdf(0.0, left, right), 0.0)


def _generalized_beta(positive: list[int], probabilities: list[float]) -> DensityScore:
    try:
        import numpy as np
        from scipy.optimize import least_squares
        from scipy.special import betainc, betaincinv
    except ImportError as exc:
        raise RuntimeError("Generalized beta scoring requires numpy and scipy") from exc

    highest, lowest = positive[0], positive[-1]
    lower_open = lowest == 9
    upper_open = highest == 0
    fixed_left = BIN_BOUNDS[lowest][0]
    fixed_right = BIN_BOUNDS[highest][1]
    # Use every internal questionnaire boundary between occupied extremes.
    boundaries = np.array([BIN_BOUNDS[i][1] for i in range(lowest, highest, -1)], dtype=float)
    # The loop above is reversed for descending indices; sort and take the CDF below each edge.
    boundaries.sort()
    bin_order = list(range(lowest, highest - 1, -1))
    masses = np.array([probabilities[i] / 100 for i in bin_order], dtype=float)
    empirical = np.cumsum(masses)[:-1]
    if len(boundaries) != len(empirical):
        raise AssertionError("bin edge and CDF lengths differ")

    def unpack(params: Sequence[float]) -> tuple[float, float, float, float]:
        alpha, beta = float(params[0]), float(params[1])
        cursor = 2
        left = float(params[cursor]) if lower_open else fixed_left
        cursor += int(lower_open)
        right = float(params[cursor]) if upper_open else fixed_right
        return alpha, beta, left, right

    lower = [1.0, 1.0]
    upper = [200.0, 200.0]
    initial_tail = []
    if lower_open:
        lower.append(-TAIL_LIMIT)
        upper.append(-12.000001)
        initial_tail.append(-20.0)
    if upper_open:
        lower.append(12.000001)
        upper.append(TAIL_LIMIT)
        initial_tail.append(20.0)

    def residual(params: Sequence[float]):
        alpha, beta, left, right = unpack(params)
        x = np.clip((boundaries - left) / (right - left), 0, 1)
        return betainc(alpha, beta, x) - empirical

    candidates = []
    for a, b in ((1.1, 1.1), (2.0, 2.0), (5.0, 5.0)):
        result = least_squares(residual, [a, b, *initial_tail], bounds=(lower, upper),
                               ftol=1e-11, xtol=1e-11, gtol=1e-11, max_nfev=1200)
        candidates.append(result)
    best = min(candidates, key=lambda item: float(np.dot(item.fun, item.fun)))
    alpha, beta, left, right = unpack(best.x)
    span = right - left
    q25, q50, q75 = (left + span * float(betaincinv(alpha, beta, q)) for q in (0.25, 0.5, 0.75))
    mean = left + span * alpha / (alpha + beta)
    prob_deflation = (0.0 if 0 <= left else 1.0 if 0 >= right
                      else float(betainc(alpha, beta, (0 - left) / span)))
    loss = float(np.dot(best.fun, best.fun))
    if not all(isfinite(x) for x in (mean, q25, q50, q75, prob_deflation, loss)):
        return DensityScore("fit_nonfinite")
    return DensityScore("ok", "generalized_beta", mean, q25, q50, q75,
                        q75 - q25, prob_deflation, loss)


def score_q9(bins: Sequence[float]) -> DensityScore:
    """Score ten percentages in questionnaire order; never silently normalize."""
    if len(bins) != 10:
        return DensityScore("invalid_bin_count")
    try:
        probabilities = [float(value) for value in bins]
    except (TypeError, ValueError):
        return DensityScore("invalid_probabilities")
    if not all(isfinite(value) and 0 <= value <= 100 for value in probabilities):
        return DensityScore("invalid_probabilities")
    if abs(sum(probabilities) - 100) > 1e-6:
        return DensityScore("invalid_probability_sum")
    positive = [index for index, value in enumerate(probabilities) if value > 0]
    if len(positive) == 1:
        left, right = BIN_BOUNDS[positive[0]]
        return _uniform(-TAIL_LIMIT if left == float("-inf") else left,
                        TAIL_LIMIT if right == float("inf") else right)
    if len(positive) == 2:
        return _triangle(positive, probabilities)
    return _generalized_beta(positive, probabilities)


def weighted_empirical_quantile(values: Sequence[float], weights: Sequence[float], q: float = 0.5) -> float:
    """Smallest observed value whose cumulative valid weight reaches q."""
    if len(values) != len(weights) or not 0 <= q <= 1:
        raise ValueError("values/weights length or quantile invalid")
    pairs = sorted((float(value), float(weight)) for value, weight in zip(values, weights)
                   if value is not None and weight is not None
                   and isfinite(float(value)) and isfinite(float(weight)) and float(weight) > 0)
    if not pairs:
        raise ValueError("no valid positive-weight observations")
    threshold = q * sum(weight for _, weight in pairs)
    running = 0.0
    for value, weight in pairs:
        running += weight
        if running >= threshold:
            return value
    return pairs[-1][0]
