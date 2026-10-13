"""Read-only audit of prepared U1 messages; no real simulation or API calls."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.u1_preparation_audit import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bundle", type=Path,
                        default=ROOT / "outputs/sce_u1_state_preparation_20261013_v2")
    args = parser.parse_args()
    result = run(ROOT, args.bundle, args.out)
    print(f"Prepared-input audit: {result['status']}; cases={result['counts']['checked_cases']}; API=0")
