#!/usr/bin/env python3
"""Download public BLS ATUS files through an already connected browser.

No browser credentials are exported. Only public bls.gov links discovered in
official pages are fetched; local raw files/receipts are immutable on reuse.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def browser(code, session):
    request = Request('http://127.0.0.1:10086/command',
        data=json.dumps({'action': 'evaluate', 'args': {'code': code}, 'session': session}).encode(),
        headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=60) as response:
        result = json.load(response)
    if not result.get('ok'):
        raise RuntimeError(str(result.get('error')))
    value = result['data']['value']
    if value.get('status') != 200:
        raise RuntimeError(f'Public BLS request failed: {value}')
    return value


def public_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc != 'www.bls.gov' or not parsed.path.startswith('/tus/'):
        raise ValueError('Only official public ATUS links allowed')
    return url


def download(out, years, session, extra_urls=()):
    out = Path(out).resolve()
    if not out.is_relative_to(ROOT/'data/raw/behavior_references'):
        raise ValueError('Raw reference folder required')
    out.mkdir(parents=True, exist_ok=True)
    records = []

    def save(name, url, value, body):
        path, receipt = out/name, out/(name+'.receipt.json')
        digest = hashlib.sha256(body).hexdigest()
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('Preserve changed source; choose fresh version folder: '+name)
        else:
            path.write_bytes(body)
        record = {'file': name, 'requested_url': url, 'final_url': value['url'], 'bytes': len(body),
            'sha256': digest, 'http_last_modified': value.get('last_modified'),
            'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
            'retrieval_method': 'same-origin browser fetch; no credentials exported',
            'historical_release_date_verified': False, 'new_paid_calls': 0}
        if not receipt.exists():
            receipt.write_text(json.dumps(record, indent=2)+'\n')
        records.append(json.loads(receipt.read_text()))

    def page(url):
        public_url(url)
        code = '''(async()=>{const u=URL;const r=await fetch(u);if(!r.ok)return {status:r.status,url:r.url};
const html=await r.text();const d=new DOMParser().parseFromString(html,"text/html");
return {status:r.status,url:r.url,last_modified:r.headers.get("last-modified"),html,
links:Array.from(d.querySelectorAll("a[href]")).map(a=>({text:a.textContent.trim(),url:new URL(a.getAttribute("href"),u).href}))};})()'''.replace('URL', json.dumps(url), 1)
        value = browser(code, session)
        name = 'page_'+hashlib.sha256(url.encode()).hexdigest()[:12]+'.html'
        save(name, url, value, value.pop('html').encode())
        return value['links']

    def file(url):
        public_url(url)
        name = Path(urlparse(url).path).name
        path, receipt = out/name, out/(name+'.receipt.json')
        if path.exists() and receipt.exists():
            old = json.loads(receipt.read_text())
            if hashlib.sha256(path.read_bytes()).hexdigest() != old['sha256']:
                raise ValueError('Existing raw archive hash mismatch')
            records.append(old)
            print('Verified existing', name, flush=True)
            return
        code = '''(async()=>{const r=await fetch(URL);if(!r.ok)return {status:r.status,url:r.url};
const b=await r.arrayBuffer();if(b.byteLength>30000000)return {status:413,url:r.url};
const a=new Uint8Array(b);let s="";for(let i=0;i<a.length;i+=32768)s+=String.fromCharCode(...a.subarray(i,i+32768));
return {status:r.status,url:r.url,last_modified:r.headers.get("last-modified"),bytes:b.byteLength,base64:btoa(s)};})()'''.replace('URL', json.dumps(url), 1)
        value = browser(code, session)
        body = base64.b64decode(value.pop('base64'))
        if len(body) != value['bytes']:
            raise ValueError('Truncated browser transfer')
        if name.endswith('.zip'):
            with ZipFile(BytesIO(body)) as archive:
                if archive.testzip() is not None:
                    raise ValueError('Corrupt public ZIP')
        elif name.endswith('.pdf') and not body.startswith(b'%PDF'):
            raise ValueError('Expected public PDF, not error HTML')
        save(name, url, value, body)
        print('Downloaded', name, len(body), flush=True)

    eh_index = page('https://www.bls.gov/tus/modules/ehdatafiles.htm') if years else []
    basic_index = page('https://www.bls.gov/tus/data.htm') if years else []
    for year in years:
        eh = [r['url'] for r in eh_index if f'—{year} Eating' in r['text'] and 'Microdata' in r['text']]
        basic = [r['url'] for r in basic_index if f'—{year} Microdata' in r['text']]
        if len(eh) != 1 or len(basic) != 1:
            raise ValueError('Unique official year-page links required')
        for kind, url in [('eh', eh[0]), ('basic', basic[0])]:
            links = page(url)
            wanted = [r for r in links if r['url'].lower().endswith('.zip') and (
                ('EH Respondent' in r['text'] if kind == 'eh' else
                 ('Respondent file' in r['text'] or 'ATUS-CPS' in r['text'])))]
            if len(wanted) != (1 if kind == 'eh' else 2):
                raise ValueError('Unexpected year-file selection')
            for record in wanted:
                file(record['url'])
            if kind == 'eh':
                for record in links:
                    if record['url'].lower().endswith('.pdf') and any(v in record['text'] for v in ('Data Dictionary', 'Questionnaire')):
                        file(record['url'])
    for url in extra_urls:
        file(public_url(url))
    manifest = {'source': 'BLS official public ATUS/EH files discovered in official pages',
        'years': years, 'new_paid_calls': 0, 'credentials_exported': False,
        'historical_version_evidence_complete': False,
        'records': list({r['file']: r for r in records}.values())}
    target = out/'download_manifest.json'
    if target.exists():
        raise ValueError('Preserve completed manifest; use a fresh folder')
    target.write_text(json.dumps(manifest, indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--years', nargs='+', type=int, default=[2016, 2022, 2023])
    parser.add_argument('--session', default='sce-atus-20261019')
    parser.add_argument('--only-urls', nargs='+', help='Supplementary observed public BLS links, without year-page downloads')
    args = parser.parse_args()
    result = download(args.out, [] if args.only_urls else args.years, args.session, args.only_urls or ())
    print('Completed', len(result['records']), 'public files/pages; no paid calls.')
