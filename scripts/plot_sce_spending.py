#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.spending_figures import make_figures
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--summary',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();print('\n'.join(make_figures(ROOT/a.summary,ROOT/a.out)))
