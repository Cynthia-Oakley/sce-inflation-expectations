#!/usr/bin/env python3
"""Offline exact-reuse package and official Core checks; never sends an API call."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.experiments.media_timing_package import build

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--draft',type=Path,required=True)
    p.add_argument('--labels',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    print(json.dumps(build(args.draft,args.labels,args.out),ensure_ascii=False,indent=2))
