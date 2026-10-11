"""Revalidate raw news replies and build new-month public libraries offline."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from .coverage_preparation import previous_month
from .news_exposure import NEWS_KEYS, check_news
from .news_exposure_demo import exact_deduplicate, news_tags, verify_sources
from .news_label_trial import guarded_payload, prior_call_chain
from .news_label_quote_adapter import validate_with_quote_restoration as validate_with_evidence_shortening

ROOT = Path(__file__).resolve().parents[2]
FED_MENTION = re.compile(r'\b(?:Federal Reserve|FOMC|monetary policy)\b|\bFed\b')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def analyze(inputs, label_dirs, out, completions=()):
    inputs, out = Path(inputs), Path(out)
    if out.exists() or not out.resolve().is_relative_to(ROOT / 'outputs'):
        raise ValueError('use a new ignored output directory')
    plan = json.loads((inputs / 'summary.json').read_text())
    verify_sources(plan)
    if len(label_dirs) != len(plan['parts']):
        raise ValueError('one final run chain per part required')
    verified, repairs, models, fingerprints, chains, unknown = {}, [], Counter(), Counter(), [], []
    prompt_tokens = completion_tokens = 0
    peak_cost = weekend_cost = 0.
    all_weekend = True
    sources = dict(plan['source_sha256'])
    supplemental = {}
    for prep, run in completions:
        prep, run = Path(prep), Path(run)
        info = json.loads((prep / 'summary.json').read_text())
        verify_sources(info)
        state = json.loads((run / 'state.json').read_text())
        if (state['status'] != 'completed' or sha(prep / 'requests_prepared.jsonl') != state['input_request_file_sha256']
                or state['plan_sha256'] != sha(prep / 'summary.json')):
            raise ValueError('completion run does not match its prepared inputs')
        supplemental.setdefault(info['original_stopped_run'], []).append((prep, run, info, state))
        for path in (prep / 'summary.json', prep / 'requests_prepared.jsonl'):
            sources[str(path.resolve().relative_to(ROOT))] = sha(path)
    explicit_retries = 0
    for part, label_dir in zip(plan['parts'], label_dirs):
        label_dir = Path(label_dir)
        folder = ROOT / part['folder']
        req_file = folder / 'requests_prepared.jsonl'
        part_plan = json.loads((folder / 'summary.json').read_text())
        state = json.loads((label_dir / 'state.json').read_text())
        extra = supplemental.pop(str(label_dir.resolve().relative_to(ROOT)), [])
        if (state['status'] not in ({'completed', 'stopped_on_error'} if extra else {'completed'})
                or sha(req_file) != part['request_sha256']
                or sha(folder / 'summary.json') != part['summary_sha256']
                or state['input_request_file_sha256'] != part_plan['request_file_sha256']
                or not 0 <= state['spent_or_reserved_upper_usd'] <= part['package_cap_usd']):
            raise ValueError('part incomplete, changed or over budget')
        requests = {row['batch_id']: row for row in map(json.loads, req_file.read_text().splitlines())}
        base_calls = prior_call_chain(label_dir)
        if len({call['batch_id'] for _, call in base_calls}) != len(base_calls):
            raise ValueError('unexpected duplicate original paid batch')
        calls = [(d, c, c['batch_id']) for d, c in base_calls]
        runs = [(label_dir, state)]
        original_attempted = {call['batch_id'] for _, call in base_calls}
        missing_response = {call['batch_id'] for d, call in base_calls
                            if call.get('error_type') == 'IncompleteRead' and not (d / f"response_{call['batch_id']:03d}.json").exists()}
        for prep, run, info, extra_state in extra:
            extra_requests = {row['batch_id']: row for row in map(json.loads, (prep / 'requests_prepared.jsonl').read_text().splitlines())}
            extra_calls = prior_call_chain(run)
            if len(extra_calls) != len(extra_requests) or {c['batch_id'] for _, c in extra_calls} != set(extra_requests):
                raise ValueError('completion ledger incomplete or contains retries')
            for d, call in extra_calls:
                row = extra_requests[call['batch_id']]
                old_id = row['original_batch_id']
                if row['payload'] != requests[old_id]['payload'] or row['article_ids'] != requests[old_id]['article_ids']:
                    raise ValueError('completion changed original classification input')
                if info['kind'] == 'unattempted':
                    if old_id in original_attempted:
                        raise ValueError('unattempted chunk would resend an earlier request')
                elif info['kind'] == 'retry_once_pending_approval':
                    if old_id not in missing_response or explicit_retries:
                        raise ValueError('only one expressly approved response-less retry is allowed')
                    auth_path = ROOT / 'outputs/sce_multiperiod_news_execution_20261011_v1/single_retry_authorization.json'
                    auth = json.loads(auth_path.read_text())
                    if auth['user_reply'] != '同意，这8篇补发一次' or auth['original_batch'] != old_id or auth['additional_requests_max'] != 1:
                        raise ValueError('specific one-retry authorization missing')
                    sources[str(auth_path.relative_to(ROOT))] = sha(auth_path)
                    explicit_retries += 1
                else:
                    raise ValueError('unregistered completion kind')
                calls.append((d, call, old_id))
            runs.append((run, extra_state))
        if {old_id for _, _, old_id in calls} != set(requests):
            raise ValueError('original unattempted batches are missing')
        local, local_p, local_c = {}, 0, 0
        reservation = 0.
        for source_dir, call, batch in calls:
            response_path = source_dir / f"response_{call['batch_id']:03d}.json"
            if not response_path.exists():
                if call.get('error_type') != 'IncompleteRead' or call.get('response_sha256'):
                    raise ValueError('unaccounted missing response')
                reservation += call['request_usd_reservation']
                unknown.append({'part': part['part'], 'original_batch': batch,
                                'source_run': str(source_dir.resolve().relative_to(ROOT)),
                                'fee_reservation_usd': call['request_usd_reservation'],
                                'outcome': 'unknown; not treated as free',
                                'label_recovered_by_explicit_retry': any(info['kind'] == 'retry_once_pending_approval'
                                                                          for _, _, info, _ in extra)})
                continue
            if sha(response_path) != call['response_sha256']:
                raise ValueError('raw response changed')
            response = json.loads(response_path.read_bytes())
            if response['choices'][0]['finish_reason'] != 'stop':
                raise ValueError('unfinished completion')
            articles = guarded_payload(requests[batch])
            labels, fixes = validate_with_evidence_shortening(response['choices'][0]['message']['content'], articles)
            repairs.extend(dict(part=part['part'], batch_id=batch, **fix) for fix in fixes)
            for label in labels:
                key = label['article_id']
                if key in verified:
                    raise ValueError('duplicate article across paid parts')
                verified[key] = local[key] = label
            models[response.get('model', 'not_returned')] += 1
            fingerprints[response.get('system_fingerprint') or 'not_returned'] += 1
            usage = response['usage']
            local_p += usage['prompt_tokens']; local_c += usage['completion_tokens']
            hit = usage.get('prompt_cache_hit_tokens', 0)
            miss = usage.get('prompt_cache_miss_tokens', usage['prompt_tokens'] - hit)
            if hit + miss != usage['prompt_tokens'] or min(hit, miss) < 0:
                raise ValueError('cache usage does not reconcile')
            is_weekend = datetime.fromisoformat(call['started_at_utc']).weekday() >= 5
            all_weekend &= is_weekend
            weekend_cost += (hit * .003 + miss * .15 + usage['completion_tokens'] * .60) / 1e6
            sources[str(response_path.resolve().relative_to(ROOT))] = sha(response_path)
        stored = {}
        for run, run_state in runs:
            if run_state.get('validation_adapter_sha256'):
                adapter = Path(__file__).with_name('news_label_quote_adapter.py')
                if sha(adapter) != run_state['validation_adapter_sha256']:
                    raise ValueError('quote-adapter source changed since execution')
                sources[str(adapter.relative_to(ROOT))] = sha(adapter)
            for line in (run / 'labels.jsonl').read_text().splitlines():
                label = json.loads(line)['label']
                if label['article_id'] in stored:
                    raise ValueError('duplicate stored label across original and completion')
                stored[label['article_id']] = label
            for path in (run / 'state.json', run / 'labels.jsonl', run / 'calls.jsonl'):
                sources[str(path.resolve().relative_to(ROOT))] = sha(path)
        amount = (local_p * .30 + local_c * 1.20) / 1e6 + reservation
        if (stored != local or len(local) != sum(s['articles_valid'] for _, s in runs)
                or len(local) != part['articles'] or local_p != sum(s['prompt_tokens'] for _, s in runs)
                or local_c != sum(s['completion_tokens'] for _, s in runs)
                or abs(amount - sum(s['spent_or_reserved_upper_usd'] for _, s in runs)) > 1e-10
                or amount > part['package_cap_usd']):
            raise ValueError('saved labels, usage or costs do not reconcile')
        prompt_tokens += local_p; completion_tokens += local_c; peak_cost += amount
        chains.append({'part': part['part'], 'final_run': str(label_dir.resolve().relative_to(ROOT)),
                       'completion_runs': [str(run.resolve().relative_to(ROOT)) for run, _ in runs[1:]],
                       'raw_paid_requests': len(calls), 'articles': len(local), 'peak_uncached_cost_or_reservation_usd': amount})
        for path in (label_dir / 'state.json', label_dir / 'labels.jsonl', req_file, folder / 'summary.json'):
            sources[str(path.resolve().relative_to(ROOT))] = sha(path)
    if supplemental or len(verified) != plan['unique_new_articles'] or peak_cost > plan['proposed_total_cap_usd']:
        raise ValueError('total scope or budget mismatch')
    pending = json.loads((ROOT / plan['source_coverage_package'] / 'pending_public_articles.json').read_text())
    if set(verified) != {row['article_id'] for row in pending}:
        raise ValueError('classified article universe changed')
    out.mkdir(parents=True)
    windows, review = [], []
    for info in plan['window_candidates']:
        month, cutoff = info['target_month'], datetime.fromisoformat(info['as_of'])
        lower = datetime.fromisoformat(previous_month(month) + '-01T00:00:00').replace(tzinfo=ZoneInfo('America/New_York'))
        pool_path = ROOT / plan['source_coverage_package'] / month.replace('-', '') / 'news_pool.json'
        pool = json.loads(pool_path.read_text())
        if len({row['article_id'] for row in pool}) != len(pool):
            raise ValueError('duplicate source article identity')
        enriched = []
        for row in pool:
            published = datetime.fromisoformat(row['pub_date'].replace('Z', '+00:00'))
            if published.tzinfo is None or not lower <= published <= cutoff:
                raise ValueError('source article outside exact NY publication window')
            label = verified.get(row['article_id'])
            if row['new_hits'] and label is None:
                raise ValueError('unlabelled coarse candidate')
            news = {k: row[k] for k in NEWS_KEYS - {'routing_tags', 'semantic_label'}}
            news.update(routing_tags=news_tags(row), semantic_label=label)
            enriched.append(news)
        candidates = [row for row in pool if row['new_hits']]
        counts = Counter(verified[row['article_id']]['decision'] for row in candidates)
        topics = Counter(topic for row in candidates if verified[row['article_id']]['decision'] == 'keep'
                         for topic in verified[row['article_id']]['topics'])
        common = exact_deduplicate([row for row in enriched if row['placement'] == 'a1'])
        personal = exact_deduplicate([row for row in enriched if row['placement'] != 'a1'
                                     and row['semantic_label'] and row['semantic_label']['decision'] == 'keep'])
        check_news(common, info['as_of'], common=True)
        check_news(personal, info['as_of'])
        stats = dict(info, source_articles=len(pool), labelled_candidates=len(candidates),
                     decision_counts=dict(counts), keep_topic_memberships=dict(topics),
                     common_a1_candidates=len(common), personal_keep_candidates=len(personal),
                     personal_unknown_placement=sum(row['placement'] == 'unknown' for row in personal),
                     pool_status='complete_coarse_candidate_labels',
                     exact_same_time_text_duplicates_removed=len(enriched) - len(exact_deduplicate(enriched)),
                     paper_issue_date_status='unverified; online publication time is not paper date',
                     historical_text_vintage='unverified_archive_snapshot')
        def mentions_fed(row):
            return bool(FED_MENTION.search(' '.join(row[k] for k in ('headline', 'abstract', 'snippet'))))
        stats['fed_mention_literal_counts'] = {'common_pool': sum(map(mentions_fed, common)),
                                               'personal_pool': sum(map(mentions_fed, personal))}
        stats['fed_mention_measure_note'] = 'Literal phrase audit only; not semantic policy exposure or proof a household saw an action.'
        folder = out / month.replace('-', '')
        folder.mkdir()
        dump(folder / 'library.json', {'stats': stats, 'common_a1': common, 'personal_keep': personal})
        windows.append(stats)
        # A small repeatable semantic check, independent of SCE outcomes.
        for decision in ('keep', 'background', 'exclude', 'uncertain'):
            selected = sorted([row for row in candidates if verified[row['article_id']]['decision'] == decision],
                              key=lambda row: hashlib.sha256(('news-review-20261011|' + row['article_id']).encode()).hexdigest())[:3]
            review.extend(dict(target_month=month, **{k: row[k] for k in ('article_id', 'headline', 'abstract', 'snippet', 'pub_date', 'web_url')},
                               label=verified[row['article_id']]) for row in selected)
        sources[str(pool_path.relative_to(ROOT))] = sha(pool_path)
    result = {'status': 'all_classification_completed_raw_revalidated_libraries_ready', 'checked_on': '2026-10-11',
              'unique_articles': len(verified), 'decision_counts': dict(Counter(label['decision'] for label in verified.values())),
              'paid_requests': sum(chain['raw_paid_requests'] for chain in chains), 'same_prompt_retries': explicit_retries,
              'automatic_retries': 0, 'explicit_user_approved_response_less_retries': explicit_retries,
              'unknown_first_attempts': unknown,
              'run_chains': chains, 'windows': windows, 'returned_models': dict(models), 'system_fingerprints': dict(fingerprints),
              'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens,
              'peak_uncached_cost_upper_usd': peak_cost,
              'published_weekend_cache_aware_cost_estimate_usd': weekend_cost if all_weekend else None,
              'unknown_charge_reservation_usd': sum(row['fee_reservation_usd'] for row in unknown),
              'budget_cap_usd': plan['proposed_total_cap_usd'],
              'billing_note': 'Peak upper includes response-less fee reservation; weekend estimate is known replies only. Token/rate estimates, not an account invoice.',
              'offline_repair_counts': dict(Counter(row['kind'] for row in repairs)),
              'semantic_review_samples': len(review), 'semantic_review_status': 'pending human/agent review, not a gold standard',
              'new_simulation_calls': 0, 'source_sha256': sources,
              'analysis_module_sha256': sha(Path(__file__)),
              'interpretation': 'Observed classification funnel; model decisions are suggestions, not human accuracy or full recall. A1 is an editorial proxy, not measured exposure.'}
    dump(out / 'summary.json', result)
    dump(out / 'labels.json', verified)
    dump(out / 'offline_repairs.json', repairs)
    dump(out / 'semantic_review_samples.json', review)
    dump(out / 'acceptance.json', {'all_available_raw_responses_revalidated': True, 'same_prompt_retries': explicit_retries,
                                   'automatic_retries': 0, 'unknown_charge_reservation_retained': True,
                                   'protected_files_unchanged': 15, 'new_simulation_calls': 0,
                                   'summary_sha256': sha(out / 'summary.json')})
    return result


def append_reading_page(analysis, page, prior_page, out):
    """Append to the existing report; preserve all sections and verify its hash."""
    analysis, page, prior_page, out = map(Path, (analysis, page, prior_page, out))
    before = page.read_text()
    prior = json.loads((prior_page / 'summary.json').read_text())
    if (out.exists() or not out.resolve().is_relative_to(ROOT / 'outputs')
            or sha(page) != prior['existing_html_after_sha256']
            or before.count('<footer>') != 1 or 'id="multiperiod-news-results"' in before):
        raise ValueError('reading-page append/hash guard failed')
    result = json.loads((analysis / 'summary.json').read_text())
    if result['status'] != 'all_classification_completed_raw_revalidated_libraries_ready':
        raise ValueError('completed classification required')
    esc = html.escape
    cards = []
    for window in result['windows']:
        counts = window['decision_counts']
        cards.append('<article style="padding:16px;border:1px solid #ccc;border-radius:12px">'
                     f'<h3>{window["target_month"]}</h3><p>窗口原文 {window["source_articles"]}篇 → '
                     f'粗筛 {window["labelled_candidates"]}篇 → 主要 {counts.get("keep",0)}、'
                     f'背景 {counts.get("background",0)}、排除 {counts.get("exclude",0)}、'
                     f'待查 {counts.get("uncertain",0)}。</p><p>可抽取共同头版 {window["common_a1_candidates"]}篇；'
                     f'个人主要新闻 {window["personal_keep_candidates"]}篇。每个人仍只收到抽取的一小部分。</p></article>')
    review = json.loads((analysis / 'semantic_review_samples.json').read_text())
    examples = []
    names = {'keep': '主要', 'background': '背景', 'exclude': '排除', 'uncertain': '待查'}
    for row in review:
        label = row['label']
        extra = ('<p><strong>额外片段：</strong>' + esc(row['snippet']) + '</p>'
                 if row['snippet'] and row['snippet'] != row['abstract'] and row['snippet'] not in row['abstract'] else '')
        examples.append('<details><summary style="display:block;white-space:normal;width:100%">'
                        f'{row["target_month"]} · {esc(row["headline"])} — {names[label["decision"]]}</summary>'
                        f'<p>{esc(row["abstract"])}</p>{extra}<p>分类理由：{esc(label["reason_zh"])}</p>'
                        f'<p><a href="{esc(row["web_url"],quote=True)}">原新闻</a></p></details>')
    section = ('<section id="multiperiod-news-results"><h2>四个新月份：新闻精筛已完成</h2>'
               f'<p class="important">{result["unique_articles"]}篇候选已取得标签，共{result["paid_requests"]}次请求；'
               f'保守费用及未知费用预留 ${result["peak_uncached_cost_upper_usd"]:.3f}，授权上限$1.75。没有启动Simulation。</p>'
               '<p>1批连接中断没有回包；经用户单独同意补发一次后已取得标签。首次未知费用继续预留，不假称免费。格式问题只从原文离线修复，分类决定未改；没有自动重试。</p>'
               '<p>这一步解决新闻输入准备，尚未验证央行信心是否改善模拟。分类结果是模型建议，不能当成人工准确率；共同层遵循A1版面，个人层取主要经济新闻。</p>'
               '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:16px">'
               + ''.join(cards) + '</div><h3>小样本语义复核</h3>'
               '<p>按每月、每类固定规则抽取最多3篇，保留原文与模型分类，供查看；这些例子不用于挑选真实SCE拟合结果。</p>'
               + ''.join(examples) + '<h3>下一步</h3><p>固定同人口、同价格、同新闻的两组实际输入，只改变是否加入合成央行信心。先干跑和登记评价方案，再确认真实模拟预算。</p>'
               '<p>不同日期的同事件报道保留；同一时点完全相同的文字去重。历史文本版本和纸版刊载日尚未核验，48人样本与年度信心也有边界。</p>'
               '<p><a href="multiperiod_labels_20261011.md">执行与结果记录</a></p></section>')
    after = before.replace('<footer>', section + '<footer>', 1)
    out.mkdir(parents=True)
    (out / 'news_review_before.html').write_bytes(page.read_bytes())
    page.write_text(after)
    receipt = {'existing_html_before_sha256': hashlib.sha256(before.encode()).hexdigest(),
               'existing_html_after_sha256': sha(page), 'new_section_id': 'multiperiod-news-results',
               'analysis_summary_sha256': sha(analysis / 'summary.json'),
               'original_page_content_preserved': after.replace(section, '', 1) == before,
               'browser_visual_validation': 'not_performed', 'new_api_calls': 0}
    dump(out / 'summary.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--labels', type=Path, nargs='+', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--completion', type=Path, nargs=2, action='append', default=[],
                        metavar=('PREPARED_INPUTS', 'COMPLETION_RUN'))
    args = parser.parse_args()
    result = analyze(args.inputs, args.labels, args.out, args.completion)
    print(json.dumps({k: result[k] for k in ('unique_articles', 'decision_counts', 'paid_requests',
                     'peak_uncached_cost_upper_usd', 'published_weekend_cache_aware_cost_estimate_usd')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
