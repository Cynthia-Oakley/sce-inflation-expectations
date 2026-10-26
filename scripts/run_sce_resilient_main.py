#!/usr/bin/env python3
"""Bounded resilient continuation: prepare/run/watch/status, no failed-slot retries."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments import monthly_main_resilient as robust

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare')
    for name in ('parent','calls','truth','registry','out'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('run','watch','status','_worker','_pipeline','_generate'):
        p=sub.add_parser(name);p.add_argument('--run-dir',type=Path,required=True)
        if name=='run':p.add_argument('--confirm-continuation',action='store_true')
    args=vars(parser.parse_args());name=args.pop('command')
    if name=='prepare':result=robust.prepare(**args)
    elif name=='run':result=robust.run(args['run_dir'],args['confirm_continuation'])
    else:result=getattr(robust,name.lstrip('_'))(args['run_dir'])
    print(json.dumps(result,ensure_ascii=False,indent=2))
