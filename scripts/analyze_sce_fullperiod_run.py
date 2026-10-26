#!/usr/bin/env python3
"""Analyze the frozen final A82 run; no LLM requests or Q9 refitting."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.evaluation.fullperiod_analysis import run
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--declaration',type=Path,default=ROOT/'docs/workstreams/20261024_fullperiod_analysis/analysis_sources.json')
    p.add_argument('--out',type=Path,required=True)
    print(json.dumps(run(**vars(p.parse_args())),ensure_ascii=False,indent=2))
