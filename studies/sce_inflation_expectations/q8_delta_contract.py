"""Q8-only response representation; Q9 probabilities are never transformed."""
from copy import deepcopy
from decimal import Decimal
import json
import math

ARMS = ('direct', 'q8_delta')


def object_from_text(text):
    text = (text or '').strip()
    if text.startswith('```'):
        text = text.strip('`').strip()
        if text.lower().startswith('json'):
            text = text[4:].strip()
    try:
        obj = json.loads(text)
    except ValueError:
        first, last = text.find('{'), text.rfind('}')
        if first < 0 or last <= first:
            raise ValueError('JSON object required')
        obj = json.loads(text[first:last+1])
    if not isinstance(obj, dict):
        raise ValueError('JSON object required')
    return obj


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Finite numeric Q8 required')
    return float(value)


def convert_response(text, arm, previous_point):
    if arm not in ARMS:
        raise ValueError('Unknown response arm')
    obj = object_from_text(text)
    delta = arm == 'q8_delta' and previous_point is not None
    expected = 'point_revision_pp' if delta else 'point_pct'
    forbidden = 'point_pct' if delta else 'point_revision_pp'
    if forbidden in obj or 'q9_revision_pp' in obj:
        raise ValueError('Wrong Q8/Q9 response representation')
    value = number(obj.get(expected))
    if delta:
        value = float(Decimal(str(number(previous_point)))+Decimal(str(value)))
        number(value)
    result = deepcopy(obj)
    result.pop('point_revision_pp', None)
    result['point_pct'] = value
    # No Q9 validation, clipping, rounding, normalization or replacement here.
    # The existing Q9 validator remains responsible for absolute probabilities.
    return result


def mapping_result(text, arm, previous_point):
    try:
        obj = convert_response(text, arm, previous_point)
    except (ValueError, TypeError, OverflowError) as exc:
        error = str(exc)
        return json.dumps({'mapping_error': error}), None, error
    try:
        return json.dumps(obj, ensure_ascii=False, allow_nan=False), obj['point_pct'], None
    except (ValueError, TypeError) as exc:
        error = str(exc)
        return json.dumps({'mapping_error': error}), obj['point_pct'], error


def candidate_contract(previous_point):
    missing = previous_point is None
    key = 'point_pct' if missing else 'point_revision_pp'
    instruction = (
        "point_pct: today's signed absolute point estimate, in percent inflation. "
        "Your previous point answer is missing; do not invent it or subtract a Q9 mean."
        if missing else
        "point_revision_pp: today's signed Q8 point estimate minus your earlier Q8 point estimate, "
        "in percentage points of inflation. For example, +1 changes 3% to 4%; "
        "-1 changes 3% to 2%. A negative change is permitted.")
    return ("Return today's answer, expressing Q8 as "+('an absolute value' if missing else 'a change')+
        ' and Q9 as absolute probabilities:\n- '+instruction+
        "\n- q9: today's probabilities in the same ten ranges, in percent probability, "
        'not changes from the earlier probabilities. Each must be 0 to 100, and all ten must sum to 100.\n\n'
        'Reply with ONLY a JSON object:\n{"'+key+'": <number>, "q9": {"bin1": <number>, "bin2": <number>,\n'
        ' "bin3": <number>, "bin4": <number>, "bin5": <number>, "bin6": <number>,\n'
        ' "bin7": <number>, "bin8": <number>, "bin9": <number>, "bin10": <number>},\n'
        ' "reason": "<one or two short sentences>"}\n')
