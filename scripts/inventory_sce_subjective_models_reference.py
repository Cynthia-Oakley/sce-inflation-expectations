#!/usr/bin/env python3
"""Inspect public replication data locally; save aggregate inventory only."""
import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT/'data/raw/behavior_references/2026-10-18_subjective_models_v1/SubMod_Replication_220111.zip'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); out = args.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output directory required')
    blob = ARCHIVE.read_bytes()
    assert hashlib.md5(blob).hexdigest() == '1538f753c65672ce884c52d3b99f0eba'
    with ZipFile(BytesIO(blob)) as archive:
        readme = archive.read('README.md').decode()
        assert 'Attribution–NonCommercial' in readme and 'CC BY-NC 4.0' in readme
        frame = pd.read_stata(BytesIO(archive.read('out/data/associations.dta')), convert_categoricals=False)
        household = frame.loc[frame.survey.eq('household')].copy()
        assert household.ResponseId.is_unique
        assert len(household) == 2126
        valid = household.follow_news.dropna()
        assert set(valid.unique()).issubset(set(range(1, 7)))
        questions = []
        for name in archive.namelist():
            if '__MACOSX' in name or not name.endswith('.qsf'):
                continue
            data = json.loads(archive.read(name))
            for element in data.get('SurveyElements', []):
                payload = element.get('Payload', {})
                if isinstance(payload, dict) and payload.get('DataExportTag') == 'follow_news':
                    questions.append({'source': name, 'question_html': payload['QuestionText'],
                                      'choices': payload.get('Choices'), 'recode': payload.get('RecodeValues')})
        codebook = pd.read_csv(BytesIO(archive.read('codebook/associations.csv')))
        codebook_map = dict(zip(codebook.iloc[:, 0].astype(str), codebook.iloc[:, 1].astype(str)))
        key_columns = ['age', 'region', 'income', 'education', 'college', 'follow_news',
                       'econ_college', 'politics', 'rat_att_model', 'num_std',
                       'sources_1', 'sources_2', 'sources_3', 'sources_4', 'sources_5', 'sources_6']
        channels = []
        for shock in ('oil', 'int', 'gov', 'tax'):
            cols = ['super_narra_'+shock+'_costs', 'super_narra_'+shock+'_demand']
            group = household.loc[household.type.eq(shock)]
            observed = group.loc[group[cols].notna().all(axis=1)]
            assert observed[cols].isin([0., 1.]).all().all()
            channels.append({'shock': shock, 'n_households': len(group), 'n_joint_observed': len(observed),
                             'cost_selected_share': float(observed[cols[0]].mean()),
                             'demand_selected_share': float(observed[cols[1]].mean()),
                             'joint_counts_cost_demand': {f'{int(i)}_{int(j)}': int(n)
                                 for (i,j), n in observed.groupby(cols).size().items()},
                             'definition': {c:codebook_map.get(c) for c in cols}})
        groups = {}
        household['age_group'] = np.where(household.age < 40, 'under_40', np.where(household.age < 60, '40_to_59', '60_plus'))
        household['income_group'] = np.where(household.income < 50000, 'under_50k', np.where(household.income <= 100000, '50k_to_100k', 'over_100k'))
        household.loc[household.income.isna(), 'income_group'] = 'missing'
        for field in ('age_group', 'college', 'income_group', 'region'):
            groups[field] = {}
            for key, group in household.groupby(field, dropna=False):
                good = group.follow_news.dropna()
                groups[field][str(key)] = {'n': len(group), 'follow_news_observed_n': len(good),
                    'follow_news_mean_ordinal_not_cardinal': float(good.mean()) if len(good) else None,
                    'follow_news_1_to_6_counts': {str(int(k)): int(v) for k,v in good.value_counts().sort_index().items()}}
        result = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'new_api_calls': 0,
            'source_url': 'https://zenodo.org/records/5838445', 'version': '1.0.1',
            'archive_relative_path': str(ARCHIVE.relative_to(ROOT)),
            'archive_sha256': hashlib.sha256(blob).hexdigest(),
            'archive_md5': hashlib.md5(blob).hexdigest(), 'bytes': len(blob),
            'data_file': 'out/data/associations.dta', 'total_households_and_experts': len(frame),
            'household_rows': len(household), 'expert_rows_excluded': int(frame.survey.eq('expert').sum()),
            'household_follow_news_observed': len(valid),
            'household_follow_news_missing': int(household.follow_news.isna().sum()),
            'follow_news_1_to_6_counts_unweighted': {str(int(k)):int(v) for k,v in valid.value_counts().sort_index().items()},
            'question_sources': questions,
            'fields': {c:{'in_file':c in household, 'observed_households':int(household[c].notna().sum()) if c in household else 0,
                         'description':codebook_map.get(c)} for c in key_columns},
            'channels_by_shock': channels, 'demographic_attention_inventory_unweighted': groups,
            'license': {'zenodo_metadata': 'CC-BY-4.0', 'bundled_README': 'CC-BY-NC-4.0',
                        'handling': 'Record discrepancy; use the more restrictive bundled noncommercial attribution terms for local academic research. No raw redistribution or LLM upload.'},
            'interpretation': ['Wave 3 household sample (February 2021), not SCE identities or annual US attention series.',
                'Follow-news is a six-level agreement statement, not article counts, credibility, or observed clicks.',
                'Cost/demand indicators may both equal one: not mutually exclusive economic schools.',
                'Matching demographics can transfer external conditional distributions, not recover an SCE person’s actual cognition.',
                'Economic knowledge and survey numeracy instruments are not automatically interchangeable with SCE quizzes.',
                'No year-ahead SCE answers, synthetic personality allocation, or new simulation is produced.',
                'Income uses original authors’ bracket midpoints; reference group summaries here are unweighted and descriptive.'],
            'nonexecuted_upstream_code': True}
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({'out':str(out), 'households':len(household), 'news_observed':len(valid),
                      'channels':channels, 'license':result['license']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
