"""Validate frozen scientific values and author-slide/media preservation."""
from pathlib import Path
import hashlib
import json
import posixpath
import zipfile
from lxml import etree as ET

ROOT=Path(__file__).resolve().parents[4]
BUILD=ROOT/'tmp/video_complete_v05'
OUT=ROOT/'deliverables/video/v05'
NS={'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
    'c':'http://schemas.openxmlformats.org/drawingml/2006/chart',
    'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())


def main():
    checks=[]
    def check(v,label):
        assert v,label
        checks.append(label)
    frozen=read(BUILD/'author_source.json')
    check(sha(ROOT/frozen['source'])==frozen['sha256'],'author source unchanged')
    latest=read(BUILD/'latest_build.json');receipt=read(latest['receipt'])
    check(sha(OUT/'SCE_video_complete_v05.pptx')==receipt['finalSha256'],'finalizer matches delivery')
    check(receipt['packageIntegrity']['status']=='pass','native package integrity')
    check(receipt['presentationLayout']['finding_count']==0,'native layout geometry')
    check(not receipt['presentationLayout']['warnings'],'no unresolved layout warnings')
    check(receipt['nativeChartValidation']['passed'],'native charts and embedded workbooks')
    with zipfile.ZipFile(ROOT/frozen['source']) as old,zipfile.ZipFile(OUT/'SCE_video_complete_v05.pptx') as new:
        for page in [1,2,3,4,9]:
            for name in [f'ppt/slides/slide{page}.xml',f'ppt/slides/_rels/slide{page}.xml.rels',f'ppt/notesSlides/notesSlide{page}.xml']:
                check(old.read(name)==new.read(name),f'preserved {name}')
        # Data labels, numeric/string caches and chart workbook bytes remain author's.
        for name in old.namelist():
            if '/charts/' not in name or not name.endswith('.xml') or name not in new.namelist():continue
            a=ET.fromstring(old.read(name));b=ET.fromstring(new.read(name))
            for expr in ['//c:dLbls','//c:numCache','//c:strCache','//c:numLit','//c:strLit']:
                check([ET.tostring(x) for x in a.xpath(expr,namespaces=NS)]==[ET.tostring(x) for x in b.xpath(expr,namespaces=NS)],f'chart labels/cache {name} {expr}')
        for name in old.namelist():
            if name.endswith('.xlsx') and name in new.namelist():check(old.read(name)==new.read(name),'author workbook '+name)
        slide=ET.fromstring(new.read('ppt/slides/slide8.xml'))
        check(len(slide.xpath('//a:tbl',namespaces=NS))==2,'editable MAE and micro tables')
        rels=ET.fromstring(new.read('ppt/slides/_rels/slide8.xml.rels'))
        chart_targets=[r.attrib['Target'] for r in rels if r.attrib['Type'].endswith('/chart')]
        chart_name=posixpath.normpath(posixpath.join('ppt/slides',chart_targets[0]))
        chart=ET.fromstring(new.read(chart_name))
        lengths=[len(s.xpath('.//c:yVal//c:pt',namespaces=NS)) for s in chart.xpath('//c:ser',namespaces=NS)]
        check(lengths==[93,93,93,93,2],'truth raw blend baseline all span 93 months')
    data=read(BUILD/'data.json');story=read(OUT/'storyboard.json')
    for p,h in read(BUILD/'source_manifest.json').items():check(sha(ROOT/p)==h,'frozen source '+p)
    check(len(data['A'])==82 and len(data['B'])==11,'82 historical and 11 simulated months')
    for row in data['A']:
        expected=(1-data['lam'])*float(row['anchor_pp'])+data['lam']*float(row['sim_pp'])
        assert abs(expected-row['fixed_blend_pp'])<1e-12
    check(abs(data['metrics']['A_blend']-.22246445671186058)<1e-12,'full historical frozen blend without refit')
    check(abs(data['metrics']['late_blend']-.1841250067081133)<1e-12,'later34 fixed-weight check')
    check(sha(OUT/'real_samples.html')==sha(ROOT/'deliverables/video/samples_v02/index.html'),'real demo bytes unchanged')
    check(story['recording_order']==[1,5,'environment_design',6,2,4,3,7,8,9],'P E behavior precede true-run example')
    media=read(ROOT/'deliverables/video/recordings/media_manifest.json')
    clip=ROOT/'deliverables/video/recordings'/media['assembly_selection']['2']
    check(clip.name=='page_02_trimmed_38.5s.mp4','author38.5s clip selected')
    check(sha(clip)==media['author_page_02_revision']['sha256'],'author recording unchanged')
    browser=read(BUILD/'browser_acceptance.json')
    check(not browser['failures'] and browser['checks']>=25,'browser routes and two recording sizes')
    report=dict(status='passed',checks=len(checks),passed=checks,failures=[],
        visual_review_pages=[5,6,7,8],native_WPS_open_test=False,new_model_calls=0,new_parameter_fits=0)
    (BUILD/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='passed'},ensure_ascii=False))


if __name__=='__main__':main()
