"""Create the local nine-slide reading/recording entry and a separate operation list."""
from pathlib import Path
import html
import json

ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'deliverables/video/v03'
story=json.loads((OUT/'storyboard.json').read_text())
data=json.dumps(story,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
page='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SCE视频完整9页 v03</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f6f8;color:#203447;font-family:'Kaiti SC','STKaiti','Times New Roman',serif}header{padding:16px 24px;background:white;border-bottom:1px solid #dbe3e8;display:flex;gap:20px;align-items:center;flex-wrap:wrap}header strong{font-size:23px}a{color:#2b5e87}header a{font-size:17px}button,select{font:inherit;font-size:18px;cursor:pointer;background:white;border:1px solid #dbe3e8;border-radius:4px;color:#203447;padding:7px 12px}button:hover{background:#edf3f8}.layout{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:20px;padding:24px;max-width:1800px;margin:auto}.screen{min-width:0}.image-frame{background:white;border:1px solid #dbe3e8}.image-frame img{display:block;width:100%;height:auto}.controls{display:flex;gap:10px;align-items:center;justify-content:center;margin:16px 0}.counter{font-family:'Times New Roman',serif;font-size:19px;color:#637481;margin:0 8px}.interaction{padding:12px 0;text-align:center;font-size:19px;min-height:55px}.interaction a{display:inline-block;padding:8px 15px;background:white;border:1px solid #dbe3e8;border-radius:4px;text-decoration:none}.notes{background:white;padding:22px;border:1px solid #dbe3e8;align-self:start}.notes h2{font-size:24px;margin:0 0 10px}.duration{color:#637481;font-size:16px}.speech{font-size:21px;line-height:1.85;margin:19px 0}.operation{border-top:1px solid #dbe3e8;padding-top:16px;font-size:17px;line-height:1.7;color:#637481}.thumbnails{display:grid;grid-template-columns:repeat(9,1fr);gap:8px}.thumbnails button{padding:3px;border:2px solid transparent;background:none;border-radius:0}.thumbnails button.active{border-color:#2b5e87}.thumbnails img{display:block;width:100%;height:auto}.thumbnails span{font-family:'Times New Roman',serif;font-size:15px}.bottom{font-size:16px;color:#637481;line-height:1.7;margin-top:12px}.slideshow{background:#141b23}.slideshow header,.slideshow .notes,.slideshow .controls,.slideshow .interaction,.slideshow .thumbnails,.slideshow .bottom{display:none}.slideshow .layout{padding:0;display:block;max-width:none;height:100vh}.slideshow .screen{height:100vh;display:flex;align-items:center;justify-content:center}.slideshow .image-frame{border:0;width:min(100vw,177.7778vh)}.slideshow .image-frame img{max-height:100vh}.slideshow-exit{display:none;position:fixed;right:14px;top:12px;z-index:10;font-size:15px;opacity:.2}.slideshow .slideshow-exit{display:block}.slideshow .slideshow-exit:hover{opacity:1}.slideshow .slideshow-exit:focus{opacity:1}
@media(max-width:1000px){.layout{display:block;padding:15px}.notes{margin-top:20px}.speech{font-size:20px}.thumbnails{grid-template-columns:repeat(5,1fr)}}
</style></head><body><header><strong>SCE · 完整9页录制稿 v03</strong><a href="SCE_video_complete_v03.pptx">下载PPT</a><a href="发言稿_逐页录制_v03.txt">单独发言稿</a><a href="录制操作单_v03.md">操作单</a><button id="present">纯画面放映</button></header><button class="slideshow-exit" id="exit">退出放映（Esc）</button><main class="layout"><section class="screen"><div class="image-frame"><img id="slide" alt=""></div><div class="controls"><button id="prev">上一页</button><select id="jump" aria-label="选择页面"></select><span class="counter" id="counter"></span><button id="next">下一页</button></div><div class="interaction" id="interaction"></div><div class="thumbnails" id="thumbs"></div><p class="bottom">左右方向键翻页。已确认的第2、4、5页保留真实样本与原生图表，可单独切换至交互页面录制。首页引用作者确认的方法图。当前是演示材料，尚未录音或导出视频。</p></section><aside class="notes"><h2 id="title"></h2><div class="duration" id="duration"></div><p class="speech" id="speech"></p><div class="operation" id="operation"></div></aside></main><script type="application/json" id="story">__STORY__</script><script>
const data=JSON.parse(document.getElementById('story').textContent),$=s=>document.querySelector(s);let i=0;
$('#jump').innerHTML=data.slides.map((s,k)=>'<option value="'+k+'">第'+s.page+'页　'+s.title+'</option>').join('');
$('#thumbs').innerHTML=data.slides.map((s,k)=>'<button data-index="'+k+'" aria-label="第'+s.page+'页"><img src="slides/page_'+String(s.page).padStart(2,'0')+'.png" alt=""><span>'+s.page+'</span></button>').join('');
function show(n){i=Math.max(0,Math.min(8,n));let s=data.slides[i];$('#slide').src='slides/page_'+String(s.page).padStart(2,'0')+'.png';$('#slide').alt='第'+s.page+'页 '+s.title;$('#counter').textContent=(i+1)+' / 9';$('#jump').value=String(i);$('#title').textContent='第'+s.page+'页　'+s.title;$('#duration').textContent='建议约'+s.seconds+'秒';$('#speech').textContent=s.narration;$('#operation').textContent='录制操作：'+s.operation;$('#interaction').innerHTML=[2,4,5].includes(s.page)?'<a target="_blank" href="../samples_v02/index.html#page='+s.page+'&sample=A01">打开第'+s.page+'页真实样本交互</a>':'';document.querySelectorAll('[data-index]').forEach(b=>b.classList.toggle('active',+b.dataset.index===i));history.replaceState(null,'','#page='+s.page);}
$('#prev').onclick=()=>show(i-1);$('#next').onclick=()=>show(i+1);$('#jump').onchange=e=>show(+e.target.value);document.querySelectorAll('[data-index]').forEach(b=>b.onclick=()=>show(+b.dataset.index));$('#present').onclick=()=>document.body.classList.add('slideshow');$('#exit').onclick=()=>document.body.classList.remove('slideshow');document.onkeydown=e=>{if(e.target.tagName==='SELECT')return;if(['ArrowRight','PageDown',' '].includes(e.key)){e.preventDefault();show(i+1)}if(['ArrowLeft','PageUp'].includes(e.key)){e.preventDefault();show(i-1)}if(e.key==='Escape')document.body.classList.remove('slideshow');};const match=location.hash.match(/page=(\d)/);show(match?+match[1]-1:0);
</script></body></html>'''
(OUT/'index.html').write_text(page.replace('__STORY__',data))

ops=['# 分页录制操作单 v03','','配套9页PPT与独立发言稿，计划4分45秒。按页边讲边录，出错只重录该页。PPT静态页没有逐步动画，左右键用于翻页；交互按钮在HTML中操作。','','## 录制前','','- 打开PPT放映或本目录index.html的“纯画面放映”。','- 麦克风已由作者实测可用。稿子放手机、纸上或录屏区域之外。','- 所有页面统一16:9，选取相同录制区域；每段前后留约2秒静止画面。','- 第2/4/5页如用HTML，先恢复家庭A01。第4页默认对照A02，不必现场反复抽样。','','## 逐页顺序','']
for s in story['slides']:
    ops += [f"### 第{s['page']}页　{s['title']}（约{s['seconds']}秒）",'',s['operation'],'']
ops += ['## 第7页的唯一命令','','在本机Terminal复制下列整行；该命令只做20户工程示例和封存聚合结果复算，0 API，不启动正式生成。','','```bash','"/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/deliverables/video/v01/record_demo.command"','```','',
        '运行结束会打印新的结果页和receipt路径。打开结果后，只展示A82_personal_T0及收据，不将页面保留的旧B参考当成最新B结果。第7页25秒包含这段录屏，不能把PPT25秒与操作25秒重复相加。','',
        '## 录制完成','','按页保存01—09。只需裁掉开头结尾的准备时间，再按顺序拼接；操作页讲述不顺时，可保留画面另补旁白。最终检查总时长、字幕、单位及声音，导出MP4。','',
        '原报告、研究包、框架图和已确认样页均未覆盖。完整PPT可以手改；后续以作者手改文件为准，不用构建脚本覆盖。']
(OUT/'录制操作单_v03.md').write_text('\n'.join(ops))
(OUT/'README.md').write_text('''# 视频完整录制稿 v03

2026年10月28日。新增第1、3、6、7、8、9页，导入并保留已确认第2、4、5页，合成为9页录制稿。原v01、三张样稿、论文、方法图和研究包保留。

- [逐页预览、台词及操作](index.html)
- [完整9页PPT](SCE_video_complete_v03.pptx)
- [单独发言稿](发言稿_逐页录制_v03.txt)
- [分页录制操作单](录制操作单_v03.md)
- [已有真实样本交互](../samples_v02/index.html)

独立发言稿约1,040字，计划4分45秒，实际以作者试读为准。每页的同一段口播也在PPT备注中。操作指令放在单独操作单，不夹在口播正文。

第1页直接引用作者确认的高清方法框架图，其可编辑原稿仍在原目录；其他8页保留原生文字与可编辑图表。第2/4/5页的点击换样、完整Prompt和JSON展开通过既有HTML进行。所有静态PPT页不依赖逐步动画，可以直接分页录制。

人口页采用2021年6月真实抽样权重，较小格3人全取，较大格110人抽19人。图中“仅原调查权重”与“校准后”显示抽样校正的作用，不是当期真值驱动的调权。A01贯穿画像、信息与计分。

结果主图用512人直接模拟口径，统计扩展单列；A与B阶段分开，不合并计算一个总MAE。固定组合权重沿用早48月MSE拟合值，不在近期重拟。周度只有11个月末真值点，没有虚构周真值；信贷8.17%是历史月度模拟相对同结构SCE回归的RMSE下降。

不新增API调用、Q9密度拟合或研究参数。完整视频与录音尚未制作。此目录用于本地录制，含匿名真实样本条件输入的节选，已从自动Git收集排除；不自动并入公开提交包。

制作源码在`studies/sce_inflation_expectations/reports/video_complete_v03/`，私有来源核对与验收在`tmp/video_complete_v03/`。手调后以作者PPT为基底，勿用旧构建器覆盖。
''')
print(json.dumps(dict(preview=str(OUT/'index.html'),pages=9,speech_characters=sum(len(s['narration']) for s in story['slides'])),ensure_ascii=False))
