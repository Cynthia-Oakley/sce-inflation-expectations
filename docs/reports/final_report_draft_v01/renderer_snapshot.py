"""Render an eight-page article PDF and HTML reader from one manuscript.

This is typesetting, not simulation or evaluation. No API client, private
person-level records, density refitting, or scientific configuration mutation.
"""
from __future__ import annotations

import argparse
import hashlib
from html import escape
from itertools import groupby
import json
from pathlib import Path
import shutil

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[4]
SOURCE = Path(__file__).with_name("manuscript.json")
DEST = ROOT / "docs/reports/final_report_draft_v01"
PDF_NAME = "SCE研究报告_初稿_v01.pdf"
SOURCES = [
    "docs/workstreams/20261024_fullperiod_analysis/analysis_sources.json",
    "outputs/sce_fullperiod_analysis_20261024_v1/summary.json",
    "outputs/sce_2021_environment_blend_diagnostic_20261024_v2/summary.json",
    "docs/workstreams/20261023_main_run/mechanism_guide_20261024.json",
    "docs/workstreams/20261023_main_run/README.md",
    "docs/EXPERIMENT_STATUS_20261018.md",
    "docs/workstreams/20261021_fullperiod/news_matching_results_20261022.md",
    "docs/workstreams/20261019_advisor_followup/temperature_results_20261019.md",
    "docs/workstreams/20261016_cognition/results.md",
    "docs/workstreams/20261016_household_finance/results.md",
    "docs/workstreams/20261017_finance_validation/results.md",
    "docs/workstreams/20261018_psychological_waves/results.md",
    "docs/sources/challenge_requirements_20261024.json",
]
INK = colors.HexColor("#242424")
MUTED = colors.HexColor("#606060")
LINE = colors.HexColor("#d4d4d4")
ACCENT = colors.HexColor("#af5700")
PALE = colors.HexColor("#f4f5f7")
W, H = A4
MARGIN = 47
WIDTH = W - MARGIN * 2


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fonts():
    candidates = [
        ROOT / "outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf",
        Path("/Library/Fonts/Kaiti SC.ttf"),
    ]
    cn = next((p for p in candidates if p.exists()), None)
    if cn is None:
        raise FileNotFoundError("Set up a local embeddable Kaiti SC TTF for report typesetting")
    en = Path("/System/Library/Fonts/Supplemental/Times New Roman.ttf")
    pdfmetrics.registerFont(TTFont("ReportCN", str(cn)))
    pdfmetrics.registerFont(TTFont("ReportEN", str(en)))
    return {"Chinese": str(cn), "Latin": str(en),
            "font_files_redistributed": False}


def rich(text):
    glyphs = pdfmetrics.getFont("ReportEN").face.charToGlyph
    def which(c):
        return "ReportEN" if ord(c) < 0x2E80 and ord(c) in glyphs else "ReportCN"
    return "".join(f'<font name="{font}">{escape("".join(chars))}</font>'
                   for font, chars in groupby(str(text), key=which)).replace("\n", "<br/>")


def style(name="body", size=None):
    specs = {
        "body": (10.1, 15.0, 5.0),
        "abstract": (9.9, 14.7, 6.5),
        "h2": (12.1, 17.2, 6.0),
        "small": (8.7, 12.0, 5.0),
        "caption": (8.3, 11.3, 6.0),
        "reference": (8.0, 10.7, 3.0),
        "table": (9.1, 13.0, 0),
        "equation": (10.2, 15.0, 6.0),
        "note": (9.4, 13.7, 0),
        "title": (21, 28, 3),
        "subtitle": (14, 20, 7),
    }
    sz, lead, after = specs[name]
    if size:
        lead = lead * size / sz
        sz = size
    return ParagraphStyle(name, fontName="ReportCN", fontSize=sz, leading=lead,
                          textColor=INK if name not in {"small", "caption", "reference"} else MUTED,
                          alignment=TA_LEFT, wordWrap="CJK", spaceAfter=after,
                          splitLongWords=True, allowWidows=0, allowOrphans=0)


def para(text, kind="body", size=None):
    return Paragraph(rich(text), style(kind, size))


def table(block):
    widths = [WIDTH * x for x in block["widths"]]
    data = [[para(x, "table", block.get("size")) for x in row]
            for row in [block["headers"], *block["rows"]]]
    out = Table(data, colWidths=widths, hAlign="LEFT")
    out.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), PALE),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, INK),
        ("LINEBELOW", (0, 0), (-1, 0), 0.55, LINE),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return out


