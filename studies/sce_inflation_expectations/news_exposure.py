"""Isolated news-exposure decision using existing Q8/Q9, audit and cost ledger."""
from copy import deepcopy
from datetime import datetime
from math import isfinite

from socioverse.engine import register
from .model import SCEDecision, build_sce_messages_v2
from .news_exposure_demo import render_news_input
from .price_experience import CATEGORIES, PROFILE_KEYS, canonical_hash, profile_hash
from .experience_mechanism import _check_public_time

SCHEMA = 'sce-news-exposure-v1'
REF = 'sce_inflation_expectations.news_exposure_decision'
PROMPT_VERSION = 'sce-q8-q9-news-exposure-v1'
ARMS = ('shared', 'random', 'matched')
NEWS_KEYS = {'article_id', 'headline', 'abstract', 'snippet', 'pub_date', 'web_url',
             'text_sha256', 'text_vintage_status', 'print_section', 'print_page',
             'placement', 'routing_tags', 'semantic_label'}


def interests_for_profile(profile, shares):
    """Only observed housing/employment categories and SYNTHETIC CE shares.

    The four-category CE basket cannot identify utility spending or media
    preference. Missing housing never becomes owner by default.
    """
    if set(profile) - PROFILE_KEYS or set(shares) != set(CATEGORIES):
        raise ValueError('profile/share whitelist')
    if any(type(x) not in (float, int) or not isfinite(x) or not 0 <= x <= 1 for x in shares.values()) or abs(sum(shares.values()) - 1) > 1e-8:
        raise ValueError('invalid synthetic CE shares')
    interests = set()
    if profile.get('housing_tenure') == 'renter':
        interests.add('rental_housing')
    elif profile.get('housing_tenure') == 'owner':
        interests.add('owned_housing')
    if profile.get('employment_status') in {'employed', 'unemployed', 'on_leave'}:
        interests.add('labor_income')
    if shares['food'] >= .25:
        interests.add('food')
    if shares['gasoline'] >= .08:
        interests.add('road_fuel')
    return interests


def check_news(rows, as_of, common=False):
    cutoff = datetime.fromisoformat(as_of)
    if cutoff.tzinfo is None or len({r['article_id'] for r in rows}) != len(rows):
        raise ValueError('time/duplicate news')
    for row in rows:
        if set(row) != NEWS_KEYS:
            raise ValueError('unexpected news fields')
        published = datetime.fromisoformat(row['pub_date'].replace('Z', '+00:00'))
        if published.tzinfo is None or published > cutoff:
            raise ValueError('future or unqualified publication time')
        if common and (row['placement'] != 'a1' or str(row['print_section']).upper() != 'A' or str(row['print_page']) != '1'):
            raise ValueError('common news must have recorded A1 placement')
        if not common and (row['placement'] == 'a1' or not row['semantic_label'] or row['semantic_label']['decision'] != 'keep'):
            raise ValueError('personal news must be classified keep and not recorded A1')


def validate_bundle(bundle, personas, target, as_of):
    keys = {'schema_version', 'research_line', 'target_month', 'as_of', 'arm',
            'mixing_weight', 'affinity_boost', 'common_news', 'rows', 'source_sha256', 'pool_status'}
    if set(bundle) != keys or bundle['schema_version'] != SCHEMA or bundle['research_line'] != 'A_historical_reconstruction':
        raise ValueError('unsupported news bundle')
    if bundle['target_month'] != target or bundle['as_of'] != as_of or bundle['arm'] not in ARMS:
        raise ValueError('target/as_of/arm mismatch')
    expected = .5 if bundle['arm'] == 'matched' else 0.
    if bundle['mixing_weight'] != expected or bundle['affinity_boost'] != 2:
        raise ValueError('unexpected exposure parameters')
    if set(bundle['rows']) != {p.agent_id for p in personas}:
        raise ValueError('news roster coverage')
    common = bundle['common_news']
    if len(common) != 3:
        raise ValueError('requires the same three common news items')
    check_news(common, as_of, common=True)
    for p in personas:
        row = bundle['rows'][p.agent_id]
        if set(row) != {'profile_sha256', 'spending_shares', 'personal_news'} or row['profile_sha256'] != profile_hash(p.attributes):
            raise ValueError('news row/profile mismatch')
        interests_for_profile(p.attributes, row['spending_shares'])
        if len(row['personal_news']) != 5:
            raise ValueError('requires five personal news items')
        check_news(row['personal_news'], as_of)
        if {r['article_id'] for r in common} & {r['article_id'] for r in row['personal_news']}:
            raise ValueError('common and personal overlap')
    if bundle['arm'] == 'shared' and len({canonical_hash(r['personal_news']) for r in bundle['rows'].values()}) != 1:
        raise ValueError('shared arm must deliver the same personal news to all')
    return deepcopy(bundle)


def build_messages(ob, bundle):
    info, profile = ob.macro_information, ob.local_physical['profile']
    if info['target_month'] != bundle['target_month'] or info['as_of'] != bundle['as_of']:
        raise ValueError('news observation cutoff mismatch')
    if info.get('events') or info.get('broadcasts') or ob.local_information:
        raise ValueError('old news or other treatment may enter through another path')
    _check_public_time(info)
    row = bundle['rows'][ob.agent_id]
    if row['profile_sha256'] != profile_hash(profile):
        raise ValueError('profile binding')
    clean_profile = {k: v for k, v in profile.items() if k in PROFILE_KEYS}
    interests_for_profile(clean_profile, row['spending_shares'])
    messages = build_sce_messages_v2(ob, include_event_abstracts=True)
    content = messages[0]['content']
    marker = 'Question 1 (point estimate):'
    if content.count(marker) != 1:
        raise ValueError('questionnaire insertion point')
    shares = row['spending_shares']
    basket = ('Synthetic household spending context (not your observed receipts):\n'
              f"Food {shares['food']*100:.1f}%; gasoline and motor oil {shares['gasoline']*100:.1f}%; "
              f"cash shelter {shares['shelter']*100:.1f}%; other {shares['other']*100:.1f}%.\n"
              'These are expenditure shares, not CPI weights, shopping frequency or measured attention.\n\n')
    news = render_news_input(bundle['common_news'], row['personal_news'])
    position = content.index(marker)
    messages[0]['content'] = content[:position] + basket + news + '\n\n' + content[position:]
    return messages


@register('decision', REF)
class NewsExposureDecision(SCEDecision):
    def __init__(self, **decision_args):
        self.news_bundle = decision_args['news_exposure_bundle']
        super().__init__(**decision_args)
        if self.llm_kind == 'openai' and (self.prompt_version != PROMPT_VERSION or self.news_bundle['pool_status'] != 'complete_coarse_candidate_labels'):
            raise ValueError('real simulation needs this prompt and complete candidate labels')

    def build_llm_messages(self, ob):
        return build_messages(ob, self.news_bundle)

    def _decide_scripted(self, obs):
        # Force the actual message path even though scripted answers ignore it.
        for ob in obs:
            self.build_llm_messages(ob)
        return super()._decide_scripted(obs)

    def _decide_openai_one(self, ob):
        action = super()._decide_openai_one(ob)
        action.payload.update(news_exposure_arm=self.news_bundle['arm'],
                              news_exposure_bundle_sha256=canonical_hash(self.news_bundle),
                              research_line='A_historical_reconstruction')
        return action
