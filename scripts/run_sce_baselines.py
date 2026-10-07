#!/usr/bin/env python3
"""Run the frozen offline benchmark protocol and retain per-month predictions."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'studies/sce_inflation_expectations'))
from evaluation.benchmark import (
    forecast_benchmarks, reconstruction_benchmarks, summarize_forecasts, summarize_reconstruction,
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, default=ROOT / 'data/evaluation/sce_baselines_20261007')
    parser.add_argument('--protocol', type=Path, default=ROOT / 'studies/sce_inflation_expectations/evaluation/baseline_protocol_v1.json')
    parser.add_argument('--aggregate-file', type=Path, help='Versioned public aggregate source ledger; permits headline-only reproduction without microdata')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--headlines-only', action='store_true')
    args = parser.parse_args()
    for name in ('inputs', 'protocol', 'aggregate_file', 'output_dir'):
        if getattr(args, name) is not None:
            setattr(args, name, getattr(args, name).resolve())
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    dest = args.output_dir or ROOT / 'outputs' / f'sce_baselines_{stamp}_{uuid.uuid4().hex[:8]}'
    dest.mkdir(parents=True, exist_ok=False)
    protocol = json.loads(args.protocol.read_text())
    aggregate_path = args.aggregate_file or args.inputs / 'aggregate_inputs.json'
    aggregate = json.loads(aggregate_path.read_text())
    if aggregate['protocol_id'] != protocol['protocol_id']:
        raise ValueError('Input/protocol identity mismatch')
    source_paths = [Path(__file__), args.protocol,
        ROOT / 'scripts/build_sce_baseline_inputs.py', ROOT / 'scripts/prepare_sce_baseline_sources.py',
        ROOT / 'scripts/evaluate_sce_outputs.py',
        *(ROOT / 'scripts').glob('extend_sce_baseline_inputs.py'),
        *(ROOT / 'studies/sce_inflation_expectations/evaluation').glob('*.py')]
    code_hashes = {str(p.relative_to(ROOT)): sha(p) for p in source_paths}
    manifest = dict(run_id=dest.name, started_at=datetime.now(timezone.utc).isoformat(),
                    git_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    dirty_paths=subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True).splitlines(),
                    protocol_sha256=sha(args.protocol), code_hashes=code_hashes,
                    aggregate_input_sha256=sha(aggregate_path),
                    real_llm_calls=0, paid_mcp_calls=0,
                    historical_evidence='official SCE first-released rounded headlines; archived CPI original-release pages',
                    limitation='retrospectively downloaded official archives; not contemporaneously saved web snapshots')
    write_json(dest / 'run_manifest.json', manifest)
    write_json(dest / 'protocol.json', protocol)
    predictions, skipped = forecast_benchmarks(aggregate, protocol)
    forecasts = summarize_forecasts(predictions, protocol)
    with (dest / 'monthly_forecasts.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(predictions[0]))
        writer.writeheader()
        for row in predictions:
            row = dict(row, parameters=json.dumps(row['parameters'], sort_keys=True))
            writer.writerow(row)
    write_json(dest / 'coverage_exclusions.json', skipped)
    reconstruction = []
    if not args.headlines_only:
        import pandas as pd
        micro_path = args.inputs / 'micro_reference.parquet'
        metadata = json.loads((args.inputs / 'micro_reference_sources.json').read_text())
        if sha(micro_path) != metadata['cache_sha256']:
            raise ValueError('Micro cache hash mismatch')
        micro = pd.read_parquet(micro_path)
        distribution_rows, diagnostics = reconstruction_benchmarks(micro, protocol)
        reconstruction = summarize_reconstruction(distribution_rows)
        write_json(dest / 'monthly_reconstruction.json', distribution_rows)
        write_json(dest / 'reconstruction_coverage.json', diagnostics)
        manifest['micro_input_sha256'] = sha(micro_path)
        manifest['micro_source_hashes'] = metadata['sources']
    summary = dict(protocol_id=protocol['protocol_id'], evaluation_window=[protocol['evaluation_start'], protocol['evaluation_end']],
                   forecasts=forecasts, reconstruction=reconstruction, excluded_macro_forecasts=len(skipped),
                   interpretation='retrospective baseline characterization over declared coverage; not blind validation of an Agent mechanism',
                   forecast_signal_note='Public past SCE headlines are allowed to baselines; current LLM E omitted them, so comparisons do not isolate method alone',
                   reconstruction_note='A-line latest micro snapshots; official derived means, not an exact Q9 fitting replication')
    write_json(dest / 'summary.json', summary)
    manifest.update(finished_at=datetime.now(timezone.utc).isoformat(), status='complete',
                    output_hashes={p.name: sha(p) for p in sorted(dest.iterdir()) if p.name != 'run_manifest.json'})
    write_json(dest / 'run_manifest.json', manifest)
    print(dest)
    print(json.dumps([{'policy': r['policy'], 'method': r['method'], **r['primary']} for r in forecasts], indent=2))


if __name__ == '__main__':
    main()
