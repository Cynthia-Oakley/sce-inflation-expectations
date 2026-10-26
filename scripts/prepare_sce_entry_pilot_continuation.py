#!/usr/bin/env python3
"""Prepare (never execute) a scoped exception to the small pilot gate."""
from pathlib import Path
import argparse
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.entry_pilot_continuation import prepare
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('parent','calls','out'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();print(prepare(args.parent,args.calls,args.out))
