#!/usr/bin/env python3
"""Recalculate micro metrics from answers with all Python networking disabled."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.submission_tools.micro_replay import replay
from studies.sce_inflation_expectations.submission_tools.reproduce import no_network

if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--refit-density",action="store_true")
    a=p.parse_args()
    with no_network():r=replay(a.data,a.out,refit_density=a.refit_density)
    print(json.dumps({k:r[k] for k in ("status","actual_LLM_calls","verification","national","scoring_mode","new_numerical_density_fits")},ensure_ascii=False,indent=2))
