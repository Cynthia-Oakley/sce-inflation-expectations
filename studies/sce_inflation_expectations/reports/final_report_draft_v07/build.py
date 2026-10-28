from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "sce_report_v07_mpl"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "docs/reports/final_report_draft_v07"
BLUE, ORANGE, BLACK, GREY = "#1769aa", "#c46a16", "#252b33", "#787f88"
LAMBDA_FULL = 0.159249952
LAMBDA_EARLY = 0.133976257


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def mean_absolute_error(data: list[dict[str, str]], field: str) -> float:
    return float(np.mean([abs(float(row[field]) - float(row["truth_pp"])) for row in data]))


def combined(row: dict[str, str], weight: float) -> float:
    return (1 - weight) * float(row["anchor_pp"]) + weight * float(row["sim_pp"])


def descriptive_mae(data: list[dict[str, str]]) -> float:
    return float(np.mean([abs(combined(row, LAMBDA_FULL) - float(row["truth_pp"])) for row in data]))


def month(value: str) -> str:
    value = str(value).replace("-", "")
    return value[:4] + "-" + value[4:6]


def figure_style() -> None:
    cn = ROOT / "outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf"
    if cn.exists():
        font_manager.fontManager.addfont(str(cn))
    plt.rcParams.update({
        "font.family": ["DejaVu Sans", "Kaiti SC"], "font.size": 11,
        "axes.unicode_minus": False, "axes.spines.top": False,
        "axes.spines.right": False, "axes.titlesize": 13,
        "legend.fontsize": 9, "svg.fonttype": "path",
    })


def save(fig: plt.Figure, stem: str) -> None:
    fig.savefig(OUT / "assets" / f"{stem}.png", dpi=190, bbox_inches="tight")
    fig.savefig(OUT / "assets" / f"{stem}.svg", bbox_inches="tight")
    plt.close(fig)


def line_plot(ax: plt.Axes, data: list[dict[str, str]], series: list[tuple], title: str) -> None:
    x = np.arange(len(data))
    for key, label, color, style in series:
        ax.plot(x, [float(row[key]) for row in data], color=color, label=label,
                ls=style, lw=1.8, marker="o" if len(data) <= 12 else None, ms=3.5)
    ticks = list(range(len(data))) if len(data) <= 12 else list(range(0, len(data), 12)) + [len(data) - 1]
    ax.set_xticks(ticks, [month(data[i]["month"]) for i in ticks], rotation=25, ha="right", fontsize=8.5)
    ax.set(xlabel="调查目标月", ylabel="一年期通胀预期（%）", title=title)
    ax.grid(axis="y", alpha=.16)
    ax.legend(frameon=False, ncol=2, loc="upper left")


