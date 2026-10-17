"""Finish unattempted frozen news batches; restore exact duplicate rows offline.

No semantic label, evidence or input is invented. Non-identical duplicate IDs
still fail the existing validator. The prior-run ledger prevents any resend.
"""
import hashlib
import json
from pathlib import Path
import sys

from . import news_label_trial as base
from .expanded_news_quote_adapter import validate as existing_validate


def validate(content, inputs):
    obj = json.loads(content)
    if not isinstance(obj, dict) or not isinstance(obj.get('labels'), list):
        return existing_validate(content, inputs)
    unique, repairs = [], []
    for row in obj['labels']:
        if row in unique:
            repairs.append({'kind':'remove_exact_duplicate_label_row', 'article_id':row.get('article_id'),
                            'semantic_fields_changed':False})
        else:
            unique.append(row)
    obj['labels'] = unique
    labels, other = existing_validate(json.dumps(obj,ensure_ascii=False), inputs)
    return labels, repairs + other


def main():
    argv=sys.argv[1:]
    if '--prior-run' not in argv:
        raise ValueError('Completion adapter requires the original ledger; no fresh full-batch replay')
    out=Path(argv[argv.index('--out')+1])
    base.validate_with_evidence_shortening=validate
    base.main(argv)
    if (out/'state.json').exists():
        state=json.loads((out/'state.json').read_text())
        state['validation_adapter_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        state['validation_adapter_scope']='Existing source-proven formatting rules plus removal of fully identical duplicate label rows; no semantic changes, no attempted request resent.'
        base.dump(out/'state.json',state)


if __name__=='__main__':main()
