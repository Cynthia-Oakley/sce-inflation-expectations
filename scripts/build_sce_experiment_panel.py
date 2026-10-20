#!/usr/bin/env python3
"""Build the offline SCE experiment analysis panel (zero API calls, zero network).

Scans outputs/*_evaluation_*/cases_private.json, adapts same-contract batches
into canonical records, aggregates the six fixed sections plus the experiment
catalog, and writes:
  docs/reports/experiment_panel/index.html          (publishable aggregate panel)
  outputs/sce_experiment_panel_private/records_private.json  (person-level
      intermediate; outputs/ is git-ignored, never commit this)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from studies.sce_inflation_expectations.panel.adapters import load_all, public_records
from studies.sce_inflation_expectations.panel.regimes import DEFAULT_PARQUET, load_regime_lookup
from studies.sce_inflation_expectations.panel.render import render_html
from studies.sce_inflation_expectations.panel.sections import build_panel

PRIVATE_DIR_NAME = 'sce_experiment_panel_private'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outputs', type=Path, default=ROOT / 'outputs',
                        help='Directory scanned for *_evaluation_*/cases_private.json')
    parser.add_argument('--regimes-parquet', type=Path, default=DEFAULT_PARQUET,
                        help='Archived full-sample truth parquet for regime lookup')
    parser.add_argument('--out-dir', type=Path,
                        default=ROOT / 'docs' / 'reports' / 'experiment_panel')
    parser.add_argument('--private-dir', type=Path, default=None,
                        help='Person-level intermediate directory (must stay under outputs/)')
    args = parser.parse_args(argv)
    if args.private_dir is None:
        args.private_dir = args.outputs / PRIVATE_DIR_NAME
    args.private_dir = args.private_dir.resolve()
    outputs_resolved = args.outputs.resolve()
    if args.private_dir == outputs_resolved or outputs_resolved not in args.private_dir.parents:
        raise ValueError('private dir must live under the scanned outputs/ directory')

    records, metas = load_all(args.outputs)
    regime_lookup = load_regime_lookup(args.regimes_parquet)
    panel = build_panel(records, metas, regime_lookup)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.private_dir.mkdir(parents=True, exist_ok=True)
    private_path = args.private_dir / 'records_private.json'
    private_path.write_text(json.dumps(public_records(records), ensure_ascii=False,
                                       allow_nan=False) + '\n')
    html_path = args.out_dir / 'index.html'
    html_path.write_text(render_html(panel))
    # the v0 private file location must not keep person-level data
    stale = args.out_dir / 'panel_data_private.json'
    if stale.exists():
        stale.unlink()

    print(json.dumps({
        'status': 'ok', 'api_calls': 0,
        'n_batches': len(metas),
        'batches': [{'batch': m['batch'], 'status': m['status'],
                     'n_records': m['n_records'], 'skip_reason': m['skip_reason']} for m in metas],
        'n_records': len(records),
        'experiments_in_panel': sorted(panel['experiments']),
        'private_json': str(private_path.relative_to(ROOT)),
        'private_json_bytes': private_path.stat().st_size,
        'html_bytes': html_path.stat().st_size,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
