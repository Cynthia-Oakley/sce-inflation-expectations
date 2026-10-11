"""Freeze new-period public news requests for the existing budget-gated runner.

Offline only. No credentials, network calls, simulation or questionnaire answers.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .news_exposure_demo import verify_sources
from .news_label_trial import guarded_payload
from .news_pool_preparation import FIELDS, partition_requests

ROOT = Path(__file__).resolve().parents[2]
PART_CAP = .25


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def freeze_requests(drafts, pending):
    """Keep prompts unchanged; establish reservations and a unique article ledger."""
    expected = {}
    for article in pending:
        if set(article) != set(FIELDS) or article['article_id'] in expected:
            raise ValueError('pending articles violate public whitelist or unique identity')
        expected[article['article_id']] = article
    requests, seen, prompt_hashes = [], set(), set()
    for index, draft in enumerate(drafts, 1):
        if draft['batch_id'] != index:
            raise ValueError('draft batch IDs must be continuous and unique')
        bound = len(json.dumps(draft['payload']['messages'], ensure_ascii=False).encode()) + 512
        if bound != draft['input_byte_reservation']:
            raise ValueError('draft reservation changed')
        row = {'batch_id': index, 'article_ids': draft['article_ids'], 'payload': draft['payload'],
               'input_token_reservation': bound,
               'request_usd_reservation': (bound * .30 + 2400 * 1.20) / 1e6}
        articles = guarded_payload(row)
        prompt_hashes.add(hashlib.sha256(row['payload']['messages'][0]['content'].encode()).hexdigest())
        for article in articles:
            identity = article['article_id']
            if identity in seen or expected.get(identity) != article:
                raise ValueError('duplicate article or draft differs from pending source')
            seen.add(identity)
        requests.append(row)
    if seen != set(expected) or len(prompt_hashes) != 1:
        raise ValueError('missing articles or inconsistent classification prompt')
    return requests, prompt_hashes.pop()


def prepare(inputs, out):
    inputs, out = map(Path, (inputs, out))
    if out.exists() or not out.resolve().is_relative_to(ROOT / 'outputs'):
        raise ValueError('use a new ignored outputs directory')
    plan = json.loads((inputs / 'summary.json').read_text())
    verify_sources(plan)
    pending_path = inputs / 'pending_public_articles.json'
    drafts_path = inputs / 'news_requests_draft.jsonl'
    pending = json.loads(pending_path.read_text())
    drafts = [json.loads(line) for line in drafts_path.read_text().splitlines()]
    requests, prompt_hash = freeze_requests(drafts, pending)
    sources = dict(plan['source_sha256'])
    paths = [inputs / 'summary.json', pending_path, drafts_path, Path(__file__),
             ROOT / 'studies/sce_inflation_expectations/news_label_trial.py',
             ROOT / 'studies/sce_inflation_expectations/news_pool_preparation.py',
             ROOT / 'studies/sce_inflation_expectations/news_selection_trial.py',
             ROOT / 'docs/literature/sce/news_selection/llm_label_prompt_v1_2.md']
    for path in paths:
        sources[str(path.resolve().relative_to(ROOT))] = sha(path)
    out.mkdir(parents=True)
    (out / 'source_module.py').write_bytes(Path(__file__).read_bytes())
    parts = []
    for part, subset in enumerate(partition_requests(requests, PART_CAP), 1):
        folder = out / f'part_{part:02d}'
        folder.mkdir()
        rows = [dict(row, batch_id=index + 1) for index, row in enumerate(subset)]
        request_file = folder / 'requests_prepared.jsonl'
        request_file.write_text(''.join(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n' for row in rows))
        reserved = sum(row['request_usd_reservation'] for row in rows)
        summary = {'status': 'offline_prepared_new_budget_required',
                   'unique_articles_to_label': sum(len(row['article_ids']) for row in rows),
                   'batches': len(rows), 'request_file_sha256': sha(request_file),
                   'source_sha256': sources, 'system_prompt_sha256': prompt_hash,
                   'preparation_module_sha256': sha(ROOT / 'studies/sce_inflation_expectations/news_selection_trial.py'),
                   'extension_preparation_module_sha256': sha(Path(__file__)),
                   'proposed_budget_usd': PART_CAP,
                   'total_usd_reservation_no_retries': reserved, 'retry_policy': 'none',
                   'new_project_api_calls': 0}
        dump(folder / 'summary.json', summary)
        parts.append({'part': part, 'folder': str(folder.resolve().relative_to(ROOT)),
                      'articles': summary['unique_articles_to_label'], 'batches': len(rows),
                      'reservation_usd': reserved, 'package_cap_usd': PART_CAP,
                      'request_sha256': sha(request_file), 'summary_sha256': sha(folder / 'summary.json')})
    result = {'status': 'prepared_not_authorized_not_run',
              'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'source_coverage_package': str(inputs.resolve().relative_to(ROOT)),
              'target_months': [month['target_month'] for month in plan['months']],
              'window_candidates': [{k: month[k] for k in ('target_month', 'as_of', 'new_labels_needed')}
                                    for month in plan['months']],
              'unique_new_articles': len(pending), 'new_batches': len(requests), 'parts': parts,
              'total_reservation_usd': sum(row['request_usd_reservation'] for row in requests),
              'proposed_total_cap_usd': len(parts) * PART_CAP,
              'pricing_basis': {'input_usd_per_million': .30, 'output_usd_per_million': 1.20,
                                'basis': 'peak uncached rates; actual weekend prices may be lower',
                                'verified_on': '2026-10-11',
                                'source': 'https://api-docs.deepseek.com/quick_start/pricing/'},
              'source_sha256': sources, 'retry_policy': 'none', 'new_api_calls': 0,
              'destination': 'https://api.deepseek.com/v1/chat/completions',
              'data_scope': 'public NYT metadata only; no population or SCE answers',
              'batch_size_max': 8, 'temperature': 0, 'requested_model': 'deepseek-flash',
              'execution_policy': 'one run chain per part; resume only unattempted batches; stop all parts on failure',
              'classification_contract': 'unchanged v1.2; different-time event repetition retained',
              'simulation_status': 'not_configured_not_authorized_not_run'}
    dump(out / 'summary.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.inputs, args.out)
    print(json.dumps({k: result[k] for k in ('unique_new_articles', 'new_batches',
                     'total_reservation_usd', 'proposed_total_cap_usd')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
