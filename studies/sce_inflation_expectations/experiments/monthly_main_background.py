"""Local detached supervision; no agent SDK, inference, retries or changed science.

Preparation and status are offline. Only start of an exactly authorized package
can launch the existing pipeline. Run from the user's native Terminal so app
lifecycle/sandbox cleanup is not part of overnight process ownership.
"""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from .frozen_batch import ROOT, OFFICIAL, read_json, sha
from .monthly_main_pipeline import plan

KEYS = ('package', 'calls', 'truth', 'evaluation', 'registry', 'readout')
SELF = ROOT / 'scripts/manage_sce_monthly_main.py'
PIPELINE = ROOT / 'scripts/run_sce_monthly_main_pipeline.py'


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


def prepare(out, **paths):
    paths = {k: str(Path(paths[k]).resolve()) for k in KEYS}
    review = plan(**paths)
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh private supervisor folder required')
    if any(out == Path(v) or out in Path(v).parents or Path(v) in out.parents for v in paths.values()):
        raise ValueError('Supervisor must be separate from frozen inputs and stage outputs')
    out.mkdir(parents=True, mode=0o700)
    config = dict(paths=paths, python=sys.executable, protocol_sha256=review['protocol_sha256'],
                  supervisor_source_sha256=sha(Path(__file__)), entry_sha256=sha(SELF),
                  pipeline_source_sha256=sha(PIPELINE), prepared_at_utc=now(),
                  planned_calls=review['planned_calls'], budget_cap_usd=review['budget_cap_usd'])
    atomic_json(out / 'config.json', config)
    return dict(status='supervisor_prepared_not_started', run_dir=str(out),
                authorization_file_exists=review['authorization_file_exists'], new_api_calls=0)


def verified_config(folder):
    config = read_json(folder / 'config.json')
    for file, key in ((Path(__file__), 'supervisor_source_sha256'), (SELF, 'entry_sha256'),
                      (PIPELINE, 'pipeline_source_sha256')):
        if sha(file) != config[key]:
            raise ValueError('Prepared launcher source changed; prepare a new supervisor')
    review = plan(**config['paths'])
    if review['protocol_sha256'] != config['protocol_sha256']:
        raise ValueError('Prepared protocol changed')
    package = Path(config['paths']['package'])
    protocol = read_json(package / 'protocol.json')
    auth = read_json(package / 'authorization.json')
    if not auth.get('approved') or auth.get('protocol_sha256') != config['protocol_sha256']:
        raise ValueError('Exact existing human authorization required')
    for key in ('planned_calls', 'budget_cap_usd', 'destination', 'model', 'route'):
        if auth.get(key) != protocol[key]:
            raise ValueError('Authorization scope mismatch: ' + key)
    if (package / 'execution_registration.json').exists():
        raise ValueError('Attempted package cannot be restarted')
    return config


def pipeline_command(config, folder):
    command = [config['python'], '-u', str(PIPELINE)]
    for key in KEYS:
        command += ['--' + key, config['paths'][key]]
    return command + ['--execute', '--out', str(folder / 'pipeline')]


def current_phase(paths):
    if (Path(paths['readout']) / 'summary.json').exists():
        return 'aggregate_readout_written'
    if (Path(paths['evaluation']) / 'summary.json').exists():
        return 'macro_readout'
    receipt = Path(paths['calls']) / 'receipt.json'
    if receipt.exists():
        return 'micro_evaluation' if read_json(receipt)['status'] == 'completed' else 'generation_stopped'
    return 'generation_or_initial_validation'


def start(folder):
    folder = Path(folder).resolve()
    config = verified_config(folder)
    from ..news_label_trial import dotenv_values
    if not (os.environ.get('OPENROUTER_API_KEY') or dotenv_values(OFFICIAL / '.env').get('OPENROUTER_API_KEY')):
        raise ValueError('OpenRouter credential unavailable; never put it in command arguments')
    # Exclusive lock persists on failure: no automatic or accidental relaunch.
    with (folder / 'launch_lock.json').open('x') as stream:
        json.dump(dict(at_utc=now(), automatic_restart=False), stream)
        stream.flush(); os.fsync(stream.fileno())
    with (folder / 'supervisor.log').open('x') as log:
        child = subprocess.Popen([config['python'], '-u', str(SELF), '_worker', '--run-dir', str(folder)],
                                 cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True, close_fds=True)
    atomic_json(folder / 'launch.json', dict(pid=child.pid, launched_at_utc=now()))
    return dict(status='launched_check_status_for_real_progress', pid=child.pid, run_dir=str(folder))


