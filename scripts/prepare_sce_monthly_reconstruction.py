#!/usr/bin/env python3
"""Prepare independent six-cell monthly A inputs with recent donor beliefs."""
from pathlib import Path
import argparse
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT)); sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.monthly_reconstruction_inputs import prepare
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--months',nargs='+',default=['202505','202506','202507'])
    p.add_argument('--delivery',type=Path,default=ROOT/'outputs/sce_fullperiod_data_20261021_v1')
    a=p.parse_args()
    result=prepare(a.out,months=tuple(a.months),delivery=a.delivery)
    print({k:result[k] for k in ['status','person_months','recursive_dependencies','new_api_calls']})
