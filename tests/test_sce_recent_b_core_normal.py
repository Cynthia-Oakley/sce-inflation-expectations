from copy import deepcopy
import math

import numpy as np
import pytest

from studies.sce_inflation_expectations.experiments import recent_b_core_normal as mod
from studies.sce_inflation_expectations.core_normal_joint import JointAnswer, JointExpansion


def record(uid,age='Under 40',weight=2.,raw=1.):
    return dict(persona=dict(agent_id=uid,attributes=dict(age_group=age,education_group='college',
        numeracy='high',household_income_band='50k_to_100k',region='South'),source_reference_period='202501'),
        analysis_weight=weight,raw_source_weight=raw)


def test_allocate_only_positive_remaining_mass_and_conserve_row_count():
    result=mod.allocate_normal({('a',):1.,('b',):9.,('none',):0.},20)
    assert sum(result.values())==20 and result[('b',)]>result[('a',)]>=1
    assert ('none',) not in result
    with pytest.raises(ValueError):mod.allocate_normal({('a',):1.,('b',):1.},1)


def test_keep_core_once_scale_population_and_preserve_grid_shares():
    rows=[record('a'),record('b','Over 60')];before=deepcopy(rows)
    frame,profiles,cw,audit=mod.make_frame(rows,'202511',10)
    assert rows==before and len(frame)==10 and len(profiles)==10
    assert sum(r['id']=='a' for r in frame)==sum(r['id']=='b' for r in frame)==1
    assert all(r['entry']=='unknown' for r in frame)
    assert math.isclose(sum(r['weight'] for r in frame),10.)
    assert sum(r['weight'] for r in frame if r['age']=='under_40')==5.
    assert audit['core_mass_fraction']==.5 and cw=={'a':2.,'b':2.}
    assert [r['weight'] for r in frame if r['id'] in ('a','b')]==[2.5,2.5]


def test_representation_size_does_not_change_exact_answer_distribution():
    rows=[record('a',weight=3.),record('b','Over 60',weight=1.)]
    answers=[JointAnswer('a',tuple([10.]*10),2.,1.,2.),JointAnswer('b',tuple([10.]*10),8.,1.,8.)]
    results=[]
    for size in (10,11,1300):
        frame,profiles,cw,audit=mod.make_frame(rows,'202511',size)
        model=JointExpansion(frame,['a','b'],answers,cw,prior_strength=8.)
        results.append(model.atom_weights()/size)
        assert model.report()['mass_conservation_error']<1e-9
    assert all(np.allclose(results[0],r,atol=1e-12) for r in results[1:])


def test_fully_observed_cell_receives_no_fictitious_normal_rows():
    frame,profiles,_,_=mod.make_frame([record('a',weight=1.),record('b','Over 60',weight=3.)],'202511',10)
    assert sum(r['age']=='under_40' for r in frame)==1
    assert all(p['kind']=='Core_LLM' for aid,p in profiles.items() if next(r for r in frame if r['id']==aid)['age']=='under_40')


def test_unknown_coordinates_retained_without_inventing_complete_grid():
    rows=[record('a'),record('b','Over 60')];rows[0]['persona']['attributes']['numeracy']=None
    frame,profiles,_,_=mod.make_frame(rows,'202511',10)
    assert next(r for r in frame if r['id']=='a')['numeracy'] is None
    assert any(r['numeracy'] is None for r in frame if r['id'].startswith('BNormal'))


def test_frame_cannot_hide_missing_weights_or_excess_core_mass():
    for bad in (None,0.,-1.,float('nan')):
        with pytest.raises(ValueError):mod.make_frame([record('a',raw=bad),record('b','Over 60')],'202511',10)
    with pytest.raises(ValueError,match='exceeds'):
        mod.make_frame([record('a',weight=1.,raw=2.),record('b','Over 60')],'202511',10)


def test_reproducible_profile_assignments_and_answer_draws():
    rows=[record('a'),record('b','Over 60')]
    assert mod.make_frame(rows,'202511',10)==mod.make_frame(rows,'202511',10)
    assert mod.TAU==8. and mod.SEED==20261026
