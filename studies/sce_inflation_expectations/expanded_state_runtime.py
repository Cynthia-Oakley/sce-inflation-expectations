"""Expanded experiment B provider; exact frozen messages, audited existing API client."""
from socioverse.engine import register
from .model import SCEDecision
from .confidence_experiment import build_messages as baseline_messages
from .prior_belief_preparation import add_prior
from .belief_state_preparation import add_state_block
from .prior_belief_experiment import message_hash

REF = 'sce_inflation_expectations.expanded_state_decision'
PROMPT = 'sce-q8-q9-expanded-state-v1'

def build_messages(ob, bundle):
    if bundle['arm'] not in ('self_update', 'new_signal'):
        raise ValueError('Unknown expanded arm')
    messages = baseline_messages(ob, bundle['baseline'])
    row = bundle['rows'][ob.agent_id]
    if bundle['arm'] == 'self_update':
        messages, _ = add_prior(messages, row['prior'], bundle['month'])
        messages, _ = add_state_block(messages, row['state'], bundle['month'], guidance=False)
    if message_hash(messages) != row['messages_sha256']:
        raise ValueError('Actual decision input differs from frozen preview')
    return messages

@register('decision', REF)
class ExpandedDecision(SCEDecision):
    def __init__(self, **args):
        self.bundle = args['expanded_bundle']
        if args.get('prompt_version') != PROMPT:
            raise ValueError('Expanded provider and prompt must match')
        super().__init__(**args)

    def build_llm_messages(self, ob):
        return build_messages(ob, self.bundle)

    def _decide_scripted(self, obs):
        for ob in obs:
            self.build_llm_messages(ob)
        return super()._decide_scripted(obs)

    def _decide_openai_one(self, ob):
        action = super()._decide_openai_one(ob)
        action.payload.update(expanded_arm=self.bundle['arm'],
                              research_line='A_conditional_returner_reconstruction',
                              actual_messages_sha256=self.bundle['rows'][ob.agent_id]['messages_sha256'])
        return action
