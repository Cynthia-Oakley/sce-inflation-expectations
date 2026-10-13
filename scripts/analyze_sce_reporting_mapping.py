"""Run the registered personal reporting mapping into a fresh local directory."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.reporting_behavior.mapping import run


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    run(ROOT, args.out, ROOT / "docs/workstreams/20261013_behavior/codex_mapping_protocol.json")
