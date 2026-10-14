#!/usr/bin/env python3
"""Dispatch only never-started, frozen public-news packages under the approved cap."""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'outputs/sce_expanded_news_prepared_20261014_v1'

def main():
    manifest = json.loads((BASE / 'manifest.json').read_text())
    assert manifest['articles'] == 3555 and manifest['batches'] == 445
    assert sum(p['cap_usd'] for p in manifest['parts']) <= 2.50 + 1e-9
    parent = ROOT / manifest['run_parent']
    parent.mkdir(exist_ok=True)
    pending = [p for p in manifest['parts'] if not (parent / Path(p['folder']).name).exists()]
    def one(part):
        name = Path(part['folder']).name
        command = [sys.executable, '-B', '-m', 'studies.sce_inflation_expectations.news_label_trial',
                   '--inputs', part['folder'], '--out', str(parent / name), '--execute',
                   '--authorization-note', 'User explicitly approved frozen packages individually on 2026-10-14; '
                   '3555 public articles/445 batches total, $2.50 total cap, this disjoint part $0.25; no retries.']
        with (parent / (name + '.log')).open('x') as handle:
            code = subprocess.run(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT).returncode
        row = {'part': name, 'returncode': code}
        print(json.dumps(row), flush=True)
        return row
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, pending))
    with (parent / 'never_started_dispatch.json').open('x') as handle:
        json.dump(results, handle, indent=2)
    return int(any(r['returncode'] for r in results))

if __name__ == '__main__':
    sys.exit(main())
