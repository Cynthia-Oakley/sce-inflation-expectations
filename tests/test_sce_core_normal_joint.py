"""Independent mass, leakage and joint-payload invariants for Core/Normal."""
import math

import numpy as np
import pytest

from studies.sce_inflation_expectations.core_normal_joint import JointAnswer, JointExpansion, PointAnswer
from studies.sce_inflation_expectations.evaluation.metrics import quantile


def person(uid, age='young', *, entry='returner', weight=1.):
    return dict(id=uid, weight=weight, entry=entry, education='college',
                numeracy='High', age=age, income='middle')


def answer(uid, value, q8=None):
    p = [0.]*10; p[5 if value < 4 else 3] = 100.
    return JointAnswer(uid, tuple(p), value, 1., q8)


def example(tau=1.):
    people = [person('a'), person('b','old'), person('c','old', entry='newcomer',weight=100.),
              person('d',weight=3.),person('e','old',entry='newcomer',weight=4.)]
    atoms = [answer('a',2.,1.), answer('b',8.,9.),answer('c',20.,21.)]
    return JointExpansion(people,['a','b','c'],atoms,{'a':1.,'b':9.,'c':100.},prior_strength=tau)


def test_parent_excludes_local_and_newcomer_evidence():
    model = example()
    p, alpha, info = model.conditional(model.group_key('d'))
    assert np.allclose(p,[.5,.5,0.])
    assert np.allclose(alpha,[1.,1.,0.])
    assert info['parent_local_overlap'] == 0
    assert info['parent_matching_coordinates'] == 3


def test_full_population_mass_is_integrated_once_not_plus_core_again():
    model = example()
    # Returner weight 5: 4 in young + 1 old -> 2.5 on each Core atom;
    # newcomer weight 104 is entirely on c. Total is 109, not 109+Core.
    assert np.allclose(model.atom_weights(),[2.5,2.5,104.])
    assert model.report()['mass_conservation_error'] < 1e-12


def test_normal_only_mass_and_median_are_exact():
    model = example()
    mass = model.atom_weights(['d','e'])
    assert np.allclose(mass,[1.5,1.5,4.])
    assert quantile([2.,8.,20.],mass,.5) == 20.


def test_normal_answer_or_outcome_in_profile_is_rejected():
    people = [person('a'),person('d')]
    with pytest.raises(ValueError,match='Normal answers forbidden'):
        JointExpansion(people,['a'],[answer('d',2.)],{'a':1.})
    people[1]['q9_mean']=3.
    with pytest.raises(ValueError,match='outcome-free'):
        JointExpansion(people,['a'],[answer('a',2.)],{'a':1.})


def test_no_silent_cross_entry_fallback():
    with pytest.raises(ValueError,match='entry pool'):
        JointExpansion([person('a'),person('n',entry='newcomer')],['a'],[answer('a',2.)],{'a':1.})


def test_parent_pooling_treats_age_and_income_symmetrically():
    rows=[person('a'),person('b','old'),{**person('c'),'income':'low'},person('d')]
    model=JointExpansion(rows,['a','b','c'],[answer('a',2.),answer('b',8.),answer('c',12.)],
                         {'a':1.,'b':1.,'c':1.},prior_strength=2.)
    p,_,info=model.conditional(model.group_key('d'))
    assert np.allclose(p,[1/3,1/3,1/3])
    assert info['outside_parent_core_n']==2


def test_zero_tau_local_and_explicit_unsupported_fallback():
    model=example(tau=0.)
    assert np.allclose(model.conditional(model.group_key('d'))[0],[1.,0.,0.])
    key=('returner','other_education','High','young','middle')
    p,_,audit=model.conditional(key)
    assert np.allclose(p,[1.,0.,0.])
    assert audit['local_unsupported'] and audit['parent_fraction']==1.


def test_weight_scale_does_not_change_conditional_distribution():
    a=example()
    rows=[{**person('a'), 'weight':10.},person('b','old',weight=10.),
          person('c','old',entry='newcomer',weight=1000.),person('d',weight=30.),
          person('e','old',entry='newcomer',weight=40.)]
    b=JointExpansion(rows,a.core_ids,a.answers,{'a':10.,'b':90.,'c':1000.},prior_strength=1.)
    assert np.allclose(a.atom_weights()/a.atom_weights().sum(),b.atom_weights()/b.atom_weights().sum())


def test_q8_missing_does_not_drop_valid_q9_atom_and_invalid_bins_fail():
    a=answer('a',2.,None)
    model=JointExpansion([person('a'),person('d')],['a'],[a],{'a':1.})
    assert model.report()['valid_q9_core_atoms']==1
    assert model.draw_normal(month=202501,seed=4)['d']['q8'] is None
    with pytest.raises(ValueError,match='normalised'):
        JointAnswer('bad',tuple([9.]*10),3.,1.)


