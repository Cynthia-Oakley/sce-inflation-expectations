"""Carry exact source chart XML/workbooks into an expanded Artifact Tool deck.

The importer preserves chart facades but not the embedded workbook bytes. This
copy restores the existing four genuine workbooks; it never synthesizes their
values or formulas. Source slides 1/3 become destination slides 2/5.
"""
from pathlib import Path
import hashlib
import json
import posixpath
import sys
import xml.etree.ElementTree as ET
import zipfile

NS={'r':'http://schemas.openxmlformats.org/package/2006/relationships',
    'c':'http://schemas.openxmlformats.org/drawingml/2006/chart',
    'rel':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
RELNS=NS['r'];CT='http://schemas.openxmlformats.org/package/2006/content-types'
sha=lambda b:hashlib.sha256(b).hexdigest()

def relpart(part):
    d,b=posixpath.split(part)
    return posixpath.join(d,'_rels',b+'.rels')

def resolve(part,target):return posixpath.normpath(posixpath.join(posixpath.dirname(part),target)).lstrip('/')

def chart_parts(files,slide):
    part=f'ppt/slides/slide{slide}.xml';root=ET.fromstring(files[part])
    rels={r.attrib['Id']:resolve(part,r.attrib['Target']) for r in ET.fromstring(files[relpart(part)])}
    return [rels[e.attrib['{'+NS['rel']+'}id']] for e in root.findall('.//c:chart',NS)]

def preserve(source,candidate,receipt):
    with zipfile.ZipFile(source) as z:old={n:z.read(n) for n in z.namelist()}
    with zipfile.ZipFile(candidate) as z:new={n:z.read(n) for n in z.namelist()}
    pairs=list(zip(chart_parts(old,1),chart_parts(new,2)))+list(zip(chart_parts(old,3),chart_parts(new,5)))
    assert len(pairs)==4
    manifest=[]
    for i,(src,dst) in enumerate(pairs,1):
        new[dst]=old[src]
        tree=ET.fromstring(old[relpart(src)])
        books=[]
        for r in tree:
            original=resolve(src,r.attrib['Target'])
            assert original.endswith('.xlsx') and r.attrib['Type'].endswith('/package')
            target=f'ppt/embeddings/approved-sample-{i:02}.xlsx'
            new[target]=old[original]
            r.attrib['Target']=posixpath.relpath(target,posixpath.dirname(dst))
            books.append(dict(source=original,destination=target,sha256=sha(old[original])))
        ET.register_namespace('',RELNS)
        new[relpart(dst)]=ET.tostring(tree,encoding='utf-8',xml_declaration=True)
        manifest.append(dict(source_chart=src,destination_chart=dst,chart_sha256=sha(old[src]),workbooks=books))
    types=ET.fromstring(new['[Content_Types].xml'])
    if not any(e.attrib.get('Extension')=='xlsx' for e in types):
        ET.SubElement(types,'{'+CT+'}Default',Extension='xlsx',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    ET.register_namespace('',CT)
    new['[Content_Types].xml']=ET.tostring(types,encoding='utf-8',xml_declaration=True)
    temporary=Path(candidate).with_suffix('.workbooks-restored.pptx')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in new.items():z.writestr(n,b)
    temporary.replace(candidate)
    Path(receipt).write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    return manifest

if __name__=='__main__':
    result=preserve(*sys.argv[1:4]);print(json.dumps({'preserved_source_charts':len(result),'invented_workbooks':0}))
