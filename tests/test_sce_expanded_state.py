"""Concrete risks: probability-mixture scoring, history isolation and frozen inputs."""
import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.evaluation.expanded_state import combine
from studies.sce_inflation_expectations.expanded_state_runtime import build_messages

def test_combination_preserves_endpoints_and_probability_mass():
    old=[0,0,0,0,100,0,0,0,0,0];signal=[100,0,0,0,0,0,0,0,0,0]
    assert combine(old,signal,0)==old and combine(old,signal,1)==signal
    mixed=combine(old,signal,.25)
    assert mixed==[25,0,0,0,75,0,0,0,0,0] and sum(mixed)==100
    with pytest.raises(ValueError):combine(old,signal,-.1)
    with pytest.raises(ValueError):combine(old,[0]*10,.5)

def test_new_signal_does_not_add_private_survey_history(monkeypatch):
    import studies.sce_inflation_expectations.expanded_state_runtime as module
    from types import SimpleNamespace
    baseline=[{'role':'user','content':'Question 1 (point estimate):\nNext 12 months.'}]
    monkeypatch.setattr(module,'baseline_messages',lambda ob,b:baseline)
    from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
    bundle={'arm':'new_signal','baseline':{},'rows':{'p':{'messages_sha256':message_hash(baseline),'prior':'THIS MUST NOT APPEAR'}}}
    assert build_messages(SimpleNamespace(agent_id='p'),bundle)==baseline
    bundle['rows']['p']['messages_sha256']='0'*64
    with pytest.raises(ValueError):build_messages(SimpleNamespace(agent_id='p'),bundle)

def test_quote_restoration_has_no_semantic_label_changes():
    import json
    from studies.sce_inflation_expectations.news_label_trial import guarded_payload
    from studies.sce_inflation_expectations.expanded_news_quote_adapter import validate
    path=ROOT/'outputs/sce_expanded_news_run_20261014_v1/part_05/response_005.json'
    if not path.exists():pytest.skip('Local real response fixture is private, not distributed')
    content=json.loads(path.read_text())['choices'][0]['message']['content']
    q=[json.loads(x) for x in (ROOT/'outputs/sce_expanded_news_prepared_20261014_v1/part_05/requests_prepared.jsonl').read_text().splitlines()][4]
    old={r['article_id']:{k:v for k,v in r.items() if k!='evidence_snippet'} for r in json.loads(content)['labels']}
    labels,repairs=validate(content,guarded_payload(q))
    new={r['article_id']:{k:v for k,v in r.items() if k!='evidence_snippet'} for r in labels}
    assert old==new and len(repairs)==1
