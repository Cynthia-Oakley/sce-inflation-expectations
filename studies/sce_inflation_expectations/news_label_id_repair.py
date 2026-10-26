"""Auditable identifier-only correction for a uniquely determined public-news row.

The strict classifier validator is unchanged. This optional local derivation
never edits tone/persistence or the original model response.
"""
from copy import deepcopy
import json


def correct_single_id_substitution(content, expected_ids):
    obj = json.loads(content)
    if not isinstance(obj, dict) or set(obj) != {'labels'} or not isinstance(obj['labels'], list):
        raise ValueError('An otherwise intact labels object is required')
    rows = obj['labels']
    if len(rows) != len(expected_ids) or len(set(expected_ids)) != len(expected_ids):
        raise ValueError('Complete unique input/output cardinality required')
    actual_ids = [r.get('article_id') for r in rows]
    if any(not isinstance(v, str) for v in actual_ids) or len(set(actual_ids)) != len(actual_ids):
        raise ValueError('Cannot infer duplicate or missing output identities')
    unknown = [v for v in actual_ids if v not in expected_ids]
    missing = [v for v in expected_ids if v not in actual_ids]
    if len(unknown) != 1 or len(missing) != 1:
        raise ValueError('Exactly one unrecognized ID and one missing ID required')
    before, after = unknown[0], missing[0]
    if len(before) != len(after) or sum(a != b for a, b in zip(before, after)) != 1:
        raise ValueError('Only one-character substitutions are supported')
    index = actual_ids.index(before)
    if any(v != expected_ids[i] for i, v in enumerate(actual_ids) if i != index) or expected_ids[index] != after:
        raise ValueError('All other row IDs and the unique correction must preserve input order')
    fixed = deepcopy(obj)
    fixed['labels'][index]['article_id'] = after
    return fixed, dict(rule='one_missing_one_unknown_single_substitution_preserved_input_order',
                       article_id_before=before, article_id_after=after, row_index=index,
                       tone_and_persistence_changed=False)
