#!/usr/bin/env python3
"""Archive official current public GSS2018 data; no historical-vintage claim."""
from datetime import datetime, timezone
import argparse, hashlib, json, zipfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'official_stata_index.html': 'https://gss.norc.org/get-the-data/stata.html',
    'gss2018_stata.zip': 'https://gss.norc.org/content/dam/gss/get-the-data/documents/stata/2018_stata.zip',
    'sce_chart_guide.pdf': 'https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/glossary/frbny-sce-chartglossary.pdf',
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-root', type=Path, default=ROOT/'data/raw/psychological/gss/2018')
    args = parser.parse_args()
    folder = args.out_root/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_%f')
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {'historical_version_proven': False, 'files': [], 'note': 'Current official files for A exploration; no credentials or paid services.'}
    try:
        for name, url in SOURCES.items():
            with urlopen(Request(url, headers={'User-Agent':'Mozilla/5.0 academic data audit'}), timeout=60) as response:
                data = response.read(100_000_001)
                if len(data)>100_000_000:
                    raise ValueError('Download exceeds size bound')
                if name.endswith('.pdf') and not data.startswith(b'%PDF-'):
                    raise ValueError('Expected a PDF')
                record = {'url':url, 'resolved_url':response.geturl(), 'downloaded_at_utc':datetime.now(timezone.utc).isoformat(), 'path':str(folder/name), 'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()}
            (folder/name).write_bytes(data)
            manifest['files'].append(record)
        with zipfile.ZipFile(folder/'gss2018_stata.zip') as archive:
            # Exact observed official member, rather than extracting arbitrary paths.
            member = archive.getinfo('GSS2018.dta')
            if member.file_size>250_000_000:
                raise ValueError('DTA exceeds size bound')
            data = archive.read(member)
            (folder/'GSS2018.dta').write_bytes(data)
            manifest['files'].append({'archive':'gss2018_stata.zip','member':member.filename,'path':str(folder/'GSS2018.dta'),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        manifest['status'] = 'completed'
    except Exception as error:
        manifest['status'] = 'failed_partial'
        manifest['error'] = str(error)
        raise
    finally:
        (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(folder)

if __name__ == '__main__':
    main()
