"""Refresh the existing 16:9 PDF/HTML briefing from frozen aggregate evidence.

No model calls, raw microdata processing, Q9 refits or independent Kimi audit.
Reuses the previous report's typesetting primitives without modifying it.
"""
from pathlib import Path
import base64
import hashlib
import html
import json
import re
import shutil
import sys

import render_sce_progress_report as prior
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "docs/reports/20261019"
BUILD = ROOT / "outputs/sce_progress_report_20261019_v1"
PDF = DEST / "SCE项目进展汇报_20261019.pdf"
HTML = DEST / "index.html"
SOURCES = {
    "overview": "docs/DESIGN.md",
    "configuration": "docs/CURRENT_SIMULATION_CONFIGURATION.md",
    "experiments": "docs/EXPERIMENT_STATUS_20261018.md",
    "scaleup": "docs/workstreams/20261017_reference_scaleup/results_summary.json",
    "scaleup_report": "docs/workstreams/20261017_reference_scaleup/results.md",
    "gap_report": "docs/workstreams/20261018_response_gap/results.md",
    "news": "docs/workstreams/20261018_targeted_mechanisms/news_breadth_results_v1/summary.json",
    "news_report": "docs/workstreams/20261018_targeted_mechanisms/news_breadth_results_20261019.md",
    "atus": "docs/workstreams/20261018_targeted_mechanisms/atus_sce_matching_results_20261019.md",
    "kimi": "docs/workstreams/20261019_updating_facts/README.md",
    "kimi_summary": "outputs/sce_updating_facts_20261019_v1/analysis_summary.json",
    "attention_literature": "docs/literature/sce/information_exposure/news_attention_demographics_20261019.md",
    "prior_web_check": "docs/sources/sce_progress_report_planning_20261015.json",
    "prior_renderer": "scripts/render_sce_progress_report.py",
}
TEAL, GOLD, INK, MUTED, PALE, LINE, RED = prior.TEAL, prior.GOLD, prior.INK, prior.MUTED, prior.PALE, prior.LINE, prior.RED


class Page(prior.Page):
    def para(self,x,y,s,w,size=22,leading=None,color=INK):
        leading=leading or size*1.50
        closing=set('，。；：！？、）》】”’%')
        for paragraph in str(s).split('\n'):
            tokens=re.findall(r'[A-Za-z0-9][A-Za-z0-9_.,/%+()=<>:–-]*|\s+|.',paragraph)
            line=''
            for token in tokens:
                if prior.text_width(line+token,size)<=w:
                    line+=token
                    continue
                # Keep Chinese closing punctuation with the preceding character.
                if token and token[0] in closing and line:
                    tail=line[-1:]; head=line[:-1]
                    if head:self.text(x,y,head.rstrip(),size,color);y+=leading
                    line=tail+token
                else:
                    if line:self.text(x,y,line.rstrip(),size,color);y+=leading
                    line=token.lstrip()
            if line:self.text(x,y,line,size,color);y+=leading
        if y>650:raise ValueError(f'Page {self.number}: paragraph exceeds body')
        return y

    def image_path(self, path, x, y, w, h):
        raw = path.read_bytes()
        img = ImageReader(str(path))
        iw, ih = img.getSize()
        ratio = min(w / iw, h / ih)
        dw, dh = iw * ratio, ih * ratio
        dx, dy = x + (w - dw) / 2, y + (h - dh) / 2
        self.doc.drawImage(img, dx, 720-dy-dh, dw, dh, mask="auto")
        encoded = base64.b64encode(raw).decode()
        self.svg.append(f'<image href="data:image/png;base64,{encoded}" x="{dx}" y="{dy}" width="{dw}" height="{dh}"/>')

    def finish(self):
        self.line(56, 657, 1224, 657, LINE)
        self.text(56, 668, self.source, 12, MUTED)
        self.text(56, 692, "水上挽月  |  SocioVerse Challenge 2026  |  截至2026.10.19", 11, MUTED)
        self.text(1125, 691, ("附录 " if self.appendix else "") + f"{self.number:02}", 13, TEAL)
        self.doc.showPage()
        self.doc._report_pages.append({"number": self.number, "title": self.title,
            "section": self.section, "svg": "".join(self.svg), "text": self.plain[:],
            "source": self.source, "appendix": self.appendix})

    def bars(self, labels, values, colors, x, y, w, h, xmax=None, unit="pp", fmt=".3f"):
        xmax = xmax or max(values) * 1.2
        step = h / len(labels)
        label_w = 135
        for n, (label, value, color) in enumerate(zip(labels, values, colors)):
            yy = y + n * step
            self.text(x, yy + 4, label, 20, INK)
            length = (w-label_w-88) * value / xmax
            self.rect(x+label_w, yy+3, length, 23, color)
            self.text(x+label_w+length+10, yy+3, f"{value:{fmt}}", 20, color)
        self.text(x+label_w, y+h+4, unit, 16, MUTED)

    def line_plot(self, labels, series, x=106, y=238, w=1055, h=260, ymax=8):
        for tick in range(ymax+1):
            yy = y+h-h*tick/ymax
            self.line(x, yy, x+w, yy, LINE, .55)
            self.text(x-35, yy-8, str(tick), 17, MUTED)
        self.text(x-43, y-29, "%", 18, MUTED)
        dx = w / max(1, len(labels)-1)
        for n, lab in enumerate(labels):
            self.text(x+n*dx-24, y+h+16, lab, 16, MUTED)
        cursor = x
        for title, vals, color in series:
            self.line(cursor, y-42, cursor+28, y-42, color, 3)
            self.text(cursor+36, y-53, title, 19, color)
            cursor += 245
            points = [(x+i*dx, y+h-float(v)/ymax*h) for i,v in enumerate(vals)]
            for a,b in zip(points,points[1:]):self.line(*a,*b,color,2.8)
            for xx,yy in points:self.rect(xx-3,yy-3,6,6,color)


