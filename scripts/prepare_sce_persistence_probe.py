#!/usr/bin/env python3
"""Prepare local-only previews; there is deliberately no execute mode."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.persistence_probe_preparation import prepare

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=ROOT/'outputs/sce_news_exposure_trial_20261011_v3')
    p.add_argument('--diagnostic',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    r=prepare(ROOT,a.source,a.diagnostic,a.out)
    print(f"Prepared {r['preview_message_count']} local previews. No provider or executable simulation configuration. New API calls: 0.")
