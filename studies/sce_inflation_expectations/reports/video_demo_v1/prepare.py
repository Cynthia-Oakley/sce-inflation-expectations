"""Read frozen evidence and v10; prepare a separate, non-destructive video kit."""
from pathlib import Path
import csv,json,hashlib,zipfile
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'deliverables/video/v01'; BUILD=ROOT/'tmp/video_demo_v1'
OUT.mkdir(parents=True,exist_ok=True);BUILD.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
protected=[]
for directory in ['docs/reports/final_report_draft_v10','deliverables/research_package/v05']:
 for p in sorted((ROOT/directory).rglob('*')):
  if p.is_file() and p.name!='.DS_Store':protected.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p)})
for name in ['docs/workstreams/20261027_final_delivery/overview_figure_v3/SCE_framework_editable_v3.pptx','submission/latest_package.json']:
 p=ROOT/name;protected.append({'path':name,'sha256':sha(p)})
snapshot=BUILD/'protected_before.json'
if snapshot.exists():
 assert json.loads(snapshot.read_text())==protected,'A protected source changed since this video draft began'
else:
 snapshot.write_text(json.dumps(protected,ensure_ascii=False,indent=2))
doc=ROOT/'docs/reports/final_report_draft_v10/SCE研究报告_作者审阅稿_v10.docx'
with zipfile.ZipFile(doc) as z:
 docroot=ET.fromstring(z.read('word/document.xml'))
(BUILD/'v10_author_text.txt').write_text('\n'.join(''.join(p.itertext()) for p in docroot.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p')))
e=ROOT/'deliverables/research_package/v05/package/studies/sce_inflation_expectations/reproduction_data'
def rows(name):
 with (e/name).open() as f:return list(csv.DictReader(f))
def nums(rs):
 return [{k:(float(v) if k not in ('month','step_key','cutoff','reset_required','scope','outcome','reference','candidate','evaluation','anchor_reference','anchor_published_date','truth_published_date') and v not in ('','True','False') else v) for k,v in r.items()} for r in rs]
a=nums(rows('A82_personal_T0.csv'));b=nums(rows('B11_latest_Core_and_Normal.csv'));w=nums(rows('weekly47_path.csv'));wm=nums(rows('weekly47_monthly11_primary.csv'))
A=lambda rs,key,truth='truth_pp':sum(abs(float(r[key])-float(r[truth])) for r in rs)/len(rs)
assert abs(A(a,'sim_pp')-.29840671263598517)<1e-10
assert abs(A(b,'Core_blend_pp')-.1442772448935732)<1e-10
assert abs(A(wm,'raw_pp')-.151581)<1e-6
ex=json.loads((ROOT/'outputs/sce_research_report_figures_20261024_v03/figure_data.json').read_text())
# Export only the already published anonymous illustration, excluding private lookup offsets.
example={k:ex[k] for k in ['month','q8_point_pct','q9_probabilities_ascending_pct','density_mean_pct','density_iqr_pp']}
data={'A':a,'B':b,'weekly':w,'weekly_monthly':wm,'q9_example':example,'metrics':{'A_mae':A(a,'sim_pp'),'A_baseline':A(a,'anchor_pp'),'B_raw':A(b,'Core_pp'),'B_blend':A(b,'Core_blend_pp'),'B_baseline':A(b,'baseline_pp'),'B_macro':A(b,'macro_without_sim_pp'),'weekly_raw':A(wm,'raw_pp'),'weekly_baseline':A(wm,'anchor_pp')},'credit_contrasts':rows('downstream_contrasts.csv'),'source_docx_sha256':sha(doc),'reference_pptx_sha256':sha(ROOT/'docs/workstreams/20261027_final_delivery/overview_figure_v3/SCE_framework_editable_v3.pptx')}
(BUILD/'data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
records=json.loads((Path(__file__).parent/'storyboard.json').read_text())['slides']
start=records[-1]['end_seconds']
(OUT/'storyboard.json').write_text(json.dumps({'status':'first_recording_draft','target_seconds':start,'slides':records},ensure_ascii=False,indent=2))
lines=['# 视频分镜与口播稿 v01','','以当前v10 Word与冻结结果为依据。计划4分45秒，实际以试读计时为准。第3页插入真实录屏；其他页使用PPT画面。','']
for r in records:
 fmt=lambda x:f'{x//60:02d}:{x%60:02d}'
 lines += [f"## 第{r['slide']}页　{r['title']}",f"时间：{fmt(r['start_seconds'])}—{fmt(r['end_seconds'])}，约{r['seconds']}秒。",'',f"画面：{r['visual']}",'','口播：',r['narration'],'']
(OUT/'narration.md').write_text('\n'.join(lines))
print(json.dumps({'slides':len(records),'seconds':start,'narration_characters':sum(len(r['narration']) for r in records),'protected_files':len(protected),'metrics':data['metrics']},ensure_ascii=False))
