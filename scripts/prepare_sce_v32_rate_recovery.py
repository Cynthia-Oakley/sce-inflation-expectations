#!/usr/bin/env python3
"""Prepare an explicitly authorized low-concurrency completion; never calls APIs."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.v32_rate_recovery import prepare_retry,prepare_remainder

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['retry','remainder'])
    p.add_argument('--parent',type=Path,required=True);p.add_argument('--folder',type=Path,required=True)
    a=p.parse_args();print((prepare_retry if a.action=='retry' else prepare_remainder)(a.parent,a.folder))
