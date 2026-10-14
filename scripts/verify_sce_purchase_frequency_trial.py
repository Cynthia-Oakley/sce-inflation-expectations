#!/usr/bin/env python3
"""Focused saved-run verification: actual inputs/parameters/cost and SciPy metrics."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from scipy.stats import wasserstein_distance

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_sce_purchase_frequency_trial import verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--evaluation', type=Path, required=True)
    args = parser.parse_args()
    folder = args.folder.resolve(); evaluation = args.evaluation.resolve()
    output = evaluation / 'focused_receipt.json'
    if output.exists():
        raise ValueError('receipt exists; do not overwrite')
    m = verify(folder)
    summary = json.loads((evaluation / 'summary.json').read_text())
    cases = [r for r in json.loads((evaluation / 'cases_private.json').read_text()) if r['common']]
    calls = 0; ledger_cost = 0.0; errors = 0; requested = set(); returned = set(); fingerprints = set()
    for job in m['jobs']:
        run = ROOT / 'outputs/local_runs' / job['run_id']
        metadata = json.loads((run / 'run_manifest.json').read_text())
        previews = {r['agent_id']: r['messages'] for r in json.loads((folder / str(job['month']) / f"preview_{job['arm']}.json").read_text())}
        rows = [json.loads(s) for s in (run / 'llm_calls.jsonl').read_text().splitlines()]
        if len(rows) != 48 or len({r['agent_id'] for r in rows}) != 48:
            raise ValueError('call coverage differs')
        expected_cost = 0.0
        for row in rows:
            text = json.dumps(previews[row['agent_id']], ensure_ascii=False)
            assert text == row['prompt_text']
            assert row['prompt_sha256'] == hashlib.sha256(text.encode()).hexdigest()
            assert row['temperature'] == .5 and row['max_tokens'] == 1024 and row['attempt_idx'] == 0
            assert row['extra_body'] == {'thinking': {'type': 'disabled'}}
            assert 'Do not mechanically treat a past price change' not in text
            if row.get('raw_response_text') is not None:
                assert hashlib.sha256(row['raw_response_text'].encode()).hexdigest() == row['raw_response_sha256']
            usage = row.get('usage') or {}
            expected_cost += ((usage.get('prompt_tokens') or 0) * .3 + (usage.get('completion_tokens') or 0) * 1.2) / 1e6
            calls += 1; errors += bool(row.get('error'))
            requested.add(row['requested_model']); returned.add(row.get('returned_model')); fingerprints.add(row.get('system_fingerprint'))
        assert abs(expected_cost - metadata['cost']['estimated_cost_usd']) <= .000001
        assert expected_cost <= job['cap_usd']
        ledger_cost += metadata['cost']['estimated_cost_usd']
    assert calls == 768 and ledger_cost <= m['proposed_cap_usd']
    assert abs(ledger_cost - summary['new_cost_estimate_usd']) < 1e-10
    checks = []; maxdiff = 0.0
    def median(values):
        values = np.sort(values)
        return values[max(0, math.ceil(len(values) / 2) - 1)]  # left-inverse empirical CDF
    for arm, result in summary['results'].items():
        key = 'reused_C' if arm == 'reused_C_context' else arm
        for cell in result['cells']:
            rows = [r for r in cases if r['month'] == cell['month'] and r['repeat'] == cell['repeat']]
            pred = np.array([r[key] for r in rows]); actual = np.array([r['actual'] for r in rows]); prior = np.array([r['previous'] for r in rows])
            independent = {'sample_center_mae_pp': abs(median(pred) - median(actual)),
                           'cross_section_w1_pp': wasserstein_distance(pred, actual),
                           'delta_w1_pp': wasserstein_distance(pred-prior, actual-prior)}
            difference = max(abs(independent[k] - cell[k]) for k in independent)
            maxdiff = max(maxdiff, difference); assert difference < 1e-10
            checks.append({'arm': arm, 'month': cell['month'], 'repeat': cell['repeat'], 'max_metric_difference': difference})
    protected = json.loads((ROOT / 'docs/sources/sol_handoff_protected_files_20261010.json').read_text())['files_sha256']
    assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest for name, digest in protected.items())
    receipt = {'status': 'passed_focused_actual_run_checks', 'api_calls': calls, 'connection_errors': errors,
               'extra_api_calls_for_verification': 0, 'actual_inputs_and_parameters_match': True,
               'user_removed_instruction_absent': True, 'raw_response_hashes_match': True,
               'ledger_cost_matches': True, 'estimated_peak_token_cost_usd': ledger_cost,
               'cost_is_provider_bill': False, 'requested_models': sorted(requested),
               'returned_models': sorted(returned, key=str), 'system_fingerprints': sorted(fingerprints, key=str),
               'independent_scipy_metric_max_difference': maxdiff, 'checked_cells': checks,
               'protected_files_unchanged': len(protected)}
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ['checked_cells', 'system_fingerprints']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
