"""Offline news recall trial and blind labeling inputs; no credentials/network."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import re

ROOT = Path(__file__).resolve().parents[2]
RULE_FILE = Path(__file__).with_name('news_keyword_rules_v1_2.json')
WINDOWS = {
    '202105': ('2021-04', '2021-05', '2021-05-12', 'outputs/local_runs/sce-local-openai-20261005T092656Z-202105-8d2e3b2c/environment_effective.json'),
    '202106': ('2021-05', '2021-06', '2021-06-10', 'outputs/local_runs/sce-local-openai-20261005T092656Z-202106-e4f49f76/environment_effective.json'),
    # Independent news-method check, not a new simulation date/as_of.
    '202109': ('2021-09', '2021-09', '2021-09-30', None),
}


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    return digest_bytes(path.read_bytes())


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def normalize(text):
    text = re.sub(r'(?<=\w)[‐‑‒–—-](?=\w)', ' ', text.casefold())
    return ' '.join(text.split())


def phrase_pattern(terms):
    return re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(normalize(t)) for t in sorted(terms, key=len, reverse=True)) + r')(?!\w)')


def spans(text, pattern):
    tokens = list(re.finditer(r'\w+', text))
    result = []
    for match in pattern.finditer(text):
        touched = [i for i, tok in enumerate(tokens) if tok.start() < match.end() and tok.end() > match.start()]
        if touched:
            result.append((touched[0], touched[-1], match.group()))
    return result


def near_matches(text, left, right, gap):
    pairs = []
    for a, b, term_a in spans(text, left):
        for c, d, term_b in spans(text, right):
            distance = max(0, max(c - b - 1, a - d - 1))
            if distance <= gap:
                pairs.append([term_a, term_b])
    return pairs


class RecallRules:
    def __init__(self, config):
        self.config = config
        self.patterns = {key: phrase_pattern(config[key]) for key in (
            'strong_terms', 'objects', 'change_context', 'price_terms',
            'price_changes', 'general_terms', 'economic_context')}

    def classify(self, doc):
        hits = []
        if normalize(doc.get('section_name') or '') in {normalize(x) for x in self.config['economic_sections']} or normalize(doc.get('news_desk') or '') in {normalize(x) for x in self.config['economic_desks']}:
            hits.append({'rule': 'economic_section', 'field': 'metadata', 'evidence': [doc.get('section_name'), doc.get('news_desk')]})
        fields = {'headline': (doc.get('headline') or {}).get('main') or '',
                  'abstract': doc.get('abstract') or '', 'snippet': doc.get('snippet') or ''}
        for field, value in fields.items():
            text = normalize(value)
            strong = [m.group() for m in self.patterns['strong_terms'].finditer(text)]
            if strong:
                hits.append({'rule': 'direct_economic_terms', 'field': field, 'evidence': sorted(set(strong))})
            for name, left, right, gap in (
                ('object_and_change', 'objects', 'change_context', self.config['object_gap']),
                ('price_and_change', 'price_terms', 'price_changes', self.config['price_gap']),
                ('general_economic_context', 'general_terms', 'economic_context', self.config['general_gap']),
            ):
                pairs = near_matches(text, self.patterns[left], self.patterns[right], gap)
                if pairs:
                    hits.append({'rule': name, 'field': field, 'evidence': pairs})
        return hits


def load_old_selector():
    spec = importlib.util.spec_from_file_location('nyt_old_rules_trial', ROOT / 'scripts/build_nyt_events.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_window(target, rules, old, source_hashes):
    previous, current, cutoff, old_path = WINDOWS[target]
    all_docs = []
    date_excluded = 0
    for month in dict.fromkeys((previous, current)):
        path = ROOT / 'data/raw/nyt_archive' / (month + '.json')
        source_hashes[str(path.relative_to(ROOT))] = digest(path)
        docs = json.loads(path.read_bytes())['response']['docs']
        for doc in docs:
            # Exact legacy date-level window. Do not claim instant-level PIT.
            if (doc.get('pub_date') or '')[:10] <= cutoff:
                all_docs.append((month, doc))
            else:
                date_excluded += 1
    if old_path:
        source_hashes[old_path] = digest(ROOT / old_path)
        old_selected = json.loads((ROOT / old_path).read_bytes())['provider_args']['events_by_step']['0']
        assert all(x['selection_cutoff'] == cutoff for x in old_selected)
    else:
        old_selected = old.select_events([d for _, d in all_docs], current, source_hashes[f'data/raw/nyt_archive/{current}.json'], 30)
    selected_ids = {e['event_id'] for e in old_selected}
    rows, seen = [], set()
    counts = Counter(raw_in_date_window=len(all_docs), excluded_after_date_cutoff=date_excluded)
    for month, doc in all_docs:
        if str(doc.get('document_type') or '').casefold() != 'article':
            counts['non_article'] += 1
            continue
        text = {k: doc.get(k) or '' for k in ('abstract', 'snippet')}
        text['headline'] = (doc.get('headline') or {}).get('main') or ''
        if not any(text.values()):
            counts['no_text'] += 1
            continue
        canonical_id = doc.get('_id') or doc.get('uri') or doc.get('web_url')
        if not canonical_id:
            counts['no_identity'] += 1
            continue
        if canonical_id in seen:
            counts['duplicate_article_id'] += 1
            continue
        seen.add(canonical_id)
        counts['unique_articles_with_text'] += 1
        text_hash = digest_bytes(json.dumps(text, sort_keys=True, ensure_ascii=False).encode())
        input_id = digest_bytes((canonical_id + '\n' + text_hash).encode())[:24]
        event_id = digest_bytes((doc.get('web_url') or '').encode())[:16]
        old_tier, old_keywords = old.classify_doc(doc)
        new_hits = rules.classify(doc)
        row = dict(text, article_id=input_id, canonical_source_id=canonical_id,
                   event_id=event_id, source='NYT Archive API', source_month=month,
                   pub_date=doc.get('pub_date'), section_name=doc.get('section_name') or '',
                   news_desk=doc.get('news_desk') or '', web_url=doc.get('web_url') or '',
                   text_sha256=text_hash, text_vintage_status='unverified_archive_snapshot',
                   new_hits=new_hits, old_tier=old_tier, old_keywords=old_keywords,
                   old_final=event_id in selected_ids)
        row['stratum'] = ('old_final' if row['old_final'] else
                          'new_only' if new_hits and old_tier is None else
                          'both_rules_not_final' if new_hits and old_tier else
                          'old_rule_only' if old_tier else 'neither_rule')
        # Old final is a census stratum regardless of whether new rules recall it.
        rows.append(row)
        counts['old_rule_candidates'] += old_tier is not None
        counts['new_rule_candidates'] += bool(new_hits)
        counts['old_final'] += row['old_final']
    assert counts['old_final'] == len(selected_ids)
    assert sum(counts[k] for k in ('non_article','no_text','no_identity','duplicate_article_id','unique_articles_with_text')) == len(all_docs)
    rng = random.Random(42 + int(target))
    sample = []
    strata = {}
    quotas = {'old_final': 100000, 'new_only': 30, 'both_rules_not_final': 30,
              'old_rule_only': 15, 'neither_rule': 15}
    for name, quota in quotas.items():
        pool = sorted((r for r in rows if r['stratum'] == name), key=lambda r: r['article_id'])
        chosen = pool if len(pool) <= quota else rng.sample(pool, quota)
        strata[name] = {'population': len(pool), 'sample': len(chosen),
                        'sampling': 'census' if len(chosen) == len(pool) else 'simple_random_without_replacement'}
        sample.extend(chosen)
    rule_counts = Counter(hit['rule'] for r in rows for hit in {x['rule']: x for x in r['new_hits']}.values())
    return rows, sample, {
        'target': target, 'role': 'independent_news_check' if old_path is None else 'development_window',
        'months': list(dict.fromkeys((previous,current))), 'cutoff_date': cutoff,
        'date_rule': 'legacy UTC pub_date first10 <= cutoff date; not precise New York timestamp PIT',
        'counts': dict(counts), 'strata': strata, 'rule_hits_article_counts_overlap': dict(rule_counts),
        'new_candidate_fraction_of_unique_articles': counts['new_rule_candidates']/counts['unique_articles_with_text'],
        'old_candidate_fraction_of_unique_articles': counts['old_rule_candidates']/counts['unique_articles_with_text'],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.mkdir(parents=True, exist_ok=False)
    conf = json.loads(RULE_FILE.read_bytes())
    rules = RecallRules(conf)
    old = load_old_selector()
    prompt_path = ROOT / 'docs/literature/sce/news_selection/llm_label_prompt_v1_2.md'
    system = re.search(r'```text\n(.*?)\n```', prompt_path.read_text(), re.S).group(1)
    sources = {str(RULE_FILE.relative_to(ROOT)): digest(RULE_FILE),
               str(prompt_path.relative_to(ROOT)): digest(prompt_path),
               'scripts/build_nyt_events.py': digest(ROOT / 'scripts/build_nyt_events.py')}
    summaries, unique_inputs = [], {}
    for target in WINDOWS:
        rows, sample, summary = prepare_window(target, rules, old, sources)
        write_json(out / f'pool_{target}.json', rows)
        write_json(out / f'sample_{target}.json', sample)
        summaries.append(summary)
        for row in sample:
            public = {k: row[k] for k in ('article_id','headline','abstract','snippet','source','section_name','news_desk')}
            if row['article_id'] in unique_inputs:
                assert public == unique_inputs[row['article_id']]
            unique_inputs[row['article_id']] = public
    ordered = [unique_inputs[k] for k in sorted(unique_inputs)]
    requests = []
    for index in range(0, len(ordered), 8):
        messages = [{'role': 'system', 'content': system},
                    {'role': 'user', 'content': json.dumps({'articles': ordered[index:index+8]}, ensure_ascii=False)}]
        payload = {'model':'deepseek-flash','temperature':0,'max_tokens':2400,
                   'response_format':{'type':'json_object'},'thinking':{'type':'disabled'},'messages':messages}
        # Conservative byte reservation, not a bill or exact tokenizer count.
        token_bound = len(json.dumps(messages,ensure_ascii=False).encode()) + 512
        cost_bound = (token_bound * .30 + payload['max_tokens'] * 1.20) / 1e6
        requests.append({'batch_id':len(requests)+1, 'article_ids':[r['article_id'] for r in ordered[index:index+8]],
                         'payload':payload,'input_token_reservation':token_bound,'request_usd_reservation':cost_bound})
    request_file = out/'requests_prepared.jsonl'
    request_file.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in requests))
    write_json(out/'inputs_unique.json',ordered)
    protected = json.loads((ROOT/'docs/sources/sol_handoff_protected_files_20261010.json').read_bytes())['files_sha256']
    assert all(digest(ROOT/p)==h for p,h in protected.items()), 'Protected work changed'
    summary = {'run_id':out.name,'prepared_at_utc':datetime.now(timezone.utc).isoformat(),
               'status':'offline_prepared; no model labels yet','windows':summaries,
               'unique_articles_to_label':len(ordered),'batches':len(requests),'batch_size':8,
               'request_file_sha256':digest(request_file),'system_prompt_sha256':digest_bytes(system.encode()),
               'source_sha256':sources,'preparation_module_sha256':digest(Path(__file__)),
               'total_usd_reservation_no_retries':sum(r['request_usd_reservation'] for r in requests),
               'pricing_url':'https://api-docs.deepseek.com/quick_start/pricing/',
               'peak_uncached_prices_per_million':{'input':.30,'output':1.20},
               'proposed_budget_usd':.25,'authorization_status':'pending_explicit_budget',
               'new_project_api_calls':0,'new_simulation_calls':0,'protected_files_unchanged':len(protected),
               'sampling_note':'Each target has disjoint strata; old final census plus fixed random samples. Rates require per-stratum weights, not pooled sample fraction. Cached text versions remain unverified.'}
    write_json(out/'summary.json',summary)
    print(json.dumps({'out':str(out),'unique_articles_to_label':len(ordered),'batches':len(requests),
                     'total_usd_reservation':summary['total_usd_reservation_no_retries'],
                     'windows':summaries},ensure_ascii=False))


if __name__ == '__main__':
    main()
