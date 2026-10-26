#!/usr/bin/env python3
"""Render the cached continuity trial in the project's existing HTML style."""
from pathlib import Path
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.evaluation.state_continuity_report import publish

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--dest',type=Path,required=True);a=p.parse_args()
    print(json.dumps(publish(a.source,a.dest),ensure_ascii=False,indent=2))
