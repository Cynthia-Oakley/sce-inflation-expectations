"""Focused mathematical, source-boundary and placebo checks, with toy data."""
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'studies/sce_inflation_expectations/evaluation'))
from center_shift_diagnostic import common_shift, metric, quantile
from frequency_matching_candidate import (income_code, coarse_income, family_group,
    recipient_profile, assign, permute_vectors)


def test_common_shift_matches_center_without_losing_prior_width():
    previous = [0., 1., 5., 12.]
    llm = [3., 4., 4.5, 6.]
    shifted = common_shift(previous, llm)
    assert shifted == pytest.approx([3., 4., 8., 15.])
    assert quantile(shifted, .5) == 4.
    assert quantile(shifted, .75)-quantile(shifted, .25) == 5.
    # Current truth changes evaluation, not predictions.
    before = shifted.copy()
    assert metric(shifted, [1., 1., 1., 1.], previous)['cross_W1'] != metric(shifted, [8., 8., 8., 8.], previous)['cross_W1']
    np.testing.assert_equal(common_shift(previous, llm), before)


def test_difference_of_medians_is_not_median_individual_revision():
    previous, llm = [0., 10., 11.], [12., 13., 2.]
    assert quantile(llm, .5)-quantile(previous, .5) == 2.
    assert quantile(np.array(llm)-previous, .5) == 3.


def test_common_shift_rejects_missing_alignment():
    with pytest.raises(ValueError):
        common_shift([1., 2.], [1.])
    with pytest.raises(ValueError):
        common_shift([1., float('nan')], [1., 2.])


def test_income_and_family_crosswalk_boundaries():
    assert income_code(49999) == 5
    assert income_code(50000) == 6
    assert income_code(99999) == 8
    assert income_code(100000) == 9
    assert coarse_income(income_code(100000)) == 'over_100k'
    assert family_group(1) == '1'
    assert family_group(8) == '3+'
    assert family_group(0) is None


def test_stale_family_or_current_month_not_used():
    original = {'month': 202105, 'profile': {'age_group': 'Under 40', 'household_income_band': 'under_50k'}}
    history = {'features': {
        'fine_income': {'available': True, 'source_month': 202105, 'age_months': 0, 'value': 5, 'agrees_with_current_coarse_income': True},
        'family_composition': {'available': True, 'source_month': 202101, 'age_months': 4, 'moved_after_record': True,
            'value': {'members_including_self_excluding_nonrelatives': 2}}}}
    profile, _ = recipient_profile(original, history)
    assert 'family_size_group' not in profile
    assert 'fine_income_code' not in profile


def test_supported_zero_week_can_be_selected_and_fallback_is_explicit():
    donors = [{'cu_key': 'only', 'week_key': 'w', 'quarter': 1, 'weight': 1.,
               'attributes': {'age_group': 'Under 40'}, 'days': [0, 0, 0, 0]}]
    result = assign(donors, {'age_group': 'Under 40', 'family_size_group': '3+'}, 'example', min_units=1, min_effective=1)
    assert result['days'] == [0, 0, 0, 0]
    assert result['matched_fields'] == ['age_group']
    assert result['relaxed_fields'] == ['family_size_group']


def test_placebo_permutation_preserves_whole_vectors_not_identity():
    from collections import Counter
    rows = [{'days': [i, i+1, i+2, i+3]} for i in range(4)]
    shuffled = permute_vectors(rows)
    assert Counter(tuple(r['days']) for r in rows) == Counter(tuple(r['days']) for r in shuffled)
    assert all(r['source_index'] != i for i, r in enumerate(shuffled))
    for r in shuffled:
        assert r['days'] == rows[r['source_index']]['days']
