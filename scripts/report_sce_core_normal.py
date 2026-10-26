"""Render frozen Core/Normal implementation and validation outputs."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.core_normal_report import render

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['human','cached','pilot','out']:p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();render(a.human,a.cached,a.pilot,a.out)
