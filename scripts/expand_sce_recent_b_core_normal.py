#!/usr/bin/env python3
"""Expand the completed B proxy population offline, without accuracy evaluation."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.recent_b_core_normal import main
if __name__=='__main__':main()
