#!/usr/bin/env python3
"""Freeze the development weight, or evaluate held-out months offline."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.evaluation.expanded_state import select_weight,evaluate

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['select','evaluate']);p.add_argument('--folder',type=Path,required=True);p.add_argument('--out',type=Path)
    a=p.parse_args()
    if a.action=='select':select_weight(a.folder.resolve())
    else:
        if a.out is None:p.error('--out required')
        s=evaluate(a.folder.resolve(),a.out);print('Evaluation complete; alpha',s['alpha'],'gate',s['predefined_success_gate_passed'])

if __name__=='__main__':main()
