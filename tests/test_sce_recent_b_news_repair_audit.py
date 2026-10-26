import json

from studies.sce_inflation_expectations.experiments import recent_b_news_repair_audit as mod


def row(aid, day, text='same'):
    return {
        '_id': aid,
        'pub_date': f'2026-09-{day:02d}T00:00:00Z',
        'headline': {'main': text},
        'abstract': '',
        'snippet': '',
    }


def test_snapshot_audit_counts_daily_coverage_duplicates_and_conflicts(tmp_path):
    path = tmp_path / '2026-09.json'
    docs = [row('a', 1), row('a', 1), row('b', 2), row('b', 2, 'edited')]
    path.write_text(json.dumps({'response': {'docs': docs}}))
    result = mod.snapshot_audit(path, '2026-09')
    assert result['n_docs'] == 4
    assert result['daily_counts'] == {'01': 2, '02': 2}
    assert result['observed_day_count'] == 2
    assert result['unobserved_required_days'] == list(range(3, 31))
    assert result['duplicate_identity_text_rows'] == 1
    assert result['conflicting_source_identities'] == ['b']
    assert result['missing_required_field_counts']['web_url'] == 4


def test_comparison_distinguishes_exact_bytes_from_text_changes(tmp_path):
    old = tmp_path / 'old.json'
    new = tmp_path / 'new.json'
    old.write_text(json.dumps({'response': {'docs': [row('a', 1), row('b', 2)]}}))
    new.write_text(old.read_text())
    exact = mod.compare_snapshots(old, new, '2026-09')
    assert exact['exact_bytes'] is True
    assert exact['changed_text_source_identities'] == []
    new.write_text(json.dumps({'response': {'docs': [row('a', 1, 'edited'), row('c', 3)]}}))
    changed = mod.compare_snapshots(old, new, '2026-09')
    assert changed['exact_bytes'] is False
    assert changed['added_source_identities'] == ['c']
    assert changed['removed_source_identities'] == ['b']
    assert changed['changed_text_source_identities'] == ['a']
