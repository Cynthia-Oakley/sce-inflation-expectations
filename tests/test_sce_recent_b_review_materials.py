import pytest
from studies.sce_inflation_expectations.experiments.recent_b_review_materials import require_past_labels,macro_prediction,cpi_review,freeze_macro_parameters


def test_B_target_or_late_A_label_never_enters_parameter_fit():
    row=dict(month='202510',truth_published_date='2025-11-07',truth_pp=3.2,baseline_pp=3.4,
             before_model_pp=3.3,cpi_yoy_pp=3.,cpi_change_pp=.1)
    require_past_labels([row],'2025-11-13T23:59:59-05:00')
    with pytest.raises(ValueError,match='Only A labels'):
        require_past_labels([dict(row,month='202511')],'2025-11-13T23:59:59-05:00')
    with pytest.raises(ValueError,match='Only A labels'):
        require_past_labels([dict(row,truth_published_date='2025-11-13')],'2025-11-13T23:59:59-05:00')


def test_macro_control_does_not_depend_on_simulation_or_need_a_fake_value():
    fit=dict(features=['cpi_change'],intercept=.1,coefficients=[2.])
    row=dict(baseline_pp=3.,cpi_yoy_pp=2.,cpi_change_pp=.2)
    assert macro_prediction(row,fit)==pytest.approx(3.5)
    assert macro_prediction(dict(row,sim_pp=90),fit)==pytest.approx(3.5)
    fit=dict(features=['sim_gap'],intercept=0.,coefficients=[.5])
    with pytest.raises(ValueError,match='Missing finite'):
        macro_prediction(row,fit)
    assert macro_prediction(dict(row,sim_pp=4),fit)==pytest.approx(3.5)


def test_canceled_CPI_reference_is_explicit_not_silently_adjacent():
    env={'provider_args':{'targets':[{'as_of':'2025-12-18T23:59:59-05:00'}],
      'signals_by_step':{'0':[dict(signal_id='bls_cpi_u_all_items_yoy_a',reference_period='2025-11',published_at='2025-12-18T08:30:00-05:00',value=2.7),
                             dict(signal_id='bls_cpi_u_all_items_yoy_b',reference_period='2025-09',published_at='2025-10-24T08:30:00-04:00',value=3.)]}}}
    r=cpi_review(env)
    assert r['cpi_reference_gap_months']==2 and r['cpi_change_pp']==pytest.approx(-.3)


def test_CSV_strings_are_converted_and_fixed_alpha_recovers_known_change_slope():
    rows=[]
    for i in range(48):
        year,month=2019+i//12,i%12+1;dc=i/100
        rows.append(dict(month=f'{year}{month:02}',truth_published_date=f'{year+1}-01-01',
             truth_pp=str(3+2*dc),baseline_pp='3',before_model_pp='4',cpi_yoy_pp='2',cpi_change_pp=str(dc)))
    fit={f'Core_{name}':dict(alpha=0,validation=[]) for name in ('macro_without_sim','macro_plus_sim')}
    p=freeze_macro_parameters(rows,fit,'2025-11-13T23:59:59-05:00')
    assert p['fits']['macro_without_sim']['coefficients'][2]==pytest.approx(2.)
    assert macro_prediction(dict(baseline_pp='3',cpi_yoy_pp='2',cpi_change_pp='.5'),p['fits']['macro_without_sim'])==pytest.approx(4.)
