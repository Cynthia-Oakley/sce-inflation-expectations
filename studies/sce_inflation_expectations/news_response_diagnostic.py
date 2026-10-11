"""Read-only diagnostics of recorded answers. No network, model or decision imports."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import numpy as np

ARMS = ('shared', 'random', 'matched')
MARKERS = {
    'base_effect': r'\bbase effects?\b',
    'easing_language': r'\b(?:ease|easing|moderate|moderation|fade|fading|transitory|temporary|normalization|normalize|normalise)\b',
    'fed': r'\b(?:fed|federal reserve)\b',
    'deflation_language': r'\b(?:deflation|negative inflation|prices fall|prices falling|price decline)\b',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def valid_bins(bins):
    return (len(bins) == 10 and all(type(v) in (int, float) and np.isfinite(v) and 0 <= v <= 100 for v in bins)
            and abs(sum(bins) - 100) <= .5)


def describe(values):
    x = np.asarray([v for v in values if v is not None and np.isfinite(v)], float)
    if not len(x):
        return {'n': 0, 'median': None, 'q25': None, 'q75': None}
    q = np.quantile(x, [.25, .5, .75])
    return {'n': len(x), 'median': float(q[1]), 'q25': float(q[0]), 'q75': float(q[2])}


def bin_stats(bins):
    good = [b for b in bins if valid_bins(b)]
    return {'n_total': len(bins), 'n_valid': len(good),
            'positive_bin_count': describe([sum(v > 0 for v in b) for b in good]),
            'zero_deflation_mass_count': sum(sum(b[5:]) == 0 for b in good),
            'deflation_probability_percent': describe([sum(b[5:]) for b in good]),
            'all_ten_bins_positive_count': sum(all(v > 0 for v in b) for b in good),
            'unique_vectors': len({tuple(b) for b in good})}


def summarize(rows):
    points = [r['point'] for r in rows]
    common = [r for r in rows if r['density_mean'] is not None]
    mode = Counter(points).most_common(1)[0]
    out = {'n_answers': len(rows), 'n_people': len({r['agent_id'] for r in rows}),
           'point_mode_pp': mode[0], 'point_mode_count': mode[1],
           'point_counts': dict(sorted(Counter(points).items())),
           'half_point_grid_count': sum(abs(v * 2 - round(v * 2)) < 1e-9 for v in points),
           'q9': bin_stats([r['bins'] for r in rows]),
           'point_minus_density_mean_pp': describe([r['point'] - r['density_mean'] for r in common]),
           'point_minus_current_CPI_yoy_pp': describe([r['point'] - r['latest_cpi'] for r in rows]),
           'lexical_clues': {}}
    for key in MARKERS:
        matched = [r for r in rows if r['reason_markers'][key]]
        out['lexical_clues'][key] = {
            'in_reason_count': len(matched),
            'in_news_count': sum(r['news_markers'][key] for r in rows),
            'reason_without_same_phrase_in_news_count': sum(not r['news_markers'][key] for r in matched),
            'point_with_phrase_pp': describe([r['point'] for r in matched]),
            'point_without_phrase_pp': describe([r['point'] for r in rows if not r['reason_markers'][key]])}
    out['numeracy_descriptive'] = {
        value: {'n': len(g), 'point_pp': describe([r['point'] for r in g]), 'q9': bin_stats([r['bins'] for r in g])}
        for value in sorted({r['numeracy'] for r in rows})
        if (g := [r for r in rows if r['numeracy'] == value])}
    return out


def run_inventory(root):
    """Inspect recorded month metadata only, never future-month outcomes."""
    files, counts = [], Counter()
    for p in sorted((root/'outputs').rglob('llm_calls.jsonl')):
        months = Counter()
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            value = str(d.get('target_month') or d.get('month') or d.get('case_id') or '')
            match = re.match(r'(20\d{2})-?(0[1-9]|1[0-2])', value)
            month = ''.join(match.groups()) if match else 'unknown'
            months[month] += 1
        counts.update(months)
        files.append({'path': str(p.relative_to(root)), 'sha256': sha(p), 'target_month_counts': dict(months)})
    return {'scope': 'outputs/**/llm_calls.jsonl metadata; no proof of absent external or differently named runs',
            'file_count': len(files), 'counts': dict(counts), 'files': files}


def audit(root, trial, analysis, out):
    root, trial, analysis, out = [Path(p).resolve() for p in (root, trial, analysis, out)]
    if out.exists() or not out.is_relative_to(root / 'outputs'):
        raise ValueError('new local output directory required')
    previous = json.loads((analysis / 'summary.json').read_text())
    # Reuse the already frozen scorer results only if all their source files still match.
    for name, expected in previous['sources'].items():
        if sha(root / name) != expected:
            raise ValueError(f'previous analysis source changed: {name}')
    pairs = json.loads((analysis / 'paired_evaluation_private.json').read_text())
    fit = {(r['month'], r['agent_id'], arm): r[arm] for r in pairs if r['measure'] == 'Q9' for arm in ARMS}
    plan = json.loads((trial / 'trial_manifest.json').read_text())
    truth_file = root / 'data/evaluation/dev_full_20261005T045330Z_947a818f/truth.json'
    truth = {(str(r['date']), f"sce_u{int(r['userid'])}"): r for r in json.loads(truth_file.read_text())['per_person']}
    links = json.loads((trial / 'evaluation_links_private.json').read_text())
    sources = {str(p.relative_to(root)): sha(p) for p in
               [Path(__file__), analysis/'summary.json', analysis/'paired_evaluation_private.json',
                trial/'trial_manifest.json', trial/'evaluation_links_private.json', truth_file]}
    result = {'status': 'completed_offline_diagnostic', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'new_api_calls': 0, 'new_cost_usd': 0, 'source_sha256': sources,
              'lexical_marker_regexes': MARKERS,
              'lexical_limits': 'Exploratory word matches, not semantic labels, attention, causality or model-memory evidence. Absence of a phrase does not mean its economic implication is absent.',
              'quantiles': 'numpy linear descriptive quantiles; not a replacement of the headline scorer/weighted median',
              'repeated_people': 'Each month 48 people answered in 3 arms; pooled 144 answers are not 144 independent people.',
              'months': {}, 'questionnaire_unique_sha256': [], 'case_review_selection': 'one modal/one nonmodal case per month and arm, smallest local alias, not representative narrative sampling'}
    private, reviews, qtexts = [], [], set()
    for month in plan['months']:
        poppath = trial/month/'population.json'
        sources[str(poppath.relative_to(root))] = sha(poppath)
        profiles = {r['agent_id']: r['attributes'] for r in json.loads(poppath.read_text())['personas']}
        month_rows, parts = [], {}
        for arm in ARMS:
            job = next(j for j in plan['jobs'] if j['month'] == month and j['arm'] == arm)
            p = root/'outputs/local_runs'/job['run_id']/'llm_calls.jsonl'
            sources[str(p.relative_to(root))] = sha(p)
            rows = []
            for line in p.read_text().splitlines():
                c = json.loads(line)
                if digest(c['prompt_text']) != c['prompt_sha256'] or digest(c['raw_response_text']) != c['raw_response_sha256']:
                    raise ValueError('raw prompt or response hash failed')
                messages = json.loads(c['prompt_text'])
                if len(messages) != 1 or messages[0]['role'] != 'user':
                    raise ValueError('unreviewed message layout')
                text = messages[0]['content']
                before, question = text.split('Question 1 (point estimate):')
                qtexts.add(question)
                news = before.split('General news you encountered:')[1]
                a = json.loads(c['raw_response_text'])
                bins = [a['q9'][f'bin{i}'] for i in range(1, 11)]
                if not valid_bins(bins):
                    raise ValueError('invalid simulated probability vector')
                latest = float(re.search(r'Consumer Price Index \([^\n]+\): ([+-]?\d+(?:\.\d+)?)% compared', before).group(1))
                row = {'month': month, 'arm': arm, 'agent_id': c['agent_id'], 'point': a['point_pct'],
                       'bins': bins, 'density_mean': fit[(month,c['agent_id'],arm)], 'latest_cpi': latest,
                       'numeracy': profiles[c['agent_id']].get('numeracy','unknown'),
                       'reason': a.get('reason',''), 'prompt_sha256': c['prompt_sha256'],
                       'raw_response_sha256': c['raw_response_sha256'],
                       'reason_markers': {k: bool(re.search(p, a.get('reason',''), re.I)) for k,p in MARKERS.items()},
                       'news_markers': {k: bool(re.search(p, news, re.I)) for k,p in MARKERS.items()}}
                rows.append(row)
            if len(rows) != 48 or len({r['agent_id'] for r in rows}) != 48:
                raise ValueError('incomplete cell')
            parts[arm] = summarize(rows)
            mode = parts[arm]['point_mode_pp']
            for is_mode in (True, False):
                chosen = next((r for r in sorted(rows,key=lambda x:x['agent_id']) if (r['point']==mode)==is_mode),None)
                if chosen:
                    reviews.append({**chosen, 'selection_is_modal': is_mode})
            month_rows += rows
        real_bins = []
        gaps = []
        for link in [r for r in links if r['month']==month]:
            actual = truth[(month,link['source_agent_id'])]
            real_bins.append([actual.get(f'Q9_bin{i}') for i in range(1,11)])
            q8 = next(r['real'] for r in pairs if r['month']==month and r['agent_id']==link['agent_id'] and r['measure']=='Q8_secondary')
            q9 = next(r['real'] for r in pairs if r['month']==month and r['agent_id']==link['agent_id'] and r['measure']=='Q9')
            if q8 is not None and q9 is not None:
                gaps.append(q8-q9)
        result['months'][month] = {'pooled': summarize(month_rows), 'arms': parts,
                                  'same_people_real_q9': bin_stats(real_bins),
                                  'same_people_real_point_minus_density_mean_pp': describe(gaps)}
        private += month_rows
    if len(qtexts) != 1:
        raise ValueError('questionnaire drift')
    result['questionnaire_unique_sha256'] = [digest(next(iter(qtexts)))]
    result['questionnaire_findings'] = {
        'next_12_months_explicit': True, 'zero_probability_already_allowed': True,
        'numeric_point_example_in_schema': False,
        'official_direction_then_magnitude_collapsed': True,
        'negative_bins_instead_of_deflation_wording': True,
        'one_year_probability_and_point_elicited_jointly': True,
        'shelter_incorrectly_named_rent_and_shelter': True,
        'notes': 'No proof of horizon confusion. Do not force point=density mean or eliminate deflation. Shelter index is not tenant-specific rent. Future common correction required.'}
    inventory = run_inventory(root)
    result['run_coverage'] = {k: v for k,v in inventory.items() if k != 'files'}
    out.mkdir(parents=True)
    for name, value in [('summary.json',result), ('diagnostic_rows_private.json',private), ('case_review_private.json',reviews),
                        ('run_coverage_inventory.json',inventory)]:
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return result
