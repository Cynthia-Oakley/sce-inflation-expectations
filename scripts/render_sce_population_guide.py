#!/usr/bin/env python3
"""Render the requested fixed reading handout, not simulation code or inputs."""
from html import escape
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'docs/SCE_POPULATION_GUIDE_20261015.md'
PDF = ROOT/'output/pdf/sce_population_guide_20261015.pdf'
TXT = ROOT/'docs/sce_population_guide_20261015.txt'


def main():
    text = SOURCE.read_text()
    pdfmetrics.registerFont(TTFont('GuideChinese', '/Library/Fonts/Arial Unicode.ttf'))
    pdfmetrics.registerFont(TTFont('GuideEnglish', '/System/Library/Fonts/Supplemental/Times New Roman.ttf'))
    styles = {
        'body': ParagraphStyle('body', fontName='GuideChinese', fontSize=10, leading=15,
            spaceAfter=6, wordWrap='CJK', alignment=TA_LEFT),
        'english': ParagraphStyle('english', fontName='GuideEnglish', fontSize=10.5, leading=14,
            spaceAfter=7),
        'h1': ParagraphStyle('h1', fontName='GuideChinese', fontSize=18, leading=24,
            textColor=colors.HexColor('#224e45'), spaceAfter=13, keepWithNext=True),
        'h2': ParagraphStyle('h2', fontName='GuideChinese', fontSize=13, leading=19,
            textColor=colors.HexColor('#224e45'), spaceBefore=7, spaceAfter=8, keepWithNext=True),
        'h3': ParagraphStyle('h3', fontName='GuideChinese', fontSize=11, leading=16,
            spaceBefore=6, spaceAfter=6, keepWithNext=True),
    }
    flow = []
    for block in text.split('\n\n'):
        block = block.strip()
        if not block:
            continue
        if block == '<!-- pagebreak -->':
            flow.append(PageBreak()); continue
        if block.startswith('#'):
            level = len(block)-len(block.lstrip('#'))
            flow.append(Paragraph(escape(block[level:].strip()), styles['h'+str(level)])); continue
        lines = block.splitlines()
        if all(re.match(r'^(?:- |\d+\. )', line) for line in lines):
            for line in lines:
                flow.append(Paragraph(escape(line.removeprefix('- ')), styles['body']))
        else:
            english = block.startswith(('In your earlier', 'You answered', 'In that survey'))
            flow.append(Paragraph(escape(' '.join(lines)), styles['english' if english else 'body']))
    PDF.parent.mkdir(parents=True, exist_ok=True)
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('GuideChinese', 8)
        canvas.setFillColor(colors.HexColor('#65716c'))
        canvas.drawString(43, 27, 'SCE人口资料 | 水上挽月 | 2026-10-15')
        canvas.drawRightString(A4[0]-43, 27, str(doc.page))
        canvas.restoreState()
    SimpleDocTemplate(str(PDF), pagesize=A4, leftMargin=43, rightMargin=43,
        topMargin=37, bottomMargin=43, title='SCE人口资料：原题、公开编码与提示词',
        author='水上挽月项目', allowSplitting=True).build(flow, onFirstPage=footer, onLaterPages=footer)
    plain = re.sub(r'^#{1,3} ', '', text, flags=re.M).replace('<!-- pagebreak -->', '\n'+'='*54+'\n')
    TXT.write_text(plain)
    print(PDF)
    print(TXT)


if __name__ == '__main__':
    main()
