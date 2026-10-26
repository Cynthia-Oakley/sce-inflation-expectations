#!/usr/bin/env python3
"""Prepare/authorize/start/status a never-dispatched-only monthly continuation."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments import monthly_main_continuation as resume

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare')
    for name in ('parent','calls','truth','registry','out'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('authorize','start','status','_worker','_pipeline','_generate'):
        p=sub.add_parser(name);p.add_argument('--run-dir',type=Path,required=True)
        if name=='authorize':p.add_argument('--confirmation',required=True)
    args=vars(parser.parse_args());command=args.pop('command')
    if command=='prepare':result=resume.prepare(**args)
    elif command=='authorize':result=resume.authorize(args['run_dir'],args['confirmation'])
    else:result=getattr(resume,command.lstrip('_'))(args['run_dir'])
    print(json.dumps(result,ensure_ascii=False,indent=2))
