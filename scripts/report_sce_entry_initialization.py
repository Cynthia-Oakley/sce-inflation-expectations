#!/usr/bin/env python3
"""Refresh the initialization section of the existing project reading page."""
import argparse
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent / 'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT / 'studies'), *studies.__path__]
from studies.sce_inflation_expectations.evaluation.entry_initialization_report import publish
if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--report', type=Path, default=ROOT / 'docs/workstreams/20261021_fullperiod/state_continuity_results_v2')
    a = p.parse_args()
    print(publish(a.source, a.report))
