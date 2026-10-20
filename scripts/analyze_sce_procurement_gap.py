#!/usr/bin/env python3
"""Conditional DeepSeek/Qwen diagnostics from existing scores only."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT/'studies'), *studies.__path__]
from studies.sce_inflation_expectations.evaluation.procurement_gap import run

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); r = run(a.out)
    for key in ('six_month_configuration_comparison', 'three_month_same_prompt_model_comparison'):
        print(key, r[key]['common_person_months'],
              {arm: v['center_mae_pp'] for arm, v in r[key]['total']['metrics'].items()})
