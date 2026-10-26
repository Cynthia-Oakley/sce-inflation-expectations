#!/usr/bin/env python3
"""Prepare fixed-cohort population/environment for future belief recursion; no API."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent / "socioverse2_repo"))
import studies
studies.__path__ = [str(ROOT / "studies"), *studies.__path__]

from studies.sce_inflation_expectations.experiments.recent_b_continuity_pe import DEFAULT_OUT, MONTHS, prepare

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--months", nargs="+", default=list(MONTHS))
    args = parser.parse_args()
    result = prepare(args.out, months=args.months)
    print(json.dumps({key: result[key] for key in ("status", "months", "n_fixed_proxies", "person_months",
        "lineage_check", "new_api_calls", "official_schema_months", "official_core_units")}, ensure_ascii=False, indent=2))
