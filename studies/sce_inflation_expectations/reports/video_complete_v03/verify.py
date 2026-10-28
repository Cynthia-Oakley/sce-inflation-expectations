"""Check the final recording deck and its separate narration; no model calls."""
from pathlib import Path
import hashlib
import json
import re
import zipfile
from lxml import etree as ET
from PIL import Image
from preserve_sample_charts import chart_parts, relpart, resolve

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'deliverables/video/v03';BUILD=ROOT/'tmp/video_complete_v03'
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
    'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
    'c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}


def main():
    story=read(OUT/'storyboard.json');d=read(BUILD/'data.json')
    script=(OUT/'发言稿_逐页录制_v03.txt').read_text()
    assert len(story['slides'])==9 and sum(s['seconds'] for s in story['slides'])==285
    for s in story['slides']:assert script.count(s['narration'])==1
    source=read(BUILD/'source_manifest.json')
    for p,h in source['source_sha256'].items():assert sha(ROOT/p)==h,p
    for p in read(BUILD/'protected_at_integration.json'):assert sha(ROOT/p['path'])==p['sha256'],p['path']
    assert source['new_api_calls']==source['new_q9_fits']==source['new_parameters']==0
    assert d['sampling']['small']['frame_n']==d['sampling']['small']['n']==3
    assert (d['sampling']['large']['frame_n'],d['sampling']['large']['n'])==(110,19)
    for g in ['small','large']:assert abs(d['sampling'][g]['target']-d['sampling'][g]['corrected'])<1e-10
    assert len(d['A'])==82 and len(d['B'])==11 and len(d['weekly'])==47
    ppt=OUT/'SCE_video_complete_v03.pptx'
    with zipfile.ZipFile(ppt) as z:files={n:z.read(n) for n in z.namelist()}
    slides=[n for n in files if re.fullmatch(r'ppt/slides/slide\d+.xml',n)]
    assert len(slides)==9
    used_charts=[];alltext=''
    for page in range(1,10):
        tree=ET.fromstring(files[f'ppt/slides/slide{page}.xml'])
        text=''.join(tree.xpath('//a:t/text()',namespaces=ns));alltext+=text
        notes=ET.fromstring(files[f'ppt/notesSlides/notesSlide{page}.xml'])
        assert story['slides'][page-1]['narration'] in ''.join(notes.xpath('//a:t/text()',namespaces=ns)),page
        used_charts+=chart_parts(files,page)
        if page>1:
            families=set(tree.xpath('//a:latin/@typeface|//a:ea/@typeface',namespaces=ns))
            assert 'Kaiti SC' in families and 'Times New Roman' in families,(page,families)
        image=Image.open(OUT/'slides'/f'page_{page:02}.png')
        assert image.size==(1920,1080) and (OUT/'slides'/f'page_{page:02}.png').stat().st_size>20000
    assert len(set(used_charts))==7
    with zipfile.ZipFile(BUILD/'source_for_import.pptx') as z:old={n:z.read(n) for n in z.namelist()}
    with zipfile.ZipFile(BUILD/'source_charts_approved.pptx') as z:chartsource={n:z.read(n) for n in z.namelist()}
    preserved=0
    for srcpage,dstpage in [(1,2),(2,4),(3,5)]:
        # Native text is preserved despite the application's serialization.
        src=ET.fromstring(old[f'ppt/slides/slide{srcpage}.xml'])
        dst=ET.fromstring(files[f'ppt/slides/slide{dstpage}.xml'])
        assert src.xpath('//a:t/text()',namespaces=ns)==dst.xpath('//a:t/text()',namespaces=ns)
        for a,b in zip(chart_parts(chartsource,srcpage),chart_parts(files,dstpage)):
            assert chartsource[a]==files[b],(a,b)
            ra=ET.fromstring(chartsource[relpart(a)]);rb=ET.fromstring(files[relpart(b)])
            wa=[chartsource[resolve(a,r.attrib['Target'])] for r in ra]
            wb=[files[resolve(b,r.attrib['Target'])] for r in rb]
            assert wa==wb,(a,b)
            preserved+=1
    assert preserved==4
    assert all(t in alltext for t in ['41,970','0.298','0.184','0.144','0.152','8.17%','3.2%'])
    # The author's method figure remains the exact source image.
    imagehash=sha(ROOT/'docs/workstreams/20261027_final_delivery/overview_figure_v3/sce_framework_author_v3.png')
    assert any(hashlib.sha256(b).hexdigest()==imagehash for n,b in files.items() if n.startswith('ppt/media/'))
    receipt=read(read(BUILD/'latest_build.json')['receipt'])
    assert receipt['finalSha256']==sha(ppt)
    html=(OUT/'index.html').read_text()
    assert '__STORY__' not in html and 'fetch(' not in html and '<script src=' not in html
    assert not re.search(r'\bsce_[0-9a-f]{16}\b',html)
    for name in ['SCE_video_complete_v03.pptx','发言稿_逐页录制_v03.txt','录制操作单_v03.md']:
        assert name in html and (OUT/name).is_file()
    assert (OUT/'../samples_v02/index.html').resolve().is_file()
    browser=read(BUILD/'browser_acceptance.json')
    assert browser['failures']==[] and browser['checked_pages']==9
    result=dict(status='passed',slides=9,native_editable_charts=7,
                preserved_original_charts_and_workbooks=preserved,
                protected_files_unchanged=len(read(BUILD/'protected_at_integration.json')),
                narration_characters=sum(len(s['narration']) for s in story['slides']),
                planned_seconds=285,new_api_calls=0,new_research_parameters=0,
                native_desktop_PowerPoint_test=False,pptx_sha256=sha(ppt))
    (BUILD/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
