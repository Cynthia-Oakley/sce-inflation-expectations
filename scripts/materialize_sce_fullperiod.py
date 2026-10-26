#!/usr/bin/env python3
"""Build versioned offline P/E using existing raw caches and field mappers."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT)); sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.fullperiod_materialization import materialize
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--stage',choices=['all','population','environment'],default='all')
    p.add_argument('--months',nargs='+')
    a=p.parse_args(); print(materialize(a.out,stage=a.stage,months=a.months))
