#!/usr/bin/env python3
"""Assemble state-ready templates and deterministic replay, with zero API calls."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent / 'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT / 'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments.state_continuity_prompts import prepare

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preparation', type=Path, default=ROOT / 'outputs/sce_state_continuity_preparation_20261022_v1')
    p.add_argument('--history', type=Path, default=ROOT / 'outputs/sce_state_continuity_history_20261022_v1')
    p.add_argument('--environments', type=Path, default=ROOT / 'outputs/sce_state_continuity_environments_20261022_v1')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--family-projection', type=Path)
    p.add_argument('--policy-supplement', type=Path)
    args = p.parse_args()
    result = prepare(args.preparation, args.history, args.environments, args.out,
                     family_projection=args.family_projection, policy_supplement=args.policy_supplement)
    print(json.dumps({k: v for k, v in result.items() if k not in ('source_sha256', 'coverage')}, ensure_ascii=False, indent=2))
