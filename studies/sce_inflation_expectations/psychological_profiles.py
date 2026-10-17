"""Exploratory A-line sidecars; independent of simulation and evaluation truth.

Weighted whole-person GSS donor. Fine matching falls back by pooling region,
retaining age, education and historical nominal family-income proxy.
"""
from __future__ import annotations
import hashlib,json
import numpy as np
import pandas as pd

BASIC=['_AGE_CAT','_EDU_CAT','_HH_INC_CAT']
FINE=BASIC+['_REGION_CAT']

def valid_key(row,keys):
    vals=[row[k] for k in keys]
    return None if any(pd.isna(x) for x in vals) else tuple(map(str,vals))


def build_sidecars(profiles,donors,*,seed=42,draw=0,min_ess=10.,source_hash,include_household_state=True):
    if not np.isfinite(min_ess) or min_ess<=0:raise ValueError('min_ess must be positive')
    if profiles.duplicated(['date','userid']).any():raise ValueError('duplicate recipient-month')
    if donors.id.duplicated().any():raise ValueError('duplicate donors')
    pools=[]
    for keys in [FINE,BASIC]:
        registry={}
        for key,g in donors.dropna(subset=keys).sort_values('id').groupby(keys,sort=True):
            w=g.donor_weight.to_numpy(float)
            if not (np.isfinite(w)&(w>0)).all():raise ValueError('invalid donor weights')
            ess=float(w.sum()**2/(w@w));registry[key]=(g,w/w.sum(),ess)
        pools.append(registry)
    out=[]
    for _,p in profiles.sort_values(['date','userid']).iterrows():
        uid=int(p.userid);selected=None
        for tier,keys in enumerate([FINE,BASIC]):
            key=valid_key(p,keys)
            entry=pools[tier].get(key)
            if entry is not None and entry[2]>=min_ess:
                selected=(tier,keys,key,entry);break
        rec={'agent_id':f'sce_u{uid}','target_month':str(int(p.date)), 'draw_id':draw,'assignment_seed':seed,
             'source_survey':'GSS','source_wave':2018,'source_hash':source_hash,
             'eligibility':'A_exploratory_only_not_verified_B_vintage',
             'temporal_assumption':'held_constant_synthetic_state_if_matching_covariates_unchanged',
             'psychological_attributes':{'HAPPY':None,'SATFIN':None},'support_status':'unsupported',
             'donor_local_id':None,'fallback_tier':None,'donor_ess':0.,'donor_n':0,'match_fields':None}
        if include_household_state:
            rec['observed_household_state']={'financial_change_12m_code':int(p.Q1),'source':'SCE_Q1_current_microdata'}
        if selected:
            tier,keys,key,(g,prob,ess)=selected
            token=json.dumps([seed,draw,uid,list(key),tier],ensure_ascii=False).encode()
            random_seed=int.from_bytes(hashlib.sha256(token).digest()[:8],'big')
            d=g.iloc[np.random.default_rng(random_seed).choice(len(g),p=prob)]
            rec.update({'psychological_attributes':{'HAPPY':int(d.happy),'SATFIN':int(d.satfin)},
                        'support_status':'synthetic_assigned','donor_local_id':int(d.id),'fallback_tier':tier,
                        'donor_ess':ess,'donor_n':len(g),'match_fields':keys,
                        'matching_values':list(key),'observed_or_synthetic':'external_synthetic_not_true_SCE_psychology'})
        out.append(rec)
    return out


def candidate_text(rec):
    """Preview only: no IDs, donor metadata, survey weights or outcome fields."""
    finance={1:'much worse',2:'somewhat worse',3:'about the same',4:'somewhat better',5:'much better'}
    happy={1:'very happy',2:'pretty happy',3:'not too happy',None:'unknown'}
    sat={1:'pretty well satisfied',2:'more or less satisfied',3:'not satisfied at all',None:'unknown'}
    q=rec['psychological_attributes']
    return ('Past 12 months, reported household financial position: '+finance[rec['observed_household_state']['financial_change_12m_code']]+'.\n'
           +'General happiness: '+happy[q['HAPPY']]+'.\n'
           +'Satisfaction with current financial situation: '+sat[q['SATFIN']]+'.')
