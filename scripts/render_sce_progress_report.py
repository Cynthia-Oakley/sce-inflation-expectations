"""Render the agreed progress briefing as PDF and a matching local HTML reader.

All content comes from existing aggregate evidence. PDF and HTML share the same
text, geometry and figures. No remote assets, tracking, model calls or new fits.
"""
from pathlib import Path
import hashlib
import html
import json
import re
from itertools import groupby
import shutil

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/sce_progress_report_20261015_v2"
SRC = ROOT / "studies/sce_inflation_expectations/reports/progress_20261015_v2"
PDF = ROOT / "output/pdf/sce_progress_report_20261015_v2.pdf"
W, H = 1280, 720
INK, TEAL, GOLD, RED = "#18343d", "#087f80", "#aa762f", "#ad5950"
MUTED, LINE, PALE, BG = "#526970", "#d5e1e2", "#eef5f4", "#fafcfb"
FONT_PATH = str(OUT / "assets/kaiti_sc.ttf")
pdfmetrics.registerFont(TTFont("CN", FONT_PATH))
pdfmetrics.registerFont(TTFont("Latin", "/System/Library/Fonts/Supplemental/Times New Roman.ttf"))
LATIN_GLYPHS = pdfmetrics.getFont("Latin").face.charToGlyph


def font_runs(s):
    def which(c):
        return 'Latin' if ord(c) < 0x2E80 and ord(c) in LATIN_GLYPHS else 'CN'
    return [(f, ''.join(chars)) for f, chars in groupby(str(s), key=which)]


def text_width(s, size):
    return sum(pdfmetrics.stringWidth(t, f, size) for f, t in font_runs(s))


