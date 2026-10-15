#!/usr/bin/env python3
"""Offline prompt drafts, not a runnable/authorized experiment batch."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'studies/sce_inflation_expectations/belief_revision.py'
spec = importlib.util.spec_from_file_location('belief_revision_draft', MODULE)
mechanism = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mechanism)


def main(out):
    out = out.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh ignored output required')
    previews, sources, tests, missing_previous_point = [], {}, 0, 0
    for month in (202004, 202105, 202111, 202203):
        path = ROOT / f'outputs/sce_information_update_trial_20261014_v2/{month}/preview_new_wording.json'
        sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        for r in json.loads(path.read_text()):
            messages = r['messages']
            content = messages[0]['content']
            marker = content.index('Your earlier survey response')
            start = content.index('{"point_pct"', marker)
            previous, _ = json.JSONDecoder().raw_decode(content[start:])
            if previous['point_pct'] is None:
                # Do not invent a prior point estimate from its Q9 density.
                # The missing-Q8 response branch is a remaining runtime task.
                missing_previous_point += 1
                continue
            # Offline algebra check: exactly the same prior is reconstructed by
            # a zero revision. This is not evidence that an LLM will use it well.
            zero = mechanism.answer_to_revision(previous, previous)
            assert mechanism.revision_to_answer(previous, zero) == previous
            updated = mechanism.draft_revision_messages(messages)
            prefix = content.split('Reply with ONLY a JSON object', 1)[0]
            assert updated[0]['content'].startswith(prefix)
            previews.append({'month': month, 'agent_id': r['agent_id'],
                'previous': previous, 'baseline_messages': messages, 'revision_draft_messages': updated})
            tests += 1
    summary = {'status': 'draft_messages_and_adapter_only_NOT_runtime_ready',
        'new_api_calls': 0, 'message_pairs': len(previews), 'months': [202004, 202105, 202111, 202203],
        'not_drafted_missing_previous_Q8': missing_previous_point,
        'same_P_E_prior_questions_prefix_verified': tests,
        'zero_revision_roundtrip_verified': tests,
        'limits': ['All months are already exposed development months; not independent confirmation.',
            'No decision provider, runtime config or request batch wired; no cost authorization sought.',
            'Self-same-information placebo must keep forecast date/window fixed, unlike monthly rolling forecasts.',
            'A real test must compare fixed-population direct vs revision formats with identical P/E/prior.',
            'Invalid probability revisions rejected; no clipping/renormalization or hidden fixed updating weight.',
            'One prior Q8 is missing: define direct-Q8 fallback before any real batch; do not substitute the Q9 mean.',
            'Original Question 1 asks a signed absolute estimate; added response contract encodes it as a delta. This is a task-format intervention, not the unmodified official questionnaire.'],
        'source_sha256': {**sources, str(MODULE.relative_to(ROOT)): hashlib.sha256(MODULE.read_bytes()).hexdigest()}}
    out.mkdir(parents=True)
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    (out / 'preview_pairs_private.json').write_text(json.dumps(previews, ensure_ascii=False, indent=2)+'\n')
    (out / 'preview_sample_private.txt').write_text(previews[0]['revision_draft_messages'][0]['content'])
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    main(p.parse_args().out)
