#!/usr/bin/env python3
"""Add reviewed diagnostic aggregates to the existing HTML; no browser or network."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.news_response_reporting import append_report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--diagnostic',type=Path,required=True)
    p.add_argument('--prior',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    page=ROOT/'docs/literature/sce/news_selection/news_review_20261011.html'
    append_report(ROOT,a.diagnostic,page,a.prior,a.out)
    print(page)
