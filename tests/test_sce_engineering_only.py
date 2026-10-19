"""No-live-call contract, not tests of scripted behavioral accuracy."""
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.frozen_batch import verify,authorize,dump,sha


def package(folder, **overrides):
    p={'execution_mode':'engineering_only','mechanism':'procurement_price_engineering',
       'months':[202009],'arms':['shared_price'],'generation_repeats':[1], 'n_per_month':2,
       'model':'NOT_CONFIGURED_ENGINEERING_ONLY','destination':None,'temperature':.5,
       'budget_cap_usd':0.,'price_input_per_mtok':0.,'price_output_per_mtok':0.,'max_tokens':1024,
       'thinking':'disabled','retry_max':0,'planned_calls':0,'engineering_decision_count':2,**overrides}
    dump(folder/'protocol.json',p)
    m={'source_sha256':{},'prepared_file_sha256':{},'planned_calls':p['planned_calls'],
       'protocol_sha256':sha(folder/'protocol.json'),
       'jobs':[{'month':202009,'arm':'shared_price','repeat':1,'run_id':'unit-test-only','cap_usd':0}]}
    dump(folder/'manifest.json',m)
    return m,p


def test_zero_spend_only_when_explicit_engineering_mode(tmp_path):
    package(tmp_path); verify(tmp_path)
    package(tmp_path,execution_mode='live')
    with pytest.raises(ValueError,match='Invalid model'):
        verify(tmp_path)


@pytest.mark.parametrize('changed',[
    {'model':'gpt-4o-mini'},{'destination':'https://example.invalid'},
    {'budget_cap_usd':1.},{'price_output_per_mtok':.1},
    {'planned_calls':2},{'engineering_decision_count':99},
])
def test_engineering_scope_cannot_turn_into_live_or_fake_counts(tmp_path,changed):
    package(tmp_path,**changed)
    with pytest.raises(ValueError):verify(tmp_path)


def test_forged_authorization_cannot_make_engineering_package_paid(tmp_path):
    manifest,protocol=package(tmp_path)
    dump(tmp_path/'authorization.json',{'approved':True,'user_confirmation':'forged test fixture'})
    with pytest.raises(ValueError,match='cannot run paid'):
        authorize(tmp_path,manifest,protocol)


def test_engineering_package_cannot_score_against_truth(tmp_path):
    from studies.sce_inflation_expectations.evaluation.frozen_trial import evaluate
    package(tmp_path)
    with pytest.raises(ValueError,match='no truth read'):
        evaluate(tmp_path, ROOT/'outputs/never_created_engineering_test_evaluation')


def test_legacy_paid_protocol_keeps_positive_budget_contract(tmp_path):
    manifest,p=package(tmp_path,execution_mode='live',model='legacy-model',
        destination='https://example.invalid',budget_cap_usd=1.,planned_calls=2)
    manifest['jobs'][0]['cap_usd']=.5
    dump(tmp_path/'manifest.json',manifest)
    verify(tmp_path)
    manifest['jobs'][0]['cap_usd']=0.
    dump(tmp_path/'manifest.json',manifest)
    with pytest.raises(ValueError,match='Finite job caps'):
        verify(tmp_path)