def read(name):
    return json.loads((ROOT / SOURCES[name]).read_text())


def assemble():
    if (PDF.exists() or HTML.exists()) and '--revise-draft' not in sys.argv:
        raise SystemExit("Refusing to overwrite an existing briefing; use a new version directory.")
    DEST.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    scale, news, kimi = read("scaleup"), read("news"), read("kimi_summary")
    all_m = scale["scopes"]["all_months"]["model_metrics_equal_month_repeat_cells"]
    all_b = scale["scopes"]["all_months"]["scalar_baselines_equal_month_repeat_cells"]["copy_previous"]["metrics"]
    prior.OUT = ROOT / "outputs/sce_progress_report_20261015_v2"
    doc = canvas.Canvas(str(PDF), pagesize=(1280,720), pageCompression=1)
    doc.setTitle("美国居民通胀预期的Agent模拟：项目进展与研究计划")
    doc.setAuthor("水上挽月")
    doc.setSubject("SocioVerse Challenge 2026赛道A；2026年10月19日进展汇报")
    doc._report_pages = []
    return doc, scale, news, kimi, all_m, all_b


def add_content(doc, scale, news, kimi, all_m, all_b):
    old_assets = ROOT / "outputs/sce_progress_report_20261015_v2/assets"
    # 01
    p=Page(doc,1,"SocioVerse Challenge 2026 · Track A","美国居民通胀预期的Agent模拟",source="项目进展与研究计划 · 用于学术汇报和讨论 · 2026-10-19")
    p.text(58,192,"基于SCE的历史重建与机制检验",30,TEAL)
    p.para(58,267,"给定家庭处境、接触的信息与原有信念，\n能否同时重建总体预期和家庭之间的差异？",1110,30,48)
    p.line(58,404,1220,404,LINE)
    p.text(58,437,"当前阶段",21,GOLD)
    p.para(58,482,"已完成真实模拟及十二期扩大验证。\n工程流程已贯通，稳定超越基线的行为机制仍在研究。",1110,26,43)
    p.text(58,589,"水上挽月  ·  复旦大学  ·  2026年10月19日",21,MUTED)
    p.finish()
    # 02
    p=Page(doc,2,"01 · Survey background","SCE：纽约联储的消费者预期调查","研究的是居民对未来12个月物价变化的判断，不是直接预测下一月实际CPI。","来源：纽约联储SCE FAQ（2026-10-19核查）；微观资料与问卷。")
    p.table(["调查制度","具体情况"],[
        ("调查机构","美国纽约联邦储备银行（纽约联储）"),
        ("频率与起点","2013年6月启动，每月在线调查，月内分周收集"),
        ("对象与规模","约1,200名家庭户主；涉及家庭财务决策"),
        ("同一人参与多久","轮换面板，最多12个月；每月有人退出和加入"),
        ("公开时间","月度汇总通常次月公布；核心微观资料滞后9个月"),
        ("本项目研究的题目","Q8点预期；Q9十档概率，均针对未来12个月")
    ],[235,550],y=183,row_h=58,size=20)
    p.text(879,194,"为什么选择SCE",25,TEAL)
    p.para(879,245,"通胀预期影响消费、工资判断和政策传导。",330,23,36)
    p.para(879,365,"公开逐人概率回答和跨月记录，可以检验家庭差异及信念更新。",330,22,35)
    p.para(879,505,"总体指标和微观结构可以相互校验。",330,22,35)
    p.takeaway("真实调查每月约千人；本项目的192人是实验抽样规模，不是SCE调查本身的规模。")
    p.finish()
    # 03
    p=Page(doc,3,"02 · Research design","历史重建与未来预测的研究边界","当前主要结果属于A线：给定真实回访者画像与过去信念，重建本期回答。","项目A/B安排、十二期冻结协议；本期目标通胀答案只进评价层。")
    p.table(["比较维度","A  历史重建","B  未来预测"],[
        ("研究问题","已知历史条件下，能否还原该月回答与分布？","在结果公布前，能否预测下一期调查？"),
        ("人口与原有信念","可用后来公开的真实画像、本人过去问卷","只用截止前可得旧人口、合成人口与可用历史"),
        ("信息范围","可声明事后重建条件；现实验仍按历史窗口截断E","人口、E、参数和模型时间边界均须符合事前条件"),
        ("目前完成情况","已完成多轮条件模拟和十二期检验","新加入者初始化、信念递推和误差累积尚未验收")
    ],[205,482,481],y=184,row_h=76,size=20)
    p.para(65,563,"当前每个月补入真人上期回答，不能称为Agent连续十二个月自主预测。",1120,22,32)
    p.takeaway("A也需要独立检验；若使用某项历史结果作校准，就不能再用同一项证明预测成功。")
    p.finish()
    # 04
    p=Page(doc,4,"03 · SocioVerse workflow","项目架构与各环节进度","研究遵循B=f(P,E)：居民处境与信息环境共同影响回答；模型如何理解信息也需要检验。","来源：项目总纲、实验流程与当前配置；官方SocioVerse2引擎＋本项目准备和评价模块。")
    p.table(["研究环节","已经实现","主要缺口"],[
        ("Literature / Study","价格体验、信念更新等综述；A/B边界与对照","理论需转成可检验机制"),
        ("Population","真实画像、本人历史、CE与信心合成","新入组者与合成属性的联合关系"),
        ("Environment / Dataset","价格、新闻、政策归档；106个月微观资料","个人实际接触与历史版本证据"),
        ("Simulation / Trajectory","官方引擎真实LLM运行；保存消息、失败和用量","尚未形成稳定优于基线的配置"),
        ("Analysis","同支持评价、分组、跨期与过去信息基线","独立月份检验与B路线递推"),
        ("Reports","开题已提交，实验台账与复算入口齐备","最终研究报告、研究包和演示")
    ],[260,465,443],y=184,row_h=62,size=20)
    p.takeaway("流程能够运行和结果有效是两个标准：工程基础已具备，经验有效性仍是当前重点。")
    p.finish()
    # 05
    p=Page(doc,5,"04 · Population","居民画像、原有信念与合成补充","当前从SCE真实回访者中抽样；真实测量与外部合成字段分别标记。","来源：SCE原问卷和微观资料、CE供体、Gallup信心分布；合成字段不是本人实测。")
    p.table(["信息层","当前输入","设计目的及限制"],[
        ("实测人口特征","年龄组、教育、收入档、地区/州、住房、就业、数理标签","刻画家庭处境；标签不等于行为已真实实现"),
        ("本人过去信念","真实上期Q8点值和Q9十档；更早均值与有效次数","保留个人位置；短历史与无历史者需另设规则"),
        ("合成消费结构","按外部CE同类家庭分配四类支出占比","提供生活背景；不是该受访者的真实购物篮子"),
        ("合成美联储信心","依据外部调查分布分配的态度标签","描述政策理解背景；不能视为本人已测信任")
    ],[220,470,478],y=183,row_h=76,size=21)
    p.para(65,548,"十二期采用年龄×收入分层；评价使用调查权重÷入样概率。模型不接收原始ID、权重或本期通胀答案。",1120,21,31)
    p.takeaway("当前实验覆盖有上期回答的回访者，不能直接代表新加入者或全国全部家庭。")
    p.finish()
    # 06
    p=Page(doc,6,"05 · Environment","从公共资料到每个家庭接触的信息","参考输入包含公开价格、趋势、政策及新闻；“信息已公开”仍不等于“每个人都看过并理解”。","来源：BLS首发稿、EIA汽油、NYT Archive、政策事实和Event MCP核查。")
    p.table(["组成","当前做法","需要改进的地方"],[
        ("价格与趋势","CPI、就业、汽油等；保留单位、参考期和发布日","完整统计表可能让不同家庭都获得同样宏观信号"),
        ("新闻","粗筛＋LLM分类；标题和摘要，重复文本只呈现一次","NYT不是所有居民实际使用的媒体；主题覆盖不均"),
        ("个体分配","参考为3篇共同新闻＋5篇个人新闻；50/50混合抽取","50/50是抽取概率，不是每人恰好一半相关新闻"),
        ("时间与版本","通常截至目标月CPI首发日当天结束（纽约时间）","这是月中参照截点，不等于每位真人的作答日")
    ],[205,475,488],y=184,row_h=76,size=20)
    p.para(65,548,"USTR贸易与消费者处境资料已做小试；Google Trends、Household Pulse等仍需核可得性与历史版本。",1120,21,31)
    p.takeaway("下一步重点不是继续增加资料总量，而是检验家庭角色如何改变接触的类别和详细程度。")
    p.finish()
    # 07
    p=Page(doc,7,"06 · Behavior / prompt","Agent收到什么，如何形成问卷回答","以下为压缩示意，所有数字均为虚构值；实际运行使用完整问卷和冻结消息。","依据实际提示结构改写示意；示意值不是真人记录，不是新增模拟结果。")
    p.text(60,184,"输入示意",24,TEAL)
    p.rect(58,225,710,320,PALE)
    p.para(80,245,"你的处境：40–59岁、大学教育、租房、全职就业。\n原有信念：上月点预期4%；同时保留上月十档概率。\n更早记录：已回答5次，历史平均预期约3.5%。\n本期信息：截至指定日已发布的价格趋势、政策和8篇新闻。\n这是你原有的判断；可结合后来获得的信息调整，也可保持。",665,22,39)
    p.text(825,184,"输出要求",24,TEAL)
    p.para(825,241,"Q8：未来12个月物价变化的点预测。",375,23,37)
    p.para(825,348,"Q9：向10个通胀/通缩区间分配概率，非负、合计100%。",375,23,37)
    p.para(825,480,"直接填写本期答案；不让模型提交概率差值。",375,22,35)
    p.takeaway("保留先验并不等于模型会充分保留个人差异；它实际如何使用输入，要看对照结果。")
    p.finish()
    # 08
    p=Page(doc,8,"07 · Simulation / trajectory","真实运行规模与可复现记录","核心模拟使用官方SocioVerse2引擎；本项目开发输入准备、机制适配、计分和评价。","来源：十二期执行收据、六期新闻量执行记录；费用为token估算，非独立账单。")
    p.table(["已执行批次","规模与覆盖","实际执行"],[
        ("十二期扩大验证","2020—2025每年2个月；192人/月；生成2遍","4,608请求；4,606有效；估$5.155；约24分钟"),
        ("六期新闻量对照","6个月×96人；3组；各生成2遍","3,456请求；3,454有效；估$3.860；约19分钟"),
        ("其他机制小试","先验、认知、财务、心理、经历、价格信息等","按各批同样本对照解释，不把不同批次拼成成绩")
    ],[250,455,463],y=184,row_h=77,size=20)
    p.text(60,458,"共同运行设置",24,TEAL)
    p.para(60,502,"DeepSeek官方Flash；温度0.5，关闭思考，无自动重试。保存输入、原始回复、非法回答、种子、模型回包指纹与用量。可复用已有轨迹重算，无需再次付费。",1150,22,34)
    p.takeaway("当前模型为可变别名：记录实际回包和指纹，不将别名等同于永久固定的模型版本。")
    p.finish()
    # 09
    p=Page(doc,9,"08 · Evaluation","评价总体水平、家庭差异和跨月变化","主指标始终与同一批真人、同一月份及同一权重比较；Q8与Q9分别报告。","统一评价口径：个人Q9密度均值→跨人设计加权中位数→逐月/遍绝对误差→等权平均。")
    p.table(["评价对象","指标及直观含义","比较基准"],[
        ("总体预期水平","中位数MAE（pp）；越低越好，先逐月算误差再平均","当前A线：照抄同一本人上期问卷"),
        ("家庭之间的差异","W1：整条分布相距多远；IQR：中间一半人的跨度","同样本真人分布；IQR不是越大越好"),
        ("同一个人的变化","更新分布距离、变化方向、保持比例、秩序保留","对应真人相邻月变化"),
        ("个人主观不确定性","一个人Q9内部的概率宽度、零值和刻度","区别于跨人分歧；不与人际IQR混用")
    ],[225,520,423],y=184,row_h=76,size=20)
    p.para(65,548,"Q9用同一冻结近似计分器；分位数采用加权经验CDF左逆。它与官方插值中位数及headline不完全相同。",1120,21,31)
    p.takeaway("总体接近是有效性的门槛；还原微观差异与更新，才是Agent方法需要另外证明的价值。")
    p.finish()
    # 10
    p=Page(doc,10,"09 · Main validation","十二期扩大验证：仍未稳定优于持续性基线","每期192人、两遍生成；主口径是模型与同一批真人Q9中心的差距。","来源：2026-10-17十二期冻结评价。图为两遍中心均值；MAE先逐遍计算，不由均值曲线重算。")
    months=sorted({c['month'] for c in scale['cells']})
    grouped={m:[c for c in scale['cells'] if c['month']==m] for m in months}
    actual=[sum(c['matched_sample_truth_center_pp'] for c in grouped[m])/2 for m in months]
    model=[sum(c['simulated_center_pp'] for c in grouped[m])/2 for m in months]
    carry=[sum(c['matched_sample_truth_center_pp']+c['scalar_baseline_metrics_same_sample']['copy_previous']['q9_center_bias_pp'] for c in grouped[m])/2 for m in months]
    p.line_plot([str(m)[2:4]+'.'+str(m)[4:] for m in months],[("真人",actual,INK),("Agent",model,TEAL),("照抄本人上期",carry,GOLD)],y=244,h=253,ymax=8)
    p.text(70,548,f"全部12期 MAE：Agent {all_m['q9_center_mae_pp']:.3f} / 照抄 {all_b['q9_center_mae_pp']:.3f} pp",24,TEAL)
    p.text(775,548,"新增8期：0.539 / 0.277 pp",24,RED)
    p.takeaway("旧4期扩大人数后MAE为0.300；主要退步来自新增时期，说明早期好结果未稳定推广。")
    p.finish()
    # 11
    p=Page(doc,11,"10 · Microstructure","微观差距：个人差异被压缩，更新对象没有区分好","十二期诊断发现：真人基本保持时模型常改动；真人大幅调整时模型又改得不够。","来源：十二期主评价及2026-10-18回复差距诊断；按本期真实变化分组，仅用于事后定位。")
    p.text(60,187,"跨人的预期跨度（IQR）",24,TEAL)
    p.bars(["真人","Agent","照抄上期"],[5.055,2.424,all_b['cross_person_iqr_pp']],[INK,TEAL,GOLD],60,245,510,210,xmax=6,fmt=".2f")
    p.text(680,187,"相对上月的平均绝对变化（pp）",24,TEAL)
    p.table(["真人事后分组","真人","Agent"],[
        ("基本保持（≤0.5pp）","0.117","2.553"),
        ("上调者","4.368","2.346"),
        ("下调者","4.567","2.602")
    ],[290,115,115],x=680,y=235,row_h=62,size=20)
    p.para(65,510,"十二期分布W1：Agent 2.434，照抄0.873pp。共同中心接近不能掩盖完整分布仍有较大差距。",1130,22,33)
    p.takeaway("不能用本期真人属于哪组来选择预测方法；需要检验过去资料能否事前区分保持和更新。")
    p.finish()
    # 12
    p=Page(doc,12,"11 · Mechanism experiments","机制实验的收获与取舍","沿用某项配置不代表它已单独验证有效；不同批次的最低误差不能相加。","来源：实验台账；原有各批真实对照及后续跨月复查，详附录配置和证据。")
    p.table(["方向","得到的信息","当前处理"],[
        ("本人过去信念、时间说明","部分改善水平或分布；个人位置仍保留不足","保留A线工作参考，继续检验持续性"),
        ("政策事实＋合成央行信心","早期四期中心误差有下降，微观差异仍小","保留参考；合成态度非本人实测"),
        ("数理实答、Q1/Q2财务信息","局部人群或指标改善，未形成跨期整体收益","不叠加为默认；保留得失与复算"),
        ("心理、历史经历、频率说明","现有匹配/文字注入未稳定改善主指标","暂缓实现；不否定机制本身"),
        ("概率映射、差值作答","取整改善外观；差值出现大量非法概率","默认直接回答，不以格式改善冒充拟合成功")
    ],[290,495,383],y=181,row_h=73,size=19)
    p.takeaway("目前较清楚的经验是：增加标签和更多背景，不能自动恢复个人经历、信念与信息的真实关系。")
    p.finish()
    # 13
    p=Page(doc,13,"12 · News exposure","差异化新闻量：有积极信号，人口匹配未显示增量","六期96人、三组各两遍。随机和人口匹配使用相同3/8/20篇名额：48/28/20人。","来源：2026-10-19新闻量试验；571共同人月。六期为已探索月份，不称独立盲测。")
    p.text(60,186,"同支持群体中位数MAE",24,TEAL)
    keys=['carry','baseline','news_matched','news_randomized']
    p.bars(["照抄上期","人人8篇","人口匹配","随机分配"],[news['weighted_metrics'][k]['center_mae_pp'] for k in keys],[GOLD,INK,'#7695ab',TEAL],60,244,555,250,xmax=.5)
    p.text(690,187,"如何理解结果",24,TEAL)
    p.para(690,241,"随机组0.339pp，低于同批照抄0.369；但只在3/6个月胜出，去掉部分月份后优势反转。",515,22,35)
    p.para(690,374,"人口匹配0.354，未胜随机；分布W1和人际跨度没有同步改善，未通过预登记筛选。",515,22,35)
    p.para(690,506,"完整统计表可能绕过新闻接触差异；这是待检解释。",515,21,32)
    p.takeaway("保留随机新闻量作验证候选；六期0.339不能替换十二期0.459，二者样本、时期与配置不同。")
    p.finish()
    # 14
    p=Page(doc,14,"13 · Human updating evidence","真人行为研究：为机制设计提供经验约束","Kimi基于2017—2025微观资料完成初步分析；本轮只引用交付，不复跑、不作独立验证。","来源：Kimi 2026-10-19报告与汇总；相邻月有效对103,630。以下为待复核的描述性发现。")
    p.table(["初步观察","报告中的量级","设计启发"],[
        ("有一部分人保持原答","十档完全不变：加权约15.4%","保留保持的可能，不要求每期必须调整"),
        ("变动有长尾","变动者绝对变化均值：加权约3.34pp","不能只用小幅、对称扰动代替所有更新"),
        ("概率表达较粗","非零概率约81%为5的倍数（非加权）","报告习惯需单列，但取整不是全部解释"),
        ("个人位置有持续性","至少6个有效月者，奇偶波个人均值相关约0.85","保留持久个人状态，避免每月重新抽一个人")
    ],[300,440,428],y=182,row_h=76,size=20)
    p.para(65,543,"这些是问卷层面的规律，可能混合真实信念、重复填法和测量误差；不能直接命名为注意力或心理因果参数。",1135,21,31)
    p.takeaway("F3a负斜率的经济解释、F3b的OLS/IV差异和类型分配，先列复核，不直接用于参数校准。")
    p.finish()
    # 15
    p=Page(doc,15,"14 · Next mechanism","下一项重点：家庭采购角色与可见价格信息","先把“谁接触哪些信息”做成可核查的对照，再判断它能否改善水平和微观分布。","依据：D’Acunto等JPE/PNAS（2021）价格接触与采购分工研究；ATUS—SCE原型尚未模拟。")
    p.text(60,187,"传导路径",25,TEAL)
    for xx,ww,title,body in [
        (60,260,"家庭结构","年龄、全住所人数、儿童状态"),
        (370,275,"采购承担程度","按ATUS同类家庭概率合成"),
        (695,260,"可见价格信息","调整食品/日用品的类别与细节")]:
        p.rect(xx,235,ww,130,PALE)
        p.text(xx+16,253,title,23,TEAL)
        p.para(xx+16,295,body,ww-32,20,29)
    p.text(335,278,"→",26,TEAL);p.text(660,278,"→",26,TEAL);p.text(980,278,"→",26,TEAL)
    p.para(1025,248,"未来12个月\n通胀预期",180,23,37)
    p.para(60,414,"已完成：六期576人月家庭核查，94.6%有可用过去家庭构成；采购角色与信息菜单原型已备。",1145,22,35)
    p.para(60,497,"下一步：核食品和日用品资料，固定新闻条件，比较角色匹配与同月打乱；避免完整宏观表掩盖个人菜单差异。",1145,22,35)
    p.takeaway("这是跨调查概率合成，不是识别出本人真实购物角色；宏观分类CPI也不冒充本人购物收据。")
    p.finish()
    # 16
    p=Page(doc,16,"15 · Plan and discussion","后续研究与需要讨论的问题","在最终交付前，优先完成一个有依据的机制对照，并保留完整的有效与无效结果。","工作顺序，非新付费授权；最终提交：2026-10-31 23:59北京时间，依据用户提供的组委会邮件。")
    p.table(["顺序","具体工作","完成标准"],[
        ("1  收束已有证据","复核Kimi关键解释；补角色—价格输入与未知处理","理论路径与资料范围清楚，不直接套回归系数"),
        ("2  固定一项对照","角色匹配/打乱，冻结月份、种子、模型及评价","先干跑；真实调用另确认范围和预算"),
        ("3  独立验证","在未参与该机制调整的时期检验中心与分布","同支持胜基线，报告区间和分组局限"),
        ("4  最终交付","研究报告、研究包、演示；B可执行性单独验收","明确时间边界、许可、实际成本与复现入口")
    ],[200,490,478],y=182,row_h=70,size=20)
    p.text(65,529,"希望讨论",22,TEAL)
    p.para(185,529,"如何提高相对过去信念的新信息增量？怎样区分真实信念与报告习惯？在时间约束下，哪项机制最值得验证？",1020,21,32)
    p.takeaway("若新机制仍不能稳定改善，应报告其失效边界与可复现证据，不将局部最低误差包装为成功。")
    p.finish()
    # Appendix A (17)
    p=Page(doc,17,"Appendix A · Configuration","关键实验配置与实际采用范围","“参考配置”用于保持各次对照可比，不表示其中每个模块都已单独证明有效。","来源：12期执行收据、6期新闻量协议、当前配置；所有费用均为token估算。")
    p.table(["项目","十二期参考验证","六期新闻接触对照"],[
        ("月份","2020-03/09；2021-03/09；2022-06/12；\n2023-06/12；2024-04/10；2025-03/09","2020-09；2021-09；2022-06；\n2023-12；2024-10；2025-03"),
        ("规模","192人/月；1组×2遍；4,608请求","96人/月；3组×2遍；3,456请求"),
        ("抽样和评价","年龄×收入分层；调查权重÷入样概率","固定旧样本，同支持按设计权重评价"),
        ("信息差异","3篇共同＋5篇个人新闻；完整统计","3/8/20篇；仍保留完整统计；未加ATUS角色"),
        ("共同参数","Flash、温度0.5、关闭思考、无重试","Flash、温度0.5、关闭思考、无重试"),
        ("有效率/模拟费用","4,606/4,608；约$5.155","3,454/3,456；约$3.860")
    ],[200,484,484],y=181,row_h=64,size=18)
    p.takeaway("生成两遍衡量输出随机性，不等于独立受访者翻倍；已外推的Normal人口也不算新增独立LLM样本。")
    p.finish()
    # Appendix B (18)
    p=Page(doc,18,"Appendix B · Statistics","Q8/Q9口径、比较对象与复现","Q8是点回答；Q9拟合个人连续密度后取均值。两者不能简单混合或互换。","来源：SCE原问卷与FAQ、冻结计分器、统一评价协议、十二期共同支持记录。")
    p.table(["口径问题","本项目处理"],[
        ("Q9如何形成总体中心","合法十档→同一冻结近似拟合→个人密度均值→设计加权中位数"),
        ("MAE如何跨期汇总","逐月、逐遍先算绝对误差，再对月份/遍等权平均；单位pp"),
        ("同支持与全国波次","12期同支持2,284/2,304人月；全国完整波次另报，不混用"),
        ("官方headline的差异","近似数值拟合及经验CDF左逆，不宣称完全复刻官方插值统计"),
        ("基线与后处理","A用本人上期；B用截止前最后公开指标；加权组合另列校准结果"),
        ("失败和复现","无效回答保留；固定种子、输入/代码哈希；旧轨迹可零API重算")
    ],[290,878],y=181,row_h=62,size=20)
    p.takeaway("不按测试答案挑权重、月份、种子或成功指标；探索性结果与独立验证分别报告。")
    p.finish()
    # Appendix C (19)
    p=Page(doc,19,"Appendix C · Pending review","Kimi六项发现与待复核内容","本页记录合作交付，不表示Codex已复算或认可所有解释；机制参数暂不据此冻结。","来源：Kimi 2026-10-19 README及analysis_summary；103,630相邻月有效对，具体子样本各不相同。")
    p.table(["发现","交付结果 / 覆盖","后续核查"],[
        ("F1 / F2 保持与变动","约15%完全保持；变动幅度有长尾","阈值、权重、取整与真实更新分别解释"),
        ("F3a 误差—修正回归","报告斜率−0.483；2017-02至2023-02","共享误差项、预测窗口和固定效应；补CPI是否必要"),
        ("F3b 均值回归","报告OLS约−0.43、IV约−0.05","工具有效性未定；两估计不能当可信区间端点"),
        ("F4 概率刻度","非零格约81%为5的倍数（非加权）","区分格子与人；刻度映射不等于恢复信念"),
        ("F5 持续差异","奇偶波个人均值相关约0.85","有限波次、选择样本与报告习惯的影响"),
        ("F6 行为类型","按更新频率、幅度和长期水平做聚类","探索性分类；须防全期信息回填及校准过拟合")
    ],[250,430,488],y=181,row_h=64,size=18)
    p.takeaway("负斜率不能单独证明居民过度反应；OLS/IV差异也不能直接决定均值回归的校准强度。")
    p.finish()
    # Appendix D (20)
    p=Page(doc,20,"Appendix D · Evidence / delivery","资料依据与最终交付要求","围绕社会科学价值、方法严谨性、可信结果及可复现工程组织报告。","来源：赛事官网已归档评分；用户提供的资助反馈邮件（2026-10-15）；原始来源详HTML资料链接。")
    p.table(["组委会关注点","目前已覆盖","最终还需落实"],[
        ("时间边界与模型知识","历史发布日期、版本与知识诊断记录","固定开发/验证/预测月；真值隔离与预测封存"),
        ("人群与跨期规则","分层权重、CE匹配、真实上期信念","Core/Normal扩展、新入组者与B自递推"),
        ("评价与基线","Q8/Q9分列；MAE、W1、IQR和分组诊断","独立时期、公平信息基线和稀疏组规则"),
        ("运行与可复现","官方引擎、种子/轨迹、干跑和旧轨迹重算","全项目调用/成本/耗时台账、干净环境验收"),
        ("许可与发布范围","原始微观不进Git；聚合证据可追溯","核各源许可；新闻/汽油历史版本未知则排除严格B")
    ],[270,420,478],y=180,row_h=58,size=19)
    p.para(65,535,"资料：纽约联储SCE、BLS/CE/ATUS；价格体验、经验学习、信息更新文献与ConsumerSim；各批冻结协议和聚合结果。",1130,20,29)
    p.takeaway("现有模型未稳定贴合历史SCE或未来CPI；这不能证明预训练知识无影响，严格预测仍需时间证据或事前封存。")
    p.finish()


