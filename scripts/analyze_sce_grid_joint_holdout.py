"""Check conditional joint-response distributions on a frozen grid shortlist."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.grid_joint_holdout import run

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True,type=Path); p.add_argument('--out',required=True,type=Path)
    a=p.parse_args(); run(a.source,a.out)
