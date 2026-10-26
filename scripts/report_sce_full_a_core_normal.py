#!/usr/bin/env python3
"""Render the offline HTML readout for a completed Core + Normal A82 evaluation."""
import importlib.util
from pathlib import Path

REPORT_MODULE = (Path(__file__).resolve().parents[1]
                 / 'studies/sce_inflation_expectations/reports/full_a_core_normal.py')
SPEC = importlib.util.spec_from_file_location('sce_full_a_core_normal_report', REPORT_MODULE)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError('Could not load offline Core + Normal report module')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


if __name__ == '__main__':
    MODULE.main()
