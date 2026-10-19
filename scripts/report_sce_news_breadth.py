#!/usr/bin/env python3
"""Read out matched/random/uniform news exposure using shared scored outputs."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.news_breadth_readout import report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder',type=Path,required=True);p.add_argument('--evaluation',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=report(a.folder,a.evaluation,a.out)
    print({k:result[k] for k in ('common_person_months','weighted_metrics','development_screen_passed','estimated_cost_usd_not_bill','seconds')})
