import hashlib
import json
import sys

import pytest

from scripts.run_sce_event_probe import main, sanitize


def prepared(tmp_path, *, source='ustr', cap=.10, approved=True):
    protocol = {'automatic_retries': 0, 'planned_calls': 1, 'hard_cap_usd': cap,
                'unit_price_usd_email': .005,
                'jobs': [{'tool': 'get_source_detail', 'arguments': {'source': source}}]}
    path = tmp_path/'protocol.json'; path.write_text(json.dumps(protocol))
    auth = {'approved': approved, 'protocol_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'cap_usd': cap}
    (tmp_path/'authorization.json').write_text(json.dumps(auth))
    return path


def test_secrets_removed_while_search_keywords_survive():
    value = {'api_key': 'secret_value', 'keyword': 'inflation', 'message': 'token=another & x=secret_value'}
    out = sanitize(value, 'secret_value')
    assert out['api_key'] == '<redacted>'
    assert out['keyword'] == 'inflation'
    assert 'secret_value' not in str(out) and 'another' not in str(out)


@pytest.mark.parametrize('reason', ['not_approved', 'source_out_of_scope', 'cap_insufficient', 'changed_protocol'])
def test_reject_before_network_or_credential_loading(tmp_path, monkeypatch, reason):
    path = prepared(tmp_path, source='nyfed_sce' if reason == 'source_out_of_scope' else 'ustr',
                    cap=.001 if reason == 'cap_insufficient' else .10, approved=reason != 'not_approved')
    if reason == 'changed_protocol': path.write_text(path.read_text()+'\n')
    monkeypatch.setattr(sys, 'argv', ['probe', '--folder', str(tmp_path)])
    with pytest.raises(ValueError): main()
    assert not (tmp_path/'execution_started.json').exists()
