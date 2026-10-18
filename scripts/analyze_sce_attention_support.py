#!/usr/bin/env python3
"""Check external attention/channel predictive support without paid calls."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.attention_support import analyze

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.out)
    print(json.dumps({'out': str(args.out), 'attention': result['attention']['mean_scores'],
        'channels': {k: v['mean_scores'] for k, v in result['channels'].items()},
        'seconds': result['seconds'], 'new_api_calls': 0}, ensure_ascii=False))
