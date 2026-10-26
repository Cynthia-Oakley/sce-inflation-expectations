"""Prepare four-dimensional monthly A inputs with recent prior beliefs, no API."""
from pathlib import Path
import argparse
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.monthly_fine_inputs import prepare

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--months',nargs='+',required=True)
    args=parser.parse_args()
    r=prepare(args.out,months=args.months)
    print({k:r[k] for k in ['status','person_months','grid_version','new_api_calls']})
