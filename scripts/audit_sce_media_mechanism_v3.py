#!/usr/bin/env python3
"""Verify a V3 package and print its offline acceptance receipt."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent / "socioverse2_repo"))
import studies

studies.__path__ = [str(ROOT / "studies"), *studies.__path__]
from studies.sce_inflation_expectations.experiments.media_mechanism_v3_preparation import audit_preparation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = audit_preparation(args.folder)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        if args.out.exists():
            parser.error("refuse to overwrite existing receipt")
        args.out.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
