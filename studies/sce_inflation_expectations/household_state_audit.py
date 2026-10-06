"""Offline descriptive audit. Never imports providers or alters study inputs.

Official Q9_mean and signed Q8 are evaluation-only. Synthesis candidates
contain demographic crosswalks and HAPPY/SATFIN only; no SCE outcomes.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

NUMERACY_ANSWERS = {'QNUM1':150., 'QNUM2':242., 'QNUM3':10., 'QNUM5':100., 'QNUM6':5.}
PROFILE = ['_AGE_CAT','_EDU_CAT','_HH_INC_CAT','_REGION_CAT','_NUM_CAT']


def weighted_quantile(values, weights, q=.5, *, interpolate=False):
    x=np.asarray(values,float);w=np.asarray(weights,float)
    mask=np.isfinite(x)&np.isfinite(w)&(w>0);x=x[mask];w=w[mask]
    if not len(x):return None
    if not 0<=q<=1:raise ValueError('quantile must be in [0,1]')
    order=np.argsort(x,kind='stable');x=x[order];w=w[order]
    if interpolate:
        u, inverse=np.unique(x,return_inverse=True)
        mass=np.bincount(inverse,weights=w)
        return float(np.interp(q,(mass.cumsum()-.5*mass)/mass.sum(),u))
    i=np.searchsorted(w.cumsum(),q*w.sum(),side='left')
    return float(x[min(i,len(x)-1)])


def summary(values,weights,*,interpolate=False):
    x=np.asarray(values,float);w=np.asarray(weights,float)
    mask=np.isfinite(x)&np.isfinite(w)&(w>0);x=x[mask];w=w[mask]
    if not len(x):return {'valid_n':0}
    qu=[weighted_quantile(x,w,q,interpolate=interpolate) for q in [.25,.5,.75]]
    return {'valid_n':len(x),'weighted_mean_pp':float(np.average(x,weights=w)),
            'weighted_p25_pp':qu[0],'weighted_median_pp':qu[1],'weighted_p75_pp':qu[2],
            'between_person_iqr_pp':qu[2]-qu[0],'weight_sum':float(w.sum()),
            'effective_n':float(w.sum()**2/(w@w))}


def classify_numeracy(frame):
    raw=frame[list(NUMERACY_ANSWERS)].apply(pd.to_numeric,errors='coerce')
    valid=np.isfinite(raw).all(axis=1)
    score=sum(np.isclose(raw[k],a,rtol=0,atol=1e-8) for k,a in NUMERACY_ANSWERS.items())
    result=pd.Series(None,index=frame.index,dtype='object')
    result.loc[valid]=np.where(score[valid]>=4,'High','Low')
    return result,valid


def audit_sce(frame):
    out={}
    for month,g in frame.groupby('date',sort=True):
        if g.userid.duplicated().any():raise ValueError('duplicate respondent-month')
        if not (np.isfinite(g.weight)&(g.weight>0)).all():raise ValueError('invalid survey weights')
        if not g.Q1.dropna().isin([1,2,3,4,5]).all():raise ValueError('unexpected Q1 code')
        rec={'n':len(g),'q1_valid_n':int(g.Q1.notna().sum()),'groups':{},'q1_by_profile':{},
             'official_q9':summary(g.Q9_mean,g.weight),'q8_signed_point':summary(g.Q8v2part2,g.weight,interpolate=True)}
        for col in ['Q1','_NUM_CAT']:
            rec['groups'][col]={}
            for val,h in g.groupby(col,dropna=False):
                rec['groups'][col][str(val)]={'n':len(h),'weighted_share':float(h.weight.sum()/g.weight.sum()),
                     'q9':summary(h.Q9_mean,h.weight),'q8':summary(h.Q8v2part2,h.weight,interpolate=True)}
        for col in PROFILE:
            tab={}
            for val,h in g.groupby(col,dropna=False):
                tab[str(val)]={'n':len(h),'q1_weighted_proportions':{str(c):float(z.weight.sum()/h.weight.sum()) for c,z in h.groupby('Q1',dropna=False)}}
            rec['q1_by_profile'][col]=tab
        inferred,valid=classify_numeracy(g)
        known=valid&g._NUM_CAT.isin(['High','Low'])
        rec['numeracy_check']={'complete_five_question_n':int(valid.sum()),'comparable_n':int(known.sum()),
            'agreement_n':int((inferred[known]==g.loc[known,'_NUM_CAT']).sum()),
            'disagreement_n':int((inferred[known]!=g.loc[known,'_NUM_CAT']).sum()),
            'missing_policy':'Incomplete five-question rows not scored; QNUM8/9 excluded per official guide.'}
        # Descriptive WLS, not causal effects or national hypothesis tests.
        d=g[['Q9_mean','weight','Q1']+PROFILE].dropna().copy()
        blocks=[pd.Series(1.,index=d.index,name='intercept')]
        for code in [1,2,4,5]:blocks.append((d.Q1==code).astype(float).rename(f'Q1_{code}_vs_3'))
        blocks.append(pd.get_dummies(d[PROFILE].astype(str),drop_first=True,dtype=float))
        X=pd.concat(blocks,axis=1);sw=np.sqrt(d.weight.to_numpy(float))
        coef,_,rank,_=np.linalg.lstsq(X.to_numpy(float)*sw[:,None],d.Q9_mean.to_numpy(float)*sw,rcond=None)
        rec['adjusted_mean_association']={'n':len(d),'rank':int(rank),'parameters':X.shape[1],
            'controls':PROFILE,'coefficients_pp':{name:float(v) for name,v in zip(X.columns,coef) if str(name).startswith('Q1_')},
            'interpretation':'Weighted linear mean associations vs Q1=3, categorical controls; no causal or significance claim. Not fitted to create P or change B.'}
        out[str(int(month))]=rec
    repeat=frame.groupby('userid')['_NUM_CAT'].agg(['size','nunique'])
    return {'months':out,'two_month_numeracy_persistence':{'repeated_ids':int((repeat['size']>1).sum()),
        'repeated_ids_changing_category':int(((repeat['size']>1)&(repeat["nunique"]>1)).sum())}}


def gss_education(degree,educ):
    if pd.isna(degree) or pd.isna(educ):return None
    if degree>=3:return 'College'
    if degree==2 or educ>12:return 'Some College'
    return 'High School'


def gss_income(code):
    """Historical nominal family-income proxy; do not split $90k-$109,999.

    Different reference year/unit from SCE, explicitly exploratory support only.
    """
    if pd.isna(code):return None
    code=int(code)
    if 1<=code<=18:return 'Under 50k'
    if 19<=code<=21:return '50k to 100k'
    if code==22:return None
    if 23<=code<=26:return 'Over 100k'
    raise ValueError('unexpected INCOME16 code')


def prepare_gss(df,label_maps,weight='wtssps'):
    if not (df.year==2018).all() or df.id.duplicated().any():raise ValueError('not unique 2018 cross section')
    g=df.copy()
    g['_AGE_CAT']=g.age.map(lambda a:None if pd.isna(a) else ('Under 40' if a<40 else ('40 to 60' if a<60 else 'Over 60')))
    g['_EDU_CAT']=[gss_education(d,e) for d,e in zip(g.degree,g.educ)]
    g['_HH_INC_CAT']=g.income16.map(gss_income)
    mapping={'northeast':'Northeast','midwest':'Midwest','south':'South','west':'West'}
    g['_REGION_CAT']=g.region.map(lambda x:mapping[label_maps['region'][str(int(x))]] if pd.notna(x) else None)
    valid=g.happy.isin([1,2,3])&g.satfin.isin([1,2,3])&np.isfinite(g[weight])&(g[weight]>0)
    g=g.loc[valid].copy()
    g['donor_weight']=g[weight]
    return g


def audit_support(target,donors,keys):
    pools={k:h for k,h in donors.dropna(subset=keys).groupby(keys,sort=True)}
    cells=[]
    for k,t in target.groupby(keys,dropna=False,sort=True):
        k=k if isinstance(k,tuple) else (k,)
        d=pools.get(k)
        w=np.array([]) if d is None else d.donor_weight.to_numpy(float)
        ess=0. if not len(w) else float(w.sum()**2/(w@w))
        cells.append({'cell':list(map(str,k)),'target_n':len(t),'target_weight':float(t.weight.sum()),'donor_n':len(w),'donor_ess':ess})
    return {'keys':keys,'cells':cells,'target_n':len(target),'target_zero_support_n':sum(x['target_n'] for x in cells if x['donor_n']==0),
            'target_donor_ess_below10_n':sum(x['target_n'] for x in cells if x['donor_ess']<10),
            'min_nonzero_donor_ess':min((x['donor_ess'] for x in cells if x['donor_n']),default=0.),
            'note':'ESS<10 is a reported descriptive threshold, not a frozen donor acceptance gate.'}
