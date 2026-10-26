from scripts.analyze_sce_post2025_support import analyze


def test_scalar_fallback_uses_prior_and_keeps_original_missing_reply():
    cases=[]
    for i,(now,previous) in enumerate([(3.,1.),(10.,10.)]):
        for repeat in (1,2):
            cases.append(dict(month=202504,userid=i,agent_id=str(i),repeat=repeat,survey_weight=1.,
                real=dict(q9_mean=now,q9_iqr=1.,q9_zero_deflation=1.,q9_bins=[0.]*9+[100.],previous_q9_mean=previous),
                arms={'model':dict(mean=None if i==0 and repeat==2 else now,
                    iqr=1.,zero_deflation=1.,q9_bins=[0.]*9+[100.])}))
    result=analyze(cases,'model',[202504])
    assert result['fallback_slots']==1
    assert result['fixed_human_valid_roster_with_scalar_prior_fallback']['person_months']==2
    assert result['fixed_human_valid_roster_with_scalar_prior_fallback']['metrics']['model']['center_mae_pp']==1.
    assert cases[1]['arms']['model']['mean'] is None
    assert result['generated_replies_fabricated']==0
