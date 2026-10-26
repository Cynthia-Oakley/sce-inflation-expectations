#!/usr/bin/env python3
"""Offline preparation for additional 2025 evaluation months."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.post2025_validation import prepare_news,prepare_population

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['news','population'])
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    r=(prepare_news if a.action=='news' else prepare_population)(a.out)
    print(json.dumps({k:r[k] for k in ['status','unique_new_articles','new_batches','total_reservation_usd',
        'proposed_total_cap_usd','n_per_month'] if k in r},ensure_ascii=False,indent=2))
