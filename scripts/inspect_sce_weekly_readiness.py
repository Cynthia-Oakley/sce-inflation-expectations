#!/usr/bin/env python3
"""Inventory proposed weekly dates and existing source snapshots, with no API."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.weekly_design import main
if __name__=='__main__':main()
