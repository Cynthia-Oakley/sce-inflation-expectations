"""Design checks with synthetic people only; no survey target files are read."""
from collections import Counter

import pytest

from studies.sce_inflation_expectations.reference_population_preparation import sample_strata, anonymous_id
from studies.sce_inflation_expectations.reference_validation_preparation import registered_protocol


def test_sparse_strata_have_positive_known_inclusion_and_reproducible_sample():
    frame=[]
    for label,count in [('young',1),('middle',17),('old',82)]:
        frame += [{'agent_id':f'{label}_{i}', 'attributes':{'age_group':label,'household_income_band':'low'}} for i in range(count)]
    selected,pi,meta=sample_strata(frame,202003,n=24)
    assert len(selected)==24 and 'young_0' in selected
    assert sample_strata(list(reversed(frame)),202003,n=24)==(selected,pi,meta)
    represented=Counter(p['attributes']['age_group']+'|low' for p in frame if p['agent_id'] in selected)
    assert represented==meta['stratum_n']
    for p in frame:
        if p['agent_id'] in selected:
            key=p['attributes']['age_group']+'|low'
            assert pi[p['agent_id']]==meta['stratum_n'][key]/meta['stratum_N'][key]
    assert 0<min(pi.values())<=max(pi.values())<=1


def test_unobserved_categories_remain_a_stratum_and_bad_frames_fail():
    frame=[{'agent_id':str(i),'attributes':{}} for i in range(10)]
    assert sample_strata(frame,202003,n=5)[2]['stratum_N']=={'unknown|unknown':10}
    with pytest.raises(ValueError):sample_strata(frame+frame[:1],202003,n=5)
    with pytest.raises(ValueError):sample_strata(frame,202003,n=11)


def test_private_identity_is_stable_and_protocol_keeps_new_months_primary():
    assert anonymous_id(12)==anonymous_id(12) and anonymous_id(12)!=anonymous_id(13)
    assert anonymous_id(12).startswith('ref_') and len(anonymous_id(12))==20
    p=registered_protocol(20)
    assert p['planned_calls']==len(p['months'])*p['n_per_month']*2==4608
    assert len(p['new_months'])==8 and len(p['old_months'])==4
    assert not set(p['new_months'])&set(p['old_months'])
    assert p['primary_month_scope']=='new_months' and p['budget_cap_usd']==20
