#!/usr/bin/env python3
"""Local overnight B runner; one launch, bounded waiting and one repair pass."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.experiments.recent_b_night import main
if __name__=='__main__':main()
