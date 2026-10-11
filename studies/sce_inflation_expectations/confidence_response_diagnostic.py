"""Offline description of frozen confidence answers; no providers or API calls."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

import numpy as np
import pandas as pd

ARMS = ('no_added_confidence', 'national_confidence')
SOURCES = ('real',) + ARMS


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite(x):
    return isinstance(x, (int, float)) and np.isfinite(x)


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def diagnose(root, trial, analysis, truth, out):
    root, trial, analysis, truth, out = [Path(p).resolve() for p in (root, trial, analysis, truth, out)]
    if out.exists() or not out.is_relative_to(root / 'outputs'):
        raise ValueError('new output directory required')
    summary = json.loads((analysis / 'summary.json').read_text())
    plan = json.loads((trial / 'trial_manifest.json').read_text())
    private = json.loads((analysis / 'paired_evaluation_private.json').read_text())
    links = json.loads((trial / 'evaluation_links_private.json').read_text())
    rows = pd.read_parquet(truth / 'raw_reference.parquet').to_dict('records')
    reference = {(str(int(r['date'])), f"sce_u{int(r['userid'])}"): r for r in rows}
    linked = {(r['month'], r['agent_id']): r['source_agent_id'] for r in links}
    indexed = {(r['month'], r['repeat'], r['measure'], r['agent_id']): r for r in private}
    protected_path = root / 'docs/sources/sol_handoff_protected_files_20261010.json'
    protected = json.loads(protected_path.read_text())['files_sha256']
    if any(sha(root / p) != expected for p, expected in protected.items()):
        raise ValueError('protected file drift')
    sources = {str(p.relative_to(root)): sha(p) for p in (
        analysis / 'summary.json', analysis / 'paired_evaluation_private.json', trial / 'trial_manifest.json',
        trial / 'evaluation_links_private.json', truth / 'raw_reference.parquet', Path(__file__))}
    cells, reasons, examples = [], Counter(), []
    for month in plan['months']:
        labels = json.loads((trial / month / 'simulation_national_confidence.json').read_text())['decision_args']['confidence_bundle']['labels']
        for repeat in (1, 2):
            q9rows = [r for r in private if r['month'] == month and r['repeat'] == repeat and r['measure'] == 'Q9'
                      and all(finite(r[k]) for k in SOURCES)]
            ids = sorted(r['agent_id'] for r in q9rows)
            answer = {}
            for arm in ARMS:
                job = next(j for j in plan['jobs'] if (j['month'], j['repeat'], j['arm']) == (month, repeat, arm))
                path = root / 'outputs/local_runs' / job['run_id'] / 'llm_calls.jsonl'
                calls = [json.loads(line) for line in path.read_text().splitlines()]
                audit = next(r for r in summary['runs'] if (r['month'], r['repeat'], r['arm']) == (month, repeat, arm))
                if sha(path) != audit['llm_calls_sha256'] or len(calls) != 48:
                    raise ValueError('actual answer source drift')
                sources[str(path.relative_to(root))] = sha(path)
                answer[arm] = {c['agent_id']: json.loads(c['raw_response_text']) for c in calls if c['agent_id'] in ids}
                for value in answer[arm].values():
                    text = value.get('reason', '').lower()
                    for name, pattern in {
                        'easing_or_moderation': r'\b(?:eas(?:e|es|ing|ed)|cool\w*|declin\w*|moderat\w*|disinfl\w*|base effects?)\b',
                        'persistence': r'\b(?:persist\w*|sticky|remain\w*|stay\w*|stubborn)\b',
                        'policy_or_fed': r'\b(?:fed|policy|tighten\w*|interest rates?)\b',
                    }.items():
                        reasons[(month, arm, name)] += bool(re.search(pattern, text))
            result = {'month': month, 'repeat': repeat, 'n_common_Q9': len(ids), 'sources': {},
                      'interval': summary['months'][month]['repeats'][str(repeat)]['Q9']['confidence_minus_no_confidence']['median_absolute_error_pp']}
            for kind in SOURCES:
                bins, gaps = [], []
                for aid in ids:
                    r = reference[(month, linked[(month, aid)])]
                    probs = [r[f'Q9_bin{i}'] for i in range(1, 11)] if kind == 'real' else [answer[kind][aid]['q9'][f'bin{i}'] for i in range(1, 11)]
                    if not all(finite(x) and 0 <= x <= 100 for x in probs) or abs(sum(probs) - 100) > .5:
                        raise ValueError('unexpected invalid common raw bins')
                    bins.append(probs)
                    point, center = indexed[(month, repeat, 'Q8', aid)][kind], indexed[(month, repeat, 'Q9', aid)][kind]
                    if finite(point) and finite(center):
                        gaps.append(point - center)
                a = np.asarray(bins)
                cell = summary['months'][month]['repeats'][str(repeat)]
                result['sources'][kind] = {
                    'mean_raw_bin_probability_pct': a.mean(axis=0).tolist(),
                    'nonzero_bins_median': float(np.median((a > 0).sum(axis=1))),
                    'zero_deflation_share_pct': float(np.mean(a[:, 5:].sum(axis=1) == 0) * 100),
                    'raw_deflation_median_pct': float(np.median(a[:, 5:].sum(axis=1))),
                    'raw_deflation_mean_pct': float(np.mean(a[:, 5:].sum(axis=1))),
                    'raw_at_least_8pct_mean_probability_pct': float(np.mean(a[:, :2].sum(axis=1))),
                    'point_minus_Q9_center_median_pp': float(np.median(gaps)),
                    'point_vs_Q9_gap_n': len(gaps),
                    'cross_person_center_IQR_pp': (cell['Q9']['real'] if kind == 'real' else cell['Q9']['arms'][kind]['distribution'])['cross_person_iqr_pp'],
                    'typical_person_density_IQR_pp': (cell['personal_uncertainty']['real'] if kind == 'real' else cell['personal_uncertainty']['arms'][kind]['distribution'])['median_pp'],
                    'cross_person_uncertainty_IQR_pp': (cell['personal_uncertainty']['real'] if kind == 'real' else cell['personal_uncertainty']['arms'][kind]['distribution'])['cross_person_iqr_pp'],
                }
            shifts = defaultdict(list)
            for r in q9rows:
                shifts[labels[r['agent_id']]].append(r[ARMS[1]] - r[ARMS[0]])
            result['synthetic_label_response_shift_exploratory'] = {
                k: {'n': len(v), 'mean_pp': float(np.mean(v)), 'median_pp': float(np.median(v))} for k, v in shifts.items()}
            # A fixed, deterministic example; no real ID, persona, or real response is published.
            if month == '202403' and repeat == 1:
                aid = ids[0]
                examples.append({'selection': 'first common valid anonymous case in sorted order, March 2024 generation 1',
                                 'point_pct': answer[ARMS[1]][aid]['point_pct'],
                                 'Q9_center_pp': indexed[(month, repeat, 'Q9', aid)][ARMS[1]],
                                 'raw_probabilities': answer[ARMS[1]][aid]['q9'], 'reason': answer[ARMS[1]][aid]['reason']})
            cells.append(result)
    avg = {kind: {k: float(np.mean([c['sources'][kind][k] for c in cells])) for k in (
        'nonzero_bins_median', 'zero_deflation_share_pct', 'raw_deflation_median_pct', 'raw_deflation_mean_pct',
        'cross_person_center_IQR_pp', 'typical_person_density_IQR_pp', 'cross_person_uncertainty_IQR_pp',
        'point_minus_Q9_center_median_pp')} for kind in SOURCES}
    result = {'status': 'offline_frozen_response_description', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'new_API_calls': 0, 'new_API_cost_usd': 0, 'sources_sha256': sources, 'cells': cells,
              'equal_cell_average': avg, 'anonymous_model_example': examples,
              'reason_keyword_counts_exploratory': [dict(month=m, arm=a, marker=k, count=n) for (m, a, k), n in reasons.items()],
              'limits': ['Unweighted selected common samples; averages across eight cells, not nationally representative.',
                         'Two generations of the same people are not twice as many respondents.',
                         'Reason strings and synthetic-label associations are clues, not causal explanations.',
                         'Q9 continuous mean/IQR use the frozen approximate scorer; raw bins have no fitting dependency.',
                         'Averaged individual probability vectors are not the distribution of personal expectation centers.'],
              'protected_files_unchanged': len(protected)}
    out.mkdir()
    dump(out / 'summary.json', result)
    plot(result, out)
    return result


def plot(result, out):
    os.environ.setdefault('MPLCONFIGDIR', str(out / 'matplotlib_cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': ['Arial Unicode MS', 'PingFang SC', 'sans-serif'], 'axes.unicode_minus': False,
                         'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    colors = ('#333333', '#8a9298', '#286c68')
    names = ('真人同样本', '不加信心', '加合成央行信心')
    months = list(dict.fromkeys(c['month'] for c in result['cells']))
    x = np.arange(len(months))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    for kind, label, color, offset in zip(SOURCES, names, colors, (-.24, 0, .24)):
        for ax, key in zip(axes, ('cross_person_center_IQR_pp', 'typical_person_density_IQR_pp')):
            vals = [np.mean([c['sources'][kind][key] for c in result['cells'] if c['month'] == m]) for m in months]
            ax.bar(x + offset, vals, width=.23, color=color, label=label)
    for ax in axes:
        ax.set_xticks(x, [m[:4] + '-' + m[4:] for m in months]); ax.legend(fontsize=9)
        ax.set_xlabel('调查月（两次生成平均，双方共同有效样本）'); ax.set_ylabel('中间50%跨度（个百分点）')
        ax.grid(axis='y', alpha=.15)
    axes[0].set_title('不同人想法的差异：模型远小于真人')
    axes[1].set_title('每个人的不确定性：并非所有月都过宽')
    fig.savefig(out / 'two_kinds_of_spread.png', dpi=160); plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True)
    labels = ('≥12', '8–12', '4–8', '2–4', '0–2', '−2–0', '−4–−2', '−8–−4', '−12–−8', '≤−12')
    for ax, month in zip(axes.flat, months):
        for kind, label, color in zip(SOURCES, names, colors):
            vals = np.mean([c['sources'][kind]['mean_raw_bin_probability_pct'] for c in result['cells'] if c['month'] == month], axis=0)
            ax.plot(np.arange(10), vals, marker='o', color=color, label=label)
        ax.set_xticks(np.arange(10), labels, rotation=35, ha='right'); ax.set_ylabel('平均分配概率（%）')
        ax.set_xlabel('未来12个月的通胀区间（%），左上涨 / 右下跌'); ax.set_title(month[:4] + '-' + month[4:])
        ax.legend(fontsize=8); ax.grid(axis='y', alpha=.15)
    fig.suptitle('原始Q9十档：这是个人概率的平均，不是人群预期中心的分布', fontsize=12)
    fig.savefig(out / 'raw_probability_profiles.png', dpi=160); plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 4.8), constrained_layout=True)
    for i, cell in enumerate(result['cells']):
        change = cell['interval']; lo, hi = change['paired_person_bootstrap_95_interval_pp']
        value = change['change_pp']; ax.hlines(i, lo, hi, color='#286c68', linewidth=2)
        ax.scatter(value, i, color='#286c68', zorder=3)
    ax.axvline(0, color='#555555', linewidth=1, linestyle='--')
    ax.set_yticks(np.arange(8), [c['month'][:4]+'-'+c['month'][4:]+' / 第'+str(c['repeat'])+'次生成' for c in result['cells']])
    ax.invert_yaxis(); ax.set_xlabel('加入信心后的中心绝对误差 − 不加信心的误差（个百分点）；负值为改善')
    ax.set_title('点为本次观察；线为人员配对重抽样95%区间（7/8跨过零）')
    fig.savefig(out / 'error_change_intervals.png', dpi=160); plt.close(fig)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('trial', 'analysis', 'truth', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    a = parser.parse_args(argv)
    r = diagnose(Path(__file__).resolve().parents[2], a.trial, a.analysis, a.truth, a.out)
    print(json.dumps({'status': r['status'], 'averages': r['equal_cell_average'], 'new_API_calls': 0}))
