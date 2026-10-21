#!/usr/bin/env python3
"""Build the offline SCE experiment analysis panel (zero API calls, zero network).

Scans outputs/*_evaluation_*/cases_private.json, adapts same-contract batches
into canonical records, aggregates the six fixed sections plus the experiment
catalog, and publishes (atomically, temp file + rename):
  docs/reports/experiment_panel/index.html            (self-contained aggregate panel)
  docs/reports/experiment_panel/panel_aggregate_v1.json (full aggregate dict)
  docs/reports/experiment_panel/build_receipt.json    (provenance + hashes)
Person-level intermediates stay under outputs/sce_experiment_panel_private/
(git-ignored, never commit those).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from studies.sce_inflation_expectations.panel.adapters import load_all, public_records
from studies.sce_inflation_expectations.panel.regimes import DEFAULT_PARQUET, load_regime_lookup
from studies.sce_inflation_expectations.panel.render import render_html
from studies.sce_inflation_expectations.panel.sections import build_panel

PRIVATE_DIR_NAME = 'sce_experiment_panel_private'
PANEL_MODULES = ('adapters.py', 'registry.py', 'sections.py', 'regimes.py', 'render.py',
                 '__init__.py')
STATS_VERSION = 'panel-stats-v1.1'

README = """# SCE 实验分析面板（离线）

- 入口：`index.html`，浏览器直接打开（file:// 可用，无服务器、无网络、无外部库）。
- 新增同契约批次（`outputs/<批次>_evaluation_*/cases_private.json`）后，在仓库根运行
  `python scripts/build_sce_experiment_panel.py` 一条命令即可重建本目录的
  `index.html`、`panel_aggregate_v1.json` 与 `build_receipt.json`（原子发布）。
- 私有逐人中间文件写在 `outputs/sce_experiment_panel_private/`（git 忽略，勿提交、勿外传）；
  本目录只含允许发布的聚合产物。
- 统计口径版本见 `build_receipt.json` 的 `stats_version`；验收数字（0.459191pp 主指标、
  552/571 共同支持等）以冻结批次 summary 为准。
"""


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_atomic(path, text):
    """Write via a temporary sibling file + os.replace for atomic publish."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(text)
    os.replace(tmp, path)


def build_receipt(metas, panel):
    return {
        'generated_at_utc': panel['generated_at_utc'],
        'stats_version': STATS_VERSION,
        'python_version': platform.python_version(),
        'panel_modules_sha256': {
            'studies/sce_inflation_expectations/panel/' + name:
            _sha256(ROOT / 'studies/sce_inflation_expectations/panel' / name)
            for name in PANEL_MODULES
        },
        'build_entry_sha256': _sha256(Path(__file__).resolve()),
        'source_batches': [{
            'batch': m['batch'],
            'cases_sha256': _sha256(Path(m['summary_path']).parent / 'cases_private.json'),
            'n_records': m['n_records'],
            'status': m['status'],
        } for m in metas],
    }


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

    args.private_dir.mkdir(parents=True, exist_ok=True)
    private_path = args.private_dir / 'records_private.json'
    write_atomic(private_path, json.dumps(public_records(records), ensure_ascii=False,
                                          allow_nan=False) + '\n')
    html_path = args.out_dir / 'index.html'
    write_atomic(html_path, render_html(panel))
    aggregate_path = args.out_dir / 'panel_aggregate_v1.json'
    write_atomic(aggregate_path, json.dumps(panel, ensure_ascii=False,
                                            allow_nan=False, indent=1) + '\n')
    receipt = build_receipt(metas, panel)
    receipt_path = args.out_dir / 'build_receipt.json'
    write_atomic(receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    readme_path = args.out_dir / 'README.md'
    if not readme_path.exists():
        write_atomic(readme_path, README)
    # the v0 private file location must not keep person-level data
    stale = args.out_dir / 'panel_data_private.json'
    if stale.exists():
        stale.unlink()

    print(json.dumps({
        'status': 'ok', 'api_calls': 0,
        'stats_version': STATS_VERSION,
        'n_batches': len(metas),
        'batches': [{'batch': m['batch'], 'status': m['status'],
                     'n_records': m['n_records'], 'skip_reason': m['skip_reason']} for m in metas],
        'n_records': len(records),
        'experiments_in_panel': sorted(panel['experiments']),
        'private_json': str(private_path.relative_to(ROOT)),
        'private_json_bytes': private_path.stat().st_size,
        'html_bytes': html_path.stat().st_size,
        'aggregate_bytes': aggregate_path.stat().st_size,
        'receipt_batches': len(receipt['source_batches']),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
