import json
from copy import deepcopy
from pathlib import Path

import pytest

from studies.sce_inflation_expectations.experiments.post2025_trial import source_labels, validate_config, unique_public_signals
from studies.sce_inflation_expectations.experiments.pending_call_ledger import queue_worker_limit

ROOT = Path(__file__).resolve().parents[1]


def test_new_registration_retains_scope_and_transport_lock():
    c = json.loads((ROOT/'docs/workstreams/20261021_fullperiod/new2025_validation_config.json').read_text())
    validate_config(c)
    for field, value in [('route','atlas-cloud/fp8'), ('n_per_month',96), ('temperature',1.),
            ('allocation_seed',20261022), ('technical_max_workers',16)]:
        wrong = deepcopy(c); wrong[field] = value
        with pytest.raises(ValueError):
            validate_config(wrong)


def test_news_metadata_repair_does_not_allow_reclassification(tmp_path):
    label = dict(article_id='article', decision='keep', topics=['food'], scope='US',
        claim_type='report', reason_zh='reason', evidence_snippet='verified text')
    first, second = tmp_path/'a.jsonl', tmp_path/'b.jsonl'
    first.write_text(json.dumps({'label':label})+'\n')
    repaired = dict(label, evidence_snippet='', reason_zh='other wording')
    second.write_text(json.dumps({'label':repaired})+'\n')
    assert source_labels([first,second])['article']['decision'] == 'keep'
    repaired['decision'] = 'exclude'
    second.write_text(json.dumps({'label':repaired})+'\n')
    with pytest.raises(ValueError, match='Conflicting'):
        source_labels([first,second])


def test_concurrency_ramp_changes_capacity_only_after_gate():
    p = dict(max_workers=16, technical_max_workers=8)
    assert queue_worker_limit(p,16,True) == 8
    assert queue_worker_limit(p,16,False) == 16
    assert queue_worker_limit(p,4,True) == 4
    assert queue_worker_limit(dict(max_workers=4),4,True) == 4
    with pytest.raises(ValueError):
        queue_worker_limit(dict(max_workers=16,technical_max_workers=0),16,True)


def test_delayed_observation_is_not_counted_twice_in_history():
    latest=dict(signal_id='employment_aug',role='latest_release',value=4.3,published_at='2025-09-05')
    history=dict(latest,role='history')
    signals,removed=unique_public_signals([latest,history])
    assert signals == [latest] and len(removed)==1
    with pytest.raises(ValueError,match='Conflicting'):
        unique_public_signals([latest,dict(history,value=4.4)])


def test_baselines_use_same_valid_respondents_as_model():
    from scripts.evaluate_sce_post2025_validation import same_support_baselines
    cases=[];baselines=[]
    for i,y in enumerate((1.,3.,100.)):
        real=dict(q9_mean=y,q9_iqr=1.,q9_zero_deflation=1.,q9_bins=[0.]*9+[100.])
        for repeat in (1,2):
            cases.append(dict(month=202504,userid=i,agent_id=str(i),repeat=repeat,real=real,
                arms={'model':dict(mean=y if i<2 else None,iqr=1.,zero_deflation=1.,q9_bins=[0.]*9+[100.])}))
        baselines.append(dict(month=202504,userid=i,agent_id=str(i),real=real,
            design_survey_weight=1.,carry=y if i<2 else 90.,history_anchor_half=y))
    result=same_support_baselines(cases,baselines,[dict(month=202504,official_national=dict(center_mae_pp=.1))],'model')
    assert result['common_person_months']==2
    assert result['monthly'][0]['baselines']['carry']['person_months']==2
    assert result['equal_month_metrics']['carry']['center_mae_pp']==0
