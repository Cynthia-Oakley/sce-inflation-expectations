"""Offline evaluation of archived messages and curves. No new simulation."""
from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .household_state_analysis import density
from .model import parse_sce_response, validate_sce_bins
from .scoring.sce_q9_frozen import provenance

OLD = 'outputs/local_runs/sce-local-openai-20261003T055121Z-1dc7cd15'
NEW = ['outputs/local_runs/sce-local-openai-20261005T092656Z-202105-8d2e3b2c',
       'outputs/local_runs/sce-local-openai-20261005T092656Z-202106-e4f49f76']
MEMORY = re.compile(r'Last month you gave a point estimate of\s+([-+]?\d+(?:\.\d+)?)%', re.I)


def lines(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prev_month(month):
    p = pd.Period(str(month), freq='M') - 1
    return int(p.strftime('%Y%m'))


def remembered_point(text):
    m = MEMORY.search(text)
    return float(m[1]) if m else None


def probability_diagnostic(bins):
    """Midpoints are sensitivity diagnostics; open-tail locations are assumed."""
    bins = np.asarray(bins, float)
    if bins.shape != (10,) or not np.isfinite(bins).all() or (bins < 0).any() or not np.isclose(bins.sum(), 100):
        return None
    means = [float(bins @ np.array([tail, 10, 6, 3, 1, -1, -3, -6, -10, -tail]) / 100)
             for tail in [12, 16, 20]]
    return {'deflation_mass_pct': float(bins[5:].sum()),
            'positive_bin_count': int((bins > 0).sum()),
            'inflation_above4_mass_pct': float(bins[:3].sum()),
            'midpoint_mean_tail16_pp': means[1], 'symmetric_tail12_20_mean_range_pp': [min(means), max(means)]}


@lru_cache(maxsize=None)
def fitted(bins):
    return density(list(bins))


def finite_median(values):
    a = np.asarray(values, float)
    a = a[np.isfinite(a)]
    return float(np.median(a)) if len(a) else None


def dist(values):
    a = np.asarray(values, float)
    a = a[np.isfinite(a)]
    return {'n': len(a), 'median': float(np.median(a)),
            'iqr': float(np.quantile(a, .75) - np.quantile(a, .25))} if len(a) else {'n': 0, 'median': None, 'iqr': None}


def answer_row(answer):
    bins = answer['bins']
    good, err, _ = validate_sce_bins(bins)
    if not good or not np.isfinite(answer['point_pct']):
        raise ValueError(err)
    d = fitted(tuple(bins))
    return {'point': answer['point_pct'], 'density': d['mean'], 'own_uncertainty': d['iqr'],
            'fit_status': d['status'], **probability_diagnostic(bins)}


def monthly_groups(rows):
    out = {}
    for month in sorted({r['month'] for r in rows}):
        selected = [r for r in rows if r['month'] == month]
        groups = {}
        for key in ['point', 'density']:
            valid = [r for r in selected if r[key] is not None and r['real_' + key] is not None
                     and np.isfinite(r[key]) and np.isfinite(r['real_' + key])]
            groups[key] = {'simulated': dist([r[key] for r in valid]),
                           'matched_real': dist([r['real_' + key] for r in valid])}
        out[str(month)] = {'n_selected': len(selected), **groups,
                          'raw_deflation_mass_median_pct': finite_median([r['deflation_mass_pct'] for r in selected]),
                          'raw_real_deflation_mass_median_pct': finite_median([r.get('real_deflation_mass_pct') for r in selected]),
                          'raw_positive_bin_count_median': finite_median([r['positive_bin_count'] for r in selected]),
                          'real_positive_bin_count_median': finite_median([r.get('real_positive_bin_count') for r in selected]),
                          'midpoint_mean_median_pp': finite_median([r['midpoint_mean_tail16_pp'] for r in selected]),
                          'individual_point_minus_density_median_pp': finite_median([r['point'] - r['density'] for r in selected if r['density'] is not None]),
                          'real_individual_point_minus_density_median_pp': finite_median([r['real_point'] - r['real_density'] for r in selected if r['real_density'] is not None and r['real_point'] is not None])}
    return out


def run(root, out):
    out.mkdir(parents=True, exist_ok=False)
    hashes = {}

    def tracked(relative):
        path = root / relative
        hashes[relative] = sha(path)
        return path

    assert provenance()['live_matches_pinned']
    calls = lines(tracked(OLD + '/llm_calls.jsonl'))
    obs = lines(tracked(OLD + '/observations.jsonl'))
    by_ob = {(int(x['observation']['macro_information']['target_month'].replace('-', '')), x['agent_id']): x['observation'] for x in obs}
    truth = json.loads(tracked('data/evaluation/sce_truth_main2021.json').read_text())
    truth_by = {(int(t['date']), int(t['userid'])): t for t in truth['per_person']}
    macro = json.loads(tracked('data/evaluation/sce_baselines_latest_20261007/aggregate_inputs.json').read_text())
    cpi = {int(x['reference_period'].replace('-', '')): x['value'] for x in macro['cpi_first_releases']}
    ref = lines(tracked('outputs/sce_qwen_reuse_prepared_20261008_v1/deepseek_reference_private.jsonl'))
    selected = {x['source_agent_id'] for x in ref}
    prepared = lines(tracked('outputs/sce_qwen_reuse_run_20261008_v1/requests_prepared.jsonl'))
    qwen_calls = lines(tracked('outputs/sce_qwen_reuse_run_20261008_v1/llm_calls.jsonl'))
    qwen_good = {x['case_id']: x for x in qwen_calls if x.get('answer')}
    ref_by = {x['case_id']: x for x in ref}
    old_rows, index, months, all_memory = [], {}, {}, []
    identities, profiles = {}, {}
    for call in calls:
        assert call.get('error') is None
        for text, h in [('prompt_text', 'prompt_sha256'), ('raw_response_text', 'raw_response_sha256')]:
            assert hashlib.sha256(call[text].encode()).hexdigest() == call[h]
        month = int(call['target_month'].replace('-', ''))
        aid = call['agent_id']
        assert (month, aid) not in index
        ob = by_ob[month, aid]
        text = json.loads(call['prompt_text'])[0]['content']
        answer, error = parse_sce_response(call['raw_response_text'])
        assert error is None
        t = truth_by[month, int(aid.removeprefix('sce_u'))]
        bins_real = tuple(t[f'Q9_bin{i}'] for i in range(1, 11))
        d = fitted(bins_real)
        r = {'month': month, 'agent_id': aid, **answer_row(answer),
             'real_point': t['Q8v2part2'], 'real_density': d['mean'],
             'real_deflation_mass_pct': probability_diagnostic(bins_real)['deflation_mass_pct'] if probability_diagnostic(bins_real) else None}
        r['real_positive_bin_count'] = probability_diagnostic(bins_real)['positive_bin_count'] if probability_diagnostic(bins_real) else None
        index[month, aid] = {'row': r, 'call': call, 'text': text}
        old_rows.append(r)
        note = remembered_point(text)
        if note is not None:
            old = index.get((prev_month(month), aid))
            assert old and np.isclose(note, old['row']['point'])
            all_memory.append((month, aid))
        p = {k: v for k, v in ob['local_physical']['profile'].items() if k != 'weight'}
        profiles.setdefault(aid, p)
        assert profiles[aid] == p, 'Old fixed-panel persona changed'
        mi = ob['macro_information']
        cutoff = datetime.fromisoformat(mi['as_of'])
        for signal in mi['signals']:
            assert datetime.fromisoformat(signal['published_at']) <= cutoff
            value = f"{signal['value']:g}"
            pct = '%' if signal['unit'] == 'percent' else ''
            assert f"{signal['measure']} for {signal['reference_period']}: {value}{pct}" in text
            if '12-month' in signal['measure']:
                assert np.isclose(signal['value'], cpi[int(signal['reference_period'].replace('-', ''))])
        if str(month) not in months:
            latest = mi['signals'][0]
            months[str(month)] = {'target_month': call['target_month'], 'as_of': mi['as_of'], 'signals': mi['signals'],
                'reference_period': latest['reference_period'], 'latest_known_cpi_yoy_pct': latest['value'],
                'contemporaneous_cpi_yoy_evaluation_only_pct': cpi[month],
                'actual_input_excerpt_without_persona': '[人口画像段另见汇总，不展示个体组合]\n\n' + text.split('\n\n', 1)[1],
                'reply_example': answer, 'example_density_mean_pp': r['density'],
                'example_probability_diagnostic': probability_diagnostic(answer['bins'])}
        identities.setdefault(str(month), Counter())['n_calls'] += 1
        reason = answer.get('reason', '').lower()
        for term, pattern in [('cpi', r'cpi'), ('pandemic', r'pandemic|covid'), ('temporary', r'transitor|temporar'), ('fed', r'\bfed\b|federal reserve')]:
            if re.search(pattern, reason):
                identities[str(month)][term + '_reason_mentions'] += 1
                if not re.search(pattern, text.lower()):
                    identities[str(month)][term + '_mentioned_not_in_input'] += 1
    qwen_rows, qwen_memory, different_qwen_memory = [], 0, 0
    qwen_index = {}
    for request in prepared:
        cid = request['case_id']
        x = ref_by[cid]
        month, aid = int(x['month']), x['source_agent_id']
        actual = index[month, aid]
        assert request['payload']['messages'] == json.loads(actual['call']['prompt_text'])
        c = qwen_good[cid]
        r = {'month': month, 'agent_id': aid, **answer_row(c['answer']),
             'real_point': actual['row']['real_point'], 'real_density': actual['row']['real_density'],
             'real_deflation_mass_pct': actual['row']['real_deflation_mass_pct']}
        r['real_positive_bin_count'] = actual['row']['real_positive_bin_count']
        qwen_rows.append(r)
        qwen_index[month, aid] = r
        note = remembered_point(actual['text'])
        if note is not None:
            qwen_memory += 1
            previous_qwen = qwen_index.get((prev_month(month), aid))
            assert previous_qwen is not None
            different_qwen_memory += int(not np.isclose(note, previous_qwen['point']))
    matched_deepseek = monthly_groups([r for r in old_rows if r['agent_id'] in selected])
    matched_qwen = monthly_groups(qwen_rows)
    sealed = json.loads(tracked('outputs/sce_qwen_reuse_comparison_20261008_v1/summary.json').read_text())
    for month in matched_deepseek:
        for key, old_key in [('point', 'Q8_secondary'), ('density', 'Q9')]:
            for name, target in [('deepseek', matched_deepseek), ('qwen', matched_qwen)]:
                assert np.isclose(target[month][key]['simulated']['median'], sealed['months'][month][old_key]['arms'][name]['distribution']['median'])
    # Retrospective counts of interviews before the common monthly cutoff.
    pframe = pd.read_parquet(tracked('data/cache/monthly_profiles_7f0ed622ae0915902741.parquet'))
    new_summaries = {}
    tnew = json.loads(tracked('data/evaluation/dev_full_20261005T045330Z_947a818f/truth.json').read_text())
    new_truth = {(int(x['date']), int(x['userid'])): x for x in tnew['per_person']}
    for folder in NEW:
        local_calls = lines(tracked(folder + '/llm_calls.jsonl'))
        local_obs = lines(tracked(folder + '/observations.jsonl'))
        m = int(local_calls[0]['target_month'].replace('-', ''))
        mi = local_obs[0]['observation']['macro_information']
        local_rows, notes = [], 0
        for call in local_calls:
            for text_field, h in [('prompt_text', 'prompt_sha256'), ('raw_response_text', 'raw_response_sha256')]:
                assert hashlib.sha256(call[text_field].encode()).hexdigest() == call[h]
            aid = call['agent_id']; t = new_truth[m, int(aid.removeprefix('sce_u'))]
            answer, error = parse_sce_response(call['raw_response_text']); assert error is None
            notes += int(remembered_point(call['prompt_text']) is not None)
            local_rows.append({'month': m, 'agent_id': aid, **answer_row(answer), 'real_point': t['Q8v2part2'],
                               'real_density': fitted(tuple(t[f'Q9_bin{i}'] for i in range(1, 11)))['mean']})
        cutoff = pd.Timestamp(mi['as_of']).date()
        g = pframe[pframe.date == m]
        dates = g.survey_date.dt.date
        early = dates.notna() & (dates < cutoff)
        same = dates.notna() & (dates == cutoff)
        latest = [s for s in mi['signals'] if s.get('role') == 'latest_release']
        text = json.loads(local_calls[0]['prompt_text'])[0]['content']
        assert all(json.loads(c['prompt_text'])[0]['content'].split('\n\n', 1)[1] == text.split('\n\n', 1)[1] for c in local_calls)
        assert 'jobs' in text and f"{int(next(s['value'] for s in latest if s['unit']=='thousands') * 1000):,}" in text
        new_summaries[str(m)] = {'source_run': folder, 'as_of': mi['as_of'], 'n_calls': len(local_calls),
            'memory_notes': notes, 'signal_count': len(mi['signals']), 'news_count': len(mi.get('events', [])),
            'latest_signals': latest, 'monthly': monthly_groups(local_rows)[str(m)],
            'interview_timing_full_real_frame': {'n': len(g), 'known_date_n': int(dates.notna().sum()),
                       'strictly_before_cutoff_date_n': int(early.sum()), 'same_date_n': int(same.sum()),
                       'unknown_date_n': int(dates.isna().sum()), 'before_share_known': float(early.sum()/dates.notna().sum())},
            'news_review_flagged_titles': [e['headline'] for e in mi.get('events', []) if 'Biographer' in e.get('headline', '')],
            'actual_input_excerpt_without_persona': '[人口画像段另见汇总，不展示个体组合]\n\n' + text.split('\n\n', 1)[1]}
        pop = json.loads(tracked(folder + '/population_effective.json').read_text())['personas']
        new_summaries[str(m)]['population_marginal_counts'] = {f: dict(Counter(p['attributes'].get(f, 'unknown') for p in pop))
            for f in ['age_group', 'education_group', 'household_income_band', 'region', 'numeracy', 'employment_status', 'housing_tenure']}
    fields = ['age_group', 'education_group', 'household_income_band', 'region', 'numeracy', 'employment_status', 'housing_tenure']
    populations = {name: {'n': len(ids), 'marginal_counts': {f: dict(Counter(profiles[i].get(f, 'unknown') for i in ids)) for f in fields}}
                   for name, ids in [('old73', profiles), ('selected20', selected)]}
    jan = pframe[(pframe.date == 202101) & np.isfinite(pframe.weight) & (pframe.weight > 0)]
    populations['full202101_weighted_reference'] = {'n': len(jan), 'shares': {
        'college': float(jan.loc[jan._EDU_CAT == 'College', 'weight'].sum()/jan.weight.sum()),
        'high_numeracy': float(jan.loc[jan._NUM_CAT == 'High', 'weight'].sum()/jan.weight.sum()),
        'over100k': float(jan.loc[jan._HH_INC_CAT == 'Over 100k', 'weight'].sum()/jan.weight.sum()),
        'over60': float(jan.loc[jan._AGE_CAT == 'Over 60', 'weight'].sum()/jan.weight.sum())}}
    result = {'audit_id': out.name, 'new_llm_calls': 0, 'new_mcp_calls': 0, 'changed_runtime_inputs': False,
              'memory_correction': {'old_requests': len(calls), 'old_actual_notes': len(all_memory),
                  'all_old_notes_match_actual_prior_deepseek': True, 'qwen_actual_deepseek_history_notes': qwen_memory,
                  'qwen_notes_different_from_own_previous_answer': different_qwen_memory,
                  'interpretation': 'Exact-input conditional model comparison, not independent Qwen autoregressive history',
                  'cause_of_old_audit_error': 'Checked previous/prior only; missed Last month'},
              'units': {'old_payroll_thousands_omitted_requests': len(calls), 'new_payroll_number_rendering_verified_requests': sum(x['n_calls'] for x in new_summaries.values()),
                        'old_percent_labels_and_source_values_checked': True, 'cpi_first_release_yoy_matches': True},
              'population_marginals': populations, 'old_month_inputs': months, 'old_reason_mentions': identities,
              'old73_monthly': monthly_groups(old_rows), 'selected20_deepseek': matched_deepseek, 'selected20_qwen': matched_qwen,
              'full_real_official_monthly': truth['monthly_full_sample'], 'new_v2_months': new_summaries,
              'sources_sha256': hashes, 'scorer': provenance(),
              'limits': ['No intervention identifies individual causes.', 'Reason text is reported explanation, not access to model attention.',
                         'Q8 need not equal Q9 mean.', 'Midpoint tails 12/16/20 are diagnostics, not official scoring.',
                         'Old and new P/E versions, populations and dates differ.', 'Exact E document arithmetic is distinct from household knowledge.']}
    for folder, rows in [('old73', old_rows), ('qwen20', qwen_rows)]:
        pd.DataFrame(rows).to_json(out / (folder + '_private.jsonl'), orient='records', lines=True)
    snapshot = out / 'source_snapshot'; snapshot.mkdir()
    for path in [Path(__file__), root/'scripts/audit_sce_pe_diagnostic.py']:
        (snapshot/path.name).write_bytes(path.read_bytes()); hashes[str(path.relative_to(root))] = sha(path)
    (out/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'memory': result['memory_correction'], 'units': result['units']}, ensure_ascii=False), flush=True)
    return result
