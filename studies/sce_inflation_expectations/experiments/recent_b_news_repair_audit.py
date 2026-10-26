"""Deterministic source and label evidence for versioned B news repairs."""
from collections import Counter, defaultdict
import calendar
import json
from pathlib import Path

from .recent_b_news_repair import REQUIRED_FIELDS, source_identity, text_fingerprint
from .full_a_core_normal import sha


def read_docs(path):
    payload = json.loads(Path(path).read_text())
    docs = payload.get('response', {}).get('docs')
    if not isinstance(docs, list):
        raise ValueError('NYT response.docs list required: ' + str(path))
    return docs


def snapshot_audit(path, month):
    path = Path(path)
    docs = read_docs(path)
    last_day = calendar.monthrange(int(month[:4]), int(month[5:]))[1]
    daily = Counter(row.get('pub_date', '')[8:10] for row in docs
                    if row.get('pub_date', '')[:7] == month)
    versions = defaultdict(set)
    pairs = set()
    for row in docs:
        identity = source_identity(row)
        fingerprint = text_fingerprint(row)
        versions[identity].add(fingerprint)
        pairs.add((identity, fingerprint))
    return {
        'month': month,
        'path': str(path),
        'sha256': sha(path),
        'bytes': path.stat().st_size,
        'n_docs': len(docs),
        'source_document_count': len(docs),
        'daily_counts': dict(sorted(daily.items())),
        'observed_day_count': len(daily),
        'first_observed_day': min((int(day) for day in daily), default=None),
        'last_observed_day': max((int(day) for day in daily), default=None),
        'unobserved_required_days': [day for day in range(1, last_day + 1)
                                     if f'{day:02d}' not in daily],
        'outside_month_rows': sum(row.get('pub_date', '')[:7] != month for row in docs),
        'unique_source_identities': len(versions),
        'unique_identity_text_pairs': len(pairs),
        'duplicate_identity_text_rows': len(docs) - len(pairs),
        'conflicting_source_identities': sorted(identity for identity, fingerprints in versions.items()
                                                if len(fingerprints) > 1),
        'missing_required_field_counts': {
            field: sum(field not in row for row in docs) for field in REQUIRED_FIELDS
        },
        'meaning': 'Retrieved-source reconciliation, not historical text-vintage certification',
    }


def compare_snapshots(old_path, new_path, month):
    old_docs = read_docs(old_path)
    new_docs = read_docs(new_path)
    old_versions = {source_identity(row): text_fingerprint(row) for row in old_docs}
    new_versions = {source_identity(row): text_fingerprint(row) for row in new_docs}
    old_ids = set(old_versions)
    new_ids = set(new_versions)
    return {
        'month': month,
        'old_path': str(old_path),
        'new_path': str(new_path),
        'old_sha256': sha(old_path),
        'new_sha256': sha(new_path),
        'exact_bytes': Path(old_path).read_bytes() == Path(new_path).read_bytes(),
        'old_n_docs': len(old_docs),
        'new_n_docs': len(new_docs),
        'added_source_identities': sorted(new_ids - old_ids),
        'removed_source_identities': sorted(old_ids - new_ids),
        'changed_text_source_identities': sorted(identity for identity in old_ids & new_ids
                                                 if old_versions[identity] != new_versions[identity]),
    }


def label_receipt(out):
    out = Path(out)
    labels = {}
    duplicates = 0
    for line in (out / 'labels.jsonl').read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        label = row.get('label', row)
        aid = label['article_id']
        if aid in labels:
            duplicates += 1
            if labels[aid] != label:
                raise ValueError('Conflicting labels within repair overlay: ' + aid)
        labels[aid] = label
    calls = []
    if (out / 'calls_log.jsonl').exists():
        calls = [json.loads(line) for line in (out / 'calls_log.jsonl').read_text().splitlines()
                 if line.strip()]
    errors = []
    if (out / 'errors.jsonl').exists():
        errors = [json.loads(line) for line in (out / 'errors.jsonl').read_text().splitlines()
                  if line.strip()]
    repaired = {row.get('batch_id') for row in errors if row.get('type') == 'repaired_offline'}
    unresolved = [row for row in errors if row.get('type') != 'repaired_offline'
                  and row.get('batch_id') not in repaired]
    return {
        'path': str(out / 'labels.jsonl'),
        'sha256': sha(out / 'labels.jsonl'),
        'unique_labels': len(labels),
        'duplicate_label_rows': duplicates,
        'decision_counts': dict(Counter(row['decision'] for row in labels.values())),
        'paid_attempts': sum(row.get('cost_usd') is not None for row in calls),
        'reported_or_reserved_cost_usd': sum(row.get('cost_usd') or 0 for row in calls),
        'unknown_billing_successes': sum(row.get('http_status') == 200 and not row.get('error')
                                         and row.get('cost_usd') is None for row in calls),
        'failed_call_records': sum(bool(row.get('error')) for row in calls),
        'error_log_records': len(errors),
        'unresolved_error_records': unresolved,
        'labels_complete_for_frozen_manifest': False,
    }
