"""Read only matching-field availability/coding from public local workbooks."""
from collections import Counter
from pathlib import Path
import csv
import hashlib
import io
import json
import zipfile

from lxml import etree
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

ROOT=Path(__file__).resolve().parents[3]
SCE=ROOT/'data/raw/sce_audit_20260928/micro_2020_2024.xlsx'
CE=ROOT/'data/raw/ce_experience/20261006/diary/diary20.zip'
QUESTIONNAIRE=ROOT/'data/raw/sce_audit_20260928/questionnaire.pdf'
FIELDS=['Q44']+[f'Q45new_{i}' for i in range(1,10)]+['Q46','Q47','_HH_INC_CAT']


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def run(out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored output required')
    w=load_workbook(SCE,read_only=True,data_only=True)
    header=list(next(w['Data'].iter_rows(min_row=2,max_row=2,values_only=True)));w.close()
    cols={get_column_letter(header.index(k)+1):k for k in FIELDS if k in header}
    counts=Counter();pairs=Counter();valid_income=0;n=0
    with zipfile.ZipFile(SCE) as z:
        labels=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            with z.open('xl/sharedStrings.xml') as f:
                for _,r in etree.iterparse(f,events=('end',),tag='{*}si'):
                    labels.append(''.join(r.itertext()));r.clear()
        with z.open('xl/worksheets/sheet1.xml') as f:
            for _,r in etree.iterparse(f,events=('end',),tag='{*}row'):
                if int(r.get('r'))>2:
                    n+=1;values={}
                    for c in r:
                        k=cols.get(c.get('r','').rstrip('0123456789'))
                        if k is not None:
                            v=c.find('{*}v')
                            if v is not None and v.text is not None and v.text.strip():
                                counts[k]+=1
                                values[k]=labels[int(v.text)] if c.get('t')=='s' else v.text
                    try:q47=float(values.get('Q47',''))
                    except ValueError:q47=None
                    if q47 is not None and q47.is_integer() and 1<=q47<=11:
                        valid_income+=1;pairs[(str(int(q47)),values.get('_HH_INC_CAT','missing'))]+=1
                r.clear()
                while r.getprevious() is not None:del r.getparent()[0]
    boundary={}
    with zipfile.ZipFile(CE) as z:
        for q in range(1,5):
            values=[]
            with z.open(f'diary20/fmld20{q}.csv') as f:
                for r in csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig')):
                    try:values.append(float(r['FINCBEFM']))
                    except ValueError:pass
            boundary[str(q)]={'valid_income_week_rows':len(values),'exactly_100000':sum(v==100000 for v in values)}
    s={'status':'completed_offline_matching_field_inventory','new_api_calls':0,
       'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [SCE,CE,QUESTIONNAIRE,Path(__file__).resolve()]},
       'raw_sce_rows':n,'fields_in_schema':[k for k in FIELDS if k in header],
       'nonblank_cell_counts':dict(counts),'valid_entry_income_codes':valid_income,
       'q47_to_coarse_income_counts':{a+'|'+b:v for (a,b),v in pairs.items()},
       'ce_income_boundary_by_quarter':boundary,
       'questionnaire_evidence':{'Q44':'p32: owns another home; not net wealth',
          'Q45new':'p33: household composition excluding respondent; counts and living-alone option',
          'Q46':'p34: household financial decision responsibility; not grocery shopping responsibility',
          'Q47':'p35: combined pre-tax household income in prior 12 months, 11 brackets; 100000 begins bracket9',
          'timing':'p27: Q32-Q47 asked of new respondents; coverage across all monthly rows is not current-month missingness.'},
       'limits':['Nonblank counts are not validated current-month values or representative population rates.',
                 'No individual joining, carrying forward or modification of simulation inputs.',
                 'Household composition and income must respect entry timing, changes and survey boundaries.']}
    out.mkdir(parents=True);(out/'summary.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'rows':n,'nonblank':dict(counts),'q47_valid':valid_income,'pairs':s['q47_to_coarse_income_counts'],'ce_boundary':boundary},ensure_ascii=False))
    return s
