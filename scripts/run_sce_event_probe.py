#!/usr/bin/env python3
"""Execute a protocol-bound, approved Event data probe once, with no retries."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from check_mcp_free_capabilities import McpHttpClient, gen_mcp_json

ALLOWED = {'ustr', 'google_trends', 'household_pulse', 'fred'}
SENSITIVE = re.compile(r'^(?:api[_-]?key|authorization|password|secret|token|access_token|refresh_token|credential|credentials)$', re.I)


def now():
    return datetime.now(timezone.utc).isoformat()


def sanitize(value, key):
    if isinstance(value, dict):
        return {k: '<redacted>' if SENSITIVE.fullmatch(k) else sanitize(v, key) for k,v in value.items()}
    if isinstance(value, list):
        return [sanitize(v, key) for v in value]
    if isinstance(value, str):
        return re.sub(r'(?i)(api[_-]?key|token|authorization)=([^\s&]+)', r'\1=<redacted>', value.replace(key, '<redacted>'))
    return value


def append(path, row):
    with path.open('a') as stream:
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')
        stream.flush(); os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', required=True, type=Path)
    args = parser.parse_args(); folder = args.folder
    raw = (folder/'protocol.json').read_bytes(); protocol = json.loads(raw)
    digest = hashlib.sha256(raw).hexdigest()
    authorization = json.loads((folder/'authorization.json').read_text())
    if not authorization.get('approved') or authorization['protocol_sha256'] != digest:
        raise ValueError('Missing approval for this exact protocol')
    if authorization['cap_usd'] < protocol['hard_cap_usd']:
        raise ValueError('Approved cap is insufficient')
    if protocol['automatic_retries'] != 0 or protocol['planned_calls'] != len(protocol['jobs']):
        raise ValueError('Unexpected retry/count settings')
    if len(protocol['jobs'])*protocol['unit_price_usd_email'] > protocol['hard_cap_usd']:
        raise ValueError('Conservative attempt reservation exceeds cap')
    for job in protocol['jobs']:
        a = job['arguments']
        if job['tool'] != 'get_source_detail' or a['source'] not in ALLOWED:
            raise ValueError('Source/tool outside approved allowlist')
        if a['source'] == 'fred' and a.get('series') != 'UMCSENT':
            raise ValueError('FRED scope must be UMCSENT only')
    env = gen_mcp_json.load_env(); endpoint = env.get('SV_EVENT_API_URL', ''); key = env.get('SV_EVENT_API_KEY', '')
    parsed = urlsplit(endpoint)
    if parsed.scheme != 'https' or parsed.hostname != protocol['destination_host'] or not key:
        raise ValueError('Unexpected destination or missing local credential')
    marker = folder/'execution_started.json'
    with marker.open('x') as stream:
        json.dump({'started_at_utc': now(), 'protocol_sha256': digest,
                   'no_resume': 'Already-started batches are never automatically restarted.'}, stream)
    client = McpHttpClient(endpoint, key)
    metadata = sanitize(client.initialize(), key)
    (folder/'server.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n')
    ledger = folder/'ledger.jsonl'; started = now(); statuses = []
    for index, job in enumerate(protocol['jobs'], 1):
        append(ledger, {'event': 'attempt_started', 'job_id': job['job_id'], 'index': index,
                        'at_utc': now(), 'arguments': job['arguments'], 'reserved_usd': protocol['unit_price_usd_email']})
        try:
            response = sanitize(client.call_tool(job['tool'], job['arguments']), key)
            path = folder/f"raw_{job['job_id']}.json"
            path.write_text(json.dumps(response, ensure_ascii=False, indent=2)+'\n')
            status = response.get('status', 'received')
            event = {'event': 'attempt_completed', 'job_id': job['job_id'], 'index': index,
                     'at_utc': now(), 'status': status, 'raw_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        except Exception as exc:
            event = {'event': 'attempt_completed', 'job_id': job['job_id'], 'index': index,
                     'at_utc': now(), 'status': 'transport_or_tool_error_no_retry',
                     'error_type': type(exc).__name__, 'http_status': getattr(exc, 'code', None)}
        append(ledger, event); statuses.append(event)
        print(json.dumps({'job': job['job_id'], 'status': event['status'], 'attempt': index, 'retry': 0}), flush=True)
    result = {'status': 'completed_all_planned_attempts', 'protocol_sha256': digest,
              'started_at_utc': started, 'finished_at_utc': now(), 'attempts': len(statuses),
              'maximum_estimated_charge_usd_not_bill': len(statuses)*protocol['unit_price_usd_email'],
              'cap_usd': protocol['hard_cap_usd'], 'automatic_retries': 0, 'simulation_calls': 0,
              'note': 'All attempted calls conservatively reserved; failed calls may be free under organizer terms. No provider bill obtained.',
              'jobs': statuses}
    (folder/'completion.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    main()
