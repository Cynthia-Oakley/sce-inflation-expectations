"""Render the agreed progress briefing as PDF and a matching local HTML reader.

All content comes from existing aggregate evidence. PDF and HTML share the same
text, geometry and figures. No remote assets, tracking, model calls or new fits.
"""
from pathlib import Path
import hashlib
import html
import json
import re

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/sce_progress_report_20261015_v1"
SRC = ROOT / "studies/sce_inflation_expectations/reports/progress_20261015"
PDF = ROOT / "output/pdf/sce_progress_report_20261015_v1.pdf"
W, H = 1280, 720
INK, TEAL, GOLD, RED = "#18343d", "#087f80", "#aa762f", "#ad5950"
MUTED, LINE, PALE, BG = "#526970", "#d5e1e2", "#eef5f4", "#fafcfb"
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
pdfmetrics.registerFont(TTFont("CN", FONT_PATH))
pdfmetrics.registerFont(TTFont("Latin", "/System/Library/Fonts/Supplemental/Times New Roman.ttf"))


class Page:
    def __init__(self, doc, number, section, title, subtitle="", source="", appendix=False):
        self.doc, self.number, self.svg, self.plain = doc, number, [], []
        self.rect(0, 0, W, H, "#ffffff")
        self.rect(0, 0, 10, H, TEAL)
        self.text(56, 35, section.upper(), 15, TEAL)
        self.text(56, 72, title, 34)
        if subtitle:
            self.text(58, 119, subtitle, 18, MUTED)
        self.line(56, 155, 1224, 155, LINE)
        self.source = source
        self.appendix = appendix
        self.section, self.title = section, title

    def rect(self, x, y, w, h, fill, stroke=None, radius=0):
        self.doc.setFillColor(HexColor(fill))
        self.doc.setStrokeColor(HexColor(stroke or fill))
        if radius:
            self.doc.roundRect(x, H-y-h, w, h, radius, fill=1, stroke=bool(stroke))
        else:
            self.doc.rect(x, H-y-h, w, h, fill=1, stroke=bool(stroke))
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke or fill}"/>')

    def line(self, x1, y1, x2, y2, color=LINE, width=1):
        self.doc.setStrokeColor(HexColor(color)); self.doc.setLineWidth(width)
        self.doc.line(x1, H-y1, x2, H-y2)
        self.svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"/>')

    def text(self, x, y, s, size=22, color=INK, font="CN"):
        # y is the text top, keeping the HTML and PDF coordinate systems aligned.
        s = str(s)
        self.doc.setFont(font, size); self.doc.setFillColor(HexColor(color))
        self.doc.drawString(x, H-y-size*.90, s)
        family = "Arial Unicode MS,Arial,sans-serif" if font == "CN" else "Times New Roman,serif"
        self.svg.append(f'<text x="{x}" y="{y+size*.90}" font-size="{size}" font-family="{family}" fill="{color}">{html.escape(s)}</text>')
        self.plain.append(s)

    def para(self, x, y, s, w, size=22, leading=None, color=INK):
        leading = leading or size*1.50
        start = y
        for paragraph in s.split("\n"):
            tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.,/%+()=<>:–-]*|\s+|.", paragraph)
            line = ""
            for token in tokens:
                if pdfmetrics.stringWidth(line+token, "CN", size) <= w:
                    line += token
                else:
                    if line: self.text(x, y, line.rstrip(), size, color); y += leading
                    line = token.lstrip()
            if line: self.text(x, y, line, size, color); y += leading
        if y > 650:
            raise ValueError(f"page {self.number} paragraph overflow at {start}: {s[:40]}")
        return y

    def bullet(self, x, y, title, body, w=520, color=TEAL, size=21):
        self.rect(x, y+7, 5, 18, color)
        self.text(x+17, y, title, size, color)
        return self.para(x+17, y+size+12, body, w-17, size-1, color=INK)+17

    def image(self, name, x, y, w, h):
        p = OUT / "assets" / f"{name}.png"
        im = ImageReader(str(p)); iw, ih = im.getSize()
        scale = min(w/iw, h/ih); dw, dh = iw*scale, ih*scale
        dx, dy = x+(w-dw)/2, y+(h-dh)/2
        self.doc.drawImage(im, dx, H-dy-dh, dw, dh, mask="auto")
        self.svg.append(f'<image href="assets/{name}.svg" x="{dx}" y="{dy}" width="{dw}" height="{dh}"/>')

    def takeaway(self, s):
        self.rect(56, 592, 1168, 47, PALE)
        self.para(74, 603, s, 1132, 20, 27, TEAL)

    def table(self, headers, rows, widths, y=190, row_h=60, size=19, x=56):
        height = 42+row_h*len(rows)
        self.rect(x, y, sum(widths), 42, PALE)
        xp = x
        for head, width in zip(headers, widths):
            self.text(xp+12, y+10, head, size, TEAL); xp += width
        yy = y+42
        for row in rows:
            self.line(x, yy, x+sum(widths), yy)
            xp = x
            for cell, width in zip(row, widths):
                end = self.para(xp+12, yy+10, str(cell), width-24, size, size*1.3)
                if end > yy+row_h+3:
                    raise ValueError(f"page {self.number} table overflow: {cell}")
                xp += width
            yy += row_h
        self.line(x, yy, x+sum(widths), yy)
        xp = x
        for width in widths[:-1]:
            xp += width; self.line(xp, y, xp, y+height, LINE, .65)
        return yy

    def finish(self):
        self.line(56, 657, 1224, 657, LINE)
        self.text(56, 668, self.source, 12, MUTED)
        self.text(56, 692, "水上挽月  |  SocioVerse Challenge 2026  |  2026.10.15", 11, MUTED)
        self.text(1130, 691, ("附录 " if self.appendix else "")+f"{self.number:02}", 13, TEAL)
        self.doc.showPage()
        self.doc._report_pages.append({"number": self.number, "title": self.title,
                                       "section": self.section, "svg": "".join(self.svg),
                                       "text": self.plain})


