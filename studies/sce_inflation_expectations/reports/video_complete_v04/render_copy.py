"""Normalize WPS-only label precedence for the PNG renderer, not the PPTX.

The native delivery preserves the author's actual chart labels. Artifact Tool's
PNG importer adds both WPS series and plot label defaults, and renders both
value and percent flags for bars. This private copy expresses the same intended
single percentage label explicitly, with zero labels suppressed.
"""
from pathlib import Path
import json
import sys
import zipfile
from lxml import etree as ET

C='http://schemas.openxmlformats.org/drawingml/2006/chart';ns={'c':C}


def main(source,out,receipt):
    with zipfile.ZipFile(source) as z:files={n:z.read(n) for n in z.namelist()}
    changes=[]
    for name,blob in list(files.items()):
        if not name.endswith('.xml') or '/charts/' not in name:continue
        tree=ET.fromstring(blob)
        for chart in tree.findall('.//c:barChart',ns):
            for series in chart.findall('c:ser',ns):
                d=series.find('c:dLbls',ns)
                if d is None or d.find('c:showPercent',ns) is None or d.find('c:showPercent',ns).attrib.get('val')!='1':continue
                parent=chart.find('c:dLbls',ns)
                if parent is not None:chart.remove(parent)
                for old in d.findall('c:showPercent',ns)+d.findall('c:showBubbleSize',ns):old.attrib['val']='0'
                fmt=d.find('c:numFmt',ns)
                if fmt is None:
                    fmt=ET.Element('{'+C+'}numFmt');position=next((i for i,e in enumerate(d) if ET.QName(e).localname not in ['dLbl','delete','layout','tx']),len(d));d.insert(position,fmt)
                fmt.attrib.update({'formatCode':'0"%"','sourceLinked':'0'})
                for point in d.findall('c:dLbl',ns):
                    idx=int(point.find('c:idx',ns).attrib['val'])
                    v=series.find(f'c:val/c:numRef/c:numCache/c:pt[@idx="{idx}"]/c:v',ns)
                    if v is not None and float(v.text)==0:
                        delete=point.find('c:delete',ns)
                        if delete is None:delete=ET.Element('{'+C+'}delete');point.insert(1,delete)
                        delete.attrib['val']='1'
                    for flag in point.findall('c:showPercent',ns)+point.findall('c:showBubbleSize',ns):flag.attrib['val']='0'
                changes.append(name)
        if name in changes:files[name]=ET.tostring(tree,encoding='UTF-8',xml_declaration=True,standalone=True)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,blob in files.items():z.writestr(name,blob)
    Path(receipt).write_text(json.dumps(dict(preview_only=True,delivered_pptx_modified=False,chart_label_inheritance_normalized=changes),indent=2))


if __name__=='__main__':main(*sys.argv[1:4])
