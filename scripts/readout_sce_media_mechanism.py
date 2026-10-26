#!/usr/bin/env python3
"""Align and summarize cached media V3 results without API calls or Q9 refits."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.evaluation.media_mechanism_readout import readout

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    value=readout(args.run_dir,args.out)
    print(json.dumps({'status':value['status'],'support':value['support'],'effects':value['effects'],
                     'technical':value['technical'],'new_api_calls':0,'new_q9_fits':0},ensure_ascii=False,indent=2))
