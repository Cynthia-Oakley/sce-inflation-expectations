#!/usr/bin/env python3
"""Fetch public historical FOMC sources; no paid API calls."""
from pathlib import Path
import sys,argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.experiments.fullperiod_policy_sources import fetch_and_build
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--delivery',type=Path,required=True)
    print(fetch_and_build(p.parse_args().delivery))
