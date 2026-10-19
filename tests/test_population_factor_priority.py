import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'studies/sce_inflation_expectations/evaluation'))
from population_factor_priority import importance


def test_orthogonal_known_contributions_and_month_control():
    a=np.tile([-1., -1, 1, 1], 2); b=np.tile([-1., 1, -1, 1], 2)
    months=np.repeat([202001, 202002], 4); y=2*a+b+np.repeat([0.,100.], 4)
    r=importance(y, np.column_stack([a,b]), np.ones(8), months, {'a':[0],'b':[1]})
    assert r['r2_within_month']==pytest.approx(1)
    values={v['factor']:v for v in r['ranked_factors']}
    assert values['a']['drop_from_full_r2_points']==pytest.approx(80)
    assert values['b']['drop_from_full_r2_points']==pytest.approx(20)


def test_shared_information_not_a_unique_contribution():
    a=np.tile([-1., -1, 1, 1], 2); months=np.repeat([202001,202002],4)
    r=importance(a, np.column_stack([a,a]), np.ones(8), months, {'a':[0],'b':[1]})
    assert all(v['alone_r2_points']==pytest.approx(100) for v in r['ranked_factors'])
    assert all(v['drop_from_full_r2_points']==pytest.approx(0, abs=1e-10) for v in r['ranked_factors'])
