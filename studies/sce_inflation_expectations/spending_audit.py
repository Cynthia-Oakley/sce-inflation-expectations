"""Offline SCE QSP5 linkage and structural diagnostics; never loads an API key.

Inputs: actual shares and demographics. Inflation answers remain evaluation-only.
Current archived workbook is not proof of historic public availability.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .household_state_audit import summary, weighted_quantile

CATEGORIES = ('housing','utilities','food','clothing_personal','transportation','medical','recreation','education_childcare','other')
SHARES = [f'qsp5_{i}' for i in range(1,10)]
PROFILE = ['_AGE_CAT','_EDU_CAT','_HH_INC_CAT','_REGION_CAT','_NUM_CAT']
PROTOCOL = {'train_years':[2020,2021], 'assessment_years':[2022,2023,2024],
            'alpha':10., 'tuning':'none; fixed before outcome analysis',
            'outcomes':['Q9_mean','Q9_iqr','Q8v2part2'],
            'question':'Do measured shares add out-of-time information about within-month individual differences?',
            'scope':'Retrospective A structural diagnostic, NOT B forecast or LLM experiment',
            'centering':'Target minus same-month weighted target mean, for evaluation only',
            'weights':'Equal month total mass; actual within-month core survey weights',
            'missing':'Nine finite 0..100 shares summing to100; no renormalization or imputation',
            'shuffle':'One fixed within-month permutation seed42 of complete share vectors; no outcome-guided rematching'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def valid_baskets(frame):
    x=frame[SHARES].apply(pd.to_numeric,errors='coerce')
    complete=np.isfinite(x).all(axis=1)
    inrange=x.ge(0).all(axis=1)&x.le(100).all(axis=1)
    sums=np.isclose(x.sum(axis=1),100,rtol=0,atol=1e-6)
    return complete&inrange&sums, {'incomplete_n':int((~complete).sum()),
        'complete_out_of_range_n':int((complete&~inrange).sum()),
        'complete_in_range_bad_sum_n':int((complete&inrange&~sums).sum())}


def join_core(spending, core):
    if spending.duplicated(['userid','date']).any() or core.duplicated(['userid','date']).any():
        raise ValueError('Duplicate respondent-month; not a one-to-one linkage')
    return spending.merge(core,on=['userid','date'],how='inner',validate='one_to_one')


def historical_baskets(spending, targets, max_age=4):
    valid,_=valid_baskets(spending)
    sources=spending[valid].copy()
    rows=[]
    for month,t in targets.groupby('date',sort=True):
        eligible=sources[sources.date<int(month)].sort_values('date').groupby('userid').tail(1)
        a=t.merge(eligible[['userid','date']+SHARES],on='userid',suffixes=('','_basket'),validate='one_to_one')
        a['basket_age_months']=(a.date//100*12+a.date%100)-(a.date_basket//100*12+a.date_basket%100)
        a=a[(a.basket_age_months>=1)&(a.basket_age_months<=max_age)]
        rows.append(a)
    return pd.concat(rows,ignore_index=True) if rows else pd.DataFrame()


def centered(values, months, weights):
    y=pd.Series(np.asarray(values,float));m=pd.Series(np.asarray(months));w=pd.Series(np.asarray(weights,float))
    means=(y*w).groupby(m).transform('sum')/w.groupby(m).transform('sum')
    return (y-means).to_numpy()


def ridge_predict(train_x, train_y, train_w, test_x, alpha=10.):
    """Training-only feature scaling; unpenalized intercept, L2 slope penalty."""
    x=np.asarray(train_x,float);y=np.asarray(train_y,float);w=np.asarray(train_w,float)
    z=np.asarray(test_x,float)
    if not len(y) or len(y)!=len(w) or x.shape[0]!=len(y) or z.shape[1]!=x.shape[1]:raise ValueError('Ridge shapes')
    if not all(np.isfinite(a).all() for a in [x,y,w,z]) or (w<=0).any() or alpha<0:raise ValueError('Ridge invalid input')
    mean=np.average(x,weights=w,axis=0);scale=np.sqrt(np.average((x-mean)**2,weights=w,axis=0));scale[scale<1e-9]=1.
    a=np.column_stack([np.ones(len(x)),(x-mean)/scale]);b=np.column_stack([np.ones(len(z)),(z-mean)/scale])
    penalty=np.eye(a.shape[1])*alpha;penalty[0,0]=0
    coef=np.linalg.solve(a.T@(w[:,None]*a)+penalty,a.T@(w*y))
    return b@coef


def shuffled_baskets(frame,seed=42):
    out=frame.copy();rng=np.random.default_rng(seed)
    for _,g in frame.groupby('date',sort=True):
        order=rng.permutation(len(g));out.loc[g.index,SHARES]=g[SHARES].to_numpy()[order]
    return out


def diagnostics(joined):
    valid,checks=valid_baskets(joined)
    d=joined[valid & np.isfinite(joined.weight)&(joined.weight>0)].copy()
    records={}
    for month,g in d.groupby('date',sort=True):
        record={'n':len(g),'valid_weight_sum':float(g.weight.sum()),'basket':{},'groups':{}}
        for category,col in zip(CATEGORIES,SHARES):
            q=summary(g[col],g.weight)
            record['basket'][category]={'mean_share_pct':q['weighted_mean_pp'],'median_share_pct':q['weighted_median_pp'],
                                       'p25_share_pct':q['weighted_p25_pp'],'p75_share_pct':q['weighted_p75_pp']}
        for category,col in [('food','qsp5_3'),('housing','qsp5_1'),('transportation','qsp5_5')]:
            low=weighted_quantile(g[col],g.weight,.25);high=weighted_quantile(g[col],g.weight,.75)
            if low>=high:continue
            record['groups'][category]={'low_threshold_share_pct':low,'high_threshold_share_pct':high}
            for label,h in [('low',g[g[col]<=low]),('high',g[g[col]>=high])]:
                record['groups'][category][label]={key:summary(h[key],h.weight,interpolate=(key=='Q8v2part2')) for key in PROTOCOL['outcomes']}
        records[str(int(month))]=record
    return {'valid_joined_n':len(d),'invalid':checks,'months':records},d


def structural_experiment(frame):
    """Predeclared chronological comparison; not a nationwide forecast.

    Test targets are centered ONLY to define the retrospective outcome. The
    centering mean is never passed to features or used to initialize an Agent.
    """
    result={}
    for outcome in PROTOCOL['outcomes']:
        d=frame.dropna(subset=PROFILE+[outcome,'weight']).copy().reset_index(drop=True)
        d=d[np.isfinite(d[outcome])&np.isfinite(d.weight)&(d.weight>0)].reset_index(drop=True)
        train=(d.date//100).isin(PROTOCOL['train_years']);test=(d.date//100).isin(PROTOCOL['assessment_years'])
        if train.sum()<100 or test.sum()<100:raise ValueError('Insufficient chronology support')
        # Vocabulary learned on training demographics only; unseen categories all zero, reported.
        vocab={c:sorted(d.loc[train,c].unique()) for c in PROFILE}
        demo=np.column_stack([(d[c].to_numpy()==v).astype(float) for c in PROFILE for v in vocab[c][1:]])
        real=d[SHARES[:-1]].to_numpy(float)/100
        shuffled=shuffled_baskets(d)[SHARES[:-1]].to_numpy(float)/100
        w=(d.weight/d.groupby('date').weight.transform('sum')*1000).to_numpy(float)
        y=centered(d[outcome],d.date,d.weight)
        predictions={}
        for arm,x in [('demographics',demo),('demographics_actual_basket',np.column_stack([demo,real])),
                      ('demographics_shuffled_basket',np.column_stack([demo,shuffled]))]:
            predictions[arm]=ridge_predict(x[train],y[train],w[train],x[test],PROTOCOL['alpha'])
        evaluation=d[test].copy();evaluation['truth_centered']=y[test]
        for arm,pred in predictions.items():evaluation[arm]=pred
        years={}
        seen=set(d.loc[train,'userid'])
        for year,g in evaluation.groupby(evaluation.date//100):
            metrics={}
            for arm in predictions:
                error=g[arm]-g.truth_centered;wg=g.weight/g.groupby('date').weight.transform('sum')
                mse=float(np.average(error**2,weights=wg));zero=float(np.average(g.truth_centered**2,weights=wg))
                metrics[arm]={'mae_pp':float(np.average(error.abs(),weights=wg)),'rmse_pp':mse**.5,
                              'r2_vs_month_mean':1-mse/zero if zero else None}
            fresh=g[~g.userid.isin(seen)]
            fresh_metrics={}
            for arm in predictions:
                err=fresh[arm]-fresh.truth_centered
                wf=fresh.weight/fresh.groupby('date').weight.transform('sum')
                mse=float(np.average(err**2,weights=wf))
                fresh_metrics[arm]={'mae_pp':float(np.average(err.abs(),weights=wf)), 'rmse_pp':mse**.5}
            years[str(int(year))]={'n':len(g),'months':int(g.date.nunique()),'not_seen_in_training_n':len(fresh),'arms':metrics,
                                  'never_seen_in_training_arms':fresh_metrics}
        result[outcome]={'train_n':int(train.sum()),'assessment_n':int(test.sum()),'unseen_demographic_category_n':int(sum((~d.loc[test,c].isin(vocab[c])).sum() for c in PROFILE)),
                         'years':years,'monthly_mean_not_an_input':True}
    return result


def run(root,out):
    root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    raw=root/'data/raw/sce_spending_20261009/spending_microdata.xlsx'
    cache=root/'data/cache/sce_spending_20261009.parquet'
    corepath=root/'outputs/sce_numeracy_audit_20261008_v4/micro_evaluation_private.parquet'
    profilepath=root/'data/cache/monthly_profiles_7f0ed622ae0915902741.parquet'
    paths=[raw,cache,corepath,profilepath,root/'data/raw/sce_spending_20261009/manifest.json']
    hashes={str(p.relative_to(root)):sha(p) for p in paths}
    # Cache is verified against the original official workbook, not simply trusted.
    original=pd.read_excel(raw,skiprows=1,usecols=['userid','date']+SHARES)
    s=pd.read_parquet(cache);pd.testing.assert_frame_equal(original,s,check_dtype=False)
    core=pd.read_parquet(corepath);profiles=pd.read_parquet(profilepath)
    keys=core[['userid','date']].merge(profiles[['userid','date']],validate='one_to_one')
    assert len(keys)==len(core)==len(profiles)
    joined=join_core(s,core);description,d=diagnostics(joined)
    eligible=s[s.date.between(202001,202412)]
    assert len(joined)==len(eligible),'Not all overlapping-wave records link'
    valid,invalid=valid_baskets(s)
    waves={str(int(month)):{'n':len(g),'valid_nine_share_n':int(valid.loc[g.index].sum())} for month,g in s.groupby('date')}
    target=profiles[profiles.date.isin([202105,202106])]
    hist=historical_baskets(s,target)
    hist.to_parquet(out/'historical_baskets_private.parquet',index=False)
    d.to_parquet(out/'linked_evaluation_private.parquet',index=False)
    coverage={}
    for month,g in target.groupby('date'):
        h=hist[hist.date==month];coverage[str(int(month))]={'full_target_n':len(g),'recent_basket_n':len(h),
           'lag_counts':{str(int(k)):int(v) for k,v in h.basket_age_months.value_counts().items()},
           'survey_weight_coverage':float(h.weight.sum()/g.weight.sum())}
        selection={}
        for c in PROFILE:
            allp=g.groupby(c).weight.sum()/g.weight.sum()
            eligiblep=h.groupby(c).weight.sum()/h.weight.sum()
            selection[c]={'full_weighted_proportions':{str(k):float(v) for k,v in allp.items()},
                          'eligible_weighted_proportions':{str(k):float(v) for k,v in eligiblep.items()},
                          'max_absolute_proportion_gap':float((allp-eligiblep.reindex(allp.index,fill_value=0)).abs().max())}
        coverage[str(int(month))]['selection_diagnostic']=selection
    result={'audit_id':out.name,'protocol':PROTOCOL,'new_llm_calls':0,'new_paid_mcp_calls':0,
            'source_rows':len(s),'source_month_range':[int(s.date.min()),int(s.date.max())],
            'source_people':int(s.userid.nunique()),'waves':waves,'source_valid_nine_share_n':int(valid.sum()),
            'source_invalid':invalid,'linkage':{'overlap_rows':len(eligible),'matched_rows':len(joined),
                     'duplicate_keys':0,'core_weight_source':'Same-month core SCE; spending workbook has no survey weights',
                     'identity_support':'All overlapping 2020-24 respondent-months match; official rotating-module statement and primary paper document same households. No independent demographic fields in spending workbook.'},
            'descriptive':description,'recent_basket_coverage':coverage,'structural_experiment':structural_experiment(d),
            'schema_history':{'201412':'Eight categories only; category9 added201504. Not eligible for the nine-share analysis; missing here is structural.'},
            'limits':['QSP5 is recalled nominal expenditure composition, not price, purchase frequency or measured attention.',
                      'Current file covers through202412 only; live chart recency does not imply newer microdata.',
                      'Nine categories do not map one-to-one to CPI; transport is not gasoline and housing includes mortgage.',
                      'Spending future predictions excluded from P; they are not observed baskets.',
                      'Same-month and past-wave links are retrospective A inputs, not proof of B availability.',
                      'Within-month residual prediction is a structural probe, not national headline prediction or causal identification.',
                      'Public source has no separate spending interview date; cannot establish same-day sequence.',
                      'Incomplete baskets excluded; complete-case selection can bias associations.'],
            'sources_sha256':hashes}
    snap=out/'source_snapshot';snap.mkdir()
    for p in [Path(__file__),root/'scripts/audit_sce_spending.py']:
        (snap/p.name).write_bytes(p.read_bytes());hashes[str(p.relative_to(root))]=sha(p)
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'linkage':result['linkage'],'recent_basket_coverage':coverage,'valid_joined_n':len(d)},ensure_ascii=False),flush=True)
    return result
