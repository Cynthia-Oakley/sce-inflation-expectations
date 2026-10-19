"""Q8 arithmetic/independence and raw-to-parser evidence; no network calls."""
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.q8_delta_contract import convert_response, mapping_result
from studies.sce_inflation_expectations.q8_delta_runtime import Q8DeltaDecision, PROMPT
from studies.sce_inflation_expectations.frozen_prompt_runtime import FrozenPromptDecision
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash


def test_negative_revision_can_produce_negative_absolute_without_q9_change():
    obj={'point_revision_pp':-4,'q9':{'bin1':25,'bin2':75},'reason':'x'}
    r=convert_response(json.dumps(obj),'q8_delta',3)
    assert r['point_pct']==-1 and r['q9']==obj['q9'] and 'point_revision_pp' not in r


def test_missing_prior_absolute_branch_and_no_imputation():
    assert convert_response('{"point_pct":-2}','q8_delta',None)['point_pct']==-2
    with pytest.raises(ValueError):convert_response('{"point_revision_pp":2}','q8_delta',None)


@pytest.mark.parametrize('bad',['true','null','"2"','NaN','Infinity'])
def test_nonfinite_or_nonnumeric_q8_rejected(bad):
    with pytest.raises(ValueError):convert_response('{"point_revision_pp":'+bad+'}','q8_delta',2)


def test_bad_q9_does_not_erase_valid_q8_or_get_repaired():
    raw='{"point_revision_pp":-1,"q9":{"bin1":-10,"bin2":110}}'
    text,point,error=mapping_result(raw,'q8_delta',3)
    assert point==2 and error is None and json.loads(text)['q9']=={'bin1':-10,'bin2':110}
    _,point,error=mapping_result('{"point_revision_pp":-1,"q9":{"bin1":NaN}}','q8_delta',3)
    assert point==2 and error is not None


def test_wrong_representation_rejected():
    with pytest.raises(ValueError):convert_response('{"point_pct":2}','q8_delta',3)
    with pytest.raises(ValueError):convert_response('{"point_pct":2,"q9_revision_pp":{}}','direct',3)


def test_runtime_keeps_original_raw_row_and_records_mapping(tmp_path,monkeypatch):
    prior={'point_pct':3,'q9':{f'bin{i}':10 for i in range(1,11)}}
    messages=[{'role':'user','content':'Your earlier survey response\n'+json.dumps(prior)}]
    path=tmp_path/'prompts.json'
    path.write_text(json.dumps({'month':202004,'arm':'q8_delta','rows':{
        'anon':{'messages':messages,'prompt_sha256':message_hash(messages)}}}))
    dec=Q8DeltaDecision(llm_kind='scripted',prompt_version=PROMPT,retry_max=0,
        prompts_file=str(path),prompts_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),audit_dir=str(tmp_path))
    raw=json.dumps({'point_revision_pp':-4,'q9':{f'bin{i}':10 for i in range(1,11)}})
    original={'error':None,'raw_response_text':raw,'raw_response_sha256':hashlib.sha256(raw.encode()).hexdigest()}
    monkeypatch.setattr(FrozenPromptDecision,'_call_with_audit',lambda *args:original)
    reply=dec._call_with_audit(SimpleNamespace(agent_id='anon'),{},messages,0)
    assert original['raw_response_text']==raw and json.loads(reply['raw_response_text'])['point_pct']==-1
    record=json.loads((tmp_path/'response_mapping.jsonl').read_text())
    assert record['raw_response_sha256']==original['raw_response_sha256'] and record['reconstructed_q8_point']==-1


def test_point_readout_keeps_q8_when_q9_invalid_and_uses_same_prior_support():
    from studies.sce_inflation_expectations.evaluation.q8_delta import point_readout
    rows=[]
    for month in [202001,202002]:
        for repeat in [1,2]:
            for person,truth in [(1,0.),(2,2.)]:
                rows.append({'month':month,'repeat':repeat,'userid':person,'survey_weight':1.,
                    'prior_q8_point':0. if person==1 else None,'real':{'q8_point':truth},
                    'arms':{'direct':{'point':1.,'validation_status':'invalid'},
                            'q8_delta':{'point':truth,'validation_status':'invalid'}}})
    r=point_readout(rows,{'arms':['direct','q8_delta'],'months':[202001,202002],
                         'generation_repeats':[1,2]},draws=20)
    assert r['common_person_months']==4 and r['common_prior_person_months']==2
    assert r['equal_people']['q8_delta']['w1_pp']==0
    assert r['equal_people']['direct']['w1_pp']==1
    assert r['same_prior_support']['copy_previous']['personal_mae_pp']==0


def test_legacy_truth_missing_q9_keeps_q8(tmp_path):
    import pandas as pd
    from studies.sce_inflation_expectations.evaluation.q8_delta import legacy_truth
    path=tmp_path/'reference.parquet'
    pd.DataFrame([{'date':202001,'userid':1,**{f'Q9_bin{i}':None for i in range(1,11)}}]).to_parquet(path)
    rows=[{'month':202001,'userid':1,'agent_id':'a','repeat':1,'actual':None,'actual_iqr':None,
           'actual_zero_deflation':None,'actual_point':3.,'previous':4.,'previous_bins':[10.]*10}]
    r=legacy_truth(rows,path)[202001,'a',1]
    assert r['q9_bins']==[] and r['q9_mean'] is None and r['q8_point']==3.
