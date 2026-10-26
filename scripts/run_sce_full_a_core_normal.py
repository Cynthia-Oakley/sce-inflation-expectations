#!/usr/bin/env python3
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.experiments.full_a_core_normal import main
if __name__ == '__main__':
    main()
