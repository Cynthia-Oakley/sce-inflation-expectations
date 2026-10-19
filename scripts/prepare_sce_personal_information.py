#!/usr/bin/env python3
"""Prepare local ATUS/SCE role probabilities and quantity-balanced allocations."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.personal_information_preparation import analyze

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    r = analyze(args.out)
    print(json.dumps({k:r[k] for k in ['status','n_person_months','whole_residence_coverage','support','role_feature_diagnostic_2022_to_2023','seconds']},ensure_ascii=False,indent=2))
