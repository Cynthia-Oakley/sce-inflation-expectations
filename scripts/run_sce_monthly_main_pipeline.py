#!/usr/bin/env python3
"""Default: print a zero-API plan. --execute requires an existing exact authorization."""
from pathlib import Path
import argparse,sys,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.monthly_main_pipeline import plan,execute
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('package','calls','truth','evaluation','registry','readout'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--out',type=Path)
    args=vars(p.parse_args());live=args.pop('execute');out=args.pop('out')
    if live and out is None:p.error('--execute needs a fresh --out receipt folder')
    result=execute(**args,out=out) if live else plan(**args)
    print(json.dumps(result,ensure_ascii=False,indent=2))
