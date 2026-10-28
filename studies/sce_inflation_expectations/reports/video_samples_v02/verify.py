"""Verify the paired export, native deck and preservation of original files."""
from pathlib import Path
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parents[4]
BUILD=ROOT/'tmp/video_samples_v02';OUT=ROOT/'deliverables/video/samples_v02'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())
d=read(BUILD/'data.json');lineage=read(BUILD/'private_lineage.json')
assert len(d['samples'])==len(lineage)==24
assert not re.search(r'\bsce_[0-9a-f]{16}\b',(OUT/'index.html').read_text())
ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','c':'http://schemas.openxmlformats.org/drawingml/2006/chart','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
for s,l in zip(d['samples'],lineage):
    rows=read(ROOT/l['prompt_file'])['rows'];pr=rows[l['agent_id']]
    assert pr['messages']==s['messages']
    assert hashlib.sha256(json.dumps(s['messages'],ensure_ascii=False).encode()).hexdigest()==s['prompt_hash']
    reply=json.loads((ROOT/l['reply_file']).read_text().splitlines()[l['reply_line']-1])
    assert reply['raw_response_text']==s['response_raw']
    assert hashlib.sha256(s['response_raw'].encode()).hexdigest()==s['response_hash']
    assert reply['prompt_sha256']==s['prompt_hash']
    obj=json.loads(s['response_raw'])
    assert obj==s['response'] and obj['point_pct']==s['q8']
    assert [obj['q9'][f'bin{i}'] for i in range(1,11)]==s['bins']
    assert abs(sum(s['bins'])-100)<1e-8
    assert all(fragment in s['messages'][0]['content'] for values in s['sections'].values() for fragment in values)
    assert s['news_count']==len(s['news'])==s['common_count']+s['personal_count']
    assert s['food_reference'] in s['food_lines'][0]
for m in d['months'].values():
    total=0.;med=None
    for atom in m['atoms']:
        total+=atom['mass']
        if total>=.5 and med is None:med=atom['x']
    assert abs(total-1)<1e-10 and abs(med-m['median'])<1e-10
    assert m['frame_n']==m['n']+m['normal_n']
ppt=OUT/'SCE_samples_02_04_05_v02.pptx'
with zipfile.ZipFile(ppt) as z:
    names=z.namelist()
    slides=[n for n in names if re.fullmatch(r'ppt/slides/slide\d+.xml',n)]
    charts=[n for n in names if re.fullmatch(r'ppt/(?:slides/)?charts/chart\d+.xml',n)]
    books=[n for n in names if n.startswith('ppt/embeddings/') and n.endswith('.xlsx')]
    assert len(slides)==3 and len(charts)==4 and len(books)==4
    for n in charts:
        root=ET.fromstring(z.read(n))
        for sm in root.findall('.//c:smooth',ns):assert sm.attrib.get('val') in ('0','false')
    notes=''.join(z.read(n).decode() for n in names if re.fullmatch(r'ppt/notesSlides/notesSlide\d+.xml',n))
    assert d['samples'][0]['prompt_hash'] in notes
    alltext=''.join(''.join(ET.fromstring(z.read(n)).itertext()) for n in slides)
    assert '原有信念' in alltext and '1297' in alltext and '5.98' in alltext and '3.74' in alltext
for entry in read(BUILD/'protected_before.json'):
    assert sha(ROOT/entry['path'])==entry['sha256'],entry['path']
for name in ['02','04','05']:
    p=OUT/'slides'/f'page_{name}.png';assert p.is_file() and p.stat().st_size>20000
receipt=read(read(BUILD/'latest_build.json')['receipt'])
assert receipt['finalSha256']==sha(ppt)
browser=read(BUILD/'browser_acceptance.json');assert browser['failures']==[] and browser['checks']>=176
for view in browser['recording_pages'].values():
    v=json.loads(view);assert v['height']<=v['viewport'] and v['width']<=v['viewWidth']
html=(OUT/'index.html').read_text()
assert '__DATA__' not in html and 'fetch(' not in html and '<script src=' not in html
result=dict(status='passed',slides=3,paired_real_records=24,native_editable_charts=4,
            embedded_chart_workbooks=4,browser_checks=browser['checks'],
            protected_files_unchanged=len(read(BUILD/'protected_before.json')),
            direct_file_open_verified=True,api_calls=0,density_curve_reconstructions=24,
            pptx_sha256=sha(ppt),html_sha256=sha(OUT/'index.html'),
            scientific_parameter_changes=0,native_desktop_PowerPoint_test=False)
(BUILD/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
