import pytest
import hashlib
import json
from studies.sce_inflation_expectations.annual_model_comparison import (
    repair_messages, guarded_annual_payload, validated_answer, prior_annual_calls,
)


def test_probability_feedback_preserves_economic_point_and_original_messages():
    messages = [{'role': 'user', 'content': 'fixed P and historical E'}]
    raw = '{"point_pct":3.5,"q9":{' + ','.join(f'"bin{i}":{9 if i==10 else 10}' for i in range(1,11)) + '}}'
    revised, point = repair_messages(messages, raw)
    assert point == 3.5 and len(revised) == 3
    assert revised[0] == messages[0] and revised[1]['content'] == raw
    assert '99' in revised[2]['content'] and 'exactly 3.5' in revised[2]['content']
    assert len(messages) == 1


def test_feedback_does_not_invent_probabilities_or_repair_nonnumeric_reply():
    original = [{'role': 'user', 'content': 'fixed'}]
    for raw in ['not JSON', '{"point_pct":3,"q9":{"bin1":100}}', '{"point_pct":true,"q9":{}}']:
        result, point = repair_messages(original, raw)
        assert result == original and point is None


def test_destination_and_provider_are_locked():
    row = {'destination': 'https://openrouter.ai/api/v1', 'route_candidate': 'deepinfra/fp8',
        'payload': {'model': 'qwen/qwen-2.5-72b-instruct', 'messages': [], 'temperature': .5,
            'max_tokens': 1024, 'response_format': {'type': 'json_object'},
            'provider': {'order': ['deepinfra/fp8'], 'allow_fallbacks': False, 'require_parameters': True}}}
    assert guarded_annual_payload(row) == row['payload']
    row['payload']['provider']['allow_fallbacks'] = True
    with pytest.raises(ValueError):
        guarded_annual_payload(row)
    row['destination'] = 'https://other.example/v1'
    with pytest.raises(ValueError):
        guarded_annual_payload(row)


def test_reply_needs_100_probability_and_cannot_change_point_on_repair():
    raw = '{"point_pct":3.5,"q9":{' + ','.join(f'"bin{i}":10' for i in range(1,11)) + '}}'
    answer, error = validated_answer(raw)
    assert error is None and sum(answer['bins']) == 100
    assert validated_answer(raw, 4)[1] == 'format_repair_changed_point_estimate'
    assert validated_answer(raw.replace('"bin10":10', '"bin10":9'))[1] == 'q9_sum_99.0'
    assert validated_answer(raw.replace('3.5', 'NaN'))[1] == 'nonfinite_point'


def test_resume_keeps_error_costs_and_excludes_completed_cases():
    calls = [{'requested_model': 'a', 'case_id': 'one', 'answer': {}, 'billing': {'charged_or_reserved_usd': .1}},
        {'requested_model': 'a', 'case_id': 'two', 'error': 'q9_sum_99', 'billing': {'charged_or_reserved_usd': .02}}]
    spent, done, attempts, costs, last = prior_annual_calls(calls, {'spent_or_reserved_usd': .12})
    assert spent == pytest.approx(.12) and done == {('a', 'one')}
    assert attempts[('a', 'two')] == 1 and costs['a'] == pytest.approx(.12)
    with pytest.raises(ValueError):
        prior_annual_calls(calls, {'spent_or_reserved_usd': 0})


