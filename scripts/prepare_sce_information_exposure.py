#!/usr/bin/env python3
"""Prepare six-month news/statistics view inventory; cannot start paid calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT/'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments.information_exposure import prepare

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = prepare(args.out)
    print(json.dumps({'status': result['status'], 'totals': result['totals'],
        'months': {m: {'news': v['eligible_personal_articles_after_exact_dedup'], 'n': v['selected_n']} for m, v in result['inventory'].items()},
        'seconds': result['seconds'], 'new_api_calls': 0}, ensure_ascii=False))
