#!/usr/bin/env python3
"""Run zero-API official Core checks through the existing frozen-prompt worker."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent / 'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT / 'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments.state_continuity_core import check

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preparation', type=Path, default=ROOT / 'outputs/sce_state_continuity_preparation_20261022_v1')
    p.add_argument('--prompts', type=Path, default=ROOT / 'outputs/sce_state_continuity_prompts_20261022_v3')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); print(json.dumps(check(a.preparation, a.prompts, a.out), ensure_ascii=False, indent=2))
