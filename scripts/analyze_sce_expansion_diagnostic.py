"""Offline entry point; fresh output folder required."""
from pathlib import Path
import argparse
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.evaluation.expansion_diagnostic import run

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    result=run(ROOT,args.out if args.out.is_absolute() else ROOT/args.out)
    print(f"Completed: {result['months']} returner months; {result['unique_people']} saved U1 people; new API calls=0")
