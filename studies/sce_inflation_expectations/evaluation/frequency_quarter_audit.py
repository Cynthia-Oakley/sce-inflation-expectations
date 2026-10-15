"""Offline 2020 Diary quarter and matching sensitivity; no respondent answers/API."""
from collections import Counter, defaultdict
from pathlib import Path
import json
import math
import zipfile

import numpy as np

from ..diary_experience import (
    _parse_csv_member, _week_number, _hash_key, _xlsx_sheet_rows, _effective,
    category_map_from_dictionary, file_sha256,
)
from ..purchase_frequency_matching import (
    SOURCE, FIELDS, CATEGORIES, normalize_attributes, frequency_vector,
)

ROOT = Path(__file__).resolve().parents[3]
OLD = ROOT / 'outputs/sce_purchase_frequency_preparation_20261015_v1'


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def number(x):
    try:
        n = float(x)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def income_band(x):
    return 'under_50k' if x < 50000 else '50k_to_100k' if x <= 100000 else 'over_100k'


def load_quarters():
    manifest = json.loads((SOURCE/'manifest.json').read_text())
    archive = Path(manifest['source']['archive_path']); dictionary = Path(manifest['dictionary']['path'])
    assert file_sha256(archive) == manifest['source']['archive_sha256']
    assert file_sha256(dictionary) == manifest['dictionary']['sha256']
    quarters = {}; evidence = {}; source = {'archive':str(archive.relative_to(ROOT)),
        'archive_sha256':file_sha256(archive), 'dictionary':str(dictionary.relative_to(ROOT)),
        'dictionary_sha256':file_sha256(dictionary), 'members':{}}
    with zipfile.ZipFile(archive) as z:
        cu_quarters = defaultdict(set)
        for q in range(1,5):
            broad, known, _ = category_map_from_dictionary(dictionary, year=2020, quarter=q)
            mapping = {u:k for u,k in broad.items() if k in CATEGORIES[:2]}
            for u in ['330110','330210','330310','330510']:
                assert u in known and broad.get(u) == 'household_supplies_services'
                mapping[u] = 'household_cleaning_paper'
            mapping.update({u:'personal_care_products' for u,k in broad.items()
                            if k == 'personal_care_products_services' and u.startswith('640')})
            fmld, _, h1 = _parse_csv_member(z,f'diary20/fmld20{q}.csv')
            expd, headers, h2 = _parse_csv_member(z,f'diary20/expd20{q}.csv')
            assert {'EXPNSQDY','EXPN_QDY'} <= set(headers)
            source['members'][str(q)] = {'fmld_sha256':h1,'expd_sha256':h2,
                'category_uccs':{k:sorted(u for u,v in mapping.items() if v == k) for k in CATEGORIES}}
            details = defaultdict(list)
            for row in expd: details[row['NEWID']].append(row)
            assert not set(details)-{r['NEWID'] for r in fmld}
            rows=[]; excluded=Counter(); raw_status={k:Counter() for k in CATEGORIES}
            for r in fmld:
                newid=r['NEWID']; cu_quarters[newid[:-1]].add(q)
                vec=frequency_vector(details[newid],mapping)
                for k in CATEGORIES: raw_status[k][vec[k]['status']] += 1
                attrs=normalize_attributes(r); weight=number(r.get('FINLWT21'))
                if 'age_group' not in attrs or 'household_income_band' not in attrs or weight is None or weight<=0:
                    excluded['missing_age_income_or_weight']+=1;continue
                if any(vec[k]['recorded_days_7d'] is None for k in CATEGORIES):
                    excluded['unknown_or_partial_frequency']+=1;continue
                days=[vec[k]['recorded_days_7d'] for k in CATEGORIES]
                imputed=[number(r.get('FINCBEF'+str(i))) for i in range(1,6)]
                rows.append({'quarter':q,'cu_key':_hash_key(f'cu|Q{q}',newid[:-1]),
                    'week_key':_hash_key(f'week|Q{q}',newid),'week_number':_week_number(r),
                    'attributes':attrs,'weight':weight,'days':days,
                    'any_positive':any(days),'family_size':number(r.get('FAM_SIZE')),
                    'children_under18':number(r.get('PERSLT18')),
                    'imputation_spans_bands':len({income_band(v) for v in imputed})>1 if all(v is not None for v in imputed) else None})
            quarters[q]=rows
            evidence[q]={'raw_week_rows':len(fmld),'complete_week_rows_including_zero':len(rows),
                'complete_zero_contact_weeks':sum(not r['any_positive'] for r in rows),
                'selected_positive_week_rows':sum(r['any_positive'] for r in rows),
                'selected_positive_CUs':len({r['cu_key'] for r in rows if r['any_positive']}),
                'excluded':dict(excluded),'raw_category_status_counts':{k:dict(v) for k,v in raw_status.items()},
                'five_imputation_cross_band_week_fraction':float(np.mean([r['imputation_spans_bands'] for r in rows if r['imputation_spans_bands'] is not None]))}
        source['CU_ids_crossing_quarters']=sum(len(v)>1 for v in cu_quarters.values())
        assert source['CU_ids_crossing_quarters']==0, 'Cross-quarter CU deduplication needs explicit handling'
    assert evidence[4]['selected_positive_CUs']==1348 and evidence[4]['selected_positive_week_rows']==2426
    old={r['week_key']:r for d in json.loads((OLD/'donors_private.json').read_text()) for r in d['weeks']}
    current={r['week_key']:r for r in quarters[4] if r['any_positive']}
    assert set(old)==set(current)
    assert all([old[k]['categories'][c]['recorded_days_7d'] for c in CATEGORIES]==v['days'] for k,v in current.items())
    source['q4_original_vectors_reproduced']=len(current)
    return quarters,evidence,source,dictionary


