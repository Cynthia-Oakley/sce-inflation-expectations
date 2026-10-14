"""Source-proven inline quotation marks only. Never change semantic labels or retry."""
import hashlib
import json
from pathlib import Path
import re
import sys
from . import news_label_trial as base
from .news_label_quote_adapter import validate_with_quote_restoration as previous_adapter

def validate(content, inputs):
    try:
        return previous_adapter(content, inputs)
    except ValueError:
        pass
    obj=json.loads(content);originals={a['article_id']:a for a in inputs};repairs=[]
    quotes='"“”\'‘’'
    normalize=lambda text:' '.join(w.strip(quotes) for w in text.split()).casefold()
    for row in obj.get('labels',[]):
        if not isinstance(row,dict) or row.get('article_id') not in originals:continue
        evidence=row.get('evidence_snippet');original=originals[row['article_id']]
        if not isinstance(evidence,str) or not evidence:continue
        if any(evidence in original[field] for field in ('headline','abstract','snippet')):continue
        words=[w.strip(quotes) for w in evidence.split()]
        if len(words)<3 or not all(words):continue
        pattern=r'\s+'.join('['+re.escape(quotes)+']*'+re.escape(w)+'['+re.escape(quotes)+']*' for w in words)
        spans={m.group() for field in ('headline','abstract','snippet')
               for m in re.finditer(pattern,original[field],re.IGNORECASE)
               if normalize(m.group())==normalize(evidence)}
        if len(spans)==1:
            literal=spans.pop();row['evidence_snippet']=literal
            repairs.append(dict(article_id=row['article_id'],kind='restore_source_inline_quotes_only',
                                original_evidence_snippet=evidence,new_evidence_snippet=literal))
    labels,other=previous_adapter(json.dumps(obj,ensure_ascii=False),inputs)
    return labels,repairs+other

def main():
    argv=sys.argv[1:];out=Path(argv[argv.index('--out')+1])
    base.validate_with_evidence_shortening=validate
    base.main(argv)
    if (out/'state.json').exists():
        state=json.loads((out/'state.json').read_text());state['validation_adapter_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        state['validation_adapter_scope']='only uniquely source-proven inline single/double quotation marks; no decisions changed, no retries'
        base.dump(out/'state.json',state)

if __name__=='__main__':main()
