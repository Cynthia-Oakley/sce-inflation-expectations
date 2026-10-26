"""Publish existing demographic-grid aggregates as a readable report."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.grid_dimension_report import render

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--joint', type=Path)
    p.add_argument('--sensitivity', type=Path)
    a = p.parse_args()
    print(render(a.source, a.out, joint=a.joint, sensitivity=a.sensitivity))
