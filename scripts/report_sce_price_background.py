#!/usr/bin/env python3
"""Summarize a completed price-background evaluation without API calls or refits."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.evaluation.price_background_readout import report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trial',type=Path,required=True);p.add_argument('--evaluation',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=report(a.trial,a.evaluation,a.out)
    print({k:r[k] for k in ('status','person_months','unique_persons','development_signal_passed','seconds')})
