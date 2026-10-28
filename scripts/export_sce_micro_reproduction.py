#!/usr/bin/env python3
"""Prepare a new local answer/output review dataset; never call an LLM."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.submission_tools.micro_export import export

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    export(p.parse_args().out)
