"""U1 explicit personal-state diagnostic; reuses the executed U0 base.

Two arms (spec v2, docs/workstreams/20261013_behavior/kimi_u1_input_spec.md):
- own_state (U1s): executed own_previous prompt + source-labeled state summary.
- own_state_guided (U1g): U1s + one update-hypothesis sentence (only when the
  person has a usable anchor).

The bundle carries, per person, the frozen prior payload (validated by the
existing add_prior helper), the frozen state block text, and three hashes:
the engine-rebuilt baseline, the executed U0 prompt, and the frozen U1 prompt.
build_messages reconstructs base -> U0 -> U1 and asserts every link.
"""
from copy import deepcopy
import json

from socioverse.engine import register
from .confidence_experiment import build_messages as baseline_messages, validate_bundle as validate_baseline
from .model import SCEDecision
from .belief_state_preparation import ARMS, STATE_MARKER, FORBIDDEN_TERMS
from .prior_belief_preparation import PRIOR_MARKER, MARKER, add_prior
from .prior_belief_experiment import message_hash

REF = 'sce_inflation_expectations.u1_state_decision'
PROMPT_VERSION = 'sce-q8-q9-explicit-state-v2'
SCHEMA = 'sce-explicit-state-diagnostic-v2'
LINE = 'A_conditional_history_diagnostic'


def validate_bundle(bundle, personas, target, as_of):
    if (set(bundle) != {'schema_version', 'research_line', 'target_month', 'as_of', 'arm', 'baseline', 'rows'}
            or bundle['schema_version'] != SCHEMA or bundle['research_line'] != LINE
            or bundle['arm'] not in ARMS or bundle['target_month'] != target or bundle['as_of'] != as_of):
        raise ValueError('U1 schema/line/month/arm mismatch')
    validate_baseline(bundle['baseline'], personas, target, as_of)
    if bundle['baseline']['arm'] != 'national_confidence' or set(bundle['rows']) != {p.agent_id for p in personas}:
        raise ValueError('U1 baseline or roster mismatch')
    for row in bundle['rows'].values():
        if set(row) != {'prior', 'state_block', 'baseline_messages_sha256', 'prior_messages_sha256', 'messages_sha256'}:
            raise ValueError('unexpected U1 row field')
        if any(not isinstance(row[k], str) or len(row[k]) != 64
               for k in ('baseline_messages_sha256', 'prior_messages_sha256', 'messages_sha256')):
            raise ValueError('message hashes required')
        if row['prior_messages_sha256'] == row['messages_sha256']:
            raise ValueError('U1 prompt must differ from the U0 base')
        block = row['state_block']
        if (not isinstance(block, str) or not block.startswith(STATE_MARKER) or not block.endswith('\n\n')
                or MARKER in block or PRIOR_MARKER in block or any(t in block for t in FORBIDDEN_TERMS)):
            raise ValueError('malformed state block')
        if bundle['arm'] == 'own_state' and 'One hypothesis' in block:
            raise ValueError('state-only arm must not carry the guidance sentence')
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
    u0 = add_prior(base, row['prior'], int(bundle['target_month'].replace('-', '')))[0]
    if message_hash(u0) != row['prior_messages_sha256']:
        raise ValueError('reconstructed U0 prompt differs from the executed trial')
    text = u0[0]['content']
    if text.count(MARKER) != 1 or STATE_MARKER in text:
        raise ValueError('questionnaire boundary or duplicate state block')
    before, after = text.split(MARKER, 1)
    messages = [{'role': 'user', 'content': before + row['state_block'] + MARKER + after}]
    if message_hash(messages) != row['messages_sha256']:
        raise ValueError('actual U1 message differs from frozen preparation')
    return messages


@register('decision', REF)
class U1StateDecision(SCEDecision):
    def __init__(self, **args):
        if args.get('prompt_version') != PROMPT_VERSION:
            raise ValueError('U1 provider/prompt mismatch')
        self.u1_bundle = args['u1_bundle']
        super().__init__(**args)

    def build_llm_messages(self, ob):
        return build_messages(ob, self.u1_bundle)

    def _decide_scripted(self, obs):
        for ob in obs:
            self.build_llm_messages(ob)
        return super()._decide_scripted(obs)

    def _decide_openai_one(self, ob):
        action = super()._decide_openai_one(ob)
        action.payload.update(u1_arm=self.u1_bundle['arm'], research_line=LINE,
                              p_snapshot_id='prior_12_age_balanced_20261013',
                              e_snapshot_id='frozen_confidence_environment_' + self.u1_bundle['target_month'],
                              u1_messages_sha256=self.u1_bundle['rows'][ob.agent_id]['messages_sha256'])
        return action
