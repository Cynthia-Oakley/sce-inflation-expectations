#!/usr/bin/env python3
"""Isolated current truth and cached evaluation for independent monthly Core."""
from pathlib import Path
import sys,argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.evaluation.monthly_reconstruction import prepare_truth,evaluate
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    a=s.add_parser('prepare-truth');a.add_argument('--package',type=Path,required=True);a.add_argument('--out',type=Path,required=True)
    a.add_argument('--score-cache',type=Path,help='Verified compatible prior truth folder; fit only missing vectors')
    a=s.add_parser('evaluate');a.add_argument('--package',type=Path,required=True);a.add_argument('--calls',type=Path,required=True)
    a.add_argument('--truth',type=Path,required=True);a.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if args.command=='prepare-truth': print(prepare_truth(args.package,args.out,score_cache=args.score_cache))
    else: print(evaluate(args.package,args.calls,args.truth,args.out))
