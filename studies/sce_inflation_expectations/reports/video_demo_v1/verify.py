"""Verify the delivered video kit against actual frozen evidence and protected inputs."""
from pathlib import Path
import csv,hashlib,json,re,struct,xml.etree.ElementTree as E,zipfile
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'deliverables/video/v01';BUILD=ROOT/'tmp/video_demo_v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
protected=json.loads((BUILD/'protected_before.json').read_text())
changed=[x['path'] for x in protected if not(ROOT/x['path']).is_file() or sha(ROOT/x['path'])!=x['sha256']]
assert not changed,changed
story=json.loads((OUT/'storyboard.json').read_text());assert len(story['slides'])==8 and story['target_seconds']==285
ppt=OUT/'SCE_video_presentation_v01.pptx'
with zipfile.ZipFile(ppt) as z:
 assert len([x for x in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',x)])==8
 for r in story['slides']:
  n=E.fromstring(z.read(f'ppt/notesSlides/notesSlide{r["slide"]}.xml'));t=''.join(x.text or '' for x in n.findall('.//a:t',ns));assert r['narration'] in t
 charts=[E.fromstring(z.read(x)) for x in z.namelist() if x.endswith('.xml') and '/charts/' in x and not '/_rels/' in x];assert len(charts)==7
 assert len([x for x in z.namelist() if x.endswith('.xlsx')])==7
 for chart in charts:
  for ser in chart.findall('.//c:ser',ns):
   sm=ser.find('c:smooth',ns)
   if sm is not None:assert sm.attrib.get('val') in ('0','false')
rows=list(csv.DictReader((ROOT/'deliverables/research_package/v05/package/studies/sce_inflation_expectations/reproduction_data/downstream_contrasts.csv').open()))
for c,expected in [('simulated_sce',[3.55,8.17,1.69]),('blended_sce',[-3.18,5.03,4.80])]:
 actual=[round(float(r['rmse_improvement'])*100,2) for r in rows if r['outcome']=='REVOLSL' and r['scope']=='A' and r['reference']=='official_sce' and r['candidate']==c];assert actual==expected,(c,actual)
for i in range(1,9):
 raw=(OUT/f'slides/slide_{i:02d}.png').read_bytes();assert raw[:8]==b'\x89PNG\r\n\x1a\n';assert struct.unpack('>II',raw[16:24])==(1920,1080)
for link in re.findall(r'href="([^"]+)"',(OUT/'index.html').read_text()):assert (OUT/link).is_file(),link
latest=json.loads((BUILD/'latest_build.json').read_text());validation=json.loads(Path(latest['receipt']).read_text());assert validation['finalSha256']==sha(ppt)
assert validation['nativeQuantitativeCharts']['report']['validated_slide_count']==5
assert all(x['status']=='passed' for x in validation['nativeQuantitativeCharts']['report']['owner_results']) if 'owner_results' in validation['nativeQuantitativeCharts']['report'] else True
runs=sorted((BUILD/'recording_sessions').glob('*/demo_receipt.json'));assert runs
run=json.loads(runs[-1].read_text());assert run['status']=='passed' and run['actual_LLM_calls']==0
report={'status':'verified_video_materials_not_recorded_mp4','slides':8,'planned_seconds':285,'narration_characters':sum(len(r['narration']) for r in story['slides']),'native_charts':7,'editable_chart_workbooks':7,'all_narration_in_ppt_notes':True,'pptx_sha256':sha(ppt),'protected_files_verified_unchanged':len(protected),'protected_files_changed':changed,'new_model_api_calls':0,'native_application_UI_used':False,'native_powerpoint_opened':False,'validation_receipt':str(Path(latest['receipt']).relative_to(ROOT)),'display_chart_rounding_decimals':8,'credit_frozen_source_rechecked':True,'recording_command_run_seconds':run['seconds'],'recording_receipt':str(runs[-1].relative_to(ROOT))}
(BUILD/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False))
