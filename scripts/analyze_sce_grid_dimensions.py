"""Run evaluation-only three/four-dimensional demographic grid selection."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.grid_dimension_selection import run

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    result = run(parser.parse_args().out)
    print(result['selection'])
