"""Draw one de-identified, observed SCE answer for report v0.3.

Reuses the existing truth and scoring cache. One frozen-kernel fit is run only
to draw the example density and checked against the cached mean and IQR.
No simulation, API call, evaluation rewrite, or respondent ID export.
"""
import hashlib
import json
from pathlib import Path
import runpy

import figures_v02 as shared
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import beta

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "outputs/sce_research_report_figures_20261024_v03"
TRUTH = ROOT / "outputs/sce_monthly_fine_full_truth_20261023_v3/truth_private.json"
CACHE = TRUTH.with_name("scoring_cache_private.json")
FRAME = ROOT / "outputs/sce_prior_preparation_20261013_v4/labeled_reference_private.parquet"
KERNEL = ROOT / "studies/sce_inflation_expectations/scoring/beta_fit_kernel.py"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    shared.OUT = OUT
    shared.setup()
    # Display selection only: first valid, non-open-tail, >=4-bin response in
    # June 2025 with a finite point in (0,10). Not a population representative.
    for offset, row in enumerate(json.loads(TRUTH.read_text())):
        real = row['real']; bins = real['q9_bins']; point = real['q8_point']
        if (row['month'] == 202506 and len(bins) == 10 and sum(v > 0 for v in bins) >= 4
                and bins[0] == bins[-1] == 0 and point is not None and 0 < point < 10):
            break
    else:
        raise ValueError("No observed example met the declared display criteria")
    assert abs(sum(bins) - 100) < 1e-8
    columns = ['date', 'Q8v2part2'] + [f'Q9_bin{i}' for i in range(1, 11)]
    original = pd.read_parquet(FRAME, columns=columns, filters=[('date', '==', 202506)])
    match = np.all(np.isclose(original[columns[2:]].to_numpy(float), bins), axis=1)
    match &= np.isclose(original['Q8v2part2'].to_numpy(float), point)
    assert match.sum() >= 1, "Example must match the observed microdata projection"
    cached = next(item['score'] for item in json.loads(CACHE.read_text()) if item['bins'] == bins)
    fit = runpy.run_path(str(KERNEL))['fit'](bins, variant='relaxed_tail_skip_zero', tail_start=20.0)
    for name in ('mean', 'iqr'):
        assert np.isclose(fit[name], cached[name], atol=1e-10, rtol=0)
        assert np.isclose(fit[name], real[f'q9_{name}'], atol=1e-10, rtol=0)
    a, b, left, right = fit['params']
    p = np.array(bins[::-1])
    fig = plt.figure(figsize=(9.5, 4.15))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, .24], hspace=.85, wspace=.30)
    ax = fig.add_subplot(gs[0, 0]); density = fig.add_subplot(gs[0, 1])
    labels = ['≤−12', '−12至−8', '−8至−4', '−4至−2', '−2至0', '0至2', '2至4', '4至8', '8至12', '≥12']
    ax.bar(range(10), p, color=[shared.C['orange'] if v else '#d5d5d5' for v in p], width=.74)
    for i, value in enumerate(p):
        if value: ax.text(i, value + .9, f'{value:g}', ha='center', fontsize=12)
    ax.set_xticks(range(10), labels, rotation=55, ha='right', fontsize=11.5)
    ax.set_ylim(0, 49); ax.set_ylabel('回答概率（%）', fontsize=13)
    ax.set_xlabel('未来12个月通胀率区间（%）', fontsize=12.5)
    ax.set_title('实际Q9回答：十档合计100%', fontsize=14)
    x = np.linspace(left, right, 801)
    y = beta.pdf((x - left) / (right - left), a, b) / (right - left)
    density.plot(x, y, color=shared.C['blue'], linewidth=2)
    density.fill_between(x, y, color=shared.C['blue'], alpha=.12)
    density.axvline(fit['mean'], color=shared.C['orange'], linestyle='--', linewidth=1.4)
    density.text(fit['mean'] + .55, max(y)*.8, f"密度均值\n{fit['mean']:.2f}%", color=shared.C['orange'], fontsize=13)
    density.set_xlabel('未来12个月通胀率（%）', fontsize=12.5)
    density.set_ylabel('概率密度（每百分点）', fontsize=12)
    density.set_title('同一答卷：按冻结方法拟合密度', fontsize=14)
    density.set_ylim(0, max(y)*1.15)
    bottom = fig.add_subplot(gs[1, :]); bottom.axis('off')
    bottom.text(0, .82, f"同一人的Q8点预期：{point:.1f}%    Q9密度均值：{fit['mean']:.2f}%    个人密度IQR：{fit['iqr']:.2f}pp", fontsize=13)
    bottom.text(0, .04, '来源：SCE 2025年6月公开微观答卷；单个受访者示例，不代表当月总体。', fontsize=12, color=shared.C['muted'])
    shared.save(fig, 'q9_observed_example')
    evidence = {
        'observed_not_fictional': True, 'month': 202506,
        'q8_point_pct': float(point), 'q9_probabilities_ascending_pct': p.tolist(),
        'q9_probabilities_source_order_pct': bins,
        'density_mean_pct': fit['mean'], 'density_iqr_pp': fit['iqr'],
        'density_family': 'generalized_beta', 'density_parameters': fit['params'],
        'selection': 'First valid June-2025 selected-truth record with >=4 occupied bins, no open-tail mass, and Q8 in (0,10); presentation only.',
        'source_record_offset_zero_based': offset,
        'matching_microdata_records': int(match.sum()),
        'source_hashes': {str(path.relative_to(ROOT)): sha(path) for path in (TRUTH, CACHE, FRAME, KERNEL)},
        'raw_ids_exported': False, 'weights_or_demographics_exported': False,
        'population_representativeness_claimed': False,
        'new_api_calls': 0, 'illustrative_density_fits': 1,
        'cached_mean_iqr_unchanged': True, 'evaluation_files_modified': False,
    }
    (OUT / 'figure_data.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: evidence[k] for k in ('month', 'q8_point_pct', 'q9_probabilities_ascending_pct', 'density_mean_pct', 'density_iqr_pp')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
