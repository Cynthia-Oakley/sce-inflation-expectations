#!/usr/bin/env python3
"""Freeze / authorize / run independent months through the existing queue."""
from pathlib import Path
import argparse,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.monthly_reconstruction_execution import prepare
from studies.sce_inflation_expectations.experiments.state_continuity_execution import authorize,run
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('--assembly',type=Path,required=True);a.add_argument('--out',type=Path,required=True)
    a=sub.add_parser('authorize');a.add_argument('--package',type=Path,required=True);a.add_argument('--confirmation',required=True)
    a=sub.add_parser('run');a.add_argument('--package',type=Path,required=True);a.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if args.command=='prepare': print(prepare(args.assembly,args.out))
    elif args.command=='authorize': print(authorize(args.package,args.confirmation))
    else: print(run(args.package,args.out))