def build_figures() -> dict[str, str]:
    (OUT / "assets").mkdir(parents=True, exist_ok=True)
    package = ROOT / "deliverables/research_package/v05/package/studies/sce_inflation_expectations/reproduction_data"
    a = rows(ROOT / "outputs/sce_full_a_t0_readout_20261026_v1/monthly_national.csv")
    comparison = json.loads((package / "A82_comparison_summary.json").read_text())
    grids = json.loads((ROOT / "outputs/sce_grid_dimensions_20261023_v1/summary.json").read_text())
    weekly = rows(package / "weekly47_path.csv")
    weekly_primary = rows(package / "weekly47_monthly11_primary.csv")
    downstream = rows(package / "downstream_model_metrics.csv")
    figure_style()
    hashes: dict[str, str] = {}

    for source, target in [
        (ROOT / "docs/reports/final_report_draft_v05/assets/q9_observed_example.png", "real_q9.png"),
        (ROOT / "docs/reports/final_report_draft_v05/assets/information_routes.png", "information_routes.png"),
    ]:
        shutil.copyfile(source, OUT / "assets" / target)
        hashes[target] = digest(source)

    fig, axes = plt.subplots(1, 2, figsize=(12.4, 3.8), layout="constrained")
    names = ["education", "numeracy", "income", "age", "employment", "gender", "housing", "region"]
    labels = ["学历", "数理", "收入", "年龄", "就业", "性别", "住房", "地区"]
    uncertainty = [100 * grids["conditional_information"][n]["development_domain_loss_increase"]["uncertainty"] for n in names]
    axes[0].barh(labels[::-1], uncertainty[::-1], color=BLUE, height=.65)
    axes[0].set(xlabel="移除此变量后的损失上升（标准化损失百分点）", title="人口信息主要帮助解释概率宽度")
    axes[0].grid(axis="x", alpha=.15)
    for y, value in enumerate(uncertainty[::-1]):
        axes[0].text(value + .04, y, f"{value:.2f}", va="center", fontsize=9)
    eigen = grids["associations"]["development"]["mca"]["raw_inertia_fraction"]
    axes[1].plot(range(1, len(eigen) + 1), np.array(eigen) * 100, marker="o", color=ORANGE)
    axes[1].set(xlabel="多重对应分析的轴序号", ylabel="原始惯量比例（%）", title="人口特征共变，不代表问卷解释率")
    axes[1].grid(alpha=.15)
    save(fig, "grid_basis")

    fig, axes = plt.subplots(2, 1, figsize=(12.4, 7.1), layout="constrained")
    series = [
        ("truth_pp", "真实SCE（评价真值）", BLACK, "-"),
        ("sim_pp", "调整后的输入方案", BLUE, "-"),
        ("old_same_roster_pp", "调整前的输入方案", ORANGE, "-"),
        ("anchor_pp", "上月已公布全国值", GREY, "--"),
    ]
    line_plot(axes[0], a, series, "2019-01—2025-10：不同通胀阶段的全国中心")
    line_plot(axes[1], [r for r in a if r["month"].startswith("2021")], series,
              "2021年：低估有所减轻，仍未跟上全部上行")
    save(fig, "a82_path")

    same = comparison["same_roster"]["metrics"]
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 3.7), layout="constrained")
    values = [same["old"]["q9"]["cross_section_w1_pp"], same["new"]["q9"]["cross_section_w1_pp"]]
    bars = axes[0].bar(["调整前", "调整后"], values, color=[ORANGE, BLUE], width=.55)
    axes[0].set(ylabel="W1距离（百分点，越低越接近）", title="分布距离略有上升", ylim=(0, 2.8))
    for bar, value in zip(bars, values):
        axes[0].text(bar.get_x() + bar.get_width() / 2, value + .04, f"{value:.3f}", ha="center")
    values = [same["old"]["q9"]["cross_person_iqr_pp"], same["new"]["q9"]["cross_person_iqr_pp"], same["new"]["q9"]["real_cross_person_iqr_pp"]]
    bars = axes[1].bar(["调整前", "调整后", "真实受访者"], values, color=[ORANGE, BLUE, BLACK], width=.6)
    axes[1].set(ylabel="跨人IQR（百分点）", title="家庭间分歧仍然偏窄", ylim=(0, 6.2))
    for bar, value in zip(bars, values):
        axes[1].text(bar.get_x() + bar.get_width() / 2, value + .07, f"{value:.3f}", ha="center")
    save(fig, "a82_micro")

    fig, axes = plt.subplots(2, 1, figsize=(12.4, 6.8), layout="constrained")
    dates = [datetime.fromisoformat(row["cutoff"]).replace(tzinfo=None) for row in weekly]
    axes[0].plot(dates, [float(row["q9_median_pp"]) for row in weekly], color=BLUE, marker=".", lw=1.8, label="周度模型直接输出")
    last = {}
    for date, row in zip(dates, weekly):
        last[row["month"]] = date
    end = [last[month(row["month"])] for row in weekly_primary]
    axes[0].plot(end, [float(row["truth_pp"]) for row in weekly_primary], color=BLACK, marker="o", lw=1.4, label="当月真实SCE（事后评价）")
    axes[0].plot(end, [float(row["blend_pp"]) for row in weekly_primary], color=ORANGE, marker="s", lw=1.2, ls="--", label="月内最后周点的固定比例组合")
    reset = [(d, r) for d, r in zip(dates, weekly) if r["reset_required"] == "True"]
    axes[0].scatter([d for d, _ in reset], [float(r["q9_median_pp"]) for _, r in reset], facecolors="white", edgecolors=BLUE, s=40, zorder=4, label="公开历史值发布后的重校准周")
    axes[0].set(xlabel="周截止（每周五纽约日末）", ylabel="一年期通胀预期（%）", title="2025-11-07—2026-09-25：发布后校准，发布间沿前态更新")
    axes[0].legend(frameon=False, ncol=2)
    axes[0].grid(alpha=.15)
    axes[0].xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    axes[0].tick_params(axis="x", rotation=20, labelsize=8.5)
    for field, title, color in [("raw_pp", "模型直接输出", BLUE), ("blend_pp", "固定比例组合", ORANGE), ("anchor_pp", "上月已公布全国值", GREY)]:
        axes[1].plot(range(11), [abs(float(row[field]) - float(row["truth_pp"])) for row in weekly_primary], color=color, label=title, marker="o")
    axes[1].set_xticks(range(11), [month(row["month"]) for row in weekly_primary], rotation=25, ha="right", fontsize=8.5)
    axes[1].set(xlabel="目标月（取最后预定周点）", ylabel="绝对误差（百分点）", title="11个月主评价：5个月改善、6个月退步")
    axes[1].legend(frameon=False, ncol=3)
    axes[1].grid(axis="y", alpha=.15)
    save(fig, "weekly47")

    outcomes = ["REVOLSL", "wage_growth_overall", "PCEDGC96", "MICH"]
    outcome_labels = ["循环信贷", "工资增长", "实际耐用品消费", "Michigan通胀预期"]
    by = {(r["outcome"], int(r["horizon"]), r["model"]): r for r in downstream if r["scope"] == "A"}
    improvement = [[100 * (1 - float(by[o, h, "simulated_sce"]["rmse"]) / float(by[o, h, "official_sce"]["rmse"])) for h in [1, 2, 3]] for o in outcomes]
    blend_gain = [100 * (1 - float(by["REVOLSL", h, "blended_sce"]["rmse"]) / float(by["REVOLSL", h, "official_sce"]["rmse"])) for h in [1, 2, 3]]
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.0), layout="constrained", gridspec_kw={"width_ratios": [1, 1.1]})
    for values, label, color in [(improvement[0], "模型直接输出替代官方SCE", BLUE), (blend_gain, "固定比例组合替代官方SCE", ORANGE)]:
        axes[0].plot([1, 2, 3], values, marker="o", color=color, lw=2, label=label)
        for h, value in zip([1, 2, 3], values):
            axes[0].annotate(f"{value:+.2f}%", (h, value), xytext=(0, 8 if color == BLUE else -17), textcoords="offset points", ha="center", fontsize=9)
    axes[0].axhline(0, color=GREY, ls="--")
    axes[0].set_xticks([1, 2, 3])
    axes[0].set(xlabel="预测期（月）", ylabel="RMSE相对改善（%）", title="循环信贷：部分期限有所改善")
    axes[0].legend(frameon=False, loc="upper left", fontsize=8.5)
    axes[0].set_ylim(-6, 12)
    axes[0].grid(axis="y", alpha=.15)
    matrix = np.array(improvement)
    bound = max(abs(matrix.min()), abs(matrix.max()), 1)
    cmap = LinearSegmentedColormap.from_list("gain", ["#cb6116", "#f8f7f3", "#1769aa"])
    image = axes[1].imshow(matrix, cmap=cmap, norm=TwoSlopeNorm(vmin=-bound, vcenter=0, vmax=bound), aspect="auto")
    axes[1].set_yticks(range(4), outcome_labels)
    axes[1].set_xticks(range(3), ["1个月", "2个月", "3个月"])
    axes[1].set(xlabel="预测期", ylabel="下游结局", title="全部12项模型直接输出对照：5项改善")
    for i in range(4):
        for j in range(3):
            axes[1].text(j, i, f"{matrix[i, j]:+.2f}%", ha="center", va="center", color="white" if abs(matrix[i, j]) > bound * .55 else BLACK, fontsize=9)
    fig.colorbar(image, ax=axes[1], label="RMSE改善（%，正值为好）", shrink=.85)
    save(fig, "downstream_credit")

    for path in (OUT / "assets").glob("*.png"):
        hashes[path.name] = digest(path)
    return hashes


