#!/usr/bin/env python3
"""Free public archive downloads and deterministic aggregate macro extraction."""
import argparse
import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pypdf import PdfReader
from studies.sce_inflation_expectations.macro_profile_sources import employment_pdf, employment_html, bea_pdf, bea_xlsx, ArchiveHTML, check_employment_summary
from studies.sce_inflation_expectations.macro_population import month_shift
from scripts.build_sce_environment import BROWSER_HEADERS, DEFAULT_PROXY


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cached_get(url, path, fetch, proxy):
    if path.exists():
        return path.read_bytes()
    if not fetch:
        raise ValueError(f'uncached URL (use --fetch): {url}')
    import httpx
    with httpx.Client(proxy=proxy or None, headers=BROWSER_HEADERS, timeout=90, follow_redirects=True) as c:
        response = c.get(url)
        response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return response.content


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--macro-pool', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--fetch', action='store_true')
    ap.add_argument('--proxy', default=DEFAULT_PROXY)
    ap.add_argument('--bea-start', type=int, default=201801)
    ap.add_argument('--bea-end', type=int, default=202608)
    ap.add_argument('--pdf-only-bls', action='store_true', help='Keep candidate PDF extracts when archive HTML downloads are unavailable')
    ap.add_argument('--verify-bea-xlsx', action='store_true')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    cache = ROOT / 'data/raw/sce_macro_population'
    retrieved = datetime.now(timezone.utc).isoformat()
    pool = [json.loads(line) for line in args.macro_pool.read_text().splitlines()]
    releases = [r for r in pool if r['measure'] == 'Civilian unemployment rate, seasonally adjusted']

    def pdf_pages(path):
        memo = cache/'pdf_text'/f'{path.stem}_{sha(path)[:12]}.pages.json'
        if memo.exists():
            return json.loads(memo.read_text())
        pages = [p.extract_text() for p in PdfReader(path).pages]
        memo.parent.mkdir(parents=True, exist_ok=True)
        memo.write_text(json.dumps(pages, ensure_ascii=False)+'\n')
        return pages

    def bls_one(r):
        try:
            path = ROOT / r['source_file']
            if sha(path) != r['source_sha256'] or r['eligibility'] != 'eligible':
                raise ValueError('input source hash/eligibility mismatch')
            pages = pdf_pages(path)
            extracted = employment_pdf(pages, r['reference_period'])
            pdf_check = check_employment_summary(pages, extracted)
            url = r['source_url'].removesuffix('.pdf') + '.htm'
            html_path = cache / 'bls_html' / (path.stem + '.htm')
            html_error = None; check = None
            if not args.pdf_only_bls:
                html = cached_get(url, html_path, args.fetch, args.proxy).decode('utf-8')
                check = employment_html(html)
            else:
                html_error = 'not fetched in PDF-only mode; prior download attempt 403, full independent target validation pending'
            extracted_ue = next(x['value'] for x in extracted if x['series'] == 'LNS14000000')
            if abs(extracted_ue - r['value']) > 1e-8:
                raise ValueError('A-1 unemployment differs from independently verified prior pool')
            p, e = [next(x['value'] for x in extracted if x['series'] == s) for s in ['LNS11300000', 'LNS12300000']]
            if abs(e - p * (1-r['value']/100)) > .12:
                raise ValueError('CPS accounting identity fails beyond rounding')
            for row in extracted:
                if check is not None and row['reference_period'] == r['reference_period'] and abs(row['value'] - check[row['series']]) > 1e-8:
                    raise ValueError(f'PDF/HTML mismatch: {row["series"]}')
                row.update(published_at=r['published_at'], source_url=r['source_url'],
                           source_file=r['source_file'], source_sha256=r['source_sha256'],
                           source_version=r['source_version'], release_reference_period=r['reference_period'],
                           retrieved_at=retrieved, eligibility='eligible',
                           verification='target column independently matched archive HTML' if check else 'detail/summary PDF tables agree + independently verified prior UNRATE + CPS accounting identity; independent HTML pending',
                           independent_html_file=str(html_path.relative_to(ROOT)) if check else None,
                           independent_html_sha256=sha(html_path) if check else None, independent_html_error=html_error,
                           within_pdf_cross_check=pdf_check)
            return {'kind': 'bls', 'ref': r['reference_period'], 'rows': extracted}
        except Exception as e:
            return {'kind': 'bls', 'ref': r['reference_period'], 'error': str(e)}

    def bea_one(ref):
        try:
            y, m = divmod(ref, 100)
            release_year = y + (m == 12)
            url = f'https://www.bea.gov/news/{release_year}/personal-income-and-outlays-{calendar.month_name[m].lower()}-{y}'
            overrides = {
                201901: 'https://www.bea.gov/news/2019/personal-income-and-outlays-december-2018-personal-income-january-2019',
                201902: 'https://www.bea.gov/news/2019/personal-income-february-2019-personal-outlays-january-2019',
                202208: 'https://www.bea.gov/news/2022/personal-income-and-outlays-august-2022-and-annual-update',
            }
            url = overrides.get(ref, url)
            page = cache / 'bea' / f'pi_{ref}.htm'
            html = cached_get(url, page, args.fetch, args.proxy).decode('utf-8')
            soup = ArchiveHTML(); soup.feed(html)
            title = re.sub(r'\s+', ' ', ' '.join(soup.text))
            expected = rf'Personal Income and Outlays[:,]\s*{calendar.month_name[m]} {y}'
            special_expected = rf'Personal Income, {calendar.month_name[m]} {y}'
            if not re.search(expected, title) and not (ref in (201901, 201902) and re.search(special_expected, title)):
                raise ValueError('BEA reference title mismatch')
            links = [href for href, text in soup.links if 'Full Release' in text and href.endswith('.pdf')]
            if len(set(links)) != 1:
                raise ValueError('BEA full-release PDF link missing/ambiguous')
            from urllib.parse import urljoin
            pdf_url = urljoin(url, links[0])
            pdf = cache / 'bea' / f'pi_{ref}.pdf'
            data = cached_get(pdf_url, pdf, args.fetch, args.proxy)
            if not data.startswith(b'%PDF'):
                raise ValueError('not PDF bytes')
            rows = bea_pdf(pdf_pages(pdf), f'{y}-{m:02d}')
            release_date = datetime.fromisoformat(rows[0]['published_at'])
            date_pattern = rf'{release_date.strftime("%B")}\s+0?{release_date.day},\s*{release_date.year}'
            if not re.search(date_pattern, title, re.I):
                raise ValueError('BEA HTML/PDF embargo date differs')
            excel_path = None
            if args.verify_bea_xlsx:
                excel_links = [href for href, text in soup.links if 'Tables Only' in text and href.lower().endswith('.xlsx')]
                if len(set(excel_links)) != 1:
                    raise ValueError('BEA monthly XLSX link absent/ambiguous')
                excel_path = cache / 'bea' / f'pi_{ref}.xlsx'
                cached_get(urljoin(url, excel_links[0]), excel_path, args.fetch, args.proxy)
                check = bea_xlsx(excel_path)
                for series, values in check.items():
                    parsed = [r['value'] for r in rows if r['series'] == series]
                    if len(parsed) != len(values) or any(abs(a-b) > 1e-6 for a,b in zip(parsed, values)):
                        raise ValueError('BEA PDF/XLSX amounts disagree')
            for row in rows:
                row.update(source_url=pdf_url, release_page_url=url, source_file=str(pdf.relative_to(ROOT)),
                           source_sha256=sha(pdf), source_version='BEA release ' + rows[0]['published_at'],
                           release_reference_period=f'{y}-{m:02d}', retrieved_at=retrieved, eligibility='eligible',
                           verification='all monthly values independently matched official XLSX; PDF/HTML date checked' if excel_path else 'dated official PDF; HTML title/date cross-check; table values not independently reconciled',
                           independent_xlsx_file=str(excel_path.relative_to(ROOT)) if excel_path else None,
                           independent_xlsx_sha256=sha(excel_path) if excel_path else None)
            return {'kind': 'bea', 'ref': ref, 'rows': rows}
        except Exception as e:
            return {'kind': 'bea', 'ref': ref, 'error': str(e)}

    refs = []; ref = args.bea_start
    while ref <= args.bea_end:
        refs.append(ref); ref = month_shift(ref, 1)
    audit = []; observations = []
    # Limited concurrency; no MCP, model API, profile or secret sent.
    with ThreadPoolExecutor(max_workers=3) as ex:
        for kind, items, fn in [('bls', releases, bls_one), ('bea', refs, bea_one)]:
            for i, result in enumerate(ex.map(fn, items), 1):
                rows = result.pop('rows', [])
                observations.extend(rows); audit.append({**result, 'records': len(rows)})
                if i % 12 == 0:
                    print(f'{kind}: {i}/{len(items)}, failures={sum("error" in a for a in audit if a["kind"] == kind)}', flush=True)
    (args.out / 'observations.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in observations))
    (args.out / 'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
    summary = {'records': len(observations), 'releases': {k: sum(a['kind'] == k and 'error' not in a for a in audit) for k in ['bls', 'bea']},
               'failures': [a for a in audit if 'error' in a], 'real_llm_calls': 0, 'mcp_calls': 0,
               'retrieved_at': retrieved, 'input_pool_sha256': sha(args.macro_pool),
               'code_hashes': {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__).resolve(), ROOT/'studies/sce_inflation_expectations/macro_profile_sources.py']},
               'revision_policy': 'archive observations only; repeated past columns are partial historical vintages, not complete annual revision histories'}
    (args.out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'failures'}, ensure_ascii=False))
    print('failures:', len(summary['failures']))


if __name__ == '__main__':
    main()
