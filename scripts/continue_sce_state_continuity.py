#!/usr/bin/env python3
"""Prepare or execute an explicitly approved never-attempted-only continuation."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.state_continuity_continuation import prepare,run

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('--parent',type=Path,required=True)
    a.add_argument('--calls',type=Path,required=True);a.add_argument('--out',type=Path,required=True)
    a=sub.add_parser('run');a.add_argument('--package',type=Path,required=True)
    a.add_argument('--out',type=Path,required=True);a.add_argument('--combined',type=Path,required=True)
    a=p.parse_args();result=prepare(a.parent,a.calls,a.out) if a.command=='prepare' else run(a.package,a.out,a.combined)
    print(json.dumps(result,ensure_ascii=False,indent=2))
