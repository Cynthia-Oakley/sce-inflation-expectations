"""Build the approved SCE overview as editable scene data and vector artwork.

This is figure authoring only. No data loading, model calls or metric fitting.
The JSON scene is also consumed by the native Artifact Session slide builder.
"""
from __future__ import annotations

import argparse
from html import escape
import json
import math
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.colors import HexColor

ROOT = Path(__file__).resolve().parents[4]
W, H = 1920, 1080
C = dict(ink="#172A3A", secondary="#526170", blue="#1D5B91", orange="#B75A1D",
         rule="#CED6DE", light="#F3F5F7", p="#EFF5FA", e="#FCF3EB", white="#FFFFFF")
FONT = "Arial Unicode MS"


def make_scene():
    items = []

    def rect(name, x, y, w, h, fill, stroke="none", width=1.4, dash=False):
        items.append(dict(kind="rect", name=name, x=x, y=y, w=w, h=h,
                          fill=fill, stroke=stroke, width=width, dash=dash))

    def text(name, content, x, y, w, size=28, color=None, bold=False, align="left", h=None):
        items.append(dict(kind="text", name=name, text=content, x=x, y=y, w=w,
                          h=h or size*1.35, size=size, fill=color or C["ink"],
                          bold=bold, align=align, font=FONT))

    def line(name, points, color=None, width=2.6, dash=False, arrow=False):
        items.append(dict(kind="line", name=name, points=points, stroke=color or C["secondary"],
                          width=width, dash=dash, arrow=arrow))

    def frame(name, x, y, w, h, fill, accent):
        rect(name, x, y, w, h, fill, C["rule"])
        rect(name+"-accent", x, y, 5, h, accent)

    text("title", "调查约束下的家庭通胀预期模拟", 56, 32, 1808, 46, bold=True)
    text("research-question", "SCE一年期预期：全国中心、家庭分歧与动态更新能否同时重建？", 56, 103, 1808, 29)
    rect("theory-band", 56, 162, 1808, 66, C["light"])
    text("theory-label", "设计依据", 80, 180, 170, 28, bold=True)
    text("theory-1", "信念持续性", 320, 180, 260, 29, C["blue"])
    text("theory-2", "有限注意", 750, 180, 250, 29, C["orange"])
    text("theory-3", "生活价格体验", 1130, 180, 310, 29, C["orange"])
    text("theory-constraint", "理论动机＋经验检验", 1535, 181, 305, 26, C["secondary"])

    # P and E enter B in parallel. Arrow elbows have explicit, disjoint ports.
    line("P-to-B", [[536, 390], [578, 390], [578, 448], [620, 448]], C["blue"], 3, arrow=True)
    line("E-to-B", [[536, 690], [578, 690], [578, 624], [620, 624]], C["orange"], 3, arrow=True)
    line("B-to-score", [[920, 535], [1000, 535]], C["ink"], 3, arrow=True)
    line("score-to-evaluation", [[1390, 535], [1470, 535]], C["ink"], 3, arrow=True)
    # The optional outputs use the same Core answers; they are not later LLM calls.
    line("score-to-Normal", [[1195, 770], [1195, 834]], C["blue"], 2.4, dash=True, arrow=True)
    line("score-to-blend", [[1342, 770], [1342, 797], [1430, 797], [1430, 884], [1470, 884]], C["secondary"], 2.4, dash=True, arrow=True)

    frame("P", 56, 260, 480, 280, C["p"], C["blue"])
    text("P-label", "01  人群 P", 80, 278, 425, 27, C["blue"], True)
    text("P-title", "家庭画像与原有信念", 80, 322, 432, 34, bold=True)
    text("P-grid", "学历3 × 数理2 × 年龄3 × 收入3", 80, 375, 432, 27)
    text("P-sampling", "54格＋未知池 · 过采样与校准", 80, 416, 432, 27)
    text("P-A", "A：本人历史／近期联合供体", 80, 458, 432, 27)
    text("P-B", "B：旧框架＋公开历史校准", 80, 491, 432, 27)

    frame("E", 56, 554, 480, 278, C["e"], C["orange"])
    text("E-label", "02  环境 E", 80, 572, 425, 27, C["orange"], True)
    text("E-title", "作答时的个人信息包", 80, 615, 432, 34, bold=True)
    text("E-channels", "新闻与政策   /   生活价格", 80, 669, 432, 28)
    text("E-time", "先按时间筛选，再分配信息", 80, 713, 432, 27)
    text("E-news", "随机4 / 8 / 16 / 32篇新闻", 80, 753, 432, 27)
    text("E-price", "CPI相关度×1.5 · 采购角色匹配", 80, 793, 432, 27)

    frame("B", 620, 360, 300, 350, C["white"], C["blue"])
    text("B-label", "03  行为 B", 646, 382, 248, 27, C["blue"], True)
    text("B-title", "家庭代理作答", 642, 438, 256, 34, bold=True, align="center")
    rect("model", 644, 495, 252, 58, C["blue"])
    text("model-name", "DeepSeek V3.2", 650, 509, 240, 29, C["white"], True, "center")
    text("Q8-output", "Q8  点预期", 646, 582, 248, 31, align="center")
    text("Q9-output", "Q9  十档概率", 642, 633, 256, 31, align="center")
    text("model-format", "Core直接模拟 · JSON", 636, 730, 268, 26, C["secondary"], align="center")

    frame("score", 1000, 300, 390, 470, C["white"], C["blue"])
    text("score-label", "04  计分与汇总", 1024, 321, 342, 27, C["blue"], True)
    text("score-title", "答卷回到调查尺度", 1024, 367, 342, 32, bold=True)
    text("score-Q9", "Q9 十档概率", 1024, 435, 342, 30)
    text("score-density", "连续密度 → 个人均值", 1024, 483, 342, 29)
    text("score-national", "人口加权 → 全国中位数", 1024, 532, 342, 28)
    line("score-separator", [[1024, 591], [1366, 591]], C["rule"], 1.2)
    text("score-Q8", "Q8 独立汇总", 1024, 616, 342, 29)
    text("score-distribution", "保留跨人分布", 1024, 664, 342, 29)
    text("score-weight", "权重只用于统计与评价", 1024, 718, 342, 27, C["secondary"])

    frame("evaluation", 1470, 260, 394, 556, C["light"], C["secondary"])
    text("eval-label", "05  跨层验证", 1494, 281, 346, 27, C["secondary"], True)
    text("eval-title", "模拟接近在哪一层", 1494, 326, 346, 32, bold=True)
    text("eval-national", "全国中心", 1494, 395, 346, 30, bold=True)
    text("eval-national-metrics", "MAE / RMSE · 强基线", 1494, 439, 346, 28)
    text("eval-micro", "家庭分歧（A）", 1494, 511, 346, 30, bold=True)
    text("eval-micro-metrics", "W1 / IQR · 同支持比较", 1494, 555, 346, 28)
    text("eval-dynamic", "动态与经济用途", 1494, 625, 346, 30, bold=True)
    text("eval-dynamic-metrics", "漂移／周度信号／下游预测", 1494, 670, 346, 27)
    rect("target-truth", 1490, 737, 354, 56, C["white"], C["rule"], 1.2)
    text("target-truth-label", "目标期真值只进入评价", 1500, 751, 334, 27, align="center")

    rect("Normal", 1000, 834, 390, 105, C["p"], C["blue"], 1.6, True)
    text("Normal-title", "Normal人口扩展（τ=8）", 1024, 847, 342, 27, C["blue"], True)
    text("Normal-method", "同格经验＋邻格收缩", 1024, 888, 342, 27)
    rect("blend", 1470, 834, 394, 105, C["white"], C["secondary"], 1.6, True)
    text("blend-title", "公开历史值＋模拟指标", 1494, 847, 346, 27, bold=True)
    text("blend-method", "冻结组合 · 原始结果另报", 1494, 888, 346, 27)

    text("extensions-label", "独立拓展", 56, 884, 150, 27, bold=True)
    text("extensions-recursion", "月度自主递推／周度发布后校准", 240, 874, 700, 28)
    text("extensions-use", "月度指标 → 同结构经济预测", 240, 918, 700, 28)
    line("footer-rule", [[56, 982], [1864, 982]], C["rule"], 1.2)
    text("legend", "实线：主数据路径   虚线：可选统计支路；Normal不增加独立LLM判断", 56, 999, 1808, 27, C["secondary"])
    text("boundary", "A为历史重建，B为近期回顾性模拟；时间资格、配置、回包与复算入口分别留档", 56, 1037, 1808, 26, C["secondary"])
    return dict(schema="sce_overview_figure_scene/v1", width=W, height=H, font=FONT,
                title="调查约束下的家庭通胀预期模拟", items=items,
                notes="来源：overview_figure_brief.md；CURRENT_SIMULATION_CONFIGURATION.md；A T0、Normal及周度冻结结果说明。P/E并行进入B。Normal是同批答卷统计支路；组合只用已公开历史值。图为研究方法示意，不呈现效果数值或因果估计。")


