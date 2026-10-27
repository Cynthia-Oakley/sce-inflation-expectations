#!/usr/bin/env python3
"""Build author-facing SCE evidence materials offline, without rewriting the paper."""
from pathlib import Path
import runpy

if __name__ == '__main__':
    root=Path(__file__).resolve().parents[1]
    runpy.run_path(str(root/'studies/sce_inflation_expectations/reports/final_delivery_materials/build.py'),run_name='__main__')
