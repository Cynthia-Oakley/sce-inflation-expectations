"""Offline conditional associations, not causal estimates or simulation inputs."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from scipy.stats import t

from ..age_reporting_audit import SOURCES
from ..expanded_state_inputs import profiles
from ..monthly_population import EMPLOYMENT, EMPLOYMENT_PRIORITY

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = 'outputs/sce_prior_preparation_20261013_v4/labeled_reference_private.parquet'
CASES = 'outputs/sce_expanded_state_evaluation_20261014_v1/cases_private.json'
DEVELOPMENT_CASES = 'outputs/sce_expanded_state_trial_20261014_v3/development_cases_private.json'
CATEGORIES = {
    'gender': ['Male', 'Female'],
    '_AGE_CAT': ['Under 40', '40 to 60', 'Over 60'],
    '_EDU_CAT': ['College', 'Some College', 'High School'],
    '_HH_INC_CAT': ['Over 100k', '50k to 100k', 'Under 50k'],
    '_NUM_CAT': ['High', 'Low'],
    '_REGION_CAT': ['Northeast', 'Midwest', 'South', 'West'],
    'employment': ['employed', 'unemployed', 'on_leave', 'disabled', 'retired', 'student', 'homemaker', 'other'],
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def fit_month_wls(y, x, weights, months, persons, names):
    """Absorb monthly intercepts; person-cluster CR1 intervals, no person FE.

    Month-normalized weights give each month equal total influence. A coefficient
    with lagged answers is descriptive, not an identified learning parameter.
    """
    y, x, w = np.asarray(y,float), np.asarray(x,float), np.asarray(weights,float)
    if x.ndim != 2 or len(names) != x.shape[1] or len(y) != len(x):
        raise ValueError('inconsistent design')
    if not np.isfinite(x).all() or not np.isfinite(y).all() or not np.isfinite(w).all() or (w<=0).any():
        raise ValueError('finite observations and positive weights required')
    _, mi = np.unique(months,return_inverse=True)
    _, pi = np.unique(persons,return_inverse=True)
    m, g, n, p = mi.max()+1, pi.max()+1, len(y), x.shape[1]
    if g<2 or n<=p+m:
        raise ValueError('insufficient residual degrees of freedom')
    w = w / np.bincount(mi,weights=w)[mi] * (n/m)
    mass = np.bincount(mi,weights=w)
    yc = y-np.bincount(mi,weights=w*y)[mi]/mass[mi]
    xc = np.column_stack([x[:,j]-np.bincount(mi,weights=w*x[:,j])[mi]/mass[mi] for j in range(p)])
    cross = xc.T @ (w[:,None]*xc)
    rank = int(np.linalg.matrix_rank(cross))
    if rank != p:
        raise ValueError('rank deficient design; do not interpret unidentified coefficients')
    bread = np.linalg.inv(cross)
    beta = bread @ (xc.T @ (w*yc))
    resid = yc-xc @ beta
    scores = np.zeros((g,p))
    np.add.at(scores,pi,xc*(w*resid)[:,None])
    covariance = bread @ (scores.T @ scores) @ bread
    covariance *= g/(g-1)*(n-1)/(n-p-m)
    se = np.sqrt(np.maximum(np.diag(covariance),0))
    critical = float(t.ppf(.975,g-1))
    total = float(w @ (yc*yc))
    return {
        'rows':n,'persons':int(g),'months':int(m),'rank':rank,
        'within_month_r2':None if total==0 else float(1-(w @ (resid*resid))/total),
        'coefficients':{name:{'estimate':float(b),'se_person_cluster':float(s),
                              'ci95':[float(b-critical*s),float(b+critical*s)]}
                        for name,b,s in zip(names,beta,se)},
        'inference':'person-cluster CR1; monthly intercepts; repeated rows are not independent people; no full survey design or cross-person residual dependence adjustment',
    }


def design(frame):
    names, cols = [], []
    for field, levels in CATEGORIES.items():
        # An absent level must not create an unidentified all-zero column.
        present = [value for value in levels if frame[field].eq(value).any()]
        if len(present)<2:
            continue
        for level in present[1:]:
            names.append(field+'='+level)
            cols.append(frame[field].eq(level).to_numpy(float))
    return np.column_stack(cols), names


def carry_gender_past_only(frame):
    frame=frame.sort_values(['userid','date']).copy()
    valid=frame.Q33.isin([1,2])
    frame['gender_source_month']=frame.date.where(valid)
    frame['gender_code']=frame.Q33.where(valid)
    for col in ['gender_source_month','gender_code']:
        frame[col]=frame.groupby('userid',sort=False)[col].ffill()
    if (frame.gender_source_month.dropna()>frame.loc[frame.gender_source_month.notna(),'date']).any():
        raise ValueError('future gender source')
    frame['gender']=frame.gender_code.map({1:'Female',2:'Male'})
    return frame


def extract_gender(root):
    """Read three numeric cells per XLSX row; verify keys against the full cache.

    XLSX numeric cells are selected by exact column references. Unsupported
    shared-string encodings fail rather than being mistaken for gender values.
    """
    rows=[]
    for name,start,end in SOURCES:
        path=root/name
        book=load_workbook(path,read_only=True,data_only=True)
        it=book.worksheets[0].iter_rows(values_only=True);next(it);header=list(next(it))
        member=book.worksheets[0]._worksheet_path
        selected={get_column_letter(header.index(key)+1):key for key in ['date','userid','Q33']}
        book.close()
        with ZipFile(path) as archive:
            raw=archive.read(member)
        columns=b'|'.join(k.encode() for k in selected)
        cell_re=re.compile(rb'<c\b[^>]*\br="('+columns+rb')\d+"[^>]*>(.*?)</c>',re.S)
        count=0
        for match in re.finditer(rb'<row\b[^>]*\br="(\d+)"[^>]*>(.*?)</row>',raw,re.S):
            if int(match.group(1))<=2:
                continue
            record={}
            for cell in cell_re.finditer(match.group(2)):
                full=cell.group(0)
                if b't="s"' in full.split(b'>',1)[0]:
                    raise ValueError('unexpected shared string in numeric analysis field')
                value=re.search(rb'<v>([^<]+)</v>',cell.group(2))
                if value:
                    record[selected[cell.group(1).decode()]]=float(value.group(1))
            month=record.get('date')
            if month is None or not start<=month<=end:
                continue
            if 'userid' not in record:
                raise ValueError('missing numeric respondent key')
            rows.append({'date':int(month),'userid':int(record['userid']),'Q33':record.get('Q33',np.nan)})
            count+=1
        print('gender fields extracted',start,end,count,flush=True)
    return pd.DataFrame(rows)


def controls_frame(root, out):
    refpath=root/REFERENCE
    receipt=json.loads((refpath.parent/'summary.json').read_text())
    if sha(refpath)!=receipt['output_file_sha256'][refpath.name]:
        raise ValueError('reference drift')
    registry=json.loads((root/'data/evaluation/sce_baselines_latest_20261007/micro_reference_sources.json').read_text())
    source_hashes={REFERENCE:sha(refpath)}
    for name,_,_ in SOURCES:
        source_hashes[name]=sha(root/name)
        if source_hashes[name]!=registry['sources'][name]:
            raise ValueError('official workbook drift')
    reference=pd.read_parquet(refpath)
    gender=extract_gender(root)
    if gender.duplicated(['date','userid']).any() or set(map(tuple,gender[['date','userid']].to_numpy()))!=set(map(tuple,reference[['date','userid']].to_numpy())):
        raise ValueError('gender extraction key coverage mismatch')
    reference=carry_gender_past_only(reference.merge(gender,on=['date','userid'],validate='one_to_one'))
    profile,hashes=profiles();source_hashes.update(hashes)
    profile=profile[['date','userid','_REGION_CAT']+[f'Q10_{i}' for i in range(1,11)]].copy()
    choices=profile[[f'Q10_{i}' for i in EMPLOYMENT_PRIORITY]].eq(1).to_numpy()
    any_selected=choices.any(axis=1)
    profile['employment']=[EMPLOYMENT[EMPLOYMENT_PRIORITY[i]] if ok else None for i,ok in zip(choices.argmax(axis=1),any_selected)]
    reference=reference.merge(profile[['date','userid','_REGION_CAT','employment']],on=['date','userid'],validate='one_to_one')
    reference=reference.sort_values(['userid','date']).copy()
    lag=reference[['userid','date','Q9_mean','Q8v2part2']].copy()
    monthidx=(lag.date//100)*12+lag.date%100-1+1
    lag['date']=(monthidx//12)*100+monthidx%12+1
    lag=lag.rename(columns={'Q9_mean':'lag_q9','Q8v2part2':'lag_q8'})
    reference=reference.merge(lag,on=['userid','date'],how='left',validate='one_to_one')
    reference.to_parquet(out/'reference_with_controls_private.parquet',index=False)
    return reference, source_hashes


def official_associations(frame):
    mask=np.isfinite(frame.weight)&frame.weight.gt(0)
    for field,levels in CATEGORIES.items():
        mask &= frame[field].isin(levels)
    complete=frame.loc[mask].copy()
    result={'total_rows':len(frame),'known_gender_rows':int(frame.gender.notna().sum()),
            'complete_profile_positive_weight_rows':len(complete),
            'gender_question':'Q33 Female=1, Male=2; carry own observations forward only, no future backfill',
            'models':{},'yearly_q9':{}}
    for target,label in [('Q9_mean','q9_mean'),('Q8v2part2','q8_point'),('Q9_iqr','q9_iqr')]:
        block=complete.loc[np.isfinite(complete[target])].copy()
        if target=='Q8v2part2':
            block=block.loc[block[target].abs().le(100)]
        if target=='Q9_iqr':
            block=block.loc[block[target].ge(0)]
        x,names=design(block)
        result['models'][label]=fit_month_wls(block[target],x,block.weight,block.date,block.userid,names)
        if target=='Q9_mean':
            for year,part in block.groupby(block.date//100):
                xx,nn=design(part)
                result['yearly_q9'][str(year)]=fit_month_wls(part[target],xx,part.weight,part.date,part.userid,nn)
    block=complete.loc[np.isfinite(complete.Q9_mean)&np.isfinite(complete.lag_q9)&complete.timeline_consistent&complete.tenure_valid&complete.gap_months.eq(1)].copy()
    x,names=design(block)
    result['models']['q9_returners_without_lag']=fit_month_wls(block.Q9_mean,x,block.weight,block.date,block.userid,names)
    result['models']['q9_returners_with_lag']=fit_month_wls(block.Q9_mean,np.column_stack([x,block.lag_q9]),block.weight,block.date,block.userid,names+['lag_q9'])
    # Fixed diagnostic tail rule, not a new main scoring method or tuning step.
    clipped=block.copy()
    for _,part in clipped.groupby('date'):
        for field in ['Q9_mean','lag_q9']:
            order=np.argsort(part[field].to_numpy())
            values=part[field].to_numpy()[order];weights=part.weight.to_numpy()[order]
            cw=np.cumsum(weights)/weights.sum()
            low,high=[values[min(np.searchsorted(cw,q,side='left'),len(values)-1)] for q in [.01,.99]]
            clipped.loc[part.index,field]=part[field].clip(low,high)
    result['models']['q9_returners_with_lag_tail_sensitivity']=fit_month_wls(clipped.Q9_mean,np.column_stack([x,clipped.lag_q9]),clipped.weight,clipped.date,clipped.userid,names+['lag_q9'])
    result['tail_sensitivity']='On exactly the same returner sample, cap current and previous Q9 means at their month-specific weighted 1st/99th percentiles; diagnostic only, primary results unmodified.'
    return result


def compression_diagnostic(root):
    paths=[root/DEVELOPMENT_CASES,root/CASES]
    frame=pd.concat([pd.DataFrame(json.loads(path.read_text())) for path in paths],ignore_index=True)
    if frame.duplicated(['month','userid','repeat']).any():raise ValueError('duplicate diagnostic generation')
    # Identical valid generation support for all compared arms and baselines.
    frame=frame.loc[frame.common.eq(True)].copy()
    fields=['actual','previous','self_update','new_signal','copy_previous','history_anchor_half']
    for field in fields:
        frame[field]=pd.to_numeric(frame[field],errors='coerce')
    # Generation averaging is a diagnostic summary, not probability pooling.
    attributes=frame.groupby(['month','userid']).profile.first().to_dict()
    frame=frame.groupby(['month','userid'],as_index=False)[fields].mean()
    frame=frame.loc[np.isfinite(frame[fields]).all(axis=1)].copy()
    result={'source_sha256':{str(path.relative_to(root)):sha(path) for path in paths},'unique_complete_person_months':len(frame),
            'interpretation':'Average available model generations per person-month for this diagnostic only; use equal person weights; not nationwide or causal',
            'by_month':{},'subgroups':{}}
    for month,part in frame.groupby('month'):
        prev=part.previous.to_numpy();prev=prev-prev.mean();variance=float(np.mean(prev**2))
        report={}
        for field in fields:
            if field=='previous':continue
            y=part[field].to_numpy();y=y-y.mean();delta=y-prev
            vy=float(np.mean(y*y));vd=float(np.mean(delta*delta));cov=float(np.mean(prev*delta))
            report[field]={'previous_position_slope':float(np.mean(prev*y)/variance),
                          'previous_variance':variance,'current_variance':vy,'change_variance':vd,
                          'cov_previous_change':cov,'identity_error':float(vy-(variance+vd+2*cov)),
                          'mean_change':float((part[field]-part.previous).mean())}
        result['by_month'][str(month)]={'persons':len(part),'measures':report}
    for dimension in ['age_group','household_income_band','numeracy']:
        values=[attributes[(r.month,r.userid)].get(dimension,'unknown') for r in frame.itertuples()]
        frame[dimension]=values
        result['subgroups'][dimension]={}
        for label,part in frame.groupby(dimension):
            if label=='unknown' or part.userid.nunique()<10:continue
            xx=part.previous.to_numpy()[:,None]
            result['subgroups'][dimension][label]={field:fit_month_wls(part[field],xx,np.ones(len(part)),part.month,part.userid,['lag_q9']) for field in ['actual','self_update','new_signal']}
    return result


def run(out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('fresh ignored output directory required')
    out.mkdir(parents=True)
    frame,sources=controls_frame(ROOT,out)
    associations=official_associations(frame)
    compression=compression_diagnostic(ROOT)
    summary={'status':'descriptive_offline_analysis_not_mechanism_identification','completed_at':datetime.now(timezone.utc).isoformat(),
             'new_api_calls':0,'source_sha256':sources,'private_frame_sha256':sha(out/'reference_with_controls_private.parquet'),
             'analysis_code_sha256':sha(__file__),'official_associations':associations,'expanded_compression':compression,
             'limits':['Month fixed effects absorb common events; these regressions cannot estimate common CPI or rate effects.',
                       'Gender is observed; shopping responsibility/frequency and causal models are not observed in this core extract.',
                       'Age, cohort and period are not separately identified; no estimate of individual memory weights.',
                       'Lag coefficients mix persistent beliefs, state dependence, measurement error and omitted variables; no person fixed effects.',
                       'These full-span diagnostic outcomes must not initialize personas or be used as an independent forecast test.',
                       'Conditional regressions concern averages, not a reconstruction of the SCE headline median.']}
    dump(out/'summary.json',summary)
    return summary
