"""Guards for an exact-message OpenRouter model comparison; no I/O or API calls."""
from __future__ import annotations

import copy
import json
import math


def request_bound(payload, price_in, price_out):
    # Byte-token upper envelope plus room for the server's chat template.
    size = len(json.dumps(payload['messages'], ensure_ascii=False).encode('utf-8'))
    return ((size + 1024) * price_in + payload['max_tokens'] * price_out) / 1e6


def guarded_payload(row):
    payload = copy.deepcopy(row['payload'])
    route = row['route_candidate']
    if payload['provider'] != {'order': [route], 'allow_fallbacks': False,
                               'require_parameters': True}:
        raise ValueError('provider lock differs from prepared request')
    if payload['temperature'] != .5 or payload['max_tokens'] != 1024:
        raise ValueError('reference sampling parameters changed')
    if payload['response_format'] != {'type': 'json_object'}:
        raise ValueError('JSON contract changed')
    payload['provider']['max_price'] = {
        'prompt': row['input_price_per_million'],
        'completion': row['output_price_per_million'],
    }
    return payload


def preflight(row, directory, *, allow_degraded=False):
    endpoint = next((e for e in directory['data']['endpoints']
                     if e['tag'] == row['route_candidate']), None)
    if not endpoint:
        raise ValueError('locked_route_not_listed')
    status = endpoint.get('status', -1)
    if status != 0:
        uptime = endpoint.get('uptime_last_30m')
        if not (allow_degraded and status == -2 and type(uptime) in (int, float)
                and math.isfinite(uptime) and 80 <= uptime <= 100):
            raise ValueError('locked_route_status_not_accepted')
    required = {'response_format', 'temperature', 'max_tokens'}
    if not required.issubset(endpoint.get('supported_parameters', [])):
        raise ValueError('locked_route_missing_parameters')
    prices = endpoint['pricing']
    for name, key in [('prompt', 'input_price_per_million'),
                      ('completion', 'output_price_per_million')]:
        actual = float(prices[name]) * 1e6
        if not math.isfinite(actual) or actual > row[key] + 1e-12:
            raise ValueError('locked_route_price_increased')
    if float(prices.get('request', 0)) != 0:
        raise ValueError('unexpected_per_request_price')
    return endpoint


def billing(response, row, bound):
    usage = response.get('usage') or {}
    cost = usage.get('cost')
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        if math.isfinite(cost) and cost >= 0:
            return {'charged_or_reserved_usd': float(cost), 'kind': 'api_reported_cost',
                    'usage': usage, 'uncertain': False}
    pin, pout = usage.get('prompt_tokens'), usage.get('completion_tokens')
    if all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in [pin, pout]):
        estimate = (pin * row['input_price_per_million']
                    + pout * row['output_price_per_million']) / 1e6
        return {'charged_or_reserved_usd': estimate, 'kind': 'token_usage_estimate',
                'usage': usage, 'uncertain': False}
    return {'charged_or_reserved_usd': bound, 'kind': 'unknown_cost_reserved',
            'usage': {}, 'uncertain': True}


def fits_budget(total, model_total, bound, *, total_cap=.50, model_cap=.25):
    values = [total, model_total, bound, total_cap, model_cap]
    if not all(math.isfinite(v) and v >= 0 for v in values):
        raise ValueError('invalid budget accounting')
    return total + bound <= total_cap and model_total + bound <= model_cap
