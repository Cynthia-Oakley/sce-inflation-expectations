"""Isolated direct-versus-revision response contract; raw API evidence is retained.

The inherited caller writes the original response and usage first. A separate
mapping record then explains exactly what is passed to the unchanged SCE parser.
No frozen provider, scorer, or old input is modified.
"""
import hashlib
import json
import math

from socioverse.engine import register
from .model import SCEDecision, _append_jsonl
from .information_update_runtime import build_messages as parent_messages
from .prior_belief_experiment import message_hash
from .belief_revision import BINS, revision_to_answer

REF = 'sce_inflation_expectations.revision_format_decision'
PROMPT = 'sce-q8-q9-revision-format-v1'
ARMS = ('direct', 'revision')
REPLY_MARKER = 'Reply with ONLY a JSON object'

SHARED = '''Response instructions for the same two questions above:
Use your earlier survey response as a starting state. The forecast window has
advanced by one month, so today's next-12-month period differs from last month's.
Decide what, if anything, you would change using the information available now.
Information marked earlier was publicly available; that does not establish that
you personally knew it. Keeping a belief or revising it upward or downward is
allowed. There is no required adjustment size or direction.

'''

DIRECT = '''Return today's absolute answer:
- point_pct: today's signed point estimate, in percent inflation.
- q9: today's probabilities in the same ten ranges, in percent probability.
  Each must be 0 to 100, and all ten must sum to 100.

Reply with ONLY a JSON object:
{"point_pct": <number>, "q9": {"bin1": <number>, "bin2": <number>,
 "bin3": <number>, "bin4": <number>, "bin5": <number>, "bin6": <number>,
 "bin7": <number>, "bin8": <number>, "bin9": <number>, "bin10": <number>},
 "reason": "<one or two short sentences>"}
'''


def previous_answer(messages):
    text = messages[0]['content']
    marker = text.index('Your earlier survey response')
    start = text.index('{"point_pct"', marker)
    prior, _ = json.JSONDecoder().raw_decode(text[start:])
    if set(prior['q9']) != set(BINS):
        raise ValueError('Ten prior bins required')
    bins = list(prior['q9'].values())
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 100 for v in bins) or abs(sum(bins)-100) > 1e-6:
        raise ValueError('Invalid prior probabilities')
    point = prior.get('point_pct')
    if point is not None and (isinstance(point, bool) or not isinstance(point, (int, float)) or not math.isfinite(point)):
        raise ValueError('Invalid prior point')
    return prior


def transform(messages, arm):
    if arm not in ARMS or len(messages) != 1 or messages[0]['role'] != 'user':
        raise ValueError('Frozen one-user prompt and known arm required')
    text = messages[0]['content']
    if text.count(REPLY_MARKER) != 1:
        raise ValueError('Exact response boundary required')
    prior = previous_answer(messages)
    prefix = text.split(REPLY_MARKER, 1)[0]
    if arm == 'direct':
        contract = DIRECT
    else:
        point = ('point_revision_pp: today\'s signed point estimate minus your earlier point\n'
                 '  estimate, in percentage points of inflation. +1 changes 3% to 4%.')
        key = 'point_revision_pp'
        if prior['point_pct'] is None:
            point = ('point_pct: today\'s signed absolute point estimate. Your previous point\n'
                     '  answer is missing, so do not invent it or subtract a Q9 mean.')
            key = 'point_pct'
        contract = '''Return changes in probability rather than retyping the absolute probabilities:
- '''+point+'''
- q9_revision_pp: for each bin, today's probability minus your earlier probability,
  in percentage points of probability. +5 changes 20% to 25%; it does not raise
  the inflation rate by 5 points. The ten changes must sum to zero. Adding each
  change to its earlier probability must leave a number between 0 and 100.
  All zero changes are permitted; they are not required.

Reply with ONLY a JSON object:
{"'''+key+'''": <number>, "q9_revision_pp": {"bin1": <number>, "bin2": <number>,
 "bin3": <number>, "bin4": <number>, "bin5": <number>, "bin6": <number>,
 "bin7": <number>, "bin8": <number>, "bin9": <number>, "bin10": <number>},
 "reason": "<one or two short sentences>"}
'''
    return [{'role': 'user', 'content': prefix+SHARED+contract}]


