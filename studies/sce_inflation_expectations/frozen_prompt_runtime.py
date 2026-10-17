"""One decision provider for prepared prompt-block experiments on official Core."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from socioverse.engine import register
from .model import SCEDecision, _append_jsonl
from .prior_belief_experiment import message_hash

REF = 'sce_inflation_expectations.frozen_prompt_decision'
PROMPT = 'sce-q8-q9-frozen-blocks-v1'


def load_prompts(path, expected_hash):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError('Frozen prompt bundle changed')
    data = json.loads(raw)
    if set(data) != {'month', 'arm', 'rows'} or not data['rows']:
        raise ValueError('Invalid prompt bundle')
    for row in data['rows'].values():
        if set(row) != {'messages', 'prompt_sha256'} or message_hash(row['messages']) != row['prompt_sha256']:
            raise ValueError('Prompt content/hash mismatch')
        if len(row['messages']) != 1 or set(row['messages'][0]) != {'role', 'content'} or row['messages'][0]['role'] != 'user':
            raise ValueError('One frozen user message required')
    return data


@register('decision', REF)
class FrozenPromptDecision(SCEDecision):
    def __init__(self, **args):
        if args.get('prompt_version') != PROMPT or args.get('retry_max') != 0:
            raise ValueError('Frozen prompt provider/version and no-retry contract required')
        self.bundle = load_prompts(args['prompts_file'], args['prompts_sha256'])
        super().__init__(**args)

    def build_llm_messages(self, ob):
        if str(ob.macro_information['target_month']).replace('-', '') != str(self.bundle['month']):
            raise ValueError('Observation/prompt month mismatch')
        return deepcopy(self.bundle['rows'][ob.agent_id]['messages'])

    def _metadata(self, aid):
        return {'experiment_arm': self.bundle['arm'],
                'actual_messages_sha256': self.bundle['rows'][aid]['prompt_sha256']}

    def _decide_scripted(self, obs):
        for ob in obs:
            if self.audit_dir:
                _append_jsonl(self.audit_dir/'scripted_inputs.jsonl', {
                    'agent_id': ob.agent_id, 'messages': self.build_llm_messages(ob),
                    'prompt_sha256': self.bundle['rows'][ob.agent_id]['prompt_sha256'], 'new_api_calls': 0})
        actions = super()._decide_scripted(obs)
        for action in actions:
            action.payload.update(self._metadata(action.agent_id))
        return actions

    def _call_with_audit(self, ob, target, messages, attempt_idx):
        if attempt_idx != 0 or message_hash(messages) != self.bundle['rows'][ob.agent_id]['prompt_sha256']:
            raise ValueError('Unexpected request or retry')
        return super()._call_with_audit(ob, target, messages, attempt_idx)

    def _decide_openai_one(self, ob):
        action = super()._decide_openai_one(ob)
        action.payload.update(self._metadata(ob.agent_id))
        if action.payload['validation_status'] == 'error':
            if self.audit_dir:
                _append_jsonl(self.audit_dir/'stopped_decisions.jsonl', action.model_dump(mode='json'))
            raise RuntimeError('API/budget error: preserve partial run, no retry')
        return action
