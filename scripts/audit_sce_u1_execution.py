"""Verify U1 real run records and exports without making new API requests."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.u1_execution_audit import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", type=Path, default=ROOT/"outputs/sce_u1_trial_20261014_v2")
    parser.add_argument("--export", type=Path, default=ROOT/"outputs/sce_u1_evaluation_20261014_v1")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run(ROOT,args.trial,args.export,args.out)
    print(f"U1 runtime/export audit passed: {result['counts']['actual_messages_checked']} records; new audit API calls=0")
