"""Offline tests for per-slot reuse with a different batch size and cap."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from studies.sce_inflation_expectations.experiments import pending_call_ledger as ledger


def batch(tmp_path, approved=True):
    folder = tmp_path/'ledger'; folder.mkdir()
    prompts = [{'role':'user','content':'Synthetic public-only test'}]
    slots = [dict(slot_key=str(i),month=202109,arm='food_background',repeat=1,
                  agent_id=f'synthetic-{i}',messages=prompts,prompt_sha256='test') for i in range(2)]
    protocol = dict(model='qwen/qwen-2.5-72b-instruct',temperature=.5,max_tokens=1024,
        destination='https://openrouter.ai/api/v1',request_extra_body={},route='deepinfra/fp8',
        provider_metadata='directory.json',price_input_per_mtok=.36,price_output_per_mtok=.4,
        planned_calls=2,budget_cap_usd=.01,max_workers=2,already_spent_or_reserved_usd=0.,existing_attempted_calls=0)
    ledger.dump(tmp_path/'directory.json',{})
    ledger.dump(folder/'protocol.json',protocol); ledger.dump(folder/'pending_private.json',slots)
    ledger.dump(folder/'authorization.json',dict(approved=approved,cap_usd=.01,
        destination=protocol['destination'],protocol_sha256=ledger.sha(folder/'protocol.json')))
    ledger.dump(folder/'manifest.json',dict(protocol_sha256=ledger.sha(folder/'protocol.json'),source_sha256={},
        files_sha256={'pending_private.json':ledger.sha(folder/'pending_private.json')}))
    return folder


def test_two_slot_batch_retains_an_isolated_failure_without_retry(tmp_path, monkeypatch):
    folder = batch(tmp_path); calls = []
    monkeypatch.setattr(ledger,'ROOT',tmp_path)
    monkeypatch.setattr(ledger,'preflight',lambda *args:None)
    monkeypatch.setattr(ledger,'dotenv_values',lambda path:{'OPENROUTER_API_KEY':'not-a-real-key'})
    # Name matches the existing scheduler's transient error classification.
    ConnectionError = type('APIConnectionError',(Exception,),{})

    class LLM:
        def __init__(self, **kwargs): pass
        def chat(self, messages):
            calls.append(messages)
            if len(calls) == 1:
                raise ConnectionError('offline simulated interruption')
            usage = SimpleNamespace(cost=.0001,model_dump=lambda:{'cost':.0001})
            return SimpleNamespace(model='qwen/qwen-2.5-72b-instruct',provider='DeepInfra',
                choices=[SimpleNamespace(message=SimpleNamespace(content='{}'),finish_reason='stop')],
                usage=usage,id='synthetic-id'),1.
    monkeypatch.setattr(ledger,'SCEOpenAILLM',LLM)
    result = ledger.run(folder,workers=1)
    records = [json.loads(s) for s in (folder/'new_calls_private.jsonl').read_text().splitlines()]
    assert result['status']=='completed' and result['new_calls']==2 and len(calls)==2
    assert sum(bool(r['error']) for r in records)==1
    assert result['cap_usd']==.01 and result['combined_spent_or_reserved_usd']<.01
    assert result['automatic_retries']==0
    with pytest.raises(ValueError,match='restart'):
        ledger.run(folder,workers=1)


def test_unapproved_transport_never_opens_credentials(tmp_path, monkeypatch):
    folder = batch(tmp_path,approved=False)
    def forbidden(*args):
        pytest.fail('Unapproved call tried to read credentials')
    monkeypatch.setattr(ledger,'dotenv_values',forbidden)
    with pytest.raises(ValueError,match='authorization'):
        ledger.run(folder,workers=1)


def test_changed_cap_is_rejected_before_network(tmp_path, monkeypatch):
    folder = batch(tmp_path)
    auth = ledger.read_json(folder/'authorization.json'); auth['cap_usd']=16
    ledger.dump(folder/'authorization.json',auth)
    monkeypatch.setattr(ledger,'dotenv_values',lambda path:pytest.fail('No credential reads'))
    with pytest.raises(ValueError,match='authorization'):
        ledger.run(folder,workers=1)
