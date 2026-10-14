import pytest
from studies.sce_inflation_expectations.evaluation.expansion_preflight import scaled_budget


def test_scaled_budget_keeps_actual_estimate_separate_from_reserve():
    old=dict(planned_answers=192,jobs=[{'estimated_cost_usd':.1},{'estimated_cost_usd':.044}],
             conservative_simulation_cost_bound_usd=.63)
    result=scaled_budget(old,3072)
    assert result['historical_cost_estimate_scaled_usd']==pytest.approx(2.304)
    assert result['historical_byte_reservation_scaled_usd']==pytest.approx(10.08)
    assert old['planned_answers']==192
