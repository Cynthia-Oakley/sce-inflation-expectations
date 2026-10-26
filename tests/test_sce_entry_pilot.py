from copy import deepcopy

import pytest

from studies.sce_inflation_expectations.experiments.entry_initialization_pilot import select_people,cohort


def example():
    rows=[];states={}
    for label in ('entrant','returning'):
        for i in range(4):
            aid=f'{label}{i}'
            rows.append({'persona':{'agent_id':aid},'survey_entry_status':label,
                         'inclusion_probability':.5,'raw_survey_weight':2.,
                         'analysis_weight':4.,'weight_valid':True})
            states[aid]={'history_centers':[], 'fields':{k:{'source_kind':'synthetic_donor' if label=='entrant' else 'own_observed',
                                                          'source_period':202504} for k in ('q8','q9')}}
    return rows,states


def test_two_phase_weight_and_order_invariance():
    rows,states=example();old=deepcopy(rows)
    result,support=select_people(rows,states,'202505',n=2)
    assert len(result)==4 and all(r['inclusion_probability']==.25 for r in result)
    assert all(r['analysis_weight']==8 for r in result)
    assert support['entrant']['parent_eligible_n']==4
    assert select_people(list(reversed(rows)),states,'202505',n=2)==(result,support)
    assert rows==old


@pytest.mark.parametrize('period',[202505,202501])
def test_current_or_old_donor_rejected(period):
    rows,states=example();states['entrant0']['fields']['q9']['source_period']=period
    with pytest.raises(ValueError):cohort(rows[0],states['entrant0'],'202505')


def test_entrant_does_not_inherit_real_history():
    rows,states=example();states['entrant0']['history_centers']=[{'center':3.}]
    with pytest.raises(ValueError):cohort(rows[0],states['entrant0'],'202505')


def test_returner_reference_requires_both_adjacent_fields():
    rows,states=example();states['returning0']['fields']['q9']['source_kind']='synthetic_donor'
    assert cohort(rows[4],states['returning0'],'202505') is None


def test_missing_weight_is_retained_without_substitution():
    rows,states=example()
    for r in rows:r.update(weight_valid=False,raw_survey_weight=None)
    selected,_=select_people(rows,states,'202505',n=4)
    assert len(selected)==8 and all(r['analysis_weight'] is None for r in selected)


def test_insufficient_domain_stops_before_sampling():
    rows,states=example()
    with pytest.raises(ValueError):select_people(rows,states,'202505',n=5)


def case(repeat, mean):
    return {'month':202505,'userid':1,'repeat':repeat,'survey_weight':2.,
            'real':{'q9_mean':3.,'q9_iqr':1.,'q9_zero_deflation':0.,'q9_bins':[10.]*10,
                    'q8_point':4.,'previous_q9_mean':None},
            'arms':{'monthly_reconstruction':{'mean':mean,'iqr':1.,'zero_deflation':0.,
                                             'q9_bins':[10.]*10,'point':3.}}}


def test_two_repeats_are_one_person_and_both_contribute_to_errors():
    from studies.sce_inflation_expectations.evaluation.entry_initialization_pilot import summarize
    result=summarize([case(1,1.),case(2,2.)],[202505],[1,2],['monthly_reconstruction'])
    assert result['q9_person_months']==1
    metrics=result['arms']['monthly_reconstruction']['auxiliary_survey_weighted']['q9']
    assert len(metrics['cells'])==2
    assert metrics['center_headline_errors']['mae_pp']==1.5


def test_one_bad_q9_repeat_does_not_remove_valid_q8():
    from studies.sce_inflation_expectations.evaluation.entry_initialization_pilot import summarize
    rows=[case(1,1.),case(2,None)];rows[1]['arms']['monthly_reconstruction']['iqr']=None
    result=summarize(rows,[202505],[1,2],['monthly_reconstruction'])
    assert result['q9_person_months']==0 and result['q8_person_months']==1
