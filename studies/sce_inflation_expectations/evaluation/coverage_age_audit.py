"""Offline selected-person historical coverage and CE age associations. No API."""
from pathlib import Path
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
import zipfile

from lxml import etree
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests

ROOT=Path(__file__).resolve().parents[3]
LINK=ROOT/'outputs/sce_information_update_trial_20261014_v2/evaluation_links_private.json'
DONORS=ROOT/'outputs/sce_frequency_quarter_audit_20261015_v3/donor_weeks_private.json'
ARCHIVE=ROOT/'data/raw/ce_experience/20261006/diary/diary20.zip'
SOURCES=[ROOT/'data/raw/sce_p_sources/micro_2017_2019.xlsx',
         ROOT/'data/raw/sce_audit_20260928/micro_2020_2024.xlsx']
CATS=['food_at_home','food_away_from_home','household_cleaning_paper','personal_care_products']
FIELDS=['userid','date','Q32','Q43','Q44','Q46','Q47','D3']+[f'Q45new_{i}' for i in range(1,10)]


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def num(x):
    try:
        v=float(x);return v if math.isfinite(v) else None
    except (ValueError,TypeError):return None


def integer(x,low,high):
    v=num(x);return int(v) if v is not None and v.is_integer() and low<=v<=high else None


def family(row):
    counts=[integer(row.get(f'Q45new_{i}'),0,30) for i in range(1,9)]
    alone=integer(row.get('Q45new_9'),0,1)
    if any(v is None for v in counts) or alone is None:return None
    if alone==1 and sum(counts)!=0:return None
    if alone==0 and sum(counts)==0:return None
    return {'members_including_self_excluding_nonrelatives':1+sum(counts[:7]),
            'children_under18':counts[3]+counts[4], 'nonrelatives_excluded':counts[7],
            'living_alone':alone==1}


def selected_rows(path,ids):
    w=load_workbook(path,read_only=True,data_only=True)
    header=list(next(w['Data'].iter_rows(min_row=2,max_row=2,values_only=True)));w.close()
    cols={get_column_letter(header.index(k)+1):k for k in FIELDS if k in header}
    id_col=get_column_letter(header.index('userid')+1)
    with zipfile.ZipFile(path) as z:
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            with z.open('xl/sharedStrings.xml') as f:
                for _,r in etree.iterparse(f,events=('end',),tag='{*}si'):
                    strings.append(''.join(r.itertext()));r.clear()
        with z.open('xl/worksheets/sheet1.xml') as f:
            for _,r in etree.iterparse(f,events=('end',),tag='{*}row'):
                if int(r.get('r'))>2:
                    values={};wanted=False
                    for c in r:
                        column=c.get('r','').rstrip('0123456789')
                        if column==id_col:
                            v=c.find('{*}v')
                            if v is not None and v.text is not None:
                                wanted=integer(v.text,1,10**12) in ids
                            break
                    if wanted:
                        for c in r:
                            k=cols.get(c.get('r','').rstrip('0123456789'))
                            if k:
                                v=c.find('{*}v')
                                if v is not None and v.text is not None:
                                    values[k]=strings[int(v.text)] if c.get('t')=='s' else v.text
                        yield values
                r.clear()
                while r.getprevious() is not None:del r.getparent()[0]


