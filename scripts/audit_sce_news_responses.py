#!/usr/bin/env python3
"""Offline audit of existing inputs/replies; does not call any API."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.news_response_diagnostic import audit

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trial',type=Path,default=ROOT/'outputs/sce_news_exposure_trial_20261011_v3')
    p.add_argument('--analysis',type=Path,default=ROOT/'outputs/sce_news_exposure_analysis_20261011_v2')
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    r=audit(ROOT,args.trial,args.analysis,args.out)
    print(f"Audited {sum(v['pooled']['n_answers'] for v in r['months'].values())} saved answers; new API calls: 0; output: {args.out}")