def math_run(text: str):
    run = OxmlElement("m:r")
    props = OxmlElement("m:rPr")
    style = OxmlElement("m:sty")
    style.set(qn("m:val"), "p")
    props.append(style)
    run.append(props)
    node = OxmlElement("m:t")
    node.text = text
    run.append(node)
    return run


def math_sub(base: str, sub: str):
    node = OxmlElement("m:sSub")
    for tag, value in [("m:e", base), ("m:sub", sub)]:
        part = OxmlElement(tag)
        part.append(math_run(value))
        node.append(part)
    return node


def math_fraction(numerator: list, denominator: list):
    node = OxmlElement("m:f")
    for tag, content in [("m:num", numerator), ("m:den", denominator)]:
        part = OxmlElement(tag)
        for item in content:
            part.append(item)
        node.append(part)
    return node


def append_math(paragraph, latex: str) -> None:
    math = OxmlElement("m:oMath")
    if latex.startswith("w^{*}"):
        items = [math_sub("w", "*"), math_run("(i)="), math_fraction([math_run("w(i)")], [math_run("π(i)")]), math_run("c(g)")]
    elif latex.startswith("c_t"):
        items = [math_sub("c", "t"), math_run("=(1−λ)"), math_sub("b", "t"), math_run("+λ"), math_sub("m", "t")]
    else:
        items = [math_run("P(g)="), math_fraction([math_sub("n", "eff")], [math_sub("n", "eff"), math_run("+τ")]), math_run("P(local)+"), math_fraction([math_run("τ")], [math_sub("n", "eff"), math_run("+τ")]), math_run("P(parent)")]
    for item in items:
        math.append(item)
    paragraph._p.append(math)


