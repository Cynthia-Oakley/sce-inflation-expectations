"""Build the weekly offline P/E and calibration package; no model API."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent / 'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT/'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments.weekly_inputs import prepare

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preflight', type=Path, default=ROOT/'outputs/sce_weekly_preflight_20261026_v2')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--skip-core', action='store_true', help='Engineering draft only; cannot authorize a run')
    a = p.parse_args()
    result = prepare(a.preflight, a.out, official_core=not a.skip_core)
    print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'}, ensure_ascii=False, indent=2))
