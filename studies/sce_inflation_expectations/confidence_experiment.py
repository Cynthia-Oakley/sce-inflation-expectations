"""Isolated Fed-confidence treatment; reuse audited Q8/Q9 and news messages."""
from copy import deepcopy
from datetime import datetime

from socioverse.engine import register
from .model import SCEDecision
from .news_exposure import build_messages as news_messages, validate_bundle as validate_news
from .belief_trial_preparation import CATEGORIES, MARKER, augment_messages
from .price_experience import canonical_hash

REF = 'sce_inflation_expectations.confidence_decision'
PROMPT_VERSION = 'sce-q8-q9-confidence-v1'
SCHEMA = 'sce-confidence-experiment-v1'
ARMS = ('no_added_confidence', 'national_confidence')


def validate_bundle(bundle, personas, target, as_of):
    expected = {'schema_version', 'arm', 'news', 'labels', 'policy', 'wave_id'}
    if set(bundle) != expected or bundle['schema_version'] != SCHEMA or bundle['arm'] not in ARMS:
        raise ValueError('confidence bundle schema/arm')
    validate_news(bundle['news'], personas, target, as_of)
    if bundle['news']['arm'] != 'matched' or bundle['news']['pool_status'] != 'complete_coarse_candidate_labels':
        raise ValueError('requires frozen matched news and complete labels')
    if set(bundle['labels']) != {p.agent_id for p in personas} or any(v not in CATEGORIES for v in bundle['labels'].values()):
        raise ValueError('confidence roster/category')
    policy = bundle['policy']
    if set(policy) != {'published_at', 'source_url', 'source_sha256', 'facts'}:
        raise ValueError('policy whitelist')
    published, cutoff = datetime.fromisoformat(policy['published_at']), datetime.fromisoformat(as_of)
    if published.tzinfo is None or cutoff.tzinfo is None or published > cutoff:
        raise ValueError('future/undated policy')
    if not policy['source_url'].startswith('https://www.federalreserve.gov/') or len(policy['source_sha256']) != 64:
        raise ValueError('policy source')
    if len(policy['facts']) != 3 or any(not isinstance(f, str) or not f.strip() for f in policy['facts']):
        raise ValueError('three public policy facts required')
    if not isinstance(bundle['wave_id'], str) or not bundle['wave_id']:
        raise ValueError('confidence wave missing')
    return deepcopy(bundle)


def build_messages(ob, bundle):
    messages = news_messages(ob, bundle['news'])
    text = messages[0]['content']
    if text.count(MARKER) != 1:
        raise ValueError('questionnaire marker')
    policy = bundle['policy']
    addition = ('Public policy news brief (' + policy['published_at'][:10] + '):\n' +
                '\n'.join('- ' + f for f in policy['facts']) +
                '\nThis records the policy statement at that time, not a known future outcome.\n\n')
    before, after = text.split(MARKER, 1)
    messages[0]['content'] = before + addition + MARKER + after
    if bundle['arm'] == 'national_confidence':
        messages = augment_messages(messages, bundle['labels'][ob.agent_id])
    return messages


@register('decision', REF)
class ConfidenceDecision(SCEDecision):
    def __init__(self, **args):
        self.confidence_bundle = args['confidence_bundle']
        if args.get('prompt_version') != PROMPT_VERSION:
            raise ValueError('confidence provider/prompt mismatch')
        super().__init__(**args)

    def build_llm_messages(self, ob):
        return build_messages(ob, self.confidence_bundle)

    def _decide_scripted(self, obs):
        for ob in obs:
            self.build_llm_messages(ob)
        return super()._decide_scripted(obs)

    def _decide_openai_one(self, ob):
        action = super()._decide_openai_one(ob)
        action.payload.update(confidence_arm=self.confidence_bundle['arm'],
                              confidence_bundle_sha256=canonical_hash(self.confidence_bundle),
                              research_line='A_historical_reconstruction')
        return action
