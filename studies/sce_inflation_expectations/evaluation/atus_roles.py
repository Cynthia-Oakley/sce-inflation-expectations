"""Public ATUS role support and external news-frequency checks; no SCE truth/API."""
from collections import Counter
from io import BytesIO
import json
from pathlib import Path
from time import perf_counter
from zipfile import ZipFile

import numpy as np
import pandas as pd

from .attention_support import ARCHIVE, FEATURES, ROOT, cross_validate, harmonize, sha

SOURCE = ROOT/'data/raw/behavior_references/2026-10-19_atus_roles_v2'
SUPPLEMENT = ROOT/'data/raw/behavior_references/2026-10-19_atus_roles_supplement_v1'
PLAN = ROOT/'docs/workstreams/20261018_targeted_mechanisms/atus_and_attention_support_plan_20261019.md'


def load_csv_zip(path):
    with ZipFile(path) as archive:
        candidates = [name for name in archive.namelist() if name.lower().endswith(('.dat', '.csv'))]
        if len(candidates) != 1 or archive.testzip() is not None:
            raise ValueError('One intact comma-separated public data member required')
        return pd.read_csv(BytesIO(archive.read(candidates[0])), dtype={'TUCASEID': 'string'})


def join_role_files(eh, respondent, cps, roster):
    keys = ['TUCASEID', 'TULINENO']
    if not eh.TULINENO.eq(1).all() or eh.duplicated(keys).any():
        raise ValueError('EH respondent must be one record per case, person line 1')
    cps = cps.loc[cps.TULINENO.eq(1)]
    roster = roster.loc[roster.TULINENO.eq(1)]
    result = eh.merge(respondent[keys+['TELFS', 'TRNUMHOU', 'TRCHILDNUM']], on=keys,
        how='left', validate='one_to_one', indicator=True)
    if not result['_merge'].eq('both').all():
        raise ValueError('EH respondent missing basic ATUS match')
    result = result.drop(columns='_merge').merge(cps[keys+['PEEDUCA', 'HEFAMINC', 'GEREG']],
        on=keys, how='left', validate='one_to_one', indicator=True)
    if not result['_merge'].eq('both').all():
        raise ValueError('EH respondent missing CPS respondent match')
    result = result.drop(columns='_merge').merge(roster[keys+['TEAGE', 'TESEX']],
        on=keys, how='left', validate='one_to_one', indicator=True)
    if not result['_merge'].eq('both').all() or len(result) != len(eh):
        raise ValueError('EH respondent missing current ATUS age/sex or join altered size')
    return result.drop(columns='_merge')


def role_features(frame):
    d = frame.copy()
    d['age_group'] = np.where(d.TEAGE < 40, 'under_40', np.where(d.TEAGE <= 60, '40_to_60', 'over_60'))
    d['education_group'] = np.where(d.PEEDUCA <= 39, 'high_school', np.where(d.PEEDUCA <= 42, 'some_college', 'college'))
    d['income_group'] = np.where(d.HEFAMINC <= 11, 'under_50k', np.where(d.HEFAMINC <= 14, '50k_to_under_100k', '100k_plus'))
    for source, target, valid in [('TEAGE', 'age_group', d.TEAGE.ge(0)),
            ('PEEDUCA', 'education_group', d.PEEDUCA.between(31, 46)),
            ('HEFAMINC', 'income_group', d.HEFAMINC.between(1, 16))]:
        d.loc[~valid, target] = 'missing'
    d['region'] = d.GEREG.map({1: 'Northeast', 2: 'Midwest', 3: 'South', 4: 'West'}).fillna('missing')
    d['labor_group'] = d.TELFS.map({1: 'in_work', 2: 'in_work', 3: 'unemployed', 4: 'unemployed', 5: 'not_in_labor_force'}).fillna('missing')
    d['household_size_group'] = np.where(d.TRNUMHOU.eq(1), 'one', np.where(d.TRNUMHOU.eq(2), 'two', 'three_plus'))
    d.loc[d.TRNUMHOU.lt(1), 'household_size_group'] = 'missing'
    d['children_group'] = np.where(d.TRCHILDNUM.gt(0), 'with_children', 'no_children')
    d.loc[d.TRCHILDNUM.lt(0), 'children_group'] = 'missing'
    d['sex_cps'] = d.TESEX.map({1: 'male', 2: 'female'}).fillna('missing')
    return d


