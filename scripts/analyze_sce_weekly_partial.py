"""Read sealed weekly results offline; never sends or resumes API requests."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.weekly_partial_readout import analyze
if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--run-dir',required=True,type=Path);p.add_argument('--out-dir',required=True,type=Path)
    a=p.parse_args();r=analyze(a.run_dir,a.out_dir)
    print(r['operation']);print(r['metrics'])
