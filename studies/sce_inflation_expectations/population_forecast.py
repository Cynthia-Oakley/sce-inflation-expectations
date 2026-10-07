"""B-line profile-only weighted joint donors; no survey outcomes accepted."""
from datetime import datetime
import numpy as np
import pandas as pd
from .monthly_population import PROFILE_COLUMNS, CATEGORY_MAPS, EMPLOYMENT, EMPLOYMENT_PRIORITY, _month_index

ATTRIBUTES=['age_group','education_group','household_income_band','region','numeracy','employment_status','housing_tenure']


def profile_view(frame):
    d=frame[PROFILE_COLUMNS+['weight']].copy().sort_values(['userid','date'])
    if d[['date','userid']].isna().any().any() or d.duplicated(['date','userid']).any():
        raise ValueError('nonunique or missing profile key')
    out=d[['date','userid','weight']].copy()
    for source,name in [('_AGE_CAT','age_group'),('_REGION_CAT','region')]:
        out[name]=d[source].astype('string').fillna('unknown')
    for source,(name,mapping) in CATEGORY_MAPS.items():
        out[name]=d[source].map(mapping).fillna('unknown')
    out['employment_status']=np.select([d[f'Q10_{i}'].eq(1).fillna(False).to_numpy(dtype=bool) for i in EMPLOYMENT_PRIORITY],
                                       [EMPLOYMENT[i] for i in EMPLOYMENT_PRIORITY],default='unknown')
    q=pd.to_numeric(d.Q43,errors='coerce').where(d.Q43.isin([1,2,3]))
    housing=q.groupby(d.userid).ffill()
    source_date=d.date.where(q.notna()).groupby(d.userid).ffill()
    last_move=d.date.where(d.D3.eq(1)).groupby(d.userid).ffill()
    usable=source_date.notna() & ~(last_move>source_date)
    out['housing_tenure']=housing.where(usable).map({1:'owner',2:'renter',3:'other'}).fillna('unknown')
    out['housing_reference_month']=source_date.where(usable)
    return out.reset_index(drop=True)


def donor_probabilities(view, end_month, window=1):
    if window not in (1,12):raise ValueError('supported donor windows are 1 and 12')
    months=sorted(view.loc[view.date<=end_month,'date'].unique())[-window:]
    if len(months)!=window:raise ValueError('donor history incomplete')
    d=view[view.date.isin(months)].copy()
    w=pd.to_numeric(d.weight,errors='coerce')
    if (w.notna() & (~np.isfinite(w)|(w<=0))).any():
        raise ValueError('nonmissing donor weights must be positive finite')
    # Missing official weights are not replaced by fabricated survey weights.
    # Such rows stay in raw distribution diagnostics but cannot be weighted donors.
    d=d.loc[w.notna()].copy();w=w.loc[d.index]
    if d.date.nunique()!=len(months):raise ValueError('source wave has no weighted donors')
    # Equal mass per source wave, not proportional to pooled rows or weights.
    p=w/w.groupby(d.date).transform('sum')/len(months)
    return d.reset_index(drop=True),p.to_numpy(),list(map(int,months))


def synthesize(view, *, target_month, donor_end, available_at, cutoff, n=1200, core_n=300, window=1, seed=42):
    known,asof=datetime.fromisoformat(available_at),datetime.fromisoformat(cutoff)
    if known.tzinfo is None or asof.tzinfo is None or known>asof:
        raise ValueError('donor snapshot unavailable by cutoff')
    target=int(target_month.replace('-',''))
    _month_index(target);_month_index(donor_end)
    if int(donor_end)>=target:raise ValueError('same/future wave forbidden in forecast P')
    if not 1<=core_n<=n:raise ValueError('invalid Core/total sizes')
    d,p,months=donor_probabilities(view,int(donor_end),window)
    rng=np.random.default_rng(np.random.SeedSequence([seed,target,window]))
    positions=rng.choice(len(d),size=n,replace=True,p=p)
    ids=[f'b_synthetic_{target}_{i+1:05d}' for i in range(n)]
    # SRS Core fits the existing expansion estimator's equal-probability contract.
    core=set(rng.choice(n,size=core_n,replace=False).tolist())
    people=[];provenance=[]
    for i,k in enumerate(positions):
        row=d.iloc[k]
        attrs={a:str(row[a]) for a in ATTRIBUTES if str(row[a])!='unknown'}
        people.append({'agent_id':ids[i],'attributes':attrs,'weight':1.,'group_key':None,
                       'init_state':{'target_month':'','direction':'','point_pct':0.,'q9_valid':False}})
        provenance.append({'agent_id':ids[i],'donor_userid':int(row.userid),'donor_month':int(row.date),
                           'housing_reference_month':None if pd.isna(row.housing_reference_month) else int(row.housing_reference_month)})
    bundle={'study_id':'sce_inflation_expectations','personas':people,'interaction':{'kind':'none','edges':None,'adjacency_ref':None},
            'propagation':'independent','provider_ref':'sce_inflation_expectations.population',
            'provider_args':{'source':'past_public_SCE_weighted_joint_donors','research_line':'B_population_candidate','seed':seed,'target_month':target_month},
            'materialized_count':n}
    # Neither donor identifiers nor weights are placed in persona attributes.
    meta={'target_month':target_month,'as_of':cutoff,'donor_snapshot_available_at':available_at,'source_months':months,
          'donor_n':len(d),'unique_source_people':int(d.userid.nunique()),'donor_sampling_ess':float(1/(p*p).sum()),
          'excluded_missing_weight_rows':int(view.date.isin(months).sum()-len(d)),
          'unique_used_donor_ids':int(d.iloc[positions].userid.nunique()),'synthetic_n':n,'core_n':core_n,'normal_n':n-core_n,
          'window':window,'seed':seed,'core_design':'independent_srs','core_inclusion_probability':core_n/n,
          'core_ids':[ids[i] for i in sorted(core)],'neutral_persona_weights':True,
          'weighting_note':'historical survey weights used once in donor sampling; no second multiplication by source weights',
          'limitations':['old observed profiles are synthetic current types, not current true households',
                         'shared donors and Normal expansion do not create independent evidence',
                         'no income/employment transition or panel rotation implemented',
                         'no current survey responses, current survey weights, or current IDs used']}
    return bundle,meta,provenance
