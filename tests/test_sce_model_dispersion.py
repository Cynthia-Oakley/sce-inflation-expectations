import pytest
from studies.sce_inflation_expectations.evaluation.model_dispersion import analyze


def cases(variant):
    rows=[]
    for i,y in enumerate((1.,3.,5.)):
        for rep in (1,2):
            rows.append(dict(month=202503,agent_id=str(i),repeat=rep,design_survey_weight=1.,
                real={'q9_mean':y,'previous_q9_mean':y},
                arms={'model':{'mean':variant(i,y,rep)}}))
    return rows


def test_central_collapse_is_distinct_from_real_heterogeneity():
    r=analyze(cases(lambda i,y,rep:3.))
    assert r['equal_month_metrics']['model']['variance_pp2']==0
    assert r['equal_month_metrics']['human']['variance_pp2']>0
    assert r['equal_month_metrics']['model']['share_within_half_pp_of_human_center']==1
    assert r['memorization_test'] is False


def test_stable_diversity_is_not_generation_noise():
    r=analyze(cases(lambda i,y,rep:y))
    n=r['repeat_equal_month_means']['model']
    assert n['within_person_generation_variance_pp2']==0
    assert n['noise_adjusted_between_variance_pp2']==pytest.approx(8/3)


def test_common_support_requires_both_repeats():
    rows=cases(lambda i,y,rep:y)
    rows[-1]['arms']['model']['mean']=None
    assert analyze(rows)['common_person_months']==2


def test_duplicate_rows_rejected():
    rows=cases(lambda i,y,rep:y)
    with pytest.raises(ValueError,match='Duplicate'):analyze(rows+[rows[0]])


def test_national_headline_is_not_replaced_by_sample_median():
    r=analyze(cases(lambda i,y,rep:3.),{202503:5.})
    assert r['equal_month_metrics']['model']['share_within_half_pp_of_human_center']==1
    assert r['official_center_concentration_equal_month_means']['model']==0
