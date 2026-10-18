#!/usr/bin/env python3
"""Make an aggregate report from already scored frozen-prompt trial answers."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.evaluation.frozen_trial_reporting import report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder',type=Path,required=True);p.add_argument('--evaluation',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();r=report(args.folder,args.evaluation,args.out)
    print({'cost_usd':r['estimated_cost_usd_not_bill'],'weighted_metrics':r['weighted_metrics'],'pilot_screen_passed':r['pilot_screen_passed']})
