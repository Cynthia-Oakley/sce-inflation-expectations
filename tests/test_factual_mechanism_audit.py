import pandas as pd
import pytest
from studies.sce_inflation_expectations.factual_mechanism_audit import adjacent_pairs, category_days, audit_prior


def test_calendar_adjacency_and_panel_boundaries():
    f = pd.DataFrame({'userid':[1,1,1,2,2], 'date':[202012,202101,202103,202101,202102],
                      'weight':[1]*5, 'Q9_mean':[3,4,7,9,8], 'Q9_iqr':[2]*5})
    p = adjacent_pairs(f)
    assert p[['userid','date']].values.tolist() == [[1,202101],[2,202102]]
    assert p.previous_Q9_mean.tolist() == [3,9]
    f = pd.concat([f,f.iloc[:1]])
    with pytest.raises(ValueError, match='duplicate'):
        adjacent_pairs(f)


def test_days_count_sets_not_transactions_and_keep_missing():
    def r(ucc, day, cost=2, flag='2', dflag='D'):
        return dict(UCC=ucc, EXPNSQDY=str(day), COST=str(cost), PUB_FLAG=flag, EXPN_QDY=dflag)
    rows = [r('100000',1),r('100000',1),r('100000',3),r('100000',9),
            r('200000',1),r('200000',2,flag='1'),r('200000',3,cost=-1),r('200000',4,dflag='X')]
    out = category_days(rows, {'100000':'food_at_home','200000':'food_away_from_home'}, {'100000','200000'})
    assert out['food_at_home']['recorded_days_7d'] == 2
    assert out['food_at_home']['positive_records'] == 4
    assert out['food_at_home']['missing_day_records'] == 1
    assert out['food_away_from_home']['day_codes'] == [1]
    assert out['food_away_from_home']['missing_day_records'] == 1
    assert out['personal_care_products_services']['status'] == 'no_published_positive_records'


def test_prior_uses_same_person_previous_observation():
    f = pd.DataFrame({'userid':[1,1,2,2], 'date':[202012,202101]*2,
                      'weight':[1]*4, 'Q9_mean':[2,2,8,8], 'Q9_iqr':[1,1,3,3]})
    out = audit_prior(f)
    assert out['valid_q9_pairs'] == 2
    now = out['monthly'][1]
    assert now['own_previous_mae_pp'] == 0
    assert now['common_previous_panel_median_mae_pp'] == 3
    assert out['within_month_centered_q9_correlation'] == pytest.approx(1)
