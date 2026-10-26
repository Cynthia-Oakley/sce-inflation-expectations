#!/usr/bin/env python3
"""Prepare isolated truth or evaluate the small real-entry diagnostic."""
from pathlib import Path
import argparse
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.evaluation.entry_initialization_pilot import prepare_truth,evaluate

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare-truth');a.add_argument('--package',type=Path,required=True);a.add_argument('--out',type=Path,required=True)
    a=sub.add_parser('evaluate');a.add_argument('--package',type=Path,required=True);a.add_argument('--calls',type=Path,required=True)
    a.add_argument('--truth',type=Path,required=True);a.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='prepare-truth':print(prepare_truth(args.package,args.out))
    else:print(evaluate(args.package,args.calls,args.truth,args.out))
