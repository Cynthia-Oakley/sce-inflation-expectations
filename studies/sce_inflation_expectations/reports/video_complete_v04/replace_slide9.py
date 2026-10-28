"""Transplant only the new slide 9 into the author's saved PPTX.

The original slides/notes 1–8, chart label subtrees and embedded workbook bytes
remain untouched. WPS series-title formulas and one-series grouping are made
valid OOXML without changing values, label settings or appearance.
"""
from pathlib import Path
import hashlib
import json
import posixpath
import re
import sys
import zipfile
from lxml import etree as ET

REL='http://schemas.openxmlformats.org/package/2006/relationships'
CT='http://schemas.openxmlformats.org/package/2006/content-types'
C='http://schemas.openxmlformats.org/drawingml/2006/chart'
ns={'c':C}
digest=lambda b:hashlib.sha256(b).hexdigest()


def relpart(p):
    d,b=posixpath.split(p)
    return posixpath.join(d,'_rels',b+'.rels')


def resolve(p,target):return posixpath.normpath(posixpath.join(posixpath.dirname(p),target)).lstrip('/')


def serialize(tree):return ET.tostring(tree,encoding='UTF-8',xml_declaration=True,standalone=True)


def normalize_chart(blob,name,repairs):
    tree=ET.fromstring(blob);modified=False
    for g in tree.findall('.//c:barChart/c:grouping',ns):
        if g.attrib.get('val')=='none':
            g.attrib['val']='clustered';modified=True
            repairs.append(dict(part=name,field='single_series_bar_grouping',before='none',after='clustered'))
    for ser in tree.findall('.//c:ser',ns):
        title=ser.find('c:tx/c:strRef/c:f',ns)
        value=ser.find('c:val/c:numRef/c:f',ns)
        if value is None:value=ser.find('c:yVal/c:numRef/c:f',ns)
        if title is not None and '!' not in (title.text or '') and value is not None:
            before=title.text;title.text=re.sub(r'\$?\d+$','$1',value.text.split(':')[0]);modified=True
            repairs.append(dict(part=name,field='series_title_cell_reference',before=before,after=title.text))
    return serialize(tree) if modified else blob


def main(base,newslide,out,receipt):
    with zipfile.ZipFile(base) as z:old={n:z.read(n) for n in z.namelist()}
    with zipfile.ZipFile(newslide) as z:fresh={n:z.read(n) for n in z.namelist()}
    merged=dict(old);mapping={'ppt/slides/slide1.xml':'ppt/slides/slide9.xml'};copied=set()

    def copy(p):
        if p in copied:return mapping[p]
        if p not in mapping:
            d,b=posixpath.split(p);mapping[p]=posixpath.join(d,'sce_v04_'+b)
        target=mapping[p];copied.add(p);merged[target]=fresh[p]
        rp=relpart(p)
        if rp in fresh:
            root=ET.fromstring(fresh[rp])
            for r in root:
                if r.attrib.get('TargetMode')=='External':continue
                dest=copy(resolve(p,r.attrib['Target']))
                r.attrib['Target']=posixpath.relpath(dest,posixpath.dirname(target))
            merged[relpart(target)]=serialize(root)
        return target

    copy('ppt/slides/slide1.xml')
    types=ET.fromstring(old['[Content_Types].xml']);extra=ET.fromstring(fresh['[Content_Types].xml'])
    default={e.attrib.get('Extension') for e in types if ET.QName(e).localname=='Default'}
    overrides={e.attrib.get('PartName') for e in types if ET.QName(e).localname=='Override'}
    for e in extra:
        if ET.QName(e).localname=='Default' and e.attrib['Extension'] not in default:
            types.append(e);default.add(e.attrib['Extension'])
        elif ET.QName(e).localname=='Override' and e.attrib['PartName'].lstrip('/') in mapping:
            dest='/'+mapping[e.attrib['PartName'].lstrip('/')]
            if dest not in overrides:
                clone=ET.fromstring(serialize(e));clone.attrib['PartName']=dest;types.append(clone);overrides.add(dest)
    # Remove exclusively old slide-9 parts now unreachable from the OPC root.
    keep={'[Content_Types].xml','_rels/.rels'}
    def walk(p):
        if p in keep:return
        assert p in merged,p
        keep.add(p);rp=relpart(p)
        if rp not in merged:return
        keep.add(rp)
        for r in ET.fromstring(merged[rp]):
            if r.attrib.get('TargetMode')!='External':walk(resolve(p,r.attrib['Target']))
    for r in ET.fromstring(merged['_rels/.rels']):
        if r.attrib.get('TargetMode')!='External':walk(resolve('',r.attrib['Target']))
    removed=sorted(set(merged)-keep)
    merged={p:b for p,b in merged.items() if p in keep}
    for e in list(types):
        if ET.QName(e).localname=='Override' and e.attrib['PartName'].lstrip('/') not in merged:types.remove(e)
    merged['[Content_Types].xml']=serialize(types)
    repairs=[]
    for p,blob in list(merged.items()):
        if re.search(r'/charts/[^/]+\.xml$',p):merged[p]=normalize_chart(blob,p,repairs)
    protected=[]
    for page in range(1,9):
        for p in [f'ppt/slides/slide{page}.xml',f'ppt/slides/_rels/slide{page}.xml.rels',f'ppt/notesSlides/notesSlide{page}.xml']:
            if p in old:assert old[p]==merged[p],p;protected.append(p)
    for p,blob in old.items():
        if '/embeddings/' in p and p in merged:assert blob==merged[p],p
        if '/charts/' in p and p.endswith('.xml') and p in merged:
            a=ET.fromstring(blob);b=ET.fromstring(merged[p])
            for tag in ['dLbls','catAx','valAx','spPr','numCache','strCache']:
                oldnodes=a.findall('.//c:'+tag,ns);newnodes=b.findall('.//c:'+tag,ns)
                assert [ET.tostring(e) for e in oldnodes]==[ET.tostring(e) for e in newnodes],(p,tag)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for p,blob in merged.items():z.writestr(p,blob)
    r=dict(source_sha256=digest(Path(base).read_bytes()),slides_1_to_8_xml_preserved=True,
           original_chart_label_and_cache_subtrees_preserved=True,original_workbooks_preserved=True,
           unchanged_parts_checked=protected,part_mapping=mapping,removed_orphan_parts=removed,compatibility_repairs=repairs)
    Path(receipt).write_text(json.dumps(r,ensure_ascii=False,indent=2))
    print(json.dumps(dict(source_slides_preserved=8,new_slide=9,compatibility_repairs=len(repairs))))


if __name__=='__main__':main(*sys.argv[1:5])
