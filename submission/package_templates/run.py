#!/usr/bin/env python3
"""One-command entry for the portable SCE research review bundle."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import studies
studies.__path__ = [str(ROOT / "studies")]
from studies.sce_inflation_expectations.submission_tools.reproduce import main

if __name__ == "__main__":
    main()