def set_run_font(run, size: float, bold: bool | None = None, color: str | None = None) -> None:
    run.font.name = "Times New Roman"
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "KaiTi")
    run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def add_inline(paragraph, text: str, size: float = 10.5) -> None:
    for piece in re.split(r"(\*\*.*?\*\*)", text):
        if not piece:
            continue
        bold = piece.startswith("**") and piece.endswith("**")
        content = piece[2:-2] if bold else piece
        set_run_font(paragraph.add_run(content), size, bold=bold)


def body_paragraph(doc: Document, text: str, size: float = 10.5, indent: bool = True):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    fmt = paragraph.paragraph_format
    fmt.line_spacing = 1.04
    fmt.space_after = Pt(2.4)
    if indent:
        fmt.first_line_indent = Pt(size * 2)
    add_inline(paragraph, text, size)
    return paragraph


def add_table(doc: Document, lines: list[str]) -> None:
    parsed = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    parsed.pop(1)
    table = doc.add_table(rows=len(parsed), cols=len(parsed[0]))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    table.style = "Table Grid"
    for i, row in enumerate(parsed):
        for j, text in enumerate(row):
            cell = table.cell(i, j)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if i == 0 or j > 0 else WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            add_inline(p, text, 7.7 if len(parsed[0]) == 3 else 8.2)
            if i == 0:
                for run in p.runs:
                    run.bold = True
                shading = OxmlElement("w:shd")
                shading.set(qn("w:fill"), "EAF0F4")
                cell._tc.get_or_add_tcPr().append(shading)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def add_page_number(section) -> None:
    paragraph = section.footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, instruction, end])
    set_run_font(run, 8)


