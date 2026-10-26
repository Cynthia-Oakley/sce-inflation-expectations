"""Deterministic dependency replay. Not a real model or performance estimate."""
import json

from ..state_continuity_runtime import (
    STATE_TOKEN, TIMING_TOKEN, advance_state, render_messages,
)
from ..prior_belief_experiment import message_hash


def dry_run(nodes, inputs, *, capture_all=False):
    state_after, shared_prompts, previews, full_rows = {}, {}, {}, {}
    largest_chars = largest_bytes = 0
    for node in nodes:
        month, aid, repeat, arm = (node[k] for k in ('month', 'agent_id', 'repeat', 'arm'))
        template, initial, context = inputs[month, aid]
        dep = node['dependency']
        if dep is None:
            state = initial
        else:
            state = state_after[dep['month'], dep['agent_id'], dep['repeat'], dep['arm']]
        messages = render_messages(template, state, month, context)
        text = messages[0]['content']
        if STATE_TOKEN in text or TIMING_TOKEN in text:
            raise ValueError('Unresolved placeholder')
        prefix = template[0]['content'].split(TIMING_TOKEN)[0]
        suffix = template[0]['content'].split(STATE_TOKEN)[1]
        if not text.startswith(prefix) or not text.endswith(suffix):
            raise ValueError('A non-state environment or questionnaire byte changed')
        reuse = node['logical_reuse_key']; digest = message_hash(messages)
        if reuse in shared_prompts and shared_prompts[reuse] != digest:
            raise ValueError('Initialization sharing would merge different prompts')
        shared_prompts[reuse] = digest
        probabilities = [5, 5, 10, 10, 10, 10, 10, 10, 10, 20]
        if repeat == 2: probabilities = list(reversed(probabilities))
        raw = json.dumps({'point_pct': 2 + int(month[-2:]) / 10 + repeat / 10,
                          'q9': {f'bin{i}': v for i, v in enumerate(probabilities, 1)},
                          'reason': 'Deterministic offline fixture; not an LLM response'})
        state_after[month, aid, repeat, arm] = advance_state(state, raw, month, context['as_of'])
        largest_chars = max(largest_chars, len(text))
        largest_bytes = max(largest_bytes, len(json.dumps(messages, ensure_ascii=False).encode()))
        preview_key = f'{month}-{arm}-r{repeat}'
        if capture_all:
            full_rows.setdefault(preview_key, {})[aid] = {'messages': messages, 'prompt_sha256': digest}
        if preview_key not in previews:
            previews[preview_key] = {'messages': messages, 'prompt_sha256': digest,
                                     'source_kind': node['source_kind']}
    return {'status': 'passed_deterministic_state_replay_not_model_validation',
            'new_api_calls': 0, 'official_engine_dry_runs': 0,
            'positions_replayed': len(nodes), 'unique_request_slots': len(shared_prompts),
            'max_rendered_characters': largest_chars, 'max_rendered_utf8_bytes': largest_bytes,
            'full_environment_and_questionnaire_static': True,
            'preview_rows_private': previews,
            **({'full_rows_private': full_rows} if capture_all else {})}