def arrow_polygon(points, length=13, width=6):
    x0,y0 = points[-2]; x,y = points[-1]
    a=math.atan2(y-y0,x-x0)
    return [(x,y),(x-length*math.cos(a)+width*math.sin(a),y-length*math.sin(a)-width*math.cos(a)),
            (x-length*math.cos(a)-width*math.sin(a),y-length*math.sin(a)+width*math.cos(a))]


def svg(scene):
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="180mm" height="101.25mm" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">',
         '<title id="title">'+escape(scene['title'])+'</title>',
         '<desc id="desc">P家庭与既有信念、E个人信息包共同进入B家庭代理；Q8/Q9经过计分与加权，接受全国、微观、动态验证。Normal与冻结组合单列支路。</desc>',
         f'<rect width="{W}" height="{H}" fill="white"/>']
    for e in scene['items']:
        n=escape(e['name'])
        if e['kind']=='rect':
            out.append(f'<rect id="{n}" x="{e["x"]}" y="{e["y"]}" width="{e["w"]}" height="{e["h"]}" fill="{e["fill"]}" stroke="{e["stroke"]}" stroke-width="{e["width"]}"'+(' stroke-dasharray="9 7"' if e['dash'] else '')+'/>')
        elif e['kind']=='line':
            pts=' '.join(f'{x},{y}' for x,y in e['points'])
            out.append(f'<polyline id="{n}" points="{pts}" fill="none" stroke="{e["stroke"]}" stroke-width="{e["width"]}"'+(' stroke-dasharray="9 7"' if e['dash'] else '')+'/>')
            if e['arrow']:
                pts=' '.join(f'{x:.3f},{y:.3f}' for x,y in arrow_polygon(e['points']))
                out.append(f'<polygon points="{pts}" fill="{e["stroke"]}"/>')
        else:
            x=e['x']+e['w']/2 if e['align']=='center' else e['x']
            out.append(f'<text id="{n}" x="{x}" y="{e["y"]+e["size"]*0.96}" font-family="Arial Unicode MS, Noto Sans CJK SC, PingFang SC, sans-serif" font-size="{e["size"]}" font-weight="{700 if e["bold"] else 400}" fill="{e["fill"]}" text-anchor="{"middle" if e["align"]=="center" else "start"}">{escape(e["text"])}</text>')
    return '\n'.join(out+['</svg>'])+'\n'


