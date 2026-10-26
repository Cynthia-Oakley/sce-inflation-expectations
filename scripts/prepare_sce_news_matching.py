#!/usr/bin/env python3
"""Offline news-matching prepare/ledger inspection; never makes API calls."""
from pathlib import Path
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.news_matching import prepare
from studies.sce_inflation_expectations.experiments.news_matching_ledger import prepare_ledger

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','ledger']);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--config',type=Path);p.add_argument('--parent',type=Path)
    a=p.parse_args()
    if a.action=='prepare':
        if not a.config:p.error('--config required')
        result=prepare(a.out,json.loads(a.config.read_text()))
    else:
        if not a.parent:p.error('--parent required')
        result=prepare_ledger(a.parent,a.out)
    print(json.dumps(result,indent=2,ensure_ascii=False))
