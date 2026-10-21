import pytest

from studies.sce_inflation_expectations.evaluation.price_background_readout import summarize


def test_repeats_do_not_inflate_people_or_effective_sample_size():
    rows=[]
    for repeat in (1,2):
        for uid,y,prior,base,treat,w in [('a',0.,0.,1.,0.,1.),('b',10.,8.,5.,8.,3.)]:
            rows.append(dict(month=202109,repeat=repeat,userid=uid,survey_weight=w,
                real=dict(q9_mean=y,previous_q9_mean=prior),
                arms=dict(food_background={'mean':base},broader_background={'mean':treat})))
    result=summarize(rows,['food_background','broader_background'],[202109],[1,2],{(202109,'a'),(202109,'b')})
    assert result['person_months']==result['unique_persons']==2
    assert result['cells_used']==2
    assert all(c['n']==2 and c['ess']==pytest.approx(1.6) for c in result['cells'])
    assert result['metrics']['food_background']['center_mae_pp']==5.
    assert result['metrics']['broader_background']['center_mae_pp']==2.
    assert result['metrics']['food_background']['center_rmse_pp']==5.
    assert result['metrics']['food_background']['w1_pp']==pytest.approx(4.)
    assert result['metrics']['broader_background']['w1_pp']==pytest.approx(1.5)
    assert result['metrics']['carry']['center_mae_pp']==2.
    assert len(result['sparse_cells'])==2
