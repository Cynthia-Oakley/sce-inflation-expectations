"""Publish the local video kit preview without changing the paper or study package."""
from pathlib import Path
import html,json
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'deliverables/video/v01'
story=json.loads((OUT/'storyboard.json').read_text())
buttons=''.join(f'<button type="button" onclick="show({i})">{r["slide"]:02d}　{html.escape(r["title"])}</button>' for i,r in enumerate(story['slides']))
content='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SCE视频录制材料 v01</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f5f6;color:#203447;font:16px/1.7 system-ui,"PingFang SC",sans-serif}main{max-width:1640px;margin:auto;padding:24px}h1{margin:0;font-size:26px}p{margin:8px 0 16px}nav{display:flex;flex-wrap:wrap;gap:18px;margin:18px 0}a{color:#245d7d;text-underline-offset:4px}.controls{display:flex;gap:12px;align-items:center;margin:16px 0}button{background:white;border:1px solid #cbd6de;padding:8px 13px;border-radius:3px;color:#203447;cursor:pointer;font:inherit}.layout{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:24px;align-items:start}#stage{background:white;line-height:0;border:1px solid #d5dfe5}#stage img{width:100%;height:auto;display:block}aside{background:white;padding:22px;border-top:3px solid #245d7d}aside h2{font-size:20px;margin:0 0 8px}#speech{white-space:pre-line;font-size:18px;line-height:1.9}.muted{color:#697782}.list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:24px}.list button{text-align:left}#stage:fullscreen{border:0;display:flex;align-items:center;justify-content:center;background:#000;width:100vw;height:100vh}#stage:fullscreen img{max-width:100vw;max-height:100vh;object-fit:contain}#counter{min-width:90px;text-align:center}@media(max-width:1000px){.layout{grid-template-columns:1fr}.list{grid-template-columns:1fr}main{padding:12px}}@media print{nav,.controls,.list{display:none}.layout{display:block}aside{margin-top:16px}}
</style><main><h1>SCE视频录制材料 v01</h1><p class="muted">8页，计划4分45秒。沿用当前v10内容和方法图风格。此处是PPT与台词预览，尚未录制MP4。</p><nav><a href="SCE_video_presentation_v01.pptx">下载可编辑PPT</a><a href="narration.md">逐页口播稿</a><a href="recording_guide.md">详细录屏操作单</a><a href="record_demo.command">离线演示命令</a><a href="README.md">文件导航</a></nav><div class="controls"><button onclick="show(current-1)">上一页</button><span id="counter"></span><button onclick="show(current+1)">下一页</button><button onclick="document.getElementById('stage').requestFullscreen()">全屏预演</button><span class="muted">左右方向键翻页，Esc退出全屏</span></div><div class="layout"><div id="stage"><img id="slide" alt="当前视频PPT页面"></div><aside><h2 id="title"></h2><p id="timing" class="muted"></p><p id="speech"></p></aside></div><div class="list">BUTTONS</div><p class="muted">第3页为操作段的讲解画面，最终视频中插入约40秒真实录屏；不要把两者时长重复相加。原论文、研究包和方法图未改。</p></main><script>const story=STORY;let current=0;function show(i){current=Math.max(0,Math.min(story.slides.length-1,i));const s=story.slides[current];document.getElementById('slide').src='slides/slide_'+String(s.slide).padStart(2,'0')+'.png';document.getElementById('title').textContent=s.slide+'. '+s.title;document.getElementById('speech').textContent=s.narration;const f=x=>String(Math.floor(x/60)).padStart(2,'0')+':'+String(x%60).padStart(2,'0');document.getElementById('timing').textContent=f(s.start_seconds)+'—'+f(s.end_seconds)+'，约'+s.seconds+'秒';document.getElementById('counter').textContent=(current+1)+' / '+story.slides.length;}document.addEventListener('keydown',e=>{if(e.key==='ArrowRight')show(current+1);if(e.key==='ArrowLeft')show(current-1);});show(0);</script></html>'''
content=content.replace('BUTTONS',buttons).replace('STORY',json.dumps(story,ensure_ascii=False).replace('</','<\\/'))
(OUT/'index.html').write_text(content)
(OUT/'README.md').write_text('''# 视频录制材料 v01

2026-10-28。以当前v10 Word为内容依据，参照作者手调方法图的字体、蓝橙紫配色和清晰分层布局，新建8页16:9演示。原论文、研究包、方法图均保留。

先打开[逐页预览与台词](index.html)，左右方向键翻页；全屏模式只显示页图，可用于无动画预演。

## 你主要用这四份

- [可编辑视频PPT](SCE_video_presentation_v01.pptx)：原生文字、流程图与7个可编辑数据图表，口播在每页备注区。
- [分镜与逐页口播](narration.md)：约1100字，时间安排4分45秒，实际以试读为准。
- [详细录屏操作单](recording_guide.md)：准备窗口、唯一命令、具体镜头、预期输出与导出检查。
- [离线演示入口](record_demo.command)：在本机Terminal运行。新解压副本中执行20户规则工程例与全国结果复算，0 API、不改正式包。

## 内容顺序

1. 真实概率问卷与研究对象。
2. 家庭背景、历史信念、可见信息与统一计分。
3. 研究包执行与结果追溯，最终剪辑时插入真实操作录屏。
4. 82个月历史路径和2021年上行偏差。
5. 近期固定组合与历史微观分歧。
6. 月度漂移的启示与47周更新。
7. 循环信贷的局部用途。
8. 贡献、改进方向与研究边界。

主月度图沿用v10的512户直接模拟口径，统计扩展另述；周度没有统计扩展。近期组合沿用早48个月拟得的13.3976%模拟权重，不在近期重拟。下游8.17%是相对同结构官方SCE回归的RMSE降幅，不是胜过所有简单基线。全研究是回顾性检验。

## 其他文件

`slides/`为最终PPT重新导入后渲染的1920×1080逐页PNG。`storyboard.json`为结构化分镜。`archived_run_evidence.json`为正式A/B/周度运行公开台账的脱敏摘录，供操作段展示。

作者可以手调PPT。若手调，后续以手调PPT为基底，不用构建脚本覆盖；PPT导出可由作者在WPS中手动完成。本次未制作配音、字幕或最终MP4，不要求重新生成全量模型答卷。

源码位于`studies/sce_inflation_expectations/reports/video_demo_v1/`。本机录屏验跑写入`tmp/video_demo_v1/recording_sessions/`，不混入正式研究包。验证与保护文件哈希留在该临时构建目录，不占演示画面。
''')
print('Preview and README published')
