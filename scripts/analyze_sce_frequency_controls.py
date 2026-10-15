#!/usr/bin/env python3
"""Offline controlled associations in the completed frequency experiment."""
import argparse
from pathlib import Path
import sys
# This offline module has no framework dependency. Import directly from its
# source directory so the analysis Python need not load simulation providers.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'studies/sce_inflation_expectations/evaluation'))
from frequency_controls import run

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    run(parser.parse_args().out)
