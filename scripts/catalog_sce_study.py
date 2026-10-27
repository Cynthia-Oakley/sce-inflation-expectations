#!/usr/bin/env python3
"""Build a source-role catalogue and reviewer bundle dependency selection offline."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import studies
studies.__path__ = [str(ROOT / "studies"), *studies.__path__]
from studies.sce_inflation_expectations.submission_tools.source_layout import write_inventory
if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    result = write_inventory(a.out)
    print(json.dumps({k: v for k, v in result.items() if k not in {"files", "entry_groups"}}, ensure_ascii=False, indent=2))
