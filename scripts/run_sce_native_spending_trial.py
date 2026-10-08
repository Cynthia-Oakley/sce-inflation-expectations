#!/usr/bin/env python3
"""Prepare, then explicitly execute the isolated native SCE basket trial."""
import argparse
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.native_spending_trial import prepare,execute

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--approval-note',help='Actual human approval for real spending send and $1 cap; do not infer from prior synthetic-basket approval')
    args=p.parse_args()
    if args.execute:execute(ROOT,ROOT/args.out,args.approval_note)
    else:prepare(ROOT,ROOT/args.out)
