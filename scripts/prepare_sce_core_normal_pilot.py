"""Prepare three-month Core plus held-out LLM-audit roles, without API calls."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.experiments.core_normal_pilot import prepare

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();r=prepare(a.out);print({k:r[k] for k in ['status','maximum_calls_before_exact_prompt_reuse','new_api_calls']})