def decode_revision(text, prior):
    candidate = text.strip()
    if candidate.startswith('```'):
        candidate = candidate.strip('`').strip()
        if candidate.lower().startswith('json'):
            candidate = candidate[4:].strip()
    obj = json.loads(candidate)
    if not isinstance(obj, dict):
        raise ValueError('Revision must be a JSON object')
    if prior['point_pct'] is None:
        if 'point_revision_pp' in obj:
            raise ValueError('Missing-prior point must be absolute')
        # Zero is used only as an internal algebraic identity, not a synthetic
        # prior: add the reported absolute value to zero, and mark the branch.
        previous = {**prior, 'point_pct': 0.0}
        change = {**obj, 'point_revision_pp': obj['point_pct']}
    else:
        if 'point_pct' in obj:
            raise ValueError('Known-prior point must be a revision')
        previous, change = prior, obj
    result = revision_to_answer(previous, change)
    result['reason'] = str(obj.get('reason', ''))[:500]
    return result


def build_messages(ob, bundle):
    original = parent_messages(ob, bundle['parent'])
    result = transform(original, bundle['arm'])
    if message_hash(result) != bundle['messages_sha256'][ob.agent_id]:
        raise ValueError('Frozen revision-format prompt changed')
    return result


@register('decision', REF)
class RevisionFormatDecision(SCEDecision):
    def __init__(self, **args):
        if args.get('prompt_version') != PROMPT:
            raise ValueError('Provider/prompt mismatch')
        self.bundle = args['revision_format_bundle']
        self.last_mapping = {}
        super().__init__(**args)
        if self.retry_max != 0:
            raise ValueError('This trial has no automatic retries')

    def build_llm_messages(self, ob):
        return build_messages(ob, self.bundle)

    def _decide_scripted(self, obs):
        for ob in obs:
            self.build_llm_messages(ob)
        return super()._decide_scripted(obs)

    def _call_with_audit(self, ob, target, messages, attempt_idx):
        self.last_mapping = {}
        row = super()._call_with_audit(ob, target, messages, attempt_idx)
        if row['error'] or self.bundle['arm'] == 'direct':
            return row
        mapping = {'agent_id': ob.agent_id, 'call_seq': row['call_seq'],
                   'raw_response_sha256': row['raw_response_sha256'],
                   'prompt_sha256': row['prompt_sha256'], 'mapping_error': None}
        try:
            prior = previous_answer(messages)
            answer = decode_revision(row['raw_response_text'] or '', prior)
            mapping.update(reconstructed_answer=answer,
                           missing_previous_point_absolute_branch=prior['point_pct'] is None)
            converted = json.dumps(answer, ensure_ascii=False, allow_nan=False)
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            mapping['mapping_error'] = str(exc)
            converted = json.dumps({'mapping_error': str(exc)})
        mapping['parser_input_sha256'] = hashlib.sha256(converted.encode()).hexdigest()
        self.last_mapping = mapping
        if self.audit_dir:
            _append_jsonl(self.audit_dir/'response_mapping.jsonl', mapping)
        # Original row is already persisted by the inherited audited caller.
        # Only a copy is supplied to its ordinary absolute-answer validator.
        return {**row, 'raw_response_text': converted}

    def _decide_openai_one(self, ob):
        action = super()._decide_openai_one(ob)
        action.payload.update(revision_format_arm=self.bundle['arm'],
                              actual_messages_sha256=self.bundle['messages_sha256'][ob.agent_id],
                              research_line='A_conditional_returner_reconstruction',
                              revision_mapping_error=self.last_mapping.get('mapping_error'))
        if action.payload['validation_status'] == 'error':
            if self.audit_dir:
                _append_jsonl(self.audit_dir/'stopped_decisions.jsonl', action.payload)
            raise RuntimeError('API/budget error: preserve partial job without automatic retry')
        return action
