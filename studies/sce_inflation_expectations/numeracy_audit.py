"""Evaluation-only numeracy associations; no provider, network or runtime edits."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .household_state_audit import summary, classify_numeracy, NUMERACY_ANSWERS
from .household_state_analysis import density
from .model import parse_sce_response
from .scoring.sce_q9_frozen import provenance


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def shift_month(month, offset):
    y, m = divmod(int(month), 100)
    y, m = divmod(y * 12 + m - 1 + offset, 12)
    return y * 100 + m + 1


def group_stats(frame, weight):
    result = {}
    for label in ['High', 'Low']:
        g = frame[frame._NUM_CAT == label]
        out = {'n_rows': len(g), 'unique_people': int(g.userid.nunique())}
        for key in ['point', 'density_mean', 'uncertainty', 'point_future_error',
                    'density_future_error', 'point_current_distance', 'density_current_distance']:
            out[key] = summary(g[key], g[weight])
        result[label] = out
    return result


def add_benchmarks(frame, cpi):
    frame = frame.copy()
    frame['cpi_current'] = frame.date.map(cpi)
    frame['cpi_future'] = frame.date.map(lambda m: cpi.get(shift_month(m, 12), np.nan))
    for label, benchmark in [('future_error', 'cpi_future'), ('current_distance', 'cpi_current')]:
        for field in ['point', 'density_mean']:
            name = 'point' if field == 'point' else 'density'
            frame[f'{name}_{label}'] = (frame[field] - frame[benchmark]).abs()
    return frame


def adjusted_associations(frame, weight):
    """Descriptive WLS with month FE; not an individual-label causal effect."""
    controls = ['date', '_AGE_CAT', '_EDU_CAT', '_HH_INC_CAT', '_REGION_CAT']
    ans = {}
    for field in ['point', 'density_mean', 'uncertainty', 'point_future_error', 'density_future_error']:
        d = frame.dropna(subset=controls + ['_NUM_CAT', field, weight]).copy()
        d = d[d._NUM_CAT.isin(['High', 'Low']) & np.isfinite(d[field]) & (d[weight] > 0)]
        # Each month gets equal total mass, while preserving within-month survey weights.
        w = d[weight] / d.groupby('date')[weight].transform('sum')
        X = pd.concat([pd.Series(1., index=d.index, name='intercept'),
                       (d._NUM_CAT == 'Low').astype(float).rename('low_vs_high'),
                       pd.get_dummies(d[controls].astype(str), drop_first=True, dtype=float)], axis=1)
        sw = np.sqrt(w.to_numpy(float))
        beta, _, rank, _ = np.linalg.lstsq(X.to_numpy(float) * sw[:, None],
                                         d[field].to_numpy(float) * sw, rcond=None)
        ans[field] = {'n': len(d), 'low_minus_high_coefficient_pp': float(beta[1]),
                      'rank': int(rank), 'parameters': X.shape[1]}
    return {'controls': controls, 'weighting': 'Equal month mass; within-month survey weights',
            'interpretation': 'Descriptive conditional mean associations; panel dependence not tested; no p-values or causal claims',
            'outcomes': ans}


@lru_cache(maxsize=None)
def fit(bins):
    return density(list(bins))


def simulate_archive(root, run, truth, real_frame, cpi):
    folder = root / run
    population = json.loads((folder / 'population_effective.json').read_text())['personas']
    personas = {p['agent_id']: p for p in population}
    seen, rows, checks = set(), [], 0
    for s in (folder / 'llm_calls.jsonl').read_text().splitlines():
        call = json.loads(s)
        if call.get('error') is not None:
            continue
        aid = call['agent_id']
        month = int(call['target_month'].replace('-', ''))
        key = (month, aid)
        if key in seen:
            raise ValueError('duplicate successful agent-month')
        seen.add(key)
        persona = personas[aid]['attributes']
        label = persona['numeracy']
        assert label in ['high', 'low']
        text = call['prompt_text']
        assert digest_text(text) == call['prompt_sha256']
        assert digest_text(call['raw_response_text']) == call['raw_response_sha256']
        phrase = f"Your score on the survey's numeracy assessment was {label}."
        assert text.count(phrase) == 1
        opposite = 'low' if label == 'high' else 'high'
        assert f"Your score on the survey's numeracy assessment was {opposite}." not in text
        parsed, error = parse_sce_response(call['raw_response_text'])
        if error or parsed is None:
            raise ValueError(f'invalid archived answer: {error}')
        uid = int(aid.removeprefix('sce_u'))
        t = truth[(month, uid)]
        real = fit(tuple(t[f'Q9_bin{i}'] for i in range(1, 11)))
        sim = fit(tuple(parsed['bins']))
        r = real_frame[(real_frame.date == month) & (real_frame.userid == uid)]
        assert len(r) == 1 and r.iloc[0]._NUM_CAT.lower() == label
        rows.append({'date': month, 'userid': uid, '_NUM_CAT': label.title(), 'weight': 1.,
                     **{k: r.iloc[0][k] for k in ['_AGE_CAT', '_EDU_CAT', '_HH_INC_CAT', '_REGION_CAT']},
                     'survey_weight': t['weight'], 'point': parsed['point_pct'],
                     'density_mean': sim['mean'], 'uncertainty': sim['iqr'],
                     'real_point': t['Q8v2part2'], 'real_density_mean': real['mean'],
                     'real_uncertainty': real['iqr'],
                     'fit_status_sim': sim['status'], 'fit_status_real': real['status']})
        checks += 1
    simulated = add_benchmarks(pd.DataFrame(rows), cpi)
    matched_real = simulated.copy()
    for key in ['point', 'density_mean', 'uncertainty']:
        matched_real[key] = matched_real[f'real_{key}']
    matched_real = add_benchmarks(matched_real, cpi)
    # Identical masks independently for Q8 and Q9; missing fits not treated as zero.
    missing = {}
    for key in ['point', 'density_mean', 'uncertainty']:
        valid = np.isfinite(simulated[key]) & np.isfinite(matched_real[key])
        missing[key] = int((~valid).sum())
        for df in [simulated, matched_real]:
            df.loc[~valid, key] = np.nan
    simulated = add_benchmarks(simulated, cpi)
    matched_real = add_benchmarks(matched_real, cpi)
    result = {'source_run': run, 'n_population': len(population), 'n_valid_responses': checks,
              'prompt_and_response_hashes_checked': checks, 'actual_numeracy_sentence_checked': checks,
              'common_mask_exclusions': missing, 'matched_real_same_frozen_scoring': group_stats(matched_real, 'weight'),
              'simulated_same_frozen_scoring': group_stats(simulated, 'weight'),
              'controlled_real': adjusted_associations(matched_real, 'weight'),
              'controlled_simulated': adjusted_associations(simulated, 'weight'),
              'scope': 'Equal-weight exact selected respondents; independent group comparisons, no prompt-only ablation or national claim',
              'survey_weight_sensitivity': {'real': group_stats(matched_real, 'survey_weight'),
                                             'simulated': group_stats(simulated, 'survey_weight')}}
    return result, simulated


def digest_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def run_audit(root, out, cache=None):
    out.mkdir(parents=True, exist_ok=False)
    source = root / 'data/raw/sce_audit_20260928/micro_2020_2024.xlsx'
    columns = ['date', 'userid', 'weight', 'Q8v2part2', 'Q9_mean', 'Q9_iqr',
               '_AGE_CAT', '_EDU_CAT', '_HH_INC_CAT', '_REGION_CAT', '_NUM_CAT'] + list(NUMERACY_ANSWERS)
    print('Reading official microdata (2020–2024); evaluation only', flush=True)
    frame = pd.read_parquet(cache, columns=columns) if cache else pd.read_excel(source, skiprows=1, usecols=columns)
    frame = frame[(frame.date >= 202001) & (frame.date <= 202412)].copy()
    assert not frame.duplicated(['date', 'userid']).any()
    frame.to_parquet(out / 'micro_evaluation_private.parquet', index=False)
    n_source_rows = len(frame)
    eligible_weight = np.isfinite(frame.weight) & (frame.weight > 0)
    excluded_weight_rows = int((~eligible_weight).sum())
    frame = frame.loc[eligible_weight].copy()
    inferred, complete = classify_numeracy(frame)
    known = complete & frame._NUM_CAT.isin(['High', 'Low'])
    frame = frame.rename(columns={'Q8v2part2': 'point', 'Q9_mean': 'density_mean', 'Q9_iqr': 'uncertainty'})
    macro_path = root / 'data/evaluation/sce_baselines_latest_20261007/aggregate_inputs.json'
    macro = json.loads(macro_path.read_text())['cpi_first_releases']
    cpi = {}
    for row in macro:
        m = int(row['reference_period'].replace('-', ''))
        assert m not in cpi, 'CPI reference month duplicate'
        cpi[m] = float(row['value'])
    frame = add_benchmarks(frame, cpi)
    monthly = {str(int(m)): group_stats(g, 'weight') for m, g in frame.groupby('date')}
    fields = ['point', 'density_mean', 'uncertainty', 'point_future_error', 'density_future_error',
              'point_current_distance', 'density_current_distance']
    equal_month = {}
    for key in fields:
        gaps = [r['Low'][key]['weighted_median_pp'] - r['High'][key]['weighted_median_pp']
                for r in monthly.values() if r['Low'][key]['valid_n'] and r['High'][key]['valid_n']]
        equal_month[key] = {'months': len(gaps), 'mean_monthly_median_gap_low_minus_high_pp': float(np.mean(gaps)),
                           'months_low_greater': int(sum(x > 1e-9 for x in gaps)),
                           'months_high_greater': int(sum(x < -1e-9 for x in gaps)),
                           'months_tied': int(sum(abs(x) <= 1e-9 for x in gaps))}
    truth_path = root / 'data/evaluation/dev_full_20261005T045330Z_947a818f/truth.json'
    truth = {(int(r['date']), int(r['userid'])): r for r in json.loads(truth_path.read_text())['per_person']}
    runs = ['outputs/local_runs/sce-local-openai-20261005T092656Z-202105-8d2e3b2c',
            'outputs/local_runs/sce-local-openai-20261005T092656Z-202106-e4f49f76']
    simulations = {}
    hashes = {str(source.relative_to(root)): digest(source), str(macro_path.relative_to(root)): digest(macro_path),
              str(truth_path.relative_to(root)): digest(truth_path)}
    if cache:
        hashes[str(cache.relative_to(root))] = digest(cache)
    for run in runs:
        result, rows = simulate_archive(root, run, truth, frame, cpi)
        month = str(int(rows.date.iloc[0]))
        simulations[month] = result
        rows.to_json(out / f'simulation_{month}_private.jsonl', orient='records', lines=True)
        for file in ['population_effective.json', 'llm_calls.jsonl', 'simulation_effective.json']:
            path = root / run / file
            hashes[str(path.relative_to(root))] = digest(path)
    assert provenance()['live_matches_pinned'], 'Scoring kernel differs from frozen version'
    snapshot = out / 'source_snapshot'
    snapshot.mkdir()
    for path in [Path(__file__), root / 'scripts/audit_sce_numeracy.py',
                 root / 'studies/sce_inflation_expectations/household_state_audit.py',
                 root / 'studies/sce_inflation_expectations/household_state_analysis.py']:
        (snapshot / path.name).write_bytes(path.read_bytes())
        hashes[str(path.relative_to(root))] = digest(path)
    result = {'audit_id': out.name, 'sources_sha256': hashes, 'new_api_calls': 0,
              'changed_runtime_inputs': False, 'scorer_provenance': provenance(),
              'definition': 'Official High = at least four correct of five numeracy/financial literacy questions; category includes carried entry assessments',
              'scope': 'Retrospective descriptive evaluation; 2021-05/06 already development data; 60-month review exploratory, no independent test claim',
              'benchmarks': {'current': 'CPI-U all-items NSA y/y in survey calendar month; retrospective distance, not error or necessarily available during interview',
                             'future': 'CPI-U all-items NSA y/y in month t+12, from initial BLS release; month-level approximation to next-12-month expectation; evaluation only'},
              'numeracy_classification': {'source_rows': n_source_rows, 'excluded_missing_nonpositive_weight_rows': excluded_weight_rows,
                   'n_rows': len(frame), 'unique_people': int(frame.userid.nunique()),
                   'months': len(monthly), 'category_counts': frame._NUM_CAT.fillna('Missing').value_counts().to_dict(),
                   'complete_five_question_n': int(complete.sum()), 'comparable_n': int(known.sum()),
                   'agreement_n': int((inferred[known] == frame.loc[known, '_NUM_CAT']).sum()),
                   'disagreement_n': int((inferred[known] != frame.loc[known, '_NUM_CAT']).sum())},
              'missing_benchmarks': {'current_months': sorted(frame.loc[frame.cpi_current.isna(), 'date'].unique().tolist()),
                                     'future_months': sorted(frame.loc[frame.cpi_future.isna(), 'date'].unique().tolist())},
              'real_monthly': monthly, 'real_equal_month_contrasts': equal_month,
              'real_controlled_associations': adjusted_associations(frame, 'weight'),
              'simulations': simulations, 'limits': ['Association is not label causality.',
                 'Official Q9 derived values for full real data; identical frozen approximate fits for selected real versus simulated data.',
                 'Numeracy high/low does not manipulate the underlying LLM computation capability.',
                 'No correction for panel/survey design dependence; no significance claims.',
                 'Calendar-month CPI is not household-specific experienced inflation.']}
    (out / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'classification': result['numeracy_classification'], 'contrasts': equal_month}, ensure_ascii=False), flush=True)
    return result