def smoothed_role_probabilities(train, test, columns, alpha=20):
    """Fixed sparse-cell shrinkage; survey-weighted class frequencies, actual n."""
    if alpha <= 0:
        raise ValueError('Positive fixed shrinkage required')
    y, w = train.EUGROSHP2.to_numpy(int)-1, train.EUFINLWGT.to_numpy(float)
    if np.any((y < 0)|(y >= 5)) or np.any(w <= 0) or not np.isfinite(w).all():
        raise ValueError('Only valid five-category roles and positive EH weights')
    base = np.bincount(y, weights=w, minlength=5)/w.sum()
    records = {}
    for index, row in enumerate(train[columns].itertuples(index=False, name=None)):
        records.setdefault(row, []).append(index)
    predictions, sizes = [], []
    for row in test[columns].itertuples(index=False, name=None):
        idx = records.get(row, [])
        n = len(idx)
        p = base if not n else np.bincount(y[idx], weights=w[idx], minlength=5)/w[idx].sum()
        predictions.append(n/(n+alpha)*p+alpha/(n+alpha)*base)
        sizes.append(n)
    return np.asarray(predictions), np.asarray(sizes)


def weighted_scores(y, p, w):
    y, p, w = np.asarray(y, int), np.asarray(p, float), np.asarray(w, float)
    if not np.allclose(p.sum(1), 1) or np.any(p < 0):
        raise ValueError('Invalid class probabilities')
    one_hot = np.eye(p.shape[1])[y]
    return {'log_loss': float(np.average(-np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1)), weights=w)),
        'brier': float(np.average(np.square(p-one_hot).sum(1), weights=w)),
        'rps': float(np.average(np.square(np.cumsum(p-one_hot, axis=1)[:, :-1]).mean(1), weights=w)),
        'accuracy': float(np.average(p.argmax(1) == y, weights=w))}


def proportions(frame, role):
    w = frame.EUFINLWGT.to_numpy(float)
    return {str(k): {'n': int(frame[role].eq(k).sum()),
        'weighted_share': float(w[frame[role].eq(k)].sum()/w.sum())} for k in sorted(frame[role].unique())}


