from studies.sce_inflation_expectations.evaluation.monthly_reconstruction import summarize,ARM


def row():
    return dict(month=202501,repeat=1,userid=1,survey_weight=2.,
        real=dict(q9_mean=2.,q9_iqr=1.,q9_zero_deflation=0.,q9_bins=[10.]*10,q8_point=4.,previous_q9_mean=None),
        arms={ARM:dict(mean=1.,iqr=1.,zero_deflation=0.,q9_bins=[10.]*10,point=3.)})


def test_single_arm_uses_existing_metrics_without_dummy_comparator():
    result=summarize([row()],[202501],[ARM])
    assert result['q9_person_months']==1
    metrics=result['arms'][ARM]['auxiliary_survey_weighted']
    assert metrics['q9']['center_headline_errors']['mae_pp']==1.
    assert metrics['q8']['cells'][0]['q8_center_mae_pp']==1.


def test_q8_support_survives_unscorable_q9():
    r=row();r['arms'][ARM].update(mean=None,iqr=None)
    result=summarize([r],[202501],[ARM])
    assert result['q9_person_months']==0 and result['q8_person_months']==1


def test_explicit_calibrated_weight_label_and_weighted_statistics():
    r1=row();r2=row();r2['userid']=2;r2['survey_weight']=.25
    r2['arms'][ARM]['mean']=8.;r2['real']['q9_mean']=9.
    result=summarize([r1,r2],[202501],[ARM],weight_definition='54-cell calibrated masses')
    w=result['arms'][ARM]['auxiliary_survey_weighted']
    assert w['weight_definition']=='54-cell calibrated masses'
    assert w['q9']['center_headline_errors']['mae_pp']==1.


def test_reused_score_cache_requires_matching_content_and_frozen_scorer(tmp_path):
    import json
    from studies.sce_inflation_expectations.evaluation.monthly_reconstruction import read_score_cache
    from studies.sce_inflation_expectations.experiments.frozen_batch import sha
    from studies.sce_inflation_expectations.scoring.sce_q9_frozen import provenance
    from pytest import raises
    f=tmp_path/'scoring_cache_private.json'
    f.write_text(json.dumps([dict(bins=[10.]*10,score=dict(mean=2.,iqr=1.,zero_deflation=0.))]))
    receipt=tmp_path/'cache_receipt.json'
    receipt.write_text(json.dumps(dict(cache_sha256=sha(f),scorer=provenance())))
    assert read_score_cache(tmp_path)[(10.,)*10]['mean']==2.
    f.write_text('[]')
    with raises(ValueError,match='Incompatible or changed'):read_score_cache(tmp_path)


def test_human_sampling_offset_uses_distinct_full_wave_and_selected_weights():
    from studies.sce_inflation_expectations.evaluation.monthly_reconstruction import sampling_offsets
    t=[dict(month=202501,real=dict(q9_mean=2.,q8_point=4.),survey_weight=1.)]
    f={'202501':[dict(q9_mean=2.,q8_point=4.,weight=1.),dict(q9_mean=4.,q8_point=5.,weight=2.)]}
    result=sampling_offsets(t,f)
    assert result['monthly'][0]['q9_mean']['median_offset_pp']==-2.
    assert result['median_offset_errors']['q8_point']['mae_pp']==1.


def test_sparse_flag_uses_field_valid_support_not_just_roster_size():
    from studies.sce_inflation_expectations.evaluation.monthly_reconstruction import support_by_month
    rows=[]
    for i in range(20):
        r=row();r['userid']=i;r['survey_weight']=1.
        if i:r['real']['q9_mean']=None
        rows.append(r)
    s=support_by_month(rows,[202501])[0]
    assert s['selected_n']==20 and s['weight_ess']==20
    assert s['q9_valid_n']==1 and s['q9_weight_ess']==1.
    assert s['q8_valid_n']==20 and s['descriptive_only']
