"""Run cached household-grid and Q8-only diagnostics; no API or Q9 refitting."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.advisor_diagnostics import run

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    grid,q8=run(a.out)
    print(json.dumps({'output':str(a.out),'common_person_months':grid['common_person_months'],
                     'q8_coverage':q8['coverage'],'new_api_calls':0},ensure_ascii=False))
