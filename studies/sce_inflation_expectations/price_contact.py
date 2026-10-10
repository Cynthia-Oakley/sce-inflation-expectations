"""Dated retail-price supplementation; geography assignment without answer tuning."""
from copy import deepcopy
from datetime import datetime
from math import isfinite
from socioverse.engine import register
from .model import SCEDecision, build_sce_messages_v2
from .price_experience import profile_hash, canonical_hash

PROMPT_VERSION = 'sce-q8-q9-price-contact-v1'
REF = 'sce_inflation_expectations.price_contact_decision'
ARMS = ('baseline', 'national', 'matched', 'shuffled')
STATE_GROUPS = {
    '1': 'CT ME MA NH RI VT DE DC MD NJ NY PA FL GA NC SC VA WV',
    '2': 'IL IN IA KS KY MI MN MO NE ND OH OK SD TN WI',
    '3': 'AL AR LA MS NM TX',
    '4': 'CO ID MT UT WY',
    '5': 'AK AZ CA HI NV OR WA',
}
STATE_PADD = {s: k for k, states in STATE_GROUPS.items() for s in states.split()}


def validate_bundle(bundle, personas, target):
    if set(bundle) != {'schema', 'research_line', 'target_month', 'as_of', 'arm', 'rows', 'prices'}:
        raise ValueError('Price-contact whitelist')
    if bundle['schema'] != 'sce-price-contact-v1' or bundle['research_line'] != 'A_historical_reconstruction':
        raise ValueError('Price-contact schema/line')
    if bundle['arm'] not in ARMS or bundle['target_month'] != target:
        raise ValueError('Price-contact arm/month')
    if set(bundle['rows']) != {p.agent_id for p in personas}:
        raise ValueError('Price-contact population coverage')
    for p in personas:
        row = bundle['rows'][p.agent_id]
        if set(row) != {'profile_sha256', 'shares', 'assigned_padd'}:
            raise ValueError('Price-contact row whitelist')
        if row['profile_sha256'] != profile_hash(p.attributes):
            raise ValueError('Price-contact profile binding')
        shares = row['shares']
        if set(shares) != {'food', 'gasoline', 'shelter', 'other'} or any(
            type(x) not in (float, int) or not isfinite(x) or not 0 <= x <= 1 for x in shares.values()
        ) or abs(sum(shares.values())-1) > 1e-8:
            raise ValueError('Price-contact synthetic shares')
        if row['assigned_padd'] not in STATE_GROUPS:
            raise ValueError('Price-contact region')
        if bundle['arm'] != 'shuffled' and row['assigned_padd'] != STATE_PADD[p.attributes['state']]:
            raise ValueError('Price-contact geographic matching')
    cutoff = datetime.fromisoformat(bundle['as_of'])
    if cutoff.utcoffset() is None:
        raise ValueError('Aware cutoff required')
    for key in ('gasoline', 'dairy'):
        price = bundle['prices'][key]
        date = datetime.fromisoformat(price['available_by'])
        if date.utcoffset() is None or date > cutoff:
            raise ValueError('Price-contact future/unknown publication')
    gas = bundle['prices']['gasoline']
    if set(gas['series']) != {'national', *STATE_GROUPS} or len(gas['dates']) != 12:
        raise ValueError('Price-contact gasoline coverage')
    if any(len(v) != 12 or any(not isfinite(x) or x <= 0 for x in v) for v in gas['series'].values()):
        raise ValueError('Price-contact gasoline values')
    if sorted(gas['dates']) != gas['dates'] or len(set(gas['dates'])) != 12 or any(d > gas['available_by'][:10] for d in gas['dates']):
        raise ValueError('Price-contact gasoline chronology')
    dairy = bundle['prices']['dairy']
    if len(dairy['items']) != 3 or any(len(x['prices']) != 3 or len(x['stores']) != 3 or any(v <= 0 for v in x['prices']+x['stores']) for x in dairy['items']):
        raise ValueError('Price-contact dairy coverage')
    return deepcopy(bundle)


def build_messages(ob, bundle):
    info = ob.macro_information
    if info['target_month'] != bundle['target_month'] or info['as_of'] != bundle['as_of'] or ob.local_information:
        raise ValueError('Price-contact isolated target required')
    row = bundle['rows'][ob.agent_id]
    if profile_hash(ob.local_physical['profile']) != row['profile_sha256']:
        raise ValueError('Price-contact profile drift')
    messages = build_sce_messages_v2(ob, include_event_abstracts=True)
    block = ('Household spending context (synthetic CE allocation; not your measured purchases):\n' +
             '\n'.join(f'- {k}: {v*100:.2f}% of expenditure' for k, v in row['shares'].items()) +
             '\nThese shares are not measured shopping frequency, price changes, or attention weights.\n')
    if bundle['arm'] != 'baseline':
        gas = bundle['prices']['gasoline']; dairy = bundle['prices']['dairy']
        group = 'national' if bundle['arm'] == 'national' else row['assigned_padd']
        name = 'U.S. national' if group == 'national' else f'PADD {group} regional'
        gastext = (f'Regular gasoline retail-price context ({name}; USD per gallon including tax):\n' +
                   '; '.join(f'{d}: {v:.3f}' for d, v in zip(gas['dates'], gas['series'][group])) +
                   f'\nSource: EIA dated report available by {gas["available_by"]}. '
                   'Market averages are a price-experience proxy, not your actual fill-up receipts.\n')
        foodtext = (f'Grocery advertised-price context (national conventional dairy, published {dairy["available_by"]}):\n' +
                    '\n'.join(f'- {x["label"]}: current ${x["prices"][0]:.2f}, previous week ${x["prices"][1]:.2f}, year-ago ${x["prices"][2]:.2f}; '
                              f'advertising stores {x["stores"][0]}/{x["stores"][1]}/{x["stores"][2]}' for x in dairy['items']) +
                    '\nThese are advertised special offers weighted by stores, not a same-store/same-product index or all-food inflation. '
                    'Promotions, brands and store composition can change.\n')
        ordered = [foodtext, gastext] if row['shares']['food'] >= row['shares']['gasoline'] else [gastext, foodtext]
        block += '\nRecent retail-price context:\n' + '\n'.join(ordered)
        block += ('\nBoth channels and the common economic background remain available. '
                  'No purchasing role, frequency, price attention coefficient or forecast is prescribed. '
                  'Past price movements are not the requested next-12-month inflation forecast.\n')
    marker = 'Question 1 (point estimate):'
    content = messages[0]['content']
    if content.count(marker) != 1:
        raise ValueError('Price-contact questionnaire insertion')
    pos = content.index(marker)
    messages[0]['content'] = content[:pos]+block+'\n'+content[pos:]
    return messages


@register('decision', REF)
class PriceContactDecision(SCEDecision):
    def __init__(self, **args):
        self.contact_bundle = args['price_contact_bundle']
        super().__init__(**args)
        if self.llm_kind == 'openai' and self.prompt_version != PROMPT_VERSION:
            raise ValueError('Price-contact prompt mismatch')

    def build_llm_messages(self, ob):
        return build_messages(ob, self.contact_bundle)

    def _decide_openai_one(self, ob):
        action = super()._decide_openai_one(ob)
        action.payload.update(price_contact_arm=self.contact_bundle['arm'],
                              price_contact_bundle_sha256=canonical_hash(self.contact_bundle),
                              research_line='A_historical_reconstruction')
        return action
