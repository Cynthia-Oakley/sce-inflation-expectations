from copy import deepcopy
import json
import numpy as np
import pytest

from studies.sce_inflation_expectations.experiments import recent_b_sampled_dates as mod
from studies.sce_inflation_expectations.state_continuity_runtime import render_messages,STATE_TOKEN,TIMING_TOKEN


def test_later_synthetic_interview_cannot_move_global_cutoff():
    p=np.zeros(30);p[19]=1
    row=mod.assign_date('202511','fixture',p,'2025-11-13T23:59:59-05:00')
    assert row['synthetic_completion_day']=='2025-11-20'
    assert row['information_cutoff']=='2025-11-13T23:59:59-05:00' and row['capped_by_global_as_of']


def test_first_day_uses_previous_month_end_and_assignment_is_identity_stable():
    p=np.zeros(30);p[0]=1
    assert mod.assign_date('202511','fixture',p,'2025-11-13T23:59:59-05:00')['information_cutoff']=='2025-10-31T23:59:59-04:00'
    p=np.ones(30)/30
    a=mod.assign_date('202511','first',p,'2025-11-13T23:59:59-05:00')
    mod.assign_date('202511','another',p,'2025-11-13T23:59:59-05:00')
    assert a==mod.assign_date('202511','first',p,'2025-11-13T23:59:59-05:00')


def test_year_lag_is_explicit_and_unavailable_source_rejected():
    distributions={'202411':(np.ones(30)/30).tolist(),'202311':(np.ones(30)/30).tolist()}
    assert mod.source_probability(distributions,202511,'202501',12)[0]=='202411'
    assert mod.source_probability(distributions,202511,'202501',24)[0]=='202311'
    with pytest.raises(ValueError,match='not available'):
        mod.source_probability(distributions,202511,'202410',12)


def test_archive_repair_is_an_overlay_and_partial_archive_blocks(tmp_path,monkeypatch):
    monkeypatch.setattr(mod,'ROOT',tmp_path)
    old=tmp_path/'original.json';old.write_text(json.dumps({'response':{'docs':[{'pub_date':f'2026-01-{d:02}T12:00:00Z'} for d in range(1,8)]}}))
    fixed=tmp_path/'new.json';fixed.write_text(json.dumps({'response':{'docs':[{'pub_date':f'2026-01-{d:02}T12:00:00Z'} for d in range(1,32)]}}))
    oldbytes=old.read_bytes();sources={}
    result=mod.archive_screen('2026-01',13,{'2026-01':old},sources)
    assert result['unobserved_required_days']==[8,9,10,11,12,13]
    assert mod.archive_screen('2026-01',31,{'2026-01':fixed},sources)['screen_passed']
    assert old.read_bytes()==oldbytes


def test_template_roundtrip_keeps_questionnaire_and_prior_bytes():
    state=dict(fields={'q8':dict(value=3.,source_period=202510,source_kind='synthetic_donor'),
       'q9':dict(value=[10.]*10,source_period=202510,source_kind='synthetic_donor')},
       history_centers=[],comparison_reference_day='2025-10-31',comparison_day_source='synthetic_prior_reference_month_end')
    context=dict(as_of='2025-11-04T23:59:59-05:00',common_news=[dict(pub_date='2025-10-20T12:00:00Z')],
      personal_news=[],food_published_at='2025-10-24T08:30:00-04:00',policy_published_at='2025-10-29T14:00:00-04:00')
    original=[dict(role='user',content='Persona and environment.\n\n'+TIMING_TOKEN+'\n\n'+STATE_TOKEN+'Exact questionnaire suffix.')]
    preview=render_messages(original,state,'202511',context)
    template=mod.template_from_rendered(preview,state,'202511',context)
    assert render_messages(template,state,'202511',context)==preview
    assert template[0]['content'].endswith('Exact questionnaire suffix.')
    same_day={**context,'as_of':'2025-10-31T23:59:59-04:00'}
    prior_copy=deepcopy(state)
    equal=mod.render_B_messages(original,state,'202511',same_day)
    assert state==prior_copy and mod.template_from_rendered(equal,state,'202511',same_day)==original
    with pytest.raises(ValueError,match='only for declared synthetic'):
        mod.render_B_messages(original,{**state,'comparison_day_source':'own_observed_survey_day'},'202511',same_day)


def test_overlay_does_not_silently_change_existing_classification():
    with pytest.raises(ValueError,match='relabel'):
        mod.merge_labels({'same':{'decision':'keep'}},{'same':{'decision':'reject'}})
    assert mod.merge_labels({'same':{'decision':'keep'}},{'new':{'decision':'keep'}})['same']=={'decision':'keep'}


def test_repair_manifest_and_archive_alias_bind_new_bytes_without_overwrite(tmp_path,monkeypatch):
    monkeypatch.setattr(mod,'ROOT',tmp_path)
    original=tmp_path/'data/raw/nyt_archive/2026-01.json';original.parent.mkdir(parents=True);original.write_text('old bytes')
    repaired=tmp_path/'repair/2026-01.json';repaired.parent.mkdir();repaired.write_text('new bytes')
    config=tmp_path/'repair/manifest.json'
    config.write_text(json.dumps(dict(schema='sce_B_news_repair_overlay/v1',
      archive_overrides={'2026-01':dict(path='repair/2026-01.json',sha256=mod.sha(repaired))},base_label_overlays=[])))
    overrides,labels=mod.load_repair(config,{})
    view,aliases=mod.archive_view(tmp_path/'new_packet',{'2026-01'},overrides)
    assert (view/'data/raw/nyt_archive/2026-01.json').read_text()=='new bytes'
    assert original.read_text()=='old bytes' and aliases['2026-01']=='repair/2026-01.json' and labels=={}
    bad=json.loads(config.read_text());bad['archive_overrides']['2026-01']['sha256']='0'*64;config.write_text(json.dumps(bad))
    with pytest.raises(ValueError,match='Pinned file changed'):mod.load_repair(config,{})
