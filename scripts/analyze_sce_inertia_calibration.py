#!/usr/bin/env python3
"""Fixed-weight ConsumerSim-style aggregate sensitivity; zero network or LLM calls."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.inertia_calibration_diagnostic import main
if __name__ == '__main__':
    main()
