#!/usr/bin/env python3
"""Build the full-period A personal-cutoff prompt inputs without API calls."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent / "socioverse2_repo"))
import studies
studies.__path__ = [str(ROOT / "studies"), *studies.__path__]

from studies.sce_inflation_expectations.experiments.full_a_personal_inputs import DEFAULT_OUT, prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    summary = prepare(args.out)
    print({key: summary[key] for key in (
        "status", "eligible_total", "excluded_total", "prompt_characters_max",
        "prompt_utf8_bytes_max", "estimated_total_cost_usd", "new_api_calls",
    )})


if __name__ == "__main__":
    main()
