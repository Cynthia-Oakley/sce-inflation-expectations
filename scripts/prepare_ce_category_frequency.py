#!/usr/bin/env python3
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.category_frequency import prepare

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();r=prepare(args.out)
    print('Prepared category-day proxies:',r['household_week_rows'],'CU-weeks; API calls',r['new_api_calls'])
