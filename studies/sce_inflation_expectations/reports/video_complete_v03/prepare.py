"""Assemble frozen evidence for the six remaining video slides. Zero API."""
from collections import defaultdict
from pathlib import Path
import csv
import hashlib
import json
import shutil
import re
import zipfile
from lxml import etree as ET

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'deliverables/video/v03'
BUILD=ROOT/'tmp/video_complete_v03'
SRC=Path(__file__).parent
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True,exist_ok=True);BUILD.mkdir(parents=True,exist_ok=True)
    (OUT/'.gitignore').write_text('*\n');(BUILD/'.gitignore').write_text('*\n')
    protected=[]
    for folder in ['deliverables/video/v01','deliverables/video/samples_v02','docs/reports/final_report_draft_v10',
                   'deliverables/research_package/v05','docs/workstreams/20261027_final_delivery/overview_figure_v3']:
        for p in sorted((ROOT/folder).rglob('*')):
            if p.is_file() and p.name!='.DS_Store' and not p.name.startswith('.~'):
                protected.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p)))
    snap=BUILD/'protected_before.json'
    if snap.exists():
        before={r['path']:r['sha256'] for r in read(snap)}
        changes=[r for r in protected if before.get(r['path'])!=r['sha256']]
        # WPS resaved the open source sample during this task. Preserve that
        # author-owned file; only adapt the private import copy below.
        assert all(r['path']=='deliverables/video/samples_v02/SCE_samples_02_04_05_v02.pptx' for r in changes),changes
        if changes:
            (BUILD/'external_source_save_observed.json').write_text(json.dumps(dict(before=before[changes[0]['path']],after=changes[0],source_app='WPS',source_not_overwritten=True),ensure_ascii=False,indent=2))
    else:snap.write_text(json.dumps(protected,ensure_ascii=False,indent=2))
    (BUILD/'protected_at_integration.json').write_text(json.dumps(protected,ensure_ascii=False,indent=2))
    sample=read(ROOT/'tmp/video_samples_v02/data.json')
    source=ROOT/'deliverables/video/samples_v02/SCE_samples_02_04_05_v02.pptx'
    shutil.copy2(source,BUILD/'source_at_integration.pptx')
    approved=ROOT/'tmp/video_samples_v02/validated/samples_20261028003609407.pptx'
    assert sha(approved)=='ea3109b50e334c8904d1d353bf2ce34088a7b8de1dc0f9b0b651830a5c947e3d'
    shutil.copy2(approved,BUILD/'source_charts_approved.pptx')
    repairs=[]
    with zipfile.ZipFile(source) as z,zipfile.ZipFile(BUILD/'source_for_import.pptx','w',zipfile.ZIP_DEFLATED) as out:
        for name in z.namelist():
            blob=z.read(name)
            # A WPS one-series column chart writes the nonstandard grouping
            # enum 'none'. 'clustered' is the equivalent valid OOXML value.
            if name.startswith('ppt/charts/chart') and name.endswith('.xml'):
                blob,n=re.subn(rb'(<c:grouping\s+val=")none("\s*/>)',rb'\g<1>clustered\2',blob)
                if n:repairs.append(dict(part=name,invalid_value='none',equivalent_valid_value='clustered'))
                ns={'c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
                tree=ET.fromstring(blob);fixed=0
                for series in tree.findall('.//c:ser',ns):
                    title=series.find('c:tx/c:strRef/c:f',ns)
                    values=series.find('c:val/c:numRef/c:f',ns)
                    if values is None:values=series.find('c:yVal/c:numRef/c:f',ns)
                    if title is not None and '!' not in title.text and values is not None:
                        # WPS replaced a series-name cell formula with its
                        # literal value. Link back to the existing Y-column
                        # header in the original, unchanged workbook.
                        formula=values.text.split(':')[0]
                        title.text=re.sub(r'\$?\d+$','$1',formula)
                        fixed+=1
                if fixed:
                    blob=ET.tostring(tree,encoding='UTF-8',xml_declaration=True,standalone=True)
                    repairs.append(dict(part=name,series_title_formulas_restored_from_original_value_column=fixed))
            out.writestr(name,blob)
    (BUILD/'source_import_compatibility.json').write_text(json.dumps(dict(source_sha256=sha(source),repairs=repairs,source_overwritten=False),indent=2))
    folder=ROOT/'deliverables/research_package/v05/package/studies/sce_inflation_expectations/reproduction_data'
    def rows(name):return list(csv.DictReader((folder/name).open()))
    aa=rows('A82_personal_T0.csv');bb=rows('B11_latest_Core_and_Normal.csv')
    weekly=rows('weekly47_path.csv');wm=rows('weekly47_monthly11_primary.csv')
    ar=read(ROOT/'outputs/sce_full_a_t0_readout_20261026_v1/summary.json')
    combo=ar['official_national']['chronological_combinations']['mse'];lam=combo['simulation_weight']
    mae=lambda rr,key:sum(abs(float(r[key])-float(r['truth_pp'])) for r in rr)/len(rr)
    assert abs(mae(aa,'sim_pp')-.29840671263598517)<1e-12
    assert abs(mae(bb,'Core_blend_pp')-.1442772448935732)<1e-12
    assert abs(mae(wm,'raw_pp')-.151580640914989)<1e-8
    weights_path=ROOT/'outputs/sce_full_a_personal_inputs_20261025_v1/202106/weights_private.json'
    ww=read(weights_path);groups=defaultdict(list)
    for row in ww.values():groups[row['stratum']].append(row)
    fullmass=sum(v[0]['cell_original_mass'] for v in groups.values())
    rawmass=sum(v['raw_survey_weight'] for v in ww.values())
    calibrationmass=sum(v['poststratified_weight'] for v in ww.values())
    cells=[]
    for name,group in groups.items():
        n=len(group);frame_n=round(n/group[0]['inclusion_probability'])
        target=group[0]['cell_original_mass']/fullmass*100
        after=sum(v['poststratified_weight'] for v in group)/calibrationmass*100
        assert abs(target-after)<1e-10
        cells.append(dict(cell=name,frame_n=frame_n,n=n,target=target,corrected=after,
                          original_sample_weight_share=sum(v['raw_survey_weight'] for v in group)/rawmass*100))
    small=next(c for c in sorted(cells,key=lambda c:c['cell']) if c['frame_n']==3)
    large=max(cells,key=lambda c:c['frame_n'])
    bplan_path=ROOT/'outputs/sce_recent_b_rolling_preflight_20261025_v1/monthly_input_plan.json'
    bplan=read(bplan_path)[0]
    prior_diag_path=ROOT/'outputs/sce_recent_b_rolling_priors_20261025_v1/monthly_prior_diagnostics.json'
    prior_diag=read(prior_diag_path)
    data=dict(sample=sample['samples'][0],sampling=dict(month='202106',frame_n=sum(c['frame_n'] for c in cells),
              core_n=len(ww),represented_groups=len(cells),small=small,large=large),
              A=aa,B=bb,weekly=weekly,weekly_monthly=wm,combination=combo,
              metrics=dict(A_raw=mae(aa,'sim_pp'),A_anchor=mae(aa,'anchor_pp'),
                           B_raw=mae(bb,'Core_pp'),B_blend=mae(bb,'Core_blend_pp'),B_anchor=mae(bb,'baseline_pp'),
                           weekly_raw=mae(wm,'raw_pp'),weekly_anchor=mae(wm,'anchor_pp')),
              b_example=dict(month=bplan['month'],source_month=bplan['old_population_reference_period'],
                             cutoff=bplan['as_of'],anchor=bplan['last_public_national_anchor'],
                             micro_vintage_verified=bplan['historical_byte_vintage_verified']),
              archived_runs=read(ROOT/'deliverables/video/v01/archived_run_evidence.json'))
    assert data['sampling']['frame_n']==1297 and data['sampling']['core_n']==512
    (BUILD/'data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    sources=[folder/n for n in ['A82_personal_T0.csv','B11_latest_Core_and_Normal.csv','weekly47_path.csv','weekly47_monthly11_primary.csv']]
    sources += [weights_path,bplan_path,prior_diag_path,ROOT/'outputs/sce_full_a_t0_readout_20261026_v1/summary.json',approved,
                ROOT/'deliverables/video/samples_v02/SCE_samples_02_04_05_v02.pptx',ROOT/'tmp/video_samples_v02/data.json']
    (BUILD/'source_manifest.json').write_text(json.dumps(dict(source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},
                                              new_api_calls=0,new_q9_fits=0,new_parameters=0),ensure_ascii=False,indent=2))
    if not (BUILD/'node_modules').exists():
        (BUILD/'node_modules').symlink_to('/Users/wushuyue/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules',target_is_directory=True)
    story=read(SRC/'storyboard.json')
    assert len(story['slides'])==9 and sum(s['seconds'] for s in story['slides'])==285
    t=0;lines=['SCE项目视频发言稿 v03','', '按页分段录制，总计划4分45秒。每页只需朗读下方正文，标题和时长不用读。','']
    for s in story['slides']:
        s['start_seconds']=t;t+=s['seconds'];s['end_seconds']=t
        lines.extend([f"第{s['page']}页　{s['title']}（约{s['seconds']}秒）",'',s['narration'],'',''])
    (OUT/'发言稿_逐页录制_v03.txt').write_text('\n'.join(lines))
    (OUT/'storyboard.json').write_text(json.dumps(story,ensure_ascii=False,indent=2))
    print(json.dumps(dict(protected=len(protected),pages=9,seconds=t,narration_characters=sum(len(s['narration']) for s in story['slides']),sampling=data['sampling']),ensure_ascii=False))


if __name__=='__main__':main()