def test_mocked_runner_repairs_99_percent_then_stops_and_reserves_http429(tmp_path, monkeypatch):
    import scripts.run_sce_annual_model_comparison as runner
    models = ['deepseek-flash', 'qwen/qwen-2.5-72b-instruct',
        'meta-llama/llama-3.1-70b-instruct', 'meta-llama/llama-3.3-70b-instruct']
    inputs = tmp_path / 'inputs'; inputs.mkdir()
    request_path = inputs / 'requests_prepared.jsonl'
    with request_path.open('w') as f:
        for model in models:
            for month in range(202101, 202113):
                for i in range(300):
                    route = 'deepinfra/fp8' if model.startswith('qwen/') else 'deepinfra/turbo'
                    payload = {'model': model, 'messages': [{'role': 'user', 'content': 'fixed historical P E; reply JSON'}],
                        'temperature': .5, 'max_tokens': 1024, 'response_format': {'type': 'json_object'}}
                    destination = 'https://openrouter.ai/api/v1'
                    if model == 'deepseek-flash':
                        payload['thinking'] = {'type': 'disabled'}; destination = 'https://api.deepseek.com/v1'; route = None
                    else:
                        payload['provider'] = {'order': [route], 'allow_fallbacks': False, 'require_parameters': True}
                    f.write(json.dumps({'case_id': f'{month}_{i}', 'month': month, 'payload': payload, 'destination': destination,
                        'route_candidate': route, 'input_price_per_million': .1, 'output_price_per_million': .32}) + '\n')
    digest = hashlib.sha256(request_path.read_bytes()).hexdigest()
    summary = {'models': {m: {} for m in models}, 'source_sha256': {}, 'code_sha256': {},
        'requests_sha256': digest, 'prompt_version': 'sce-q8-q9-v2-abstract'}
    (inputs / 'summary.json').write_text(json.dumps(summary))
    receipt = tmp_path / 'receipt.json'
    receipt.write_text(json.dumps({'requests_sha256': digest,
        'preparation_summary_sha256': hashlib.sha256((inputs / 'summary.json').read_bytes()).hexdigest(),
        'execution_code_sha256': {}}))
    dotenv = tmp_path / '.env'; dotenv.write_text('OPENROUTER_API_KEY=mock-only-not-a-real-key\n')
    sent = []

    class Response:
        def __init__(self, status, data): self.status_code = status; self.data = data
        def json(self): return self.data
        def raise_for_status(self): assert self.status_code == 200

    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args, **kwargs):
            return Response(200, {'data': {'endpoints': [{'tag': 'deepinfra/turbo', 'status': 0,
                'supported_parameters': ['response_format', 'temperature', 'max_tokens'],
                'pricing': {'prompt': '0.0000001', 'completion': '0.00000032'}}]}})
        def post(self, url, *, headers, json):
            sent.append(json)
            if len(sent) == 3: return Response(429, {})
            total_last = 9 if len(sent) == 1 else 10
            content = '{"point_pct":3.5,"q9":{' + ','.join(f'"bin{i}":{total_last if i==10 else 10}' for i in range(1,11)) + '}}'
            return Response(200, {'model': models[-1], 'provider': 'DeepInfra',
                'choices': [{'message': {'content': content}}], 'usage': {'cost': .00001}})

    out = tmp_path / 'run'
    monkeypatch.setattr(runner.httpx, 'Client', Client)
    monkeypatch.setattr(runner.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(runner.subprocess, 'check_output', lambda *a, **k: 'mockcommit\n')
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    monkeypatch.setattr(runner.sys, 'argv', ['runner', '--inputs', str(inputs), '--receipt', str(receipt),
        '--out', str(out), '--models', models[-1], '--months', '202101', '--dotenv', str(dotenv),
        '--confirm-spend', '--authorization-note', 'MOCK TEST NO NETWORK'])
    runner.main()
    result = json.loads((out / 'run_summary.json').read_text())
    logs = [json.loads(s) for s in (out / 'llm_calls.jsonl').read_text().splitlines()]
    assert result['paid_attempts'] == 3 and result['valid_answers'] == 1
    assert logs[0]['error'] == 'q9_sum_99.0' and logs[1]['answer']['point_pct'] == 3.5
    assert len(sent[1]['messages']) == 3 and logs[2]['billing']['uncertain']
    assert result['spent_or_reserved_usd'] > .00002
    assert not (out / 'pending_request.json').exists()
