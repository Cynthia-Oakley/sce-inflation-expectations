#!/usr/bin/env python3
"""Read completed news trials with shared cached metrics; zero API/refits."""
from pathlib import Path
import argparse
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.evaluation.news_matching_readout import readout
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evaluation',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=readout(a.evaluation,a.ledger,a.out);print(json.dumps(r,ensure_ascii=False,indent=2))
