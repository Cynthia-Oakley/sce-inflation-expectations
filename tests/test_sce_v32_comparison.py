"""Route guards, cached support integrity and a gated continuous queue; no APIs."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from studies.sce_inflation_expectations.experiments import pending_call_ledger as ledger
from studies.sce_inflation_expectations.experiments.model_migration import validate_transport
from scripts.evaluate_sce_model_comparison import merge_cached_controls


def config():
    return dict(mechanism='v32_same_input',transport='openrouter_locked',
        destination='https://openrouter.ai/api/v1',model='deepseek/deepseek-v3.2',
        route='atlas-cloud/fp8',expected_provider='AtlasCloud',thinking='disabled',
        price_input_per_mtok=.26,price_output_per_mtok=.38,
        request_extra_body=dict(provider=dict(order=['atlas-cloud/fp8'],allow_fallbacks=False,
            require_parameters=True,max_price=dict(prompt=.26,completion=.38)),reasoning=dict(enabled=False)))


def test_v32_cannot_fallback_or_enable_reasoning():
    p=config();validate_transport(p)
    for key,value in [('model','deepseek/deepseek-r1'),('route','deepinfra/fp4'),
                      ('expected_provider','DeepInfra'),('price_output_per_mtok',.40)]:
        other=deepcopy(p);other[key]=value
        with pytest.raises(ValueError):validate_transport(other)
    for key,value in [('allow_fallbacks',True),('require_parameters',False)]:
        other=deepcopy(p);other['request_extra_body']['provider'][key]=value
        with pytest.raises(ValueError):validate_transport(other)
    other=deepcopy(p);other['request_extra_body']['reasoning']['enabled']=True
    with pytest.raises(ValueError):validate_transport(other)


def test_new_provider_requires_its_own_explicit_registration():
    p=config();p.update(mechanism='v32_same_input_siliconflow',route='siliconflow/fp8',
        expected_provider='SiliconFlow',price_input_per_mtok=.259,price_output_per_mtok=.8)
    p['request_extra_body']['provider'].update(order=['siliconflow/fp8'],max_price=dict(prompt=.259,completion=.8))
    validate_transport(p)
    old=deepcopy(p);old['mechanism']='v32_same_input'
    with pytest.raises(ValueError):validate_transport(old)


def test_cached_controls_cannot_change_person_truth_or_weight():
    rows=[dict(month=202009,repeat=rep,agent_id=str(i),real={'q9_mean':3},profile={'age_group':'mid'},
               design_survey_weight=2.,arms={'deepseek_v32':{'mean':4}}) for rep in (1,2) for i in range(96)]
    old=[dict(r,arms={'food_background':{'mean':5}}) for r in rows]
    merged=merge_cached_controls(rows,old,[202009],[1,2])
    assert len(merged)==192 and merged[0]['arms']['qwen_cached']['mean']==5
    assert 'qwen_cached' not in rows[0]['arms']
    old[0]=dict(old[0],design_survey_weight=3.)
    with pytest.raises(ValueError,match='weights'):merge_cached_controls(rows,old,[202009],[1,2])


def queue(tmp_path):
    folder=tmp_path/'ledger';folder.mkdir()
    slots=[dict(slot_key=str(i),month=202009,arm='deepseek_v32',repeat=1,agent_id=str(i),
                prompt_sha256=str(i),messages=[{'role':'user','content':str(i)}]) for i in range(4)]
    p=dict(config(),temperature=.5,max_tokens=1024,provider_metadata='directory.json',
        planned_calls=4,budget_cap_usd=.01,max_workers=4,already_spent_or_reserved_usd=0.,
        existing_attempted_calls=0,queue_technical_gate=dict(planned_calls=2,minimum_usable_fraction=.99))
    ledger.dump(tmp_path/'directory.json',{})
    ledger.dump(folder/'protocol.json',p);ledger.dump(folder/'pending_private.json',slots)
    ledger.dump(folder/'authorization.json',dict(approved=True,protocol_sha256=ledger.sha(folder/'protocol.json'),
        cap_usd=.01,destination=p['destination']))
    ledger.dump(folder/'manifest.json',dict(protocol_sha256=ledger.sha(folder/'protocol.json'),source_sha256={},
        files_sha256={'pending_private.json':ledger.sha(folder/'pending_private.json')}))
    return folder


@pytest.mark.parametrize('bad_gate',[False,True])
def test_queue_only_expands_after_normalized_format_gate(tmp_path,monkeypatch,bad_gate):
    folder=queue(tmp_path);seen=[]
    monkeypatch.setattr(ledger,'ROOT',tmp_path)
    monkeypatch.setattr(ledger,'preflight',lambda *args:None)
    monkeypatch.setattr(ledger,'dotenv_values',lambda path:{'OPENROUTER_API_KEY':'synthetic-not-secret'})
    class LLM:
        def __init__(self,**kwargs):pass
        def chat(self,messages):
            i=int(messages[0]['content']);seen.append(i)
            if i>=2:
                assert ledger.read_json(folder/'queue_technical_gate.json')['passed']
            # Sum=50 must remain usable after the user's normalization policy.
            text=json.dumps(dict(point_pct=3,q9={f'bin{k}':50 if k==8 else 0 for k in range(1,11)}))
            if bad_gate and i==0:text='{}'
            usage=SimpleNamespace(cost=.00001,model_dump=lambda:dict(cost=.00001))
            reply=SimpleNamespace(model='deepseek/deepseek-v3.2',provider='AtlasCloud',id='fake',usage=usage,
                choices=[SimpleNamespace(message=SimpleNamespace(content=text),finish_reason='stop')])
            return reply,1.
    monkeypatch.setattr(ledger,'SCEOpenAILLM',LLM)
    receipt=ledger.run(folder,workers=4)
    gate=ledger.read_json(folder/'queue_technical_gate.json')
    assert gate['passed'] is (not bad_gate)
    assert len(seen)==(2 if bad_gate else 4) and len(set(seen))==len(seen)
    assert receipt['automatic_retries']==0
    assert receipt['status']==('stopped_no_retry' if bad_gate else 'completed')
