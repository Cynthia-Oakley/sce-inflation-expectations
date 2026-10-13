"""Compare saved SCE responses and same-cohort baselines; never call an API."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.behavior_comparison import run


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--extra-answers", type=Path)
    parser.add_argument("--extra-manifest", type=Path)
    args = parser.parse_args()
    result = run(ROOT, args.out,
                 ROOT / "docs/workstreams/20261013_behavior/codex_comparison_protocol.json",
                 args.extra_answers, args.extra_manifest)
    print(f"Offline evaluation saved to {args.out}; new API calls: {result['new_api_calls']}")
