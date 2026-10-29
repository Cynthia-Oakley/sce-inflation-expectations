#!/usr/bin/env python3
"""Build a code/data allowlisted SCE review ZIP without sending API requests."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent / "socioverse2_repo"))
import studies
studies.__path__ = [str(ROOT / "studies"), *studies.__path__]
from studies.sce_inflation_expectations.submission_tools.package_builder import build

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--public-log-registry", type=Path, required=True)
    parser.add_argument("--a-refresh-readout", type=Path)
    parser.add_argument("--draft-version", choices=("v01", "v02", "v03", "v04", "v05", "v06", "v07"), default="v01")
    parser.add_argument("--micro-data",type=Path,help="Frozen answer-level projection required by v06/v07")
    args = parser.parse_args()
    print(json.dumps(build(args.out, public_log_registry=args.public_log_registry,
        a_refresh=args.a_refresh_readout, draft_version=args.draft_version,micro_data=args.micro_data), ensure_ascii=False, indent=2))
