"""Entry point for the U1 explicit-state trial: prepare, dry-run or execute."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.u1_state_trial import main

if __name__ == "__main__":
    main()
