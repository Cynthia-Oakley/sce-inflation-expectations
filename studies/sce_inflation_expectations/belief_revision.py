"""Draft revision-format adapter, isolated from every frozen runtime/provider.

Represent an answer by changes relative to its own previous answer. This does
not restrict the new answer: every valid Q8/Q9 answer has a revision form. It
does not fit an updating weight, force unchanged beliefs or widen dispersion.
"""
from decimal import Decimal
import math

BINS = tuple(f'bin{i}' for i in range(1, 11))


def _decimal(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Finite numeric value required')
    return Decimal(str(value))


def _probabilities(answer):
    if set(answer['q9']) != set(BINS):
        raise ValueError('Exactly ten Q9 bins required')
    values = [_decimal(answer['q9'][key]) for key in BINS]
    if any(p < 0 or p > 100 for p in values) or abs(sum(values)-100) > Decimal('0.000001'):
        raise ValueError('Invalid probability answer')
    _decimal(answer['point_pct'])
    return values


def answer_to_revision(previous, current):
    old, new = _probabilities(previous), _probabilities(current)
    return {'point_revision_pp': float(_decimal(current['point_pct'])-_decimal(previous['point_pct'])),
            'q9_revision_pp': {key: float(b-a) for key, a, b in zip(BINS, old, new)}}


def revision_to_answer(previous, revision):
    old = _probabilities(previous)
    if set(revision['q9_revision_pp']) != set(BINS):
        raise ValueError('Exactly ten probability revisions required')
    change = [_decimal(revision['q9_revision_pp'][key]) for key in BINS]
    if abs(sum(change)) > Decimal('0.000001'):
        raise ValueError('Probability revisions must sum to zero; never renormalized')
    answer = {'point_pct': float(_decimal(previous['point_pct'])+_decimal(revision['point_revision_pp'])),
              'q9': {key: float(a+d) for key, a, d in zip(BINS, old, change)}}
    _probabilities(answer)  # Reject invalid mass; never clip, round or repair it.
    return answer


REVISION_INSTRUCTION = '''Revision-format response for the SAME questions and ten ranges:
Use your earlier survey response as a starting state. The forecast window has
advanced by one month, so today's next-12-month period differs from last month's.
Decide what, if anything, you would change using the information available now.
Information marked earlier was publicly available; that does not establish that
you personally knew it. Keeping a belief or revising it upward or downward is
allowed. There is no required adjustment size or direction.

Return changes rather than a newly typed absolute answer:
- point_revision_pp: today's signed point estimate minus your earlier point
  estimate, in percentage points of inflation. +1 means changing 3% to 4%.
- q9_revision_pp: for each bin, today's probability minus your earlier probability,
  in percentage points of probability. +5 means changing 20% to 25%, not raising
  the inflation rate by 5 points. The ten changes must sum to zero. Adding each
  change to that bin's earlier probability must leave a number between 0 and 100.
  All zero changes are permitted; they are not required.

Reply with ONLY a JSON object:
{"point_revision_pp": <number>,
 "q9_revision_pp": {"bin1": <number>, "bin2": <number>, "bin3": <number>,
 "bin4": <number>, "bin5": <number>, "bin6": <number>, "bin7": <number>,
 "bin8": <number>, "bin9": <number>, "bin10": <number>},
 "reason": "<one or two short sentences>"}
'''


def draft_revision_messages(messages):
    """Keep actual P/E/prior/question wording; change only response instructions."""
    if len(messages) != 1 or messages[0]['role'] != 'user':
        raise ValueError('Single-user frozen preview expected')
    text = messages[0]['content']
    if text.count('Reply with ONLY a JSON object') != 1 or 'Your earlier survey response' not in text:
        raise ValueError('Unsupported source prompt, stop instead of guessing')
    context = text.split('Reply with ONLY a JSON object', 1)[0]
    return [{'role': 'user', 'content': context+REVISION_INSTRUCTION}]
