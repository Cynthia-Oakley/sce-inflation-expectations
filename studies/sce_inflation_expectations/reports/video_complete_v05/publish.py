"""Publish P/E/B-first recording instructions; existing demo scenes stay intact."""
from pathlib import Path
import hashlib,json,re,shutil,subprocess

ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'deliverables/video/v05';BASE=ROOT/'deliverables/video/v04';SRC=Path(__file__).parent


def main():
    story=json.loads((OUT/'storyboard.json').read_text());data=json.dumps(story,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    page=(BASE/'index.html').read_text().replace('v04','v05')
    page=page.replace('../samples_v02/index.html','real_samples.html')
    page=page.replace('发言稿_逐页录制_v05.txt','发言稿_录制顺序_v05.txt')
    page=page.replace('[2,4,5].includes(s.page)','Boolean(data.interactive_pages[String(s.page)])')
    page=re.sub(r'(<script type="application/json" id="story">).*?(</script>)',lambda m:m.group(1)+data+m.group(2),page,flags=re.S)
    page=page.replace('<button id="present">','<a href="environment.html">环境设计与来源</a><button id="present">')
    page=page.replace('第1—8页沿用作者手改版，当前尚未导出视频。','第1—4和第9页保留作者手改。建议录制：1 → 5（P）→ 环境HTML（E）→ 6（作答）→ 2／4／3（真实演示）→ 7 → 8 → 9。')
    page=page.replace('SCE · 完整9页录制稿 v05','SCE · 设计、真实运行与结果 v05')
    page=page.replace('已确认的第2、4、5页保留真实样本与原生图表','第2、3、4页使用已确认的真实样本交互')
    (OUT/'index.html').write_text(page)
    shutil.copy2(SRC/'environment.html',OUT/'environment.html')
    real=ROOT/'deliverables/video/samples_v02/index.html';shutil.copy2(real,OUT/'real_samples.html')
    assert hashlib.sha256(real.read_bytes()).digest()==hashlib.sha256((OUT/'real_samples.html').read_bytes()).digest()
    steps=[
      ('page_01.mp4',1,'方法概览，已有第1段',24),
      ('page_05.mp4',5,'P：资料来源、分组依据与抽样',35),
      ('environment_design.mp4','environment_design','E：环境信息的来源与匹配',15),
      ('page_06.mp4',6,'模型如何结合先验与环境作答',25),
      ('page_02_trimmed_38.5s.mp4',2,'真实输入与回复，已有38.5秒片段',38.5),
      ('page_04.mp4',4,'HTML两户信息对照',30),
      ('page_03.mp4',3,'HTML概率计分与全国指标',30),
      ('page_07.mp4',7,'执行与封存结果复算',15),
      ('page_08.mp4',8,'全时段曲线、基线与指标表',35),
      ('page_09.mp4',9,'连续更新与下游用途',45)]
    lines=['SCE视频发言稿 v05：按讲解与拼接顺序','',
      'PPT页序保留作者当前版本。录制先讲设计，再展示真实模拟；现有第1段和38.5秒第2段不重录。尚未录制部分的时间为建议值，成片时再统一控制。','']
    ops=['# 录制顺序与操作 v05','','PPT第1—4页和第9页未改。第5—8页补来源、依据、作答与结果。PPT页码不重新排列，视频拼接顺序如下。先设计再实例，避免评委第一次看到Prompt时还不了解输入从何而来。','']
    plan=[]
    for i,(file,key,title,sec) in enumerate(steps,1):
        speech=story['environment_design_narration'] if key=='environment_design' else story['slides'][key-1]['narration']
        location='environment.html的“纯画面录制”' if key=='environment_design' else ('real_samples.html#page='+str(story['interactive_pages'][str(key)])+'&sample=A01' if str(key) in story['interactive_pages'] else f'PPT第{key}页')
        lines += [f'第{i}段　{title}（建议{sec}秒）',f'文件：{file}　画面：{location}','',speech,'','']
        ops += [f'## 第{i}段　{title}','',f'建议文件：`{file}`；画面：{location}。','']
        if file.startswith('page_01') or '38.5s' in file:ops+=['已有片段，保留并在最终拼接时放到此位置。','']
        elif key==7:ops+=['展示本页后运行原record_demo.command，只复算封存结果与工程小例，0模型API。结果页与收据一闪即可，不等待重新生成。','']
        elif key==8:ops+=['先指四条曲线，再指MAE表，最后指出模拟家庭的IQR窄于真人。全期组合包含前48月拟权期，后34月另列检查。','']
        elif key=='environment_design':ops+=['打开环境设计页，点“纯画面录制”。简述新闻、食品价格与政策三种资料，最后指时间规则，暂不进入两户实例。','']
        plan.append(dict(order=i,file=file,source_page=key,title=title,seconds_suggested=sec,status='already_recorded' if i in [1,5] else 'not_yet_received'))
    (OUT/'发言稿_录制顺序_v05.txt').write_text('\n'.join(lines))
    ops+=['## 拼接与文件保护','','原始片段继续放在`deliverables/video/recordings/clips/`。第2段采用作者保存的`page_02_trimmed_38.5s.mp4`，不再用已移除的38秒剪辑版。最终按上述内容顺序拼接，不按文件名排序。','',
      '第1—4页和第9页的原生文字、布局与备注保留。网页源文件另存，不覆盖已录制的交互版本；讲稿中沿用作者在PPT备注中的最新表达。研究包、论文和正式模拟结果均不改。']
    (OUT/'录制操作单_v05.md').write_text('\n'.join(ops))
    (OUT/'recording_order.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
    (OUT/'README.md').write_text('''# 视频讲解材料 v05

- [PPT逐页预览](index.html)
- [环境来源与匹配设计](environment.html)
- [既有真实样本交互的原字节副本](real_samples.html)
- [完整PPT](SCE_video_complete_v05.pptx)
- [按最终录制顺序排列的发言稿](发言稿_录制顺序_v05.txt)
- [操作与拼接顺序](录制操作单_v05.md)

本版基于作者13:45手改v04，保护第1—4页与第9页，仅重做第5—8页。第5页补SCE/CE/ATUS/Gallup资料来源与条件信息比较；第6页区分历史重建/模拟预测的先验，再说明同一作答程序；第7页突出生成、存档与独立评价；第8页补完整固定组合曲线、持续性基线、全国MAE表和历史微观W1/IQR表。

组合沿用前48月已冻结权重，不重新拟合；全期组合含拟权期，后34月检查单列。主图维持每月约512份直接模型答卷的加权口径；人口扩展结果仍另列于报告与研究包。全国线性组合没有个人微观分布，不虚构组合的W1/IQR；模拟预测没有真人微观结构，亦不报告微观误差。

PPT物理顺序不变，视频先介绍方法、P、E和作答设计，再播放既有真实输入、信息对照、概率计分片段。原38.5秒第2段保留，在后期拼接中后移，不要求重录。环境设计为独立HTML录制场景，原三张交互场景保持原字节。

原v04、作者备注、论文、研究包与录屏均保留，0新模型调用、0新研究拟合。源代码在study的reports/video_complete_v05/；私人快照和验收在tmp/video_complete_v05/。不自动将真实问卷条件节选和录屏上传Git。
''')
    # Register the author's revised clip as the selected source, without editing it.
    rec=ROOT/'deliverables/video/recordings';media=rec/'media_manifest.json';clip=rec/'clips/page_02_trimmed_38.5s.mp4'
    if clip.exists():
        m=json.loads(media.read_text());m.setdefault('assembly_selection',{})['2']='clips/page_02_trimmed_38.5s.mp4'
        m['assembly_order_plan']=[x['file'] for x in plan]
        m['author_page_02_revision']={'file':'clips/page_02_trimmed_38.5s.mp4','sha256':hashlib.sha256(clip.read_bytes()).hexdigest(),'duration_seconds':38.502438,'selected_by_author':True}
        media.write_text(json.dumps(m,ensure_ascii=False,indent=2))
    print(json.dumps(dict(preview=str(OUT/'index.html'),recording_scenes=len(plan),seconds_suggested=sum(s['seconds_suggested'] for s in plan),new_api_calls=0),ensure_ascii=False))


if __name__=='__main__':main()
