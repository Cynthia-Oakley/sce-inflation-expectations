"""Age-linked inflation experience, isolated from truth and old providers."""
from copy import deepcopy
from datetime import datetime
import math

from socioverse.engine import register
from .model import SCEDecision
from .confidence_experiment import build_messages as baseline_messages, validate_bundle as validate_baseline
from .lifetime_experience import insert_block, json_hash
from .lifetime_episodes import render_cards

REF = 'sce_inflation_expectations.lifetime_decision'
PROMPT_VERSION = 'sce-q8-q9-lifetime-inflation-v1'
SCHEMA = 'sce-lifetime-inflation-experiment-v1'
ARMS = ('original', 'common_episodes', 'age_matched_episodes')


def validate_bundle(bundle, personas, target, as_of):
    keys = {'schema_version', 'arm', 'baseline', 'history_end', 'start_age', 'intro', 'rows', 'research_line'}
    if set(bundle) != keys or bundle['schema_version'] != SCHEMA or bundle['arm'] not in ARMS:
        raise ValueError('lifetime bundle schema/arm')
    if bundle['research_line'] != 'A_historical_reconstruction' or bundle['start_age'] != 6:
        raise ValueError('registered A-only age-6 diagnostic required')
    validate_baseline(bundle['baseline'], personas, target, as_of)
    if bundle['baseline']['arm'] != 'national_confidence':
        raise ValueError('existing confidence baseline required')
    if set(bundle['rows']) != {p.agent_id for p in personas}:
        raise ValueError('lifetime roster coverage')
    cutoff = datetime.fromisoformat(as_of)
    if cutoff.tzinfo is None or bundle['history_end'] != f'{cutoff.year-1}-12':
        raise ValueError('complete past calendar years only')
    card_keys = {'era_id', 'label', 'covered_start', 'covered_end', 'n_months',
                 'age_range_approximate', 'life_stages', 'landmarks', 'duration', 'context_facts', 'source_ids'}
    for row in bundle['rows'].values():
        if set(row) != {'cards', 'baseline_messages_sha256', 'messages_sha256'}:
            raise ValueError('lifetime row whitelist')
        if any(len(row[k]) != 64 for k in ('baseline_messages_sha256', 'messages_sha256')):
            raise ValueError('lifetime message hashes')
        if bool(row['cards']) != (bundle['arm'] != 'original'):
            raise ValueError('history missing or baseline contaminated')
        for card in row['cards']:
            if set(card) != card_keys or not ('1914-01' <= card['covered_start'] <= card['covered_end'] <= bundle['history_end']):
                raise ValueError('history card schema/time')
            for node in card['landmarks']:
                if not card['covered_start'] <= node['month'] <= card['covered_end'] or not math.isfinite(node['cpi_yoy_pct']):
                    raise ValueError('future/invalid price landmark')
            for fact in card['context_facts']:
                if set(fact) != {'id', 'event_start', 'event_end', 'source_id', 'text'} or fact['event_end'] > bundle['history_end'] + '-31':
                    raise ValueError('context whitelist or future outcome')
    return deepcopy(bundle)


def build_messages(ob, bundle):
    baseline = baseline_messages(ob, bundle['baseline'])
    row = bundle['rows'][ob.agent_id]
    if json_hash(baseline) != row['baseline_messages_sha256']:
        raise ValueError('actual old P/E/questionnaire changed')
    messages = baseline if bundle['arm'] == 'original' else insert_block(baseline, render_cards(row['cards'], bundle['intro']))
    if json_hash(messages) != row['messages_sha256']:
        raise ValueError('actual lifetime prompt differs from frozen draft')
    return messages


@register('decision', REF)
class LifetimeDecision(SCEDecision):
    def __init__(self, **args):
        if args.get('prompt_version') != PROMPT_VERSION:
            raise ValueError('lifetime provider/prompt mismatch')
        self.lifetime_bundle = args['lifetime_bundle']
        super().__init__(**args)

    def build_llm_messages(self, ob):
        return build_messages(ob, self.lifetime_bundle)

    def _decide_scripted(self, obs):
        for ob in obs:
            self.build_llm_messages(ob)
        return super()._decide_scripted(obs)

    def _decide_openai_one(self, ob):
        action = super()._decide_openai_one(ob)
        action.payload.update(lifetime_arm=self.lifetime_bundle['arm'],
                              lifetime_bundle_sha256=json_hash(self.lifetime_bundle),
                              research_line='A_historical_reconstruction')
        return action