def analyze_role_ablations(source, out):
    """Declared post-result decomposition, using prepared donors only."""
    source, out = Path(source).resolve(), Path(out).resolve()
    if not source.is_relative_to(ROOT/'outputs') or not out.is_relative_to(ROOT/'outputs') or out.exists():
        raise ValueError('Existing private donor folder and fresh ignored output required')
    train = pd.read_parquet(source/'role_donors_2022_private.parquet')
    test = pd.read_parquet(source/'role_donors_2023_private.parquet')
    sets = {'age_family': ['age_group','household_size_group','children_group'],
        'age_sex': ['age_group','sex_cps'],
        'age_family_sex': ['age_group','household_size_group','children_group','sex_cps'],
        'age_family_sex_labor': ['age_group','household_size_group','children_group','sex_cps','labor_group']}
    original = json.loads((source/'summary.json').read_text())
    baseline = original['role_2022_to_2023_validation']['weighted_scores']['population']
    results = {}
    for name, columns in sets.items():
        p,n = smoothed_role_probabilities(train,test,columns)
        scores = weighted_scores(test.EUGROSHP2.to_numpy(int)-1,p,test.EUFINLWGT)
        results[name] = {'features':columns,'scores':scores,
            'relative_log_loss_improvement_vs_population':(baseline['log_loss']-scores['log_loss'])/baseline['log_loss'],
            'weighted_share_training_cell_n_below_10':float(np.average(n<10,weights=test.EUFINLWGT))}
    receipt = {'status':'post_result_source_role_decomposition_only','new_api_calls':0,'sce_truth_read':False,
        'train_year':2022,'test_year':2023,'alpha_fixed':20,'baseline':baseline,'results':results,
        'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [source/'summary.json',source/'role_donors_2022_private.parquet',source/'role_donors_2023_private.parquet',PLAN]}}
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return receipt


def analyze(out):
    begin = perf_counter()
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output required')
    sources, frames, counts, descriptive = {}, {}, {}, {}
    for folder in [SOURCE, SUPPLEMENT]:
        manifest = json.loads((folder/'download_manifest.json').read_text())
        sources[str((folder/'download_manifest.json').relative_to(ROOT))] = sha(folder/'download_manifest.json')
        for record in manifest['records']:
            path = folder/record['file']
            if sha(path) != record['sha256']:
                raise ValueError('Downloaded public source changed')
            sources[str(path.relative_to(ROOT))] = record['sha256']
    for year in [2016, 2022, 2023]:
        suffix = f'_{year}.zip' if year == 2016 else f'-{year}.zip'
        eh, resp, cps = [load_csv_zip(SOURCE/(name+suffix)) for name in ['ehresp','atusresp','atuscps']]
        roster = load_csv_zip(SUPPLEMENT/('atusrost'+suffix))
        joined = join_role_files(eh, resp, cps, roster)
        role = 'EUGROSHP' if year == 2016 else 'EUGROSHP2'
        valid = joined.TEAGE.ge(18) & joined[role].isin(range(1, 4) if year == 2016 else range(1, 6)) & joined.EUFINLWGT.gt(0)
        frame = role_features(joined.loc[valid].copy())
        frames[year] = frame
        counts[str(year)] = {'eh_rows': len(eh), 'basic_respondent_rows': len(resp), 'all_cps_person_rows': len(cps),
            'joined_eh_rows': len(joined), 'adult_valid_role_n': len(frame),
            'invalid_or_missing_role_among_adults': int((joined.TEAGE.ge(18)&~joined[role].isin(range(1, 4) if year == 2016 else range(1, 6))).sum()),
            'role_question': role, 'weight': 'EUFINLWGT', 'role_proportions': proportions(frame, role)}
        descriptive[str(year)] = {}
        for feature in ['age_group','education_group','income_group','region','labor_group','household_size_group','children_group','sex_cps']:
            descriptive[str(year)][feature] = {str(label): proportions(group, role)
                for label, group in frame.groupby(feature) if len(group) >= 20}
    feature_sets = {'common_demographics': ['age_group','education_group','income_group','region'],
        'common_plus_labor': ['age_group','education_group','income_group','region','labor_group'],
        'common_plus_labor_family': ['age_group','education_group','income_group','region','labor_group','household_size_group','children_group'],
        'role_related_features': ['age_group','household_size_group','children_group','sex_cps']}
    train, test = frames[2022], frames[2023]
    base = proportions(train, 'EUGROSHP2')
    p = np.tile([base[str(k)]['weighted_share'] for k in range(1,6)], (len(test),1))
    prediction = {'population': weighted_scores(test.EUGROSHP2.to_numpy(int)-1,p,test.EUFINLWGT)}
    support = {}
    for name, columns in feature_sets.items():
        p, n = smoothed_role_probabilities(train, test, columns)
        prediction[name] = weighted_scores(test.EUGROSHP2.to_numpy(int)-1,p,test.EUFINLWGT)
        support[name] = {'zero_training_donor_weighted_share': float(np.average(n==0, weights=test.EUFINLWGT)),
            'fewer_than_10_training_donors_weighted_share': float(np.average(n<10, weights=test.EUFINLWGT)),
            'median_training_cell_n': float(np.median(n))}
    role_validation = {'train_year': 2022, 'test_year': 2023, 'alpha_fixed': 20, 'features': feature_sets,
        'weighted_scores': prediction, 'support': support,
        'relative_log_loss_improvement_vs_population': {k: (prediction['population']['log_loss']-v['log_loss'])/prediction['population']['log_loss'] for k,v in prediction.items()}}

    if sha(ARCHIVE) != 'ae34b5e4e67c5240bae5516eb10096e33e4a94266f8e4962631e437227e189d3':
        raise ValueError('External attention archive changed')
    with ZipFile(ARCHIVE) as archive:
        external = pd.read_stata(BytesIO(archive.read('out/data/associations.dta')), convert_categoricals=False)
    external = harmonize(external.loc[external.survey.eq('household')].copy()).reset_index(drop=True)
    external['labor_group'] = external.employment.map({1:'in_work',2:'in_work',9:'in_work',3:'unemployed',4:'not_in_labor_force',5:'not_in_labor_force',6:'not_in_labor_force',7:'not_in_labor_force'}).fillna('missing')
    external['economic_course'] = external.education_econ.fillna(0).astype(int).astype(str)
    attention = {}
    for column,k in [('follow_news',6),('know_news_pi',5),('know_news_u',5)]:
        d = external.loc[external[column].notna()].copy().reset_index(drop=True)
        fitted = cross_validate(d, d[column].astype(int).to_numpy()-1, k,
            {'common_demographics':FEATURES,'common_plus_labor':FEATURES+['labor_group'],
             'plus_economic_course_diagnostic_only':FEATURES+['labor_group','economic_course']},ordinal=True)
        fitted['unweighted_category_shares'] = (np.bincount(d[column].astype(int)-1,minlength=k)/len(d)).tolist()
        attention[column] = fitted
    joint = external.loc[external[['follow_news','know_news_pi','know_news_u']].notna().all(axis=1)]
    joint_counts = Counter(tuple(int(r[c]) for c in ['follow_news','know_news_pi','know_news_u']) for r in joint.to_dict('records'))
    result = {'status':'completed_external_support_only','new_api_calls':0,'new_llm_answers':0,'new_cost_usd':0,
        'new_q9_fits':0,'sce_truth_read':False,'sce_roles_assigned':False,'run_configuration_changed':False,
        'annual_role_inventory':counts,'role_groups_descriptive_only':descriptive,
        'role_2022_to_2023_validation':role_validation,'external_attention':attention,
        'external_attention_joint_complete_n':len(joint),'attention_joint_counts':{'|'.join(map(str,key)):v for key,v in sorted(joint_counts.items())},
        'source_sha256':{**sources,str(ARCHIVE.relative_to(ROOT)):sha(ARCHIVE),str(PLAN.relative_to(ROOT)):sha(PLAN)},
        'limits':['Source-only development, not improvement in SCE simulation MAE or causal role effects.',
            '2016 three-category and 2022/23 five-category shopping questions are not pooled or equated.',
            'ATUS current age/sex and household/labor fields used where available; CPS income/education/region observed two-five months earlier.',
            'CPS family income and ATUS household size are not automatically SCE household/family equivalents.',
            'Only EH final weights used; no replicate-weight uncertainty or population-level significance is claimed.',
            'External news data are unweighted 2021 self-reports, not counts or annual distributions.',
            'Economic coursework is not observed compatibly in SCE; diagnostic cannot be deployed by assuming it from education.',
            'Browser downloaded current files; original historical release vintages not established, strict B inclusion not approved.'],
        'seconds':perf_counter()-begin}
    out.mkdir(parents=True)
    for year,d in frames.items():
        d[['TUCASEID','TULINENO','EUFINLWGT','EUGROSHP' if year==2016 else 'EUGROSHP2',
           'age_group','education_group','income_group','region','labor_group','household_size_group','children_group','sex_cps']].to_parquet(out/f'role_donors_{year}_private.parquet',index=False)
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return result
