#!/usr/bin/env python3
"""Offline three-level macro readout after isolated monthly evaluation."""
from pathlib import Path
import sys,argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.evaluation.monthly_main_readout import run
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('package','evaluation','truth','registry','out'):p.add_argument('--'+key,type=Path,required=True)
    print(run(**vars(p.parse_args())))
