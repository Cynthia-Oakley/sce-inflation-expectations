#!/usr/bin/env python3
"""Create news/price fragments from a prepared ATUS/SCE bridge, without APIs."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.personal_information_views import prepare

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    r=prepare(args.source,args.out)
    print(json.dumps({k:r[k] for k in ['status','n_person_months','n_role_menus','monthly_inventory','seconds']},ensure_ascii=False,indent=2))
