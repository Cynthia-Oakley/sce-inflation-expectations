"""Recover literal quote suffixes, never decisions/topics/identities or API calls.

A model may replace a source pronoun with an article subject. Trim only a
nonmatching prefix when at least five trailing words (70% of quoted words)
occur uniquely and contiguously in that same source article. Keep raw replies.
"""
import json
import re

from .news_label_quote_adapter import validate_with_quote_restoration
from .news_label_trial import validate_labels


def _validate_core(content, inputs):
    try:return validate_with_quote_restoration(content,inputs)
    except ValueError:pass
    obj=json.loads(content);source={r['article_id']:r for r in inputs};repairs=[]
    for row in obj.get('labels',[]) if isinstance(obj,dict) else []:
        if not isinstance(row,dict) or row.get('article_id') not in source:continue
        original=source[row['article_id']];quote=row.get('evidence_snippet')
        if not isinstance(quote,str):continue
        try:
            validate_with_quote_restoration(json.dumps({'labels':[row]},ensure_ascii=False),[original])
            continue
        except ValueError:pass
        tokens=list(re.finditer(r'\S+',quote))
        for first in range(1,len(tokens)):
            n=len(tokens)-first
            if n<5 or n/len(tokens)<.7:continue
            suffix=quote[tokens[first].start():]
            # Repeated abstract/snippet fields count as one same source text.
            texts={original.get(k) or '' for k in ('headline','abstract','snippet')}
            hits=sum(text.count(suffix) for text in texts)
            if hits==1:
                row['evidence_snippet']=suffix
                repairs.append(dict(article_id=row['article_id'],kind='offline_trim_nonliteral_prefix_unique_literal_suffix',
                    original_evidence_snippet=quote,new_evidence_snippet=suffix,retained_word_fraction=n/len(tokens)))
                break
    try:
        labels,old=validate_with_quote_restoration(json.dumps(obj,ensure_ascii=False),inputs)
        return labels,repairs+old
    except ValueError:
        # Evidence is audit metadata, not a classification. Do not invent a
        # source quote or resend paid requests to fix an unsupported excerpt.
        # Only exact-ID rows whose ENTIRE remaining schema passes can be kept;
        # explicitly remove/quarantine the unverifiable quote in derived labels.
        obj=json.loads(content);repairs=[]
        for row in obj.get('labels',[]) if isinstance(obj,dict) else []:
            if not isinstance(row,dict) or row.get('article_id') not in source:
                raise ValueError('Unverifiable article identity cannot be repaired by removing evidence')
            try:
                validate_with_quote_restoration(json.dumps({'labels':[row]},ensure_ascii=False),[source[row['article_id']]])
                continue
            except ValueError:pass
            derived={**row,'evidence_snippet':''}
            validate_labels(json.dumps({'labels':[derived]},ensure_ascii=False),[source[row['article_id']]])
            repairs.append(dict(article_id=row['article_id'],kind='offline_quarantine_unverifiable_evidence',
                original_evidence_snippet=row['evidence_snippet'],new_evidence_snippet='',
                evidence_verified=False,classifications_changed=False))
            row['evidence_snippet']=''
        labels,old=validate_with_quote_restoration(json.dumps(obj,ensure_ascii=False),inputs)
        return labels,repairs+old


def validate(content, inputs):
    """Drop only byte-equivalent duplicate label objects, not repeated news."""
    obj=json.loads(content);repairs=[]
    rows=obj.get('labels') if isinstance(obj,dict) else None
    if isinstance(rows,list):
        unique=[];seen={}
        for row in rows:
            aid=row.get('article_id') if isinstance(row,dict) else None
            if aid is not None and aid in seen:
                if seen[aid]!=row:raise ValueError('Conflicting duplicate classifications cannot be collapsed')
                repairs.append(dict(article_id=aid,kind='offline_remove_identical_duplicate_label_object',classifications_changed=False))
                continue
            unique.append(row)
            if aid is not None:seen[aid]=row
        obj['labels']=unique
    labels,other=_validate_core(json.dumps(obj,ensure_ascii=False),inputs)
    return labels,repairs+other
