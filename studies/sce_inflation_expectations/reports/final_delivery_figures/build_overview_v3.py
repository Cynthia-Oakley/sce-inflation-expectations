"""Paper-facing editable overview; no API calls or density re-estimation.

The tiny Q9 plot evaluates an already frozen, previously displayed example.
It is a scoring illustration, not a new simulated response or population result.
"""
from __future__ import annotations

import argparse
from html import escape
import importlib.util
import json
import math
from pathlib import Path
import hashlib

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.colors import HexColor

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("sce_overview_v2_layout", HERE / "build_overview_v2.py")
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
ROOT = common.ROOT
W, H = 1920, 1080
S = .96
C = dict(ink="#203447", blue="#285580", orange="#AC5725", purple="#77558F",
         gray="#526170", rule="#D5DEE5", p="#F1F6FA", e="#FCF4EC",
         b="#F5F0F8", light="#F5F7F9", white="#FFFFFF")


def make_scene():
    boxes, arrows, graphics = [], [], []

    def para(text, size=29, color=None, bold=False, after=6, label=None):
        return dict(text=text, size=size*S, color=color or C['ink'],
                    runs=common.runs_for(text, bold=bold, label=label), after=after*S)

    def box(name, x, y, w, h, paragraphs, fill='none', stroke='none', inset=0):
        boxes.append(dict(name=name, x=x*S, y=y*S, w=w*S, h=h*S,
                          paragraphs=paragraphs, fill=fill, stroke=stroke, inset=inset*S))

    def card(name, x, y, w, h, title, rows, fill, accent):
        box(name, x, y, w, h,
            [para(title, 34, accent, True, 13)] + [para(t, size, label=t.split('：')[0]+'：' if '：' in t else None)
                                                              for t, size in rows], fill, C['rule'], 19)

    def arrow(name, points, color=None, width=3):
        arrows.append(dict(name=name, points=[[x*S,y*S] for x,y in points],
                           color=color or C['ink'], width=width*S))

    def rect(name, x, y, w, h, fill, stroke='none'):
        graphics.append(dict(kind='rect', name=name, x=x*S, y=y*S, w=w*S, h=h*S,
                             fill=fill, stroke=stroke))

    def line(name, points, color, width=2, dashed=False):
        graphics.append(dict(kind='path', name=name, points=[[x*S,y*S] for x,y in points],
                             color=color, width=width*S, dashed=dashed))

    box('title', 40, 18, 1920, 61, [para('居民通胀预期模拟的方法框架',46,bold=True)])
    box('subject',40,91,1920,46,[para('SCE一年期问卷：家庭画像与既有信念 × 可见环境 → 个体答卷 → 全国指标',30)])
    for name,x,w,title,color in [
        ('stage-input',40,500,'01  人群与信息',C['blue']),
        ('stage-agent',635,320,'02  问卷行为',C['purple']),
        ('stage-index',1030,460,'03  指标形成',C['blue']),
        ('stage-evaluation',1570,390,'04  效果检验',C['ink'])]:
        box(name,x,164,w,48,[para(title,33,color,True)])
        line(name+'-rule',[[x,213],[x+w,213]],C['rule'],1.5)

    card('population',40,235,500,330,'P  家庭画像与原有信念',[
        ('来源：SCE公开微观资料',29),
        ('网格：学历×数理×年龄×收入',29),
        ('抽样：小格过采样，人口权重校准',28),
        ('重建：本人或相似家庭的历史答卷',28),
        ('近期：联合抽样＋最新已公布SCE校准',27),
        ('合成：支出、采购责任、联储信心',28),
    ],C['p'],C['blue'])
    card('environment',40,590,500,330,'E  因人、因时组织信息',[
        ('价格：食品CPI总项与采购细项',29),
        ('新闻：随机4/8/16/32篇',29),
        ('主题：人口兴趣与价格相关性',29),
        ('通胀相关度高的新闻，抽样权重×1.5',28),
        ('政策：截止前公开的美联储动态',28),
        ('时点：实际或合成作答日前一日¹',28),
    ],C['e'],C['orange'])
    box('theory-note',40,935,500,85,[
        para('设计依据',29,C['gray'],True,4),
        para('信念持续性 · 有限注意 · 价格体验',28,C['gray'])])

    card('behavior',635,350,320,350,'B  模拟问卷回答',[
        ('DeepSeek V3.2',31),
        ('温度0.5；关闭思考',28),
        ('Q8：未来12个月点预期',27),
        ('Q9：十档概率',28),
        ('输出：JSON答卷',28),
    ],C['b'],C['purple'])
    box('model-details',635,720,330,90,[
        para('SiliconFlow FP8 固定供应商',26,C['gray'],after=3),
        para('最多1,024输出token',26,C['gray'])])

    # The scoring visual is the existing observed June-2025 example, without IDs.
    example = json.loads((ROOT/'outputs/sce_research_report_figures_20261024_v03/figure_data.json').read_text())
    probabilities = example['q9_probabilities_ascending_pct']
    assert len(probabilities)==10 and abs(sum(probabilities)-100)<1e-8
    box('q9-scoring',1030,236,460,52,[para('Q9：概率答卷 → 个人密度均值',30,C['blue'],True)])
    bx,by,bw,bh = 1050,312,160,88
    line('bin-baseline',[[bx,by+bh],[bx+bw,by+bh]],C['rule'],1.7)
    for i,p in enumerate(probabilities):
        x=bx+i*bw/10+2
        if p>0: rect(f'observed-q9-bin-{i+1}',x,by+bh-bh*p/max(probabilities),bw/10-4,bh*p/max(probabilities),C['orange'])
        line(f'bin-tick-{i+1}',[[x+6,by+bh],[x+6,by+bh+4]],C['gray'],1)
    box('bins-label',1030,416,200,45,[para('十档概率',28,C['gray'])])
    arrow('bins-to-density',[[1230,356],[1260,356]],C['blue'],2.5)
    a,b,left,right=example['density_parameters']
    def density(z):
        if not 0<z<1:return 0.
        return math.exp((a-1)*math.log(z)+(b-1)*math.log1p(-z)-math.lgamma(a)-math.lgamma(b)+math.lgamma(a+b))/(right-left)
    yy=[density(i/80) for i in range(81)]; maximum=max(yy)
    dx,dy,dw,dh=1280,312,175,88
    points=[[dx+dw*i/80,dy+dh-dh*y/maximum] for i,y in enumerate(yy)]
    line('frozen-example-density',points,C['blue'],3)
    line('density-baseline',[[dx,dy+dh],[dx+dw,dy+dh]],C['rule'],1.7)
    mx=dx+dw*(example['density_mean_pct']-left)/(right-left)
    line('density-mean',[[mx,dy-4],[mx,dy+dh]],C['orange'],1.8,True)
    box('density-label',1275,416,210,45,[para('连续密度',28,C['gray'])])
    box('weighted-center',1030,480,460,90,[
        para('个人均值 → 人口加权中位数',29,bold=True,after=4),
        para('Q8点预期独立汇总',28,C['gray'])])
    arrow('scores-to-national',[[1260,573],[1260,605]],C['blue'],2.8)
    box('national-index',1030,610,460,85,[para('全国模拟指标',35,C['blue'],True)],C['p'],C['rule'],16)
    box('postprocessing',1030,706,460,124,[
        para('规模：经验贝叶斯扩展（τ=8）',28,label='规模：'),
        para('组合：已公布SCE＋模拟指标',28,label='组合：'),
        para('原始、扩展与组合分别报告',27,C['gray'])])

    for name,y,metric,explain in [
        ('mae',237,'MAE','全国中心的拟合误差'),
        ('w1',363,'W1','模型与真人的分布距离'),
        ('iqr',489,'IQR','不同家庭之间的分歧')]:
        box('metric-'+name,1570,y,390,120,[
            para(metric,39,C['blue'],True,5),para(explain,28,C['ink'])],C['light'],'none',14)
    box('evaluation-scope',1570,622,390,161,[
        para('基线：已公开SCE持续性',28,label='基线：'),
        para('　　　同结构SCE＋CPI模型',27),
        para('微观：用于历史重建',27,label='微观：'),
        para('近期：仅评价全国误差',27,label='近期：')])
    box('truth-only',1570,807,390,52,[para('真实SCE：仅用于事后评价',28,C['gray'])])
    arrow('truth-to-evaluation',[[1940,807],[1940,787]],C['gray'],2)

    arrow('P-to-B',[[540,382],[585,382],[585,465],[635,465]],C['blue'])
    arrow('E-to-B',[[540,733],[585,733],[585,595],[635,595]],C['orange'])
    arrow('B-to-statistics',[[955,518],[1013,518]],C['purple'])
    arrow('index-to-evaluation',[[1490,646],[1545,646]],C['blue'])

    # Separate dynamic studies use individual simulated states. Downstream uses
    # the monthly index; these branches must not be confused with one another.
    arrow('state-to-monthly',[[955,680],[975,680],[975,849],[795,849],[795,887]],C['purple'],2.4)
    arrow('state-to-weekly',[[975,849],[1265,849],[1265,887]],C['purple'],2.4)
    arrow('monthly-index-to-economy',[[1490,747],[1525,747],[1525,849],[1755,849],[1755,887]],C['blue'],2.4)
    for name,x,w,title,text in [
        ('monthly',635,395,'月度递推','固定家庭 → 检查信念漂移'),
        ('weekly',1057,415,'周度更新','发布后校准 → 月末MAE'),
        ('downstream',1505,455,'下游经济用途','月度指标 → 信贷等RMSE')]:
        box('extension-'+name,x,887,w,120,[para(title,31,C['purple'],True,8),para(text,28)],C['b'],'none',15)

    box('timing-note',40,1024,1920,37,[para('¹ 历史重建用实际完成日；近期用合成日期，环境另受月度全局截止限制。P与先验按月准备。',25,C['gray'])])
    box('graphic-note',40,1065,1920,38,[para('Q9小图取自已封存的2025-06匿名真实答卷，仅说明计分；图中箭头表示数据与分析依赖。',25,C['gray'])])
    return dict(schema='sce_overview_native/v3',width=W,height=H,chinese_font='Kaiti SC',latin_font='Times New Roman',
                title='居民通胀预期模拟的方法框架',boxes=boxes,arrows=arrows,graphics=graphics,
                example=dict(month=example['month'],probabilities=probabilities,parameters=example['density_parameters'],
                             existing_mean=example['density_mean_pct'],new_density_fits=0),
                notes='主模拟评价与v09对齐：全国MAE、跨人W1与IQR；RMSE仅列下游经济用途。偏差与漂移为路径诊断，不增加并列主指标。中文楷体，英文/数字Times New Roman。原始、扩展和组合分报，近期不评真人微观准确率。方法图无目标期真值输入。微观真实答卷示例来自已封存figure_data.json，未重拟合。')