def image_block(block):
    path = ROOT / block["source"]
    iw, ih = ImageReader(str(path)).getSize()
    width = WIDTH * block.get("width", 1)
    height = width * ih / iw
    if height > block.get("max_height", 10000):
        height = block["max_height"]
        width = height * iw / ih
    im = Image(str(path), width, height)
    im.hAlign = "CENTER"
    return im


def flowables(block):
    kind = block["type"]
    if kind == "h2":
        return [Spacer(1, 6), para(block["text"], "h2")]
    if kind == "table":
        return [Spacer(1, 4), table(block), Spacer(1, 7)]
    if kind == "figure":
        return [image_block(block), Spacer(1, 3), para(block["caption"], "caption")]
    if kind == "reference":
        p = Paragraph(rich(f'[{block["id"]}] {block["text"]}') +
                      f' <link href="{escape(block["url"], quote=True)}" color="#245d9c">[链接]</link>', style("reference"))
        return [p]
    if kind == "note":
        box = Table([[para(block["text"], "note")]], colWidths=[WIDTH])
        box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), PALE),
            ("LINEBEFORE", (0, 0), (0, 0), 2, ACCENT),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        return [Spacer(1, 3), box, Spacer(1, 7)]
    return [para(block["text"], "body" if kind == "p" else kind)]


def write_pdf(manuscript, output):
    doc = canvas.Canvas(str(output), pagesize=A4, pageCompression=1, invariant=1)
    doc.setTitle(manuscript["title"] + "：" + manuscript["subtitle"])
    doc.setAuthor("水上挽月")
    records = []
    for number, page in enumerate(manuscript["pages"], 1):
        doc.setStrokeColor(LINE)
        doc.setLineWidth(0.4)
        doc.line(MARGIN, H - 35, W - MARGIN, H - 35)
        running = para("SCE研究报告 · 初稿 v0.1", "small")
        running.wrap(WIDTH / 2, 25)
        running.drawOn(doc, MARGIN, H - 27)
        label = para(page["title"], "small")
        lw, lh = label.wrap(WIDTH / 2, 25)
        label.drawOn(doc, W - MARGIN - WIDTH / 2, H - 27)
        y = H - 48
        items = []
        if number == 1:
            items.extend([para(manuscript["title"], "title"),
                          para(manuscript["subtitle"], "subtitle"),
                          para(manuscript["byline"], "small"),
                          para(manuscript["version"], "small"), Spacer(1, 3)])
        for block in page["blocks"]:
            items.extend(flowables(block))
        sizes = []
        for item in items:
            width, height = item.wrap(WIDTH, H)
            sizes.append((item, width, height, item.getSpaceAfter()))
        need = sum(height + after for _, _, height, after in sizes)
        available = y - 47
        records.append({"page": number, "content_height_pt": round(need, 2),
                        "available_height_pt": round(available, 2),
                        "bottom_clearance_pt": round(available - need, 2)})
        if need > available:
            raise ValueError(f"Page {number} overflows by {need - available:.1f} pt")
        for item, width, height, after in sizes:
            y -= height
            dx = MARGIN + (WIDTH - width) / 2 if isinstance(item, Image) else MARGIN
            item.drawOn(doc, dx, y)
            y -= after
        doc.line(MARGIN, 36, W - MARGIN, 36)
        footer = para("工作稿 · 近期预测评测及研究包验收待补 · 2026-10-24", "caption")
        footer.wrap(WIDTH - 45, 25)
        footer.drawOn(doc, MARGIN, 20)
        doc.setFont("ReportEN", 9)
        doc.setFillColor(MUTED)
        doc.drawRightString(W - MARGIN, 21, f"{number} / {len(manuscript['pages'])}")
        doc.showPage()
    doc.save()
    return records


