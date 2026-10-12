#!/usr/bin/env python3
"""Budget-gated qualitative history comparison, no change to old configurations."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.lifetime_text_trial import main
if __name__=='__main__':main()