def render(scene,out):
    scale=180*72/25.4/W
    c=Canvas(str(out/'sce_framework_paper_v3.pdf'),pagesize=(W*scale,H*scale),pageCompression=1)
    c.setTitle(scene['title']);c.setAuthor('水上挽月');c.scale(scale,scale)
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="180mm" height="101.25mm" viewBox="0 0 {W} {H}">',
         f'<title>{escape(scene["title"])}</title>',f'<rect width="{W}" height="{H}" fill="white"/>']
    for b in scene['boxes']:
        if b['fill']=='none':continue
        c.setFillColor(HexColor(b['fill']));c.setLineWidth(1.1)
        c.setStrokeColor(HexColor(b['stroke']) if b['stroke']!='none' else HexColor(b['fill']))
        c.rect(b['x'],H-b['y']-b['h'],b['w'],b['h'],fill=1,stroke=b['stroke']!='none')
        svg.append(f'<rect x="{b["x"]}" y="{b["y"]}" width="{b["w"]}" height="{b["h"]}" fill="{b["fill"]}" stroke="{b["stroke"]}"/>')
    def path(points,color,width,dashed=False):
        c.saveState();c.setStrokeColor(HexColor(color));c.setLineWidth(width)
        if dashed:c.setDash(6,4)
        p=c.beginPath();p.moveTo(points[0][0],H-points[0][1])
        for x,y in points[1:]:p.lineTo(x,H-y)
        c.drawPath(p);c.restoreState()
        svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="{width}"'+(' stroke-dasharray="6 4"' if dashed else '')+'/>')
    for a in scene['arrows']:
        path(a['points'],a['color'],a['width'])
        pts=common.arrow_tip(a['points']);p=c.beginPath();p.moveTo(pts[0][0],H-pts[0][1])
        for x,y in pts[1:]:p.lineTo(x,H-y)
        p.close();c.setFillColor(HexColor(a['color']));c.drawPath(p,fill=1,stroke=0)
        svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in pts)}" fill="{a["color"]}"/>')
    for g in scene['graphics']:
        if g['kind']=='path':path(g['points'],g['color'],g['width'],g.get('dashed',False))
        else:
            c.setFillColor(HexColor(g['fill']));c.rect(g['x'],H-g['y']-g['h'],g['w'],g['h'],fill=1,stroke=0)
            svg.append(f'<rect x="{g["x"]}" y="{g["y"]}" width="{g["w"]}" height="{g["h"]}" fill="{g["fill"]}"/>')
    fits=[]
    for b in scene['boxes']:
        lines,end=common.layout_box(b)
        fits.append(dict(name=b['name'],content_bottom=round(end,2),box_bottom=round(b['y']+b['h']-b['inset'],2),fits=end<=b['y']+b['h']-b['inset']))
        svg.append(f'<text id="{b["name"]}">')
        for row in lines:
            p=row['para'];size=p['size'];x=row['x'];baseline=H-row['y']-size*.87
            svg.append(f'<tspan x="{x}" y="{row["y"]+size*.87}" font-size="{size}" fill="{p["color"]}">')
            for run in common.line_runs(row):
                fn='Kai' if run['font']=='Kaiti SC' else 'Times';text=run['text']
                c.saveState();c.setFillColor(HexColor(p['color']));c.setFont(fn,size);t=c.beginText(x,baseline)
                if run['bold']:c.setLineWidth(.34);c.setStrokeColor(HexColor(p['color']));t.setTextRenderMode(2)
                t.textOut(text);c.drawText(t);c.restoreState();x+=pdfmetrics.stringWidth(text,fn,size)
                svg.append(f'<tspan font-family="{run["font"]}" font-weight="{700 if run["bold"] else 400}">{escape(text)}</tspan>')
            svg.append('</tspan>')
        svg.append('</text>')
    c.showPage();c.save();svg.append('</svg>')
    (out/'sce_framework_paper_v3.svg').write_text('\n'.join(svg)+'\n')
    return fits


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise SystemExit('Use a new output directory.')
    pdfmetrics.registerFont(TTFont('Kai',str(common.KAI)));pdfmetrics.registerFont(TTFont('Times',str(common.TIMES)))
    a.out.mkdir(parents=True);scene=make_scene()
    (a.out/'scene.json').write_text(json.dumps(scene,ensure_ascii=False,indent=2)+'\n')
    fits=render(scene,a.out)
    (a.out/'text_fit.json').write_text(json.dumps(fits,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(text_boxes=len(scene['boxes']),failed=[x for x in fits if not x['fits']]),ensure_ascii=False))
    if any(not x['fits'] for x in fits):raise SystemExit(2)


if __name__=='__main__':main()
