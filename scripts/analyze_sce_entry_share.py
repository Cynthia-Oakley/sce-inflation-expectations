#!/usr/bin/env python3
"""Entry proportions and existing-pilot aggregate sensitivity, with zero API."""
from pathlib import Path
import argparse,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.evaluation.entry_share_sensitivity import analyze
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    analyze(parser.parse_args().out)
