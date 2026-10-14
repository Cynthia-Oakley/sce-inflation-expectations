"""Offline candidate coverage and budgeting only; no execution option."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.evaluation.expansion_preflight import run, TARGETS

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--months',nargs=8,default=TARGETS)
    args=parser.parse_args()
    result=run(ROOT,args.out if args.out.is_absolute() else ROOT/args.out,args.months)
    print(f"Eight dates inventoried; {result['unique_pending_articles']} new public-news labels; new calls=0")
