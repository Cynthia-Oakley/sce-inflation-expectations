#!/usr/bin/env python3
"""Render an offline audit into static scientific plots and a browser report."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.pe_diagnostic_view import render
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit',type=Path,required=True)
    p.add_argument('--html',type=Path,required=True)
    args=p.parse_args()
    render(ROOT,args.audit.resolve(),args.html.resolve())