def build_docx() -> Path:
    text = (HERE / "manuscript.md").read_text()
    lines = text.splitlines()
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(1.45), Cm(1.35)
    section.left_margin, section.right_margin = Cm(1.65), Cm(1.65)
    section.header_distance, section.footer_distance = Cm(.55), Cm(.55)
    add_page_number(section)
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "KaiTi")
    normal.font.size = Pt(10.5)
    for name, size in [("Title", 19), ("Heading 1", 13), ("Heading 2", 11.5)]:
        style = doc.styles[name]
        style.font.name = "Times New Roman"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "KaiTi")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string("172C3D")

    i = 0
    image_widths = {"real_q9.png": 16.4, "grid_basis.png": 15.0, "information_routes.png": 13.4, "a82_path.png": 15.6, "a82_micro.png": 14.9, "weekly47.png": 15.4, "downstream_credit.png": 15.5}
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line == "\\newpage":
            doc.add_page_break()
        elif line.startswith("# "):
            p = doc.add_paragraph(style="Title")
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(3)
            add_inline(p, line[2:], 19)
        elif line.startswith("## "):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(5)
            add_inline(p, line[3:], 13)
            for run in p.runs:
                run.bold = True
        elif line.startswith("### "):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(5)
            p.paragraph_format.space_after = Pt(2.5)
            p.paragraph_format.keep_with_next = True
            add_inline(p, line[4:], 12)
            for run in p.runs:
                run.bold = True
                run.font.color.rgb = RGBColor.from_string("172C3D")
        elif line.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            add_table(doc, table_lines)
            continue
        elif line.startswith("!["):
            match = re.match(r"!\[(.*)\]\(assets/(.*)\)", line)
            caption, image = match.groups()
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(1)
            p.add_run().add_picture(str(OUT / "assets" / image), width=Cm(image_widths[image]))
            cap = doc.add_paragraph()
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cap.paragraph_format.space_after = Pt(2.5)
            add_inline(cap, caption, 8.2)
        elif line.startswith("$$"):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(3)
            append_math(p, line.strip("$"))
        elif line.startswith("水上挽月") or line.startswith("作者审阅稿"):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(2)
            add_inline(p, line.rstrip("  "), 9)
        elif re.match(r"^\[\d+\]", line):
            p = body_paragraph(doc, line, size=7.6, indent=False)
            p.paragraph_format.space_after = Pt(1.3)
            p.paragraph_format.line_spacing = 1.0
        elif line.startswith("注："):
            body_paragraph(doc, line, size=8.0, indent=False)
        else:
            body_paragraph(doc, line)
        i += 1

    path = OUT / "SCE研究报告_作者审阅稿_v07.docx"
    doc.save(path)
    return path


def verify(docx_path: Path, figure_hashes: dict[str, str]) -> dict:
    source = (HERE / "manuscript.md").read_text()
    a = rows(ROOT / "outputs/sce_full_a_t0_readout_20261026_v1/monthly_national.csv")
    year2021 = [row for row in a if row["month"].startswith("2021")]
    calculations = {
        "A82_direct_mae": mean_absolute_error(a, "sim_pp"),
        "A82_descriptive_combined_mae": descriptive_mae(a),
        "2021_descriptive_combined_mae": descriptive_mae(year2021),
        "A82_baseline_mae": mean_absolute_error(a, "anchor_pp"),
        "2021_baseline_mae": mean_absolute_error(year2021, "anchor_pp"),
    }
    expected = [0.298407, 0.222331, 0.365199, 0.223171, 0.325]
    for actual, target in zip(calculations.values(), expected):
        assert abs(actual - target) < 0.00001, (actual, target)
    required = ["2019年1月至2025年10月", "2025年11月至2026年9月", "2025年11月7日至2026年9月25日", "滞后九个月", "0.013272", "0.026928", "0.365", "2019-01—2022-12", "普通最小二乘"]
    banned = ["我们", "旧A", "新版T0", "冻结组合", "公开历史参照", "原始模拟", "持续性基线", "警示内容不额外加权", "normal_expansion.png"]
    for phrase in required:
        assert phrase in source, phrase
    for phrase in banned:
        assert phrase not in source, phrase
    assert source.count("![") == 7
    assert source.count("$$") == 6
    with zipfile.ZipFile(docx_path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
        assert xml.count("<m:oMath>") == 3
        assert xml.count("<w:br w:type=\"page\"") == 4
        assert len([name for name in archive.namelist() if name.startswith("word/media/")]) == 7
        assert "我们" not in xml
    reopened = Document(docx_path)
    assert len(reopened.inline_shapes) == 7
    shutil.copyfile(HERE / "manuscript.md", OUT / "manuscript.md")
    result = {
        "status": "docx_structural_and_numeric_acceptance_passed",
        "date": "2026-10-27",
        "docx": docx_path.name,
        "docx_sha256": digest(docx_path),
        "figures": 7,
        "native_editable_equations": 3,
        "explicit_page_breaks": 4,
        "calculations": calculations,
        "figure_sha256": figure_hashes,
        "new_model_calls": 0,
        "new_parameter_estimation": False,
        "visual_acceptance": "pending_word_rendering",
        "notes": "Word为交付物，未生成新版PDF。页数需在Word排版引擎中核验；不得用隐式分页数声称恰好8页。",
    }
    (OUT / "acceptance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-figures", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    hashes = build_figures() if not args.skip_figures else {p.name: digest(p) for p in (OUT / "assets").glob("*.png")}
    docx = build_docx()
    result = verify(docx, hashes)
    print(json.dumps({"docx": str(docx), "status": result["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
