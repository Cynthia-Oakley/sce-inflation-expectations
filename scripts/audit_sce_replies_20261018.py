#!/usr/bin/env python3
"""Audit archived SCE reply text without API calls, fitting, or source mutation.

All row-level content is private. Rules detect words, not latent understanding.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[1]
SEED = 'sce_reply_audit_20261018_v1'
RULES = {
    'prior_reference': r'\b(?:last month|previous|prior|earlier (?:answer|survey|belief)|history|historical|typical|usual|outlier|revert)',
    'history_or_normality': r'\b(?:history|historical|typical|usual|outlier|revert|long[- ]run|long[- ]term|past surveys|own average)',
    'extreme_or_outlier': r'\b(?:extreme|outlier|unusually (?:high|low)|abnormally|implausib|unrealistic)',
    'statistics_or_price_evidence': r'\b(?:CPI|consumer price|unemployment|gasoline|energy|shelter|food|rent|inflation (?:is|was|has been) running)',
    'policy_reference': r'\b(?:Fed\b|Federal Reserve|rate cut|rate hike|tightening|easing|monetary|policy rate)',
    'persistence_vocabulary': r'\b(?:lag|persist|sticky|sustain|durab|gradual|continu|remain|longer|temporary|transitory|one[- ]off|over time)',
    'explicit_deflation': r'\b(?:deflation|negative inflation|below[- ]zero|negative (?:tail|outcome))',
    'lower_tail_or_downside': r'\b(?:downside|lower tail|negative tail|deflation)',
    'future_horizon': r'\b(?:next (?:12|twelve)|(?:12|twelve)[- ]month|year ahead|year-ahead|coming year|over the year)',
    'small_change_wording': r'\b(?:slight|modest|nudge|shade|small|little|a bit)',
    'explicit_month_rate': r'\b(?:month[- ]over[- ]month|monthly inflation|monthly CPI|per month|annualiz|multipl(?:y|ied).{0,20}12)',
    'price_level_wording': r'\b(?:price level|overall prices|prices overall|general prices|broad[- ]based price declines)',
    'disinflation_wording': r'\b(?:disinflation|inflation (?:has |is |was )?(?:eas|cool|declin|fall|slow)|easing inflation|cooling inflation|slowing inflation)',
    'food_price_decline_wording': r'\bfalling (?:energy and )?food(?: and energy|/energy)? prices\b|\bfood(?:/energy)? prices (?:have |are |were |has )?(?:fallen|falling|declin(?:ed|ing)|drop(?:ped|ping))',
    'base_effect_or_window_price_wording': r'price level|base.effect|year.ago base|roll.{0,30}window|forecast window|window.{0,30}(?:price|inflat)',
}
COMPILED = {k: re.compile(v, re.I) for k, v in RULES.items()}


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(x):
    return isinstance(x, (float, int)) and math.isfinite(x)


def quantile(values, p):
    values = sorted(values)
    z = (len(values)-1)*p
    lo = math.floor(z)
    return values[lo] + (z-lo)*(values[min(lo+1, len(values)-1)]-values[lo])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial', type=Path, default=ROOT/'outputs/sce_reference_validation_trial_20261017_v2')
    parser.add_argument('--cases', type=Path, default=ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1/cases_private.json')
    parser.add_argument('--out', type=Path, default=ROOT/'outputs/sce_reply_audit_20261018_v1')
    args = parser.parse_args()
    for name in ['trial', 'cases', 'out']:
        value = getattr(args, name)
        setattr(args, name, value.resolve() if value.is_absolute() else (ROOT/value).resolve())
    if args.out.exists():
        raise SystemExit('Output exists; use a new version instead of overwriting.')
    cases = json.loads(args.cases.read_text())
    bykey = {(x['month'], x['agent_id'], x['repeat']): x for x in cases}
    if len(bykey) != len(cases):
        raise ValueError('Duplicate archived scored case key')
    jobs = json.loads((args.trial/'manifest.json').read_text())['jobs']
    rows, sources, prompts = [], {}, {}
    actual_prompt_match = 0
    scored_reply_match = 0
    prompt_structure = defaultdict(Counter)
    pattern_candidates = defaultdict(list)
    for job in jobs:
        # Archived execution directory is fixed by the job identifier, never executed.
        run_id = job.get('run_id') or job.get('job_id')
        if run_id is None:
            raise ValueError('Missing archived run identifier')
        path = ROOT/'outputs/local_runs'/run_id/'llm_calls.jsonl'
        if not path.exists():
            raise FileNotFoundError(path)
        sources[str(path.relative_to(ROOT))] = sha(path)
        for line_no, line in enumerate(path.read_text().splitlines(), 1):
            call = json.loads(line)
            if call['error'] is not None:
                raise ValueError('Unexpected API error in archived complete batch')
            month = int(call['target_month'].replace('-', ''))
            repeat = int(re.search(r'-r(\d+)$', run_id).group(1))
            case = bykey[(month, call['agent_id'], repeat)]
            messages = json.loads(call['prompt_text'])
            text = '\n\n'.join(x['content'] for x in messages)
            key = (month, call['agent_id'])
            if key not in prompts:
                preview = json.loads((args.trial/str(month)/'preview_reference.json').read_text())
                prompts.update({(month, x['agent_id']): x for x in preview})
            actual_prompt_match += messages == prompts[key]['messages']
            raw = json.loads(call['raw_response_text'])
            arm = case['arms']['reference']
            bins = [raw['q9'][f'bin{i}'] for i in range(1, 11)]
            scored_reply_match += bins == arm['q9_bins'] and raw['point_pct'] == arm['point']
            marker = text.index('Your earlier survey response')
            prior_start = text.index('{', marker)
            prior, _ = json.JSONDecoder().raw_decode(text[prior_start:])
            reason = str(raw.get('reason', ''))
            flags = {k: bool(v.search(reason)) for k,v in COMPILED.items()}
            flags['policy_and_persistence_words'] = flags['policy_reference'] and flags['persistence_vocabulary']
            # Actual message structure, not the 77-signal stored environment count.
            structure = {
                'correct_yoy_label': 'compared with a year earlier' in text,
                'separate_monthly_label': bool(re.search(r'; [+-]?[\d.]+% in \w+ alone', text)),
                'rolling_cpi_yoy_label': 'CPI inflation (12-month %)' in text,
                'prior_raw_ten_bins': len(prior.get('q9', {})) == 10,
                'prior_is_expectation': 'These were your reported expectations, not measured inflation.' in text,
                'prior_own_horizon': '12 months following that earlier survey' in text,
                'window_advanced_twice': text.count('advanced by one month') == 2,
                'history_summary': 'Your survey history (a summary of your own earlier answers)' in text,
                'no_fixed_adjustment': 'no fixed amount of adjustment is required' in text,
                'timing_is_public_not_read': 'not what you actually read or remembered' in text,
                'policy_not_known_outcome': 'not a known future outcome' in text,
                'no_explicit_cumulative_price_definition_in_questions': not bool(re.search(r'cumulative|price level.*12|prices.*today.*12', text[text.index('Question 1 (point estimate):'):], re.I)),
            }
            ps = prompt_structure[month]
            for k,v in structure.items(): ps[k] += v
            if repeat == 1:
                ps['unique_prompts'] += 1
            # Both repeats intentionally count in field coverage denominators.
            ps['reply_prompts'] += 1
            if repeat == 1:
                # Count displayed bullet groups in each bounded section.
                sections = [('rolling_trends', 'Recent trends', 'Synthetic household spending'),
                            ('general_news', 'General news you encountered:', 'Other news you encountered:'),
                            ('other_news', 'Other news you encountered:', 'Public policy news brief'),
                            ('policy_bullets', 'Public policy news brief', 'Publication timing'),
                            ('publication_timing_bullets', 'Publication timing', 'Your earlier survey response')]
                for name,a,b in sections:
                    frag = text[text.index(a):text.index(b)]
                    ps[name] += sum(z.startswith('- ') for z in frag.splitlines())
                ps['prompt_chars_sum'] += len(text)
            model_mean = arm['mean']
            real_mean = case['real']['q9_mean']
            pdef = sum(prior['q9'][f'bin{i}'] for i in range(6,11))
            row = {
                'month': month, 'agent_id': call['agent_id'], 'repeat': repeat,
                'source': str(path.relative_to(ROOT)), 'source_line': line_no,
                'prompt_sha256': call['prompt_sha256'], 'raw_response_sha256': call['raw_response_sha256'],
                'reason': reason, 'flags': flags,
                'point': raw['point_pct'], 'prior_point': prior['point_pct'],
                'q9_bins': bins, 'prior_bins': [prior['q9'][f'bin{i}'] for i in range(1,11)],
                'deflation_probability': sum(bins[5:]), 'prior_deflation_probability': pdef,
                'valid': arm['validation_status'] == 'valid',
                'model_q9_mean': model_mean, 'real_q9_mean': real_mean,
                'prior_q9_mean': case['real']['previous_q9_mean'],
                'error': model_mean-real_mean if finite(model_mean) and finite(real_mean) else None,
                'profile': case['profile'],
            }
            rows.append(row)
            for name in ['explicit_month_rate', 'price_level_wording', 'explicit_deflation', 'extreme_or_outlier',
                         'food_price_decline_wording', 'base_effect_or_window_price_wording']:
                if flags[name]: pattern_candidates[name].append(row)
    if len(rows) != len(cases) or actual_prompt_match != len(rows) or scored_reply_match != len(rows):
        raise ValueError('Archived prompt/response/case reconciliation failed')
    # Choose one hash-random person per error stratum per month. Two repeats remain paired.
    grouped = defaultdict(list)
    for row in rows: grouped[(row['month'], row['agent_id'])].append(row)
    strata = defaultdict(list)
    for (month, agent), group in grouped.items():
        if len(group) != 2 or any(x['error'] is None for x in group): continue
        error = statistics.mean(x['error'] for x in group)
        label = 'negative' if error < -.3 else ('positive' if error > .3 else 'stable')
        strata[(month,label)].append((agent, error, group))
    samples, sampling_counts = [], []
    for (month,label), group in sorted(strata.items()):
        chosen = min(group, key=lambda x: hashlib.sha256(f'{SEED}|{month}|{label}|{x[0]}'.encode()).hexdigest())
        alias = f'{month}_{label}'
        sampling_counts.append({'month':month, 'stratum':label, 'population_n':len(group), 'selected_n':1})
        samples.append({'alias':alias, 'month':month, 'stratum':label, 'eligible_in_stratum':len(group),
                        'agent_id':chosen[0], 'paired_mean_error':chosen[1],
                        'prompt_messages':prompts[(month,chosen[0])]['messages'], 'replies':chosen[2]})
    summary = {
        'status':'archived_text_audited_zero_api_no_refit', 'seed':SEED,
        'api_calls':0, 'q9_refits':0, 'reply_n':len(rows), 'person_month_n':len(grouped),
        'reconciliation':{'actual_prompt_equals_preview_n':actual_prompt_match,'raw_reply_equals_scored_n':scored_reply_match},
        'rule_definitions':RULES, 'warning':'Literal text cues only, not proof of cognition, causal mechanisms, or information use.',
        'all_reply_rules':{name:sum(x['flags'][name] for x in rows) for name in rows[0]['flags']},
        'per_month_rules':{str(month):{'reply_n':len(g), **{name:sum(x['flags'][name] for x in g) for name in g[0]['flags']}}
                           for month in sorted({x['month'] for x in rows})
                           for g in [[x for x in rows if x['month']==month]]},
        'prompt_structure':{str(m):dict(v) for m,v in sorted(prompt_structure.items())},
        'sampling':{'unit':'person-month with both scored Q9 means and real Q9 mean', 'error_unit':'percentage point',
                    'negative':'two-repeat mean error < -0.3', 'stable':'absolute two-repeat mean error <= 0.3',
                    'positive':'two-repeat mean error > 0.3', 'selection':'minimum SHA256(seed|month|stratum|agent_id)',
                    'strata':sampling_counts,'selected_person_month_n':len(samples),'selected_reply_n':sum(len(s['replies']) for s in samples)},
    }
    valid = [x for x in rows if x['valid']]
    for label,group in [('all_valid',valid), *[(str(m),[x for x in valid if x['month']==m]) for m in sorted({x['month'] for x in valid})]]:
        prob = [x['deflation_probability'] for x in group]
        point = [x['point'] for x in group]
        oldzero = [x for x in group if x['prior_deflation_probability']==0]
        summary.setdefault('probability_expression',{})[label] = {
            'valid_reply_n':len(group), 'deflation_zero_n':sum(p==0 for p in prob),
            'deflation_positive_n':sum(p>0 for p in prob), 'positive_deflation_without_explicit_word_n':sum(x['deflation_probability']>0 and not x['flags']['explicit_deflation'] for x in group),
            'prior_zero_n':len(oldzero), 'prior_zero_to_positive_n':sum(x['deflation_probability']>0 for x in oldzero),
            'deflation_probability_median':statistics.median(prob),
            'deflation_probability_at_1_2_5_10_n':sum(p in [1,2,5,10] for p in prob),
            'point_integer_n':sum(abs(p-round(p))<1e-9 for p in point),
            'point_half_grid_n':sum(abs(p*2-round(p*2))<1e-9 for p in point),
            'point_q25':quantile(point,.25),'point_q75':quantile(point,.75),
        }
    sources[str(args.cases.relative_to(ROOT))] = sha(args.cases)
    for p in [args.trial/'manifest.json', ROOT/'data/raw/sce_audit_20260928/questionnaire.pdf',
              ROOT/'data/raw/sce_baselines_20261007/cpi_20231212.web.txt',
              ROOT/'data/raw/sce_baselines_20261007/cpi_20230613.web.txt', Path(__file__)]:
        sources[str(p.relative_to(ROOT))] = sha(p)
    summary['source_sha256'] = sources
    args.out.mkdir(parents=True)
    dump(args.out/'aggregate_summary.json', summary)
    dump(args.out/'sampled_cases_private.json', samples)
    dump(args.out/'semantic_candidates_private.json', dict(pattern_candidates))
    with (args.out/'reply_rows_private.jsonl').open('w') as f:
        for row in rows: f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps({'reply_n':len(rows),'sample_person_month_n':len(samples),'out':str(args.out.relative_to(ROOT)),
                      'rules':summary['all_reply_rules'],'probability_expression':summary['probability_expression']['all_valid']},ensure_ascii=False))


if __name__ == '__main__':
    main()
