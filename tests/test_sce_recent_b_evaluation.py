import hashlib,json

import pytest

from studies.sce_inflation_expectations.experiments import recent_b_evaluation as module


def write(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj))


def manifest(folder):
    write(folder/'package/manifest.json',{'protocol_sha256':hashlib.sha256((folder/'package/protocol.json').read_bytes()).hexdigest(),'source_sha256':{}})


def test_national_only_evaluation_has_known_errors_and_keeps_fixed_roster(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'ROOT',tmp_path)
    catalog=tmp_path/'catalog.json';monkeypatch.setattr(module,'CATALOG',catalog)
    monkeypatch.setattr(module,'make_figure',lambda rows,out:None)
    archive=tmp_path/'release.html';archive.write_text('Fixture published national value, not a real result')
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    write(catalog,{'headline_releases':[{'reference_period':'2025-11','value_pp':3.5,'published_date':'2025-12-08','source_file':'release.html','source_sha256':digest}]})
    folder=tmp_path/'run';write(folder/'package/protocol.json',{'planned_calls':512,'population_preflight':'population','input_templates':'prompts',
        'frozen_combination_simulation_share':0.,'months':['202511'],'research_line':'offline_test_fixture'})
    manifest(folder)
    write(folder/'combined/receipt.json',{'main_logical_positions':512})
    people=[{'persona':{'agent_id':str(i)},'analysis_weight':1.} for i in range(512)]
    write(tmp_path/'population/selected_proxy_population_private.json',{'202511':people})
    write(tmp_path/'population/monthly_input_plan.json',[{'month':'202511','as_of':'2025-11-13T23:59:59-05:00','last_public_national_anchor':{'value_pp':3.2,'reference_period':'2025-10'}}])
    prior_bins=[0.]*10;prior_bins[4]=100. # 0-2, mean 1
    model_bins=[0.]*10;model_bins[3]=100. # 2-4, mean 3
    initial={str(i):{'fields':{'q9':{'value':prior_bins}}} for i in range(512)}
    write(tmp_path/'prompts/202511/initial_states_private.json',initial)
    rows=[]
    for i in range(512):
        bins=model_bins if i else [0.]*10
        rows.append({'month':'202511','agent_id':str(i),'state_after':{'fields':{'q9':{'value':bins},'q8':{'value':4.}},
            'transition':{'field_updated_from_model':{'q8':True,'q9':bool(i)}}}})
    (folder/'combined/positions_private.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    result=module.evaluate(folder)
    assert result['model']['mae_pp']==pytest.approx(.5)
    assert result['persistence']['mae_pp']==pytest.approx(.3)
    assert result['frozen_combination']==result['persistence']
    assert result['quality']['q9_density_fallback']==1
    assert result['monthly'][0]['fixed_n']==512 and result['monthly'][0]['usable_model_q9_n']==511
    assert result['monthly'][0]['sim_q8_median_pp_descriptive_only']==4.
    assert 'w1' not in result and result['new_api_calls']==0


def test_incomplete_main_scope_cannot_be_called_full_evaluation(tmp_path):
    write(tmp_path/'package/protocol.json',{'planned_calls':5632})
    manifest(tmp_path)
    write(tmp_path/'combined/receipt.json',{'main_logical_positions':32})
    with pytest.raises(ValueError,match='Complete main scope'):module.evaluate(tmp_path)
