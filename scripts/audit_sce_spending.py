#!/usr/bin/env python3
"""Link real SCE spending baskets and run a fixed offline structural probe."""
from pathlib import Path
import argparse,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.spending_audit import run
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
 a=p.parse_args();run(ROOT,a.out.resolve())
