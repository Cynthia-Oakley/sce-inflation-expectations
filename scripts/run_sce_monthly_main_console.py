#!/usr/bin/env python3
"""Human terminal entry: explicit run confirmation, live progress, no repeated API calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments import monthly_main_console as console

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare')
    for name in ('parent','calls','truth','registry','out'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('run','watch'):
        p=sub.add_parser(name);p.add_argument('--run-dir',type=Path,required=True)
        if name=='run':p.add_argument('--confirm-continuation',action='store_true')
    args=vars(parser.parse_args());command=args.pop('command')
    if command=='prepare':result=console.prepare(**args)
    elif command=='run':result=console.run(args['run_dir'],confirm_continuation=args['confirm_continuation'])
    else:result=console.watch(args['run_dir'])
    print(json.dumps(result,ensure_ascii=False,indent=2))
