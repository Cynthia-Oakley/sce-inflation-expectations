"""Prepare only previously unlabelled coarse candidates; no network or truth."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from .news_exposure_demo import verify_sources
from .news_label_trial import guarded_payload

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ('article_id', 'headline', 'abstract', 'snippet', 'source', 'section_name', 'news_desk')
MONTHS = ('202105', '202106')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def partition_requests(requests, cap=.25):
    """Use the existing fixed-$0.25 runner, with no duplicate batch across parts."""
    parts, current, reserved = [], [], 0.
    for row in requests:
        cost = row['request_usd_reservation']
        if cost > cap:
            raise ValueError('single request exceeds package cap')
        if current and reserved + cost > cap:
            parts.append(current)
            current, reserved = [], 0.
        current.append(row)
        reserved += cost
    if current:
        parts.append(current)
    return parts


def prepare(inputs, prior_labels, out):
    inputs, prior_labels, out = map(Path, (inputs, prior_labels, out))
    if out.exists() or not out.resolve().is_relative_to(ROOT / 'outputs'):
        raise ValueError('use a new ignored outputs directory')
    plan = json.loads((inputs / 'summary.json').read_text())
    verify_sources(plan)
    if json.loads((prior_labels / 'state.json').read_text())['status'] != 'completed':
        raise ValueError('prior label run incomplete')
    known = {}
    for line in (prior_labels / 'labels.jsonl').read_text().splitlines():
        label = json.loads(line)['label']
        if label['article_id'] in known:
            raise ValueError('duplicate prior label')
        known[label['article_id']] = label
    unique, stats = {}, []
    sources = dict(plan['source_sha256'])
    for p in [inputs / 'summary.json', prior_labels / 'labels.jsonl', prior_labels / 'state.json', Path(__file__)]:
        sources[str(p.resolve().relative_to(ROOT))] = sha(p)
    for month in MONTHS:
        p = inputs / f'pool_{month}.json'
        sources[str(p.resolve().relative_to(ROOT))] = sha(p)
        rows = json.loads(p.read_text())
        candidates = [r for r in rows if r['new_hits']]
        for row in candidates:
            public = {k: row[k] for k in FIELDS}
            if row['article_id'] in unique and unique[row['article_id']] != public:
                raise ValueError('cross-window source text differs')
            unique[row['article_id']] = public
        stats.append({'target': month, 'coarse_candidates': len(candidates),
                      'already_labelled': sum(r['article_id'] in known for r in candidates),
                      'unlabelled_memberships': sum(r['article_id'] not in known for r in candidates)})
    pending = [unique[k] for k in sorted(unique) if k not in known]
    prompt_path = ROOT / 'docs/literature/sce/news_selection/llm_label_prompt_v1_2.md'
    prompt = re.search(r'```text\n(.*?)\n```', prompt_path.read_text(), re.S).group(1)
    requests = []
    for index in range(0, len(pending), 8):
        articles = pending[index:index + 8]
        messages = [{'role': 'system', 'content': prompt},
                    {'role': 'user', 'content': json.dumps({'articles': articles}, ensure_ascii=False)}]
        payload = {'model': 'deepseek-flash', 'temperature': 0, 'max_tokens': 2400,
                   'response_format': {'type': 'json_object'}, 'thinking': {'type': 'disabled'}, 'messages': messages}
        bound = len(json.dumps(messages, ensure_ascii=False).encode()) + 512
        requests.append({'batch_id': len(requests) + 1, 'article_ids': [r['article_id'] for r in articles],
                         'payload': payload, 'input_token_reservation': bound,
                         'request_usd_reservation': (bound * .30 + 2400 * 1.20) / 1e6})
    out.mkdir(parents=True)
    (out / 'source_module.py').write_bytes(Path(__file__).read_bytes())
    dump(out / 'pending_articles.json', pending)
    records = []
    for part, subset in enumerate(partition_requests(requests), 1):
        folder = out / f'part_{part:02d}'
        folder.mkdir()
        rows = [dict(row, batch_id=i + 1) for i, row in enumerate(subset)]
        for row in rows:
            guarded_payload(row)
        request_path = folder / 'requests_prepared.jsonl'
        request_path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
        summary = {'status': 'offline_prepared_new_budget_required', 'windows': stats,
                   'unique_articles_to_label': sum(len(r['article_ids']) for r in rows), 'batches': len(rows),
                   'request_file_sha256': sha(request_path),
                   'system_prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                   'source_sha256': sources,
                   # Existing runner checks its original request-schema producer too.
                   'preparation_module_sha256': sha(ROOT / 'studies/sce_inflation_expectations/news_selection_trial.py'),
                   'complement_preparation_module_sha256': sha(Path(__file__)),
                   'proposed_budget_usd': .25, 'retry_policy': 'none',
                   'total_usd_reservation_no_retries': sum(r['request_usd_reservation'] for r in rows),
                   'new_project_api_calls': 0}
        dump(folder / 'summary.json', summary)
        records.append({'part': part, 'folder': str(folder.resolve().relative_to(ROOT)),
                        'articles': summary['unique_articles_to_label'], 'batches': len(rows),
                        'reservation_usd': summary['total_usd_reservation_no_retries'], 'package_cap_usd': .25})
    aggregate = {'status': 'prepared_not_run', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
                 'window_stats': stats, 'unique_coarse_candidates': len(unique),
                 'existing_labels_reused': len(set(unique) & known.keys()), 'unique_new_articles': len(pending),
                 'new_batches': len(requests), 'parts': records,
                 'total_reservation_usd': sum(r['request_usd_reservation'] for r in requests),
                 'proposed_total_cap_usd': len(records) * .25,
                 'pricing_basis': {'input_usd_per_million': .30, 'output_usd_per_million': 1.20,
                                   'source': 'https://api-docs.deepseek.com/quick_start/pricing/',
                                   'status': 'reuse previously verified peak rates; live page timed out 2026-10-11'},
                 'source_sha256': sources, 'retry_policy': 'none', 'new_api_calls': 0,
                 'destination': 'https://api.deepseek.com/v1/chat/completions',
                 'data_scope': 'public NYT article metadata only; no personas or SCE answers',
                 'temporal_repetition_policy': 'retain different-time coverage; no semantic event deletion',
                 'independent_check_month_added': False}
    dump(out / 'summary.json', aggregate)
    return aggregate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs', type=Path, default=ROOT / 'outputs/sce_nyt_selection_trial_20261011_v1')
    p.add_argument('--prior-labels', type=Path, default=ROOT / 'outputs/sce_nyt_label_trial_20261011_v3')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    result = prepare(a.inputs, a.prior_labels, a.out)
    print(json.dumps({k: result[k] for k in ('unique_new_articles', 'new_batches', 'total_reservation_usd', 'proposed_total_cap_usd')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
