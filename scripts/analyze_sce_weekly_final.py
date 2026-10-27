"""Audit and analyze completed weekly SCE checkpoints offline."""
from pathlib import Path
import argparse
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.weekly_final_readout import analyze
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True,type=Path);p.add_argument('--out-dir',required=True,type=Path)
    a=p.parse_args();r=analyze(a.run_dir,a.out_dir)
    print(r['operation']);print(r['primary'])
