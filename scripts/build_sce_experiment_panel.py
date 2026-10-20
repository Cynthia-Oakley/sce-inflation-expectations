#!/usr/bin/env python3
"""Build the offline SCE experiment analysis panel (zero API calls, zero network).

Scans outputs/*_evaluation_*/cases_private.json, adapts same-contract batches
into canonical records, aggregates the six fixed sections, and writes:
  docs/reports/experiment_panel/panel_data_private.json  (skinny records, local only)
  docs/reports/experiment_panel/index.html               (self-contained aggregate panel)
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outputs', type=Path, default=ROOT / 'outputs',
                        help='Directory scanned for *_evaluation_*/cases_private.json')
    parser.add_argument('--regimes-parquet', type=Path, default=DEFAULT_PARQUET,
                        help='Archived full-sample truth parquet for regime lookup')
    parser.add_argument('--out-dir', type=Path,
                        default=ROOT / 'docs' / 'reports' / 'experiment_panel')
    args = parser.parse_args(argv)

    records, metas = load_all(args.outputs)
    regime_lookup = load_regime_lookup(args.regimes_parquet)
    panel = build_panel(records, metas, regime_lookup)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    private_path = args.out_dir / 'panel_data_private.json'
    private_path.write_text(json.dumps(public_records(records), ensure_ascii=False,
                                       allow_nan=False) + '\n')
    html_path = args.out_dir / 'index.html'
    html_path.write_text(render_html(panel))

    print(json.dumps({
        'status': 'ok', 'api_calls': 0,
        'n_batches': len(metas),
        'batches': [{'batch': m['batch'], 'status': m['status'],
                     'n_records': m['n_records'], 'skip_reason': m['skip_reason']} for m in metas],
        'n_records': len(records),
        'experiments_in_panel': sorted(panel['experiments']),
        'private_json_bytes': private_path.stat().st_size,
        'html_bytes': html_path.stat().st_size,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
