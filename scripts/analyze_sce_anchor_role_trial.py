#!/usr/bin/env python3
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.anchor_role import evaluate

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=evaluate(a.folder.resolve(),a.out)
    print('completed',r['new_api_calls'],'real calls; candidate gate',r['candidate_continue_gate_passed'])
