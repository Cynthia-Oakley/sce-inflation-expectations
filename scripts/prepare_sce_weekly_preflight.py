"""Prepare a fixed weekly roster and audit full weekly inputs; no API calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent / 'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT / 'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments.weekly_preflight import prepare


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--n', type=int, default=300)
    args = parser.parse_args()
    result = prepare(args.out, args.n)
    print(json.dumps({k: v for k, v in result.items() if k != 'roster'}, ensure_ascii=False, indent=2))
