#!/usr/bin/env python3
"""Audit, bind and accept the versioned recent-B public-news repair."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from label_sce_news_pool import validate_label
from studies.sce_inflation_expectations.experiments.full_a_core_normal import sha, write
from studies.sce_inflation_expectations.experiments.recent_b_news_repair import repair_manifest
from studies.sce_inflation_expectations.experiments.recent_b_news_repair_audit import (
    compare_snapshots, label_receipt, snapshot_audit,
)

REPAIR = ROOT / 'data/raw/nyt_archive_repairs/20261026'
OUT = ROOT / 'outputs/sce_recent_b_news_repair_20261026_v1'
EXPECTED_OLD = {
    '2026-01': '788ab41712e164d6c7cbf0a425a2a899730614e98eb29bd2d62c9d5cd8f58266',
    '2026-09': '4576d2696b9f8e6254f87beeed400e9041c4aa0f028c51fad2baaa3fef5e472e',
}


def source_audit(out):
    out.mkdir(parents=True, exist_ok=True)
    result = {
        'schema': 'sce_B_news_source_reconciliation/v1',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'months': {},
        'new_api_calls': 0,
        'limitations': 'A later fetch reconciles the current official source, not the historical article-text vintage.',
    }
    for month in ('2026-01', '2026-09'):
        canonical = ROOT / f'data/raw/nyt_archive/{month}.json'
        refreshed = REPAIR / f'official_archive_refresh/{month}.json'
        result['months'][month] = {
            'canonical': snapshot_audit(canonical, month),
            'official_refresh': snapshot_audit(refreshed, month),
            'canonical_vs_refresh': compare_snapshots(canonical, refreshed, month),
        }
        if sha(canonical) != EXPECTED_OLD[month]:
            raise ValueError('Protected canonical archive changed: ' + month)
    merged = REPAIR / '2026-01.json'
    if merged.exists():
        result['january_merged'] = snapshot_audit(merged, '2026-01')
        result['january_canonical_vs_merged'] = compare_snapshots(
            ROOT / 'data/raw/nyt_archive/2026-01.json', merged, '2026-01')
    write(out / 'source_reconciliation.json', result)
    print(json.dumps({month: {
        'canonical_docs': row['canonical']['n_docs'],
        'refresh_docs': row['official_refresh']['n_docs'],
        'exact_bytes': row['canonical_vs_refresh']['exact_bytes'],
        'refresh_unobserved_days': row['official_refresh']['unobserved_required_days'],
    } for month, row in result['months'].items()}, ensure_ascii=False, indent=2))


def read_labels(path):
    rows = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        label = value.get('label', value)
        invalid = validate_label(label)
        if invalid:
            raise ValueError(f'Invalid repair label in {path}: {invalid}')
        aid = label['article_id']
        if len(aid) != 24:
            raise ValueError('Repair article_id must retain 24 characters')
        if aid in rows and rows[aid] != label:
            raise ValueError('Conflicting repair label: ' + aid)
        rows[aid] = label
    return rows


def write_delivery_manifest(out, repair, label_paths, pending_paths):
    all_labels = {}
    pending = {}
    for path in pending_paths:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            aid = row['article_id']
            if aid in pending and pending[aid] != row:
                raise ValueError('Pending article text version changed between manifests: ' + aid)
            pending[aid] = row
    receipts = []
    for path in label_paths:
        rows = read_labels(path)
        for aid, label in rows.items():
            if aid in all_labels and all_labels[aid] != label:
                raise ValueError('Cross-overlay relabeling: ' + aid)
            all_labels[aid] = label
        receipt = label_receipt(path.parent)
        receipt['labels_complete_for_frozen_manifest'] = True
        receipts.append(receipt)
    missing = sorted(set(pending) - set(all_labels))
    extra = sorted(set(all_labels) - set(pending))
    if missing or extra:
        raise ValueError(f'Label/pending mismatch: missing={len(missing)} extra={len(extra)}')
    receipt_path = out / 'label_receipt.json'
    write(receipt_path, {
        'unique_pending_articles': len(pending),
        'unique_new_labels': len(all_labels),
        'missing_article_ids': missing,
        'extra_article_ids': extra,
        'batches': receipts,
        'total_reported_or_reserved_cost_usd': sum(row['reported_or_reserved_cost_usd'] for row in receipts),
        'simulation_calls': 0,
    })
    receipts_relative = [
        'outputs/sce_recent_b_news_repair_20261026_v1/source_reconciliation.json',
        'outputs/sce_recent_b_news_repair_20261026_v1/label_receipt.json',
    ]
    config = repair_manifest(ROOT, repair / '2026-01.json', repair / '2026-01.meta.json',
                             label_paths, receipts_relative)
    write(out / 'repair_manifest.json', config)
    print(json.dumps({'pending': len(pending), 'new_labels': len(all_labels),
                      'manifest': str(out / 'repair_manifest.json')}, ensure_ascii=False, indent=2))


def accept(out, inventory):
    import jsonschema

    config = json.loads((out / 'repair_manifest.json').read_text())
    schema = json.loads((ROOT / 'docs/workstreams/20261026_response_dates/news_repair_manifest.schema.json').read_text())
    jsonschema.Draft202012Validator(schema).validate(config)
    bound = {}
    for month, row in config['archive_overrides'].items():
        path = ROOT / row['path']
        if sha(path) != row['sha256']:
            raise ValueError('Archive override hash mismatch: ' + month)
        bound[row['path']] = row['sha256']
        if row.get('meta_path') and sha(ROOT / row['meta_path']) != row['meta_sha256']:
            raise ValueError('Archive meta hash mismatch: ' + month)
    for row in config['base_label_overlays']:
        if sha(ROOT / row['path']) != row['sha256']:
            raise ValueError('Label overlay hash mismatch: ' + row['path'])
        bound[row['path']] = row['sha256']
    for month, expected in EXPECTED_OLD.items():
        if sha(ROOT / f'data/raw/nyt_archive/{month}.json') != expected:
            raise ValueError('Canonical source changed: ' + month)
    summary = json.loads((inventory / 'summary.json').read_text())
    coverage = json.loads((inventory / 'archive_coverage.json').read_text())
    blockers = summary.get('archive_coverage_blockers') or [row for row in coverage if not row['screen_passed']]
    pending = summary.get('unique_pending_articles')
    if pending != 0 or blockers:
        raise ValueError(f'Inventory not complete: pending={pending}, blockers={len(blockers)}')
    receipt = {
        'status': 'accepted_offline_news_repair',
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'manifest_schema_valid': True,
        'bound_file_hashes': bound,
        'canonical_archives_unchanged': EXPECTED_OLD,
        'inventory': str(inventory.relative_to(ROOT)),
        'unique_pending_articles': pending,
        'missing_labels_by_window': summary['missing_labels_by_window'],
        'archive_coverage_blockers': blockers,
        'january_and_february_windows_constructible': True,
        'september_source_reconciled': True,
        'new_simulation_calls': 0,
        'historical_text_vintage_certified': False,
    }
    write(out / 'acceptance.json', receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    audit = sub.add_parser('source-audit')
    audit.add_argument('--out', type=Path, default=OUT)
    delivery = sub.add_parser('write-manifest')
    delivery.add_argument('--out', type=Path, default=OUT)
    delivery.add_argument('--repair', type=Path, default=REPAIR)
    delivery.add_argument('--labels', type=Path, action='append', required=True)
    delivery.add_argument('--pending', type=Path, action='append', required=True)
    acceptance = sub.add_parser('accept')
    acceptance.add_argument('--out', type=Path, default=OUT)
    acceptance.add_argument('--inventory', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'source-audit':
        source_audit(args.out)
    elif args.command == 'write-manifest':
        write_delivery_manifest(args.out, args.repair, args.labels, args.pending)
    else:
        accept(args.out, args.inventory)


if __name__ == '__main__':
    main()
