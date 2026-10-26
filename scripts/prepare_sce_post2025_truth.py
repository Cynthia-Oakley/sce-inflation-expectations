#!/usr/bin/env python3
"""Extract real evaluation truth and past-only baselines for a frozen cohort."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.evaluation.post2025_baselines import run
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--population',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=run(a.population,a.out)
    print(json.dumps({k:r[k] for k in ('status','national_copy_errors','individual_copy_equal_month_metrics')},ensure_ascii=False,indent=2))
