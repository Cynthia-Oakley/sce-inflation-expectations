#!/usr/bin/env python3
"""Prepare and execute an explicitly scoped B-repair slim-label batch."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import label_sce_news_pool as labels

ROOT = Path(__file__).resolve().parents[1]
VARIANT = 'recent_b_repair'


def register(out, manifest, budget_cap):
    labels.VARIANTS[VARIANT] = {
        'out': out,
        'prompt': labels.SYSTEM_PROMPT_V21,
        'prompt_file': 'system_prompt_v21.md',
        'groups': ['full'],
        'budget_cap': budget_cap,
        'cons_dir': 'consistency',
        'engine': 'deepseek_official',
        'manifest': manifest,
        'purpose': 'Versioned B public-news repair: incremental slim4 labels only; no simulation',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'execute'])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--budget-cap', type=float, default=0.30)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--confirm-deepseek-flash', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    manifest = args.manifest.resolve()
    register(out, manifest, args.budget_cap)
    if args.command == 'prepare':
        result = labels.prepare(out, variant=VARIANT)
        receipt = {
            'wrapper': str(Path(__file__).relative_to(ROOT)),
            'wrapper_sha256': labels.sha(Path(__file__)),
            'registered_variant': VARIANT,
            'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'user_authorized_model': 'DeepSeek Flash for required repair labels',
            'simulation_calls': 0,
        }
        (out / 'wrapper_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if not args.confirm_deepseek_flash:
        raise ValueError('Explicit --confirm-deepseek-flash required for paid labeling')
    authorization = {
        'approved': True,
        'protocol_sha256': labels.sha(out / 'protocol.json'),
        'user_confirmation': '2026-10-26 user authorized DeepSeek v4.1 Flash if repair labeling is needed',
        'scope': 'Only the frozen pending_public_news manifest; no simulation and no mechanism labels',
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
    }
    (out / 'authorization.json').write_text(json.dumps(authorization, ensure_ascii=False, indent=2) + '\n')
    labels.execute(out, workers=args.workers)
    labels.write_manifest(out)


if __name__ == '__main__':
    main()
