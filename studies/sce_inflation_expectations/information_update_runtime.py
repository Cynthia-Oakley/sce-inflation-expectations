"""Isolated wording/time-index contrast; no reference-data reads at runtime."""
from copy import deepcopy
from datetime import datetime, date
from zoneinfo import ZoneInfo

from socioverse.engine import register
from .anchor_role_runtime import build_messages as parent_messages
from .behavior_prompt_blocks import ANCHOR_BLOCK
from .model import SCEDecision, _find_signal, _TREND_LINES
from .prior_belief_preparation import PRIOR_MARKER
from .prior_belief_experiment import message_hash

REF = 'sce_inflation_expectations.information_update_decision'
PROMPT = 'sce-q8-q9-information-update-v1'
ARMS = ('new_wording', 'dated_information')
TIME_ROLE_BLOCK = (
    'Belief update instruction:\n'
    'Your previous survey records the belief you formed last month using the information you had at that time. '
    'Treat it as the starting point for your current view. The forecast window has now advanced by one month. '
    'Consider whether more recent information warrants keeping or revising that view; keeping it is allowed, '
    'revising it is allowed, and no fixed amount of adjustment is required.\n\n'
)
NY = ZoneInfo('America/New_York')


def publication_status(published, previous_day, as_of):
    """Date-only prior response: releases on that day remain ambiguous."""
    when = datetime.fromisoformat(published.replace('Z', '+00:00'))
    cutoff = datetime.fromisoformat(as_of.replace('Z', '+00:00'))
    if when.tzinfo is None or cutoff.tzinfo is None or when > cutoff:
        raise ValueError('undated/naive/future publication')
    previous_day = date.fromisoformat(previous_day)
    local_day = when.astimezone(NY).date()
    if previous_day >= cutoff.astimezone(NY).date():
        raise ValueError('previous survey day must precede current scenario cutoff')
    return ('earlier' if local_day < previous_day else
            'later' if local_day > previous_day else 'same-day uncertain')


def displayed_signals(signals):
    """Only facts already rendered by build_sce_messages_v2, not all stored E."""
    latest = [s for s in signals if s.get('role') != 'history']
    history = [s for s in signals if s.get('role') == 'history']
    prefixes = ['bls_cpi_u_all_items_yoy', 'bls_cpi_u_all_items_mom',
                'bls_unemployment_rate', 'bls_nonfarm_payroll',
                'eia_gasoline_retail_regular_mean', 'bls_cpi_gasoline_yoy',
                'bls_cpi_energy_yoy', 'bls_cpi_food_yoy',
                'bls_cpi_food_at_home_yoy', 'bls_cpi_shelter_yoy']
    selected = {s['signal_id']: s for prefix in prefixes
                if (s := _find_signal(latest, prefix)) is not None}
    for _, prefix, _ in _TREND_LINES:
        for s in history:
            if s['signal_id'].startswith(prefix): selected[s['signal_id']] = s
    return list(selected.values())


def time_index(signals, news, personal_news, policy, previous_day, as_of):
    groups = {}
    selected = displayed_signals(signals)
    for s in selected:
        sid = s['signal_id']
        family = ('CPI figures' if sid.startswith('bls_cpi_') else
                  'employment figures' if sid.startswith(('bls_unemployment_', 'bls_nonfarm_')) else
                  'gasoline price figures' if sid.startswith('eia_gasoline_') else None)
        if family is None: raise ValueError('unmapped displayed signal')
        status = publication_status(s['published_at'], previous_day, as_of)
        released = datetime.fromisoformat(s['published_at']).astimezone(NY).date().isoformat()
        key = (s['reference_period'], family, released, status)
        groups.setdefault(key, []).append(sid)
    lines = [
        'Publication timing for the same information above:',
        'earlier = published before your previous survey day; later = published after that day '
        'but by the current information cutoff; same-day uncertain = published on that day, '
        'with no known order relative to your response.',
        'These labels describe public availability, not what you actually read or remembered. '
        'Dates use New York time. The rolling trends above span both earlier and later releases.',
    ]
    for (reference, family, released, status), _ in sorted(groups.items()):
        lines.append(f'- {family}, reference {reference}, released {released}: {status}.')
    statuses = [publication_status(r['pub_date'], previous_day, as_of) for r in news]
    personal = [publication_status(r['pub_date'], previous_day, as_of) for r in personal_news]
    lines.append('- General news, in the order listed above: ' + '; '.join(statuses) + '.')
    lines.append('- Other news, in the order listed above: ' + '; '.join(personal) + '.')
    policy_status = publication_status(policy['published_at'], previous_day, as_of)
    released = datetime.fromisoformat(policy['published_at']).astimezone(NY).date().isoformat()
    lines.append(f'- Policy brief, released {released}: {policy_status}.')
    block = '\n'.join(lines) + '\n\n'
    return block, {'displayed_signal_ids': sorted(s['signal_id'] for s in selected),
                   'release_groups': [{'reference_period': key[0], 'family': key[1],
                                       'released_day': key[2], 'status': key[3],
                                       'signal_ids': value} for key, value in sorted(groups.items())],
                   'general_news_statuses': statuses, 'personal_news_statuses': personal,
                   'policy_status': policy_status}


def transform(messages, arm, timing_block):
    if arm not in ARMS: raise ValueError('unknown arm')
    result = deepcopy(messages)
    if len(result) != 1 or result[0]['content'].count(ANCHOR_BLOCK) != 1:
        raise ValueError('exact parent prior-role block required')
    text = result[0]['content'].replace(ANCHOR_BLOCK, TIME_ROLE_BLOCK, 1)
    if arm == 'dated_information':
        if text.count(PRIOR_MARKER) != 1 or not timing_block.startswith('Publication timing for the same information above:'):
            raise ValueError('timing insertion boundary')
        text = text.replace(PRIOR_MARKER, timing_block + PRIOR_MARKER, 1)
    result[0]['content'] = text
    return result


def build_messages(ob, bundle):
    old = parent_messages(ob, bundle['parent'])
    messages = transform(old, bundle['arm'], bundle['time_index_by_id'][ob.agent_id])
    if message_hash(messages) != bundle['messages_sha256'][ob.agent_id]:
        raise ValueError('frozen follow-up message changed')
    return messages


@register('decision', REF)
class InformationUpdateDecision(SCEDecision):
    def __init__(self, **args):
        if args.get('prompt_version') != PROMPT: raise ValueError('provider/prompt mismatch')
        self.bundle = args['information_update_bundle']
        super().__init__(**args)

    def build_llm_messages(self, ob): return build_messages(ob, self.bundle)

    def _decide_scripted(self, obs):
        for ob in obs: self.build_llm_messages(ob)
        return super()._decide_scripted(obs)

    def _decide_openai_one(self, ob):
        action = super()._decide_openai_one(ob)
        action.payload.update(information_update_arm=self.bundle['arm'],
                              actual_messages_sha256=self.bundle['messages_sha256'][ob.agent_id],
                              research_line='A_conditional_returner_reconstruction')
        return action