def render():
    OUT.mkdir(parents=True, exist_ok=True); PDF.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads((SRC / "aggregate_data.json").read_text())
    doc = canvas.Canvas(str(PDF), pagesize=(W, H), pageCompression=1)
    doc.setTitle("美国居民通胀预期的Agent模拟 - SCE项目阶段性汇报")
    doc.setAuthor("水上挽月")
    doc.setSubject("SocioVerse Challenge 2026 赛道A；2026年10月15日研究进展")
    doc._report_pages = []

    p = Page(doc, 1, "SocioVerse Challenge 2026 · Track A", "美国居民通胀预期的Agent模拟", source="阶段性研究汇报 · 基于SCE的历史重建与方法验证 · 第一版")
    p.text(58, 186, "基于SCE的历史重建与方法验证", 30, TEAL)
    p.para(58, 255, "给定家庭特征、信息环境与既有信念，\nAgent能否生成接近真实调查的预期及其分布？", 1070, 30, 48)
    p.line(58, 392, 1220, 392, LINE)
    p.text(58, 426, "阶段判断", 19, GOLD)
    p.para(58, 466, "调查模拟流程已贯通。\n总体拟合与个人差异仍未达到稳定有效的标准。", 1110, 27, 44)
    p.text(58, 579, "水上挽月  ·  复旦大学  ·  2026年10月15日", 21, MUTED)
    p.finish()

    p = Page(doc, 2, "01 · Research question", "既要还原群体指标，也要解释家庭之间的差异", "SCE的一年期预期是居民对未来12个月物价变化的判断，与当期实际CPI不同。", "来源：NY Fed SCE公开月度指标（10/07归档）；SCE微观2022-06；官方FAQ。[1–2]")
    p.text(58, 180, "预期随经济环境变化", 23, TEAL)
    p.text(696, 180, "同一月份，家庭判断也不同", 23, TEAL)
    p.image("headline", 58, 218, 580, 287)
    p.image("real_distribution", 690, 218, 530, 287)
    p.para(70, 517, "官方全国指标：2020-01至2026-08\n已归档资料版，不代表官网当前最新一期。", 555, 16, 25, MUTED)
    p.para(704, 517, "真人2022-06，有效1,202条，官方派生值、调查权重。\n包含全部尾部；与后文实验样本及计分口径不同。", 510, 16, 25, MUTED)
    p.takeaway("聚合拟合是有效性门槛；家庭分布和更新，是Agent方法需要证明的额外价值。")
    p.finish()

    p = Page(doc, 3, "02 · Study", "历史重建与未来预测：使用不同的信息边界", "赛道A同时容纳两类任务；本项目当前证据主要来自历史条件重建。", "任务边界：项目A/B契约与已冻结八期协议；官网赛道A说明。[1]")
    p.text(58, 184, "A  历史重建：已实施", 25, TEAL)
    p.para(58, 229, "用已声明的历史家庭画像、本人过去回答与当时公开信息，重建该月调查。\n当前以回访者为对象，尚未推广到全国完整人口。", 1140, 23, 37)
    p.line(64, 329, 1200, 329, TEAL, 2)
    for x, a, b in [(80,"历史记录","画像 / 原有信念"),(435,"调查月 t","模拟Q8与Q9"),(900,"t 至 t+12个月","居民所判断的通胀窗口")]:
        p.rect(x, 323, 11, 11, TEAL); p.text(x, 350, a, 21); p.text(x, 380, b, 17, MUTED)
    p.text(58, 451, "B  未来预测：尚待独立验证", 25, GOLD)
    p.para(58, 494, "只用截止日可得资料预测下一调查月；以模拟自身的旧信念递推。\n需要另验新参与者初始化、输入发布时间、误差累积与模型知识边界。", 1140, 23, 37)
    p.takeaway("“预测哪一月的SCE”与“居民预测未来12个月通胀”，是两个不同的时间维度。")
    p.finish()

    p = Page(doc, 4, "03 · P / E / B", "P和E通过信息理解与信念更新，形成调查回答", "B = f(P, E)：研究的不只是输入，还包括普通居民怎样理解信息、保留经验和表达概率。", "参照官方CCI/PMI案例的调查—状态—回答—聚合流程；理论见[3–6]。连线为待验证设计假设。")
    boxes = [(58, 185, 330, "Population · 人群", "人口与家庭处境\n已有信念与认知答题\n实测信息和合成假设分开"),
             (438,185,350,"Environment · 环境","公开价格、趋势与事件\n家庭接触到的信息视图\n可公开不等于已经注意到"),
             (840,185,380,"Behavior · 行为","信息理解 → 保留或更新\n直接填写Q8与Q9\n个人密度 → 跨人聚合")]
    for x,y,w,title,body in boxes:
        p.rect(x,y,w,196,PALE,LINE); p.text(x+18,y+18,title,23,TEAL)
        p.para(x+18,y+66,body,w-36,21,34)
    p.text(400, 267, "+", 28, TEAL); p.text(803, 267, "→", 28, TEAL)
    p.text(58, 422, "三条可检验的经济学路径", 24)
    p.bullet(58, 468, "价格体验", "高频接触与显著性，可能改变居民关注哪些价格。", 350, size=20)
    p.bullet(458, 468, "原有信念", "过去经验与更新成本，可能使新信息只被部分吸收。", 350, size=20)
    p.bullet(858, 468, "认知与表达", "信息理解、主观不确定性与概率填法，需要分别研究。", 350, size=20)
    p.takeaway("把一个特征写进提示词，只代表完成输入；是否改变行为，仍须对照检验。")
    p.finish()

    p = Page(doc, 5, "04 · Project status", "基础链路已贯通，经验有效性仍是主要工作", "按SocioVerse研究流程梳理；“有交付”与“已证明有效”分开。", "项目清单与运行收据，截至2026-10-15；状态是本项目判断，不是赛事评分。")
    rows = [
        ("Literature review","价格体验、信念更新、概率认知已有综述","理论尚未全部转成有效机制"),
        ("Study","A/B边界、对照和时间范围已声明","B递推与全国代表性待验"),
        ("Population","实测画像、过去回答、合成属性已接入","人口更新与新加入者仍需补齐"),
        ("Environment","价格、新闻、政策与个人视图已构建","接触强度和理解机制待验证"),
        ("Dataset","106个月微观资料；来源及发布时间台账","各来源覆盖不同，不能视作全部同步"),
        ("Simulation","本地真实LLM已多轮运行","尚未稳定优于简单基线"),
        ("Trajectory","原始消息、回答、失败、用量可追溯","完整提交包独立验收待完成"),
        ("Analysis","同样本中心、分布、更新及基线评价","独立新时期与公平信息对照待扩大"),
        ("Reports","开题已提交；本次汇报与证据索引","最终论文、复现包、演示尚未成稿")]
    p.table(["研究环节", "已实现 / 已核验", "距离目标的缺口"], rows, [235, 470, 463], y=176, row_h=40, size=18)
    p.takeaway("项目已经能够开展可追溯的经验研究；当前仍处于机制筛选与模型诊断阶段。")
    p.finish()

    p = Page(doc, 6, "05 · Dataset", "每一种数据，都有明确用途和时间边界", "真实当期通胀答案只在评价层使用；历史重建与未来预测的可用人口信息不同。", "已归档来源：NY Fed、BLS、EIA、NYT Archive API、CE；数据清单及限制见附录C。")
    rows = [
        ("SCE微观 + 原问卷","人口、本人历史、真实回答与原始题意","2017-01至2025-10；106个月、130,216人月"),
        ("SCE官方月度指标","全国时间序列与外部统计口径核对","归档指标示例延伸至2026-08；不同于微观覆盖"),
        ("BLS首发新闻稿","CPI、就业及其他已核验宏观信号","按实际发布日期入窗；首发值与修订值分开"),
        ("EIA等公开价格资料","较及时的能源价格与家庭近期价格线索","仅在已取得历史时间证据的窗口使用"),
        ("NYT Archive API","公开事件背景、政策与家庭相关消息","粗筛 → LLM分类 → 家庭抽取；不等于实际阅读"),
        ("BLS CE / Diary","合成支出结构与分类购买日数的现实参考","供体家庭非SCE本人；跨年覆盖与发布时间有缺口")]
    p.table(["数据来源", "在项目中的用途", "覆盖与边界"], rows, [270, 420, 478], y=176, row_h=60, size=18)
    p.takeaway("历史发布稿控制外部信息前视；它不能消除LLM预训练中可能已有的历史知识。")
    p.finish()

    p = Page(doc, 7, "06 · Population", "家庭输入由三类信息组成，证据强弱不同", "以下为虚构说明例，不对应真实受访者。合成消费或信心标签不视为本人实测属性。", "SCE微观与问卷；CE供体匹配；既有信念状态规范。Core/Normal的边界见附录D。")
    y = 190
    y = p.bullet(58,y,"实测画像", "年龄组、学历、收入档、就业、住房、地区、数理能力等；需按本人历史维护更新。", 540)
    y = p.bullet(58,y,"本人过去信念", "上期Q8、十档Q9，以及更早回答摘要。当前A条件重建可用，不等于B递推已完成。", 540)
    p.bullet(58,y,"外部迁移的合成属性", "CE消费结构、购买日数和部分信心标签：有现实参考，但分配给个人仍含假设。", 540, color=GOLD)
    p.rect(650,190,570,351,PALE,LINE)
    p.text(674,214,"一个虚构家庭的输入结构",25,TEAL)
    p.para(674,267,"40–59岁 · 租房 · 中等收入\n在职 · 本科 · 数理能力标签\n\n上期认为未来一年物价会上涨\n保留本人当时的概率分配\n\n合成篮子：食品 / 家居 / 个人护理等",515,22,34)
    p.para(674,542,"新加入者没有本人上期回答，需另设初始化；\n不能用当期真实预期补齐。", 530, 17, 24, MUTED)
    p.takeaway("人口异质性要通过信息接触、理解和更新产生作用，不能只靠增加标签数量。")
    p.finish()

    p = Page(doc, 8, "07 · Environment", "从公共事实库到家庭接触的信息，还缺一层验证", "已有价格趋势、新闻与政策事实；困难在于“哪些被看见、如何被理解”。", "既有新闻分类及暴露实验；50/50为本项目分配设定，尚无代表性参数估计。")
    p.rect(58,188,340,340,PALE,LINE)
    p.text(78,210,"公共事实库",25,TEAL)
    p.para(78,260,"首发价格与就业数据\n过去趋势，注明同比 / 环比\n较及时的汽油等价格\n事件、政策与新闻摘要\n\n记录观测期、公开日、版本",298,22,36)
    p.text(416,320,"→",30,TEAL)
    p.rect(474,188,310,340,"#f9f6ef",LINE)
    p.text(494,210,"信息分配",25,GOLD)
    p.para(494,260,"共同新闻背景\n个人抽取的新闻\n随机性与家庭相关性结合\n\n50%随机 + 50%相关加权\n尚待跨时期验证",268,21,35)
    p.text(801,320,"→",30,TEAL)
    p.rect(858,188,364,340,PALE,LINE)
    p.text(878,210,"家庭实际接收的提示",24,TEAL)
    p.para(878,260,"日常价格与经济背景\n部分不同的新闻组合\n家庭特征与旧信念\n\n仍可能过于像一份统计简报，\n而非居民的日常信息环境。",320,21,35)
    p.para(64,548,"已发现：单纯增加信息、消费类别或频率标签，尚未稳定改善拟合。",1150,21,30)
    p.takeaway("后续重点是验证信息的作用路径，而非继续无差别增加指标和新闻。")
    p.finish()

    p = Page(doc, 9, "08 · Behavior / Simulation / Trajectory", "一次真实模拟，已经可以从输入追溯到评价", "当前默认直接填写本期Q8与Q9；上期信念仍可作为输入。", "本地SocioVerse2链路与真实运行收据；Q9近似计分边界见附录A。")
    steps = [("01 输入","P / E / 历史信念"),("02 行为","真实LLM回答"),("03 原始记录","Q8与十档Q9"),("04 校验计分","合法性 / 个人密度"),("05 评价","聚合 / 分布 / 更新")]
    for i,(title,body) in enumerate(steps):
        x=58+i*238
        p.rect(x,193,215,116,PALE,LINE); p.text(x+13,211,title,22,TEAL)
        p.para(x+13,253,body,190,19,27)
        if i<4:p.text(x+221,236,"→",19,TEAL)
    p.bullet(58,366,"已经留存", "实际消息、原始回答、配置、源码版本、模型回包、token、费用估算、失败与重试。", 350, size=22)
    p.bullet(458,366,"当前默认", "直接报告当期答案。完整概率改动格式有效率不足，未被采用；不自动修复非法概率。", 350, size=22)
    p.bullet(858,366,"尚需验收", "最终提交目录、单一运行入口和干净环境复现。已有日志不等于已经一键交付。", 350, color=GOLD, size=22)
    p.takeaway("流程跑通证明能够开展实验；模型是否像真人，必须由独立观测和基线决定。")
    p.finish()

    p = Page(doc, 10, "09 · Analysis", "把“拟合得像不像”拆成不同的问题", "主结果以同一批人、同一月份和同一计分口径比较；不把全国指标与小样本中心直接混比。", "冻结评价协议：左逆经验CDF；主结果等权、等月/重复平均；调查权重为辅助结果。")
    rows = [
        ("群体中心","Q9个人密度均值的跨人中位数；按期算绝对误差再平均","MAE，越小越好；Q8另报"),
        ("跨人分布","家庭之间的预期水平分布，是否同质化或尾部失真","W1距离；IQR辅助，不能只求更宽"),
        ("个人更新","同一个人相对上月的变化，是否过度修正或不更新","变化分布W1；秩相关与分组检查"),
        ("个人不确定性","一个人给未来不同通胀结果分配概率的宽度与尾部","个人密度IQR、零通缩比例"),
        ("运行可靠性","是否都能产生可计分回答，失败是否选择性发生","合法率、覆盖率、失败原因与成本")]
    p.table(["评价对象", "要回答的问题", "指标与解释"], rows, [195, 590, 383], y=182, row_h=63, size=19)
    p.para(70,550,"参照：本人上期与个人历史锚；全国长跨度宏观基线另列，不混作同样本对照。",1120,19,29,MUTED)
    p.takeaway("中心接近、分歧合理、更新有效，需要同时看；某一个指标改善不能替代整体有效性。")
    p.finish()

    p = Page(doc, 11, "10 · Main results", "个人历史有帮助，但仍落后于过去信息基线", "八期×96人、两组各生成两次；下图仅展示开发后固定规则的四个评价月。", "八期冻结评价与运行收据（10/14）；4评价月379个共同人月、757次配对生成；非全国或B预测。")
    p.text(66,178,"同样本中心：各月两次生成的中位数取平均",20,TEAL)
    p.text(666,178,"2022-06分布：LLM保留的个人差异偏少",20,TEAL)
    p.image("main_centers",58,208,568,274)
    p.image("main_ecdf",656,208,568,274)
    p.text(66,486,"折线作展示；MAE按每月 / 重复分别算绝对误差再平均。",12,MUTED)
    p.text(666,486,"分布展示-5至25%；计分不截尾。2022-06第1次生成、96人。",12,MUTED)
    p.text(64,507,"Q9中心MAE",18,MUTED);p.text(64,535,"LLM 0.636  /  照抄 0.156 pp",23,TEAL)
    p.text(464,507,"跨人分布W1",18,MUTED);p.text(464,535,"3.161  /  0.691 pp",23,TEAL)
    p.text(846,507,"变化分布W1",18,MUTED);p.text(846,535,"1.625  /  2.770 pp",23,TEAL)
    p.takeaway("LLM的变化分布较照抄更接近真人，但中心与跨人分布更差；整体未通过筛选。")
    p.finish()

    p = Page(doc, 12, "11 · Mechanism evidence", "机制实验带来了局部证据，也排除了几条近路", "以下只比较各批内部对照；不同月份、样本、输入版本的误差不排列成进步曲线。", "实验协议、原始回答与统一评价；关键配置和费用见附录B。结论均有样本与时期边界。")
    rows = [
        ("本人原有信念","部分实验减小误差、扩大人际差异；仍有向共同中心回缩","保留为输入；更新方式待验"),
        ("美联储信心标签","相同政策事实下，合成标签有局部收益；跨时期稳定性不足","保留候选，不称普遍有效"),
        ("新闻与购买频率","个性新闻无稳定增量；频率作用说明未改善总体拟合","修正匹配后再做干净对照"),
        ("个人历史叙述","加入年龄对应历史数值或文字，未稳定改善","暂缓整段叙述；不否定经验理论"),
        ("机械概率映射","概率填法更像真人，身份增量很小，分歧未恢复","不作为主要成功机制"),
        ("相对上期报改动","直接组192/192有效；十档改动组仅118/192有效","保留直接填写本期答案")]
    p.table(["尝试的机制", "观察到的结果", "当前处理"],rows,[235,580,353],y=178,row_h=60,size=18)
    p.takeaway("理论有依据，不保证当前合成、提示和传导方式有效；阴性结果同样指导设计取舍。")
    p.finish()

    p = Page(doc, 13, "12 · Bottlenecks", "下一步从真实关联出发，检验信息如何被理解", "70个月、82,535人月：控制月份与已有画像后，两类关联在前后时期均出现。", "SCE官方派生值；月固定效应、官方权重等月归一、按人聚类；观察关联，非因果或留出预测增量。")
    p.image("population_evidence",58,176,1164,255)
    p.bullet(58,455,"认知信息应解释什么", "学历和具体认知答法，更稳定地联系个人不确定性；不宜简单翻译成“预测更高通胀”。",550,size=21)
    p.bullet(660,455,"财务处境应怎样加入", "财务变差与预期较高相关，但存在反向解释；不能把回归系数机械加进每个人的答案。",550,size=21)
    p.takeaway("先检验相同事实下的理解与更新，再决定哪些人口信息应进入主模型。")
    p.finish()

    p = Page(doc, 14, "13 · Next milestones", "收束候选机制，再进行独立验证和研究交付", "优先解决证据链最短、可清楚对照的问题；保持每轮只检验一个主要变化。", "与赛事对应：社会问题25% · 设计25% · 结果20% · 可复现20%（硬门槛） · 呈现10%。[1]")
    rows = [
        ("下一项：认知输入小试","标签 vs 具体题目与本人作答；另比较同内容的忠实转述","事实相同、无标准答案反馈；合法率与三主指标共同评价"),
        ("并行补齐：人口与价格匹配","维护收入 / 家庭更新；补跨年CE和时间证据；分开合成与实测","先通过离线匹配检查，再决定是否支付新模拟费用"),
        ("有效后：固定方案再验证","新时期 / 种子、同信息基线、分组误差与日期敏感性","跨期可重复收益才升级；未改善则报告适用边界"),
        ("交付：可复现研究成果","研究报告、完整运行目录、依赖与来源、实际运行演示","干净环境验收；B递推作为需另验的后续扩展")]
    p.table(["里程碑", "具体行动", "继续推进的判据"],rows,[275,460,433],y=183,row_h=82,size=19)
    p.para(65,565,"当前贡献：建立可审计的调查模拟与评价流程，识别模型压缩个体差异的现象，并用对照筛选改进机制。",1140,21,31)
    p.finish()

    # Appendices keep implementation and interpretation details out of the main talk.
    p = Page(doc, 15, "Appendix A · Survey / scoring", "Q8、Q9与项目计分口径", "两题都是未来12个月；Q8点值与Q9密度均值不必相同。", "来源：SCE原问卷、FAQ、方法材料及项目冻结计分器；这里区分官方统计与项目近似。[2,7]")
    p.bullet(58,187,"Q8：方向与幅度", "先判断总体价格会上涨或下降，再报百分比；项目将其转换成带符号点预期，作为独立辅助结果。",1120,size=23)
    p.bullet(58,304,"Q9：十个区间的概率", "通胀五档：0–2、2–4、4–8、8–12、≥12%；通缩对称五档。原表bin1为通胀≥12%、bin10为通缩≥12%，合计100%。",1120,size=23)
    p.bullet(58,423,"由回答到统计量", "逐人拟合连续密度，再计算个人均值与分位数。全国指标使用调查权重聚合；本报告主实验使用同样本等权中位数，单独注明经验CDF口径。",1120,size=23)
    p.takeaway("冻结计分器已做独立月份对照，但Beta分支仍属近似；不称完全复现官方数值实现。")
    p.finish()

    p = Page(doc, 16, "Appendix B · Experiments", "用于汇报的关键实验与采用状态", "DeepSeek官方API · deepseek-flash · 温度0.5；费用为token估算，非账单，各行不作性能排行。", "完整协议及用量来源见源稿索引；模型别名以回包记录为准，不能据此推断训练截止。")
    rows = [
        ("八期状态 / 新信息","8期×96人×2组×2次","3,072；约$2.141","未过预设筛选；主要多期证据"),
        ("U1显式状态 / 指导","4期×12人×2组×2次","192；约$0.145","状态有局部收益；指导无明确增量"),
        ("本人 / 置换先验","4期×12人×3组×2次","288；约$0.201","可继续研究，身份增量未证实"),
        ("合成央行信心","4期×48人×2组×2次","768；约$0.495","相同政策事实；标签增量为局部证据"),
        ("购买频率作用说明","4期×48人×2组×2次","768；约$0.875","两组均有频率，不是有无频率试验"),
        ("直接 / 十档改动","4期×24人×2组×2次","384；约$0.434","74份非法；完整改动格式不采用")]
    p.table(["实验", "配置", "请求数 / 模拟费", "结论与限制"],rows,[260,290,250,368],y=180,row_h=65,size=18)
    p.para(65,624,"八期另含新闻补标约$0.583；共约$2.725。模拟3072次中3069有效，无自动重试。",1120,16,23,MUTED)
    p.finish()

    p = Page(doc, 17, "Appendix C · Time / information", "外部资料的时点合规，与模型记忆风险分别处理", "原始资料保留来源与版本；未知时间证据不能由当前下载日期替代。", "官方来源：newyorkfed.org / bls.gov / eia.gov / developer.nytimes.com；CE与NYT公开再分发需另核许可。")
    p.table(["环节", "已有处理", "尚未解决 / 未来要求"],[
        ("价格与就业修订","历史输入优先取首发稿；保留观测期、发布日、版本","年度季调等修订不能覆盖原快照；时点缺失则隔离"),
        ("SCE微观可得性","A使用声明的历史画像与本人旧回答；当期答案仅评价","B不能拿未公布的当期微观样本初始化，需旧人口或合成"),
        ("新闻与政策事实","按公开时间截断、分类并物化；摘要/片段重复做文本去重","公开不等于本人已读；摘要不能视为完整报道或真实记忆"),
        ("CE与合成属性","标注跨调查供体、假设与缺失；不伪装为SCE实测","2020供体不全满足早期预测时点；2019/21/22下载仍受阻"),
        ("模型预训练知识","记录别名、实际回包、端点、温度和指纹","历史数值可能在训练内；未知截止下不称严格事前预测")
    ],[245,450,473],y=184,row_h=69,size=18)
    p.takeaway("历史条件重建可以声明使用的信息；严格未来预测还需要真正的未公布目标和封存验证。")
    p.finish()

    p = Page(doc, 18, "Appendix D · Statistics", "主结果的比较对象、有效样本与解释边界", "主表来自同样本支持，不套用长跨度全国基线的MAE作为该实验的直接对照。", "冻结八期协议、覆盖澄清与评价摘要；经验CDF使用左逆定义，区别于插值分位数。")
    p.table(["比较对象", "中心MAE", "跨人W1", "变化W1", "跨人IQR"],[
        ("LLM + 本人历史","0.636","3.161","1.625","1.565"),
        ("照抄上期","0.156","0.691","2.770","5.291"),
        ("个人历史锚（过去均值各半）","0.488","1.052","1.707","5.060"),
        ("无本人历史的新信息LLM","1.337","4.398","2.933","0.608"),
        ("对应真人分歧","-","-","-","5.545")
    ],[505,166,166,166,165],y=181,row_h=49,size=19)
    p.para(65,493,"样本：4评价月计划384人月，共同可评分379个不同人月、757次生成；378人月两次均有共同支持。各月/重复分别计分，再等权平均。单位均为百分点。",1135,19,29)
    p.para(65,563,"LLM和两条过去信息基线的信息集不同：这里只检验实用表现，不单凭胜负识别因果优势。开发选择的新信号权重为0，程序组合因此等于照抄；未据评价期重新选择。",1135,19,29)
    p.finish()

    p = Page(doc, 19, "Appendix E · Reliability", "不确定性、失败回答与Core / Normal的使用边界", "扩展人口数量、扩大时间覆盖与改变行为机制，解决的是不同问题。", "评价器与统一比较协议；ConsumerSim仅提供设计参照，不作为本项目已达到的性能标准。[8]")
    y=185
    y=p.bullet(58,y,"区间跨0是什么意思", "在既定重抽样方法下，数据尚不能排除“平均没有改善”。这不等于效果为0，也不能据少数月份宣称普遍有效。重复生成按同一个人保留在一起。",1130,size=22)
    y=p.bullet(58,y,"失败必须进入评价", "十档改动组只对118/192份合法回答评分，会选择性排除困难样本。因此该批准确度只作条件描述，不作机制增益或成功证据。",1130,size=22)
    y=p.bullet(58,y,"Core / Normal不能凭空制造独立信息", "可用少量LLM核心回答向普通人口投影以控制成本，但投影误差必须另验。本报告主要机制试验直接调用抽样人群，不把外推人数当成新增真实回答。",1130,size=22)
    p.takeaway("相同几个月反复调参不能替代独立验证；扩大后需覆盖不同经济阶段与新种子。")
    p.finish()

    p = Page(doc, 20, "Appendix F · References / delivery", "来源与最终交付检查", "网页及证据核查截至2026-10-15；完整本地来源索引与聚合数据随源稿留存。", "赛事要求与网页链接以官方当前版本为准；本稿是进展汇报，不代替最终参赛论文。")
    refs=[
        ("[1] SocioVerse Challenge 2026", "socioverse.fudan-disc.com/challenge/ · 赛道A、评分与交付要求"),
        ("[2] NY Fed SCE FAQ / data", "newyorkfed.org/microeconomics/sce · 调查、指标与公开微观材料"),
        ("[3] D’Acunto et al. (2021), JPE", "Exposure to Grocery Prices and Inflation Expectations · doi:10.1086/713192"),
        ("[4] Malmendier & Nagel (2016), QJE", "Learning from Inflation Experiences · 经验学习与代际差异"),
        ("[5] Armantier et al., NY Fed SR543", "The Price Is Right · 随机价格信息与预期更新"),
        ("[6] Carroll (2003), QJE", "Macroeconomic Expectations of Households and Professional Forecasters"),
        ("[7] Armantier et al. (2017), FRBNY", "An Overview of the Survey of Consumer Expectations · 调查方法"),
        ("[8] ConsumerSim (2026)", "arxiv.org/abs/2606.30395 · 人群模拟、投影与统计验证的研究参照")]
    y=178
    for title, body in refs:
        p.text(60,y,title,18,TEAL);p.text(60,y+25,body,16,MUTED);y+=49
    p.line(58,578,1220,578)
    p.para(60,590,"最终交付仍需：4–8页论文、≤5分钟实际运行演示、固定依赖与种子、来源及模型/调用/成本说明、干净环境复现。",1150,20,29)
    p.finish()

    doc.save()
    pages=doc._report_pages
    links = [
        ("赛事官网","https://socioverse.fudan-disc.com/challenge/"),
        ("SCE官方","https://www.newyorkfed.org/microeconomics/sce"),
        ("SCE FAQ","https://www.newyorkfed.org/microeconomics/sce/sce-faq"),
        ("价格体验研究","https://www.journals.uchicago.edu/doi/10.1086/713192"),
        ("随机信息实验","https://www.newyorkfed.org/research/staff_reports/sr543.html"),
        ("ConsumerSim","https://arxiv.org/abs/2606.30395")]
    nav="".join(f'<a href="#p{a["number"]}">{a["number"]:02} {html.escape(a["title"])}</a>' for a in pages)
    body="".join(f'<section id="p{a["number"]}" aria-label="第{a["number"]}页 {html.escape(a["title"])}"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" role="img"><title>{html.escape(a["title"])}</title>{a["svg"]}</svg></section>' for a in pages)
    linkhtml=" · ".join(f'<a href="{u}" target="_blank" rel="noreferrer">{n}</a>' for n,u in links)
    html_doc='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SCE项目阶段性汇报 · 水上挽月</title><style>
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#e8efee;color:#18343d;font-family:"Arial Unicode MS",Arial,sans-serif}header{position:sticky;top:0;background:#18343d;color:white;padding:12px 22px;z-index:2;display:flex;align-items:center;gap:18px;flex-wrap:wrap}header strong{font-size:17px}header span{font-size:13px;color:#c7dbd9}button,header a{background:#edf5f4;color:#18343d;border:0;border-radius:4px;padding:7px 11px;font-size:14px;cursor:pointer;text-decoration:none}main{max-width:1440px;margin:24px auto;padding:0 18px}section{margin:0 auto 26px;background:white;box-shadow:0 3px 16px #18343d18;scroll-margin-top:80px}section svg{display:block;width:100%;height:auto}details{max-width:1400px;margin:20px auto;background:white;padding:14px 20px}nav{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:9px;margin:15px 0}nav a,footer a{color:#087f80;text-decoration:none;font-size:14px}footer{max-width:1400px;margin:25px auto 45px;padding:16px;color:#526970}body.present header,body.present details,body.present footer{display:none}body.present main{padding:0;margin:0;max-width:none}body.present section{display:none;margin:0;box-shadow:none;height:100vh;background:#18343d}body.present section.active{display:flex;align-items:center;justify-content:center}body.present svg{max-width:100vw;max-height:100vh}@page{size:landscape;margin:0}@media print{header,details,footer{display:none}body,main{margin:0;padding:0;background:white;max-width:none}section{box-shadow:none;margin:0;page-break-after:always;break-after:page}section svg{width:100%}}
</style></head><body><header><strong>SCE项目阶段性汇报</strong><span>14页主讲 + 6页附录 · 2026.10.15</span><button id="present">演示模式</button><button onclick="window.print()">打印 / 另存为PDF</button><span>演示中：← →翻页，Esc返回</span></header><details><summary>逐页目录</summary><nav>'''+nav+'''</nav></details><main>'''+body+'''</main><footer>来源链接：'''+linkhtml+'''<p>所有图表均来自已有聚合证据；阅读本页不联网、不调用模型。HTML与PDF使用同一份文字、布局和图表。第一版供内容与排版复核。</p></footer><script>
let pages=[...document.querySelectorAll('section')],current=0;function show(i){current=Math.max(0,Math.min(pages.length-1,i));pages.forEach((p,j)=>p.classList.toggle('active',j===current))}document.querySelector('#present').onclick=()=>{current=Math.max(0,pages.findIndex(p=>p.getBoundingClientRect().bottom>90));document.body.classList.add('present');show(current)};document.addEventListener('keydown',e=>{if(!document.body.classList.contains('present'))return;if(['ArrowRight','PageDown',' '].includes(e.key)){show(current+1);e.preventDefault()}if(['ArrowLeft','PageUp'].includes(e.key)){show(current-1);e.preventDefault()}if(e.key==='Escape'){document.body.classList.remove('present');pages[current].scrollIntoView()}});
</script></body></html>'''
    (OUT/"index.html").write_text(html_doc)
    notes="\n\n".join(f'## {a["number"]:02} {a["title"]}\n\n'+"\n\n".join(a["text"][:-3]) for a in pages)
    (SRC/"content.md").write_text("# SCE项目阶段性汇报 · 第一版\n\n14页主讲、6页附录；2026-10-15。图文同源，派生稿的正文如下。\n\n"+notes+"\n")
    manifest={"date":"2026-10-15","pages":len(pages),"main_pages":14,"appendix_pages":6,
              "new_api_calls":0,"pdf":str(PDF.relative_to(ROOT)),"html":str((OUT/"index.html").relative_to(ROOT)),
              "pdf_sha256":hashlib.sha256(PDF.read_bytes()).hexdigest(),
              "html_sha256":hashlib.sha256((OUT/"index.html").read_bytes()).hexdigest(),
              "aggregate_source":"aggregate_data.json","status":"draft_v1_rendered_awaiting_visual_qa"}
    (SRC/"delivery.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(manifest,ensure_ascii=False))


if __name__=="__main__":render()
