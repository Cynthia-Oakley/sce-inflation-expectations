import json
from pathlib import Path
import subprocess
import sys

import pytest

from studies.sce_inflation_expectations.experiments import monthly_main_background as bg


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def ledger(path, *rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        for row in rows:
            stream.write(json.dumps(row) + '\n')


def configuration(tmp_path, monkeypatch):
    paths = {k: str(tmp_path / k) for k in bg.KEYS}
    for value in paths.values():
        Path(value).mkdir()
    monkeypatch.setattr(bg, 'ROOT', tmp_path)
    monkeypatch.setattr(bg, 'plan', lambda **kw: dict(protocol_sha256='abc', planned_calls=2,
                       budget_cap_usd=1., authorization_file_exists=False))
    folder = tmp_path / 'outputs/supervisor'
    bg.prepare(folder, **paths)
    protocol = dict(planned_calls=2, budget_cap_usd=1., destination='test', model='test', route='test')
    write(Path(paths['package']) / 'protocol.json', protocol)
    return folder, paths, protocol


def test_prepare_status_never_launch(tmp_path, monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError('Offline operations cannot launch a child')
    monkeypatch.setattr(bg.subprocess, 'Popen', forbidden)
    folder, _, _ = configuration(tmp_path, monkeypatch)
    assert bg.status(folder)['status'] == 'prepared_not_started'
    assert bg.status(folder)['new_api_calls'] == 0


def test_missing_and_wrong_authorization_block_start(tmp_path, monkeypatch):
    folder, paths, protocol = configuration(tmp_path, monkeypatch)
    with pytest.raises(FileNotFoundError):
        bg.start(folder)
    write(Path(paths['package']) / 'authorization.json', dict(approved=True, protocol_sha256='wrong', **protocol))
    with pytest.raises(ValueError, match='authorization'):
        bg.start(folder)
    assert not (folder / 'launch_lock.json').exists()


def test_attempted_package_is_not_restarted(tmp_path, monkeypatch):
    folder, paths, protocol = configuration(tmp_path, monkeypatch)
    write(Path(paths['package']) / 'authorization.json', dict(approved=True, protocol_sha256='abc', **protocol))
    write(Path(paths['package']) / 'execution_registration.json', {})
    with pytest.raises(ValueError, match='restarted'):
        bg.start(folder)


def test_source_or_budget_drift_blocks_start(tmp_path, monkeypatch):
    folder, paths, protocol = configuration(tmp_path, monkeypatch)
    write(Path(paths['package']) / 'authorization.json', dict(approved=True, protocol_sha256='abc',
                                                           **{**protocol, 'budget_cap_usd': 2.}))
    with pytest.raises(ValueError, match='scope mismatch'):
        bg.start(folder)
    config = bg.read_json(folder / 'config.json')
    config['entry_sha256'] = 'changed'
    write(folder / 'config.json', config)
    with pytest.raises(ValueError, match='source changed'):
        bg.start(folder)


def test_progress_incremental_partial_tail_and_unknown_cost(tmp_path):
    progress = bg.Progress(tmp_path)
    ledger(tmp_path / 'dispatch_private.jsonl', dict(reserved_usd=.1), dict(reserved_usd=.2))
    ledger(tmp_path / 'calls_private.jsonl', dict(request_reservation_usd=.1, month='201901',
           technical_usable=True, error=None, api_reported_cost_usd=.01))
    half = dict(request_reservation_usd=.2, month='201901', error='APIConnectionError',
                api_reported_cost_usd=None)
    encoded = json.dumps(half)
    with (tmp_path / 'calls_private.jsonl').open('a') as stream:
        stream.write(encoded[:20])
    first = progress.poll()
    assert first['completed'] == 1 and first['dispatched_without_local_result'] == 1
    assert first['outstanding_reservation_usd'] == pytest.approx(.2)
    assert progress.poll()['completed'] == 1
    with (tmp_path / 'calls_private.jsonl').open('a') as stream:
        stream.write(encoded[20:] + '\n')
    second = progress.poll()
    assert second['completed'] == 2 and second['errors'] == 1 and second['technically_usable'] == 1
    assert second['api_reported_cost_usd'] == .01
    assert second['unknown_fee_reservation_usd'] == .2
    assert second['outstanding_reservation_usd'] == pytest.approx(0.)
    assert second['completed_by_month'] == {'201901': 2}


def test_stopped_pipeline_is_not_reported_as_success(tmp_path):
    write(tmp_path / 'config.json', dict(planned_calls=5, budget_cap_usd=1.))
    write(tmp_path / 'worker_receipt.json', dict(status='generation_stopped_no_evaluation', exit_code=0))
    assert bg.status(tmp_path)['status'] == 'generation_stopped_no_evaluation'


def test_phase_tracks_generation_evaluation_and_readout(tmp_path):
    paths = {k: str(tmp_path / k) for k in ('calls', 'evaluation', 'readout')}
    assert bg.current_phase(paths) == 'generation_or_initial_validation'
    write(tmp_path / 'calls/receipt.json', dict(status='stopped_no_retry'))
    assert bg.current_phase(paths) == 'generation_stopped'
    write(tmp_path / 'calls/receipt.json', dict(status='completed'))
    assert bg.current_phase(paths) == 'micro_evaluation'
    write(tmp_path / 'evaluation/summary.json', {})
    assert bg.current_phase(paths) == 'macro_readout'
    write(tmp_path / 'readout/summary.json', {})
    assert bg.current_phase(paths) == 'aggregate_readout_written'


def test_worker_reuses_existing_pipeline_with_no_restart(tmp_path, monkeypatch):
    folder, paths, _ = configuration(tmp_path, monkeypatch)
    write(folder / 'launch_lock.json', {})
    monkeypatch.setattr(bg, 'verified_config', lambda f: bg.read_json(folder / 'config.json'))
    # Actual zero-network child simulates the existing pipeline's receipt only.
    code = "from pathlib import Path; p=Path({!r}); p.mkdir(); (p/'receipt.json').write_text({!r})".format(
        str(folder / 'pipeline'), json.dumps(dict(status='generation_and_separate_process_evaluation_complete')))
    monkeypatch.setattr(bg, 'pipeline_command', lambda c, f: [sys.executable, '-c', code])
    monkeypatch.setattr(bg.time, 'sleep', lambda seconds: None)
    assert bg.worker(folder)['status'] == 'generation_and_separate_process_evaluation_complete'
    assert bg.status(folder)['progress']['never_dispatched'] == 2
    with pytest.raises(FileExistsError):
        bg.worker(folder)


def test_launcher_detaches_and_excludes_secrets_from_args(tmp_path, monkeypatch):
    folder, _, _ = configuration(tmp_path, monkeypatch)
    monkeypatch.setattr(bg, 'verified_config', lambda f: bg.read_json(folder / 'config.json'))
    monkeypatch.setenv('OPENROUTER_API_KEY', 'unit-test-not-a-real-key')
    launched = []
    def fake_popen(command, **kwargs):
        launched.append((command, kwargs))
        return type('Child', (), {'pid': 123})()
    monkeypatch.setattr(bg.subprocess, 'Popen', fake_popen)
    assert bg.start(folder)['pid'] == 123
    assert launched[0][1]['start_new_session'] is True
    assert launched[0][1]['stdin'] == subprocess.DEVNULL
    assert 'unit-test-not-a-real-key' not in json.dumps(launched[0][0])
    with pytest.raises(FileExistsError):
        bg.start(folder)
    assert len(launched) == 1
