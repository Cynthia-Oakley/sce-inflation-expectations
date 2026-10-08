"""Format-only correction for annual comparisons; no probability normalization."""
import copy
import json
import math
from collections import Counter


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def raw_object(text):
    text = text.strip()
    if text.startswith('```'):
        text = text.strip('`').strip()
        if text.startswith('json'):
            text = text[4:].strip()
    try:
        obj = json.loads(text)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def repair_messages(messages, raw_text):
    """Return feedback messages and protected point estimate, or unchanged retry.

    Only numeric ten-bin replies with an incorrect total receive feedback.
    We do not change their probabilities or feed any real survey answer back.
    """
    obj = raw_object(raw_text)
    if not obj or not number(obj.get('point_pct')) or not isinstance(obj.get('q9'), dict):
        return copy.deepcopy(messages), None
    bins = [obj['q9'].get(f'bin{i}') for i in range(1, 11)]
    if not all(number(v) and 0 <= v <= 100 for v in bins):
        return copy.deepcopy(messages), None
    total = sum(bins)
    if math.isclose(total, 100, abs_tol=1e-6, rel_tol=0):
        return copy.deepcopy(messages), None
    point = obj['point_pct']
    feedback = (f'The ten probabilities in your preceding reply add up to {total:g}, not 100. '
        'Correct only this questionnaire probability allocation so all ten bins sum to exactly 100. '
        f'Keep your point_pct exactly {point:g}; do not change your economic judgment or use new information. '
        'Return the complete JSON object in the originally requested format, without explanation outside JSON.')
    return [*copy.deepcopy(messages), {'role': 'assistant', 'content': raw_text},
        {'role': 'user', 'content': feedback}], point


def guarded_annual_payload(row):
    payload = row['payload']
    if payload.get('temperature') != .5 or payload.get('max_tokens') != 1024 or payload.get('response_format') != {'type': 'json_object'}:
        raise ValueError('annual generation parameters changed')
    if row['destination'] == 'https://api.deepseek.com/v1':
        if payload.get('model') != 'deepseek-flash' or payload.get('thinking') != {'type': 'disabled'} or 'provider' in payload:
            raise ValueError('DeepSeek identity/options changed')
    elif row['destination'] == 'https://openrouter.ai/api/v1':
        routes = {'qwen/qwen-2.5-72b-instruct': 'deepinfra/fp8',
            'meta-llama/llama-3.1-70b-instruct': 'deepinfra/turbo',
            'meta-llama/llama-3.3-70b-instruct': 'deepinfra/turbo'}
        route = routes.get(payload.get('model'))
        if not route or row.get('route_candidate') != route or payload.get('provider') != {
            'order': [route], 'allow_fallbacks': False, 'require_parameters': True} or 'thinking' in payload:
            raise ValueError('OpenRouter identity/route changed')
    else:
        raise ValueError('unapproved annual destination')
    if set(payload) - {'model', 'messages', 'temperature', 'max_tokens', 'response_format', 'provider', 'thinking'}:
        raise ValueError('unexpected API payload fields')
    return copy.deepcopy(payload)


def validated_answer(raw_text, protected_point=None):
    from .model import parse_sce_response, validate_sce_bins
    obj = raw_object(raw_text)
    if obj:
        q9 = obj.get('q9')
        if type(obj.get('point_pct')) is bool or (isinstance(q9, dict) and any(type(v) is bool for v in q9.values())):
            return None, 'boolean_is_not_a_numeric_answer'
    parsed, error = parse_sce_response(raw_text)
    if not error and not number(parsed['point_pct']):
        error = 'nonfinite_point'
    if not error:
        _, error, _ = validate_sce_bins(parsed['bins'])
    if not error and protected_point is not None and parsed['point_pct'] != protected_point:
        error = 'format_repair_changed_point_estimate'
    return (None, error) if error else (parsed, None)


def prior_annual_calls(calls, summary):
    """Carry all costs forward; never regenerate a successful model/case."""
    fees = [c['billing']['charged_or_reserved_usd'] for c in calls]
    if any(not number(fee) or fee < 0 for fee in fees):
        raise ValueError('invalid prior fee')
    spent = sum(fees)
    if not number(spent) or not math.isclose(spent, summary['spent_or_reserved_usd'], abs_tol=1e-10):
        raise ValueError('annual resume budget differs from original log')
    if summary.get('paid_attempts', len(calls)) != len(calls):
        raise ValueError('annual resume attempt count differs from original log')
    done = set()
    attempts = Counter()
    costs = Counter()
    last = {}
    for call in calls:
        key = (call['requested_model'], call['case_id'])
        attempts[key] += 1
        costs[key[0]] += call['billing']['charged_or_reserved_usd']
        last[key] = call
        if 'answer' in call and not call.get('error'):
            if key in done:
                raise ValueError('duplicate valid model/case')
            done.add(key)
    return spent, done, attempts, costs, last
