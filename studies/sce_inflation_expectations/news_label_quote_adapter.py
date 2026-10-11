"""Restore only omitted inline double quotes, without changing frozen requests.

The base runner stays unchanged. Raw replies remain immutable. This adapter
records its source hash and makes no new retry; it can continue unattempted rows.
"""
import hashlib
import json
from pathlib import Path
import re
import sys

from . import news_label_trial as base

BASE_VALIDATE = base.validate_with_evidence_shortening


def validate_with_quote_restoration(content, inputs):
    try:
        return BASE_VALIDATE(content, inputs)
    except ValueError:
        pass
    obj = json.loads(content)
    originals = {row['article_id']: row for row in inputs}
    repairs = []
    for row in obj.get('labels', []) if isinstance(obj, dict) else []:
        if not isinstance(row, dict) or row.get('article_id') not in originals:
            continue
        evidence = row.get('evidence_snippet')
        if not isinstance(evidence, str) or not evidence:
            continue
        original = originals[row['article_id']]
        try:
            BASE_VALIDATE(json.dumps({'labels': [row]}, ensure_ascii=False), [original])
            continue
        except ValueError:
            pass
        if any(evidence in (original.get(f) or '') for f in ('headline', 'abstract', 'snippet')):
            continue
        words = [word.strip('"“”') for word in evidence.split()]
        if len(words) < 3 or not all(words):
            continue
        pattern = r'\s+'.join(r'["“”]*' + re.escape(word) + r'["“”]*' for word in words)
        def normalized(text):
            return ' '.join(word.strip('"“”') for word in text.split()).casefold()
        spans = {match.group() for field in ('headline', 'abstract', 'snippet')
                 for match in re.finditer(pattern, original.get(field) or '', re.IGNORECASE)
                 if normalized(match.group()) == normalized(evidence)}
        if len(spans) == 1:
            literal = spans.pop()
            row['evidence_snippet'] = literal
            repairs.append({'article_id': row['article_id'], 'kind': 'offline_restore_source_inline_double_quotes',
                            'original_evidence_snippet': evidence, 'new_evidence_snippet': literal})
    labels, base_repairs = BASE_VALIDATE(json.dumps(obj, ensure_ascii=False), inputs)
    return labels, repairs + base_repairs


def main():
    argv = sys.argv[1:]
    if '--out' not in argv:
        raise ValueError('output required for adapter provenance')
    out = Path(argv[argv.index('--out') + 1])
    base.validate_with_evidence_shortening = validate_with_quote_restoration
    base.main(argv)
    if (out / 'state.json').exists():
        state = json.loads((out / 'state.json').read_text())
        state['validation_adapter_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        state['validation_adapter_scope'] = 'source-proven inline double-quote formatting only; unchanged decisions/requests'
        base.dump(out / 'state.json', state)


if __name__ == '__main__':
    main()
