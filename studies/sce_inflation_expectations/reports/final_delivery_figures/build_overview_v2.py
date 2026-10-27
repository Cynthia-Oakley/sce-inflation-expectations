"""SCE overview v2: audience-facing wording, native text-owning diagram boxes.

No simulations, target reads, metric fitting or external requests.
"""
from __future__ import annotations
import argparse
from html import escape
import json
import math
from pathlib import Path
import re
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.colors import HexColor

ROOT=Path(__file__).resolve().parents[4]
W,H=1920,1080
KAI=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
TIMES=Path('/System/Library/Fonts/Supplemental/Times New Roman.ttf')
C={'ink':'#172A3A','blue':'#1D5B91','orange':'#AE541D','gray':'#526170','rule':'#C8D2DB','p':'#EFF5FA','e':'#FCF3EB','light':'#F3F5F7','white':'#FFFFFF'}


def chinese(ch):
    return bool(re.match(r'[\u2e80-\u9fff\u3000-\u303f\uff00-\uffef]',ch))


def font_for(ch):return 'Kai' if chinese(ch) else 'Times'


def measure(text,size):return sum(pdfmetrics.stringWidth(ch,font_for(ch),size) for ch in text)


def runs_for(text,bold=False,label=None):
    runs=[]
    for i,ch in enumerate(text):
        font='Kaiti SC' if chinese(ch) else 'Times New Roman'
        weight=bold or (label is not None and i<len(label))
        if runs and runs[-1]['font']==font and runs[-1]['bold']==weight:runs[-1]['text']+=ch
        else:runs.append({'text':ch,'font':font,'bold':weight})
    return runs


