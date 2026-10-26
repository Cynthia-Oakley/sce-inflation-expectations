"""Evaluation-only registry of public national lags at actual E cutoffs.

Release-day dates lack intraday times. A release on the cutoff date is not used;
this conservative rule is recorded rather than assuming an 11:00 release.
This does not certify the separate public release dates of microdata vintages.
"""
from datetime import datetime,timezone
from pathlib import Path
import html,re

from ..experiments.frozen_batch import ROOT,read_json,dump,sha

CATALOG=ROOT/'data/evaluation/sce_baselines_latest_20261007/aggregate_inputs.json'
NOV2018=ROOT/'data/raw/sce_main_preflight_20261023/an181210.html'


def eligible_release(releases,cutoff):
    eligible=[r for r in releases if r['published_date']<cutoff[:10]]
    return max(eligible,key=lambda r:(r['published_date'],r['reference_period'])) if eligible else None


def prepare(delivery,out):
    delivery,out=Path(delivery).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored registry directory required')
    releases=read_json(CATALOG)['headline_releases']
    text=' '.join(html.unescape(re.sub('<[^>]+>',' ',NOV2018.read_text())).split())
    excerpt='The median one-year ahead expected inflation rate was unchanged for the eighth straight month, at 3.0%'
    if 'December 10, 2018' not in text or excerpt not in text:raise ValueError('November 2018 release evidence mismatch')
    releases=[dict(reference_period='2018-11',value_pp=3.,published_date='2018-12-10',
        source_url='https://www.newyorkfed.org/newsevents/news/research/2018/an181210',
        source_file=str(NOV2018.relative_to(ROOT)),source_sha256=sha(NOV2018),audit_excerpt=excerpt),*releases]
    sources={str(CATALOG.relative_to(ROOT)):sha(CATALOG),str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))}
    for r in releases:
        p=ROOT/r['source_file']
        if sha(p)!=r['source_sha256']:raise ValueError('Release archive changed: '+r['source_file'])
        sources[r['source_file']]=r['source_sha256']
    rows=[]
    for f in sorted(delivery.glob('20*/environment.json')):
        e=read_json(f);cutoff=e['provider_args']['targets'][0]['as_of'];previous=eligible_release(releases,cutoff)
        if previous is None:raise ValueError('No eligible published national baseline for '+f.parent.name)
        rows.append(dict(month=f.parent.name,information_as_of=cutoff,last_eligible_public_headline=previous,
                         same_day_publications_excluded=[r['reference_period'] for r in releases if r['published_date']==cutoff[:10]],
                         microdata_vintage_certified=False))
        sources[str(f.relative_to(ROOT))]=sha(f)
    out.mkdir(parents=True)
    dump(out/'past_public_headlines.json',rows)
    result=dict(status='national_release_lags_registered_not_B_certification',months=len(rows),new_api_calls=0,
                retrieved_at_utc=datetime.now(timezone.utc).isoformat(),source_sha256=sources,
                registry_sha256=sha(out/'past_public_headlines.json'),
                scope='Evaluation-only national persistence/combination feature; no current target outcomes in registry',
                date_rule='Published date strictly before local cutoff date; same-day time uncertainty excluded',
                value_rule='Contemporaneous one-decimal press-release value; later chart precision is auxiliary and never silently substituted',
                limits=['National headline definition differs from the project frozen micro scorer.',
                        'Microdata vintage release times and strict-B P/initialization remain unverified.'])
    dump(out/'manifest.json',result)
    return {k:result[k] for k in ['status','months','new_api_calls']}
