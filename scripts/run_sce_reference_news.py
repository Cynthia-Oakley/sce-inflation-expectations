#!/usr/bin/env python3
"""Budget-bound dispatch of frozen public news, no automatic retry or resume."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(folder):
    folder = Path(folder).resolve()
    if not folder.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Ignored prepared folder required')
    manifest = json.loads((folder / 'manifest.json').read_text())
    if (manifest['articles'] != 4316 or manifest['batches'] != 540 or manifest['proposed_cap_usd'] != 3.
            or sum(p['cap_usd'] for p in manifest['parts']) != 3.):
        raise ValueError('Frozen article count or budget differs')
    for name, digest in manifest['source_sha256'].items():
        p = (ROOT / name).resolve()
        if not p.is_relative_to(ROOT) or sha(p) != digest:
            raise ValueError('News source changed: ' + name)
    for part in manifest['parts']:
        p = (ROOT / part['folder']).resolve()
        if not p.is_relative_to(folder) or part['cap_usd'] != .25:
            raise ValueError('Unexpected part location/budget')
        if sha(p / 'summary.json') != part['summary_sha256'] or sha(p / 'requests_prepared.jsonl') != part['requests_sha256']:
            raise ValueError('Prepared part changed')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['dry-run', 'run'])
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    folder = args.folder.resolve()
    m = verify(folder)
    if not 1 <= args.workers <= 4:
        raise ValueError('workers must be1..4')
    parent = (ROOT / m['run_parent']).resolve()
    if not parent.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Ignored run parent required')
    if args.action == 'run':
        auth = json.loads((folder / 'authorization.json').read_text())
        expected = {'approved':True,'articles':4316,'batches':540,'cap_usd':3.,
                    'manifest_sha256':sha(folder/'manifest.json'),'runner_sha256':sha(__file__)}
        if any(auth.get(k) != v for k,v in expected.items()):
            raise ValueError('Exact current scope/budget authorization required')
        if any((parent / Path(p['folder']).name).exists() for p in m['parts']):
            raise ValueError('Already dispatched output exists; preserve, no auto resume')
        parent.mkdir(parents=True, exist_ok=True)

    def one(part):
        name = Path(part['folder']).name
        cmd = [sys.executable,'-B','-m','studies.sce_inflation_expectations.expanded_news_quote_adapter',
               '--inputs',str(ROOT/part['folder']),'--out',str(parent/name)]
        if args.action == 'run':
            cmd += ['--execute','--authorization-note',
                    'Explicit user approval:4316 public NYT articles/540 batches, total$3, '
                    'this disjoint part$0.25, no retries; no population or SCE answers.']
        log = folder / (name + ('-offline' if args.action == 'dry-run' else '-real') + '.log')
        with log.open('x') as handle:
            code = subprocess.run(cmd,cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT).returncode
        # The label tool deliberately writes failures to state.json and may
        # return exit zero. A successful process is not sufficient evidence.
        if args.action == 'run' and code == 0:
            state_path = parent/name/'state.json'
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            if state.get('status') != 'completed' or state.get('articles_valid') != part['articles']:
                code = 1
        print(name, 'completed' if code == 0 else 'stopped', flush=True)
        return {'part':name,'exit_code':code,'articles':part['articles'],'batches':part['batches']}

    results, next_index, failed = [], 0, False
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        active = {}
        while next_index < len(m['parts']) and len(active) < args.workers:
            active[pool.submit(one,m['parts'][next_index])] = next_index
            next_index += 1
        while active:
            done, _ = wait(active,return_when=FIRST_COMPLETED)
            for future in done:
                active.pop(future)
                row = future.result()
                results.append(row)
                failed |= bool(row['exit_code'])
            (folder / ('engineering_checks.json' if args.action == 'dry-run' else 'real_dispatch.json')).write_text(
                json.dumps(results,indent=2)+'\n')
            while not failed and next_index < len(m['parts']) and len(active) < args.workers:
                active[pool.submit(one,m['parts'][next_index])] = next_index
                next_index += 1
    if failed:
        raise RuntimeError('A part stopped; preserve partial outputs without automatic retry')


if __name__ == '__main__':
    main()
