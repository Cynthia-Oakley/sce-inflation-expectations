"""Prepare author-preserving P/E/B explanations and frozen-result presentation."""
from pathlib import Path
import csv
import hashlib
import json
import shutil
import zipfile
from lxml import etree as ET

ROOT=Path(__file__).resolve().parents[4];BUILD=ROOT/'tmp/video_complete_v05';OUT=ROOT/'deliverables/video/v05'
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
NS={'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}


def main():
    BUILD.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    (BUILD/'.gitignore').write_text('*\n');(OUT/'.gitignore').write_text('*\n')
    source=ROOT/'deliverables/video/v04/SCE_video_complete_v04.pptx'
    snapshot={'source':str(source.relative_to(ROOT)),'sha256':sha(source)}
    frozen=BUILD/'author_source.json'
    if frozen.exists():assert read(frozen)==snapshot,'Author changed the deck; review before rebuilding'
    else:frozen.write_text(json.dumps(snapshot,indent=2))
    shutil.copy2(source,BUILD/'author_deck.pptx')
    oldstory=read(ROOT/'deliverables/video/v04/storyboard.json')
    with zipfile.ZipFile(source) as z:
        for page in range(1,10):
            texts=ET.fromstring(z.read(f'ppt/slides/slide{page}.xml')).xpath('//a:t/text()',namespaces=NS)
            if texts:oldstory['slides'][page-1]['title']=texts[0]
            n=f'ppt/notesSlides/notesSlide{page}.xml'
            if n in z.namelist():
                note=''.join(ET.fromstring(z.read(n)).xpath('//a:t/text()',namespaces=NS))
                ends=[note.index(t) for t in ['录制操作：','来源：','计划停留：','录制：'] if t in note]
                oldstory['slides'][page-1]['narration']=note[:min(ends)].strip() if ends else note.strip()
    oldstory['slides'][2]['page']=3;oldstory['slides'][3]['page']=4
    oldstory['interactive_pages']={'2':2,'3':5,'4':4}
    oldstory['narration_source_pages']={str(i):i for i in range(1,10)}
    edits={
      5:('家庭画像从哪里来，为什么这样分组',35,'家庭画像来自纽约联储SCE调查。消费支出参考CE调查，采购角色参考ATUS，政策信心参考盖洛普，补充属性按相似特征合成匹配。我们比较126套分组，检查去掉变量后会损失多少预测信息。最终保留学历、数理、年龄和收入。稀有类别多抽一些，再用人口权重恢复原比例。'),
      6:('模拟怎样保留信念并形成答卷',25,'历史重建沿用本人既有答卷，缺失时参考近期同类。模拟预测按发布滞后规则选取调查样本，构造先验，再对齐最新公开全国水平。两条路线都由DeepSeek结合可见信息，回答点预测和十档概率，不强制改变方向或幅度。'),
      7:('生成、存档与独立评价',15,'正式生成会逐条保存输入、原始答卷和费用，再由独立程序评价。这里从研究包入口复算封存结果，现场不再调用模型。'),
      8:('全时段结果与固定组合',35,'原始模拟能够跟随总体变化，但历史重建全期误差为零点二九八个百分点，仍高于持续性基线。用前四十八个月确定组合权重后，后面三十四个月的组合误差为零点一八四，模拟预测阶段为零点一四四，均低于对应基线。微观上，模拟家庭之间的分歧仍明显不足，说明中心拟合与人群结构需要分别评价。')}
    for page,(title,seconds,narration) in edits.items():
        oldstory['slides'][page-1].update(page=page,title=title,seconds=seconds,narration=narration)
    operations={
      3:'HTML先展示十档概率，再显示个人连续分布与全国加权中位数。沿用已确认场景，不用旧PPT页码判断交互入口。',
      4:'HTML两户对照：依次点击新闻、采购角色与价格、时间边界。原场景不改。',
      5:'PPT先讲左侧四种资料来源，再指右侧移除变量后的损失增加，最后说明54类与代表权重。',
      6:'PPT先区分两条路线的历史起点，再讲统一模型与问卷。模拟预测的公开滞后规则不等于全部严格事前资格已经认证。',
      7:'展示PPT后运行原record_demo.command，复算封存全国结果与20户小例，0模型API。',
      8:'先指全时段四条曲线，再讲后34个月和预测阶段的MAE，最后说明模拟人群分歧仍窄于真人。'}
    cursor=0
    for item in oldstory['slides']:
        if item['page'] in operations:item['operation']=operations[item['page']]
        item['start_seconds']=cursor;cursor+=item['seconds'];item['end_seconds']=cursor
    oldstory['status']='author_pages_1_4_9_preserved_peb_before_demo';oldstory['recording_order']=[1,5,'environment_design',6,2,4,3,7,8,9]
    oldstory['environment_design_narration']='环境来自纽约时报新闻、BLS食品价格和联储政策。先按发布日期筛选，再依家庭主题与采购角色分配，形成因人、因时而异的信息。'
    (OUT/'storyboard.json').write_text(json.dumps(oldstory,ensure_ascii=False,indent=2))
    b=ROOT/'deliverables/research_package/v05/package/studies/sce_inflation_expectations/reproduction_data'
    def rows(n):return list(csv.DictReader((b/n).open()))
    aa=rows('A82_personal_T0.csv');bb=rows('B11_latest_Core_and_Normal.csv')
    summary_path=ROOT/'outputs/sce_full_a_t0_readout_20261026_v1/summary.json';summary=read(summary_path)
    lam=summary['official_national']['chronological_combinations']['mse']['simulation_weight']
    mae=lambda r,k:sum(abs(float(x[k])-float(x['truth_pp'])) for x in r)/len(r)
    for r in aa:r['fixed_blend_pp']=(1-lam)*float(r['anchor_pp'])+lam*float(r['sim_pp'])
    grid_path=ROOT/'outputs/sce_grid_dimensions_20261023_v1/summary.json';grid=read(grid_path)
    ci=grid['conditional_information'];assoc=grid['associations']['development']['within_month_block_gvif']
    micro=summary['same_roster']['metrics']['new']['q9']
    data=dict(A=aa,B=bb,lam=lam,grid_conditionals={k:{q:v*100 for q,v in ci[k]['development_domain_loss_increase'].items()} for k in ['numeracy','education','income','age']},
      gvif_range=[min(v['adjusted_gvif'] for v in assoc.values()),max(v['adjusted_gvif'] for v in assoc.values())],
      metrics=dict(A_raw=mae(aa,'sim_pp'),A_blend=mae(aa,'fixed_blend_pp'),A_baseline=mae(aa,'anchor_pp'),
        late_raw=mae(aa[48:],'sim_pp'),late_blend=mae(aa[48:],'fixed_blend_pp'),late_baseline=mae(aa[48:],'anchor_pp'),
        B_raw=mae(bb,'Core_pp'),B_blend=mae(bb,'Core_blend_pp'),B_baseline=mae(bb,'baseline_pp'),
        w1=micro['cross_section_w1_pp'],iqr=micro['cross_person_iqr_pp'],real_iqr=micro['real_cross_person_iqr_pp']))
    assert abs(data['metrics']['A_raw']-.29840671263598517)<1e-12
    assert abs(data['metrics']['A_blend']-.22246445671186058)<1e-12
    (BUILD/'data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    paths=[summary_path,grid_path,b/'A82_personal_T0.csv',b/'B11_latest_Core_and_Normal.csv']
    (BUILD/'source_manifest.json').write_text(json.dumps({str(p.relative_to(ROOT)):sha(p) for p in paths},indent=2))
    if not (BUILD/'node_modules').exists():(BUILD/'node_modules').symlink_to('/Users/wushuyue/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules',target_is_directory=True)
    print(json.dumps(dict(edited_pages=[5,6,7,8],protected_pages=[1,2,3,4,9],A_full_fixed_blend=data['metrics']['A_blend'],new_api_calls=0,new_parameter_fits=0),ensure_ascii=False))


if __name__=='__main__':main()
