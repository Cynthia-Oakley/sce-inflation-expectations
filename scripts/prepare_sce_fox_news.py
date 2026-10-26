#!/usr/bin/env python3
"""Prepare Fox News / Fox Business sitemap candidates for the SCE
media-mechanism trial (NEWS_MECHANISM_PLAN_V3 section 3, step 2).

Subcommands:
  collect          enumerate official sitemaps, keyword-recall, fetch article
                   pages, apply deterministic slim4 labels (all five missing
                   windows or --month). Resumable; never overwrites raw work.
  wayback          verify keep/background candidates against Wayback CDX
                   (read-only public API); marks unverified on any failure.
  import-existing  copy Fox-only rows of the 2021-06 / 2022-06 manual samples
                   into this output dir (NYPost never imported).
  report           aggregate per-month funnels into summary.json.

Examples:
  python scripts/prepare_sce_fox_news.py collect --month 201905
  python scripts/prepare_sce_fox_news.py collect --all
  python scripts/prepare_sce_fox_news.py wayback --all
  python scripts/prepare_sce_fox_news.py import-existing
  python scripts/prepare_sce_fox_news.py report

Only free public read-only GETs (foxnews.com / foxbusiness.com sitemaps and
article pages, web.archive.org CDX). No credentials, no LLM calls, no
writes anywhere outside --out.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from studies.sce_inflation_expectations import fox_news_archive as fna  # noqa: E402

OUT = ROOT / 'outputs' / 'sce_fox_news_20261025_v1'
EXISTING_EXTERNAL = ROOT / 'outputs' / 'sce_media_mechanism_20261024_v1'
MISSING_MONTHS = (201905, 202009, 202109, 202112, 202312)
EXISTING_MONTHS = (202106, 202206)
ALL_MONTHS = MISSING_MONTHS + EXISTING_MONTHS


def cmd_collect(args) -> int:
    months = MISSING_MONTHS if args.all else (args.month,)
    fetcher = fna.UrlLibFetcher(min_interval=args.min_interval,
                                timeout=args.timeout, max_retries=args.retries)
    for month in months:
        window_start, as_of = fna.window_for_month(ROOT, month)
        out_dir = OUT / str(month)
        result = fna.collect_month(fetcher=fetcher, out_dir=out_dir, month=month,
                                   window_start=window_start, as_of=as_of,
                                   page_limit=args.page_limit)
        f = result['funnel']
        print(f"[{month}] window {window_start}..{as_of[:10]} "
              f"pages={f['sitemap_pages_scanned']} in_window={f['sitemap_entries_in_window']} "
              f"slug_recalled={f['slug_recalled']} fetched={f['article_fetch_ok']} "
              f"pub_in_window={f['published_in_window']} sce_excluded={f['excluded_sce_report']} "
              f"eligible={f['eligible']} decisions={f['decision_counts']}")
    return 0


def cmd_wayback(args) -> int:
    months = ALL_MONTHS if args.all else (args.month,)
    fetcher = fna.UrlLibFetcher(min_interval=args.min_interval, timeout=60.0,
                                max_retries=args.retries)
    for month in months:
        path = OUT / str(month) / 'candidates.json'
        if not path.exists():
            print(f'[{month}] candidates.json missing, skipped')
            continue
        payload = fna.read_json(path)
        state = fna._load_state(OUT / str(month))
        verified = unverified = skipped = 0
        for cand in payload['candidates']:
            aid = cand['article_id']
            if aid in state['wayback']:
                cand['wayback'] = state['wayback'][aid]
                skipped += 1
                continue
            rec = fna.verify_wayback(fetcher, cand['original_url'],
                                     cand['published_at'])
            fna.record_http(OUT / str(month),
                            'wayback:' + cand['original_url'],
                            200 if rec['status'] == 'archive_verified' else None,
                            0, None if rec['status'] == 'archive_verified' else rec.get('error'))
            state['wayback'][aid] = rec
            cand['wayback'] = rec
            if rec['status'] == 'archive_verified':
                verified += 1
            else:
                unverified += 1
            fna._atomic_write_json(OUT / str(month) / 'state.json', state)
        for cand in payload['candidates']:
            if cand['wayback']['status'] == 'archive_verified':
                cand['text_vintage_status'] = (
                    'wayback_capture_found_not_diffed_' + fna.utc_now_iso()[:10])
        fna._atomic_write_json(path, payload)
        print(f'[{month}] wayback verified={verified} unverified={unverified} '
              f'cached={skipped}')
    return 0


def cmd_import_existing(args) -> int:
    windows = fna.import_existing_fox(EXISTING_EXTERNAL, months=EXISTING_MONTHS)
    out_dir = OUT / 'existing_months'
    out_dir.mkdir(parents=True, exist_ok=True)
    for month, rows in windows.items():
        target = out_dir / f'{month}.json'
        if target.exists() and not args.force:
            print(f'[{month}] {target} exists, skipped (use --force)')
            continue
        payload = {'schema': 'sce_fox_existing_import/v1', 'month': int(month),
                   'source_dir': str(EXISTING_EXTERNAL.relative_to(ROOT)),
                   'import_rule': 'Fox-only; NYPost excluded; manual labels preserved',
                   'candidate_count': len(rows), 'candidates': rows}
        fna._atomic_write_json(target, payload)
        print(f'[{month}] imported {len(rows)} Fox candidates -> {target}')
    return 0


def cmd_report(args) -> int:
    summary = {'schema': 'sce_fox_collection_summary/v1',
               'generated_at': fna.utc_now_iso(), 'months': {}}
    for month in ALL_MONTHS:
        path = OUT / str(month) / 'candidates.json'
        if path.exists():
            payload = fna.read_json(path)
            summary['months'][str(month)] = {
                'window_start': payload['window_start'], 'as_of': payload['as_of'],
                'funnel': payload['funnel'],
                'candidate_count': len(payload['candidates'])}
        else:
            existing = OUT / 'existing_months' / f'{month}.json'
            if existing.exists():
                payload = fna.read_json(existing)
                summary['months'][str(month)] = {
                    'imported_from': payload['source_dir'],
                    'candidate_count': payload['candidate_count']}
    fna._atomic_write_json(OUT / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    default_out = OUT
    parser.add_argument('--out', type=Path, default=None,
                        help='output dir (default: outputs/sce_fox_news_20261025_v1)')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_col = sub.add_parser('collect')
    p_col.add_argument('--month', type=int, choices=MISSING_MONTHS)
    p_col.add_argument('--all', action='store_true')
    p_col.add_argument('--min-interval', type=float, default=2.0)
    p_col.add_argument('--timeout', type=float, default=30.0)
    p_col.add_argument('--retries', type=int, default=2)
    p_col.add_argument('--page-limit', type=int, default=400)
    p_col.set_defaults(func=cmd_collect)

    p_wb = sub.add_parser('wayback')
    p_wb.add_argument('--month', type=int, choices=ALL_MONTHS)
    p_wb.add_argument('--all', action='store_true')
    p_wb.add_argument('--min-interval', type=float, default=3.0)
    p_wb.add_argument('--retries', type=int, default=2)
    p_wb.set_defaults(func=cmd_wayback)

    p_imp = sub.add_parser('import-existing')
    p_imp.add_argument('--force', action='store_true')
    p_imp.set_defaults(func=cmd_import_existing)

    p_rep = sub.add_parser('report')
    p_rep.set_defaults(func=cmd_report)

    args = parser.parse_args()
    OUT = args.out or default_out
    if args.cmd == 'collect' and not args.all and not args.month:
        parser.error('collect requires --month or --all')
    if args.cmd == 'wayback' and not args.all and not args.month:
        parser.error('wayback requires --month or --all')
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
