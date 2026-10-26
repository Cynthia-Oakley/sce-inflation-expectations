"""Date-only diagnostics, time-eligible historical samplers and B engineering."""
import argparse
import calendar
import csv
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ..experiments.full_a_core_normal import ROOT,read,write,sha,fresh,checked
from ..experiments.media_timing_inputs import FRAME
from ..experiments.recent_b_rolling_preflight import select_source_wave
from ..experiments.recent_b_news_refresh import _load_labels,is_sce_report,B_SCE_PATTERN,text_of
from ..experiments.fullperiod_materialization import news_pool_for_prompts
from ..news_selection_trial import RecallRules,RULE_FILE
from ..submission_tools.reproduce import no_network
from .metrics import wasserstein1,quantile

PROTOCOL=ROOT/'docs/workstreams/20261026_response_dates/protocol.json'
METHODS=('uniform','previous_year_same_month','last6_available_months','same_month_last3_years')
LABELS={'uniform':'全月均匀','previous_year_same_month':'前一年同月','last6_available_months':'最近6个可得月','same_month_last3_years':'过去最多3年同月'}
B_INPUT=ROOT/'outputs/sce_recent_b_news_refresh_20261025_v3'


def shifted(month,delta):
    year,mon=divmod(int(month),100);year,zero=divmod(year*12+mon-1+delta,12)
    return year*100+zero+1


