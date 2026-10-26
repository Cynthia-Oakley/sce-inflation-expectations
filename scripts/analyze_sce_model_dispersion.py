#!/usr/bin/env python3
"""Analyze cached model dispersion without refitting or paid calls."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.evaluation.model_dispersion import run

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--official-chart',type=Path)
    a=p.parse_args();r=run(a.cases,a.out,a.official_chart)
    print(json.dumps({k:r[k] for k in ('common_person_months','equal_month_metrics','repeat_equal_month_means')},ensure_ascii=False,indent=2))
