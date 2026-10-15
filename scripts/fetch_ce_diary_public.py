#!/usr/bin/env python3
"""Download explicit public BLS CE Diary CSV archives; no credentials/API."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1];out=a.out.resolve()
    if out.exists() or not out.is_relative_to(root/'data/raw/ce_experience'):raise ValueError('Fresh CE raw directory required')
    out.mkdir(parents=True)
    def fetch(year):
        url=f'https://www.bls.gov/cex/pumd/data/comma/diary{year%100:02d}.zip'
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (academic research)'})
            with urllib.request.urlopen(req,timeout=45) as response:
                blob=response.read();status=response.status;final=response.url
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                assert z.testzip() is None
                files=[n for n in z.namelist() if n.lower().endswith('.csv')]
                assert any('fmld' in n.lower() for n in files) and any('expd' in n.lower() for n in files)
            path=out/f'diary{year%100:02d}.zip';path.write_bytes(blob)
            return {'year':year,'url':url,'final_url':final,'http_status':status,'bytes':len(blob),
                'sha256':hashlib.sha256(blob).hexdigest(),'path':str(path.relative_to(root)),
                'csv_members':files,'status':'downloaded_valid_zip','vintage':'current archive fetched now; not a verified first-release vintage',
                'historical_release_date':None}
        except Exception as exc:
            return {'year':year,'url':url,'status':'download_failed','error_type':type(exc).__name__,'error':str(exc)[:300]}
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(fetch,[2019,2021,2022]))
    manifest={'fetched_at_utc':datetime.now(timezone.utc).isoformat(),'listing':'https://www.bls.gov/cex/pumd_data.htm',
              'new_paid_api_calls':0,'files':results}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([{k:r.get(k) for k in ['year','status','bytes','error']} for r in results]))


if __name__=='__main__':main()
