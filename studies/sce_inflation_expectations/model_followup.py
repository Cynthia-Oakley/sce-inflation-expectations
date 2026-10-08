"""Frozen model substitutions and prior-run ledger for the October 8 follow-up."""
import copy
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

MODELS = {
    'qwen/qwen-2.5-72b-instruct': ('deepinfra/fp8', .36, .40, 'DeepInfra'),
    'meta-llama/llama-3.3-70b-instruct': ('deepinfra/turbo', .10, .32, 'DeepInfra'),
    'meta-llama/llama-3.1-8b-instruct': ('deepinfra/fp8', .02, .04, 'DeepInfra'),
    'qwen/qwen-2.5-7b-instruct': ('phala', .10, .20, 'Phala'),
}
DEFAULT_MODELS = list(MODELS)[:3]


def followup_rows(original, models):
    """Retain exact forty case messages; modify only model and fixed route/price."""
    if not models or len(models) != len(set(models)) or any(m not in MODELS for m in models):
        raise ValueError('unsupported_or_duplicate_models')
    source = [r for r in original if r['payload']['model'] == 'qwen/qwen-2.5-72b-instruct']
    if len(source) != 40 or len({r['case_id'] for r in source}) != 40:
        raise ValueError('need_forty_unique_frozen_cases')
    rows = []
    for model in models:
        route, pin, pout, provider = MODELS[model]
        for base in source:
            row = copy.deepcopy(base)
            row['payload']['model'] = model
            row['payload']['provider']['order'] = [route]
            row.update(route_candidate=route, input_price_per_million=pin,
                       output_price_per_million=pout)
            rows.append(row)
    return rows


def prior_ledger(summary, calls):
    """Never reset the earlier spend or permit duplicate successful cases."""
    if summary['status'] == 'running' or len(calls) != summary['paid_attempts']:
        raise ValueError('prior_run_not_final_or_log_incomplete')
    costs = [c['billing']['charged_or_reserved_usd'] for c in calls]
    if any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 for x in costs):
        raise ValueError('invalid_prior_cost')
    prior_cost = summary.get('prior_cost_usd', 0.)
    if type(prior_cost) not in (int, float) or not math.isfinite(prior_cost) or prior_cost < 0:
        raise ValueError('invalid_carry_forward_cost')
    spent = prior_cost + sum(costs)
    if abs(spent - summary['total_charged_or_reserved_usd']) > 1e-10:
        raise ValueError('prior_summary_log_cost_mismatch')
    successes = {(c['case_id'], c['requested_model']) for c in calls
                 if not c.get('error') and 'answer' in c}
    if len(successes) != summary['valid_answers']:
        raise ValueError('prior_success_count_mismatch')
    per_model = Counter()
    for call, cost in zip(calls, costs):
        per_model[call['requested_model']] += cost
    # Follow-up summaries already carry earlier costs for each selected model.
    for model, record in summary.get('models', {}).items():
        recorded = record['charged_or_reserved_usd']
        if type(recorded) not in (int, float) or not math.isfinite(recorded) or recorded < per_model[model] - 1e-10:
            raise ValueError('invalid_per_model_carry_forward_cost')
        per_model[model] = recorded
    return spent, dict(per_model), successes


def ancestor_successes(summary, root):
    """Validate the frozen parent chain and retain successes across every resume."""
    result = set()
    visited = set()
    for _ in range(16):
        hashes = summary.get('prior_run_hashes', {})
        if not hashes:
            return result
        parent = None
        for name, expected in hashes.items():
            path = Path(name)
            if not path.is_absolute(): path = root / path
            path = path.resolve()
            if not path.is_relative_to((root / 'outputs').resolve()):
                raise ValueError('parent_path_outside_outputs')
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('parent_hash_changed')
            if path.name == 'run_summary.json':
                if path in visited: raise ValueError('cyclic_parent_chain')
                visited.add(path)
                parent = json.loads(path.read_text())
            elif path.name == 'llm_calls.jsonl':
                for line in path.read_text().splitlines():
                    call = json.loads(line)
                    if not call.get('error') and 'answer' in call:
                        result.add((call['case_id'], call['requested_model']))
            else:
                raise ValueError('unrecognized_parent_artifact')
        if parent is None: raise ValueError('missing_parent_summary')
        summary = parent
    raise ValueError('parent_chain_too_deep')


MODEL_LABELS = {
    'meta-llama/llama-3.1-70b-instruct': 'llama',
    'qwen/qwen-2.5-72b-instruct': 'qwen',
    'meta-llama/llama-3.3-70b-instruct': 'llama_3_3_70b',
    'meta-llama/llama-3.1-8b-instruct': 'llama_3_1_8b',
    'qwen/qwen-2.5-7b-instruct': 'qwen_2_5_7b',
}
