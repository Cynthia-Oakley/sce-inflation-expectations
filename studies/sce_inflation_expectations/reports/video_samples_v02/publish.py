"""Publish a self-contained, network-free, real-record demo."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[4]
SRC=Path(__file__).parent
OUT=ROOT/'deliverables/video/samples_v02'
data=json.loads((ROOT/'tmp/video_samples_v02/data.json').read_text())
template=(SRC/'demo.html').read_text()
embedded=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/')
(OUT/'index.html').write_text(template.replace('__DATA__',embedded))
print(json.dumps(dict(html=str(OUT/'index.html'),samples=len(data['samples']),bytes=(OUT/'index.html').stat().st_size)))
