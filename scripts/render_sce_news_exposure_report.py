#!/usr/bin/env python3
"""Append actual aggregate results to the existing news reading HTML."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.news_exposure_reporting import render

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--analysis',type=Path,required=True)
    p.add_argument('--page',type=Path,required=True)
    p.add_argument('--prior-page',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(render(ROOT,a.analysis,a.page,a.prior_page,a.out),ensure_ascii=False))