def month_diff(a,b):return (a//100-b//100)*12+a%100-b%100


def coverage():
    links=json.loads(LINK.read_text());ids={int(r['userid']) for r in links};history=defaultdict(dict)
    for p in SOURCES:
        for row in selected_rows(p,ids):
            uid=integer(row.get('userid'),1,10**12);m=integer(row.get('date'),201001,202612)
            if m is None:continue
            if m in history[uid]:raise ValueError('Overlapping profile source rows')
            history[uid][m]=row
    results=[]
    for link in links:
        uid=int(link['userid']);target=int(link['month']);past=[(m,r) for m,r in sorted(history[uid].items()) if m<target]
        rec={'month':target,'agent_id':link['agent_id'],'own_prior_rows':len(past),'features':{}}
        selectors={'entry_age':lambda r:integer(r.get('Q32'),18,110),
            'fine_income':lambda r:integer(r.get('Q47'),1,11),'family_composition':family,
            'other_home':lambda r:integer(r.get('Q44'),1,2),'financial_decision_role':lambda r:integer(r.get('Q46'),1,5)}
        for name,fn in selectors.items():
            valid=[(m,fn(r)) for m,r in past if fn(r) is not None]
            if not valid:rec['features'][name]={'available':False};continue
            m,v=valid[-1];details={'available':True,'source_month':m,'age_months':month_diff(target,m),'value':v}
            if name=='fine_income':
                coarse='under_50k' if v<=5 else '50k_to_100k' if v<=8 else 'over_100k'
                details['agrees_with_current_coarse_income']=coarse==link['profile'].get('household_income_band')
            if name=='family_composition':
                details['moved_after_record']=any(integer(r.get('D3'),0,1)==1 for mm,r in past if mm>m)
            rec['features'][name]=details
        results.append(rec)
    def summarize(rows):
        output={}
        for name in results[0]['features']:
            valid=[r['features'][name] for r in rows if r['features'][name]['available']]
            ages=[r['age_months'] for r in valid]
            output[name]={'available':len(valid),'total':len(rows),
                'record_age_months_min_median_max':[int(min(ages)),float(np.median(ages)),int(max(ages))] if ages else None,
                'older_than_12_months':sum(a>12 for a in ages)}
            if name=='fine_income':output[name]['coarse_income_agrees']=sum(r['agrees_with_current_coarse_income'] for r in valid)
            if name=='family_composition':output[name]['moved_after_record']=sum(r['moved_after_record'] for r in valid)
        return output
    return results,{'overall':summarize(results),'by_month':{str(m):summarize([r for r in results if r['month']==m]) for m in sorted({r['month'] for r in results})},
        'n_person_months':len(results),'unique_people':len(ids),'historical_rows_considered':sum(r['own_prior_rows'] for r in results)}


def ce_frame():
    quarter_rows=json.loads(DONORS.read_text());frame=[]
    with zipfile.ZipFile(ARCHIVE) as z:
        for q,rows in quarter_rows.items():
            raw={}
            with z.open(f'diary20/fmld20{q}.csv') as f:
                for r in csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig')):
                    key=hashlib.sha256(f"ce-diary-2020|week|Q{q}|{r['NEWID']}".encode()).hexdigest()
                    raw[key]=r
            for r in rows:
                age=num(raw[r['week_key']].get('AGE_REF'))
                frame.append({'quarter':int(q),'cu':r['cu_key'],'raw_weight':r['weight'],
                    **r['attributes'],'age':age,'family_size':r['family_size'],'children_under18':r['children_under18'],
                    'any_positive':r['any_positive'],**dict(zip(CATS,r['days']))})
    df=pd.DataFrame(frame)
    # Equal quarter total source mass, CU-first mean-weight then within-CU weeks.
    cu_mean=df.groupby(['quarter','cu']).raw_weight.mean()
    cu_total=cu_mean.groupby('quarter').sum().to_dict()
    df['weight']=[w/(4*cu_total[q]*n) for w,q,n in zip(df.raw_weight,df.quarter,df.groupby(['quarter','cu']).raw_weight.transform('size'))]
    assert np.isclose(df.weight.sum(),1)
    return df


def age_analysis(frame):
    df=frame.dropna(subset=['age_group','household_income_band','housing_tenure','region','education_group','family_size','children_under18']).copy()
    base="C(quarter)+C(age_group,Treatment(reference='Under 40'))+C(household_income_band)+C(housing_tenure)+C(region)+C(education_group)"
    models={};pvalues=[];index=[]
    for extra in [False,True]:
        label='with_family_composition' if extra else 'demographics_only'
        models[label]={}
        for cat in CATS:
            f=cat+' ~ '+base+(' + family_size + children_under18' if extra else '')
            model=smf.wls(f,data=df,weights=df.weight).fit(cov_type='cluster',cov_kwds={'groups':df.cu},use_t=True)
            assert np.linalg.matrix_rank(model.model.exog)==model.model.exog.shape[1]
            params=[k for k in model.params.index if 'C(age_group' in k];mat=np.zeros((len(params),len(model.params)))
            for i,k in enumerate(params):mat[i,list(model.params.index).index(k)]=1
            test=model.wald_test(mat,use_f=True,scalar=True);coeff={}
            for k in params:coeff[k]={'difference_days':float(model.params[k]),'ci95':model.conf_int().loc[k].tolist()}
            models[label][cat]={'n_week_rows':int(model.nobs),'n_CUs':int(df.cu.nunique()),'formula':f,'age_coefficients':coeff,
                'joint_age_p':float(test.pvalue),'method':'WLS descriptive conditional mean; cluster-robust by CU, t intervals'}
            pvalues.append(float(test.pvalue));index.append((label,cat))
    for (label,cat),p in zip(index,multipletests(pvalues,method='fdr_bh')[1]):models[label][cat]['age_joint_BH_p']=float(p)
    descriptive={}
    for age,g in frame.groupby('age_group'):
        descriptive[age]={'n_week_rows':len(g),'n_CUs':int(g.cu.nunique()),
            'mean_days':{k:float(np.average(g[k],weights=g.weight)) for k in CATS}}
    return {'complete_week_rows':len(df),'complete_CUs':int(df.cu.nunique()),'coarse_age_descriptive':descriptive,'models':models,
        'interpretation':'Within-2020 conditional associations, not causal aging effects. Family composition can lie on an age pathway; controlling it changes the question. Includes supported zero-contact weeks; missing frequency still excluded.'}


def run(out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored output required')
    private,c=coverage();frame=ce_frame();a=age_analysis(frame)
    summary={'status':'completed_offline_profile_coverage_and_age_associations','new_api_calls':0,
        'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [LINK,DONORS,ARCHIVE,*SOURCES,Path(__file__).resolve()]},
        'coverage':c,'ce_age':a,
        'limits':['Coverage requires own valid records strictly before target month; month timing is not historical public availability.',
            'Family/income records can change since entry; no current-value imputation or extra prompt fields created.',
            'CE uses reference-person age and CU purchases, not SCE respondent shopping responsibility.',
            '2020 quarters cannot establish cross-year stability or explain a past LLM treatment effect.']}
    out.mkdir(parents=True)
    (out/'person_coverage_private.json').write_text(json.dumps(private,ensure_ascii=False,indent=2)+'\n')
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'coverage':c['overall'],'age_effects':a['models']['with_family_composition']},ensure_ascii=False))
    return summary
