#!/usr/bin/env python3
"""Prepare only unlabeled public articles for reference scaleup; never call API."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def prepare(out):
    from studies.sce_inflation_expectations.expanded_state_inputs import labels
    from studies.sce_inflation_expectations.coverage_preparation import build_news_pool
    from studies.sce_inflation_expectations.news_selection_trial import RecallRules, RULE_FILE
    from studies.sce_inflation_expectations.news_label_trial import guarded_payload
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh ignored output required')
    coverage_path = ROOT / 'docs/workstreams/20261017_finance_validation/scaleup_coverage.json'
    coverage = json.loads(coverage_path.read_text())
    prompt_path = ROOT / 'docs/literature/sce/news_selection/llm_label_prompt_v1_2.md'
    system = re.search(r'```text\n(.*?)\n```', prompt_path.read_text(), re.S).group(1)
    known, hashes = labels()
    for path in (coverage_path, RULE_FILE, prompt_path, Path(__file__),
                 ROOT / 'studies/sce_inflation_expectations/news_label_trial.py',
                 ROOT / 'studies/sce_inflation_expectations/expanded_news_quote_adapter.py'):
        hashes[str(path.relative_to(ROOT))] = sha(path)
    rules = RecallRules(json.loads(RULE_FILE.read_text()))
    unique, monthly = {}, []
    out.mkdir(parents=True)
    for row in coverage['rows']:
        month = row['month']
        pool, counts, source = build_news_pool(ROOT, f'{month//100}-{month%100:02}', row['as_of'], rules)
        hashes.update(source)
        missing = [r for r in pool if r['new_hits'] and r['article_id'] not in known]
        dump(out / f'pool_{month}.json', pool)
        for item in missing:
            public = {k: item[k] for k in ('article_id','headline','abstract','snippet','source','section_name','news_desk')}
            if item['article_id'] in unique and public != unique[item['article_id']]:
                raise ValueError('Conflicting repeated article')
            unique[item['article_id']] = public
        monthly.append({'month': month, 'as_of': row['as_of'], 'missing_before_dedup': len(missing), **counts})
    articles = [unique[k] for k in sorted(unique)]
    if len(articles) != coverage['news_unique_missing_labels']:
        raise ValueError('Coverage changed; do not silently widen scope')
    requests = []
    for start in range(0, len(articles), 8):
        group = articles[start:start+8]
        messages = [{'role':'system','content':system},
                    {'role':'user','content':json.dumps({'articles':group},ensure_ascii=False)}]
        bound = len(json.dumps(messages,ensure_ascii=False).encode()) + 512
        request = {'batch_id': len(requests)+1, 'article_ids':[r['article_id'] for r in group],
            'payload':{'model':'deepseek-flash','temperature':0,'max_tokens':2400,
                       'response_format':{'type':'json_object'},'thinking':{'type':'disabled'},'messages':messages},
            'input_token_reservation':bound, 'request_usd_reservation':(bound*.3+2400*1.2)/1e6}
        guarded_payload(request)
        requests.append(request)
    parts, chunks, current, amount = [], [], [], 0.
    for row in requests:
        if current and amount + row['request_usd_reservation'] > .25:
            chunks.append(current);current=[];amount=0.
        if row['request_usd_reservation'] > .25:
            raise ValueError('Single news batch exceeds cap')
        current.append(row);amount+=row['request_usd_reservation']
    if current:
        chunks.append(current)
    for i, chunk in enumerate(chunks,1):
        dest = out / f'part_{i:02}'
        dest.mkdir()
        request_path = dest / 'requests_prepared.jsonl'
        request_path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in chunk))
        n = sum(len(row['article_ids']) for row in chunk)
        summary = {'status':'prepared_no_calls_pending_explicit_budget','unique_articles_to_label':n,
            'batches':len(chunk),'request_file_sha256':sha(request_path),
            'system_prompt_sha256':hashlib.sha256(system.encode()).hexdigest(),
            'preparation_module_sha256':sha(ROOT/'studies/sce_inflation_expectations/news_selection_trial.py'),
            'source_sha256':hashes,'proposed_budget_usd':.25,'retry_policy':'none',
            'total_usd_reservation_no_retries':sum(row['request_usd_reservation'] for row in chunk)}
        dump(dest/'summary.json',summary)
        parts.append({'part':i,'folder':str(dest.relative_to(ROOT)),'batches':len(chunk),'articles':n,'cap_usd':.25,
                      'summary_sha256':sha(dest/'summary.json'),'requests_sha256':sha(request_path)})
    dump(out/'pending_public_articles.json',articles)
    dump(out/'monthly_coverage.json',monthly)
    manifest = {'status':'prepared_requires_budget_authorization','prepared_at_utc':datetime.now(timezone.utc).isoformat(),
        'articles':len(articles),'batches':len(requests),'batch_size':8,'parts':parts,
        'run_parent':'outputs/sce_reference_news_run_20261017_v1',
        'conservative_reservation_usd':sum(row['request_usd_reservation'] for row in requests),
        'proposed_cap_usd':sum(p['cap_usd'] for p in parts),'new_api_calls':0,
        'estimated_note':'Byte upper bounds with max2400 output at peak uncached rates; no retries, no population inputs.',
        'source_sha256':hashes,'system_prompt_sha256':hashlib.sha256(system.encode()).hexdigest()}
    dump(out/'manifest.json',manifest)
    return manifest


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    m=prepare(args.out)
    print(json.dumps({k:m[k] for k in ('status','articles','batches','conservative_reservation_usd','proposed_cap_usd','new_api_calls')},indent=2))
