"""Qualitative lifetime history: delete price magnitudes, not add behavioral rules."""
from copy import deepcopy

from socioverse.engine import register
from .model import SCEDecision
from .confidence_experiment import build_messages as baseline_messages
from .lifetime_experiment import LifetimeDecision, validate_bundle as validate_numeric, SCHEMA as NUMERIC_SCHEMA
from .lifetime_episodes import render_cards, trend_sentence
from .lifetime_experience import insert_block, json_hash

ARMS = ('original', 'numeric_history', 'text_history')
REF = 'sce_inflation_expectations.lifetime_text_decision'
SCHEMA = 'sce-lifetime-text-experiment-v1'
PROMPT_VERSION = 'sce-q8-q9-lifetime-text-v1'
TEXT_INTRO = 'Past U.S. price history. Slower inflation means prices rose more slowly.'
TEXT_FACTS = {
    'recession_2007_09': 'The housing and financial crisis was followed by a deep recession. The Federal Reserve cut its policy rate to an exceptionally low level during the crisis.',
    'pce_goal_2012': 'The Federal Reserve announced an explicit longer-run inflation goal measured by PCE, rather than CPI.',
}


def render_text_cards(cards):
    """Fixed qualitative descriptions; no Q8/Q9, extra LLM or selected outcomes."""
    lines = [TEXT_INTRO]
    shown_spells = set()
    for card in cards:
        # Calendar years identify the episode; no exact age or monthly nodes.
        first, last = card['covered_start'][:4], card['covered_end'][:4]
        years = first if first == last else f'{first}–{last}'
        stages = '' if not card['life_stages'] else '; ' + '/'.join(card['life_stages'])
        lines.append(f"{years}: {card['label']}{stages}.")
        lines.extend('Context: ' + TEXT_FACTS.get(fact['id'], fact['text']) for fact in card['context_facts'])
        lines.append(trend_sentence(card['landmarks']))
        duration = card['duration']
        spell = duration['continuous_high_inflation_spell_around_peak']
        key = None if spell is None else (spell['start'], spell['end'])
        if key is not None and key not in shown_spells:
            shown_spells.add(key)
            if spell['right_censored']:
                lines.append('Elevated inflation was still continuing when the history shown stops.')
            elif spell['left_censored']:
                lines.append('This portion of history shows elevated inflation that later eased; its full duration is not observed.')
            elif spell['known_months'] >= 12:
                lines.append('Elevated inflation persisted over an extended period before easing.')
            elif spell['known_months'] <= 6:
                lines.append('The elevated-inflation episode was relatively short-lived in the history shown.')
            else:
                lines.append('Elevated inflation continued for a while before easing.')
        lines.append('')
    return '\n'.join(lines).strip() + '\n'


def validate_bundle(bundle, personas, target, as_of):
    if bundle.get('schema_version') != SCHEMA or bundle.get('arm') not in ARMS:
        raise ValueError('qualitative lifetime schema/arm')
    mapped = deepcopy(bundle)
    mapped['schema_version'] = NUMERIC_SCHEMA
    mapped['arm'] = 'original' if bundle['arm'] == 'original' else 'age_matched_episodes'
    validate_numeric(mapped, personas, target, as_of)
    if bundle['arm'] == 'text_history' and bundle['intro'] != TEXT_INTRO:
        raise ValueError('fixed qualitative introduction required')
    return deepcopy(bundle)


def build_messages(ob, bundle):
    baseline = baseline_messages(ob, bundle['baseline'])
    row = bundle['rows'][ob.agent_id]
    if json_hash(baseline) != row['baseline_messages_sha256']:
        raise ValueError('actual old P/E/questionnaire changed')
    if bundle['arm'] == 'original':
        messages = baseline
    else:
        text = render_text_cards(row['cards']) if bundle['arm'] == 'text_history' else render_cards(row['cards'], bundle['intro'])
        messages = insert_block(baseline, text)
    if json_hash(messages) != row['messages_sha256']:
        raise ValueError('actual qualitative prompt differs from frozen draft')
    return messages


@register('decision', REF)
class LifetimeTextDecision(LifetimeDecision):
    def __init__(self, **args):
        if args.get('prompt_version') != PROMPT_VERSION:
            raise ValueError('qualitative lifetime provider/prompt mismatch')
        self.lifetime_bundle = args['lifetime_bundle']
        # Inherit the audited scripted/openai dispatch, but use this renderer.
        SCEDecision.__init__(self, **args)

    def build_llm_messages(self, ob):
        return build_messages(ob, self.lifetime_bundle)
