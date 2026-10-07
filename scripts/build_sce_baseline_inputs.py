#!/usr/bin/env python3
"""Prepare release-audited aggregate inputs and evaluation-only micro reference cache."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare_sce_baseline_sources import clean

PROTOCOL = ROOT / 'studies/sce_inflation_expectations/evaluation/baseline_protocol_v1.json'
RAW = ROOT / 'data/raw/sce_baselines_20261007'
OUT = ROOT / 'data/evaluation/sce_baselines_20261007'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_releases():
    import openpyxl
    protocol = json.loads(PROTOCOL.read_text())
    evidence = json.loads((RAW / 'release_evidence.json').read_text())['records']
    curated = {}
    for period, values in protocol['curated_first_release_headlines'].items():
        if isinstance(values, list):
            curated.update({f'{period}-{i + 1:02d}': v for i, v in enumerate(values)})
        else:
            curated[period] = values
    chart_path = ROOT / 'data/raw/sce_audit_20260928/chart.xlsx'
    workbook = openpyxl.load_workbook(chart_path, read_only=True, data_only=True)
    chart = {f'{int(row[0]) // 100}-{int(row[0]) % 100:02d}': float(row[1])
             for row in workbook['Inflation expectations'].iter_rows(min_row=5, values_only=True)
             if isinstance(row[0], (int, float)) and row[1] is not None}
    workbook.close()
    releases = []
    for period, value in sorted(curated.items()):
        candidates = [r for r in evidence if r['reference_period'] == period and r['inflation_passages']]
        if not candidates:
            raise ValueError(f'Missing core release evidence: {period}')
        record = min(candidates, key=lambda r: r['published_date'])
        text = ' '.join(record['inflation_passages'])
        match = re.search(rf'(?<![\d.]){value:.1f}\s*%', text)
        if not match:
            raise ValueError(f'Curated headline absent from source: {period} {value}')
        if sha(ROOT / record['file']) != record['sha256']:
            raise ValueError(f'Archived SCE release hash mismatch: {period}')
        # A short numerical excerpt is an audit locator, not a substitute for horizon review.
        words_before = text[:match.start()].split()[-9:]
        words_after = text[match.end():].split()[:7]
        quote = ' '.join(words_before + [match.group(0)] + words_after)
        releases.append(dict(reference_period=period, value_pp=value,
                             published_date=record['published_date'], source_url=record['source_url'],
                             source_file=record['file'], source_sha256=record['sha256'],
                             audit_excerpt=quote, chart_snapshot_value_pp=chart[period],
                             chart_rounded_agrees=abs(round(chart[period], 1) - value) < 1e-8))
    calendar = json.loads((RAW / 'cpi_calendar.json').read_text())
    if len({r['target_month'] for r in calendar}) != 60:
        raise ValueError('Need 60 distinct CPI cutoff dates')
    macro = json.loads((RAW / 'cpi_first_release_values.json').read_text())['records']
    for r in macro:
        text = (ROOT / r['file']).read_text()
        flat = re.sub(r'L\d+:\s*', ' ', text)
        flat = re.sub(r'\s+', ' ', flat)
        release = datetime.strptime(r['published_date'], '%Y-%m-%d')
        reference = datetime.strptime(r['reference_period'], '%Y-%m')
        visible_date = re.search(r'8:30 a\.m\. \(E[DS]?T\).*?' + re.escape(release.strftime('%B'))
                                 + r'\s+0?' + str(release.day) + ', ' + str(release.year), flat)
        title = re.search(r'CONSUMER PRICE INDEX\W+' + reference.strftime('%B %Y'), flat, re.I)
        if not visible_date or not title:
            raise ValueError(f'CPI title/publication date verification failed: {r["reference_period"]}')
        r['source_sha256'] = sha(ROOT / r['file'])
    data = dict(protocol_id=protocol['protocol_id'], headline_releases=releases,
                cpi_calendar=calendar, cpi_first_releases=macro,
                chart_source_sha256=sha(chart_path), chart_source='data/raw/sce_audit_20260928/chart.xlsx')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'aggregate_inputs.json').write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(json.dumps({'headline_releases': len(releases), 'cpi_releases': len(macro),
                      'headline_chart_rounding_disagreements': [r['reference_period'] for r in releases
                                                              if not r['chart_rounded_agrees']]}))


def compile_micro():
    import pandas as pd
    OUT.mkdir(parents=True, exist_ok=True)
    dest, metadata = OUT / 'micro_reference.parquet', OUT / 'micro_reference_sources.json'
    sources = [ROOT / 'data/raw/sce_p_sources/micro_2017_2019.xlsx',
               ROOT / 'data/raw/sce_audit_20260928/micro_2020_2024.xlsx']
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in sources}
    builder_hash = sha(Path(__file__))
    if dest.exists() and metadata.exists() and json.loads(metadata.read_text())['sources'] == hashes and json.loads(metadata.read_text()).get('builder_sha256') == builder_hash:
        print('Reusing hash-matched evaluation-only micro cache', flush=True)
        return
    columns = ['date', 'weight', 'Q9_mean', 'Q9_iqr', '_AGE_CAT', '_EDU_CAT']
    frames = []
    for p in sources:
        print('Reading official derived fields:', p.name, flush=True)
        df = pd.read_excel(p, sheet_name='Data', header=1, usecols=columns, engine='openpyxl')
        for col in ['date', 'weight', 'Q9_mean', 'Q9_iqr']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        for col in ['_AGE_CAT', '_EDU_CAT']:
            # Public SCE categories are textual labels, not integer codes.
            df[col] = df[col].astype('string').str.strip().replace('', pd.NA)
        df = df.loc[df['date'].between(201912, 202412)].copy()
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    for col in ['_AGE_CAT', '_EDU_CAT']:
        if not combined[col].notna().any():
            raise ValueError(f'Profile field lost during preparation: {col}')
    combined.to_parquet(dest, index=False)
    metadata.write_text(json.dumps(dict(sources=hashes, columns=columns, rows=len(combined),
                                        builder_sha256=builder_hash,
                                        category_coverage={k:int(combined[k].notna().sum()) for k in ['_AGE_CAT','_EDU_CAT']},
                                        cache_sha256=sha(dest),
                                        role='A reconstruction reference/evaluation; not B personas',
                                        scoring_version='official_provided_derived_values_latest_snapshot'), indent=2))
    print('Micro cache rows:', len(combined), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--micro', action='store_true')
    args = parser.parse_args()
    compile_releases()
    if args.micro:
        compile_micro()
