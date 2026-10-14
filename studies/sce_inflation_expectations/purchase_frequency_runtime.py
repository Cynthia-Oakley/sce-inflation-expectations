"""Isolated contact-frequency contrast; no reference data reads at runtime."""
from copy import deepcopy

from socioverse.engine import register
from .model import SCEDecision, _append_jsonl
from .information_update_runtime import build_messages as parent_messages
from .purchase_frequency_matching import render_frequency
from .frequency_price_inputs import render_prices
from .prior_belief_experiment import message_hash

REF = 'sce_inflation_expectations.purchase_frequency_decision'
PROMPT = 'sce-q8-q9-purchase-frequency-v1'
ARMS = ('frequency_data', 'frequency_rule')
MARKER = 'Question 1 (point estimate):'


def transform(messages, arm, price_bundle, frequency):
    if arm not in ARMS:
        raise ValueError('unknown frequency arm')
    result = deepcopy(messages)
    if len(result) != 1 or result[0]['content'].count(MARKER) != 1:
        raise ValueError('questionnaire insertion boundary')
    addition = render_prices(price_bundle) + render_frequency(
        {'recorded_days_7d': frequency}, active_rule=arm == 'frequency_rule')
    before, after = result[0]['content'].split(MARKER, 1)
    result[0]['content'] = before + addition + MARKER + after
    return result


def build_messages(ob, bundle):
    messages = transform(parent_messages(ob, bundle['parent']), bundle['arm'],
                         bundle['price_bundle'], bundle['frequency_by_id'][ob.agent_id])
    if message_hash(messages) != bundle['messages_sha256'][ob.agent_id]:
        raise ValueError('frozen frequency message changed')
    return messages


@register('decision', REF)
class PurchaseFrequencyDecision(SCEDecision):
    def __init__(self, **args):
        if args.get('prompt_version') != PROMPT:
            raise ValueError('provider/prompt mismatch')
        self.bundle = args['purchase_frequency_bundle']
        super().__init__(**args)

    def build_llm_messages(self, ob):
        return build_messages(ob, self.bundle)

    def _decide_scripted(self, obs):
        for ob in obs:
            self.build_llm_messages(ob)
        return super()._decide_scripted(obs)

    def _decide_openai_one(self, ob):
        action = super()._decide_openai_one(ob)
        action.payload.update(purchase_frequency_arm=self.bundle['arm'],
                              actual_messages_sha256=self.bundle['messages_sha256'][ob.agent_id],
                              research_line='A_conditional_returner_reconstruction')
        if action.payload.get('validation_status') == 'error':
            if self.audit_dir:
                _append_jsonl(self.audit_dir / 'stopped_decisions.jsonl', action.payload)
            raise RuntimeError('frequency provider/budget error; preserve partial job without retry')
        return action
