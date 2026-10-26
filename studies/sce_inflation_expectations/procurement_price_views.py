"""Offline shopping-role / national price-proxy views. No targets or API client.

The role instrument measures grocery responsibility, not driving or all purchases.
The view is a synthetic information exposure, never an observed personal receipt.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import re
import unicodedata

import numpy as np

FOOD_CATEGORIES = {
    'cereals_bakery': 'Cereals and bakery products',
    'meat_fish_eggs': 'Meats, poultry, fish, and eggs',
    'dairy': 'Dairy and related products',
    'fruit_vegetables': 'Fruits and vegetables',
    'nonalcoholic_drinks': 'Nonalcoholic beverages and beverage materials',
    'other_food': 'Other food at home',
}
RESERVE_CATEGORIES = {
    'cleaning': 'Household cleaning products',
    'paper': 'Household paper products',
    'personal_care': 'Personal care products',
}
ROLE_TEXT = {
    1: 'You do none of the usual grocery shopping for your household.',
    2: 'You do a little of the usual grocery shopping for your household.',
    3: 'You do some of the usual grocery shopping for your household.',
    4: 'You do a lot of the usual grocery shopping for your household.',
    5: 'You do all of the usual grocery shopping for your household.',
}
# Experimental exposure levels, NOT ATUS-estimated counts or shopping frequency.
DETAIL_COUNT = {1: 0, 2: 1, 3: 3, 4: 6, 5: 6}
NUMERICAL = 'Recent official statistics:\n'
BASKET = 'Synthetic household spending context (not your observed receipts):\n'
PRIOR = 'Your earlier survey response ('
NEWS = 'General news you encountered:\n'
POLICY = 'Public policy news brief ('
TIMING = 'Publication timing for the same information above:\n'


def table_text(pages, number):
    text = unicodedata.normalize('NFKC', '\n'.join(pages))
    # partition, not split()[1]: repeated page headings belong to the same table.
    marker = f'Table {number}. Consumer Price Index'
    if marker not in text:
        raise ValueError('Missing table heading')
    text = text.partition(marker)[2]
    following = f'Table {number + 1}. Consumer Price Index'
    text = text.partition(following)[0]
    return re.sub(r'\s+', ' ', text)


def row_values(text, label, width):
    expression = re.escape(label).replace(r'\ ', r'\s+')
    expression += r'\s*(?:[1-9](?:\s*,\s*[1-9])*)?\s*(?:\.\s*){2,}'
    matches = list(re.finditer(expression, text))
    if len(matches) != 1:
        raise ValueError(f'Expected one exact table row: {label}, found {len(matches)}')
    tail = text[matches[0].end():]
    pattern = r'\s*'.join([r'(-?\d+\.\d+)'] * width)
    values = re.match(pattern + r'(?=\s|$)', tail)
    if values is None:
        raise ValueError('Missing or nonnumeric table cells: ' + label)
    return [float(v) for v in values.groups()], text[matches[0].start():matches[0].end()+values.end()]


def extract_categories(pages):
    """Table2: weight, YoY NSA, MoM NSA, three MoM SA. Cross-check other tables."""
    tables = {n: table_text(pages, n) for n in (1, 2, 7)}
    result = {}
    for key, label in {'food_at_home': 'Food at home', **FOOD_CATEGORIES, **RESERVE_CATEGORIES}.items():
        values, raw = row_values(tables[2], label, 6)
        yoy, raw7 = row_values(tables[7], label, 2)
        if values[1] != yoy[1]:
            raise ValueError('Table2 / Table7 YoY mismatch: ' + label)
        cross = {'table7_yoy_nsa': yoy[1]}
        if key == 'food_at_home' or key in FOOD_CATEGORIES:
            main, _ = row_values(tables[1], label, 9)
            if main[4:6] != values[1:3]:
                raise ValueError('Table1 / Table2 YoY or MoM mismatch: ' + label)
            cross['table1_yoy_mom_nsa'] = main[4:6]
        result[key] = {'category': key, 'label': label,
            'yoy_nsa_percent': values[1], 'mom_nsa_percent': values[2],
            'mom_sa_percent': values[5], 'source_table': 2,
            'exact_extracted_row': raw, 'crosscheck_table7_row': raw7, 'crosschecks': cross,
            'scope': 'US city average CPI-U category, not a respondent transaction',
            'use': 'grocery_exposure_candidate' if key in FOOD_CATEGORIES else 'shared_aggregate' if key == 'food_at_home' else 'reserve_no_role_link'}
    return result


def validate_cutoff(facts, as_of):
    cutoff = datetime.fromisoformat(as_of)
    if cutoff.tzinfo is None:
        raise ValueError('Aware cutoff required')
    for fact in facts:
        when = datetime.fromisoformat(fact['published_at'])
        if when.tzinfo is None or when > cutoff:
            raise ValueError('Undated or future price')


def choose_categories(role, person_key, seed):
    if role not in DETAIL_COUNT:
        raise ValueError('Unknown grocery role')
    # Price values and current answers are intentionally absent from this API.
    order = sorted(FOOD_CATEGORIES, key=lambda k: hashlib.sha256(
        f'{seed}|{person_key}|{k}|grocery-category'.encode()).hexdigest())
    return order[:DETAIL_COUNT[role]]


def rate(value, period):
    direction = 'increased' if value > 0 else 'decreased' if value < 0 else 'were unchanged'
    return (f'{direction} {abs(value):.1f}% {period}' if value else f'{direction} {period}')


def fact_line(fact):
    # Both changes are unadjusted. Never relabel a one-month change as annualized.
    if fact['mom_nsa_percent'] is None:
        return (f"- {fact['label']}: month-to-month change was not published; "
            f"{rate(fact['yoy_nsa_percent'], 'from the same month a year earlier')}. "
            f"Reference month {fact['reference_period']} (not seasonally adjusted).")
    return (f"- {fact['label']}: {rate(fact['mom_nsa_percent'], 'from the previous month')}; "
        f"{rate(fact['yoy_nsa_percent'], 'from the same month a year earlier')}. "
        f"Reference month {fact['reference_period']} (not seasonally adjusted).")


def render_view(role, categories, facts, timing_status):
    if role is None:
        if categories:
            raise ValueError('Shared aggregate control has no assigned role details')
        role_line = 'No additional grocery-shopping role or category exposure is assigned in this control.'
    else:
        if role not in ROLE_TEXT or len(categories) != DETAIL_COUNT[role] or len(set(categories)) != len(categories):
            raise ValueError('Role/view inconsistency')
        role_line = ROLE_TEXT[role]
    if set(categories) - set(FOOD_CATEGORIES):
        raise ValueError('Grocery role cannot establish cleaning, driving or other purchases')
    aggregate = facts['food_at_home']
    lines = ['Household grocery context for this simulation:', role_line,
        'National category prices proxy the information available here; they are not your actual receipts.',
        'General grocery-price background:', fact_line(aggregate)]
    if categories:
        lines += ['Additional grocery categories in your information view:']
        lines.extend(fact_line(facts[k]) for k in categories)
    lines += [f"BLS release {aggregate['published_at']}; availability relative to your previous survey: {timing_status}."]
    return '\n'.join(lines)+'\n\n'


def transform_prompt(messages, view):
    """Hold news, prior, questions and all other persona/state bytes unchanged.

    All three new arms remove the same full public numerical table. This changes
    their common base and requires a NEW concurrent control; no archived answer
    is claimed reusable for the new shared-control arm.
    """
    if len(messages) != 1 or messages[0]['role'] != 'user':
        raise ValueError('One user message required')
    original = messages[0]['content']
    for marker in (NUMERICAL, BASKET, NEWS, POLICY, TIMING, PRIOR):
        if original.count(marker) != 1:
            raise ValueError('Missing or duplicate prompt boundary: '+marker)
    a, b = original.index(NUMERICAL), original.index(BASKET)
    if a >= b:
        raise ValueError('Reversed statistics boundary')
    text = original[:a]+view+original[b:]
    lines = text.splitlines(keepends=True)
    text = ''.join(line.replace(' The rolling trends above span both earlier and later releases.', '')
        for line in lines if not line.startswith(('- CPI figures,', '- employment figures,', '- gasoline price figures,')))
    if NUMERICAL in text or 'Recent trends (' in text:
        raise ValueError('Full statistics survived')
    if text[text.index(PRIOR):] != original[original.index(PRIOR):]:
        raise ValueError('Prior/state/questionnaire changed')
    if text[text.index(NEWS):text.index(POLICY)] != original[original.index(NEWS):original.index(POLICY)]:
        raise ValueError('News changed')
    result = deepcopy(messages); result[0]['content'] = text
    return result


def balanced_bundle_shuffle(bundles, weights, seed, max_draws=20000):
    """Permute whole role/category bundles within month; no outcome access.

    Equal unweighted multiset exactly. Proposals permute within adjacent
    survey-weight ranks (blocks of 12) so a heavy respondent does not change
    the total information mass merely by receiving another bundle. This is a
    weight-conditioned placebo, not unconstrained population randomization.
    """
    n = len(bundles); w = np.asarray(weights, float)
    if n < 2 or len(w) != n or not np.isfinite(w).all() or (w <= 0).any():
        raise ValueError('At least two bundles and finite positive weights required')
    w = w/w.sum()
    features = np.array([[len(b['categories']), len(b['view'].encode()),
        *[k in b['categories'] for k in FOOD_CATEGORIES],
        *[b['role'] == r for r in ROLE_TEXT]] for b in bundles], float)
    reference = w@features; rng = np.random.default_rng(seed)
    order = np.argsort(w, kind='stable')
    blocks = np.array_split(order, max(1, n//12))
    for attempt in range(1, max_draws+1):
        ix = np.arange(n)
        for block in blocks:
            ix[block] = rng.permutation(block)
        candidate = w@features[ix]
        relative = np.abs(candidate[:2]-reference[:2])/np.maximum(reference[:2], 1.)
        absolute = np.abs(candidate[2:]-reference[2:])
        if not np.array_equal(ix,np.arange(n)) and max(relative) <= .01 and max(absolute) <= .02:
            return ix, {'attempts': attempt, 'weighted_detail_count_relative_gap': float(relative[0]),
                'weighted_view_bytes_relative_gap': float(relative[1]),
                'max_category_and_role_share_absolute_gap': float(max(absolute)),
                'same_bundle_fraction': float(np.mean(ix == np.arange(n))),
                'proposal': 'within adjacent survey-weight rank blocks of about 12',
                'weight_rank_block_sizes': [len(block) for block in blocks],
                'same_role_fraction': float(np.mean([bundles[i]['role']==bundles[j]['role'] for i,j in enumerate(ix)]))}
    raise ValueError('No balanced permutation; do not relax thresholds automatically')
