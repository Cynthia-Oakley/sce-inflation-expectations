"""Prepare shared Core-budget pilot roles; never call a model."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.experiments.core_normal_scale_pilot import prepare

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = prepare(args.out)
    print(json.dumps({'status': result['status'], 'new_api_calls': result['new_api_calls'],
                      'maximum_calls': result['maximum_unique_requests_before_exact_prompt_reuse']}, ensure_ascii=False))
