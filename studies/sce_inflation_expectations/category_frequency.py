"""Category purchase-day proxies from existing CE Diary; no network or LLM."""
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np

from .diary_experience import (CATEGORY_NAMES, DAY_FIELD, DAY_FLAG_FIELD, VALID_DAY_FLAGS,
    _hash_key, _int_code, _normal_row, _number, canonical_hash, file_sha256,
    read_official_diary_zip)

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'data/interim/ce_experience/20261006T071002778274Z_ce_diary2020q4_4862a21e'


def category_days(rows, mapping, known):
    days={name:set() for name in CATEGORY_NAMES}
    counts={name:Counter() for name in CATEGORY_NAMES}
    for raw in rows:
        row=_normal_row(raw)
        ucc=str(row.get('UCC') or '').strip().zfill(6)
        category=mapping.get(ucc,'other_known_ucc' if ucc in known else 'unknown_ucc')
        flag=str(row.get('PUB_FLAG') or '').strip()
        if flag!='2':
            counts[category]['excluded_pub_flag_1' if flag=='1' else 'unknown_publication_flag']+=1
            continue
        try: cost=_number(row.get('COST'),'COST')
        except ValueError:
            counts[category]['invalid_published_cost']+=1
            continue
        if cost<=0:
            counts[category]['nonpositive_published_cost']+=1
            continue
        counts[category]['positive_published_rows']+=1
        try:
            if str(row.get(DAY_FLAG_FIELD) or '').strip() not in VALID_DAY_FLAGS:
                raise ValueError('invalid day flag')
            day=_int_code(row.get(DAY_FIELD),DAY_FIELD)
            if not 1<=day<=7:raise ValueError('invalid day')
        except ValueError:
            counts[category]['missing_valid_day']+=1
        else:days[category].add(day)
    result={}
    for category in CATEGORY_NAMES:
        c=counts[category]
        uncertain=c['missing_valid_day']+c['invalid_published_cost']+c['unknown_publication_flag']
        if not rows:
            status='no_expd_rows';number=None
        elif uncertain:
            status='partial_support';number=None
        elif c['positive_published_rows']==0:
            status='no_positive_published_records';number=0
        else:
            status='available';number=len(days[category])
        result[category]={'status':status,'recorded_days_7d':number,
                          'observed_valid_days_lower_bound':len(days[category]),
                          'valid_day_codes':sorted(days[category]),'record_counts':dict(c)}
    return result


def prepare(out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('fresh ignored output directory required')
    manifest=json.loads((SOURCE/'manifest.json').read_text())
    archive=Path(manifest['source']['archive_path'])
    if file_sha256(archive)!=manifest['source']['archive_sha256']:
        raise ValueError('Diary archive drift')
    if file_sha256(manifest['dictionary']['path'])!=manifest['dictionary']['sha256']:
        raise ValueError('Dictionary drift')
    oldpath=SOURCE/'diary_weekly.jsonl'
    if file_sha256(oldpath)!=manifest['files']['diary_weekly.jsonl']['sha256']:
        raise ValueError('old weekly output drift')
    old={row['diary_week_key_sha256']:row for row in map(json.loads,oldpath.read_text().splitlines())}
    fmld,expd,members,_=read_official_diary_zip(archive)
    for key,value in members.items():
        if value['sha256']!=manifest['source']['members'][key]['sha256']:
            raise ValueError('Diary member drift')
    known=set().union(*[set(v) for v in manifest['category_mapping_by_quarter']['4']['category_ucc_codes'].values()])
    # Known UCCs outside mapped roots must remain other_known, not unknown.
    from .diary_experience import category_map_from_dictionary
    mapping,known,_=category_map_from_dictionary(manifest['dictionary']['path'],year=2020,quarter=4)
    grouped=defaultdict(list)
    for raw in expd[4]:
        row=_normal_row(raw);grouped[str(row['NEWID']).strip()].append(row)
    rows=[]
    for raw in fmld[4]:
        row=_normal_row(raw);newid=str(row['NEWID']).strip()
        key=_hash_key('week|Q4',newid);previous=old[key];details=grouped[newid]
        if canonical_hash([canonical_hash(r) for r in details])!=previous['source']['expd_detail_rows_sha256']:
            raise ValueError('CU-week source hash mismatch')
        categories=category_days(details,mapping,known)
        union=set().union(*(set(c['valid_day_codes']) for c in categories.values()))
        if union!=set(previous['purchase_day_support']['valid_day_codes_1_to_7']):
            raise ValueError('category union does not reproduce old overall days')
        rows.append({'diary_week_key_sha256':key,'diary_cu_pair_key_sha256':previous['diary_cu_pair_key_sha256'],
                     'diary_week_number':previous['diary_week_number'],'sampling_weight_FINLWT21':previous['sampling_weight_FINLWT21'],
                     'consumer_unit_demographics_raw':previous['consumer_unit_demographics_raw'],
                     'overall_status':previous['purchase_day_support']['status'],'categories':categories,
                     'source_detail_hash':previous['source']['expd_detail_rows_sha256']})
    if len(rows)!=len(old):raise ValueError('weekly coverage mismatch')
    summary={}
    for category in CATEGORY_NAMES:
        supported=[r for r in rows if r['categories'][category]['recorded_days_7d'] is not None]
        w=np.array([float(r['sampling_weight_FINLWT21']) for r in supported])
        values=np.array([r['categories'][category]['recorded_days_7d'] for r in supported])
        summary[category]={'status_counts':dict(Counter(r['categories'][category]['status'] for r in rows)),
                           'supported_weighted_mean_days_7d':float(np.average(values,weights=w)),
                           'supported_unweighted_day_counts':dict(Counter(map(int,values)))}
    result={'status':'offline_category_day_proxy_not_integrated','new_api_calls':0,'household_week_rows':len(rows),
            'consumer_unit_pairs':len({r['diary_cu_pair_key_sha256'] for r in rows}),'categories':summary,
            'source_manifest_sha256':file_sha256(SOURCE/'manifest.json'),'source_archive_sha256':file_sha256(archive),
            'all_category_unions_match_old_overall':True,
            'limitations':['Distinct days, not trips, quantities, person-specific attention or annual habits.',
                          'PUB_FLAG=2 positive costs only; zero published days does not prove no true purchases.',
                          '2020Q4 corrected current file is retrospective A proxy, not automatically available to B at earlier dates.',
                          'Diary reference-person demographics do not identify household shopping responsibility or SCE respondents.',
                          'Two weeks of the same consumer unit are related; per-week survey weights are preserved; no independent-person interpretation.',
                          'Assignment, price-category alignment and prompt integration are still pending.']}
    out.mkdir(parents=True)
    (out/'category_days_private.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows))
    result['private_output_sha256']=file_sha256(out/'category_days_private.jsonl')
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result
