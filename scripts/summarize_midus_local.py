"""User-run MIDUS statistics. Do not execute on real data through an AI agent.

Uses codebook-defined columns only. No network, no individual exports, no raw
data in the project directory. The user reviews the aggregate file before sharing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
EXPECTED_MR1_SHA256 = "b8d268f373559988b2f5edb92e833234e4ddd852f8cba3b95b4667072eaf9b2f"
sys.path.insert(0, str(PROJECT))

from studies.sce_inflation_expectations.midus_group_summary import (  # noqa: E402
    TRAITS, WEIGHTS, summarize_frame,
)


def check_isolated(path: Path):
    resolved = path.expanduser().resolve()
    workspace = PROJECT.parent
    if resolved == workspace or workspace in resolved.parents:
        raise ValueError("MIDUS input and output must stay outside the DISC workspace")
    return resolved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--weight", choices=sorted(WEIGHTS), default="RA1SWGHT6")
    args = parser.parse_args()
    source, target = check_isolated(args.input), check_isolated(args.out)
    if target.exists():
        raise FileExistsError("Use a new output filename; existing summaries are preserved")
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != EXPECTED_MR1_SHA256:
        raise ValueError("Input version differs from the verified MR1 2025 download")
    import pyreadstat  # lazy import: not needed for public-codebook or synthetic tests

    fields = ["RA1PRAGE", "RA1PB1", args.weight, *TRAITS]
    frame, _ = pyreadstat.read_sav(str(source), usecols=fields, apply_value_formats=False)
    summary = summarize_frame(frame, args.weight)
    del frame
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print("Group summary saved. Please review it locally before sharing: " + str(target))


if __name__ == "__main__":
    main()
