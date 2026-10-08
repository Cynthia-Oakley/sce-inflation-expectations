#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.native_spending_analysis import analyze
if __name__=='__main__':
    p=argparse.ArgumentParser(description='Offline common-case native basket evaluation')
    p.add_argument('--trial',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();analyze(ROOT,ROOT/a.trial,ROOT/a.out)
