"""Export-only repair: preserve missing truth values as JSON null.

The frozen analysis and scoring sources remain unchanged. This adapter changes
only serialization of nonfinite missing entries in private evaluation records.
"""
import json
import math
from pathlib import Path
from . import confidence_analysis as analysis


def json_missing(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: json_missing(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_missing(item) for item in value]
    return value


def analyze_with_missing_export(root, trial, truth, out):
    original_dump = analysis.dump
    def strict_dump(path, value):
        Path(path).write_text(json.dumps(json_missing(value), ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    analysis.dump = strict_dump
    try:
        result = analysis.analyze(root, trial, truth, out)
    finally:
        analysis.dump = original_dump
    strict_dump(Path(out) / 'export_repair_receipt.json', {
        'repair': 'nonfinite missing private evaluation entries -> JSON null',
        'adapter_sha256': analysis.sha(Path(__file__)),
        'frozen_analysis_sha256': analysis.sha(Path(analysis.__file__)),
        'scoring_and_statistical_parameters_changed': False, 'new_api_calls': 0})
    return result


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--truth', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    result = analyze_with_missing_export(Path(__file__).resolve().parents[2], args.trial, args.truth, args.out)
    print(json.dumps({k: result[k] for k in ('actual_calls', 'conservative_cost_usd', 'candidate_upgrade_gate_passed')}))
