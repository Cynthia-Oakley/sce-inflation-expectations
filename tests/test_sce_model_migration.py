from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.model_migration import validate_transport,MODEL
from studies.sce_inflation_expectations.openrouter_frozen_runtime import OpenRouterFrozenDecision
from studies.sce_inflation_expectations.frozen_prompt_runtime import PROMPT
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
from studies.sce_inflation_expectations.experiments.frozen_batch import dump,sha,authorize


def test_no_route_fallback_or_wrong_destination():
    p={'transport':'openrouter_locked','destination':'https://openrouter.ai/api/v1','model':MODEL,
       'route':'deepinfra/fp8','thinking':'disabled','price_input_per_mtok':.36,'price_output_per_mtok':.4,
       'request_extra_body':{'provider':{'order':['deepinfra/fp8'],'allow_fallbacks':False,
          'require_parameters':True,'max_price':{'prompt':.36,'completion':.4}}}}
    validate_transport(p)
    for key,value in [('destination','https://example.invalid'),('model','another-model'),('route','another-route')]:
        q=deepcopy(p);q[key]=value
        with pytest.raises(ValueError):validate_transport(q)
    q=deepcopy(p);q['request_extra_body']['provider']['allow_fallbacks']=True
    with pytest.raises(ValueError):validate_transport(q)


def test_provider_failure_retains_billable_evidence(tmp_path):
    messages=[{'role':'user','content':'Q8 Q9'}];path=tmp_path/'prompts.json'
    dump(path,{'month':202004,'arm':'qwen','rows':{'anon':{'messages':messages,'prompt_sha256':message_hash(messages)}}})
    decision=OpenRouterFrozenDecision(llm_kind='scripted',prompt_version=PROMPT,retry_max=0,
       prompts_file=str(path),prompts_sha256=sha(path),price_input_per_mtok=.36,price_output_per_mtok=.4,max_tokens=1024)
    decision.llm=SimpleNamespace(last_provider_evidence={'returned_provider':'Unapproved','api_reported_cost_usd':.00001})
    row={'error':None,'returned_model':MODEL,'prompt_text':'test'}
    decision._audit_llm_call(row)
    assert row['error'] and row['returned_provider']=='Unapproved'
    assert decision.cost_summary()['api_reported_cost_usd']==.00001


def test_openrouter_cannot_reuse_deepseek_credential(tmp_path,monkeypatch):
    from studies.sce_inflation_expectations import news_label_trial
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    monkeypatch.setenv('SV_LLM_API_KEY','not-an-openrouter-credential')
    monkeypatch.setattr(news_label_trial,'dotenv_values',lambda path:{})
    p={'transport':'openrouter_locked','budget_cap_usd':1,'planned_calls':192,'destination':'https://openrouter.ai/api/v1'}
    dump(tmp_path/'authorization.json',{'approved':True,'protocol_sha256':'hash','cap_usd':1,'planned_calls':192,
        'destination':p['destination'],'user_confirmation':'unit fixture only'})
    dump(tmp_path/'engineering_checks.json',[])
    with pytest.raises(ValueError,match='OpenRouter credential'):
        authorize(tmp_path,{'protocol_sha256':'hash','jobs':[]},p)


def test_complete_job_cannot_be_called_again(tmp_path,monkeypatch):
    from studies.sce_inflation_expectations.experiments import frozen_batch as batch
    monkeypatch.setattr(batch,'verify',lambda folder:({'jobs':[{'run_id':'done'}]},
        {'reused_completed_jobs':{'done':'old_hash'}}))
    with pytest.raises(ValueError,match='never be generated again'):
        batch.worker(tmp_path,0,True)


def test_completion_requires_matching_new_call_authorization(tmp_path):
    p={'budget_cap_usd':1,'planned_calls':192,'destination':'https://openrouter.ai/api/v1',
       'new_planned_calls':120,'reused_completed_jobs':{'done':'old_hash'}}
    dump(tmp_path/'authorization.json',{'approved':True,'protocol_sha256':'hash','cap_usd':1,
        'planned_calls':192,'destination':p['destination'],'user_confirmation':'unit fixture only'})
    with pytest.raises(ValueError,match='authorization required'):
        authorize(tmp_path,{'protocol_sha256':'hash','jobs':[]},p)
