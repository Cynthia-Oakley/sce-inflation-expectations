"""Isolated Q1 fact/perspective arms with the existing absolute-answer contract."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from socioverse.engine import register
from .household_finance_input import (
    ARMS, RESEARCH_LINE, render_household_finance_block,
    validate_household_finance_record,
)
from .information_update_runtime import build_messages as parent_messages
from .model import SCEDecision, _append_jsonl
from .prior_belief_experiment import message_hash
from .revision_format_runtime import REPLY_MARKER, transform as direct_transform

REF = 'sce_inflation_expectations.household_finance_decision'
PROMPT = 'sce-q8-q9-household-finance-v1'


def transform(messages, arm, record):
    """Insert only the assigned household-finance block into the direct input."""
    if arm not in ARMS:
        raise ValueError('Unknown household-finance arm')
    validate_household_finance_record(record)
    result = direct_transform(messages, 'direct')
    block = render_household_finance_block(arm, record)
    if arm == 'baseline':
        return result
    text = result[0]['content']
    if text.count(REPLY_MARKER) != 1:
        raise ValueError('Exact direct response boundary required')
    result[0]['content'] = text.replace(REPLY_MARKER, block.rstrip()+'\n\n'+REPLY_MARKER, 1)
    return result


def _validate_bundle(bundle):
    if (not isinstance(bundle, dict) or set(bundle) != {'arm', 'parent', 'messages_sha256'}
            or bundle['arm'] not in ARMS or not isinstance(bundle['parent'], dict)
            or not isinstance(bundle['messages_sha256'], dict) or not bundle['messages_sha256']):
        raise ValueError('Frozen household-finance bundle required')


def build_messages(ob, bundle, records):
    _validate_bundle(bundle)
    record = records[ob.agent_id]
    validate_household_finance_record(record)
    target = str(ob.macro_information['target_month']).replace('-', '')
    if str(record['target_month']) != target:
        raise ValueError('Household-finance payload target month mismatch')
    original = parent_messages(ob, bundle['parent'])
    result = transform(original, bundle['arm'], record)
    if message_hash(result) != bundle['messages_sha256'][ob.agent_id]:
        raise ValueError('Frozen household-finance prompt changed')
    return result


def load_payloads(path, expected_sha256):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Frozen household-finance payload file changed')
    records = json.loads(raw)
    if not isinstance(records, dict) or not records:
        raise ValueError('Agent-indexed household-finance payloads required')
    for agent_id, record in records.items():
        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError('Anonymous agent identifier required')
        validate_household_finance_record(record)
    return records


@register('decision', REF)
class HouseholdFinanceDecision(SCEDecision):
    def __init__(self, **args):
        if args.get('prompt_version') != PROMPT:
            raise ValueError('Provider/prompt mismatch')
        if args.get('retry_max') != 0:
            raise ValueError('This trial has no automatic retries')
        self.bundle = deepcopy(args['household_finance_bundle'])
        _validate_bundle(self.bundle)
        self.payloads_sha256 = args['household_finance_payloads_sha256']
        self.records = load_payloads(args['household_finance_payloads_file'], self.payloads_sha256)
        if set(self.records) != set(self.bundle['messages_sha256']):
            raise ValueError('Household-finance payload roster differs from frozen prompts')
        super().__init__(**args)

    def build_llm_messages(self, ob):
        return build_messages(ob, self.bundle, self.records)

    def _metadata(self, ob):
        return {'household_finance_arm': self.bundle['arm'],
                'household_finance_payloads_sha256': self.payloads_sha256,
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
            raise ValueError('Actual request differs from frozen household-finance preview')
        return super()._call_with_audit(ob, target, messages, attempt_idx)

    def _decide_openai_one(self, ob):
        action = super()._decide_openai_one(ob)
        action.payload.update(self._metadata(ob))
        if action.payload['validation_status'] == 'error':
            if self.audit_dir:
                _append_jsonl(self.audit_dir/'stopped_decisions.jsonl', action.model_dump(mode='json'))
            raise RuntimeError('API/budget error: preserve partial job without automatic retry')
        return action
