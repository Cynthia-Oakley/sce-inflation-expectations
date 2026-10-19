"""ATUS/SCE bridge and local information menus, without target answers or APIs.

This is an A-line preparation prototype, not an executable simulation provider.
Whole-household and family-only counts deliberately have separate contracts.
"""
from collections import Counter, defaultdict
from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
from time import perf_counter
from zipfile import ZipFile

from xml.etree import ElementTree as etree
import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from .evaluation.attention_support import ARCHIVE, FEATURES, ROOT, fit_probabilities, harmonize, sha
from .evaluation.atus_roles import weighted_scores
from .evaluation.heterogeneous_news import allocate, stable_uniform
from .news_exposure_demo import draw_news, exact_deduplicate, news_tags
from .news_exposure import NEWS_KEYS, check_news

TRIAL = ROOT/'outputs/sce_information_exposure_trial_20261018_v1'
DONORS = ROOT/'outputs/sce_atus_roles_attention_support_20261019_v1'
SOURCES = [ROOT/'data/raw/sce_p_sources/micro_2017_2019.xlsx',
    ROOT/'data/raw/sce_audit_20260928/micro_2020_2024.xlsx',
    ROOT/'data/raw/sce_baselines_latest_20261007/micro_latest.xlsx']
PLAN = ROOT/'docs/workstreams/20261018_targeted_mechanisms/atus_sce_matching_plan_20261019.md'
FIELDS = {'userid','date','Q32','D1','D3'} | {
    f'{p}_{i}' for p in ('Q45new','D2new') for i in range(1,10)}
ROLE_FEATURES = ['age_group','household_size_group','children_group']
SEEDS = (20261019, 20261020, 20261021)


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def code(value, low, high):
    try:
        value = float(value)
        return int(value) if np.isfinite(value) and value.is_integer() and low <= value <= high else None
    except (ValueError, TypeError):
        return None


def read_profile_rows(path, ids):
    """Physical projection excludes Q8/Q9, Q1/Q2 and actual response dates."""
    wb = load_workbook(path, read_only=True, data_only=True)
    headers = list(next(wb['Data'].iter_rows(min_row=2, max_row=2, values_only=True)))
    wb.close()
    cols = {get_column_letter(i+1): k for i,k in enumerate(headers) if k in FIELDS}
    id_column = get_column_letter(headers.index('userid')+1)
    with ZipFile(path) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            with archive.open('xl/sharedStrings.xml') as stream:
                for _,element in etree.iterparse(stream, events=('end',)):
                    if element.tag.endswith('}si'):
                        strings.append(''.join(element.itertext())); element.clear()
        with archive.open('xl/worksheets/sheet1.xml') as stream:
            for _,element in etree.iterparse(stream, events=('end',)):
                if not element.tag.endswith('}row'):
                    continue
                if int(element.get('r')) > 2:
                    cells = {c.get('r','').rstrip('0123456789'): c for c in element}
                    c = cells.get(id_column)
                    value = c.find('{*}v') if c is not None else None
                    if value is not None and code(value.text, 1, 10**12) in ids:
                        row = {}
                        for column,key in cols.items():
                            c = cells.get(column)
                            value = c.find('{*}v') if c is not None else None
                            if value is not None and value.text is not None:
                                row[key] = strings[int(value.text)] if c.get('t') == 's' else value.text
                        yield row
                element.clear()


def composition(row, prefix):
    counts = [code(row.get(f'{prefix}_{i}'),0,30) for i in range(1,9)]
    alone = code(row.get(f'{prefix}_9'),0,1)
    if any(v is None for v in counts) or alone is None or ((alone == 1) != (sum(counts) == 0)):
        return None
    children = counts[3]+counts[4]
    # Own children are not all possible household children; other members' ages are unknown.
    child_group = 'with_children' if children > 0 else (
        'missing' if counts[6]+counts[7] else 'no_children')
    return {'whole_residence_size':1+sum(counts),
        'family_size_excluding_nonrelatives':1+sum(counts[:7]),
        'known_own_children_under18':children, 'children_group':child_group,
        'nonrelatives':counts[7], 'other_relatives':counts[6]}


