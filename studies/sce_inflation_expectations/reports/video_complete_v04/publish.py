"""Publish the new slide-9 preview without rewriting the author's v03 files."""
from pathlib import Path
import json
import re

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'deliverables/video/v04';BASE=ROOT/'deliverables/video/v03'


def main():
    story=json.loads((OUT/'storyboard.json').read_text())
    data=json.dumps(story,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    page=(BASE/'index.html').read_text().replace('SCE_video_complete_v03.pptx','SCE_video_complete_v04.pptx')
    page=page.replace('发言稿_逐页录制_v03.txt','发言稿_逐页录制_v04.txt').replace('录制操作单_v03.md','录制操作单_v04.md').replace('v03','v04')
    page=page.replace("#page='+s.page+'&sample=A01", "#page='+data.interactive_pages[String(s.page)]+'&sample=A01")
    page=re.sub(r'(<script type="application/json" id="story">).*?(</script>)',lambda m:m.group(1)+data+m.group(2),page,flags=re.S)
    page=page.replace('首页引用作者确认的方法图。当前是演示材料，尚未录音或导出视频。','第9页按50%／25%／25%展示周度、月度与下游预测。第1—8页沿用作者手改版，当前尚未导出视频。')
    (OUT/'index.html').write_text(page)
    ops=(BASE/'录制操作单_v03.md').read_text().replace('v03','v04').replace('4分45秒','约5分钟')
    s=story['slides'][8]
    sections='\n\n'.join(f'### 第{s["page"]}页　{s["title"]}（约{s["seconds"]}秒）\n\n{s["operation"]}' for s in story['slides'])+'\n\n'
    ops=re.sub(r'### 第1页.*?(?=## 第7页)',lambda _:sections,ops,flags=re.S)
    ops=ops.replace('第2/4/5页如用HTML，先恢复家庭A01。第4页默认对照A02','第2/4/5页如用HTML，先恢复家庭A01。信息对照页默认对照A02')
    (OUT/'录制操作单_v04.md').write_text(ops)
    (OUT/'README.md').write_text('''# 视频录制稿 v04

本版以作者2026年10月28日10:26保存的完整v03 PPT为基础，只重排第9页。原v03和作者10:48修改的发言稿保留。

- [逐页预览](index.html#page=9)
- [完整9页PPT](SCE_video_complete_v04.pptx)
- [单独发言稿](发言稿_逐页录制_v04.txt)
- [录制操作单](录制操作单_v04.md)

第9页的空间比例为50%周度、25%月度、25%下游指标预测。新增周度小标题与解释，月度改为“个人模拟信念连续传递”，下游给出循环消费信贷的解释与1—3月预测误差图。三幅图均采用封存真实数据，并保留可编辑图表和工作簿。周度没有周真值，图中的真实值仍是11个月末点。

第1—8页保留作者手调文字、布局和图表标签。对WPS保存造成的不规范图表标题公式及单系列分组枚举，只作不改变数值、标签和外观的封包兼容修复，不用旧样页覆盖作者修好的第2、5页。源文件和研究结果不回写。

当前作者PPT中，第4页为概率计分，第5页为信息对照。发言稿的同一段正文与交互入口按这个现有顺序对齐，不调整前8页PPT。

发言稿第1—8页沿用作者最新版本，第9页按作者新增思路微调，约45秒。整套计划约5分钟，实际以试读为准。所有静态PPT页均无逐步动画，第2/4/5页仍可打开已有交互页面。

制作源码位于study的reports/video_complete_v04/，私人输入快照与检查在tmp/video_complete_v04/。本地样本节选不自动加入公开研究包或Git。0新增模型调用、0新增研究拟合。
''')
    print(json.dumps(dict(preview=str(OUT/'index.html'),edited_page=9),ensure_ascii=False))


if __name__=='__main__':main()
