from copy import deepcopy
import json
import math
import pytest
from studies.sce_inflation_expectations.q9_normalization import normalize_bins, response_view, response_point


def test_known_proportions_and_zeros_preserved():
    raw = [20, 30, 45]+[0]*7; original = deepcopy(raw)
    r = normalize_bins(raw)
    assert raw == original and r['raw_bins'] == original
    assert r['bins'][:3] == pytest.approx([400/19, 600/19, 900/19])
    assert r['bins'][3:] == [0]*7 and math.fsum(r['bins']) == pytest.approx(100)
    assert r['bins'][1]/r['bins'][0] == pytest.approx(1.5)
    assert r['raw_sum'] == 95 and r['applied']


def test_over_sum_and_unchanged_complete_probability():
    r = normalize_bins([15]+[10]*9)
    assert r['raw_sum'] == 105 and r['bins'][0] == pytest.approx(100/7)
    assert normalize_bins([10]*10)['bins'] == [10]*10
    assert not normalize_bins([10]*10)['applied']


@pytest.mark.parametrize('raw', [[0]*10, [-1]+[11]*9, [float('nan')]+[1]*9,
    [float('inf')]+[1]*9, [True]+[1]*9, ['10']*10, [10]*9])
def test_unusable_probabilities_are_not_invented(raw):
    with pytest.raises(ValueError): normalize_bins(raw)


def test_point_unchanged_and_numeric_response_required():
    o = {'point_pct': -2.25, 'q9': {f'bin{i}': 9.5 for i in range(1,11)}}
    r = response_view(json.dumps(o))
    assert r['point'] == -2.25 and r['raw_sum'] == 95
    assert r['bins'] == pytest.approx([10]*10)
    del o['q9']['bin1']
    with pytest.raises(ValueError): response_view(json.dumps(o))
    assert response_point(json.dumps(o)) == -2.25  # Q9 failure must not erase legal Q8.
    assert response_point('{bad json') is None


def test_very_small_positive_total_does_not_overflow_scaling():
    r = normalize_bins([1e-320]*10)
    assert r['bins'] == pytest.approx([10]*10)
