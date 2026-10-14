#!/usr/bin/env python3
"""Zero-API audit of official conditional associations and existing LLM compression."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.mechanism_audit import run

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    r=run(args.out)
    print('completed; official rows',r['official_associations']['total_rows'],'API calls',r['new_api_calls'])
