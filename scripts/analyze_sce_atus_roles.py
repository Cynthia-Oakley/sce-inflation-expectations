#!/usr/bin/env python3
"""Audit public ATUS roles and external attention without simulation calls."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.atus_roles import analyze, analyze_role_ablations

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--role-ablations-from',type=Path)
    args=parser.parse_args()
    if args.role_ablations_from:
        print(json.dumps(analyze_role_ablations(args.role_ablations_from,args.out),ensure_ascii=False,indent=2))
    else:
        result=analyze(args.out)
        print(json.dumps({'status':result['status'],'seconds':result['seconds'],'role_validation':result['role_2022_to_2023_validation'],
            'attention_scores':{k:v['mean_scores'] for k,v in result['external_attention'].items()}},ensure_ascii=False,indent=2))
