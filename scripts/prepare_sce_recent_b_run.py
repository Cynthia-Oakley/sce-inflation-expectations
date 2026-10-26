#!/usr/bin/env python3
"""Assemble recent-B prompts and official Core checks without network calls."""
import argparse,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.experiments.recent_b_prompts import prepare

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--population',type=Path,required=True);p.add_argument('--priors',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=prepare(a.population,a.priors,a.out)
    print(json.dumps({k:v for k,v in r.items() if k!='source_sha256'},ensure_ascii=False,indent=2))
