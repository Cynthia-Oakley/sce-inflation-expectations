import json
from pathlib import Path
import pytest
from studies.sce_inflation_expectations.experiments import automatic_pipeline as ap


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, 'ROOT', tmp_path)
    ledger = tmp_path / 'outputs/ledger'
    ledger.mkdir(parents=True)
    protocol = dict(model='test-model', route='test-route', max_workers=16,
                    new_planned_calls=20, destination='https://example.invalid', budget_cap_usd=1)
    (ledger / 'protocol.json').write_text(json.dumps(protocol))
    pin = ap.digest(ledger / 'protocol.json')
    (ledger / 'manifest.json').write_text(json.dumps(dict(protocol_sha256=pin, source_sha256={}, files_sha256={})))
    (ledger / 'authorization.json').write_text(json.dumps(dict(approved=True, protocol_sha256=pin,
        destination=protocol['destination'], cap_usd=1)))
    plan = dict(version=1, ledger='outputs/ledger', evaluation_out='outputs/evaluation',
                protocol_sha256=pin, profile='single_model', workers=8)
    return tmp_path, ledger, plan


def test_inspect_is_offline_and_requires_existing_approval(prepared, monkeypatch):
    root, ledger, plan = prepared
    monkeypatch.setattr(ap, 'dispatch', lambda *a: pytest.fail('Inspection cannot dispatch'))
    assert ap.inspect(plan)['new_api_calls'] == 0
    auth = ap.read(ledger / 'authorization.json');auth['approved'] = False
    (ledger / 'authorization.json').write_text(json.dumps(auth))
    with pytest.raises(ValueError, match='approval'):
        ap.inspect(plan)


def test_completed_dispatch_runs_evaluation_once(prepared, monkeypatch):
    root, ledger, plan = prepared
    calls = []
    monkeypatch.setattr(ap, 'dispatch', lambda *a: calls.append('dispatch') or {'status': 'completed', 'new_calls': 20})
    monkeypatch.setattr(ap, 'evaluate', lambda *a: calls.append('evaluate'))
    out = root / 'outputs/pipeline'
    assert ap.execute(plan, out)['status'] == 'completed'
    assert calls == ['dispatch', 'evaluate']
    assert ap.read(out / 'pipeline_receipt.json')['new_api_calls'] == 20
    with pytest.raises(ValueError, match='Fresh'):
        ap.execute(plan, out)
    assert calls == ['dispatch', 'evaluate']


def test_stopped_run_does_not_trigger_evaluation_or_retry(prepared, monkeypatch):
    root, ledger, plan = prepared
    calls = []
    monkeypatch.setattr(ap, 'dispatch', lambda *a: calls.append('dispatch') or {'status': 'stopped_no_retry'})
    monkeypatch.setattr(ap, 'evaluate', lambda *a: pytest.fail('Incomplete run must not be scored as complete'))
    r = ap.execute(plan, root / 'outputs/pipeline')
    assert r['status'] == 'stopped' and r['evaluation_skipped']
    assert calls == ['dispatch']


def test_evaluation_failure_preserves_paid_run_without_redispatch(prepared, monkeypatch):
    root, ledger, plan = prepared
    monkeypatch.setattr(ap, 'dispatch', lambda *a: {'status': 'completed'})
    def fail(*a):
        raise ValueError('Evaluation failed')
    monkeypatch.setattr(ap, 'evaluate', fail)
    out = root / 'outputs/pipeline'
    with pytest.raises(ValueError):ap.execute(plan, out)
    r = ap.read(out / 'pipeline_receipt.json')
    assert r['status'] == 'failed' and r['stage'] == 'evaluation'
    assert r['runtime_receipt']['status'] == 'completed'


@pytest.mark.parametrize('field,value', [('workers', 17), ('workers', True), ('protocol_sha256', 'wrong')])
def test_invalid_plan_stops_before_dispatch(prepared, field, value):
    _, _, plan = prepared
    plan[field] = value
    with pytest.raises(ValueError):ap.inspect(plan)


def test_completed_ledger_is_never_restarted(prepared):
    _, ledger, plan = prepared
    (ledger / 'execution_started.json').write_text('{}')
    with pytest.raises(ValueError, match='Never restart'):ap.inspect(plan)
