"""Isolated observed-prior diagnostic; no current-answer or reference-file reads."""
from copy import deepcopy
import hashlib
import json

from socioverse.engine import register
from .confidence_experiment import build_messages as baseline_messages, validate_bundle as validate_baseline
from .model import SCEDecision
from .prior_belief_preparation import ARMS, add_prior

REF = 'sce_inflation_expectations.prior_belief_decision'
PROMPT_VERSION = 'sce-q8-q9-observed-prior-v1'
SCHEMA = 'sce-observed-prior-diagnostic-v1'
LINE = 'A_observed_prior_conditional_update'


def message_hash(messages):
    return hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()


def validate_bundle(bundle, personas, target, as_of):
    if (set(bundle) != {'schema_version', 'research_line', 'target_month', 'as_of', 'arm', 'baseline', 'rows'}
            or bundle['schema_version'] != SCHEMA or bundle['research_line'] != LINE
            or bundle['arm'] not in ARMS or bundle['target_month'] != target or bundle['as_of'] != as_of):
        raise ValueError('prior schema/line/month/arm mismatch')
    validate_baseline(bundle['baseline'], personas, target, as_of)
    if bundle['baseline']['arm'] != 'national_confidence' or set(bundle['rows']) != {p.agent_id for p in personas}:
        raise ValueError('prior baseline or roster mismatch')
    for row in bundle['rows'].values():
        if set(row) != {'prior', 'baseline_messages_sha256', 'messages_sha256'}:
            raise ValueError('unexpected prior row field')
        if any(not isinstance(row[k], str) or len(row[k]) != 64 for k in ('baseline_messages_sha256', 'messages_sha256')):
            raise ValueError('message hashes required')
        if bundle['arm'] == 'no_prior':
            if row['prior'] is not None or row['baseline_messages_sha256'] != row['messages_sha256']:
                raise ValueError('no-prior row changed')
        else:
            # The existing insertion helper enforces t-1, ten-bin order,
            # exact probability sum and a signed legal optional Q8.
            add_prior([{'role': 'user', 'content': 'Question 1 (point estimate):'}],
                      row['prior'], int(target.replace('-', '')))
    return deepcopy(bundle)


def build_messages(ob, bundle):
    base = baseline_messages(ob, bundle['baseline'])
    row = bundle['rows'][ob.agent_id]
    if message_hash(base) != row['baseline_messages_sha256']:
        raise ValueError('actual baseline P/E or questionnaire changed')
    messages = base if bundle['arm'] == 'no_prior' else add_prior(
        base, row['prior'], int(bundle['target_month'].replace('-', '')))[0]
    if message_hash(messages) != row['messages_sha256']:
        raise ValueError('actual prior message differs from frozen preparation')
    return messages


@register('decision', REF)
class PriorBeliefDecision(SCEDecision):
    def __init__(self, **args):
        if args.get('prompt_version') != PROMPT_VERSION:
            raise ValueError('prior provider/prompt mismatch')
        self.prior_bundle = args['prior_bundle']
        super().__init__(**args)

    def build_llm_messages(self, ob):
        return build_messages(ob, self.prior_bundle)

    def _decide_scripted(self, obs):
        for ob in obs:
            self.build_llm_messages(ob)
        return super()._decide_scripted(obs)

    def _decide_openai_one(self, ob):
        action = super()._decide_openai_one(ob)
        action.payload.update(prior_arm=self.prior_bundle['arm'], research_line=LINE,
                              p_snapshot_id='prior_12_age_balanced_20261013',
                              e_snapshot_id='frozen_confidence_environment_' + self.prior_bundle['target_month'],
                              prior_messages_sha256=self.prior_bundle['rows'][ob.agent_id]['messages_sha256'])
        return action
