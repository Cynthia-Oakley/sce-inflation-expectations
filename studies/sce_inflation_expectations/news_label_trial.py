"""Budget-gated news classification, validation and audit; no simulation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
DECISIONS = {'keep','background','exclude','uncertain'}
TOPICS = {'living_prices','supply_costs','employment_income_consumption','policy','economic_outlook','other_economic'}
SCOPES = {'us_national','us_local','us_unspecified','us_and_global','global','non_us','unspecified'}
CLAIMS = {'fact','attributed_claim','mixed','unclear'}
LABEL_FIELDS = {'article_id','decision','topics','scope','claim_type','reason_zh','evidence_snippet'}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, obj):
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    temp.replace(path)


def append(path, obj):
    with path.open('a') as handle:
        handle.write(json.dumps(obj,ensure_ascii=False,allow_nan=False)+'\n')


def validate_labels(content, inputs):
    obj = json.loads(content)
    if not isinstance(obj,dict) or set(obj)!={'labels'} or not isinstance(obj['labels'],list):
        raise ValueError('expected exactly labels array')
    source = {x['article_id']:x for x in inputs}
    labels = obj['labels']
    if len(labels)!=len(source) or any(not isinstance(x,dict) for x in labels):
        raise ValueError('missing/extra or invalid label')
    ids = [x.get('article_id') for x in labels]
    if len(set(ids))!=len(ids) or set(ids)!=set(source):
        raise ValueError('duplicate or cross-batch IDs')
    for row in labels:
        if set(row)!=LABEL_FIELDS:
            raise ValueError('unexpected label fields')
        if row['decision'] not in DECISIONS or row['scope'] not in SCOPES or row['claim_type'] not in CLAIMS:
            raise ValueError('invalid enum')
        topics = row['topics']
        if not isinstance(topics,list) or any(not isinstance(t,str) or t not in TOPICS for t in topics) or len(set(topics))!=len(topics):
            raise ValueError('invalid topics')
        if not isinstance(row['reason_zh'],str) or not row['reason_zh'].strip():
            raise ValueError('reason missing')
        evidence = row['evidence_snippet']
        if not isinstance(evidence,str) or len(evidence.split())>12:
            raise ValueError('bad evidence length')
        original = source[row['article_id']]
        if evidence and not any(evidence in (original.get(field) or '') for field in ('headline','abstract','snippet')):
            raise ValueError('evidence is not verbatim from this article')
    return labels


def validate_with_evidence_shortening(content, inputs):
    """Only reconcile independently verified format/identity; never change classifications."""
    obj = json.loads(content)
    originals = {x['article_id']:x for x in inputs}
    repairs = []
    # A mistyped hash is recovered only when the original excerpt uniquely
    # proves one missing input AND its identifier differs by one character.
    # Response order alone is never evidence for article identity.
    rows = obj.get('labels', []) if isinstance(obj, dict) else []
    claimed = {r.get('article_id') for r in rows if isinstance(r, dict)}
    missing = set(originals) - claimed
    def one_edit(left, right):
        if not isinstance(left, str) or abs(len(left) - len(right)) > 1:
            return False
        if len(left) == len(right):
            return sum(a != b for a, b in zip(left, right)) == 1
        longer, shorter = (left, right) if len(left) > len(right) else (right, left)
        return any(longer[:i] + longer[i+1:] == shorter for i in range(len(longer)))
    for row in rows:
        if not isinstance(row, dict) or row.get('article_id') in originals:
            continue
        quote = row.get('evidence_snippet')
        candidates = [key for key in missing if isinstance(quote, str) and len(quote.split()) >= 3
                      and one_edit(row.get('article_id'), key)
                      and any(quote in (originals[key].get(f) or '') for f in ('headline', 'abstract', 'snippet'))]
        if len(candidates) != 1:
            raise ValueError('unmatched article ID lacks unique literal evidence and one-character typo')
        recovered = candidates[0]
        repairs.append({'kind': 'offline_identity_recovery_by_unique_literal_quote',
                        'original_article_id': row['article_id'], 'article_id': recovered,
                        'evidence_snippet': quote})
        row['article_id'] = recovered
        missing.remove(recovered)
    for row in obj.get('labels',[]) if isinstance(obj,dict) else []:
        if not isinstance(row,dict):
            continue
        evidence = row.get('evidence_snippet')
        original = originals.get(row.get('article_id'))
        if isinstance(evidence, str) and evidence and original and not any(
            evidence in (original.get(field) or '') for field in ('headline', 'abstract', 'snippet')
        ) and re.search(r'\.{3}|…', evidence):
            # An omitted span is formatting, not a continuous source quote.
            # Accept only fragments occurring IN ORDER in ONE original field.
            fragments = [f.strip() for f in re.split(r'\.{3}|…', evidence) if f.strip()]
            verified = False
            for field in ('headline', 'abstract', 'snippet'):
                text, position = original.get(field) or '', 0
                for fragment in fragments:
                    found = text.find(fragment, position)
                    if found < 0:
                        break
                    position = found + len(fragment)
                else:
                    verified = bool(fragments)
                if verified:
                    break
            if not verified:
                raise ValueError('ellipsis quote fragments do not match this article in order')
            fragment = max(fragments, key=len)
            repairs.append({'article_id':row['article_id'], 'kind':'offline_extract_verified_continuous_quote',
                            'original_evidence_snippet':evidence, 'new_evidence_snippet':fragment})
            evidence = row['evidence_snippet'] = fragment
        if isinstance(evidence, str) and evidence and original and len(evidence.split()) <= 12 and not any(
            evidence in (original.get(field) or '') for field in ('headline', 'abstract', 'snippet')
        ):
            fragments = []
            for field in ('headline', 'abstract', 'snippet'):
                text = original.get(field) or ''
                block = SequenceMatcher(None, evidence, text, autojunk=False).find_longest_match()
                fragment = evidence[block.a:block.a + block.size].strip()
                if len(fragment.split()) >= 3 and len(fragment) >= .7 * len(evidence) and fragment in text:
                    fragments.append(fragment)
            if not fragments:
                raise ValueError('nonliteral short quote has no substantial continuous source fragment')
            fragment = max(fragments, key=len)
            repairs.append({'article_id':row['article_id'], 'kind':'offline_clip_minor_quote_difference_to_literal_fragment',
                            'original_evidence_snippet':evidence, 'new_evidence_snippet':fragment})
            evidence = row['evidence_snippet'] = fragment
        extra = set(row)-LABEL_FIELDS
        if extra:
            allowed_echo = {'headline','abstract','snippet','source','section_name','news_desk'}
            if not original or not extra.issubset(allowed_echo) or any(row[k]!=original[k] for k in extra):
                raise ValueError('unexpected non-verbatim extra fields; cannot repair')
            repairs.append({'article_id':row['article_id'],'kind':'offline_remove_verbatim_input_echo',
                            'removed_fields':sorted(extra)})
            for key in extra:del row[key]
        if isinstance(evidence,str) and original and len(evidence.split())>12:
            if not any(evidence in (original.get(field) or '') for field in ('headline','abstract','snippet')):
                raise ValueError('long evidence not verbatim; cannot shorten')
            tokens = list(re.finditer(r'\S+',evidence))
            clipped = evidence[:tokens[11].end()]
            repairs.append({'article_id':row['article_id'],'kind':'offline_verbatim_quote_shortening',
                            'original_evidence_snippet':evidence,'new_evidence_snippet':clipped})
            row['evidence_snippet']=clipped
    return validate_labels(json.dumps(obj,ensure_ascii=False),inputs),repairs


def prior_call_chain(directory):
    """Every paid call once, with its original directory; never resend a batch."""
    paths,seen=[],set()
    while directory:
        directory=directory.resolve()
        if directory in seen:raise ValueError('cycle in prior runs')
        seen.add(directory);paths.append(directory)
        state=json.loads((directory/'state.json').read_bytes())
        parent=state.get('prior_run')
        directory=(ROOT/parent) if parent and not Path(parent).is_absolute() else Path(parent) if parent else None
    result=[]
    for path in reversed(paths):
        result.extend((path,json.loads(line)) for line in (path/'calls.jsonl').read_text().splitlines())
    return result


def dotenv_values(path):
    # Read only after explicit execution; never print keys or raw env lines.
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        key,value = line.split('=',1)
        values[key.strip()] = value.strip().strip('\"\'')
    return values


def guarded_payload(row):
    p = row['payload']
    if set(p)!={'model','temperature','max_tokens','response_format','thinking','messages'}:
        raise ValueError('unexpected request field')
    if p['model']!='deepseek-flash' or p['temperature']!=0 or p['max_tokens']!=2400 or p['thinking']!={'type':'disabled'} or p['response_format']!={'type':'json_object'}:
        raise ValueError('unregistered model/settings')
    if len(p['messages'])!=2 or p['messages'][0]['role']!='system' or p['messages'][1]['role']!='user':
        raise ValueError('unexpected messages')
    articles = json.loads(p['messages'][1]['content'])['articles']
    allowed = {'article_id','headline','abstract','snippet','source','section_name','news_desk'}
    if not articles or len(articles)>8 or any(set(a)!=allowed for a in articles):
        raise ValueError('input whitelist or batch gate')
    if [a['article_id'] for a in articles]!=row['article_ids']:
        raise ValueError('batch input IDs changed')
    bound = len(json.dumps(p['messages'],ensure_ascii=False).encode())+512
    amount = (bound*.30+p['max_tokens']*1.20)/1e6
    if bound!=row['input_token_reservation'] or abs(amount-row['request_usd_reservation'])>1e-12:
        raise ValueError('reservation changed')
    return articles


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--authorization-note')
    parser.add_argument('--prior-run',type=Path,help='Continue only unattempted batches; preserve prior outputs and cap')
    parser.add_argument('--dotenv',type=Path,default=ROOT.parent/'socioverse2_repo/.env')
    args = parser.parse_args(argv)
    plan = json.loads((args.inputs/'summary.json').read_bytes())
    requests_path = args.inputs/'requests_prepared.jsonl'
    if sha(requests_path)!=plan['request_file_sha256'] or sha(ROOT/'studies/sce_inflation_expectations/news_selection_trial.py')!=plan['preparation_module_sha256']:
        raise ValueError('preparation changed')
    for path, expected in plan['source_sha256'].items():
        if sha(ROOT/path)!=expected:
            raise ValueError('source changed: '+path)
    requests = [json.loads(line) for line in requests_path.read_text().splitlines()]
    ids = []
    for row in requests:
        inputs = guarded_payload(row)
        ids.extend(row['article_ids'])
        if hashlib.sha256(row['payload']['messages'][0]['content'].encode()).hexdigest()!=plan['system_prompt_sha256']:
            raise ValueError('system prompt changed')
    if len(ids)!=len(set(ids)) or len(ids)!=plan['unique_articles_to_label']:
        raise ValueError('prepared article set differs')
    cap = .25
    if plan['proposed_budget_usd']!=cap or sum(r['request_usd_reservation'] for r in requests)>cap:
        raise ValueError('budget does not cover planned reservation')
    print(json.dumps({'status':'validated offline','articles':len(ids),'batches':len(requests),'cap_usd':cap}),flush=True)
    if not args.execute:
        return
    if not args.authorization_note:
        raise ValueError('explicit new classification budget authorization required')
    # These inputs are public archive metadata, not personas or survey answers.
    config = dotenv_values(args.dotenv) if args.dotenv.exists() else {}
    key = os.environ.get('DEEPSEEK_API_KEY') or config.get('DEEPSEEK_API_KEY')
    if not key:
        host = os.environ.get('SV_LLM_BASE_URL') or config.get('SV_LLM_BASE_URL') or ''
        if host.rstrip('/') not in {'https://api.deepseek.com','https://api.deepseek.com/v1'}:
            raise ValueError('cannot establish credential as official DeepSeek')
        key = os.environ.get('SV_LLM_API_KEY') or config.get('SV_LLM_API_KEY')
    if not key:
        raise ValueError('official DeepSeek credential missing')
    args.out.mkdir(parents=True,exist_ok=False)
    state = {'run_id':args.out.name,'started_at_utc':stamp(),'status':'running',
             'authorization_note':args.authorization_note,'cap_usd':cap,
             'input_request_file_sha256':sha(requests_path),'plan_sha256':sha(args.inputs/'summary.json'),
             'execution_module_sha256':sha(Path(__file__)),'destination':'https://api.deepseek.com/v1/chat/completions',
             'articles_planned':len(ids),'batches_planned':len(requests),'batches_attempted':0,
             'batches_valid':0,'articles_valid':0,'spent_or_reserved_upper_usd':0.,
             'prompt_tokens':0,'completion_tokens':0,'errors':0,'retry_policy':'none',
             'cost_note':'Conservative token-cost estimate at peak uncached rates; not account billing. Unknown outcomes retain full reservation.'}
    attempted = set()
    if args.prior_run:
        prior = json.loads((args.prior_run/'state.json').read_bytes())
        if prior['input_request_file_sha256']!=sha(requests_path) or prior['cap_usd']!=cap or prior['destination']!=state['destination']:
            raise ValueError('prior scope/budget does not match')
        calls = prior_call_chain(args.prior_run)
        request_by_id = {row['batch_id']:row for row in requests}
        if len({c['batch_id'] for _,c in calls})!=len(calls):
            raise ValueError('duplicate paid batch in prior log')
        for source_directory,call in calls:
            batch_id = call['batch_id']
            attempted.add(batch_id)
            response_path = source_directory/f'response_{batch_id:03d}.json'
            if not response_path.exists() or sha(response_path)!=call.get('response_sha256'):
                raise ValueError('prior response cannot be verified; no retry')
            response = json.loads(response_path.read_bytes())
            choice = response['choices'][0]
            if choice.get('finish_reason')!='stop':
                raise ValueError('prior completion incomplete; no retry')
            inputs = guarded_payload(request_by_id[batch_id])
            labels,repairs = validate_with_evidence_shortening(choice['message']['content'],inputs)
            for label in labels:
                append(args.out/'labels.jsonl',{'batch_id':batch_id,'label':label,'prior_run':str(source_directory)})
            state['batches_valid']+=1;state['articles_valid']+=len(labels)
            append(args.out/'recovered_prior_batches.jsonl',{'batch_id':batch_id,'prior_run':str(source_directory),
                   'response_sha256':sha(response_path),'local_repairs':repairs,'new_api_calls':0})
        state['prior_run']=str(args.prior_run)
        state['batches_attempted']=len(attempted)
        state['spent_or_reserved_upper_usd']=prior['spent_or_reserved_upper_usd']
        state['prompt_tokens']=prior['prompt_tokens'];state['completion_tokens']=prior['completion_tokens']
        state['prior_errors_recorded']=prior['errors']
        state['prior_state_sha256']=sha(args.prior_run/'state.json')
    dump(args.out/'state.json',state)
    for row in requests:
        if row['batch_id'] in attempted:
            continue  # No same-prompt retries, including the initial batch.
        if state['spent_or_reserved_upper_usd']+row['request_usd_reservation']>cap:
            state['status']='budget_stopped'
            break
        inputs = guarded_payload(row)
        state['spent_or_reserved_upper_usd']+=row['request_usd_reservation']
        state['batches_attempted']+=1
        dump(args.out/'state.json',state)  # Reserve before dispatch.
        audit = {'batch_id':row['batch_id'],'started_at_utc':stamp(),
                 'article_ids':row['article_ids'],'request_usd_reservation':row['request_usd_reservation'],
                 'requested_model':row['payload']['model']}
        start = time.monotonic()
        try:
            req = urllib.request.Request(state['destination'],
                  data=json.dumps(row['payload'],ensure_ascii=False).encode(),
                  headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
            with urllib.request.urlopen(req,timeout=60) as response:
                raw = response.read()
                audit['http_status']=response.status
                audit['header_request_id']=response.headers.get('x-request-id')
            (args.out/f"response_{row['batch_id']:03d}.json").write_bytes(raw)
            reply = json.loads(raw)
            audit.update(response_sha256=hashlib.sha256(raw).hexdigest(),
                         response_id=reply.get('id'),returned_model=reply.get('model'),
                         system_fingerprint=reply.get('system_fingerprint'),usage=reply.get('usage'))
            usage = reply.get('usage') or {}
            p,c = usage.get('prompt_tokens'),usage.get('completion_tokens')
            if isinstance(p,int) and isinstance(c,int) and p>=0 and c>=0:
                cost = (p*.30+c*1.20)/1e6
                state['spent_or_reserved_upper_usd']+=cost-row['request_usd_reservation']
                state['prompt_tokens']+=p; state['completion_tokens']+=c
                audit['token_cost_estimate_peak_uncached_usd']=cost
                if p>row['input_token_reservation'] or c>row['payload']['max_tokens']:
                    raise ValueError('usage exceeded reservation; stop')
            choice = reply['choices'][0]
            audit['finish_reason']=choice.get('finish_reason')
            if choice.get('finish_reason')!='stop':
                raise ValueError('incomplete completion')
            labels,repairs = validate_with_evidence_shortening(choice['message']['content'],inputs)
            audit['local_repairs']=repairs
            for label in labels:
                append(args.out/'labels.jsonl',{'batch_id':row['batch_id'],'label':label})
            state['batches_valid']+=1
            state['articles_valid']+=len(labels)
            audit['validation']='pass'
        except Exception as exc:
            # No request/headers/env in errors; do not infer that failure was free.
            audit['error_type']=type(exc).__name__
            audit['error_detail']=str(exc)[:220]
            state['errors']+=1
            state['status']='stopped_on_error'
        audit['finished_at_utc']=stamp();audit['latency_ms']=round((time.monotonic()-start)*1000,1)
        append(args.out/'calls.jsonl',audit)
        dump(args.out/'state.json',state)
        if state['status']!='running':
            break
        if state['batches_attempted']%5==0:
            print(json.dumps({'batches_valid':state['batches_valid'],'articles_valid':state['articles_valid'],
                              'cost_estimate_upper_usd':state['spent_or_reserved_upper_usd']}),flush=True)
    if state['status']=='running':
        state['status']='completed' if state['articles_valid']==len(ids) else 'incomplete'
    state['finished_at_utc']=stamp()
    dump(args.out/'state.json',state)
    print(json.dumps(state,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
