#!/usr/bin/env python3
"""Thin entry for the isolated price-contact experiment."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.price_contact_trial import prepare,dry_run,execute

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','dry-run','run','analyze'])
    p.add_argument('--folder',required=True);p.add_argument('--approval-note',default='');a=p.parse_args()
    folder=Path(a.folder).resolve()
    if a.mode=='prepare':result=prepare(ROOT,folder);print(json.dumps({'status':result['status'],'calls':result['max_calls'],'conservative_bound':result['conservative_total_cost_bound'],'metadata':result['metadata']},ensure_ascii=False))
    elif a.mode=='dry-run':print(json.dumps(dry_run(ROOT,folder)))
    elif a.mode=='run':execute(ROOT,folder,a.approval_note)
    else:
        from studies.sce_inflation_expectations.price_contact_analysis import analyze
        analyze(ROOT,folder)

if __name__=='__main__':main()
