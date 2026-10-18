#!/usr/bin/env python3
"""Read the free Event MCP catalog without fetching metered source data."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from check_mcp_free_capabilities import McpHttpClient, gen_mcp_json, redact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('Use a fresh catalog directory')
    env = gen_mcp_json.load_env()
    endpoint = env.get('SV_EVENT_API_URL', '')
    parts = urlsplit(endpoint)
    if parts.scheme != 'https' or parts.hostname != 'mcp.socioverse.fudan-disc.com':
        raise ValueError('Expected the configured official HTTPS Event MCP host')
    if not env.get('SV_EVENT_API_KEY'):
        raise ValueError('Missing local Event MCP credential')
    client = McpHttpClient(endpoint, env['SV_EVENT_API_KEY'])
    result = {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'destination_host': parts.hostname, 'paid_source_calls': 0,
              'operations': ['initialize', 'tools/list', 'list_sources']}
    result['initialize'] = redact(client.initialize())
    result['tools'] = redact(client.list_tools())
    result['catalog'] = redact(client.call_tool('list_sources', {}))
    args.out.mkdir(parents=True)
    target = args.out/'catalog.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    names = [r.get('name') for r in result['catalog'].get('sources', [])]
    print(json.dumps({'status': 'free_catalog_complete', 'sources': names,
                      'server': result['initialize'].get('serverInfo'),
                      'paid_source_calls': 0, 'out': str(target),
                      'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