def make_scene():
    boxes=[];arrows=[]
    def p(text,label=None,size=27,bold=False,color=None,after=4):
        return {'text':text,'size':size,'runs':runs_for(text,bold,label),'color':color or C['ink'],'after':after}
    def card(name,x,y,w,h,title,rows,fill,accent):
        paras=[p(title,size=32,bold=True,color=accent,after=12)]
        paras.extend(p(text,label=label,size=size) for label,text,size in rows)
        boxes.append({'name':name,'x':x,'y':y,'w':w,'h':h,'fill':fill,'stroke':C['rule'],
                      'accent':accent,'inset':20,'paragraphs':paras})
    def plain(name,x,y,w,h,text,size,bold=False,color=None,fill='none'):
        boxes.append({'name':name,'x':x,'y':y,'w':w,'h':h,'fill':fill,'stroke':'none','inset':0,
                      'paragraphs':[p(text,size=size,bold=bold,color=color,after=0)]})
    def arrow(name,points,color=None):arrows.append({'name':name,'points':points,'color':color or C['ink'],'width':2.8})

    plain('title',50,26,1820,64,'调查约束下的家庭通胀预期模拟',46,True)
    plain('subject',50,94,1820,44,'研究对象：纽约联储消费者预期调查（SCE）中，居民对未来12个月的通胀判断',29)
    plain('theory',50,154,1820,52,'设计依据：信念持续性　｜　有限注意　｜　生活价格体验',30,True,C['gray'],C['light'])

    card('population',50,228,570,400,'01 人群画像与原有信念 P',[
        ('网格化：','网格化：学历×数理×年龄×收入',27),
        ('抽样：','抽样：小群体多抽，按人口比例加权',27),
        ('历史重建：','历史重建：本人过往回答；缺失时',27),
        (None,'　匹配近期相似家庭的过去回答',27),
        ('模拟预测：','模拟预测：历史画像＋公开预期校准',27),
        ('合成属性：','合成属性：支出结构、采购责任、',27),
        (None,'　对美联储主席的信心',27),
        ('购买频率：','购买频率：开发期已检验，主配置未采用',26),
    ],C['p'],C['blue'])
    card('environment',50,635,570,345,'02 个人可见环境 E',[
        ('价格：','价格：官方食品CPI总项与分项',27),
        ('新闻：','新闻：纽约时报；随机4/8/16/32篇',27),
        ('路由：','路由：通胀相关文章抽样权重×1.5',27),
        ('匹配：','匹配：采购责任决定价格信息广度',27),
        ('政策：','政策：公开政策消息与美联储动态',27),
        ('时间：','时间：仅保留个人截止前公开的信息',27),
    ],C['e'],C['orange'])
    card('behavior',690,358,320,390,'03 问卷行为 B',[
        ('模型：','模型：DeepSeek V3.2',27),
        ('服务：','服务：SiliconFlow FP8',26),
        ('温度：','温度：0.5；关闭思考',27),
        ('格式：','格式：JSON',27),
        ('上限：','上限：1024输出token',26),
        ('期限：','期限：未来12个月',27),
        ('Q8：','Q8：点预期',28),
        ('Q9：','Q9：十档概率',28),
    ],C['white'],C['blue'])
    card('aggregation',1080,228,360,502,'04 指标计算',[
        ('Q9计分：','Q9计分：十档→连续密度',27),
        (None,'　→个人密度均值',27),
        ('汇总：','汇总：人口加权中位数',27),
        ('Q8：','Q8：点预期独立汇总',27),
        ('扩展：','扩展：经验贝叶斯（τ=8）',27),
        (None,'　按相似家庭答卷补足人数',26),
        ('组合：','组合：已公布预期＋本期模拟',26),
        (None,'　原始与组合指标分别报告',26),
    ],C['white'],C['blue'])
    card('evaluation',1510,228,360,502,'05 模拟效果评估',[
        ('总体：','总体：MAE / RMSE / 偏差',27),
        ('微观：','微观：W1 / IQR',27),
        (None,'　用于历史重建中的比较',26),
        ('基线：','基线：照抄上期预期',27),
        (None,'　同结构SCE＋CPI模型',26),
        ('原则：','原则：同人群、同计分方法',26),
        ('近期：','近期：只评价全国误差',26),
        ('真值：','真值：仅进入事后评价',26),
    ],C['light'],C['gray'])
    card('extensions',1080,795,790,200,'06 动态更新与经济用途',[
        ('月度：','月度：个人模拟信念逐月传递，检查误差累积',27),
        ('周度：','周度：周期内传递，新SCE公布后校准先验',27),
        ('应用：','应用：月度模拟指标用于信贷等经济变量预测',27),
    ],C['light'],C['gray'])

    arrow('P-to-B',[[620,420],[655,420],[655,448],[690,448]],C['blue'])
    arrow('E-to-B',[[620,800],[655,800],[655,642],[690,642]],C['orange'])
    arrow('B-to-index',[[1010,535],[1080,535]])
    arrow('index-to-evaluation',[[1440,535],[1510,535]])
    arrow('index-to-extension',[[1260,730],[1260,795]])
    arrow('extension-to-evaluation',[[1690,795],[1690,730]],C['gray'])
    plain('scope-note',50,1000,1820,32,'资料范围：总体CPI、就业、汽油等序列用于数据准备或统计对照，并非全部输入模型。',25,color=C['gray'])
    plain('time-note',50,1038,1820,32,'时间边界：历史重建与近期回测分别报告；近期人口及先验按月准备，个人日期进一步限制环境。',25,color=C['gray'])
    return {'schema':'sce_overview_native_boxes/v2','width':W,'height':H,'chinese_font':'Kaiti SC','latin_font':'Times New Roman',
            'boxes':boxes,'arrows':arrows,'title':'调查约束下的家庭通胀预期模拟',
            'notes':'用户指定中文楷体、英文和数字Times New Roman。七个方法框的正文均为方框自身文本，非覆盖小文本框。最终主提示含合成CE支出、采购责任、联储主席信心、食品CPI、新闻和政策；购买频率为已试验未采用字段，其他宏观表不冒充实际输入。目标期真值只进评价。近期为回顾性模拟。'}


def layout_box(box):
    width=box['w']-2*box['inset'];y=box['y']+box['inset'];lines=[]
    for para in box['paragraphs']:
        size=para['size'];current='';off=0
        for ch in para['text']:
            if current and measure(current+ch,size)>width:
                lines.append({'text':current,'offset':off,'para':para,'x':box['x']+box['inset'],'y':y})
                off+=len(current);current='';y+=size*1.18
            current+=ch
        if current:
            lines.append({'text':current,'offset':off,'para':para,'x':box['x']+box['inset'],'y':y})
            y+=size*1.18
        y+=para['after']
    return lines,y


def line_runs(line):
    para=line['para'];a=line['offset'];b=a+len(line['text']);offset=0;out=[]
    for run in para['runs']:
        end=offset+len(run['text'])
        start=max(a,offset);stop=min(b,end)
        if stop>start:out.append({**run,'text':run['text'][start-offset:stop-offset]})
        offset=end
    return out