def write_delivery(doc):
    doc.save()
    pages=doc._report_pages
    assert len(pages)==20 and sum(not p['appendix'] for p in pages)==16
    tnr=Path('/System/Library/Fonts/Supplemental/Times New Roman.ttf')
    cn=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    # Embed fonts and evidence images: the HTML remains usable when copied alone.
    fonts="".join(f"@font-face{{font-family:'{name}';src:url(data:font/ttf;base64,{base64.b64encode((BUILD/subset).read_bytes() if (BUILD/subset).exists() else path.read_bytes()).decode()}) format('truetype');font-weight:normal;font-style:normal}}" for name,path,subset in [('Kaiti SC',cn,'kaiti_subset.ttf'),('Times New Roman',tnr,'times_subset.ttf')])
    nav=''.join(f'<a href="#p{p["number"]}">{p["number"]:02} {html.escape(p["title"])}</a>' for p in pages)
    body=''.join(f'<section id="p{p["number"]}" aria-label="第{p["number"]}页 {html.escape(p["title"])}"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" role="img"><title>{html.escape(p["title"])}</title>{p["svg"]}</svg></section>' for p in pages)
    links=[('SCE官方FAQ','https://www.newyorkfed.org/microeconomics/sce/sce-faq'),('赛事官网','https://socioverse.fudan-disc.com/challenge/'),('价格体验研究','https://doi.org/10.1086/713192'),('购物角色研究','https://doi.org/10.1073/pnas.2008534118'),('经验学习研究','https://doi.org/10.1093/qje/qjv037'),('ConsumerSim','https://arxiv.org/abs/2606.30395')]
    references=' · '.join(f'<a href="{u}" target="_blank" rel="noreferrer">{n}</a>' for n,u in links)
    references+='<ul>'+''.join(f'<li><a href="../../{html.escape(str(Path(rel).relative_to("docs")))}">{html.escape(name)}：{html.escape(rel)}</a></li>' for name,rel in SOURCES.items() if rel.startswith('docs/') and name not in ['prior_renderer'])+'</ul>'
    css="""*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#e8efee;color:#18343d;font-family:'Times New Roman','Kaiti SC',serif}header{position:sticky;top:0;background:#18343d;color:white;padding:12px 22px;z-index:2;display:flex;align-items:center;gap:16px;flex-wrap:wrap}header strong{font-size:18px}header span{font-size:14px;color:#c7dbd9}button,header a{background:#edf5f4;color:#18343d;border:0;border-radius:4px;padding:7px 11px;font-family:inherit;font-size:15px;cursor:pointer;text-decoration:none}main{max-width:1440px;margin:24px auto;padding:0 18px}section{margin:0 auto 26px;background:white;box-shadow:0 3px 16px #18343d18;scroll-margin-top:85px}section svg{display:block;width:100%;height:auto}details{max-width:1400px;margin:20px auto;background:white;padding:14px 20px}nav{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:10px;margin:15px 0}nav a,footer a{color:#087f80;text-decoration:none;font-size:16px}footer{max-width:1400px;margin:25px auto 45px;padding:16px;color:#526970;overflow-wrap:anywhere}footer ul{line-height:1.8}body.present header,body.present details,body.present footer{display:none}body.present main{padding:0;margin:0;max-width:none}body.present section{display:none;margin:0;box-shadow:none;height:100vh;background:#18343d}body.present section.active{display:flex;align-items:center;justify-content:center}body.present svg{max-width:100vw;max-height:100vh}@page{size:landscape;margin:0}@media print{header,details,footer{display:none}body,main{margin:0;padding:0;background:white;max-width:none}section{box-shadow:none;margin:0;page-break-after:always;break-after:page}section svg{width:100%}}"""
    js="""let pages=[...document.querySelectorAll('section')],current=0;function show(i){current=Math.max(0,Math.min(pages.length-1,i));pages.forEach((p,j)=>p.classList.toggle('active',j===current))}document.querySelector('#present').onclick=()=>{current=Math.max(0,pages.findIndex(p=>p.getBoundingClientRect().bottom>90));document.body.classList.add('present');show(current)};document.addEventListener('keydown',e=>{if(!document.body.classList.contains('present'))return;if(['ArrowRight','PageDown',' '].includes(e.key)){show(current+1);e.preventDefault()}if(['ArrowLeft','PageUp'].includes(e.key)){show(current-1);e.preventDefault()}if(e.key==='Escape'){document.body.classList.remove('present');pages[current].scrollIntoView()}});"""
    HTML.write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SCE项目进展汇报 · 2026-10-19</title><style>'+fonts+css+'</style></head><body><header><strong>SCE项目进展汇报</strong><span>16页正文＋4页附录 · 2026.10.19</span><button id="present">演示模式</button><a href="'+html.escape(PDF.name)+'">下载PDF</a><button onclick="window.print()">打印</button><span>← →翻页，Esc返回</span></header><details><summary>逐页目录</summary><nav>'+nav+'</nav></details><main>'+body+'</main><footer><details><summary>资料与证据索引</summary>'+references+'</details><p>本稿更新已有结果与研究计划，不是新的模拟实验；Kimi交付标注为初步分析，未独立复跑。</p></footer><script>'+js+'</script></body></html>')
    (DEST/'汇报提纲.md').write_text('# SCE项目进展汇报 · 2026-10-19\n\n16页正文＋4页附录；中文楷体、英文数字Times New Roman。\n\n'+'\n\n'.join(f'## {p["number"]:02} {p["title"]}\n\n'+'\n\n'.join(p['text'][:-3])+'\n\n来源：'+p['source'] for p in pages)+'\n')
    ledger={name:{'path':rel,'sha256':hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()} for name,rel in SOURCES.items()}
    manifest={'date_beijing':'2026-10-19','main_pages':16,'appendix_pages':4,'pages':20,'new_api_calls':0,'new_q9_fits':0,'independent_kimi_audit':False,'source':ledger,'files':{p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in [PDF,HTML]},'fonts':{'chinese':'Kaiti SC','latin':'Times New Roman'},'status':'rendered_pending_visual_review'}
    (BUILD/'delivery.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (BUILD/'page_text.json').write_text(json.dumps([{k:v for k,v in p.items() if k!='svg'} for p in pages],ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'pdf':str(PDF),'html':str(HTML),'pages':len(pages),'new_api_calls':0},ensure_ascii=False))


if __name__=='__main__':
    doc,scale,news,kimi,all_m,all_b=assemble()
    add_content(doc,scale,news,kimi,all_m,all_b)
    write_delivery(doc)