def block_html(b):
    kind = b["type"]
    text = escape(b.get("text", "")).replace("\n", "<br>")
    if kind == "table":
        def row(xs, tag):
            return "<tr>" + "".join(f"<{tag}>{escape(x).replace(chr(10), '<br>')}</{tag}>" for x in xs) + "</tr>"
        return '<table><thead>' + row(b["headers"], "th") + '</thead><tbody>' + ''.join(row(r, "td") for r in b["rows"]) + '</tbody></table>'
    if kind == "figure":
        return f'<figure><img src="assets/{b["asset"]}" alt="{escape(b["caption"], quote=True)}"><figcaption>{escape(b["caption"])}</figcaption></figure>'
    if kind == "reference":
        return f'<p class="reference">[{b["id"]}] {text} <a href="{escape(b["url"], quote=True)}">原文</a></p>'
    tag = "h2" if kind == "h2" else "aside" if kind == "note" else "p"
    return f'<{tag} class="{kind}">{text}</{tag}>'


def write_reader(manuscript, destination):
    pages = []
    md = [f'# {manuscript["title"]}\n\n{manuscript["subtitle"]}\n\n{manuscript["version"]}\n\n{manuscript["status"]}\n']
    for n, page in enumerate(manuscript["pages"], 1):
        cover = '' if n > 1 else f'<h1>{escape(manuscript["title"])}</h1><p class="subtitle">{escape(manuscript["subtitle"])}</p><p class="small">{escape(manuscript["byline"])}</p>'
        pages.append(f'<article id="page-{n}"><div class="page-label">第{n}页 · {escape(page["title"])}</div>{cover}' + ''.join(block_html(b) for b in page["blocks"]) + '</article>')
        md.append(f'\n## 第{n}页：{page["title"]}\n')
        for b in page["blocks"]:
            if b["type"] == "table":
                md.append(' | '.join(b["headers"]) + '\n' + '\n'.join('；'.join(x.replace('\n', ' ') for x in r) for r in b["rows"]))
            elif b["type"] == "figure":
                md.append(f'![{b["caption"]}](assets/{b["asset"]})')
            elif b["type"] == "reference":
                md.append(f'[{b["id"]}] {b["text"]} {b["url"]}')
            else:
                md.append(('### ' if b["type"] == "h2" else '') + b["text"])
    nav = ''.join(f'<a href="#page-{n}">{n}. {escape(p["title"])}</a>' for n,p in enumerate(manuscript["pages"],1))
    content = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(manuscript['title'])}｜研究报告初稿</title><style>
