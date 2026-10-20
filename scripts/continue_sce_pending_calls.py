#!/usr/bin/env python3
"""Continue only never-attempted frozen slots, without retrying failed requests."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.pending_call_ledger import prepare,run

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run'])
    p.add_argument('--parent',type=Path);p.add_argument('--folder',type=Path,required=True);p.add_argument('--workers',type=int,default=12)
    a=p.parse_args()
    if a.action=='prepare':
        if a.parent is None:p.error('prepare requires --parent')
        print(prepare(a.parent,a.folder))
    else:run(a.folder,a.workers)
