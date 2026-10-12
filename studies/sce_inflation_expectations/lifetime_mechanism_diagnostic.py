"""Read-only diagnosis of saved lifetime trials; no simulation or network calls."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import numpy as np

ARMS = ('original', 'numeric_history', 'text_history')
# Evaluation-only, manually transcribed from dated BLS first-release pages.
FUTURE_CPI = {
    '202203': ('202303', 5.0, '2023-04-12', 'cpi_04122023.htm'),
    '202209': ('202309', 3.7, '2023-10-12', 'cpi_10122023.htm'),
    '202303': ('202403', 3.5, '2024-04-10', 'cpi_04102024.htm'),
    '202403': ('202503', 2.4, '2025-04-10', 'cpi_04102025.htm'),
}
PATTERNS = {
    'easing_or_moderation_words': r'\b(?:eas\w*|cool\w*|moderat\w*|disinflation|fall\w*|declin\w*)\b',
    'fed_or_rate_policy_words': r'\b(?:fed|federal reserve|tighten\w*|interest rate\w*)\b',
    'history_words': r'\b(?:histor\w*|past|crisis|recession|1970s|1980s|experienced)\b',
}


def diagnose(root, out):
    root, out = Path(root).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(root / 'outputs'):
        raise ValueError('Fresh ignored output directory required')
    trial = root / 'outputs/sce_lifetime_text_trial_20261012_v1'
    analysis = root / 'outputs/sce_lifetime_text_analysis_20261012_v1'
    inputs = [trial / 'trial_manifest.json', analysis / 'paired_evaluation_private.json', analysis / 'summary.json']
    plan, pairs, saved = [json.loads(p.read_text()) for p in inputs]
    if tuple(plan['arms']) != ARMS or saved['actual_calls'] != 288:
        raise ValueError('Wrong completed trial')
    result = {'new_api_calls': 0, 'months': {}, 'prompt_audit': {}, 'reason_word_counts': {},
              'limits': ['Four previously used development months; 12 selected people per month.',
                         'Two generations are paired observations, not independent extra people.',
                         'Future CPI is an ex-post comparator, never a new simulation input.',
                         'Closer numerical agreement cannot identify training-data memorization.',
                         'Reason word matches are descriptive, not causal evidence.'],
              'future_cpi_sources': {m: {'reference_period': v[0], 'yoy_nsa_percent': v[1],
                  'published_date': v[2], 'source_url': 'https://www.bls.gov/news.release/archives/' + v[3],
                  'checked_on': '2026-10-12', 'status': 'web-verified first-release value; evaluation only'}
                  for m, v in FUTURE_CPI.items()}}
    q9_shifts, q8_shifts = {a: [] for a in ARMS[1:]}, {a: [] for a in ARMS[1:]}
    reasons = {a: [] for a in ARMS}
    raw_bins = {a: [] for a in ARMS}
    common_q9 = {(r['month'], r['repeat'], r['agent_id']) for r in pairs if r['measure'] == 'Q9'
                 and all(isinstance(r.get(a), (float, int)) and np.isfinite(r[a]) for a in ('real',) + ARMS)}
    for month in FUTURE_CPI:
        monthly = {'repeats': {}}
        for rep in (1, 2):
            cell = {}
            for measure, shifts in (('Q9', q9_shifts), ('Q8', q8_shifts)):
                rr = [r for r in pairs if r['month'] == month and r['repeat'] == rep and r['measure'] == measure
                      and all(isinstance(r.get(a), (int, float)) and np.isfinite(r[a]) for a in ('real',) + ARMS)]
                values = {a: np.array([r[a] for r in rr]) for a in ('real',) + ARMS}
                # Match the frozen evaluation conventions: Q9 weighted quantile,
                # Q8 interpolated percentile, even for equal-weight samples.
                from .news_exposure_analysis import describe
                stats = {a: describe(v, measure == 'Q8') for a, v in values.items()}
                centers = {a: s['median_pp'] for a, s in stats.items()}
                cell[measure] = {'n': len(rr), 'centers_percent': centers,
                    'iqr_pp': {a: s['cross_person_iqr_pp'] for a, s in stats.items()},
                    'distance_to_future_cpi_pp': {a: abs(c - FUTURE_CPI[month][1]) for a, c in centers.items()},
                    'distance_to_real_sample_center_pp': {a: abs(centers[a] - centers['real']) for a in ARMS}}
                for a in ARMS[1:]:
                    diff = values[a] - values['original']
                    shifts[a].extend(diff.tolist())
                    cell[measure][a + '_shift'] = {'mean_pp': float(np.mean(diff)), 'negative': int(sum(diff < 0)), 'n': len(diff)}
                if measure == 'Q9':
                    for a in ARMS:
                        expected = saved['months'][month]['repeats'][str(rep)][measure]['arms'][a]['median_absolute_error_pp']
                        if not np.isclose(cell[measure]['distance_to_real_sample_center_pp'][a], expected):
                            raise ValueError('Saved Q9 score mismatch')
            monthly['repeats'][str(rep)] = cell
        previews = {a: json.loads((trial / month / f'preview_{a}.json').read_text()) for a in ARMS}
        inputs.extend(trial / month / f'preview_{a}.json' for a in ARMS)
        texts = [p['messages'][0]['content'] for p in previews['original']]
        macro = [t.split('Recent official statistics:\n')[1].split('Synthetic household spending context')[0] for t in texts]
        view = [t.split('Personal view about economic policy:\n')[1].split('\n\n')[0] if 'Personal view about economic policy:\n' in t else 'not supplied' for t in texts]
        other = [float(re.search(r'other (\d+(?:\.\d+)?)%', t).group(1)) for t in texts]
        result['prompt_audit'][month] = {'person_months': len(texts), 'distinct_national_statistics_blocks': len(set(macro)),
            'unknown_housing_count': sum('unknown housing situation' in t for t in texts),
            'other_spending_share_percent_min_max': [min(other), max(other)],
            'confidence_statements': dict(Counter(view)),
            'history_immediately_precedes_questionnaire': all('Past U.S. price history.' in p['messages'][0]['content'].split('Question 1')[0] for p in previews['text_history'])}
        monthly['across_two_generations'] = {
            measure: {a: float(np.mean([monthly['repeats'][str(rep)][measure]['centers_percent'][a] for rep in (1, 2)]))
                      for a in ('real',) + ARMS} for measure in ('Q8', 'Q9')}
        result['months'][month] = monthly
    for job in plan['jobs']:
        path = root / 'outputs/local_runs' / job['run_id'] / 'llm_calls.jsonl'
        inputs.append(path)
        expected = {p['agent_id']: p for p in json.loads((trial / job['month'] / f"preview_{job['arm']}.json").read_text())}
        for line in path.read_text().splitlines():
            call = json.loads(line)
            if call['prompt_text'] != json.dumps(expected[call['agent_id']]['messages'], ensure_ascii=False):
                raise ValueError('Actual input differs from saved preview')
            if call['prompt_sha256'] != expected[call['agent_id']]['prompt_sha256']:
                raise ValueError('Actual prompt hash mismatch')
            raw = call['raw_response_text']
            if hashlib.sha256(raw.encode()).hexdigest() != call['raw_response_sha256']:
                raise ValueError('Raw response hash mismatch')
            obj = json.loads(raw.removeprefix('```json').removesuffix('```').strip())
            reasons[job['arm']].append(obj.get('reason', ''))
            if (job['month'], job['repeat'], call['agent_id']) in common_q9:
                raw_bins[job['arm']].append([obj['q9'][f'bin{i}'] for i in range(1, 11)])
    for a in ARMS:
        result['reason_word_counts'][a] = {'n': len(reasons[a]), **{name: sum(bool(re.search(pattern, s, re.I)) for s in reasons[a]) for name, pattern in PATTERNS.items()}}
    result['response_shifts'] = {measure: {a: {'mean_pp': float(np.mean(v)), 'median_pp': float(np.median(v)), 'negative': sum(x < 0 for x in v), 'n': len(v)} for a, v in shifts.items()} for measure, shifts in (('Q9', q9_shifts), ('Q8', q8_shifts))}
    result['raw_q9_bin_probability_means'] = {a: {'n': len(v), 'bin1_to_bin10_percent': np.mean(v, axis=0).tolist()} for a, v in raw_bins.items()}
    result['auxiliary_shape'] = {}
    for measure in ('personal_uncertainty', 'raw_deflation_probability'):
        rr = [r for r in pairs if r['measure'] == measure and
              all(isinstance(r.get(a), (float, int)) and np.isfinite(r[a]) for a in ('real',) + ARMS)]
        result['auxiliary_shape'][measure] = {'n': len(rr),
            'pooled_response_means': {a: float(np.mean([r[a] for r in rr])) for a in ('real',) + ARMS},
            'paired_changes_from_original': {a: float(np.mean([r[a] - r['original'] for r in rr])) for a in ARMS[1:]},
            'unit': 'percentage points of inflation' if measure == 'personal_uncertainty' else 'percentage points of probability'}
    result['source_sha256'] = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    result['diagnostic_code_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['word_patterns'] = PATTERNS
    out.mkdir(parents=True)
    (out / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    diagnose(Path(__file__).resolve().parents[2], args.out)
