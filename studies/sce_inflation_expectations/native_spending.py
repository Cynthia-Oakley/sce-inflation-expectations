"""Isolated native QSP5 treatment, using the existing audited SocioVerse decision.

No price index is calculated from broad spending categories. No attention or
inflation response coefficient is imposed. Inflation answers never enter here.
"""
from copy import deepcopy
from math import isfinite
from socioverse.engine import register
from .model import SCEDecision, build_sce_messages_v2
from .price_experience import canonical_hash, profile_hash
from .spending_audit import CATEGORIES

PROMPT_VERSION = 'sce-q8-q9-native-spending-v1'
SCHEMA = 'sce-native-spending-v1'
ARMS = ('withheld', 'actual', 'shuffled')
LABELS = ('housing (rent or mortgage, insurance, maintenance)', 'utilities',
          'food (groceries, dining out, beverages)', 'clothing and personal care',
          'transportation (gasoline, public transit, maintenance)', 'medical care',
          'recreation and entertainment', 'education and childcare', 'other expenditures')


def validate_bundle(bundle, personas, target_month):
    if set(bundle) != {'schema_version','research_line','target_month','arm','rows','source_sha256'}:
        raise ValueError('Unexpected native basket fields')
    if bundle['schema_version'] != SCHEMA or bundle['research_line'] != 'A_historical_reconstruction':
        raise ValueError('Native basket bundle is retrospective A only')
    if bundle['arm'] not in ARMS or bundle['target_month'] != target_month:
        raise ValueError('Native arm or target mismatch')
    if set(bundle['rows']) != {p.agent_id for p in personas}:
        raise ValueError('Native basket population coverage mismatch')
    for p in personas:
        check_row(bundle['rows'][p.agent_id], p.attributes, target_month, p.agent_id)
    return deepcopy(bundle)


def check_row(row, profile, target_month, agent_id):
    if set(row) != {'agent_id','profile_sha256','basket_month','shares_pct'} or row['agent_id'] != agent_id:
        raise ValueError('Native row input whitelist or ID mismatch')
    if row['profile_sha256'] != profile_hash(profile):
        raise ValueError('Native profile hash mismatch')
    year, month = map(int, target_month.split('-'))
    byear, bmonth = map(int, row['basket_month'].split('-'))
    age = (year-byear)*12 + month-bmonth
    if not 1 <= bmonth <= 12 or not 1 <= age <= 4:
        raise ValueError('Native basket must be an earlier wave at most four months old')
    shares = row['shares_pct']
    if set(shares) != set(CATEGORIES):
        raise ValueError('Native nine categories required')
    if any(type(v) not in (int,float) or not isfinite(v) or not 0 <= v <= 100 for v in shares.values()):
        raise ValueError('Native shares invalid')
    if abs(sum(shares.values())-100) > 1e-6:
        raise ValueError('Native shares do not sum to100; no normalization')


def build_messages(ob, bundle):
    target = ob.macro_information['target_month']
    if target != bundle['target_month'] or ob.local_information:
        raise ValueError('Native trial must have matching target and no other treatments')
    profile = ob.local_physical['profile']
    row = bundle['rows'][ob.agent_id]
    check_row(row, profile, target, ob.agent_id)
    messages = build_sce_messages_v2(ob, include_event_abstracts=True)
    marker = 'Question 1 (point estimate):'
    content = messages[0]['content']
    if content.count(marker) != 1:
        raise ValueError('Native insertion requires unchanged v2 questionnaire')
    if bundle['arm'] == 'withheld':
        block = ('Household spending context:\n'
                 '- A household expenditure breakdown is not provided. Do not infer precise shares from demographic labels.\n\n')
    else:
        block = f'Your household\'s last reported monthly spending breakdown ({row["basket_month"]}):\n'
        block += '\n'.join(f'- {label}: {row["shares_pct"][key]:g}% of total expenditure'
                           for label,key in zip(LABELS,CATEGORIES))
        block += ('\nThese are expenditure shares, not price changes or shopping frequency. '
                  'They describe an earlier month, not exact current spending. '
                  'Transportation is not solely gasoline, and housing is not solely rent. '
                  'The public economic information above remains available; these shares do not prescribe an inflation forecast.\n\n')
    pos = content.index(marker)
    messages[0]['content'] = content[:pos]+block+content[pos:]
    return messages


@register('decision','sce_inflation_expectations.native_spending_decision')
class NativeSpendingDecision(SCEDecision):
    def __init__(self, **decision_args):
        self.native_bundle = decision_args['native_spending_bundle']
        if self.native_bundle['schema_version'] != SCHEMA or self.native_bundle['research_line'] != 'A_historical_reconstruction':
            raise ValueError('Native schema/line mismatch')
        super().__init__(**decision_args)
        if self.llm_kind == 'openai' and self.prompt_version != PROMPT_VERSION:
            raise ValueError('Native decision requires native prompt')

    def build_llm_messages(self, ob):
        return build_messages(ob, self.native_bundle)

    def _decide_openai_one(self, ob):
        action = super()._decide_openai_one(ob)
        action.payload.update(native_spending_arm=self.native_bundle['arm'],
                              native_spending_bundle_sha256=canonical_hash(self.native_bundle),
                              p_snapshot_id=f"native_spending_{self.native_bundle['target_month']}_20261009",
                              research_line='A_historical_reconstruction')
        return action