def arrow_tip(points):
    x0,y0=points[-2];x,y=points[-1];a=math.atan2(y-y0,x-x0)
    return [(x,y),(x-12*math.cos(a)+5*math.sin(a),y-12*math.sin(a)-5*math.cos(a)),(x-12*math.cos(a)-5*math.sin(a),y-12*math.sin(a)+5*math.cos(a))]


def render(scene,out):
    scale=180*72/25.4/W
    c=Canvas(str(out/'sce_framework_paper_v2.pdf'),pagesize=(W*scale,H*scale),pageCompression=1)
    c.setTitle(scene['title']);c.setAuthor('水上挽月');c.scale(scale,scale)
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="180mm" height="101.25mm" viewBox="0 0 {W} {H}">',f'<title>{escape(scene["title"])}</title>',f'<rect width="{W}" height="{H}" fill="white"/>']
    fits=[]
    for arrow in scene['arrows']:
        p=c.beginPath();p.moveTo(arrow['points'][0][0],H-arrow['points'][0][1]);c.setStrokeColor(HexColor(arrow['color']));c.setLineWidth(arrow['width'])
        for x,y in arrow['points'][1:]:p.lineTo(x,H-y)
        c.drawPath(p);pts=arrow_tip(arrow['points']);p=c.beginPath();p.moveTo(pts[0][0],H-pts[0][1])
        for x,y in pts[1:]:p.lineTo(x,H-y)
        p.close();c.setFillColor(HexColor(arrow['color']));c.drawPath(p,fill=1,stroke=0)
        svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in arrow["points"])}" fill="none" stroke="{arrow["color"]}" stroke-width="{arrow["width"]}"/>')
        svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in pts)}" fill="{arrow["color"]}"/>')
    for box in scene['boxes']:
        if box['fill']!='none':
            c.setFillColor(HexColor(box['fill']));c.setStrokeColor(HexColor(box['stroke']) if box['stroke']!='none' else HexColor(box['fill']));c.setLineWidth(1.4)
            c.rect(box['x'],H-box['y']-box['h'],box['w'],box['h'],fill=1,stroke=box['stroke']!='none')
            svg.append(f'<rect id="{box["name"]}-frame" x="{box["x"]}" y="{box["y"]}" width="{box["w"]}" height="{box["h"]}" fill="{box["fill"]}" stroke="{box["stroke"]}" stroke-width="1.4"/>')
        lines,end=layout_box(box);fits.append({'name':box['name'],'content_bottom':round(end,2),'box_bottom':box['y']+box['h']-box['inset'],'fits':end<=box['y']+box['h']-box['inset']})
        svg.append(f'<text id="{box["name"]}-text">')
        for line in lines:
            p=line['para'];size=p['size'];x=line['x'];baseline=H-line['y']-size*.87
            svg.append(f'<tspan x="{x}" y="{line["y"]+size*.87}" font-size="{size}" fill="{p["color"]}">')
            for run in line_runs(line):
                fn='Kai' if run['font']=='Kaiti SC' else 'Times';value=run['text'];c.saveState();c.setFillColor(HexColor(p['color']));c.setFont(fn,size);t=c.beginText(x,baseline)
                if run['bold']:c.setLineWidth(.38);c.setStrokeColor(HexColor(p['color']));t.setTextRenderMode(2)
                t.textOut(value);c.drawText(t);c.restoreState();x+=pdfmetrics.stringWidth(value,fn,size)
                svg.append(f'<tspan font-family="{run["font"]}" font-weight="{700 if run["bold"] else 400}">{escape(value)}</tspan>')
            svg.append('</tspan>')
        svg.append('</text>')
    c.showPage();c.save();svg.append('</svg>');(out/'sce_framework_paper_v2.svg').write_text('\n'.join(svg)+'\n')
    return fits


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise SystemExit('Use a fresh output folder.')
    pdfmetrics.registerFont(TTFont('Kai',str(KAI)));pdfmetrics.registerFont(TTFont('Times',str(TIMES)))
    a.out.mkdir(parents=True);scene=make_scene()
    (a.out/'scene.json').write_text(json.dumps(scene,ensure_ascii=False,indent=2)+'\n')
    fits=render(scene,a.out);(a.out/'text_fit.json').write_text(json.dumps(fits,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(fits,ensure_ascii=False,indent=2))
    if any(not r['fits'] for r in fits):raise SystemExit(2)


if __name__=='__main__':main()
