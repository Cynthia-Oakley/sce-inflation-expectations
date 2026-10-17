"""Scaled reference input: existing information-update prompt and direct reply."""
from copy import deepcopy
import re

from socioverse.engine import register
from .information_update_runtime import build_messages as parent_messages
from .model import SCEDecision, _append_jsonl
from .prior_belief_experiment import message_hash
from .revision_format_runtime import transform as direct_transform

REF = 'sce_inflation_expectations.reference_validation_decision'
PROMPT = 'sce-q8-q9-reference-validation-v1'
ARM = 'reference'
RESEARCH_LINE = 'A_conditional_returner_reconstruction'


def _validate_bundle(bundle):
    if (not isinstance(bundle, dict) or set(bundle) != {'parent', 'messages_sha256'}
            or not isinstance(bundle['parent'], dict) or not isinstance(bundle['messages_sha256'], dict)
            or not bundle['messages_sha256']):
        raise ValueError('Frozen reference-validation bundle required')
    for agent_id, digest in bundle['messages_sha256'].items():
        if (not isinstance(agent_id, str) or not agent_id or not isinstance(digest, str)
                or re.fullmatch(r'[0-9a-f]{64}', digest) is None):
            raise ValueError('Reference prompt roster/hash mismatch')


def transform(messages):
    return direct_transform(messages, 'direct')


def build_messages(ob, bundle):
    _validate_bundle(bundle)
    result = transform(parent_messages(ob, bundle['parent']))
    if message_hash(result) != bundle['messages_sha256'][ob.agent_id]:
        raise ValueError('Frozen reference-validation prompt changed')
    return result


@register('decision', REF)
class ReferenceValidationDecision(SCEDecision):
    def __init__(self, **args):
        if args.get('prompt_version') != PROMPT:
            raise ValueError('Provider/prompt mismatch')
        if args.get('retry_max') != 0:
            raise ValueError('This trial has no automatic retries')
        self.bundle = deepcopy(args['reference_validation_bundle'])
        _validate_bundle(self.bundle)
        super().__init__(**args)

    def build_llm_messages(self, ob):
        return build_messages(ob, self.bundle)

    def _metadata(self, ob):
        return {'reference_validation_arm': ARM,
                'actual_messages_sha256': self.bundle['messages_sha256'][ob.agent_id],
                'research_line': RESEARCH_LINE}

    def _decide_scripted(self, obs):
        for ob in obs:
            messages = self.build_llm_messages(ob)
            if self.audit_dir:
                _append_jsonl(self.audit_dir/'scripted_inputs.jsonl', {
                    'run_id': self.run_id, 'agent_id': ob.agent_id, 'runtime_step': ob.step,
                    'llm_kind': 'scripted', 'new_api_calls': 0, 'messages': messages,
                    'prompt_sha256': message_hash(messages), **self._metadata(ob)})
        actions = super()._decide_scripted(obs)
        by_id = {ob.agent_id: ob for ob in obs}
        for action in actions:
            action.payload.update(self._metadata(by_id[action.agent_id]))
            if self.audit_dir:
                _append_jsonl(self.audit_dir/'scripted_decisions.jsonl', action.model_dump(mode='json'))
        return actions

    def _call_with_audit(self, ob, target, messages, attempt_idx):
        if attempt_idx != 0 or message_hash(messages) != self.bundle['messages_sha256'][ob.agent_id]:
            raise ValueError('Actual request differs from frozen reference preview')
        return super()._call_with_audit(ob, target, messages, attempt_idx)

    def _decide_openai_one(self, ob):
        action = super()._decide_openai_one(ob)
        action.payload.update(self._metadata(ob))
        if action.payload['validation_status'] == 'error':
            if self.audit_dir:
                _append_jsonl(self.audit_dir/'stopped_decisions.jsonl', action.model_dump(mode='json'))
            raise RuntimeError('API/budget error: preserve partial job without automatic retry')
        return action
