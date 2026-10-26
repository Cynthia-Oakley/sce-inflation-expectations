#!/usr/bin/env python3
"""Assemble monthly prompts, baselines and official zero-API Core checks."""
from pathlib import Path
import argparse
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.monthly_reconstruction_pipeline import finish
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--families',type=Path,required=True)
    p.add_argument('--environments',type=Path,required=True)
    p.add_argument('--delivery',type=Path,default=ROOT/'outputs/sce_fullperiod_data_20261021_v1')
    p.add_argument('--policy-supplement',type=Path)
    p.add_argument('--confidence-supplement',type=Path)
    p.add_argument('--prepared-prompts',type=Path)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    r=finish(a.inputs,a.families,a.environments,a.out,delivery=a.delivery,policy_supplement=a.policy_supplement,
             confidence_supplement=a.confidence_supplement,prepared_prompts=a.prepared_prompts)
    print({k:r[k] for k in ['status','person_months','official_core','new_api_calls']})