def test_draws_reproducible_and_preserve_whole_original_payload():
    rows=[person('a'),person('b','old')]+[person(f'n{i}') for i in range(60)]
    atoms=[answer('a',2.,1.),answer('b',8.,9.)]
    model=JointExpansion(rows,['a','b'],atoms,{'a':1.,'b':1.},prior_strength=1.)
    draws=model.draw_normal(month=202501,seed=7)
    assert draws==model.draw_normal(month=202501,seed=7)
    assert {r['q8'] for r in draws.values()}=={1.,9.}
    payload={str(a.id):a.payload() for a in atoms}
    assert all({k:r[k] for k in ['q9_bins','q9_mean','q9_iqr','q8']}==payload[r['donor_id']] for r in draws.values())


def test_unknown_coordinates_supply_no_matching_evidence():
    rows=[{**person('a'),'age':None},person('b','old'),{**person('d'),'age':None,'income':'low'}]
    model=JointExpansion(rows,['a','b'],[answer('a',2.),answer('b',8.)],{'a':1.,'b':1.},prior_strength=1.)
    p,_,info=model.conditional(model.group_key('d'))
    assert np.allclose(p,[.5,.5])
    assert info['parent_matching_coordinates']==2


def test_invalid_or_duplicate_core_weights_and_targets_fail():
    with pytest.raises(ValueError,match='positive'):
        JointExpansion([person('a')],['a'],[answer('a',2.)],{'a':-1.})
    with pytest.raises(ValueError,match='unique population targets'):
        example().atom_weights(['d','d'])


def test_q8_bank_can_use_a_core_person_without_valid_q9():
    model=JointExpansion([person('a'),person('b','old'),person('d')],['a','b'],
                         [PointAnswer('a',2.),PointAnswer('b',8.)],{'a':1.,'b':1.},prior_strength=1.)
    assert model.report()['valid_q8_core_atoms']==2
    assert model.report()['answer_bank']=='q8_point'
    assert math.isclose(model.atom_weights().sum(),3.)


def test_census_preserves_every_observed_answer_for_any_tau():
    rows=[person('a',weight=10.),person('b','old',weight=1.)]
    model=JointExpansion(rows,['a','b'],[answer('a',2.),answer('b',8.)],{'a':10.,'b':1.},prior_strength=100.)
    assert np.allclose(model.atom_weights(),[10.,1.])
    assert not np.allclose(model.atom_weights(preserve_core=False),[10.,1.])
    assert model.report()['retained_valid_core_population_fraction']==1.


def test_failed_core_is_explicitly_imputed_once_and_other_core_stay_observed():
    rows=[person('a',weight=2.),person('b','old',weight=3.),person('n',weight=5.)]
    model=JointExpansion(rows,['a','b'],[answer('a',2.)],{'a':2.,'b':3.},prior_strength=8.)
    assert np.allclose(model.atom_weights(),[10.])
    assert math.isclose(model.report()['imputed_invalid_core_population_fraction'],.3)


def test_production_adapter_keeps_q8_when_q9_scoring_fails():
    from studies.sce_inflation_expectations.experiments.core_normal_expansion import build_banks
    rows=[person('a'),person('b','old'),person('n')]
    a=answer('a',2.,3.)
    scored={'answer_origin':'llm_model_output','scorer_provenance':{'cached':True},
            'answers':[{'id':'a',**a.payload()},{'id':'b','q9_bins':[],'q9_mean':None,'q9_iqr':None,'q8':-2.}]}
    banks,support=build_banks(rows,[{'id':'a','poststratified_weight':2.},{'id':'b','poststratified_weight':2.}],scored,tau=8.)
    assert len(banks['q9'].answers)==1 and len(banks['q8'].answers)==2
    assert support['invalid_q9_core_ids']==['b'] and not support['invalid_q8_core_ids']


def test_production_adapter_rejects_audit_answers_and_unlabelled_truth():
    from studies.sce_inflation_expectations.experiments.core_normal_expansion import build_banks
    scored={'answer_origin':'human_truth','scorer_provenance':{},'answers':[]}
    with pytest.raises(ValueError,match='LLM origin'):
        build_banks([person('a')],[{'id':'a','poststratified_weight':1.}],scored,tau=8.)
    scored.update(answer_origin='llm_model_output',answers=[{'id':'audit','q8':2.}])
    with pytest.raises(ValueError,match='audit/Normal'):
        build_banks([person('a')],[{'id':'a','poststratified_weight':1.}],scored,tau=8.)


def test_one_entire_missing_field_does_not_drop_the_other_population_result():
    from studies.sce_inflation_expectations.experiments.core_normal_expansion import build_banks
    rows=[person('a'),person('n')];selected=[{'id':'a','poststratified_weight':2.}]
    scored={'answer_origin':'llm_model_output','scorer_provenance':{'cached':True},
            'answers':[{'id':'a',**answer('a',2.,None).payload()}]}
    banks,support=build_banks(rows,selected,scored,tau=8.)
    assert set(banks)=={'q9'} and 'q8' in support['unsupported_banks']
    scored['answers']=[{'id':'a','q9_bins':[],'q9_mean':None,'q9_iqr':None,'q8':3.}]
    banks,support=build_banks(rows,selected,scored,tau=8.)
    assert set(banks)=={'q8'} and 'q9' in support['unsupported_banks']