def cu_first_probabilities(rows):
    """Mean eligible-week CU weight, then weight-proportional week selection."""
    idx=defaultdict(list)
    for i,r in enumerate(rows):idx[r['cu_key']].append(i)
    assert all(len(v)<=2 for v in idx.values())
    cu_w=np.array([np.mean([rows[i]['weight'] for i in indices]) for indices in idx.values()])
    p=np.zeros(len(rows))
    for (indices,w) in zip(idx.values(),cu_w):
        week_w=np.array([rows[i]['weight'] for i in indices]);p[indices]=w/cu_w.sum()*week_w/week_w.sum()
    assert np.isclose(p.sum(),1) and np.all(p>=0)
    return p,len(idx),float(cu_w.sum()**2/np.square(cu_w).sum())


def distribution(rows,p=None):
    if p is None:p,_,_=cu_first_probabilities(rows)
    a=np.array([r['days'] for r in rows],float)
    return {k:{'mean_days':float(p@a[:,j]),'zero_share':float(p@(a[:,j]==0)),
               'day_probabilities':[float(p@(a[:,j]==i)) for i in range(8)]} for j,k in enumerate(CATEGORIES)}


def pool_for_profile(rows,profile,*,fixed_core=False):
    fields=[k for k in FIELDS if k in profile]
    active=['household_income_band','age_group'] if fixed_core else list(fields)
    while True:
        subset=[r for r in rows if all(r['attributes'].get(k)==profile[k] for k in active)]
        if subset:
            probs,n,eff=cu_first_probabilities(subset)
            if fixed_core or (n>=25 and eff>=15):break
        if not active:raise ValueError('No globally supported pool')
        active.pop()
    return subset,probs,{'matched_fields':active.copy(),'units':n,'effective_units':eff,
                        'below_original_support_threshold':n<25 or eff<15}


def target_distribution(rows,assignments,*,fixed_core=False,seeds=200):
    cache={}; expected=[]; support=[]; cdfs=[]; values=[]
    for a in assignments:
        key=tuple((k,a['profile'].get(k)) for k in FIELDS)
        if key not in cache:
            sub,p,receipt=pool_for_profile(rows,a['profile'],fixed_core=fixed_core)
            cache[key]=(sub,p,receipt)
        sub,p,receipt=cache[key]; expected.append(distribution(sub,p));support.append(receipt)
        cdfs.append(np.cumsum(p));values.append(np.array([r['days'] for r in sub]))
    averaged={k:{measure:float(np.mean([e[k][measure] for e in expected])) for measure in ['mean_days','zero_share']} for k in CATEGORIES}
    random_means=[]
    for seed in range(seeds):
        rng=np.random.default_rng(np.random.SeedSequence([20261015,seed]))
        draw=[v[min(int(np.searchsorted(cdf,rng.random(),side='right')),len(v)-1)] for cdf,v in zip(cdfs,values)]
        random_means.append(np.mean(draw,axis=0))
    arr=np.array(random_means)
    original=np.array([[a['recorded_days_7d'][k] for k in CATEGORIES] for a in assignments]).mean(axis=0)
    for j,k in enumerate(CATEGORIES):
        averaged[k]['seed_mean_central95']=np.quantile(arr[:,j],[.025,.975]).tolist()
        averaged[k]['original_assigned_mean']=float(original[j])
        averaged[k]['original_mean_within_seed_central95']=bool(np.quantile(arr[:,j],.025)<=original[j]<=np.quantile(arr[:,j],.975))
    return {'n_profiles':len(assignments),'n_unique_profile_patterns':len(cache),'categories':averaged,
        'retained_field_patterns':dict(Counter(','.join(r['matched_fields']) for r in support)),
        'field_retention':{k:{'available':sum(k in a['profile'] for a in assignments),
                              'retained':sum(k in r['matched_fields'] for r in support)} for k in FIELDS},
        'minimum_CUs':min(r['units'] for r in support),'minimum_effective_CUs':min(r['effective_units'] for r in support),
        'below_support_profiles':sum(r['below_original_support_threshold'] for r in support),
        'seed_count':seeds,'seed_interpretation':'Central range across donor draws with fixed source/profile; not a survey CI or LLM error interval.'}


