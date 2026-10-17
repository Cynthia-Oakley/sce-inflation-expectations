#!/usr/bin/env python3
"""Separate cross-month finance entry; inherit the audited no-resume runner.

The prior runner is loaded into an isolated namespace. Its worker, authorization
gate, source export, audit receipts and fail-stop dispatch remain the execution
implementation. Only the frozen-scope verifier and child-entry path are adapted.
Both runner sources must be pinned by the new preparation manifest.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
PARENT_RUNNER = ROOT / 'scripts/run_sce_household_finance_trial.py'
PROTOCOL_ID = 'sce-household-finance-crossmonth-v1'
MONTHS = (202206, 202306, 202410, 202509)
ARMS = ('baseline', 'financial_facts')
REPEATS = (1, 2)
N_PER_MONTH = 48
PLANNED_CALLS = 768

# run_path returns a copy of the globals dictionary. Adapt the function's actual
# globals so nested dispatch/worker calls use this verifier and this entry path.
_loaded = runpy.run_path(str(PARENT_RUNNER), run_name=__name__+'._inherited')
_inherited = _loaded['worker'].__globals__
_parent_verify = _inherited['verify']
sha = _inherited['sha']
dump = _inherited['dump']


def verify(folder):
    """Validate original hashes/budgets, then the exact new cross-month scope."""
    folder = Path(folder).resolve()
    manifest = _parent_verify(folder)
    protocol = json.loads((folder/'protocol.json').read_text())
    expected = {
        'id': PROTOCOL_ID, 'research_line': 'A_conditional_returner_reconstruction',
        'months': list(MONTHS), 'n_per_month': N_PER_MONTH,
        'arms': list(ARMS), 'generation_repeats': list(REPEATS),
        'planned_calls': PLANNED_CALLS, 'price_input_per_mtok': .3,
        'price_output_per_mtok': 1.2,
    }
    if any(protocol.get(key) != value for key, value in expected.items()):
        raise ValueError('Frozen cross-month protocol scope mismatch')
    if (('protocol_id' in protocol and protocol['protocol_id'] != PROTOCOL_ID)
            or ('repeats' in protocol and protocol['repeats'] != list(REPEATS))):
        raise ValueError('Cross-month protocol aliases disagree')
    if (type(protocol['n_per_month']) is not int or type(protocol['planned_calls']) is not int
            or manifest['planned_calls'] != PLANNED_CALLS
            or protocol.get('budget_cap_usd') != manifest['proposed_cap_usd']):
        raise ValueError('Frozen cross-month request/budget scope mismatch')
    cells = Counter((job['month'], job['arm'], job['repeat']) for job in manifest['jobs'])
    expected_cells = Counter((month, arm, repeat) for month in MONTHS for arm in ARMS for repeat in REPEATS)
    if cells != expected_cells or any(type(job['month']) is not int or type(job['repeat']) is not int
                                     for job in manifest['jobs']):
        raise ValueError('All 16 unique cross-month cells required')
    dependencies = {
        'scripts/run_sce_finance_validation_trial.py',
        'scripts/run_sce_household_finance_trial.py',
        'scripts/export_study_runtime.py',
    }
    if not dependencies <= set(manifest['source_sha256']):
        raise ValueError('Both runner sources and runtime exporter must be frozen')
    required = {'protocol.json'}
    for month in MONTHS:
        required.update(f'{month}/{name}' for name in (
            'population.json', 'environment.json', 'household_finance_payloads.json',
            *(f'simulation_{arm}.json' for arm in ARMS),
            *(f'preview_{arm}.json' for arm in ARMS)))
        personas = json.loads((folder/str(month)/'population.json').read_text())['personas']
        identifiers = [persona['agent_id'] for persona in personas]
        if (len(personas) != N_PER_MONTH or len(set(identifiers)) != N_PER_MONTH
                or any(not isinstance(aid, str) or not aid for aid in identifiers)):
            raise ValueError('Exactly 48 distinct personas required in every month')
    if not required <= set(manifest['prepared_file_sha256']):
        raise ValueError('All cross-month runtime inputs and previews must be frozen')
    return manifest


_inherited.update(verify=verify, __file__=str(Path(__file__).resolve()))
authorization_gate = _inherited['authorization_gate']
worker = _inherited['worker']
dispatch = _inherited['dispatch']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'dry-run', 'run', 'worker'])
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--job-index', type=int)
    parser.add_argument('--scripted', action='store_true')
    args = parser.parse_args()
    folder = args.folder.resolve()
    if args.action == 'prepare':
        from studies.sce_inflation_expectations.finance_validation_preparation import prepare
        manifest = prepare(folder)
        verify(folder)
        print('prepared', manifest['planned_calls'], 'requests; reserve',
              round(manifest['conservative_reservation_usd'], 4), 'cap', manifest['proposed_cap_usd'])
        return
    if args.action == 'worker':
        return worker(folder, args.job_index, args.scripted)
    return dispatch(folder, args.action == 'dry-run', args.workers)


if __name__ == '__main__':
    main()
