"""Pure state rendering/updating; transport remains in the existing LLM client.

No files, datasets, API keys or network are accessed here. Recursive state can
only change through the actual preceding response supplied by the caller.
"""
from copy import deepcopy
from datetime import datetime
import json
import math

from .experiments.state_continuity_inputs import density_center
from .experiments.state_continuity import month_index
from .information_update_runtime import publication_status
from .prior_belief_preparation import valid_bins
from .q9_normalization import normalize_bins, response_point

STATE_TOKEN = '[[SCE_CONTINUITY_STATE]]'
TIMING_TOKEN = '[[SCE_CONTINUITY_TIMING]]'


def initialize_state(resolved):
    return {'fields': deepcopy(resolved['fields']),
            'history_centers': deepcopy(resolved['own_history_centers']),
            'comparison_reference_day': resolved['comparison_reference_day'],
            'comparison_day_source': resolved['comparison_day_source'],
            'transition': 'initialization_not_a_new_model_answer'}


def render_state(state, month):
    fields = state['fields']
    lines = ['Earlier belief state (expectations, not measured inflation):']
    names = {'own_observed': 'your own earlier survey answer',
             'synthetic_donor': 'assigned synthetic starting belief; not your actual survey answer',
             'simulated': 'your answer from an earlier step of this simulation'}
    for key in ('q8', 'q9'):
        field = fields[key]; period = int(field['source_period'])
        if month_index(period) >= month_index(month) or field['source_kind'] not in names:
            raise ValueError('Only declared earlier belief sources can be rendered')
        value = field['value']
        if key == 'q9' and not valid_bins(value):
            raise ValueError('Unresolved probability state')
        if key == 'q8' and (type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 100):
            raise ValueError('Unresolved signed point state')
        label = f'{period // 100}-{period % 100:02}'
        payload = value if key == 'q8' else {f'bin{i}': v for i, v in enumerate(value, 1)}
        lines.append(f'- {key.upper()}, source {label}: {names[field["source_kind"]]}.')
        lines.append(json.dumps({'point_pct' if key == 'q8' else 'q9': payload}, ensure_ascii=False))
    centers = state['history_centers']
    if len(centers) >= 2:
        if any(month_index(r['source_period']) >= month_index(month) for r in centers):
            raise ValueError('History summary includes target/future answers')
        typical = sum(r['center'] for r in centers) / len(centers)
        lines.append(f'- Across {len(centers)} earlier available survey states, the probability-implied '
                     f'average expectation has typically been around {typical:.2f}%.')
    lines.extend(['The earlier answers concerned the 12 months following their own survey dates. '
                  "Today's questions concern the next 12 months from today's survey.",
                  'Use the earlier state as the starting point for your current view. Consider whether '
                  'new information warrants retaining or revising it. An unchanged answer is allowed; '
                  'no fixed amount of adjustment is required.'])
    return '\n'.join(lines) + '\n\n'


def render_messages(template, state, month, environment):
    if len(template) != 1 or template[0].get('role') != 'user':
        raise ValueError('One user-message template required')
    text = template[0]['content']
    if text.count(STATE_TOKEN) != 1 or text.count(TIMING_TOKEN) != 1:
        raise ValueError('Unique state and timing insertion points required')
    day = state['comparison_reference_day']; cutoff = environment['as_of']
    def status(when): return publication_status(when, day, cutoff)
    timing = [
        'Publication timing for the same information above:',
        'earlier/later/same-day uncertain compare public release dates with the reference day '
        'of the earlier belief state; they do not establish what you actually noticed.',
        '- General news, in the order listed above: ' + '; '.join(status(r['pub_date']) for r in environment['common_news']) + '.',
        '- Other news, in the order listed above: ' + '; '.join(status(r['pub_date']) for r in environment['personal_news']) + '.',
        '- Policy brief: ' + status(environment['policy_published_at']) + '.',
        '- Grocery figures: ' + status(environment['food_published_at']) + '.',
    ]
    if state['comparison_day_source'] != 'own_observed_survey_day':
        timing.append('The comparison day is an initialization or simulation reference, not a claimed real interview date.')
    result = deepcopy(template)
    result[0]['content'] = text.replace(STATE_TOKEN, render_state(state, month), 1).replace(
        TIMING_TOKEN, '\n'.join(timing) + '\n\n', 1)
    return result


def advance_state(previous, raw, month, as_of):
    """Normalize authorized Q9 only; failed fields explicitly retain old state."""
    result = deepcopy(previous); updated = {'q8': False, 'q9': False}
    for field in result['fields'].values():
        if month_index(field['source_period']) >= month_index(month):
            raise ValueError('State transition must move forward in calendar time')
    point = response_point(raw)
    if point is not None and abs(point) <= 100:
        result['fields']['q8'] = {'value': point, 'source_period': int(month), 'source_kind': 'simulated'}
        updated['q8'] = True
    try:
        obj = json.loads(raw); values = obj['q9']
        if not isinstance(values, dict) or set(values) != {f'bin{i}' for i in range(1, 11)}:
            raise ValueError('Nested ten-bin answer required')
        view = normalize_bins([values[f'bin{i}'] for i in range(1, 11)])
    except (ValueError, TypeError, KeyError):
        view = None
    if view is not None:
        values = view['bins']
        result['fields']['q9'] = {'value': values, 'source_period': int(month), 'source_kind': 'simulated'}
        center = density_center(tuple(values))
        if center is not None:
            result['history_centers'].append({'source_period': int(month), 'center': center})
        result['comparison_reference_day'] = datetime.fromisoformat(as_of).date().isoformat()
        result['comparison_day_source'] = 'simulation_information_cutoff'
        updated['q9'] = True
    result['transition'] = {'month': str(month), 'field_updated_from_model': updated,
                            'field_retained_as_explicit_fallback': {k: not v for k, v in updated.items()},
                            'q9_proportional_normalization': bool(view and view['applied']),
                            'raw_response_preserved_by_caller': True}
    return result
