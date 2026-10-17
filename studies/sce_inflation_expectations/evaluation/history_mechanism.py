"""Evaluation-only diagnostics of observed personal histories and SCE outlooks.

No API or runtime provider imports. External psychological microdata are never
read: a donor's personality cannot be linked to an SCE respondent's outcome.
"""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pandas as pd
from scipy.linalg import lstsq

FIELDS = ('age_group', 'education_group', 'household_income_band', 'numeracy',
          'region', 'housing_tenure', 'employment_status')
ROOT = Path(__file__).resolve().parents[3]
EVALUATION = ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1'
PREPARED = ROOT/'outputs/sce_reference_validation_trial_20261017_v2'
TRAITS = ROOT/'outputs/sce_population_associations_20261015_v1/analysis_frame_private.parquet'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def previous(month):
    return month-1 if month % 100 > 1 else (month//100-1)*100+12


def clean_code(value, low, high):
    try:
        n = float(value)
        return int(n) if np.isfinite(n) and n == int(n) and low <= n <= high else None
    except (TypeError, ValueError):
        return None


def read_q2_rows(path):
    """Project three XLSX columns using the stdlib; no optional XML dependency."""
    with zipfile.ZipFile(path) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            with archive.open('xl/sharedStrings.xml') as stream:
                for _, element in ET.iterparse(stream, events=('end',)):
                    if element.tag.endswith('}si'):
                        strings.append(''.join(element.itertext()))
                        element.clear()
        columns = {}
        with archive.open('xl/worksheets/sheet1.xml') as stream:
            parent = None
            for event, element in ET.iterparse(stream, events=('start', 'end')):
                if event == 'start' and element.tag.endswith('}sheetData'):
                    parent = element
                if event != 'end' or not element.tag.endswith('}row'):
                    continue
                number = int(element.get('r'))
                if number >= 2:
                    values = {}
                    for cell in element:
                        letter = cell.get('r', '').rstrip('0123456789')
                        if number != 2 and letter not in columns:
                            continue
                        value = cell.find('{*}v')
                        if value is not None and value.text is not None:
                            val = strings[int(value.text)] if cell.get('t') == 's' else value.text
                        else:
                            inline = cell.find('{*}is')
                            val = ''.join(inline.itertext()) if inline is not None else None
                        if number == 2 and val in ('date', 'userid', 'Q2'):
                            columns[letter] = val
                        elif number > 2:
                            values[columns[letter]] = val
                    if number == 2:
                        assert set(columns.values()) == {'date', 'userid', 'Q2'}
                    elif values.get('date') is not None and values.get('userid') is not None:
                        yield values
                element.clear()
                if parent is not None:
                    parent.clear()


def fit(x, y, w, names):
    b, _, rank, _ = lstsq(x*np.sqrt(w)[:, None], y*np.sqrt(w), lapack_driver='gelsy')
    e = y-x@b
    sse = float(np.sum(w*e*e))
    tss = float(np.sum(w*(y-np.average(y, weights=w))**2))
    return {'n': len(y), 'rank': int(rank), 'columns': x.shape[1], 'r2': 1-sse/tss,
            'rmse_pp': float(np.sqrt(sse/w.sum())),
            'coefficients': {n: float(v) for n, v in zip(names, b) if not n.startswith('month=')}}, e


def design(rows, numeric=(), categories=(), month=True):
    columns, names = [], []
    if month:
        for m in sorted({r['month'] for r in rows}):
            columns.append(np.array([r['month'] == m for r in rows], dtype=float))
            names.append(f'month={m}')
    else:
        columns.append(np.ones(len(rows))); names.append('constant')
    for key in numeric:
        columns.append(np.array([r[key] for r in rows], dtype=float)); names.append(key)
    for key in categories:
        values = [str(r.get(key, 'missing')) if r.get(key) is not None else 'missing' for r in rows]
        levels = sorted(set(values))
        # Neutral3/4 are reference categories for five-/seven-point questions.
        reference = '3' if key.startswith(('outlook', 'financial_change')) else '4' if 'risk' in key else levels[0]
        if reference not in levels:
            reference = levels[0]
        for level in levels:
            if level != reference:
                columns.append(np.array([v == level for v in values], dtype=float))
                names.append(f'{key}={level} vs {reference}')
    return np.column_stack(columns), names


def get_q2(wanted, out):
    registry = json.loads((ROOT/'data/evaluation/sce_baselines_latest_20261007/micro_reference_sources.json').read_text())['sources']
    result, sources = {}, {}
    for rel, start, end in (
            ('data/raw/sce_audit_20260928/micro_2020_2024.xlsx', 202001, 202412),
            ('data/raw/sce_baselines_latest_20261007/micro_latest.xlsx', 202501, 202510)):
        path = ROOT/rel
        assert sha(path) == registry[rel]
        sources[rel] = registry[rel]
        count = 0
        for r in read_q2_rows(path):
            month = clean_code(r.get('date'), 190001, 210012)
            uid = clean_code(r.get('userid'), 0, 10**12)
            if month is None or uid is None:
                continue
            key = (month, uid)
            if start <= key[0] <= end and key in wanted:
                if key in result:
                    raise ValueError('Overlapping Q2 workbook rows')
                result[key] = clean_code(r.get('Q2'), 1, 5)
                count += 1
        print('Extracted Q2 for requested person-months:', count, flush=True)
    path = out/'q2_selected_private.json'
    path.write_text(json.dumps([{'month': m, 'userid': u, 'Q2': v}
                               for (m, u), v in sorted(result.items())])+'\n')
    return result, sources


def load_rows(out):
    prior_summary = json.loads((EVALUATION/'regression_diagnostic_20261017.json').read_text())
    cases_path = EVALUATION/'cases_private.json'
    assert sha(cases_path) == prior_summary['source_cases_sha256']
    traits_receipt = json.loads((TRAITS.parent/'summary.json').read_text())
    assert sha(TRAITS) == traits_receipt['analysis_frame_sha256']
    cols = ['date', 'userid', 'tenure', 'financial_risk', 'general_risk', 'financial_change']
    traits = pd.read_parquet(TRAITS, columns=cols).set_index(['date', 'userid']).to_dict('index')
    grouped = defaultdict(list)
    for r in json.loads(cases_path.read_text()):
        grouped[r['month'], r['userid']].append(r)
    good = {}
    for key, pair in grouped.items():
        assert sorted(r['repeat'] for r in pair) == [1, 2]
        if all(r['arms']['reference']['validation_status'] == 'valid'
               and all(v is not None and np.isfinite(v) for v in
                       (r['arms']['reference']['mean'], r['real']['q9_mean'],
                        r['real']['q9_iqr'], r['baselines']['copy_previous'])) for r in pair):
            good[key] = pair
    wanted = set(good) | {(previous(m), uid) for m, uid in good}
    q2, sources = get_q2(wanted, out)
    histories, rows, history_hashes = {}, [], {}
    for (month, uid), pair in good.items():
        if month not in histories:
            path = PREPARED/str(month)/'past_private.json'
            histories[month] = json.loads(path.read_text())
            history_hashes[str(month)] = sha(path)
        r = pair[0]; h = histories[month][r['agent_id']]; state = h['state']
        prior, n = r['baselines']['copy_previous'], state['n_earlier_valid']
        current, before = traits[month, uid], traits[previous(month), uid]
        tenure = clean_code(current['tenure'], 2, 12)
        assert tenure is not None and 1 <= n <= tenure-1
        anchor = state['anchor']; center = round(state['center'], 1)
        rows.append({'month': month, **r['profile'], 'weight': r['design_survey_weight'],
                     'real': r['real']['q9_mean'], 'real_iqr': r['real']['q9_iqr'],
                     'prior': prior, 'prior_iqr': state['high']-state['low'],
                     'sim': np.mean([p['arms']['reference']['mean'] for p in pair]),
                     'sim_iqr': np.mean([p['arms']['reference']['iqr'] for p in pair]),
                     'anchor_gap': round(anchor, 1)-center if anchor is not None else 0.,
                     'anchor_available': int(anchor is not None), 'history_n': n,
                     'typical': round(anchor, 1) if anchor is not None else prior,
                     'earlier_excluding_last_gap': (anchor*n-state['center'])/(n-1)-prior if anchor is not None else 0.,
                     'tenure_previous_completed': tenure-1,
                     'financial_risk_prior': clean_code(before['financial_risk'], 1, 7),
                     'general_risk_prior': clean_code(before['general_risk'], 1, 7),
                     'financial_change_current': clean_code(current['financial_change'], 1, 5),
                     'outlook_previous': q2.get((previous(month), uid)),
                     'outlook_current': q2.get((month, uid))})
    # Compute denominators before normalizing any row.
    mass = {m: sum(r['weight'] for r in rows if r['month'] == m) for m in histories}
    for r in rows:
        r['weight'] /= mass[r['month']]
    return rows, {**sources, str(TRAITS.relative_to(ROOT)): sha(TRAITS),
                  'cases_private_sha256': sha(cases_path), 'past_file_sha256_by_month': history_hashes}


def regress(rows, numeric, cats=FIELDS, outcome='real', month=True):
    x, names = design(rows, numeric, cats, month)
    return fit(x, np.array([r[outcome] for r in rows]), np.array([r['weight'] for r in rows]), names)[0]


def run(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('A fresh ignored output directory is required')
    out.mkdir(parents=True)
    rows, sources = load_rows(out)
    assert len(rows) == 2284
    standard = ('prior', 'sim')
    history = (*standard, 'anchor_gap', 'anchor_available', 'history_n')
    fits = {'simulation_only': regress(rows, ('sim',), (), month=False),
            'simulation_plus_month': regress(rows, ('sim',), ()),
            'simulation_month_P': regress(rows, ('sim',)),
            'simulation_month_prior': regress(rows, standard, ()),
            'simulation_month_prior_P': regress(rows, standard),
            'full_history_valid_count': regress(rows, history),
            'history_completed_tenure_instead': regress(rows, (*standard, 'anchor_gap', 'anchor_available', 'tenure_previous_completed')),
            'history_both_counts': regress(rows, (*history, 'tenure_previous_completed'))}
    old = json.loads((EVALUATION/'history_information_increment_20261017.json').read_text())
    assert abs(fits['full_history_valid_count']['r2']-old['blocks']['history_summary']['r2']) < 1e-12
    complete = [r for r in rows if r['anchor_available']]
    fits['strict_older_mean_excludes_last'] = regress(complete, (*standard, 'earlier_excluding_last_gap', 'history_n'))
    uncertainty = regress(rows, ('prior', 'prior_iqr', 'sim_iqr', 'anchor_gap',
                                'anchor_available', 'tenure_previous_completed'), outcome='real_iqr')
    temporal = {}
    for name, pick in [('2020_2022', lambda r: r['month'] < 202300),
                       ('2023_2025', lambda r: r['month'] >= 202300)]:
        a = [r for r in rows if pick(r)]
        temporal[name] = {'valid_count_model': regress(a, history),
                          'tenure_model': regress(a, (*standard, 'anchor_gap', 'anchor_available', 'tenure_previous_completed'))}
    leave_year_out = {}
    for year in range(2020, 2026):
        result = regress([r for r in rows if r['month']//100 != year], history)
        leave_year_out[str(year)] = {k: result['coefficients'][k]
                                     for k in ('anchor_gap', 'history_n', 'prior', 'sim')}

    # Changing the zero of a covariate by a month-specific constant adds no
    # information with month fixed effects. Check using peer typical medians.
    peer_centers, cpi = {}, {}
    for m in sorted({r['month'] for r in rows}):
        a = sorted([r for r in complete if r['month'] == m], key=lambda r: r['typical'])
        total, running = sum(r['weight'] for r in a), 0.
        for r in a:
            running += r['weight']
            if running >= total/2:
                peer_centers[m] = r['typical']; break
        env = json.loads((PREPARED/str(m)/'environment.json').read_text())
        signals = [s for v in env['provider_args']['signals_by_step'].values() for s in v]
        match = [s for s in signals if s.get('role') != 'history' and s['signal_id'].startswith('bls_cpi_u_all_items_yoy')]
        assert len(match) == 1
        cpi[m] = float(match[0]['value'])
    for r in complete:
        r['typical_relative_peers'] = r['typical']-peer_centers[r['month']]
        r['typical_relative_current_CPI'] = r['typical']-cpi[r['month']]
    centered = {key: regress(complete, (*standard, key, 'history_n'))
                for key in ('typical', 'typical_relative_peers', 'typical_relative_current_CPI')}
    assert max(abs(r['r2']-centered['typical']['r2']) for r in centered.values()) < 1e-12

    # Same-person measured SCE outlook/preference proxies. No fabricated MIDUS
    # or GSS individual joint outcomes; missing categories are explicit.
    psych_specs = {'financial_outlook_previous': ('outlook_previous',),
                   'financial_outlook_current': ('outlook_current',),
                   'financial_risk_prior': ('financial_risk_prior',),
                   'general_risk_prior': ('general_risk_prior',),
                   'both_risk_preferences': ('financial_risk_prior', 'general_risk_prior'),
                   'current_finances_and_current_outlook': ('financial_change_current', 'outlook_current')}
    psychological = {}
    base_r2 = fits['full_history_valid_count']['r2']
    for name, extras in psych_specs.items():
        r = regress(rows, history, (*FIELDS, *extras))
        r['r2_increment_points'] = 100*(r['r2']-base_r2)
        r['coverage'] = {k: sum(a.get(k) is not None for a in rows) for k in extras}
        psychological[name] = r
    only_finance = regress(rows, history, (*FIELDS, 'financial_change_current'))
    psychological['current_outlook_given_current_finances_r2_points'] = 100*(
        psychological['current_finances_and_current_outlook']['r2']-only_finance['r2'])
    psychological['measured_vs_external'] = {
        'SCE_measured_proxies': 'Q2: household year-ahead financial outlook; QRA1/QRA2: financial/general risk preferences. Neither is Big Five or LOT general optimism.',
        'GSS2018': 'Existing HAPPY/SATFIN donor assignments are synthetic; no real SCE psychological measurements or identified residual association beyond matching X.',
        'MIDUS': 'Files were downloaded outside the agent workspace; no raw records read. Local aggregate script exists; no paired SCE outcome. Existing data-use restrictions and user-run pathway remain.'}
    result = {'status': 'posthoc_exploratory_history_and_measured_SCE_proxy_diagnostics',
              'completed_at_utc': datetime.now(timezone.utc).isoformat(),
              'n_person_months': len(rows), 'n_months': 12, 'new_api_calls': 0,
              'weights': 'same design-survey weights, each selected month total1; model generations averaged first',
              'fits': fits, 'uncertainty_tenure_model': uncertainty,
              'temporal_sensitivity': temporal, 'leave_one_year_out_coefficients': leave_year_out,
              'centering_sensitivity_complete_histories': centered,
              'history_counts': {'with_two_or_more_valid_prior_responses': len(complete),
                  'min_valid_prior': min(r['history_n'] for r in rows),
                  'max_valid_prior': max(r['history_n'] for r in rows),
                  'min_total_previous_surveys': min(r['tenure_previous_completed'] for r in rows),
                  'max_total_previous_surveys': max(r['tenure_previous_completed'] for r in rows),
                  'counts_differ_n': sum(r['history_n'] != r['tenure_previous_completed'] for r in rows)},
              'psychological_proxy_models': psychological,
              'limits': ['All estimates are retrospective conditional linear associations, not causal updating weights or attention measures.',
                         'Valid history count measures both experience and probability-response quality; actual tenure also has selection/cohort confounding.',
                         'Typical mean includes t-1 unless the strictly-older sensitivity explicitly excludes it.',
                         'Only returners observed; first-survey learning effect not identified.',
                         'Current Q2/Q1 are contemporaneous beliefs/reports for A-only diagnosis, not authorized new simulation inputs or strict B predictors.',
                         'Forecast above current CPI is not a forecast error: different reference periods. No future realized CPI used.',
                         'Centering on a common group level with month fixed effects changes interpretation, not information.',
                         'No independent validation or new calibration success claimed; R2 coefficient units differ from inflation percentage points.'],
              'source_sha256': sources, 'script_sha256': sha(__file__)}
    (out/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'fits': {k: {'r2': v['r2'], 'n': v['n'],
                           'selected_coefficients': {n: c for n,c in v['coefficients'].items() if n in ('anchor_gap','history_n','prior','sim','tenure_previous_completed','earlier_excluding_last_gap')}} for k,v in fits.items()},
                      'temporal': {k:{name:{key:value for key,value in v['coefficients'].items() if key in ('anchor_gap','history_n','tenure_previous_completed')} for name,v in a.items()} for k,a in temporal.items()},
                      'history_counts': result['history_counts'],
                      'psychology': {k: {'r2':v['r2'], 'increment':v['r2_increment_points'], 'coverage':v['coverage']} for k,v in psychological.items() if isinstance(v,dict) and 'r2' in v},
                      'Q2_increment_given_Q1': psychological['current_outlook_given_current_finances_r2_points']}, ensure_ascii=False), flush=True)
    return result