def dictionary_checks(path):
    variables=_xlsx_sheet_rows(path,'Variables');codes=_xlsx_sheet_rows(path,'Codes ')
    wanted=['FINCBEFM','FINCBEF1','FAM_SIZE','PERSLT18']
    vars_out={k:[] for k in wanted}
    for r in variables:
        if len(r)>=13 and r[0]=='DIARY' and r[1]=='FMLD' and r[2] in wanted and _effective(r[9],r[10],r[11],r[12],2020,4):
            vars_out[r[2]].append({'description':r[3],'start':r[9:11]})
    tenure={}
    for r in codes:
        if len(r)>=9 and tuple(r[:3])==('DIARY','FMLD','CUTENURE') and _effective(r[5],r[6],r[7],r[8],2020,4):
            tenure[str(r[3])]=r[4]
    assert set(tenure)==set('123456')
    return {'variables':vars_out,'tenure_codes_2020':tenure,
        'current_income_match':'CE last-12-month before-tax CU income mean/coarse band vs SCE supplied household income category; CU/household boundaries and original SCE categorisation not fully equivalent.',
        'assets':'Only housing tenure is used; it is not home value, housing equity, liquid assets or net wealth. No common measured asset variable is available in the current matching whitelist.',
        'unused_joint_variables':['CE FAM_SIZE','CE PERSLT18','actual household shopping responsibility'],
        'do_not_infer':'Income matching does not imply wealth matching; two-week imputation category changes are not economic income transitions.'}


def run(out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored output required')
    assignments=json.loads((OLD/'assignments_private.json').read_text())
    q,audit,source,dictionary=load_quarters();selected={k:[r for r in v if r['any_positive']] for k,v in q.items()}
    quarterly={};positive_pool=[];all_pool=[]
    for k,rows in q.items():
        sel=selected[k];_,_,_=cu_first_probabilities(sel)
        quarterly[k]={'source':audit[k],'selected_distribution':distribution(sel),
            'including_supported_zero_distribution':distribution(rows),
            'fixed_income_age_standardized':target_distribution(sel,assignments,fixed_core=True,seeds=200),
            'current_priority_matching':target_distribution(sel,assignments,seeds=200)}
        # Normalize total CU weight per quarter before pooling; each quarter
        # contributes equal unconditional source mass. Never pool raw week counts.
        for collection,destination in [(sel,positive_pool),(rows,all_pool)]:
            groups=defaultdict(list)
            for r in collection:groups[r['cu_key']].append(r['weight'])
            mass=sum(np.mean(v) for v in groups.values())
            destination.extend([{**r,'weight':r['weight']/mass/4} for r in collection])
    assert all(all(a['profile'].get(k)==a['selected_week_attributes'].get(k) for k in a['matched_fields']) for a in assignments)
    actual_matches={k:{'available':sum(k in a['profile'] for a in assignments),
        'required_and_kept':sum(k in a['matched_fields'] for a in assignments),
        'realized_agreement':sum(k in a['profile'] and a['profile'][k]==a['selected_week_attributes'].get(k) for a in assignments)} for k in FIELDS}
    assert all(quarterly[4]['current_priority_matching']['field_retention'][k]['retained']==v['required_and_kept']
               for k,v in actual_matches.items()), 'Q4 fallback must reproduce the frozen matcher'
    summary={'status':'completed_offline_quarter_and_matching_audit','new_api_calls':0,
        'source':source,'source_sha256':{str((OLD/'assignments_private.json').relative_to(ROOT)):file_sha256(OLD/'assignments_private.json'),
            str(Path(__file__).resolve().relative_to(ROOT)):file_sha256(__file__)},
        'quarterly':quarterly,'current_actual_matching':actual_matches,'dictionary_evidence':dictionary_checks(dictionary),
        'pooled_equal_quarter_source':{'method':'Each quarter normalized to equal unconditional CU source mass; same current fallback/minimums, not an official CE estimate.',
            'selected_distribution':distribution(positive_pool),
            'matching':target_distribution(positive_pool,assignments),
            'including_supported_zero_matching':target_distribution(all_pool,assignments)},
        'limits':['2020 quarters only: season, COVID and collection effects cannot be separated; not evidence of stability over 2021-2025.',
            'Current corrected retrospective A inputs; B needs independently established historical availability.',
            'No target-month SCE answers read; source/matching sensitivity is not a simulated error comparison.',
            'Random-seed ranges condition on donors and profiles; no survey sampling or donor imputation uncertainty included.',
            'Supported zero weeks are not never-buy households; missing/partial days still excluded.']}
    out.mkdir(parents=True);dump(out/'summary.json',summary)
    dump(out/'donor_weeks_private.json',q)
    print(json.dumps({'status':summary['status'],'quarters':{k:v['source']['selected_positive_CUs'] for k,v in quarterly.items()},
        'original_match':actual_matches,'pooled_match':summary['pooled_equal_quarter_source']['matching']['field_retention']},ensure_ascii=False))
    return summary
