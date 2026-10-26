"""One launch for an authorized ledger and its registered local evaluation.

No prompt building, authorization creation, retries, provider switches or
statistical calculations live here. Interrupted dispatch is never restarted.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROFILES = {'single_model', 'same_input_comparison', 'post2025_validation', 'news_matching'}


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    with Path(path).open('x') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')


def inspect(plan):
    """Local checks only; an approval already attached to the ledger is required."""
    if plan.get('version') != 1 or plan.get('profile') not in PROFILES:
        raise ValueError('Registered pipeline version/profile required')
    ledger = (ROOT / plan['ledger']).resolve()
    evaluation = (ROOT / plan['evaluation_out']).resolve()
    if not ledger.is_relative_to(ROOT / 'outputs') or not evaluation.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Private ledger and evaluation must stay in outputs')
    if evaluation.exists() or evaluation.with_name(evaluation.name + '_new_model_scores').exists():
        raise ValueError('Fresh evaluation and score-cache paths required')
    if (ledger / 'execution_started.json').exists() or (ledger / 'run_receipt.json').exists():
        raise ValueError('Never restart an attempted or finished ledger')
    p = read(ledger / 'protocol.json')
    m = read(ledger / 'manifest.json')
    a = read(ledger / 'authorization.json')
    pin = digest(ledger / 'protocol.json')
    workers = plan['workers']
    if (plan['protocol_sha256'] != pin or m['protocol_sha256'] != pin
            or not a.get('approved') or a['protocol_sha256'] != pin
            or a['destination'] != p['destination'] or a['cap_usd'] != p['budget_cap_usd']
            or type(workers) is not int or not 1 <= workers <= p.get('max_workers', 16)):
        raise ValueError('Existing scope/budget approval and registered concurrency required')
    for field in ('source_sha256', 'files_sha256'):
        for name, expected in m[field].items():
            path = (ROOT / name).resolve() if field == 'source_sha256' else (ledger / name).resolve()
            boundary = ROOT if field == 'source_sha256' else ledger
            if not path.is_relative_to(boundary) or digest(path) != expected:
                raise ValueError('Frozen source/input mismatch: ' + name)
    if plan['profile'] == 'same_input_comparison':
        if (p.get('mechanism') not in ('v32_same_input', 'v32_same_input_siliconflow')
                or len(p['months']) != 4 or p['n_per_month'] != 96):
            raise ValueError('Archived comparison evaluator only supports its frozen four-month design')
    if plan['profile'] == 'post2025_validation' and (p.get('mechanism') != 'v32_new2025_validation'
            or p['months'] != [202504,202506,202508,202510] or p['n_per_month'] != 192):
        raise ValueError('Registered later-2025 evaluation scope required')
    if plan['profile'] == 'news_matching' and p.get('mechanism') != 'v32_news_matching':
        raise ValueError('Registered news-matching evaluator required')
    if p.get('truth_scope') == 'aggregate_only':
        raise ValueError('Aggregate-only evaluation adapter must be registered before paid dispatch')
    report = plan.get('public_report_out')
    if report:
        report = (ROOT / report).resolve()
        if (plan['profile'] != 'same_input_comparison' or report.exists()
                or not report.is_relative_to(ROOT / 'docs/workstreams')):
            raise ValueError('Fresh supported public report path required')
    return dict(ledger=str(ledger), evaluation_out=str(evaluation),
                public_report_out=str(report) if report else None,
                planned_calls=p['new_planned_calls'], cap_usd=p['budget_cap_usd'],
                model=p['model'], route=p['route'], workers=workers,
                new_api_calls=0, profile=plan['profile'])


def dispatch(ledger, workers):
    from .pending_call_ledger import run
    return run(Path(ledger), workers)


def evaluate(profile, ledger, out):
    if profile == 'news_matching':
        from scripts.evaluate_sce_news_matching import evaluate as evaluator
    elif profile == 'post2025_validation':
        from scripts.evaluate_sce_post2025_validation import evaluate as evaluator
    elif profile == 'same_input_comparison':
        from scripts.evaluate_sce_model_comparison import evaluate as evaluator
    else:
        from scripts.evaluate_sce_call_ledger import evaluate as evaluator
    return evaluator(Path(ledger), Path(out))


def publish(evaluation, ledger, out):
    from scripts.report_sce_model_comparison import publish as publisher
    return publisher(Path(evaluation), Path(ledger), Path(out))


def execute(plan, out):
    info = inspect(plan)
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh private pipeline receipt directory required')
    for other in (Path(info['ledger']), Path(info['evaluation_out'])):
        if out == other or out in other.parents or other in out.parents:
            raise ValueError('Pipeline receipts, ledger and evaluation must use disjoint directories')
    out.mkdir(parents=True)
    write_new(out / 'plan.json', plan)
    receipt = dict(status='running', stage='dispatch', started_at=datetime.now(timezone.utc).isoformat(),
                   **info, automatic_retries=0, automatic_restart=False)
    receipt.update(new_api_calls=None, implementation_sha256=digest(__file__))
    write_new(out / 'execution_started.json', receipt)
    try:
        runtime = dispatch(info['ledger'], info['workers'])
        receipt['runtime_receipt'] = runtime
        receipt['new_api_calls'] = runtime.get('new_calls')
        if runtime['status'] != 'completed':
            receipt.update(status='stopped', stage='dispatch', evaluation_skipped=True)
        else:
            receipt['stage'] = 'evaluation'
            evaluate(plan['profile'], info['ledger'], info['evaluation_out'])
            if info['public_report_out']:
                receipt['stage'] = 'report'
                publish(info['evaluation_out'], info['ledger'], info['public_report_out'])
            receipt.update(status='completed', stage='finished', evaluation_skipped=False)
    except Exception as exc:
        # Do not copy remote exception text: the dispatch ledger owns redacted details.
        receipt.update(status='failed', error_type=type(exc).__name__, automatic_restart=False)
        raise
    finally:
        receipt['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_new(out / 'pipeline_receipt.json', receipt)
    return receipt
