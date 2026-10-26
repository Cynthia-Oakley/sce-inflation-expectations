from studies.sce_inflation_expectations.evaluation.monthly_main_readout import model_distribution,chronological_blend


def test_macro_model_support_does_not_depend_on_current_truth():
    cases=[dict(survey_weight=1.,real={'q9_mean':None},arms={'monthly_reconstruction':{'mean':2.,'point':3.}}),
           dict(survey_weight=2.,real={'q9_mean':100.},arms={'monthly_reconstruction':{'mean':8.,'point':9.}})]
    assert model_distribution(cases,'q9_mean')==([2.,8.],[1.,2.])
    cases[0]['real']['q9_mean']=-999
    assert model_distribution(cases,'q9_mean')==([2.,8.],[1.,2.])


def test_combination_weight_is_fit_only_on_earlier_months():
    train=[dict(month='2019-01',sim_pp=4.,anchor_pp=2.,truth_pp=3.),dict(month='2019-02',sim_pp=4.,anchor_pp=2.,truth_pp=3.)]
    test=[dict(month='2023-01',sim_pp=4.,anchor_pp=2.,truth_pp=9.)]
    first=chronological_blend(train+test,['2019-01','2022-12'],['2023-01','2025-10'])
    test[0]['truth_pp']=-20.
    second=chronological_blend(train+test,['2019-01','2022-12'],['2023-01','2025-10'])
    for loss in ('mae','mse'):
        assert first[loss]['simulation_weight']==second[loss]['simulation_weight']==.5