def past_state(history, target):
    """Use strictly earlier waves only; invalid updates never resurrect old state."""
    state, source_month, source_field = None, None, None
    invalidations, confirmations = [], []
    entry_age = None
    for month,row in sorted(history):
        if month >= target:
            continue
        age = code(row.get('Q32'),18,110)
        if age is not None:
            entry_age = {'value':age,'month':month}
        entry, update = composition(row,'Q45new'), composition(row,'D2new')
        if entry is not None:
            state, source_month, source_field = entry, month, 'Q45new'
        if code(row.get('D1'),1,2) == 2:
            state, source_month, source_field = update, month, 'D2new'
            if update is None:
                invalidations.append('reported_change_without_complete_D2')
        elif update is not None:
            # A complete directly observed roster is usable, even if D1 was omitted.
            state, source_month, source_field = update, month, 'D2new'
        elif code(row.get('D3'),1,2) == 1:
            state, source_month, source_field = None, month, 'moved_without_roster'
            invalidations.append('moved_without_complete_roster')
        if code(row.get('D1'),1,2) == 1:
            confirmations.append(month)
    if state is None:
        return {'available':False, 'source_month':source_month,'source_field':source_field,
            'entry_age':entry_age, 'invalidations':invalidations}
    lag = (target//100-source_month//100)*12+target%100-source_month%100
    return {'available':True, **state, 'source_month':source_month,'source_field':source_field,
        'record_age_months':lag, 'entry_age':entry_age,'invalidations':invalidations,
        'last_family_only_confirmation':max(confirmations) if confirmations else None,
        'nonrelative_count_currently_confirmed':False,
        'state_status':'last_observed_carried_forward_not_current_roster'}


def conditional_roles(train, targets, role, k, columns=ROLE_FEATURES, alpha=20):
    """Marginalize missing target dimensions, then shrink using actual cell n."""
    y,w = train[role].to_numpy(int)-1, train.EUFINLWGT.to_numpy(float)
    if np.any((y < 0)|(y >= k)) or not np.isfinite(w).all() or np.any(w <= 0):
        raise ValueError('Valid role classes and positive EH weights required')
    base = np.bincount(y,weights=w,minlength=k)/w.sum()
    ps, supports = [], []
    for row in targets.to_dict('records'):
        active = [c for c in columns if row.get(c) not in (None,'missing') and not pd.isna(row.get(c))]
        mask = np.ones(len(train),dtype=bool)
        for c in active:
            mask &= train[c].eq(row[c]).to_numpy()
        n = int(mask.sum()); weight = w[mask]
        cell = np.bincount(y[mask],weights=weight,minlength=k)/weight.sum() if n else base
        ps.append(n/(n+alpha)*cell+alpha/(n+alpha)*base)
        supports.append({'n':n,'effective_n':float(weight.sum()**2/np.square(weight).sum()) if n else 0.,
            'observed_dimensions':active,'pooled_population_fallback':n == 0})
    return np.asarray(ps), supports


def draw_role(probability, person, seed):
    return min(int(np.searchsorted(np.cumsum(probability),stable_uniform(seed,person,'shopping_role'),side='right'))+1,len(probability))


def balanced_permutation(values, weights, rng, tolerance=.01, max_draws=4096):
    values,weights = np.asarray(values),np.asarray(weights,float)
    reference = float(np.average(values,weights=weights))
    for attempt in range(1,max_draws+1):
        perm = rng.permutation(len(values)); candidate = values[perm]
        difference = abs(float(np.average(candidate,weights=weights))-reference)/max(abs(reference),1e-12)
        if difference <= tolerance and not np.array_equal(candidate,values):
            return perm, {'attempts':attempt,'relative_weighted_quantity_difference':difference}
    raise ValueError('No quantity-balanced shuffle within declared candidates')


def food_detail_count(role):
    # Trial operationalization, not estimated article/price knowledge in ATUS.
    return {1:0,2:1,3:1,4:2,5:2}[int(role)]


def analyze(out):
    began = perf_counter(); out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output directory required')
    source_hashes = {str(p.relative_to(ROOT)):sha(p) for p in [PLAN,*SOURCES,Path(__file__).resolve()]}
    manifest = json.loads((TRIAL/'manifest.json').read_text())
    source_hashes[str((TRIAL/'manifest.json').relative_to(ROOT))] = sha(TRIAL/'manifest.json')
    def frozen(name):
        path = TRIAL/name
        if sha(path) != manifest['prepared_file_sha256'][name]:
            raise ValueError('Frozen input changed: '+name)
        source_hashes[str(path.relative_to(ROOT))] = sha(path)
        return json.loads(path.read_text())
    protocol,links = frozen('protocol.json'),frozen('evaluation_links_private.json')
    allowed = {'month','agent_id','userid','profile','stratum','survey_weight','inclusion_probability','design_survey_weight'}
    if any(set(r)-allowed for r in links):
        raise ValueError('Unexpected current-answer field in identity links')
    ids = {int(r['userid']) for r in links}; history = defaultdict(dict)
    cache = ROOT/'outputs/sce_atus_sce_profile_cache_20261019_v1'
    cache_contract = {'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in SOURCES},
        'fields':sorted(FIELDS),'selected_ids_sha256':__import__('hashlib').sha256(str(sorted(ids)).encode()).hexdigest()}
    if cache.exists():
        receipt = json.loads((cache/'receipt.json').read_text())
        if receipt['contract'] != cache_contract or sha(cache/'profiles_private.json') != receipt['data_sha256']:
            raise ValueError('Profile projection cache changed or different scope')
        projected = json.loads((cache/'profiles_private.json').read_text())
    else:
        projected = [row for path in SOURCES for row in read_profile_rows(path,ids)]
        cache.mkdir(parents=True)
        dump(cache/'profiles_private.json',projected)
        dump(cache/'receipt.json',{'contract':cache_contract,'data_sha256':sha(cache/'profiles_private.json')})
    source_hashes[str((cache/'receipt.json').relative_to(ROOT))] = sha(cache/'receipt.json')
    for row in projected:
        uid,month = int(row['userid']),int(row['date'])
        if month in history[uid] and history[uid][month] != row:
            raise ValueError('Conflicting overlapping source profile rows')
        history[uid][month] = row
    rows = []
    for link in links:
        month,uid = int(link['month']),int(link['userid'])
        state = past_state(list(history[uid].items()),month)
        profile = link['profile']
        size = state.get('whole_residence_size')
        features = {'age_group':{'Under 40':'under_40','40 to 60':'40_to_60','Over 60':'over_60'}.get(profile.get('age_group'),'missing'),
            'household_size_group':'missing' if size is None else ('one' if size==1 else 'two' if size==2 else 'three_plus'),
            'children_group':state.get('children_group','missing'),
            'education_group':profile.get('education_group') or 'missing',
            # Income not deployed: SCE >100k and CPS >=100k boundaries differ.
            'region':profile.get('region') or 'missing'}
        rows.append({'month':month,'userid':uid,'agent_id':link['agent_id'],
            'design_weight':link['design_survey_weight'],'profile':profile,'state':state,'features':features})
    targets = pd.DataFrame([r['features'] for r in rows])
    donor = {}
    source_hashes[str((DONORS/'verification_receipt.json').relative_to(ROOT))] = sha(DONORS/'verification_receipt.json')
    for year in (2016,2022,2023):
        path = DONORS/f'role_donors_{year}_private.parquet'
        source_hashes[str(path.relative_to(ROOT))] = sha(path)
        donor[year] = pd.read_parquet(path)
    p,support = conditional_roles(donor[2022],targets,'EUGROSHP2',5)
    p16,support16 = conditional_roles(donor[2016],targets,'EUGROSHP',3)
    for i,row in enumerate(rows):
        row['role_probabilities_2022_A_only'] = p[i].tolist()
        row['role_support'] = support[i]
        row['role_probabilities_2016_separate_three_category_sensitivity'] = p16[i].tolist()
    # Fixed external year check; additional features are exploratory, not a fresh holdout.
    role_validation = {}
    for name,columns in {'age_family':ROLE_FEATURES,'plus_income':ROLE_FEATURES+['income_group'],
            'plus_income_education_region':ROLE_FEATURES+['income_group','education_group','region']}.items():
        q,s = conditional_roles(donor[2022],donor[2023],'EUGROSHP2',5,columns)
        role_validation[name] = {'scores':weighted_scores(donor[2023].EUGROSHP2.to_numpy(int)-1,q,donor[2023].EUFINLWGT),
            'weighted_fraction_cell_n_below_10':float(np.average([z['n']<10 for z in s],weights=donor[2023].EUFINLWGT))}
    with ZipFile(ARCHIVE) as archive:
        external = pd.read_stata(BytesIO(archive.read('out/data/associations.dta')),convert_categoricals=False)
    source_hashes[str(ARCHIVE.relative_to(ROOT))] = sha(ARCHIVE)
    attention = harmonize(external.loc[external.survey.eq('household') & external.follow_news.notna()].copy())
    profiles = pd.DataFrame([{k:r['profile'].get(k) or 'missing' for k in FEATURES} for r in rows])
    attention_p = fit_probabilities(attention,profiles,attention.follow_news.to_numpy(int)-1,6,FEATURES)
    out.mkdir(parents=True)
    allocations,quantity_checks = {},[]
    for seed in SEEDS:
        seed_rows = []
        for month in protocol['months']:
            ix = [i for i,r in enumerate(rows) if r['month']==month]
            wave = [rows[i] for i in ix]; people = [str(r['userid']) for r in wave]
            counts = allocate(people,attention_p[ix],seed)
            roles = [draw_role(p[i],str(rows[i]['userid']),seed) for i in ix]
            news = np.array([counts[uid] for uid in people]); detail = np.array([food_detail_count(r) for r in roles])
            w = np.array([r['design_weight'] for r in wave])
            rng = np.random.default_rng(seed+month)
            pn,cn = balanced_permutation(news,w,rng)
            pr,cr = balanced_permutation(detail,w,rng)
            quantity_checks.append({'seed':seed,'month':month,'news':cn,'food_details':cr,
                'weighted_news_matched':float(np.average(news,weights=w)),
                'weighted_news_shuffled':float(np.average(news[pn],weights=w)),
                'unweighted_mean_news':float(news.mean())})
            for j,r in enumerate(wave):
                seed_rows.append({'month':month,'agent_id':r['agent_id'],'userid':r['userid'],
                    'news_matched':int(news[j]),'news_shuffled':int(news[pn[j]]),
                    'role_matched':int(roles[j]),'role_shuffled':int(roles[pr[j]]),
                    'food_details_matched':int(detail[j]),'food_details_shuffled':int(detail[pr[j]])})
        allocations[str(seed)] = seed_rows
    dump(out/'historical_profiles_and_role_probabilities_private.json',rows)
    dump(out/'allocations_private.json',allocations)
    summary = {'status':'A_line_matching_prototype_no_simulation','new_api_calls':0,'new_cost_usd':0,
        'current_inflation_answers_read':False,'formal_configuration_changed':False,
        'n_person_months':len(rows),'n_unique_people':len(ids),'months':protocol['months'],
        'matching_features':ROLE_FEATURES,'role_source':2022,'alpha_fixed':20,'allocation_seeds':list(SEEDS),
        'source_sha256':source_hashes,'quantity_balance_checks':quantity_checks,
        'role_feature_diagnostic_2022_to_2023':role_validation,
        'whole_residence_coverage':{},'support':{
            'n_below_10':sum(s['n']<10 for s in support),'zero_donor_cells':sum(s['n']==0 for s in support),
            'minimum_donor_n':min(s['n'] for s in support),'median_donor_n':float(np.median([s['n'] for s in support])),
            'minimum_donor_effective_n':min(s['effective_n'] for s in support)},
        'limits':['Synthetic role transport, not identified actual SCE shopping roles or proven causal effects.',
            'SCE financial decision makers and ATUS adults have different selection; transfer conditional independence is unverified.',
            'Source 2022 for pre-2022 targets is explicit retrospective A assumption, not strict B input.',
            'Three news amounts and 0/1/2 food details are experimental levels, not estimated real counts.',
            'SCE roster is last observed, not known current: D1 same excludes nonrelatives.',
            'External shopping and news-attention records are not observed jointly; no empirical joint dependence is claimed.']}
    for m in ['all',*map(str,protocol['months'])]:
        selected = rows if m=='all' else [r for r in rows if str(r['month'])==m]
        available = [r['state'] for r in selected if r['state']['available']]
        ages = [s['record_age_months'] for s in available]
        summary['whole_residence_coverage'][m] = {'n':len(selected),'observed_past_composition':len(available),
            'record_age_months_min_median_max':[min(ages),float(np.median(ages)),max(ages)] if ages else None,
            'nonrelatives_recorded':sum(s['nonrelatives']>0 for s in available),
            'child_presence_unknown':sum(s['children_group']=='missing' for s in available),
            'missing_composition':sum(not r['state']['available'] for r in selected),
            'invalidations':dict(Counter(reason for r in selected for reason in r['state']['invalidations']))}
    summary['seconds'] = perf_counter()-began
    dump(out/'summary.json',summary)
    return summary