def vector_pdf(scene, out, font_path):
    pdfmetrics.registerFont(TTFont('SCEArial',str(font_path)))
    page_w=180*72/25.4
    scale=page_w/W
    c=Canvas(str(out),pagesize=(page_w,H*scale),pageCompression=1)
    c.setTitle(scene['title'])
    c.setAuthor('水上挽月')
    c.scale(scale,scale)
    fits=[]
    for e in scene['items']:
        if e['kind']=='rect':
            c.setFillColor(HexColor(e['fill']))
            c.setStrokeColor(HexColor(e['stroke']) if e['stroke']!='none' else HexColor(e['fill']))
            c.setLineWidth(e['width']); c.setDash([9,7] if e['dash'] else [])
            c.rect(e['x'],H-e['y']-e['h'],e['w'],e['h'],fill=1,stroke=e['stroke']!='none')
        elif e['kind']=='line':
            c.setStrokeColor(HexColor(e['stroke'])); c.setLineWidth(e['width']);c.setDash([9,7] if e['dash'] else [])
            p=c.beginPath();p.moveTo(e['points'][0][0],H-e['points'][0][1])
            for x,y in e['points'][1:]:p.lineTo(x,H-y)
            c.drawPath(p,stroke=1,fill=0)
            if e['arrow']:
                c.setFillColor(HexColor(e['stroke'])); c.setDash([])
                pts=arrow_polygon(e['points']);p=c.beginPath();p.moveTo(pts[0][0],H-pts[0][1])
                for x,y in pts[1:]:p.lineTo(x,H-y)
                p.close();c.drawPath(p,stroke=0,fill=1)
        else:
            c.saveState()
            c.setFillColor(HexColor(e['fill']));c.setFont('SCEArial',e['size'])
            tw=pdfmetrics.stringWidth(e['text'],'SCEArial',e['size'])
            fits.append(dict(name=e['name'],width=round(tw,2),box_width=e['w'],fits=tw<=e['w']))
            x=e['x']+(e['w']-tw)/2 if e['align']=='center' else e['x']
            t=c.beginText(x,H-e['y']-e['size']*0.96)
            if e['bold']:
                c.setStrokeColor(HexColor(e['fill']));c.setLineWidth(0.45);t.setTextRenderMode(2)
            t.textOut(e['text']);c.drawText(t);c.restoreState()
    c.showPage();c.save()
    return fits


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--font',type=Path,default=Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
    a=p.parse_args(); dest=a.out.resolve()
    if dest.exists():raise SystemExit('Use a new output directory; existing editions are preserved.')
    dest.mkdir(parents=True)
    scene=make_scene()
    (dest/'scene.json').write_text(json.dumps(scene,ensure_ascii=False,indent=2)+'\n')
    (dest/'sce_framework_paper_v1.svg').write_text(svg(scene))
    fits=vector_pdf(scene,dest/'sce_framework_paper_v1.pdf',a.font)
    (dest/'text_fit.json').write_text(json.dumps(fits,ensure_ascii=False,indent=2)+'\n')
    errors=[e for e in fits if not e['fits']]
    print(json.dumps(dict(directory=str(dest),labels=len(fits),text_overflows=errors),ensure_ascii=False,indent=2))
    if errors:raise SystemExit(2)


if __name__=='__main__':main()
