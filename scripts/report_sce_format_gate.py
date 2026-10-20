#!/usr/bin/env python3
"""Audit an executed staged format gate; no truth reads, model calls or repairs."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT/'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments.frozen_batch import verify, read_json, dump, sha
from studies.sce_inflation_expectations.experiments.staged_rosters import technical_gate
from studies.sce_inflation_expectations.model import validate_sce_bins


def report(folder, out):
    folder, out = folder.resolve(), out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output required')
    manifest, protocol = verify(folder)
    gate = technical_gate(folder, manifest, protocol, ROOT)
    if read_json(folder/'technical_gate.json') != gate:
        raise ValueError('Original technical-gate receipt differs')
    counts = Counter(); errors = Counter(); sums = Counter(); by_arm = defaultdict(Counter)
    times = []; returned = set(); providers = set(); details = []; fee = estimate = 0.
    response_hashes = {}; evidence = {}
    for job in manifest['jobs']:
        audit = ROOT/'outputs/local_runs'/job['run_id']
        if job['phase'] != 'gate':
            if audit.exists(): counts['main_units_started'] += 1
            continue
        receipt_file = audit/'run_manifest.json'; calls_file = audit/'llm_calls.jsonl'
        receipt = read_json(receipt_file); evidence[str(receipt_file.relative_to(ROOT))] = sha(receipt_file)
        evidence[str(calls_file.relative_to(ROOT))] = sha(calls_file)
        times.append((receipt['started_at_utc'], receipt['finished_at_utc']))
        estimate += receipt['cost']['estimated_cost_usd']
        counts['completed_gate_units'] += receipt['status'] == 'completed'
        for line in calls_file.read_text().splitlines():
            call = json.loads(line); arm = job['arm']; counts['requests'] += 1; by_arm[arm]['requests'] += 1
            counts['model_interface_errors'] += bool(call.get('error'))
            counts['automatic_model_retries'] += call['attempt_idx'] > 0
            usage = call.get('usage') or {}
            counts['prompt_tokens'] += usage.get('prompt_tokens') or 0
            counts['completion_tokens'] += usage.get('completion_tokens') or 0
            returned.add(call.get('returned_model')); providers.add(call.get('returned_provider'))
            charge = call.get('api_reported_cost_usd')
            if charge is not None:
                fee += charge; counts['reported_cost_calls'] += 1
            raw = call.get('raw_response_text') or ''
            if hashlib.sha256(raw.encode()).hexdigest() != call['raw_response_sha256']:
                raise ValueError('Raw response hash mismatch')
            key = f'{job["run_id"]}|{call["agent_id"]}'
            if key in response_hashes: raise ValueError('Duplicate paid request record')
            response_hashes[key] = call['raw_response_sha256']
            reason = None; bins = None
            try:
                obj = json.loads(raw); counts['json_objects'] += isinstance(obj, dict)
                q9 = obj['q9']; bins = [q9[f'bin{i}'] for i in range(1, 11)]
                shape = isinstance(q9, dict) and set(q9) == {f'bin{i}' for i in range(1, 11)}
                numeric = all(type(v) in (float, int) and math.isfinite(v) for v in bins)
                point = obj['point_pct']; point_ok = type(point) in (float, int) and math.isfinite(point)
                counts['strict_nested_ten_bin_shape'] += shape
                counts['ten_finite_numeric_probabilities'] += numeric
                counts['finite_numeric_q8'] += point_ok
                counts['normal_stop'] += call['finish_reason'] == 'stop'
                ok, error, total = validate_sce_bins(bins) if numeric else (False, 'nonnumeric', None)
                sums[str(total)] += 1
                reason = ('bad_shape' if not shape else 'nonnumeric' if not numeric else
                          'bad_q8' if not point_ok else 'incomplete_finish' if call['finish_reason'] != 'stop'
                          else error if not ok else None)
            except (KeyError, ValueError, TypeError):
                reason = 'unreadable_json_or_fields'
            if reason:
                errors[reason] += 1; by_arm[arm]['invalid'] += 1
                details.append({'run_id': job['run_id'], 'agent_id': call['agent_id'],
                                'reason': reason, 'raw_bins': bins})
            else:
                counts['strict_valid'] += 1; by_arm[arm]['valid'] += 1
    if counts['requests'] != gate['calls'] or counts['strict_valid'] != gate['valid']:
        raise ValueError('Independent format count differs from original gate')
    if not gate['passed'] and counts['main_units_started']:
        raise ValueError('Failed gate must not expand to main')
    span = (datetime.fromisoformat(max(t[1] for t in times))-
            datetime.fromisoformat(min(t[0] for t in times))).total_seconds()
    result = {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'technical_gate_passed' if gate['passed'] else 'technical_gate_failed_no_main_expansion',
        'protocol_sha256': manifest['protocol_sha256'], 'model': protocol['model'], 'route': protocol['route'],
        'months': protocol['technical_gate']['months'], 'n_per_month': protocol['technical_gate']['n_per_month'],
        'arms': protocol['arms'], 'generation_repeats': protocol['generation_repeats'],
        'counts': dict(counts), 'gate': gate, 'by_arm_format_only': dict(by_arm),
        'format_error_counts': dict(errors), 'probability_sum_counts': dict(sums),
        'returned_models': sorted(returned), 'returned_providers': sorted(providers),
        'api_reported_cost_usd': fee, 'token_based_estimated_or_reserved_cost_usd': estimate,
        'batch_cap_usd': protocol['budget_cap_usd'], 'model_api_span_seconds': span,
        'public_catalog_get_failures': 1 if (folder/'unused_gate_continuation_v1.json').exists() else 0,
        'completed_responses_reused_without_resending': 36 if (folder/'unused_gate_continuation_v1.json').exists() else 0,
        'new_api_calls_by_this_report': 0, 'probability_repair_or_normalization': False,
        'fit_metrics': None, 'reference_configuration_upgraded': False,
        'notes': ['Technical gate only; no current human truth read or fitting evaluated.',
            'Invalid original probabilities preserved. Costs are API-reported, not an account invoice.',
            'Both passing and failing replies are retained; these tiny group counts do not identify a mechanism effect.'],
        'report_source_sha256': sha(Path(__file__))}
    out.mkdir(); dump(out/'summary.json', result); dump(out/'invalid_replies_private.json', details)
    dump(out/'evidence_manifest.json', {'source_sha256': evidence, 'response_sha256_private': response_hashes})
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); print(json.dumps(report(a.folder, a.out), ensure_ascii=False, indent=2))
