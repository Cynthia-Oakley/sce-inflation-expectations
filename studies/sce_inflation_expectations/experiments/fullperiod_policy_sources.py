"""Public official-policy source completion; no model API or survey records."""
from datetime import datetime
from html import unescape
from pathlib import Path
import re
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from .frozen_batch import ROOT,dump,read_json,sha

RAW=ROOT/'data/raw/sce_fullperiod_supplement_20261022'


def paragraphs(text):
    return [re.sub(r'\s+',' ',unescape(re.sub('<[^>]+>',' ',p))).strip()
            for p in re.findall(r'<p\b[^>]*>(.*?)</p>',text,re.S)]


def facts(text):
    """Extract sentences, never infer a historical policy narrative from targets."""
    result=[]
    for p in paragraphs(text):
        for sentence in re.split(r'(?<=[.!?])\s+(?=[A-Z])',p):
            lower=sentence.lower()
            rate=('target range for the federal funds rate' in lower and
                  any(v in lower for v in ('decided','maintain','raise','lower')))
            context=('inflation' in lower and any(v in lower for v in ('elevated','2 percent','2%','declined','eased','risen')))
            if (rate or context) and len(sentence)<650 and sentence not in result:
                result.append(sentence)
    rates=[s for s in result if 'target range for the federal funds rate' in s.lower()]
    if not rates: raise ValueError('No policy-rate decision sentence')
    chosen=[rates[0],*[s for s in result if s!=rates[0]][:2]]
    if len(chosen)<3:
        for paragraph in paragraphs(text):
            paragraph=re.sub(r'^For release.*?Share\s+','',paragraph)
            for sentence in re.split(r'(?<=[.!?])\s+(?=[A-Z])',paragraph):
                if (40<len(sentence)<650 and sentence not in chosen and
                    any(w in sentence.lower() for w in ('committee','economic','coronavirus','inflation')) and
                    not any(w in sentence.lower() for w in ('voting','media','contact','copyright'))):
                    chosen.append(sentence)
                    if len(chosen)==3: return chosen
    if len(chosen)!=3: raise ValueError('Three independent source sentences not available')
    return chosen


def fetch_and_build(delivery):
    import httpx
    RAW.mkdir(exist_ok=True)
    coverage=read_json(Path(delivery)/'coverage.json')['months']
    cutoff=max(r['as_of'][:10] for r in coverage)
    urls={'https://www.federalreserve.gov/newsevents/pressreleases/monetary20181219a.htm'}
    retrieved=[]; errors=[]
    with httpx.Client(timeout=30,follow_redirects=True) as client:
        for year in range(2019,2027):
            url=(f'https://www.federalreserve.gov/monetarypolicy/fomchistorical{year}.htm'
                 if year<=2020 else 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm')
            p=RAW/(f'fomc_calendar_{year}.html' if year<=2020 else 'fomccalendars.html')
            if not p.exists():
                response=client.get(url);response.raise_for_status();p.write_bytes(response.content)
            for href in re.findall(r'href=["\']([^"\']*monetary\d{8}a\.htm)["\']',p.read_text()):
                m=re.search(r'monetary(\d{4})(\d{2})(\d{2})a',href)
                py,pm,pd=m.groups();day=f'{py}-{pm}-{pd}'
                if '2018-12-19'<=day<=cutoff: urls.add(urljoin(url,href))
            retrieved.append(dict(file=str(p.relative_to(ROOT)),url=url,sha256=sha(p)))
        # Existing project pages are reused when the URL's exact filename agrees.
        old={p.name:p for p in (ROOT/'data/raw').glob('*/monetary*a.html')}
        policies={}
        for i,url in enumerate(sorted(urls)):
            stem=url.rsplit('/',1)[1].replace('.htm','.html');p=old.get(stem,RAW/stem)
            try:
                if not p.exists():
                    response=client.get(url);response.raise_for_status();p.write_bytes(response.content)
                text=p.read_text();m=re.search(r'monetary(\d{4})(\d{2})(\d{2})a',url)
                py,pm,pd=m.groups();day=f'{py}-{pm}-{pd}'
                # The release date also must appear on the original page.
                visible=unescape(re.sub('<[^>]+>',' ',text))
                expected=datetime.strptime(day,'%Y-%m-%d').strftime('%B %d, %Y')
                if re.sub(r' 0',' ',expected) not in re.sub(r'\s+',' ',visible) and expected not in re.sub(r'\s+',' ',visible):
                    raise ValueError('Release date not visibly confirmed')
                # All these statement timestamps are conservatively date-only:
                # end of the release day, avoiding the emergency Sunday 5pm
                # statement being incorrectly called available at 2pm.
                published=datetime.fromisoformat(day+'T23:59:59').replace(tzinfo=ZoneInfo('America/New_York')).isoformat()
                policies[day]=dict(file=str(p.relative_to(ROOT)),sha256=sha(p),source_sha256=sha(p),
                     published_at=published,source_url=url,facts=facts(text),
                     retrieved_at='2026-10-22',strict_B_eligible=False,
                     publication_precision='date_only_end_of_release_day',
                     vintage_note='Current official historical page; original dated bytes not independently recovered')
            except Exception as exc:
                errors.append(dict(url=url,error=repr(exc)))
            if (i+1)%10==0: print(f'Policy sources {i+1}/{len(urls)}',flush=True)
        dump(RAW/'policy_sources_full.json',policies)
        dump(RAW/'policy_source_receipt.json',dict(calendars=retrieved,errors=errors,source_count=len(policies),
             target_coverage=[dict(month=r['target_month'],latest_policy=max((k for k,v in policies.items() if v['published_at']<=r['as_of']),default=None)) for r in coverage],new_api_calls=0))
    pdf=RAW/'gallup_2018_topline.pdf';article=RAW/'gallup_2018_article.html'
    from pypdf import PdfReader
    if not re.search(r'2018 Apr 2-11\s+5\s+40\s+20\s+15\s+21',PdfReader(pdf).pages[2].extract_text()):
        raise ValueError('Gallup 2018 exact row changed')
    wave=dict(wave_id='gallup_2018_april',field_dates=['2018-04-02','2018-04-11'],published_date='2018-04-20',
              published_at_conservative='2018-04-20T23:59:59-04:00',national_source_percent=[5,40,20,15,21],
              national_sum=101,candidate_probabilities=[v/101 for v in [5,40,20,15,21]],
              source_url='https://news.gallup.com/file/poll/232901/180420EconomicLeaders.pdf',
              local_file=str(pdf.relative_to(ROOT)),sha256=sha(pdf),article_local_file=str(article.relative_to(ROOT)),
              article_sha256=sha(article),education_source=None,original_historical_bytes='not_independently_recovered',
              source_location='original 2018 topline page 3, Jerome Powell row; original article April 20 2018',strict_B_eligible=False)
    dump(RAW/'confidence_supplement.json',dict(waves=[wave],new_api_calls=0))
    return dict(policy_sources=len(policies),errors=errors,confidence_supplement=str(RAW/'confidence_supplement.json'))