*{{box-sizing:border-box}}body{{margin:0;color:#242424;background:#ececea;font-family:"Times New Roman","Kaiti SC","STKaiti","KaiTi",serif;font-size:17px;line-height:1.8}}header{{background:#fff;border-bottom:1px solid #d4d4d4;padding:16px max(18px,calc((100% - 870px)/2));}}header p{{margin:5px 0}}a{{color:#245d9c}}nav{{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:14px;margin-top:10px}}main{{max-width:870px;margin:24px auto}}article{{padding:36px 46px 40px;background:#fff;margin-bottom:22px;scroll-margin-top:15px}}.page-label{{font-size:14px;color:#686868;border-bottom:1px solid #ddd;padding-bottom:9px}}h1{{font-size:29px;line-height:1.45;margin:22px 0 2px}}h2{{font-size:22px;line-height:1.45;margin:22px 0 10px}}p{{margin:10px 0}}.subtitle{{font-size:21px}}.small,.caption,figcaption{{font-size:14px;color:#606060;line-height:1.65}}.abstract{{font-size:16px;line-height:1.8}}aside{{padding:12px 16px;background:#f4f5f7;border-left:3px solid #af5700;font-size:16px;margin:18px 0}}table{{width:100%;border-collapse:collapse;table-layout:fixed;font-size:15px;line-height:1.65;margin:16px 0}}th,td{{text-align:left;vertical-align:top;border-bottom:1px solid #ddd;padding:9px 7px;overflow-wrap:anywhere}}th{{background:#f4f5f7}}figure{{margin:17px 0}}img{{display:block;width:100%;height:auto}}figcaption{{margin-top:6px}}.equation{{text-align:center;font-size:17px;padding:6px 0}}.reference{{font-size:13px;line-height:1.6;margin:7px 0}}@media(max-width:600px){{article{{padding:24px 18px}}main{{margin:12px auto}}table{{font-size:13px}}h1{{font-size:25px}}}}@media print{{header{{display:none}}body{{background:white}}article{{break-after:page;margin:0;padding:0}}}}
</style></head><body><header><strong>研究报告初稿 v0.1 · 8页PDF对应阅读稿</strong><p>{escape(manuscript['status'])}</p><a href="{PDF_NAME}">打开PDF</a> · <a href="manuscript.md">文字稿</a> · <a href="source_index.md">数据与图表索引</a><nav>{nav}</nav></header><main>{''.join(pages)}</main></body></html>'''
    (destination / "index.html").write_text(content)
    (destination / "manuscript.md").write_text('\n\n'.join(md) + '\n')


def source_index(destination):
    rows = ["# 初稿来源与待补说明", "\n正文唯一编辑源：studies/sce_inflation_expectations/reports/final_report_draft/manuscript.json。PDF、HTML和文字稿由同一内容生成。仅排版与引用既有汇总，不运行API、Q9计分或新回归。", "\n## 页与证据"]
    mapping = [
        (1, "研究背景", "纽约联储FAQ、Armantier2017、ConsumerSim及理论参考，均见正文链接"),
        (2, "P/E/B及权重", "docs/workstreams/20261023_main_run/README.md；mechanism_guide_20261024.json"),
        (3, "计分和时间边界", "scoring/sce_q9_frozen.py；evaluation/fullperiod_analysis.py；最终协议与来源索引"),
        (4, "机制取舍", "docs/EXPERIMENT_STATUS_20261018.md及其逐项实验结果；不跨支持拼接成绩"),
        (5, "全国结果", "outputs/sce_fullperiod_analysis_20261024_v1/summary.json：macro_whole、yearly、official_national"),
        (6, "微观和更新", "同上：fixed_roster、genuine_previous_only、update_summary、variance_summary、groups、regression"),
        (7, "2021诊断", "outputs/sce_2021_environment_blend_diagnostic_20261024_v2/summary.json；专项结果MD"),
        (8, "费用和限制", "主分析scope/quality；原始/两轮修复账本；待补项未预写成绩"),
    ]
    for page, topic, evidence in mapping:
        rows.append(f'- 第{page}页（{topic}）：{evidence}。')
    rows.extend(["\n## 当前未完成，不作虚假确认", "- 近期11个月B线暂停，是否使用Kimi新新闻机制待定；未启动新调用。", "- 研究包许可清单、独立解压验收、全开发成本总账、视频未完成。", "- Kimi媒体拓展/新测试和六项微观事实关键回归未在本轮复核，不拿未复核系数校准或写为已证实机制。", "- 全82月主结果与48/34月权重评价保留，后期不是全机制未见盲测。", "- 外部CE/ATUS固定年资料作A线合成机制，不认证历史当时可得；模型参数知识另列。", "\n## 复建", "运行scripts/render_sce_research_report.py；需要本机可嵌入楷体和Times New Roman、ReportLab，以及索引中的已有聚合图。该命令不需要API密钥。该排版依赖不是最终独立研究包已经通过验收的声明。"])
    (destination / "source_index.md").write_text('\n\n'.join(rows) + '\n')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEST)
    args = ap.parse_args(argv)
    destination = args.out.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "assets").mkdir(exist_ok=True)
    manuscript = json.loads(SOURCE.read_text())
    if len(manuscript["pages"]) > 8:
        raise ValueError("Competition report must not exceed eight pages")
    font_info = fonts()
    figures = []
    for page in manuscript["pages"]:
        for block in page["blocks"]:
            if block["type"] == "figure":
                shutil.copyfile(ROOT / block["source"], destination / "assets" / block["asset"])
                figures.append({"source": block["source"], "sha256": sha(ROOT / block["source"]), "asset": block["asset"]})
    pdf_dir = ROOT / "output/pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    canonical_pdf = pdf_dir / "sce_research_report_draft_v01.pdf"
    layout = write_pdf(manuscript, canonical_pdf)
    shutil.copyfile(canonical_pdf, destination / PDF_NAME)
    write_reader(manuscript, destination)
    source_index(destination)
    manifest = {
        "status": "draft_pending_recent_evaluation_and_research_package",
        "date": "2026-10-24", "pages": len(manuscript["pages"]),
        "new_api_calls": 0, "new_q9_fits": 0, "scientific_configuration_changes": 0,
        "manuscript_sha256": sha(SOURCE), "renderer_sha256": sha(Path(__file__)),
        "fonts": font_info, "layout": layout,
        "sources": [{"path": p, "sha256": sha(ROOT / p)} for p in SOURCES],
        "figures": figures, "pdf_sha256": sha(canonical_pdf),
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({"pdf": str(destination / PDF_NAME), "reader": str(destination / 'index.html'), "layout": layout}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
