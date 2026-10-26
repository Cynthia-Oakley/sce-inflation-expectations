"""Offline Core/Normal validation using existing answers; never calls a model."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.core_normal_validation import run_human

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--months',type=int,nargs='+')
    a=p.parse_args();run_human(a.out,months=a.months)
