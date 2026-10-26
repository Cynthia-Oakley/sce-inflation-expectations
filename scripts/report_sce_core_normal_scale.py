"""Read existing frozen results and report Core budget trade-offs."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.core_normal_scale_report import render

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = render(args.out)
    print(f"{result['months']} existing months; API={result['new_api_calls']}; Q9 refits={result['new_q9_fits']}")
