"""Small answer adapter on the existing frozen-prompt provider and official Core."""
import hashlib
import json

from socioverse.engine import register
from . import frozen_prompt_runtime as frozen
from .model import _append_jsonl
from .q8_delta_contract import ARMS, mapping_result
from .revision_format_runtime import previous_answer

REF = 'sce_inflation_expectations.q8_delta_frozen_decision'
PROMPT = 'sce-q8-only-delta-absolute-q9-v1'


@register('decision', REF)
class Q8DeltaDecision(frozen.FrozenPromptDecision):
    def __init__(self, **args):
        if args.get('prompt_version') != PROMPT:
            raise ValueError('Q8-only provider/version required')
        super().__init__(**{**args, 'prompt_version': frozen.PROMPT})
        self.prompt_version = PROMPT
        if self.bundle['arm'] not in ARMS:
            raise ValueError('Unknown Q8-only arm')

    def _call_with_audit(self, ob, target, messages, attempt_idx):
        row = super()._call_with_audit(ob, target, messages, attempt_idx)
        if row['error']:
            return row
        converted, point, error = mapping_result(row['raw_response_text'] or '', self.bundle['arm'],
                                               previous_answer(messages)['point_pct'])
        if self.audit_dir:
            _append_jsonl(self.audit_dir/'response_mapping.jsonl', {
                'agent_id': ob.agent_id, 'arm': self.bundle['arm'],
                'raw_response_sha256': row['raw_response_sha256'],
                'parser_input_sha256': hashlib.sha256(converted.encode()).hexdigest(),
                'reconstructed_q8_point': point, 'mapping_error': error})
        return {**row, 'raw_response_text': converted}

    def _decide_scripted(self, obs):
        actions = super()._decide_scripted(obs)
        for ob, action in zip(obs, actions):
            prior = previous_answer(self.build_llm_messages(ob))['point_pct']
            point = action.payload['point_pct']
            obj = {'q9': {f'bin{i}': action.payload[f'q9_bin{i}'] for i in range(1,11)}}
            delta = self.bundle['arm'] == 'q8_delta' and prior is not None
            obj['point_revision_pp' if delta else 'point_pct'] = point-prior if delta else point
            _, restored, error = mapping_result(json.dumps(obj), self.bundle['arm'], prior)
            if error or abs(restored-point) > 1e-8:
                raise ValueError('Scripted Q8-only round trip failed')
            if self.audit_dir:
                _append_jsonl(self.audit_dir/'scripted_response_mapping.jsonl', {
                    'agent_id': ob.agent_id, 'arm': self.bundle['arm'], 'new_api_calls': 0,
                    'reconstructed_q8_point': restored, 'round_trip_passed': True})
        return actions
