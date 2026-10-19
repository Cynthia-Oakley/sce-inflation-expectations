#!/usr/bin/env python3
"""Reuse archived news-count replies for a fixed external-attention allocation."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.heterogeneous_news import analyze

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    result = analyze(parser.parse_args().out)
    print(json.dumps({k: result[k] for k in ('status', 'common_person_months', 'new_api_calls', 'new_q9_fits', 'seconds')}, ensure_ascii=False))
    for mode, row in result['modes'].items():
        print(mode, {k: row['matched_assignment_range_not_confidence_interval'][k] for k in ('center_mae_pp','w1_pp')})
