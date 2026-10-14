#!/usr/bin/env python
"""Prepare the U1 explicit personal-state arms (offline, zero API calls).

Spec v2: two arms (own_state / own_state_guided) on the executed own_previous
base. Usage: python scripts/prepare_sce_u1a_state.py [output_dir]
Default output: outputs/sce_u1_state_preparation_20261013_v2/
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from studies.sce_inflation_expectations.belief_state_preparation import prepare


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "outputs" / "sce_u1_state_preparation_20261013_v2"
    prepare(root, out)


if __name__ == "__main__":
    main()