class Page:
    def __init__(self, doc, number, section, title, subtitle="", source="", appendix=False):
        self.doc, self.number, self.svg, self.plain = doc, len(doc._report_pages)+1, [], []
        self.rect(0, 0, W, H, "#ffffff")
        self.rect(0, 0, 10, H, TEAL)
        self.text(56, 35, section.upper(), 15, TEAL)
        self.text(56, 72, title, 34)
        if subtitle:
            self.text(58, 119, subtitle, 18, MUTED)
        self.line(56, 155, 1224, 155, LINE)
        self.source = source
        self.appendix = appendix or section.startswith("Appendix")
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
        self.doc.setFillColor(HexColor(color))
        for selected, run in font_runs(s):
            self.doc.setFont(selected, size)
            self.doc.drawString(x, H-y-size*.90, run)
            family = "Kaiti SC,STKaiti,KaiTi,serif" if selected == "CN" else "Times New Roman,serif"
            self.svg.append(f'<text x="{x}" y="{y+size*.90}" font-size="{size}" font-family="{family}" fill="{color}">{html.escape(run)}</text>')
            x += pdfmetrics.stringWidth(run, selected, size)
        self.plain.append(s)

    def para(self, x, y, s, w, size=22, leading=None, color=INK):
        leading = leading or size*1.50
        start = y
        for paragraph in s.split("\n"):
            tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.,/%+()=<>:–-]*|\s+|.", paragraph)
            line = ""
            for token in tokens:
                if text_width(line+token, size) <= w:
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

    p = Page(doc, 1, "SocioVerse Challenge 2026 · Track A", "美国居民通胀预期的Agent模拟", source="阶段性研究汇报 · 基于SCE的历史重建与方法验证 · 修订版")
    p.text(58, 186, "基于SCE的历史重建与方法验证", 30, TEAL)
    p.para(58, 255, "给定家庭特征、信息环境与既有信念，\nAgent能否生成接近真实调查的预期及其分布？", 1070, 30, 48)
    p.line(58, 392, 1220, 392, LINE)
    p.text(58, 426, "阶段判断", 19, GOLD)
    p.para(58, 466, "调查模拟流程已贯通。\n总体拟合与个人差异仍未达到稳定有效的标准。", 1110, 27, 44)
    p.text(58, 579, "水上挽月  ·  复旦大学  ·  2026年10月15日", 21, MUTED)
    p.finish()

    p = Page(doc, 2, "01 · Survey background", "SCE：纽约联储的消费者预期调查", "Survey of Consumer Expectations。我们研究其中的“一年期通胀预期”，即居民判断未来12个月物价会变化多少。", "来源：纽约联储SCE FAQ与官方发布档案，2026-10-15核查。约1,200人为当前FAQ设计规模，实际月样本不同。[2]")
    p.table(["调查制度", "具体情况"],[
        ("调查机构", "美国纽约联邦储备银行（纽约联储）"),
        ("调查频率与起点", "2013年6月启动，每月在线调查，月内分周收集"),
        ("调查对象与规模", "美国家庭财务负责人，设计规模约1,200人 / 月"),
        ("同一人能参加多久", "每人最多跟踪12个月，每月有一部分人退出与加入"),
        ("月度指标何时公开", "通常在调查次月公布，具体日期按官方日历"),
        ("逐人微观数据何时公开", "核心调查滞后9个月，晚于月度汇总指标")
    ],[245,530],y=181,row_h=59,size=20)
    p.text(884,198,"选择SCE的原因",25,TEAL)
    p.para(884,247,"通胀预期影响消费、工资判断和政策传导，具有直接的经济学意义。",322,22,34)
    p.para(884,373,"原问卷、人口画像、逐人概率回答与跨月记录可用于构造和检验Agent。",322,22,34)
    p.para(884,499,"既能对照总体指标，也能检验家庭分歧和信念更新。",322,22,34)
    p.takeaway("月度指标更新较快，个人记录公布较慢。这决定了历史重建与未来预测需要不同的人口输入。")
    p.finish()

    p = Page(doc, 2, "02 · Research question", "研究目标：总体水平与家庭预期分布", "用同一套模拟，同时检验群体中位数、家庭之间的分歧，以及同一家庭的逐月变化。", "来源：NY Fed SCE公开月度指标（10/07归档）；SCE微观2022-06；官方FAQ。[1–2]")
    p.text(58, 180, "预期随经济环境变化", 23, TEAL)
    p.text(696, 180, "同一月份，家庭判断也不同", 23, TEAL)
    p.image("headline", 58, 218, 580, 287)
    p.image("real_distribution", 690, 218, 530, 287)
    p.para(70, 517, "官方全国指标：2020-01至2026-08\n已归档资料版，不代表官网当前最新一期。", 555, 16, 25, MUTED)
    p.para(704, 517, "真人2022-06，有效1,202条，官方派生值、调查权重。\n包含全部尾部；与后文实验样本及计分口径不同。", 510, 16, 25, MUTED)
    p.takeaway("总体指标需要接近真实调查。Agent方法的额外价值，在于能否同时还原家庭差异及其变化。")
    p.finish()

    p = Page(doc, 3, "03 · Study", "历史重建与未来预测的信息使用范围", "关键区别是研究者能否利用后来公开的资料还原历史。当前实验以历史重建为主。", "项目路线A/B设计与八期协议；赛道A允许历史重建与未来预测。[1] 本页只说明设计，不改运行配置。")
    p.table(["比较维度", "A  历史重建", "B  未来预测"],[
        ("研究目标", "事后重建某月家庭回答与分布", "在结果公布前预测下一调查月"),
        ("人口与已有信念", "可用后来公开的该月真实画像、本人过去回答", "只用截止前已有的旧人口或合成人口，信念自行递推"),
        ("经济与新闻资料", "可事后整理历史背景。当前实验仍按调查窗口截断新闻与价格", "只可使用预先确定的预测截止日前已公开资料"),
        ("真实调查答案", "本项目未将当期答案作为输入，只在生成后检验", "预测时不可获得，公布后再进行评价")
    ],[210,479,479],y=183,row_h=77,size=21)
    p.para(65,548,"例：事后重建2022年6月可使用6月真实画像，而在5月末预测6月时，这些微观记录尚未公开。",1140,20,30)
    p.takeaway("两条路线中的家庭都可以只接触当时信息。A允许研究者事后还原人口，B要求整套方案在截止日可执行。")
    p.finish()

    p = Page(doc, 4, "04 · P / E / B", "P/E/B框架：居民、信息与作答过程", "P刻画居民的处境与原有信念，E描述其接触的信息，B是模型据此形成并表达预期的过程。", "参考SocioVerse官方CCI/PMI案例和ConsumerSim。经济学机制依据见[3–6]，具体实现由实验检验。")
    boxes = [(58, 185, 330, "Population  居民是谁", "年龄、收入、教育、就业\n住房、数理能力\n本人过去的通胀预期", "来源：SCE微观与历史回答"),
             (438,185,350,"Environment  接触什么","已公布的价格与变化趋势\n经济事件、新闻与政策\n按家庭处境分配部分信息", "来源：官方统计、价格与纽约时报"),
             (840,185,380,"Behavior  如何作答","理解信息，保留或修正旧信念\n给出Q8点预测与Q9概率\n再由计分程序形成统计量", "实现：语言模型（LLM）作答")]
    for x,y,w,title,body,src in boxes:
        p.rect(x,y,w,226,PALE,LINE); p.text(x+18,y+18,title,22,TEAL)
        p.para(x+18,y+64,body,w-36,21,34)
        p.text(x+18,y+194,src,17,MUTED)
    p.text(400, 267, "+", 28, TEAL); p.text(803, 267, "→", 28, TEAL)
    p.text(58, 439, "需要检验的传导机制", 24)
    p.bullet(58, 479, "价格体验", "购买与接触频率如何影响价格关注。", 350, size=20)
    p.bullet(458, 479, "信念更新", "新信息如何改变原有判断。", 350, size=20)
    p.bullet(858, 479, "认知与表达", "数字理解如何影响概率分配。", 350, size=20)
    p.takeaway("合成补充参考CE消费调查与Gallup信心调查。分配给个人仍含假设，其行为效果需要单独验证。")
    p.finish()

    p = Page(doc, 5, "05 · Project status", "项目各环节的完成情况", "按SocioVerse研究流程梳理已完成工作，以及尚需验证的问题。", "项目清单与运行收据，截至2026-10-15。")
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
    p.takeaway("数据、模拟、计分和评价已贯通，当前工作集中于改善拟合并验证居民行为机制。")
    p.finish()

    p = Page(doc, 6, "06 · Dataset", "数据来源、用途与覆盖范围", "输入资料用于构造居民与环境。当期真实通胀答案在模型生成后用于评价。", "已归档来源：NY Fed、BLS、EIA、NYT Archive API、CE，数据清单及限制见附录C。")
    rows = [
        ("SCE微观 + 原问卷","人口、本人历史、真实回答与原始题意","2017-01至2025-10；106个月、130,216人月"),
        ("SCE官方月度指标","全国时间序列与外部统计口径核对","归档指标示例延伸至2026-08；不同于微观覆盖"),
        ("美国劳工统计局（BLS）","首发新闻稿中的CPI、就业及其他宏观信号","按实际发布日期入窗；首发值与修订值分开"),
        ("能源信息署（EIA）等","较及时的能源价格与家庭近期价格线索","仅在已取得历史时间证据的窗口使用"),
        ("纽约时报（NYT）档案","公开事件背景、政策与家庭相关消息","关键词粗筛后由LLM分类，再抽取个人新闻"),
        ("消费者支出调查（CE）","支出表与Diary日记数据，用于合成消费结构和购买日数","供体家庭非SCE本人，跨年覆盖与发布时间有缺口")]
    p.table(["数据来源", "在项目中的用途", "覆盖与边界"], rows, [270, 420, 478], y=176, row_h=60, size=18)
    p.takeaway("价格与就业优先使用历史首发稿，保留实际公开日期，避免将后来修订值误当作当时已知值。")
    p.finish()

    p = Page(doc, 7, "07 · Population", "居民画像与原有信念的构造", "实测信息、本人历史与合成补充分别记录。右侧仅为虚构示例。", "SCE微观与问卷、CE供体匹配、既有信念状态规范。Core/Normal的说明见附录E。")
    y = 190
    y = p.bullet(58,y,"实测画像", "年龄组、学历、收入档、就业、住房、地区、数理能力等；需按本人历史维护更新。", 540)
    y = p.bullet(58,y,"本人过去信念", "上期Q8、十档Q9，以及更早回答摘要。当前A条件重建可用，不等于B递推已完成。", 540)
    p.bullet(58,y,"外部迁移的合成属性", "CE消费结构、购买日数和部分信心标签：有现实参考，但分配给个人仍含假设。", 540, color=GOLD)
    p.rect(650,190,570,351,PALE,LINE)
    p.text(674,214,"一个虚构家庭的输入结构",25,TEAL)
    p.para(674,267,"40–59岁 · 租房 · 中等收入\n在职 · 本科 · 数理能力标签\n\n上期认为未来一年物价会上涨\n保留本人当时的概率分配\n\n合成篮子：食品 / 家居 / 个人护理等",515,22,34)
    p.para(674,542,"新加入者没有本人上期回答，需另设初始化；\n不能用当期真实预期补齐。", 530, 17, 24, MUTED)
    p.takeaway("后续将检验人口特征是否真正改变信息接触、理解与更新，而不只检查提示词是否列出了该特征。")
    p.finish()

    p = Page(doc, 8, "08 · Environment", "公共信息与家庭信息接触", "保存完整事实库以便核查，再选择每个家庭实际接收的内容。信息分配方式仍需检验。", "既有新闻分类与信息分配实验。50/50为项目设定，尚无代表性参数估计。")
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
    p.takeaway("重点检验家庭接触何种信息、如何理解涨价及其持续性，再决定是否增加新的指标和新闻。")
    p.finish()

    p = Page(doc, 9, "09 · Behavior / Simulation / Trajectory", "模拟流程与运行记录", "模型直接填写本期Q8与Q9，并可参考本人上期信念。各阶段保留可核查的输入与输出。", "本地SocioVerse2流程与真实运行记录。Q9近似计分边界见附录A。")
    steps = [("01 输入","P / E / 历史信念"),("02 行为","真实LLM回答"),("03 原始记录","Q8与十档Q9"),("04 校验计分","合法性 / 个人密度"),("05 评价","聚合 / 分布 / 更新")]
    for i,(title,body) in enumerate(steps):
        x=58+i*238
        p.rect(x,193,215,116,PALE,LINE); p.text(x+13,211,title,22,TEAL)
        p.para(x+13,253,body,190,19,27)
        if i<4:p.text(x+221,236,"→",19,TEAL)
    p.bullet(58,366,"已经留存", "实际消息、原始回答、配置、源码版本、模型回包、token、费用估算、失败与重试。", 350, size=22)
    p.bullet(458,366,"当前默认", "直接报告当期答案。完整概率改动格式有效率不足，未被采用；不自动修复非法概率。", 350, size=22)
    p.bullet(858,366,"尚需验收", "最终提交目录、单一运行入口和干净环境复现。已有日志不等于已经一键交付。", 350, color=GOLD, size=22)
    p.takeaway("现有流程支持真实LLM实验与离线复算。拟合效果另外通过真实调查和基线模型检验。")
    p.finish()

    p = Page(doc, 10, "10 · Analysis", "拟合误差的组成与评价指标", "分别评价群体中心、家庭差异和逐月变化。各项结果都与同一批真人、同一月份比较。", "统一计分与经验分位数定义。主结果按月及生成次数等权平均，调查权重结果另作辅助。")
    rows = [
        ("群体中心","Q9个人密度均值的跨人中位数，按期计算误差再平均","MAE即平均绝对误差，越小越好"),
        ("跨人分布","不同家庭的预期分布是否接近真人，尾部是否失真","W1为分布差距，越小越好"),
        ("个人更新","同一个人相对上月的变化，是否过度修正或不更新","变化分布W1；秩相关与分组检查"),
        ("个人不确定性","一个人给未来不同通胀结果分配概率的宽度与尾部","中间50%的跨度（IQR）、通缩零概率"),
        ("运行可靠性","是否都能产生可计分回答，失败是否选择性发生","合法率、覆盖率、失败原因与成本")]
    p.table(["评价对象", "要回答的问题", "指标与解释"], rows, [195, 590, 383], y=182, row_h=63, size=19)
    p.para(70,550,"参照：本人上期与个人历史锚；全国长跨度宏观基线另列，不混作同样本对照。",1120,19,29,MUTED)
    p.takeaway("同时检查总体指标和微观分布，才能判断拟合改善来自合理的家庭差异，还是共同水平的移动。")
    p.finish()

    p = Page(doc, 11, "11 · Main results", "八个月模拟结果与基线对比", "每月96人，两组各生成两次。前四期用于方案选择，后四期用于固定方案后的评价。", "10/14八期实验。误差表仅按后四评价月计算：379个共同人月、757次配对生成，未外推为全国指标。")
    p.text(66,178,"八个非连续调查月：同样本Q9中位数",20,TEAL)
    p.text(666,178,"2022-06分布：LLM保留的个人差异偏少",20,TEAL)
    p.image("eight_centers",58,208,568,274)
    p.image("main_ecdf",656,208,568,274)
    p.text(66,486,"两次生成取均值展示。分界线区分开发与评价，下方误差只使用后四期。",12,MUTED)
    p.text(666,486,"分布展示-5至25%；计分不截尾。2022-06第1次生成、96人。",12,MUTED)
    p.text(64,507,"Q9中心MAE",18,MUTED);p.text(64,535,"LLM 0.636  /  照抄 0.156 pp",23,TEAL)
    p.text(464,507,"跨人分布W1",18,MUTED);p.text(464,535,"3.161  /  0.691 pp",23,TEAL)
    p.text(846,507,"变化分布W1",18,MUTED);p.text(846,535,"1.625  /  2.770 pp",23,TEAL)
    p.takeaway("后四期中，LLM的逐月变化分布较好，但群体中心与家庭分布仍差于照抄上期，尚未达到整体目标。")
    p.finish()

    p = Page(doc, 12, "12 · Mechanism evidence", "机制实验与跨模型检查的主要发现", "各项结论来自对应批次的内部对照，不能将不同版本的误差直接相减。", "已有实验、2021年DeepSeek/Qwen同消息对照与CPI核查，详细来源见源稿索引，参数与费用见附录B。")
    rows = [
        ("本人原有信念","部分实验减小误差、扩大人际差异；仍有向共同中心回缩","保留为输入；更新方式待验"),
        ("美联储信心标签","相同政策事实下，合成标签有局部收益；跨时期稳定性不足","保留候选，不称普遍有效"),
        ("新闻与购买频率","个性新闻无稳定增量；频率作用说明未改善总体拟合","修正匹配后再做干净对照"),
        ("个人历史叙述","加入年龄对应历史数值或文字，未稳定改善","暂缓整段叙述；不否定经验理论"),
        ("机械概率映射","概率填法更像真人，身份增量很小，分歧未恢复","不作为主要成功机制"),
        ("相对上期报改动","直接组192/192有效，十档改动组仅118/192有效","保留直接填写本期答案"),
        ("跨模型与历史知识","DeepSeek/Qwen均偏离SCE，也未稳定贴合一年后实际CPI","拟合偏差不能排除局部记忆，后续做训练边界前后比较")]
    p.table(["研究内容", "观察到的结果", "当前处理"],rows,[235,580,353],y=169,row_h=53,size=17)
    p.takeaway("已观察到的改善与未改善结果共同决定后续取舍。理论机制仍需通过具体实现和独立时期检验。")
    p.finish()

    p = Page(doc, 13, "13 · Bottlenecks", "认知与财务处境的真实数据依据", "70个月、82,535人月：比较月份和其他画像相近的人群，两类关联在前后时期均出现。", "SCE官方派生值。月固定效应、官方权重等月归一、按人聚类。这是条件关联，不能直接解释为因果作用。")
    p.image("population_evidence",58,176,1164,255)
    p.bullet(58,455,"认知信息应解释什么", "学历和具体认知答法，更稳定地联系个人不确定性；不宜简单翻译成“预测更高通胀”。",550,size=21)
    p.bullet(660,455,"财务处境应怎样加入", "财务变差与预期较高相关，但存在反向解释；不能把回归系数机械加进每个人的答案。",550,size=21)
    p.takeaway("这些关联为认知与处境的输入设计提供依据。是否能改善LLM模拟，还需在相同P/E下单独检验。")
    p.finish()

    p = Page(doc, 14, "14 · Next milestones", "后续研究安排与交付计划", "优先开展已有数据能够支持、对照关系清楚的研究。每轮只改变一个主要设计。", "赛事评分：社会科学价值25%，方法设计25%，结果20%，可复现20%（不及格淘汰），呈现10%。[1]")
    rows = [
        ("下一项：认知输入小试","数理高低标签与具体题目 / 本人作答对照，再检验同内容的忠实转述","不提供正确答案或纠错反馈，检查有效率与中心 / 分布误差"),
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
        ("含本人历史 / 不含历史","8期×96人×2组×2次","3,072；约$2.141","未过预设筛选，主要多期证据"),
        ("历史摘要 / 更新指导","4期×12人×2组×2次","192；约$0.145","摘要有局部收益，指导无明确增量"),
        ("本人 / 他人上期回答","4期×12人×3组×2次","288；约$0.201","可继续研究，本人特有增量未证实"),
        ("合成央行信心","4期×48人×2组×2次","768；约$0.495","相同政策事实；标签增量为局部证据"),
        ("购买频率作用说明","4期×48人×2组×2次","768；约$0.875","两组均有频率，不是有无频率试验"),
        ("直接 / 十档改动","4期×24人×2组×2次","384；约$0.434","74份非法；完整改动格式不采用")]
    p.table(["实验", "配置", "请求数 / 模拟费", "结论与限制"],rows,[260,290,250,368],y=180,row_h=65,size=18)
    p.para(65,624,"八期另含新闻补标约$0.583；共约$2.725。模拟3072次中3069有效，无自动重试。",1120,16,23,MUTED)
    p.finish()

    p = Page(doc, 17, "Appendix C · Time / information", "资料发布时间与模型历史知识的核查", "已完成历史数值对照，尚未完成能够排除模型参数知识影响的检验。", "数据来源与历史模型对照见源稿索引。未来CPI只作诊断，不用于生成回答或调整参数。")
    p.table(["环节", "已有处理", "尚未解决 / 未来要求"],[
        ("价格与就业修订","历史输入优先取首发稿；保留观测期、发布日、版本","年度季调等修订不能覆盖原快照；时点缺失则隔离"),
        ("SCE微观可得性","A使用声明的历史画像与本人旧回答；当期答案仅评价","B不能拿未公布的当期微观样本初始化，需旧人口或合成"),
        ("新闻与政策事实","按公开时间截断、分类并物化；摘要/片段重复做文本去重","公开不等于本人已读；摘要不能视为完整报道或真实记忆"),
        ("CE与合成属性","标注跨调查供体、假设与缺失；不伪装为SCE实测","2020供体不全满足早期预测时点；2019/21/22下载仍受阻"),
        ("模型预训练知识","2021年DeepSeek/Qwen对照均偏离SCE，也未稳定贴合一年后CPI","选训练边界可核验的模型，比较边界前后时期，并用相同P/E控制设计差异")
    ],[245,450,473],y=184,row_h=69,size=18)
    p.takeaway("没有稳定复现历史真值，是已有发现。它不足以证明模型完全未使用历史知识，后续将作针对性检验。")
    p.finish()

    p = Page(doc, 18, "Appendix D · Statistics", "主结果的比较对象与统计口径", "主表只比较同一批可评分的人，指标按后四评价月计算。全国长跨度基线另行报告。", "冻结八期协议、覆盖说明与评价摘要。经验CDF使用左逆定义，区别于插值分位数。")
    p.table(["比较对象", "中心MAE", "跨人W1", "变化W1", "跨人IQR"],[
        ("LLM + 本人历史","0.636","3.161","1.625","1.565"),
        ("照抄上期","0.156","0.691","2.770","5.291"),
        ("本人上期值与更早均值各半","0.488","1.052","1.707","5.060"),
        ("无本人历史的新信息LLM","1.337","4.398","2.933","0.608"),
        ("对应真人分歧","-","-","-","5.545")
    ],[505,166,166,166,165],y=181,row_h=49,size=19)
    p.para(65,493,"样本：4评价月计划384人月，共同可评分379个不同人月、757次生成；378人月两次均有共同支持。各月/重复分别计分，再等权平均。单位均为百分点。",1135,19,29)
    p.para(65,563,"LLM和两条过去信息基线的信息集不同：这里只检验实用表现，不单凭胜负识别因果优势。开发选择的新信号权重为0，程序组合因此等于照抄；未据评价期重新选择。",1135,19,29)
    p.finish()

    p = Page(doc, 19, "Appendix E · Reliability", "抽样不确定性、失败回答与人口外推", "报告区间、有效样本和投影误差，避免把增加生成次数当作增加独立受访者。", "评价器与统一比较协议。ConsumerSim提供方法参考，误差不跨研究对象直接比较。[8]")
    y=185
    y=p.bullet(58,y,"误差改善的区间估计", "如果改善区间包括0，现有样本仍不能排除平均没有改善。扩大时期与人群覆盖后再检验，重抽样时将同一个人的重复回答保留在一起。",1130,size=22)
    y=p.bullet(58,y,"失败必须进入评价", "十档改动组只对118/192份合法回答评分，会选择性排除困难样本。因此该批准确度只作条件描述，不作机制增益或成功证据。",1130,size=22)
    y=p.bullet(58,y,"Core / Normal人口扩展", "少量Core居民由LLM直接作答，再向Normal居民投影以控制成本，投影误差须另外检验。本报告主要机制试验直接调用抽样人群，外推人数不作为新增独立回答。",1130,size=22)
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
    shutil.copyfile('/System/Library/Fonts/Supplemental/Times New Roman.ttf', OUT/'assets/times_new_roman.ttf')
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
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#e8efee;color:#18343d;font-family:"Times New Roman","Kaiti SC",STKaiti,KaiTi,serif}header{position:sticky;top:0;background:#18343d;color:white;padding:12px 22px;z-index:2;display:flex;align-items:center;gap:18px;flex-wrap:wrap}header strong{font-size:17px}header span{font-size:13px;color:#c7dbd9}button,header a{background:#edf5f4;color:#18343d;border:0;border-radius:4px;padding:7px 11px;font-family:inherit;font-size:14px;cursor:pointer;text-decoration:none}main{max-width:1440px;margin:24px auto;padding:0 18px}section{margin:0 auto 26px;background:white;box-shadow:0 3px 16px #18343d18;scroll-margin-top:80px}section svg{display:block;width:100%;height:auto}details{max-width:1400px;margin:20px auto;background:white;padding:14px 20px}nav{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:9px;margin:15px 0}nav a,footer a{color:#087f80;text-decoration:none;font-size:14px}footer{max-width:1400px;margin:25px auto 45px;padding:16px;color:#526970}body.present header,body.present details,body.present footer{display:none}body.present main{padding:0;margin:0;max-width:none}body.present section{display:none;margin:0;box-shadow:none;height:100vh;background:#18343d}body.present section.active{display:flex;align-items:center;justify-content:center}body.present svg{max-width:100vw;max-height:100vh}@page{size:landscape;margin:0}@media print{header,details,footer{display:none}body,main{margin:0;padding:0;background:white;max-width:none}section{box-shadow:none;margin:0;page-break-after:always;break-after:page}section svg{width:100%}}
</style></head><body><header><strong>SCE项目阶段性汇报 · 修订版</strong><span>15页主讲 + 6页附录 · 2026.10.15</span><button id="present">演示模式</button><button onclick="window.print()">打印 / 另存为PDF</button><span>演示中：← →翻页，Esc返回</span></header><details><summary>逐页目录</summary><nav>'''+nav+'''</nav></details><main>'''+body+'''</main><footer>来源链接：'''+linkhtml+'''<p>图表使用已有数据，不新增模拟。本修订版补充SCE背景、信息边界和八期结果，中文楷体，英文及数字Times New Roman。</p></footer><script>
let pages=[...document.querySelectorAll('section')],current=0;function show(i){current=Math.max(0,Math.min(pages.length-1,i));pages.forEach((p,j)=>p.classList.toggle('active',j===current))}document.querySelector('#present').onclick=()=>{current=Math.max(0,pages.findIndex(p=>p.getBoundingClientRect().bottom>90));document.body.classList.add('present');show(current)};document.addEventListener('keydown',e=>{if(!document.body.classList.contains('present'))return;if(['ArrowRight','PageDown',' '].includes(e.key)){show(current+1);e.preventDefault()}if(['ArrowLeft','PageUp'].includes(e.key)){show(current-1);e.preventDefault()}if(e.key==='Escape'){document.body.classList.remove('present');pages[current].scrollIntoView()}});
</script></body></html>'''
    (OUT/"index.html").write_text(html_doc)
    notes="\n\n".join(f'## {a["number"]:02} {a["title"]}\n\n'+"\n\n".join(a["text"][:-3]) for a in pages)
    (SRC/"content.md").write_text("# SCE项目阶段性汇报 · 修订版\n\n15页主讲、6页附录；2026-10-15。图文同源，派生稿的正文如下。\n\n"+notes+"\n")
    manifest={"date":"2026-10-15","pages":len(pages),"main_pages":15,"appendix_pages":6,
              "new_api_calls":0,"pdf":str(PDF.relative_to(ROOT)),"html":str((OUT/"index.html").relative_to(ROOT)),
              "pdf_sha256":hashlib.sha256(PDF.read_bytes()).hexdigest(),
              "html_sha256":hashlib.sha256((OUT/"index.html").read_bytes()).hexdigest(),
              "aggregate_source":"aggregate_data.json","status":"draft_v2_rendered_awaiting_visual_qa",
              "fonts":{"Chinese":"Kaiti SC","Latin_and_numbers":"Times New Roman"}}
    (SRC/"delivery.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(manifest,ensure_ascii=False))


if __name__=="__main__":render()
