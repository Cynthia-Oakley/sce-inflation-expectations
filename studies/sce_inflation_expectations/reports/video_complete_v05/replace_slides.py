"""Replace only pages 5–8 and preserve the author's other slides and notes."""
from pathlib import Path
import hashlib,json,posixpath,sys,zipfile
from lxml import etree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'video_complete_v04'))
from replace_slide9 import normalize_chart,relpart,resolve,serialize,CT


def main(base,newdeck,out,receipt):
    with zipfile.ZipFile(base) as z:old={n:z.read(n) for n in z.namelist()}
    with zipfile.ZipFile(newdeck) as z:fresh={n:z.read(n) for n in z.namelist()}
    merged=dict(old);mapping={f'ppt/slides/slide{i}.xml':f'ppt/slides/slide{j}.xml' for i,j in enumerate([5,6,7,8],1)};done=set()
    def copy(p):
        if p in done:return mapping[p]
        if p not in mapping:
            d,b=posixpath.split(p);mapping[p]=posixpath.join(d,'sce_v05_'+b)
        target=mapping[p];done.add(p);merged[target]=fresh[p];rp=relpart(p)
        if rp in fresh:
            root=ET.fromstring(fresh[rp])
            for r in root:
                if r.attrib.get('TargetMode')=='External':continue
                dest=copy(resolve(p,r.attrib['Target']));r.attrib['Target']=posixpath.relpath(dest,posixpath.dirname(target))
            merged[relpart(target)]=serialize(root)
        return target
    for i in range(1,5):copy(f'ppt/slides/slide{i}.xml')
    types=ET.fromstring(old['[Content_Types].xml']);extra=ET.fromstring(fresh['[Content_Types].xml'])
    default={e.attrib.get('Extension') for e in types if ET.QName(e).localname=='Default'}
    overrides={e.attrib.get('PartName') for e in types if ET.QName(e).localname=='Override'}
    for e in extra:
        if ET.QName(e).localname=='Default' and e.attrib['Extension'] not in default:types.append(e);default.add(e.attrib['Extension'])
        elif ET.QName(e).localname=='Override' and e.attrib['PartName'].lstrip('/') in mapping:
            dest='/'+mapping[e.attrib['PartName'].lstrip('/')]
            if dest not in overrides:
                clone=ET.fromstring(serialize(e));clone.attrib['PartName']=dest;types.append(clone);overrides.add(dest)
    keep={'[Content_Types].xml','_rels/.rels'}
    def walk(p):
        if p in keep:return
        assert p in merged,p
        keep.add(p);rp=relpart(p)
        if rp in merged:
            keep.add(rp)
            for r in ET.fromstring(merged[rp]):
                if r.attrib.get('TargetMode')!='External':walk(resolve(p,r.attrib['Target']))
    for r in ET.fromstring(merged['_rels/.rels']):
        if r.attrib.get('TargetMode')!='External':walk(resolve('',r.attrib['Target']))
    merged={p:b for p,b in merged.items() if p in keep}
    for e in list(types):
        if ET.QName(e).localname=='Override' and e.attrib['PartName'].lstrip('/') not in merged:types.remove(e)
    merged['[Content_Types].xml']=serialize(types);repairs=[]
    for p,b in list(merged.items()):
        if '/charts/' in p and p.endswith('.xml'):merged[p]=normalize_chart(b,p,repairs)
    for i in [1,2,3,4,9]:
        for p in [f'ppt/slides/slide{i}.xml',f'ppt/slides/_rels/slide{i}.xml.rels',f'ppt/notesSlides/notesSlide{i}.xml']:
            if p in old:assert old[p]==merged[p],p
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for p,b in merged.items():z.writestr(p,b)
    Path(receipt).write_text(json.dumps(dict(protected_slides=[1,2,3,4,9],source_sha256=hashlib.sha256(Path(base).read_bytes()).hexdigest(),part_mapping=mapping,compatibility_repairs=repairs),ensure_ascii=False,indent=2))


if __name__=='__main__':main(*sys.argv[1:5])
