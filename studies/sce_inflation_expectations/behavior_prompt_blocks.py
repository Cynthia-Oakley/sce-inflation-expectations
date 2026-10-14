"""Offline candidate mechanism blocks. Not registered with any live provider."""
from copy import deepcopy

from .prior_belief_preparation import MARKER, PRIOR_MARKER

LABELS={
    'food_at_home':'groceries for home',
    'food_away_from_home':'food away from home',
    'household_supplies_services':'household supplies and services',
    'personal_care_products_services':'personal-care products and services',
}

ANCHOR_BLOCK=(
    'Belief update instruction:\n'
    'Your previous survey records your own belief, not an economic news item or someone else\'s forecast. '
    'It is the starting point for your current view. Use the new information to judge whether to retain it or revise it; '
    'an unchanged answer is allowed. The forecast window advances by one month. '
    'No fixed amount of adjustment is required.\n\n'
)


def frequency_block(categories):
    """Render a complete four-category proxy; partial supports are not set to zero."""
    lines=[]
    for key,label in LABELS.items():
        row=categories[key]
        number=row['recorded_days_7d']
        if row['status'] not in {'available','no_positive_published_records'} or isinstance(number,bool) or not isinstance(number,int) or not 0<=number<=7:
            raise ValueError('complete supported category-day vector required')
        lines.append(f'- {label}: positive published spending recorded on {number} of 7 days.')
    if not any(categories[key]['recorded_days_7d']>0 for key in LABELS):
        raise ValueError('no supported positive contact in the four-category vector')
    return (
        'Assigned shopping-contact profile (synthetic, based on a matched CE Diary household-week):\n'
        +'\n'.join(lines)+'\n'
        'These counts describe recorded purchase days, not purchases per day or every price you encountered.\n'
        'When forming your impression of inflation, give more attention and more influence to price changes in the '
        'categories you purchase more frequently. Use this profile to weigh the supplied price evidence. '
        'Judge whether these changes can persist over the next 12 months; other information can still affect your view.\n\n'
    )


def insert_block(messages, block, *, require_prior=False):
    """Add one tested mechanism immediately before the unchanged questionnaire."""
    result=deepcopy(messages)
    if len(result)!=1 or result[0].get('role')!='user' or set(result[0])!={'role','content'}:
        raise ValueError('one frozen user message required')
    text=result[0]['content']
    if text.count(MARKER)!=1 or 'Belief update instruction:' in text or 'Assigned shopping-contact profile (' in text:
        raise ValueError('question boundary or existing mechanism block')
    if (require_prior or block==ANCHOR_BLOCK) and text.count(PRIOR_MARKER)!=1:
        raise ValueError('explicit own/synthetic prior state required; no invented prior')
    if block not in {ANCHOR_BLOCK} and not block.startswith('Assigned shopping-contact profile ('):
        raise ValueError('unknown mechanism block')
    before,after=text.split(MARKER,1)
    result[0]['content']=before+block+MARKER+after
    return result