class Progress:
    """Incremental read of complete ledger lines; discard no crash-tail bytes."""
    def __init__(self, calls):
        self.calls = Path(calls)
        self.offsets = {}
        self.dispatched = self.completed = self.errors = self.usable = self.unknown_fees = 0
        self.dispatched_bound = self.completed_bound = self.reported = self.unknown_bound = 0.
        self.months = {}

    def lines(self, name):
        path = self.calls / name
        if not path.exists():
            return
        with path.open('rb') as stream:
            stream.seek(self.offsets.get(name, 0))
            while True:
                row_start = stream.tell()
                line = stream.readline()
                if not line or not line.endswith(b'\n'):
                    self.offsets[name] = row_start
                    break
                row = json.loads(line)
                self.offsets[name] = stream.tell()
                yield row

    def poll(self):
        for row in self.lines('dispatch_private.jsonl'):
            self.dispatched += 1
            self.dispatched_bound += row['reserved_usd']
        for row in self.lines('calls_private.jsonl'):
            self.completed += 1
            self.completed_bound += row['request_reservation_usd']
            self.errors += bool(row.get('error'))
            self.usable += bool(row.get('technical_usable'))
            month = str(row['month'])
            self.months[month] = self.months.get(month, 0) + 1
            fee = row.get('api_reported_cost_usd')
            if type(fee) in (int, float) and math.isfinite(fee) and fee >= 0:
                self.reported += fee
            else:
                self.unknown_fees += 1
                self.unknown_bound += row['request_reservation_usd']
        return dict(dispatched=self.dispatched, completed=self.completed, errors=self.errors,
                    technically_usable=self.usable, api_reported_cost_usd=self.reported,
                    unknown_fee_count=self.unknown_fees, unknown_fee_reservation_usd=self.unknown_bound,
                    dispatched_without_local_result=self.dispatched - self.completed,
                    outstanding_reservation_usd=max(0., self.dispatched_bound - self.completed_bound),
                    completed_by_month=self.months)


def worker(folder):
    folder = Path(folder).resolve()
    if not (folder / 'launch_lock.json').exists():
        raise ValueError('Use start; worker is not a separate bypass')
    with (folder / 'worker_lock.json').open('x') as stream:
        json.dump(dict(pid=os.getpid(), started_at_utc=now()), stream)
    wake = None
    started = time.monotonic()
    progress = None
    try:
        config = verified_config(folder)
        # Prevent idle system sleep while this worker lives. Does not prevent
        # lid-close sleep, shutdown, network loss or power failure.
        if sys.platform == 'darwin' and Path('/usr/bin/caffeinate').exists():
            wake = subprocess.Popen(['/usr/bin/caffeinate', '-i', '-w', str(os.getpid())],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        progress = Progress(config['paths']['calls'])
        with (folder / 'pipeline.log').open('x') as log:
            child = subprocess.Popen(pipeline_command(config, folder), cwd=ROOT, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, close_fds=True)
            while True:
                exit_code = child.poll()
                # Observability errors must not strand a paid child process.
                try:
                    current = progress.poll()
                    current.update(at_utc=now(), worker_pid=os.getpid(), pipeline_pid=child.pid,
                                   elapsed_seconds=time.monotonic() - started,
                                   phase=current_phase(config['paths']),
                                   planned_calls=config['planned_calls'], budget_cap_usd=config['budget_cap_usd'],
                                   never_dispatched=max(0, config['planned_calls'] - progress.dispatched))
                    atomic_json(folder / 'progress.json', current)
                except Exception as exc:
                    print('Progress read unavailable: ' + type(exc).__name__, flush=True)
                if exit_code is not None:
                    break
                time.sleep(10)
        receipt = folder / 'pipeline/receipt.json'
        pipeline_status = read_json(receipt)['status'] if receipt.exists() else 'no_pipeline_receipt'
        result = dict(status=pipeline_status, exit_code=exit_code, ended_at_utc=now(),
                      automatic_restarts=0, automatic_retries_added=0)
        atomic_json(folder / 'worker_receipt.json', result)
        return result
    except Exception as exc:
        # Exceptions can contain data/credentials: persist only their class.
        atomic_json(folder / 'worker_receipt.json', dict(status='supervisor_failed_no_restart',
                    error_type=type(exc).__name__, ended_at_utc=now()))
        raise
    finally:
        if wake is not None:
            wake.terminate(); wake.wait()


def status(folder):
    folder = Path(folder).resolve()
    config = read_json(folder / 'config.json')
    result = dict(run_dir=str(folder), planned_calls=config['planned_calls'],
                  budget_cap_usd=config['budget_cap_usd'], new_api_calls=0,
                  status='prepared_not_started')
    if (folder / 'launch_lock.json').exists():
        result['status'] = 'launch_requested_completion_not_confirmed'
    if (folder / 'progress.json').exists():
        result['progress'] = read_json(folder / 'progress.json')
        stamp = datetime.fromisoformat(result['progress']['at_utc'])
        result['progress_age_seconds'] = (datetime.now(timezone.utc) - stamp).total_seconds()
        if result['progress_age_seconds'] > 60:
            result['notice'] = 'Heartbeat older than 60s; inspect locally. Do not relaunch an attempted package.'
    if (folder / 'worker_receipt.json').exists():
        result['receipt'] = read_json(folder / 'worker_receipt.json')
        result['status'] = result['receipt']['status']
    # No PID-only "running" claim: PID reuse/abrupt host termination is possible.
    return result
