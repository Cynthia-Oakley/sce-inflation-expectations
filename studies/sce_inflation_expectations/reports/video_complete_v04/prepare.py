"""Freeze the author's current deck and narration; prepare slide 9 evidence."""
from pathlib import Path
import csv
import hashlib
import json
import re
import shutil
import copy
import zipfile
from lxml import etree as ET

ROOT=Path(__file__).resolve().parents[4]
BUILD=ROOT/'tmp/video_complete_v04';OUT=ROOT/'deliverables/video/v04'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())


def main():
    BUILD.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    (BUILD/'.gitignore').write_text('*\n');(OUT/'.gitignore').write_text('*\n')
    base=ROOT/'deliverables/video/v03'
    ppt=base/'SCE_video_complete_v03.pptx';script=base/'发言稿_逐页录制_v03.txt'
    snapshot=dict(pptx_sha256=sha(ppt),narration_sha256=sha(script))
    if (BUILD/'author_source.json').exists():assert read(BUILD/'author_source.json')==snapshot,'Author source changed; review it before rebuilding'
    else:(BUILD/'author_source.json').write_text(json.dumps(snapshot,indent=2))
    shutil.copy2(ppt,BUILD/'author_deck.pptx');shutil.copy2(script,BUILD/'author_narration.txt')
    b=ROOT/'deliverables/research_package/v05/package/studies/sce_inflation_expectations/reproduction_data'
    def rows(n):return list(csv.DictReader((b/n).open()))
    monthly=rows('monthly_autonomous_recursion.csv')
    contrasts=rows('downstream_contrasts.csv')
    credit=[r for r in contrasts if r['outcome']=='REVOLSL' and r['scope']=='A' and r['reference']=='official_sce' and r['candidate']=='simulated_sce']
    credit.sort(key=lambda r:int(r['horizon']))
    assert len(credit)==3
    assert [round(float(r['rmse_improvement'])*100,2) for r in credit]==[3.55,8.17,1.69]
    late=monthly[-5:]
    assert abs(sum(abs(float(r['recursive_pp'])-float(r['truth_pp'])) for r in late)/5-.5004858985701608)<1e-8
    evidence=dict(weekly=rows('weekly47_path.csv'),weekly_monthly=rows('weekly47_monthly11_primary.csv'),monthly=monthly,credit=credit,
                  population_blocks=[.5,.25,.25],new_api_calls=0,new_parameter_fits=0)
    (BUILD/'data.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    old=read(base/'storyboard.json')
    parsed=re.findall(r'第(\d)页\s+(.+?)（约(\d+)秒）\s*\n(.*?)(?=\n第\d页|\Z)',script.read_text(),flags=re.S)
    assert len(parsed)==9
    for page,title,seconds,narration in parsed:
        s=old['slides'][int(page)-1];s.update(title=title.strip(),seconds=int(seconds),narration=narration.strip())
    ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
    with zipfile.ZipFile(ppt) as z:
        source_titles={str(i):''.join(ET.fromstring(z.read(f'ppt/slides/slide{i}.xml')).xpath('//a:t/text()',namespaces=ns)[:1]) for i in range(1,10)}
    body_origins={str(i):i for i in range(1,10)}
    interactive_pages={'2':2,'4':4,'5':5}
    if '十档概率' in source_titles['4'] and '同月两户' in source_titles['5']:
        old['slides'][3],old['slides'][4]=copy.deepcopy(old['slides'][4]),copy.deepcopy(old['slides'][3])
        old['slides'][3]['page']=4;old['slides'][4]['page']=5
        body_origins.update({'4':5,'5':4});interactive_pages={'2':2,'4':5,'5':4}
    old['narration_source_pages']=body_origins;old['interactive_pages']=interactive_pages
    (BUILD/'source_slide_titles.json').write_text(json.dumps(source_titles,ensure_ascii=False,indent=2))
    s=old['slides'][-1]
    s.update(title='连续信念更新与下游指标预测',seconds=45,
      narration='最后是三个拓展。周度更新由同一批家庭沿用上周判断，新SCE公布后校准，月末原始误差约零点一五二个百分点，低于持续性基线。月度个人模拟信念连续传递，则在不再校准的情况下出现后段漂移。下游预测以循环信贷为例，也就是信用卡这类可反复借还的消费信贷。相对同结构SCE回归，提前两个月的RMSE降低约百分之八点二，其他指标尚未一致改善。完整记录随研究包提供。谢谢。',
      operation='按左半页周度、中间月度、右侧下游的顺序讲述。周度先指标题和校准标记，再指月度两条曲线的后段分离，最后用信贷柱图说明提前两个月的误差改善。本页静态放映，无逐步动画。')
    old['status']='author_source_preserved_slide9_revised';old['target_seconds']=sum(s['seconds'] for s in old['slides'])
    t=0;lines=['SCE项目视频发言稿 v04','',f'按页分段录制，计划约{old["target_seconds"]//60}分钟。标题和时长不用读。第1—8页沿用作者最新口播，第9页按三个板块微调。','']
    for s in old['slides']:
        s['start_seconds']=t;t+=s['seconds'];s['end_seconds']=t
        lines += [f'第{s["page"]}页　{s["title"]}（约{s["seconds"]}秒）','',s['narration'],'','']
    (OUT/'storyboard.json').write_text(json.dumps(old,ensure_ascii=False,indent=2))
    (OUT/'发言稿_逐页录制_v04.txt').write_text('\n'.join(lines))
    (BUILD/'source_manifest.json').write_text(json.dumps({str((b/n).relative_to(ROOT)):sha(b/n) for n in ['weekly47_path.csv','weekly47_monthly11_primary.csv','monthly_autonomous_recursion.csv','downstream_contrasts.csv']},indent=2))
    mod=BUILD/'node_modules'
    if not mod.exists():mod.symlink_to('/Users/wushuyue/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules',target_is_directory=True)
    print(json.dumps(dict(author_source=snapshot,page9_characters=len(s['narration']),planned_seconds=t,api_calls=0),ensure_ascii=False))


if __name__=='__main__':main()
