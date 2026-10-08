from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from socioverse.schemas import Observation
from studies.sce_inflation_expectations.native_spending import (
    SCHEMA,PROMPT_VERSION,validate_bundle,build_messages,NativeSpendingDecision)
from studies.sce_inflation_expectations.spending_audit import CATEGORIES
from studies.sce_inflation_expectations.price_experience import profile_hash
from studies.sce_inflation_expectations.model import build_sce_messages_v2


def fixture():
    profile={'age_group':'40 to 60','numeracy':'low','region':'South'}
    row={'agent_id':'a','profile_sha256':profile_hash(profile),'basket_month':'2021-04',
         'shares_pct':dict(zip(CATEGORIES,[30,10,20,5,10,5,5,5,10]))}
    b={'schema_version':SCHEMA,'research_line':'A_historical_reconstruction','target_month':'2021-05',
       'arm':'actual','rows':{'a':row},'source_sha256':'example'}
    p=SimpleNamespace(agent_id='a',attributes=profile)
    ob=Observation(agent_id='a',step=1,local_physical={'profile':profile,'prior_answer':{'point_pct':99}},
                   macro_information={'target_month':'2021-05','as_of':'2021-05-12T23:59:59-04:00','signals':[],'events':[]})
    return b,p,ob


def test_explicit_whitelist_time_and_identity_gates():
    b,p,ob=fixture();validate_bundle(b,[p],'2021-05')
    for kind in ['target','future','sum','identity','B','extra']:
        x=deepcopy(b)
        if kind=='target':x['rows']['a']['Q9_mean']=5
        elif kind=='future':x['rows']['a']['basket_month']='2021-05'
        elif kind=='sum':x['rows']['a']['shares_pct']['other']=11
        elif kind=='identity':x['rows']['a']['profile_sha256']='bad'
        elif kind=='B':x['research_line']='B_future_prediction'
        else:x['rows']['a']['shares_pct']['gasoline']=5
        with pytest.raises(ValueError):validate_bundle(x,[p],'2021-05')


def test_questionnaire_and_shared_E_unchanged_no_last_answer_or_ID():
    b,p,ob=fixture();base=build_sce_messages_v2(ob,include_event_abstracts=True)
    m=build_messages(ob,b)
    marker='Question 1 (point estimate):'
    assert m[0]['content'].split(marker,1)[1]==base[0]['content'].split(marker,1)[1]
    before=base[0]['content'].split(marker,1)[0]
    assert m[0]['content'].startswith(before)
    assert '20% of total expenditure' in m[0]['content']
    assert 'point_pct": 99' not in m[0]['content']
    b['arm']='withheld';w=build_messages(ob,b)
    assert '20% of total expenditure' not in w[0]['content']
    assert 'breakdown is not provided' in w[0]['content']


def test_native_decision_uses_audited_common_call_path():
    b,p,ob=fixture()
    d=NativeSpendingDecision(native_spending_bundle=b,llm_kind='openai',model='fake',max_calls=1,
                             retry_max=0,prompt_version=PROMPT_VERSION)
    called=[]
    d._call_with_audit=lambda ob,target,messages,attempt: (called.append(messages) or
        {'raw_response_text':json.dumps({'point_pct':3,'q9':{f'bin{i}':100 if i==5 else 0 for i in range(1,11)}}),
         'error':None,'finish_reason':'stop','returned_model':'fake','usage':{},'system_fingerprint':None,
         'request_id':'r','timestamp_utc':'now','prompt_sha256':'h','raw_response_sha256':'h','latency_ms':0})
    action=d._decide_openai_one(ob)
    assert called==[build_messages(ob,b)]
    assert action.payload['native_spending_arm']=='actual'
    assert action.payload['validation_status']=='valid'


def test_distribution_match_alone_does_not_validate_micro_matching():
    from studies.sce_inflation_expectations.native_spending_analysis import paired_metrics
    rows=[{'real':float(i),'withheld':0.,'actual':float(i),'shuffled':float(3-i),'food_stratum':i} for i in range(4)]
    x=paired_metrics(rows)
    assert x['arms']['actual']['distribution_W1_pp']==0
    assert x['arms']['shuffled']['distribution_W1_pp']==0
    assert x['arms']['shuffled']['individual_MAE_auxiliary_pp']==2
    assert x['arms']['shuffled']['food_gap_absolute_error_pp']==6


def test_no_approval_stops_before_credentials_or_network(tmp_path):
    from studies.sce_inflation_expectations.native_spending_trial import execute
    (tmp_path/'trial_manifest.json').write_text(json.dumps({'status':'prepared_not_run'}))
    with pytest.raises(ValueError,match='Explicit real-QSP5'):
        execute(tmp_path,tmp_path)
