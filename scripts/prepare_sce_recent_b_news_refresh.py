#!/usr/bin/env python3
"""Prepare B11 four-tier/CPI news inputs and official Core checks; no API."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent / "socioverse2_repo"))
import studies
studies.__path__ = [str(ROOT / "studies"), *studies.__path__]

from studies.sce_inflation_expectations.experiments.recent_b_news_refresh import DEFAULT_OUT, prepare

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    result = prepare(args.out)
    print(json.dumps({key: result[key] for key in ("status", "logical_positions", "estimated_main_cost_usd",
        "new_api_calls", "truth_opened", "execution_package_created", "official_core")}, ensure_ascii=False, indent=2))
