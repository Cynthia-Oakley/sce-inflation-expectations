"""Isolated historical cognition inputs with the existing absolute-answer contract.

The payload file contains only validated historical cognition fields. Current
survey outcomes and evaluation links never enter this decision implementation.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from socioverse.engine import register
from .cognition_input import ARMS, render_cognition_block, validate_cognition_record
from .information_update_runtime import build_messages as parent_messages
from .model import SCEDecision, _append_jsonl
from .prior_belief_experiment import message_hash
from .revision_format_runtime import REPLY_MARKER, transform as direct_transform

REF = 'sce_inflation_expectations.cognition_decision'
PROMPT = 'sce-q8-q9-cognition-v1'


def transform(messages, arm, record):
    """Preserve the latest direct input and insert one historical cognition block."""
    if arm not in ARMS:
        raise ValueError('Unknown cognition arm')
    validate_cognition_record(record)
    result = direct_transform(messages, 'direct')
    block = render_cognition_block(arm, record)
    if arm == 'label_only':
        if block:
            raise ValueError('Label-only arm must have no extra cognition block')
        return result
    if not block or not isinstance(block, str):
        raise ValueError('Historical cognition block required')
    text = result[0]['content']
    if text.count(REPLY_MARKER) != 1:
        raise ValueError('Exact direct response boundary required')
    result[0]['content'] = text.replace(REPLY_MARKER, block.rstrip()+'\n\n'+REPLY_MARKER, 1)
    return result


def build_messages(ob, bundle, records):
    if set(bundle) != {'arm', 'parent', 'messages_sha256'} or bundle['arm'] not in ARMS:
        raise ValueError('Frozen cognition bundle required')
    record = records[ob.agent_id]
    target = str(ob.macro_information['target_month']).replace('-', '')
    if str(record['target_month']).replace('-', '') != target:
        raise ValueError('Cognition payload target month mismatch')
    original = parent_messages(ob, bundle['parent'])
    result = transform(original, bundle['arm'], record)
    if message_hash(result) != bundle['messages_sha256'][ob.agent_id]:
        raise ValueError('Frozen cognition prompt changed')
    return result


def load_payloads(path, expected_sha256):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Frozen cognition payload file changed')
    records = json.loads(raw)
    if not isinstance(records, dict) or not records:
        raise ValueError('Agent-indexed cognition payloads required')
    for agent_id, record in records.items():
        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError('Anonymous agent identifier required')
        validate_cognition_record(record)
    return records


@register('decision', REF)
class CognitionDecision(SCEDecision):
    def __init__(self, **args):
        if args.get('prompt_version') != PROMPT:
            raise ValueError('Provider/prompt mismatch')
        if args.get('retry_max') != 0:
            raise ValueError('This trial has no automatic retries')
        self.bundle = deepcopy(args['cognition_bundle'])
        self.payloads_sha256 = args['cognition_payloads_sha256']
        self.records = load_payloads(args['cognition_payloads_file'], self.payloads_sha256)
        if set(self.records) != set(self.bundle['messages_sha256']):
            raise ValueError('Cognition payload roster differs from frozen prompts')
        super().__init__(**args)

    def build_llm_messages(self, ob):
        return build_messages(ob, self.bundle, self.records)

    def _metadata(self, ob):
        return {'cognition_arm': self.bundle['arm'],
                'cognition_payloads_sha256': self.payloads_sha256,
                'actual_messages_sha256': self.bundle['messages_sha256'][ob.agent_id],
                'research_line': 'A_conditional_returner_reconstruction'}

    def _decide_scripted(self, obs):
        # Exercise the exact real-message construction and preserve full input
        # evidence. This stylized rule checks engineering only, not treatment effects.
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
            raise ValueError('Actual request differs from frozen cognition preview')
        return super()._call_with_audit(ob, target, messages, attempt_idx)

    def _decide_openai_one(self, ob):
        action = super()._decide_openai_one(ob)
        action.payload.update(self._metadata(ob))
        if action.payload['validation_status'] == 'error':
            if self.audit_dir:
                _append_jsonl(self.audit_dir/'stopped_decisions.jsonl', action.model_dump(mode='json'))
            raise RuntimeError('API/budget error: preserve partial job without automatic retry')
        return action
