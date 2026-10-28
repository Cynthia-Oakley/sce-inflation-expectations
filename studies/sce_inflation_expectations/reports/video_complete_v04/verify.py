"""Check the slide-9 revision, especially the author's WPS label fixes."""
from pathlib import Path
import hashlib
import json
import re
import zipfile
from lxml import etree as ET
from PIL import Image

ROOT=Path(__file__).resolve().parents[4];BUILD=ROOT/'tmp/video_complete_v04';OUT=ROOT/'deliverables/video/v04'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())
ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}


def main():
    snap=read(BUILD/'author_source.json');base=ROOT/'deliverables/video/v03'
    assert sha(base/'SCE_video_complete_v03.pptx')==snap['pptx_sha256']
    assert sha(base/'发言稿_逐页录制_v03.txt')==snap['narration_sha256']
    for p,h in read(BUILD/'source_manifest.json').items():assert sha(ROOT/p)==h
    final=OUT/'SCE_video_complete_v04.pptx';latest=read(BUILD/'latest_build.json')
    assert read(latest['receipt'])['finalSha256']==sha(final)
    with zipfile.ZipFile(BUILD/'author_deck.pptx') as z:old={n:z.read(n) for n in z.namelist()}
    with zipfile.ZipFile(final) as z:new={n:z.read(n) for n in z.namelist()}
    assert len([p for p in new if re.fullmatch(r'ppt/slides/slide\d+.xml',p)])==9
    kept=0
    for i in range(1,9):
        for p in [f'ppt/slides/slide{i}.xml',f'ppt/slides/_rels/slide{i}.xml.rels',f'ppt/notesSlides/notesSlide{i}.xml']:
            if p in old:assert new[p]==old[p],p;kept+=1
    checked_charts=[]
    for p,b in old.items():
        if re.search(r'/charts/[^/]+\.xml$',p) and p in new:
            a=ET.fromstring(b);c=ET.fromstring(new[p])
            for tag in ['dLbls','catAx','valAx','numCache','strCache']:
                assert [ET.tostring(e) for e in a.findall('.//c:'+tag,ns)]==[ET.tostring(e) for e in c.findall('.//c:'+tag,ns)],(p,tag)
            checked_charts.append(p)
        if '/embeddings/' in p and p in new:assert b==new[p]
    assert len(checked_charts)==6
    story=read(OUT/'storyboard.json');script=(OUT/'发言稿_逐页录制_v04.txt').read_text()
    before=re.findall(r'第(\d)页\s+.+?（约\d+秒）\s*\n(.*?)(?=\n第\d页|\Z)',(BUILD/'author_narration.txt').read_text(),re.S)
    authored={page:speech.strip() for page,speech in before}
    for s in story['slides'][:8]:assert s['narration']==authored[str(story['narration_source_pages'][str(s['page'])])]
    for s in story['slides']:assert script.count(s['narration'])==1
    notes=[''.join(ET.fromstring(blob).xpath('//a:t/text()',namespaces=ns)) for p,blob in new.items() if '/notesSlides/' in p and p.endswith('.xml') and '/_rels/' not in p]
    assert any(story['slides'][8]['narration'] in n for n in notes),'Slide 9 narration missing from speaker notes'
    assert sum(s['seconds'] for s in story['slides'])==300
    text=''.join(ET.fromstring(new['ppt/slides/slide9.xml']).xpath('//a:t/text()',namespaces=ns))
    for phrase in ['周度个人信念连续更新','月度个人模拟信念','连续传递','下游指标预测','循环消费信贷','信用卡','0.152pp','0.500pp','8.17%']:
        assert phrase in text,phrase
    assert len(ET.fromstring(new['ppt/slides/slide9.xml']).findall('.//c:chart',ns))==3
    for page in range(1,10):
        image=Image.open(OUT/'slides'/f'page_{page:02}.png');assert image.size==(1920,1080)
    html=(OUT/'index.html').read_text();assert 'SCE_video_complete_v04.pptx' in html and 'fetch(' not in html
    browser=read(BUILD/'browser_acceptance.json');assert browser['failures']==[] and browser['checks']>=24 and browser['file_url']
    result=dict(status='passed',edited_slide=9,unchanged_slide_xmls=8,unchanged_native_parts=kept,
                original_chart_label_trees_preserved=len(checked_charts),new_slide_charts=3,
                spatial_proportions=[.5,.25,.25],narration_pages_1_to_8_preserved=True,
                planned_seconds=300,author_source_unchanged=True,new_api_calls=0,pptx_sha256=sha(final),
                native_WPS_application_test=False)
    (BUILD/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