def days(month):return calendar.monthrange(int(month)//100,int(month)%100)[1]


def rebin(p,n):
    p=np.asarray(p,float)
    if p.ndim!=1 or not len(p) or np.any(p<0) or not np.isclose(p.sum(),1):raise ValueError('Probability vector required')
    a=np.arange(len(p))/len(p);b=np.arange(1,len(p)+1)/len(p)
    c=np.arange(n)/n;d=np.arange(1,n+1)/n
    overlap=np.maximum(0,np.minimum(b[:,None],d)-np.maximum(a[:,None],c))
    q=(p*len(p))@overlap
    if not np.isclose(q.sum(),1,atol=1e-12):raise ValueError('Rebin lost probability mass')
    return q/q.sum()


def distance(p,q):
    p,q=np.asarray(p,float),np.asarray(q,float)
    if p.shape!=q.shape or not np.isclose(p.sum(),1) or not np.isclose(q.sum(),1):raise ValueError('Same-length probabilities required')
    support=np.arange(1,len(p)+1)
    return dict(tvd=float(.5*np.abs(p-q).sum()),maximum_cdf_gap=float(np.max(abs(np.cumsum(p-q)))),
                w1_days=wasserstein1(support,p,support,q))


def candidate(pmfs,target,method,cutoff=None):
    n=days(target)
    if method=='uniform':return np.ones(n)/n,[]
    cutoff=cutoff or f'{int(target)//100:04}-{int(target)%100:02}-15T23:59:59-05:00'
    wave=select_source_wave(pmfs.keys(),cutoff,str(target))
    eligible=sorted(int(m) for m in pmfs if int(m)<=wave)
    if method=='previous_year_same_month':sources=[shifted(target,-12)]
    elif method=='last6_available_months':sources=eligible[-6:]
    elif method=='same_month_last3_years':sources=[shifted(target,-12*j) for j in range(1,4) if shifted(target,-12*j) in pmfs]
    else:raise ValueError('Unregistered date-distribution candidate')
    if not sources or any(m not in pmfs or m>wave for m in sources):raise ValueError('Unavailable date source')
    return np.mean([rebin(pmfs[m],n) for m in sources],axis=0),sources


def B_inventory(sources):
    s=read(B_INPUT/'summary.json');sources[str((B_INPUT/'manifest.json').relative_to(ROOT))]=sha(B_INPUT/'manifest.json')
    labels=_load_labels(s,sources);rules=RecallRules(read(RULE_FILE));sources[str(RULE_FILE.relative_to(ROOT))]=sha(RULE_FILE)
    rows=[];unique_missing=set()
    for old in s['coverage']:
        month=old['month'];date=f'{month[:4]}-{month[4:]}'
        raw_path=ROOT/'data/raw/nyt_archive'/f'{date}.json'
        raw_docs=read(raw_path)['response']['docs']
        observed_days=sorted({int(r['pub_date'][8:10]) for r in raw_docs if r.get('pub_date','')[:7]==date})
        missing_days=[d for d in range(1,days(month)+1) if d not in observed_days]
        cutoff_day=int(old['as_of'][8:10])
        # Only the ISO day matters for coverage; actual NY offset is retained.
        offset='-05:00' if int(month)%100 in (11,12,1,2) else '-04:00'
        end=f'{date}-{days(month):02}T23:59:59{offset}'
        pool,_,news_sources=news_pool_for_prompts(ROOT,date,end,rules);sources.update(news_sources)
        pool=[r for r in pool if not is_sce_report(r) and not B_SCE_PATTERN.search(text_of(r))]
        cutoff=datetime.fromisoformat(old['as_of'])
        late=[r for r in pool if datetime.fromisoformat(r['pub_date'].replace('Z','+00:00'))>cutoff]
        missing={r['article_id'] for r in pool if r['new_hits'] and r['article_id'] not in labels}
        late_missing={r['article_id'] for r in late if r['new_hits'] and r['article_id'] not in labels}
        unique_missing.update(missing)
        rows.append(dict(month=month,current_as_of=old['as_of'],full_month_as_of=end,
             raw_pool_after_SCE_filter=len(pool),later_than_current_cutoff=len(late),
             missing_basic_topic_labels=len(missing),late_missing_basic_topic_labels=len(late_missing),
             target_archive_docs=len(raw_docs),target_archive_observed_day_count=len(observed_days),
             target_archive_first_day=min(observed_days) if observed_days else None,
             target_archive_last_day=max(observed_days) if observed_days else None,
             target_archive_unobserved_days=missing_days,
             target_archive_unobserved_days_before_current_cutoff=[d for d in missing_days if d<=cutoff_day]))
        meta=raw_path.with_suffix('.meta.json')
        if meta.exists():sources[str(meta.relative_to(ROOT))]=sha(meta)
    return dict(monthly=rows,unique_missing_basic_topic_labels=len(unique_missing),
       full_month_news_pools_read=11,scope='Archive/basic-label inventory only; no per-day E/prompt certification',
       new_classification_calls=0)


def analyze(out):
    out=fresh(out);write(out/'protocol.json',read(PROTOCOL));sources={str(PROTOCOL.relative_to(ROOT)):sha(PROTOCOL),str(FRAME.relative_to(ROOT)):sha(FRAME),str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))}
    frame=pd.read_parquet(FRAME,columns=['date','survey_date','weight'])
    frame['date']=frame.date.astype(int);frame['completion']=pd.to_datetime(frame.survey_date,errors='coerce')
    same=frame.completion.dt.strftime('%Y%m').eq(frame.date.astype(str));valid=frame.completion.notna()&same
    target=frame.date.between(201901,202510)
    coverage=dict(source_rows=len(frame),source_months=int(frame.date.nunique()),target_rows=int(target.sum()),
       target_missing_dates=int((target&frame.completion.isna()).sum()),
       target_outside_month_dates=int((target&frame.completion.notna()&~same).sum()),
       target_valid_dates=int((target&valid).sum()),target_bad_weight_among_valid_dates=int((target&valid&(~np.isfinite(frame.weight)|frame.weight.le(0))).sum()))
    pmfs={'counts':{},'survey_weighted':{}};metadata={}
    for month,g in frame.loc[valid].groupby('date'):
        n=days(month);ix=g.completion.dt.day.to_numpy()-1
        count=np.bincount(ix,minlength=n).astype(float);pmfs['counts'][month]=count/count.sum()
        good=np.isfinite(g.weight)&g.weight.gt(0)
        weighted=np.bincount(ix[good],weights=g.loc[good,'weight'],minlength=n);pmfs['survey_weighted'][month]=weighted/weighted.sum()
        p=pmfs['counts'][month]
        metadata[str(month)]=dict(n=len(g),days=n,day1_10_share=float(p[:10].sum()),day11_20_share=float(p[10:20].sum()),
           day21_end_share=float(p[20:].sum()),mean_day=float(p@np.arange(1,n+1)),median_day=quantile(np.arange(1,n+1),p,.5))
    months=[m for m in pmfs['counts'] if 201901<=m<=202510]
    if len(months)!=82:raise ValueError('All82 A months required')
    macro=ROOT/'outputs/sce_full_a_macro_calibration_20261026_v1/monthly_inputs_public.csv'
    sources[str(macro.relative_to(ROOT))]=sha(macro)
    with macro.open() as f:releases={int(r['month']):r['cpi_published_at'][:10] for r in csv.DictReader(f)}
    records=[];noise=[];rng=np.random.default_rng(20261026)
    for weighting,hist in pmfs.items():
        for month in months:
            truth=hist[month];n=len(truth)
            release=releases[month];rday=int(release[8:10]) if release[:7].replace('-','')==str(month) else None
            for method in METHODS:
                pred,refs=candidate(hist,month,method);rec=dict(month=month,weighting=weighting,method=method,
                   source_months=refs,**distance(pred,truth))
                if rday is not None:
                    rec.update(cpi_release_day=rday,observed_share_after_release=float(truth[rday:].sum()),
                       predicted_share_after_release=float(pred[rday:].sum()),
                       exposure_error_pp=float(100*(pred[rday:].sum()-truth[rday:].sum())))
                records.append(rec)
            if weighting=='counts':
                draws=rng.multinomial(512,truth,size=500)/512
                noise.append(dict(month=month,mean_w1_days=float(np.abs(np.cumsum(draws-truth,axis=1)[:,:-1]).sum(axis=1).mean()),
                                  mean_maximum_cdf_gap=float(np.abs(np.cumsum(draws-truth,axis=1)).max(axis=1).mean())))
    aggregate={}
    for weighting in pmfs:
        aggregate[weighting]={}
        for method in METHODS:
            rr=[r for r in records if r['weighting']==weighting and r['method']==method]
            aggregate[weighting][method]={k:float(np.mean([r[k] for r in rr])) for k in ('w1_days','tvd','maximum_cdf_gap')}
            aggregate[weighting][method].update(median_w1_days=float(np.median([r['w1_days'] for r in rr])),
               mean_absolute_CPI_exposure_error_pp=float(np.mean([abs(r['exposure_error_pp']) for r in rr if 'exposure_error_pp' in r])))
    summary=dict(status='completed_date_only_sampler_diagnostic',coverage=coverage,aggregate=aggregate,
        metadata=metadata,monthly_comparisons=records,sampling_reference=noise,
        monthly_probabilities={w:{str(m):p.tolist() for m,p in hist.items()} for w,hist in pmfs.items()},
        mean_512_sampling_w1_days=float(np.mean([r['mean_w1_days'] for r in noise])),
        mean_512_sampling_CDF_gap=float(np.mean([r['mean_maximum_cdf_gap'] for r in noise])),
        B_engineering=B_inventory(sources),new_api_calls=0,current_Q8_Q9_columns_read=False,production_changed=False)
    # Proposed probability profiles only; no proxy IDs or live input files.
    plans=read(ROOT/'outputs/sce_recent_b_rolling_preflight_20261025_v1/monthly_input_plan.json')
    summary['B_candidate_probability_profiles']={p['month']:{method:dict(probabilities=candidate(pmfs['counts'],int(p['month']),method,p['as_of'])[0].tolist(),
       source_months=candidate(pmfs['counts'],int(p['month']),method,p['as_of'])[1]) for method in METHODS} for p in plans}
    write(out/'summary.json',summary)
    public=[{k:json_safe(v) for k,v in r.items()} for r in records]
    with (out/'monthly_date_comparisons.csv').open('w') as f:
        fields=list(dict.fromkeys(k for r in public for k in r));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(public)
    for p in (ROOT/'outputs/sce_recent_b_rolling_preflight_20261025_v1/monthly_input_plan.json',B_INPUT/'summary.json'):
        sources[str(p.relative_to(ROOT))]=sha(p)
    for name in ('evaluation/metrics.py','experiments/recent_b_rolling_preflight.py','experiments/recent_b_news_refresh.py',
                 'experiments/fullperiod_materialization.py','coverage_preparation.py','news_selection_trial.py'):
        path=ROOT/'studies/sce_inflation_expectations'/name;sources[str(path.relative_to(ROOT))]=sha(path)
    write(out/'manifest.json',dict(source_sha256=sources,files_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print('COVERAGE',coverage);print('AGGREGATE',aggregate);print('512 sample W1 days',summary['mean_512_sampling_w1_days'])
    print('B missing topic labels',summary['B_engineering']['unique_missing_basic_topic_labels'])


def json_safe(v):
    import json
    return json.dumps(v) if isinstance(v,list) else v


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    with no_network():analyze(a.out)


if __name__=='__main__':main()
