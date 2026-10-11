#!/usr/bin/env python3
"""Thin entry point for the local-only NYT inventory audit."""
from pathlib import Path
import importlib.util

path = Path(__file__).resolve().parents[1] / "studies/sce_inflation_expectations/nyt_inventory_audit.py"
spec = importlib.util.spec_from_file_location("nyt_inventory_local_only", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if __name__ == "__main__":
    raise SystemExit(module.main())
