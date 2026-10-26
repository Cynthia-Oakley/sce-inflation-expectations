#!/usr/bin/env python3
"""Offline 54-cell assembly and proposed budget package; no authorize/run mode."""
from pathlib import Path
import argparse,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.monthly_fine_pipeline import assemble,freeze
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('assemble')
    for key in ['inputs','families','environments','delivery','out']:a.add_argument('--'+key,type=Path,required=True)
    a.add_argument('--policy-supplement',type=Path);a.add_argument('--confidence-supplement',type=Path)
    a.add_argument('--prepared-prompts',type=Path,help='Reuse a complete hash-verified prompt bundle')
    a=sub.add_parser('freeze');a.add_argument('--assembly',type=Path,required=True)
    a.add_argument('--out',type=Path,required=True);a.add_argument('--cap-usd',type=float,required=True)
    args=vars(p.parse_args());command=args.pop('command')
    result=(assemble if command=='assemble' else freeze)(**args)
    print({k:result[k] for k in result if k in ['status','person_months','planned_calls','grid_version','estimated_cost_usd','budget_cap_usd','budget_mode','full_conservative_reservation_usd']})
