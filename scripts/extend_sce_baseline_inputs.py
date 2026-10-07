#!/usr/bin/env python3
"""Compile a new latest-data baseline version without rewriting the 60-month sources."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from prepare_sce_baseline_sources import clean


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--micro', action='store_true')
    p.add_argument('--raw', type=Path, default=ROOT/'data/raw/sce_baselines_latest_20261007')
    p.add_argument('--out', type=Path, default=ROOT/'data/evaluation/sce_baselines_latest_20261007')
    p.add_argument('--ledger', type=Path, default=ROOT/'docs/sources/sce_baseline_aggregate_sources_latest_20261007.json')
    a=p.parse_args()
    protocol_path=ROOT/'studies/sce_inflation_expectations/evaluation/baseline_protocol_latest_20261007.json'
    protocol=json.loads(protocol_path.read_text())
    old=json.loads((ROOT/'docs/sources/sce_baseline_aggregate_sources_20261007.json').read_text())
    import openpyxl
    chart_path=a.raw/'chart.xlsx'
    w=openpyxl.load_workbook(chart_path,read_only=True,data_only=True)
    chart={f'{int(r[0])//100}-{int(r[0])%100:02d}':float(r[1]) for r in w['Inflation expectations'].iter_rows(min_row=5,values_only=True) if isinstance(r[0],(float,int)) and r[1] is not None};w.close()
    evidence=json.loads((a.raw/'release_evidence.json').read_text())
    releases=list(old['headline_releases'])
    for year,values in protocol['curated_added_headlines'].items():
        for i,value in enumerate(values,1):
            month=f'{year}-{i:02d}'
            candidates=[r for r in evidence if r['reference_period']==month and r['inflation_passages']]
            rec=min(candidates,key=lambda r:r['published_date'])
            if rec['published_date'] > protocol['source_audit_date']:
                raise ValueError('Unreleased future headline')
            path=ROOT/rec['file']
            if sha(path)!=rec['sha256']:raise ValueError('SCE archive hash mismatch')
            passage=rec['inflation_passages'][0]
            match=re.search(rf'(?<![\d.]){value:.1f}\s*%',passage)
            if not match:raise ValueError(f'Curated value absent from first inflation passage: {month}')
            excerpt=' '.join(passage[:match.start()].split()[-8:]+[match.group()]+passage[match.end():].split()[:6])
            releases.append(dict(reference_period=month,value_pp=value,published_date=rec['published_date'],source_url=rec['source_url'],source_file=rec['file'],source_sha256=rec['sha256'],audit_excerpt=excerpt))
    releases.sort(key=lambda r:r['reference_period'])
    if len({r['reference_period'] for r in releases})!=len(releases):raise ValueError('Duplicate headline month')
    for r in releases:
        r['chart_snapshot_value_pp']=chart[r['reference_period']]
        r['chart_rounded_agrees']=abs(round(r['chart_snapshot_value_pp'],1)-r['value_pp'])<1e-8
    cal=json.loads((a.raw/'cpi_calendar_additions.json').read_text())
    macro=list(old['cpi_first_releases'])
    for r in cal:
        path=a.raw/('cpi_'+r['published_date'].replace('-','')+'.web.txt')
        text=re.sub(r'L\d+:\s*',' ',path.read_text());text=re.sub(r'\s+',' ',text)
        date=datetime.strptime(r['published_date'],'%Y-%m-%d');ref=datetime.strptime(r['reference_period'],'%Y-%m')
        header=re.search(r'8:30 a\.m\. \(E[DS]?T\).*?'+date.strftime('%B')+r'\s+0?'+str(date.day)+', '+str(date.year),text)
        title=re.search(r'CONSUMER PRICE INDEX\W+'+ref.strftime('%B %Y'),text,re.I)
        annual=re.search(r'Over the last 12 months, the all items index (increased|decreased) (\d+(?:\.\d+)?) percent before seasonal adjustment',text,re.I)
        usd=re.search(r'USDL-\d{2}-\d{4}',text)
        if not all([header,title,annual,usd]):raise ValueError(f'CPI first-release extraction failed: {r}')
        value=float(annual[2])*(-1 if annual[1].lower()=='decreased' else 1)
        macro.append(dict(reference_period=r['reference_period'],published_date=r['published_date'],value=value,unit='percent_year_over_year_nsa',source_url=r['release_url'],source_version=usd[0],file=str(path.relative_to(ROOT)),source_sha256=sha(path),audit_excerpt=annual[0]))
    data=dict(old,protocol_id=protocol['protocol_id'],headline_releases=releases,cpi_calendar=old['cpi_calendar']+cal,cpi_first_releases=macro,chart_source_sha256=sha(chart_path),chart_source=str(chart_path.relative_to(ROOT)),source_audit_date=protocol['source_audit_date'],coverage_notes={'headline_end':protocol['evaluation_end'],'micro_end':protocol['reconstruction_evaluation_end'],'no_cpi_release_months':['2025-11']})
    a.out.mkdir(parents=True,exist_ok=True)
    if (a.out/'aggregate_inputs.json').exists() or a.ledger.exists():raise FileExistsError('Preserve existing source versions')
    (a.out/'aggregate_inputs.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');a.ledger.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    if a.micro:
        import pandas as pd
        old_dir=ROOT/'data/evaluation/sce_baselines_20261007'
        old_meta=json.loads((old_dir/'micro_reference_sources.json').read_text())
        if sha(old_dir/'micro_reference.parquet')!=old_meta['cache_sha256']:raise ValueError('Old micro cache changed')
        columns=old_meta['columns'];latest=a.raw/'micro_latest.xlsx'
        df=pd.read_excel(latest,sheet_name='Data',header=1,usecols=columns,engine='openpyxl')
        for k in ['date','weight','Q9_mean','Q9_iqr']:df[k]=pd.to_numeric(df[k],errors='coerce')
        for k in ['_AGE_CAT','_EDU_CAT']:df[k]=df[k].astype('string').str.strip().replace('',pd.NA)
        combined=pd.concat([pd.read_parquet(old_dir/'micro_reference.parquet'),df],ignore_index=True)
        if combined['date'].max()!=int(protocol['reconstruction_evaluation_end'].replace('-','')):raise ValueError('Latest micro endpoint differs from declared version')
        dest=a.out/'micro_reference.parquet';combined.to_parquet(dest,index=False)
        metadata=dict(old_meta,sources={**old_meta['sources'],str(latest.relative_to(ROOT)):sha(latest)},rows=len(combined),builder_sha256=sha(Path(__file__)),cache_sha256=sha(dest),source_cache_sha256=sha(old_dir/'micro_reference.parquet'),category_coverage={k:int(combined[k].notna().sum()) for k in ['_AGE_CAT','_EDU_CAT']})
        (a.out/'micro_reference_sources.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps({'headlines':len(releases),'cpi_releases':len(macro),'headline_end':releases[-1]['reference_period'],'micro_end':protocol['reconstruction_evaluation_end']},indent=2))


if __name__=='__main__':
    main()
