#!/usr/bin/env python
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent / 'socioverse2_repo'))
import studies

studies.__path__ = [str(ROOT / 'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments.media_mechanism_trial import prepare


def main():
    parser = argparse.ArgumentParser(description='Prepare the offline SCE media-mechanism contrast; never calls an API.')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    summary = prepare(args.out)
    print(json.dumps({'out': str(args.out), 'prompt_position_count': summary['prompt_position_count'],
                      'physical_call_cap_two_repeats': summary['physical_call_cap_two_repeats'],
                      'new_api_calls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
