"""A cached answer must remain tied to its original respondent and raw source."""
import json
from pathlib import Path

import pytest

from studies.sce_inflation_expectations import cognition_preparation as preparation
from studies.sce_inflation_expectations.cognition_input import build_records


def fixture_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(preparation, 'ROOT', tmp_path)
    folder = tmp_path / 'outputs/cache'
    folder.mkdir(parents=True)
    links = [{'month': m, 'agent_id': 'anon', 'userid': 101} for m in preparation.MONTHS]
    requests = [{'month': r['month'], 'userid': r['userid']} for r in links]
    records = build_records(requests, [])
    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
    save(folder / 'evaluation_links_private.json', links)
    for link, record in zip(links, records):
        save(folder / str(link['month']) / 'cognition_payloads.json', {'anon': record})
    hashes = {str(p.relative_to(folder)): preparation.sha(p) for p in folder.rglob('*.json')}
    save(folder / 'manifest.json', {'prepared_file_sha256': hashes})
    return folder, links


def test_cached_history_rejects_other_person(tmp_path, monkeypatch):
    folder, links = fixture_cache(tmp_path, monkeypatch)
    result, sources = preparation.cached_history(folder, links)
    assert len(result) == 4 and len(sources) == 6
    wrong = [dict(r) for r in links]
    wrong[0]['userid'] = 999
    with pytest.raises(ValueError, match='different respondent'):
        preparation.cached_history(folder, wrong)


def test_cached_history_rejects_unregistered_payload_change(tmp_path, monkeypatch):
    folder, links = fixture_cache(tmp_path, monkeypatch)
    path = folder / str(preparation.MONTHS[0]) / 'cognition_payloads.json'
    path.write_text(path.read_text() + '\n')
    with pytest.raises(ValueError, match='cache changed'):
        preparation.cached_history(folder, links)
