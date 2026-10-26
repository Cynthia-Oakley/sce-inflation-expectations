import hashlib
import json

import pytest

from studies.sce_inflation_expectations.experiments import recent_b_news_repair as mod


def doc(aid, day, headline='headline', abstract='abstract', snippet='snippet'):
    return {
        '_id': aid,
        'uri': 'nyt://article/' + aid,
        'web_url': 'https://www.nytimes.com/' + aid,
        'pub_date': f'2026-01-{day:02d}T12:00:00Z',
        'headline': {'main': headline},
        'abstract': abstract,
        'snippet': snippet,
        'document_type': 'article',
        'section_name': 'Business',
        'news_desk': 'Business',
        'print_section': 'A',
        'print_page': '1',
    }


def test_merge_preserves_fields_deduplicates_and_never_mutates_inputs():
    archive = {'response': {'docs': [doc(f'old-{day}', day) for day in range(1, 8)]}}
    changed = doc('new-31', 31)
    pages = [
        {'response': {'docs': [doc(f'new-{day}', day) for day in range(8, 31)]}},
        {'response': {'docs': [changed, doc('new-31', 31)]}},
    ]
    before = json.dumps([archive, pages], sort_keys=True)
    merged, receipt = mod.merge_january_archive(archive, pages)
    assert json.dumps([archive, pages], sort_keys=True) == before
    assert len(merged['response']['docs']) == 31
    assert changed in merged['response']['docs']
    assert receipt['n_docs'] == 31
    assert receipt['duplicate_identity_text_rows'] == 1
    assert receipt['observed_days'] == list(range(1, 32))
    assert receipt['unobserved_required_days'] == []
    for field in ('headline', 'abstract', 'snippet', 'pub_date', '_id', 'uri',
                  'web_url', 'document_type', 'section_name', 'news_desk',
                  'print_section', 'print_page'):
        assert field in merged['response']['docs'][-1]


def test_merge_rejects_conflicting_versions_instead_of_silent_choice():
    with pytest.raises(ValueError, match='Conflicting source identity'):
        mod.merge_january_archive(
            {'response': {'docs': []}},
            [{'response': {'docs': [doc('same', 8), doc('same', 8, headline='edited')]}}],
        )


def test_merge_requires_complete_january_and_source_month():
    with pytest.raises(ValueError, match='outside 2026-01'):
        mod.merge_january_archive({'response': {'docs': [doc('bad', 1) | {'pub_date': '2026-02-01T00:00:00Z'}]}}, [])
    with pytest.raises(ValueError, match='Incomplete January coverage'):
        mod.merge_january_archive({'response': {'docs': [doc('old', 1)]}}, [])


def test_search_log_url_has_no_credential():
    url = mod.search_log_url(8, 31, 12)
    assert 'api-key' not in url and 'api_key' not in url
    assert 'begin_date=20260108' in url and 'end_date=20260131' in url and 'page=12' in url


def test_existing_search_page_is_resumable_and_validated(tmp_path):
    path = tmp_path / 'page_0000.json'
    payload = {'response': {'docs': [doc('new', 8)]}}
    path.write_text(json.dumps(payload))
    assert mod.read_search_page(path, 0) == payload
    path.write_text(json.dumps({'response': {'docs': []}}))
    assert mod.read_search_page(path, 0) == {'response': {'docs': []}}
    path.write_text(json.dumps({'response': {'docs': [doc('bad', 1) | {'pub_date': '2026-02-01T00:00:00Z'}]}}))
    with pytest.raises(ValueError, match='outside requested January repair days'):
        mod.read_search_page(path, 0)


def test_null_docs_is_a_terminal_page_only_when_source_hits_are_exhausted(tmp_path):
    path = tmp_path / 'page_0007.json'
    path.write_text(json.dumps({'response': {'docs': None, 'metadata': {'hits': 70, 'offset': 70}}}))
    payload = mod.read_search_page(path, 7)
    assert payload['response']['docs'] == []
    assert mod.search_page_terminal(payload)
    assert mod.search_page_terminal({'response': {'docs': [doc('new', 8)] * 10,
                                                   'metadata': {'hits': 10, 'offset': 0}}})
    assert not mod.search_page_terminal({'response': {'docs': [doc('new', 8)] * 10,
                                                       'metadata': {'hits': 20, 'offset': 0}}})
    path.write_text(json.dumps({'response': {'docs': None}}))
    with pytest.raises(ValueError, match='response.docs list required'):
        mod.read_search_page(path, 7)


def test_overlay_manifest_binds_actual_hashes(tmp_path):
    archive = tmp_path / '2026-01.json'
    archive.write_text('{}')
    meta = tmp_path / '2026-01.meta.json'
    meta.write_text('{}')
    config = mod.repair_manifest(tmp_path, archive, meta, [], ['receipt.json'])
    assert config['schema'] == 'sce_B_news_repair_overlay/v1'
    row = config['archive_overrides']['2026-01']
    assert row['path'] == '2026-01.json'
    assert row['sha256'] == hashlib.sha256(b'{}').hexdigest()
    assert row['meta_sha256'] == hashlib.sha256(b'{}').hexdigest()
    assert config['base_label_overlays'] == []


def test_daily_search_loader_requires_all_days_and_binds_page_hashes(tmp_path):
    for day in range(8, 32):
        folder = tmp_path / f'day_{day:02d}'
        folder.mkdir()
        docs = [doc('new', 8)] if day == 8 else []
        (folder / 'page_0000.json').write_text(json.dumps({'response': {'docs': docs}}))
        (folder / 'search_complete.json').write_text(json.dumps({
            'begin_day': day, 'end_day': day, 'pages': 1,
        }))
    pages, evidence = mod.load_daily_search_pages(tmp_path)
    assert len(pages) == len(evidence) == 24
    assert sum(len(page['response']['docs']) for page in pages) == 1
    assert all(len(row['sha256']) == 64 for row in evidence)
