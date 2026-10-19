"""Prepare an outcome-free support report for a draft six-cell SCE design."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.stratification_support import run

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path)
    r=run(p.parse_args().out)
    print(r['current_primary_cells_strong'], '/', r['primary_cells_total'], 'strong cells; reference unchanged')
