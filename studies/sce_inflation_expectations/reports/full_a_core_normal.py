"""Build a read-only HTML report for the completed Core + Normal A82 result."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

DEFAULT_EVALUATION = ROOT / 'outputs/sce_full_a_core_normal_evaluation_20261026_v3'
DEFAULT_REPORT = ROOT / 'docs/workstreams/20261026_core_normal_full_a/results_v1'
TAUS = ('0', '8', '24')
EXPECTED_MONTHS = tuple(
    f'{2019 + index // 12}{index % 12 + 1:02d}' for index in range(82)
)
BLUE, ORANGE, GRAY, INK = '#1764AB', '#DC6B19', '#858B92', '#222222'


def _read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def _sha(path: Path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path):
    with path.open(newline='', encoding='utf-8-sig') as handle:
        return list(csv.DictReader(handle))


def _as_int(value, label):
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid integer in {label}: {value!r}') from exc
    return result


def _as_float(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid number in {label}: {value!r}') from exc
    if not math.isfinite(result):
        raise ValueError(f'Nonfinite number in {label}')
    return result


def _fmt(value, digits=3):
    return f'{_as_float(value, "display value"):.{digits}f}'


def _signed(value, digits=3):
    return f'{_as_float(value, "display delta"):+.{digits}f}'


def _month_label(month):
    value = str(month).replace('-', '')
    if len(value) != 6 or not value.isdigit():
        raise ValueError(f'Invalid month in public series: {month!r}')
    return value[:4] + '-' + value[4:]


def _load(evaluation: Path):
    evaluation = evaluation.resolve()
    outputs = (ROOT / 'outputs').resolve()
    if not evaluation.is_relative_to(outputs) or not evaluation.is_dir():
        raise ValueError('Evaluation input must be a completed directory under outputs/')
    summary_path = evaluation / 'summary.json'
    monthly_path = evaluation / 'monthly_public.csv'
    yearly_path = evaluation / 'yearly.csv'
    manifest_path = evaluation / 'manifest.json'
    manifest = _read_json(manifest_path)
    summary = _read_json(summary_path)
    if summary.get('status') != 'completed_full_a_core_normal_evaluation':
        raise ValueError('Completed Core + Normal evaluation required')
    if summary.get('new_api_calls') != 0 or summary.get('new_q9_density_fits') != 0:
        raise ValueError('Report requires zero new API calls and zero Q9 density fits')
    files = manifest.get('files_sha256', {})
    for path in (summary_path, monthly_path, yearly_path):
        expected = files.get(path.name)
        if not expected or _sha(path) != expected:
            raise ValueError('Evaluation artifact missing from or changed against manifest: ' + path.name)

    tau = str(_as_int(summary.get('selected_tau'), 'selected_tau'))
    if tau not in TAUS:
        raise ValueError('Selected tau is outside the registered candidates')
    monthly = _read_csv(monthly_path)
    months = tuple(str(row.get('month', '')).replace('-', '') for row in monthly)
    if months != EXPECTED_MONTHS or len(monthly) != 82:
        raise ValueError('Public monthly readout must contain the fixed 82-month order')
    if summary.get('month_count') != 82 or summary.get('selected_tau') != int(tau):
        raise ValueError('Summary month count or selected tau does not match the frozen scope')
    for row in monthly:
        if _as_int(row.get('selected_tau'), 'monthly selected_tau') != int(tau):
            raise ValueError('Monthly tau differs from the sealed selection')
        for field in ('before_model_pp', 'expanded_model_pp', 'truth_pp', 'baseline_pp',
                      'before_q9_w1_pp', 'expanded_q9_w1_pp', 'truth_q9_iqr_pp',
                      'before_q9_iqr_pp', 'expanded_q9_iqr_pp'):
            _as_float(row.get(field), field)

    yearly = _read_csv(yearly_path)
    if [str(row.get('year')) for row in yearly] != [str(year) for year in range(2019, 2026)]:
        raise ValueError('Yearly readout must cover 2019 through 2025')
    for row in yearly:
        for field in ('before_national_mae_pp', 'expanded_national_mae_pp',
                      'anchor_national_mae_pp'):
            _as_float(row.get(field), field)

    frame_n = sum(_as_int(row['target_frame_n'], 'target_frame_n') for row in monthly)
    core_n = sum(_as_int(row['core_n'], 'core_n') for row in monthly)
    normal_n = sum(_as_int(row['normal_n'], 'normal_n') for row in monthly)
    weighted_n = sum(_as_int(row['weighted_frame_n'], 'weighted_frame_n') for row in monthly)
    missing_weight_n = sum(_as_int(row['missing_weight_n'], 'missing_weight_n') for row in monthly)
    if frame_n != 98382 or core_n != 41970 or normal_n != frame_n - core_n:
        raise ValueError('Core + Normal frame counts differ from the registered 98,382 / 41,970 scope')
    if frame_n != core_n + normal_n or weighted_n + missing_weight_n != frame_n:
        raise ValueError('Frame, Core/Normal, or weight-missing totals do not conserve')
    if summary.get('target_frame_n_total') != frame_n:
        raise ValueError('Summary population frame total differs from monthly public rows')
    if summary.get('weighted_frame_n_total') != weighted_n:
        raise ValueError('Summary positive-weight total differs from monthly public rows')
    if summary.get('missing_weight_n_total') != missing_weight_n:
        raise ValueError('Summary missing-weight total differs from monthly public rows')

    return dict(evaluation=evaluation, summary=summary, monthly=monthly, yearly=yearly,
                tau=tau, frame_n=frame_n, core_n=core_n, normal_n=normal_n,
                weighted_n=weighted_n, missing_weight_n=missing_weight_n,
                frame_min=min(_as_int(row['target_frame_n'], 'target_frame_n') for row in monthly),
                frame_max=max(_as_int(row['target_frame_n'], 'target_frame_n') for row in monthly),
                source_hashes={path.name: _sha(path) for path in
                               (manifest_path, summary_path, monthly_path, yearly_path)})


def _style_matplotlib():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    plt.rcParams.update({
        'font.family': 'serif',
        'font.serif': ['Times New Roman', 'Kaiti SC', 'STKaiti', 'KaiTi', 'DejaVu Serif'],
        'font.size': 10,
        'axes.spines.top': False,
        'axes.spines.right': False,
        'axes.labelcolor': INK,
        'text.color': INK,
        'xtick.color': INK,
        'ytick.color': INK,
        'figure.facecolor': 'white',
        'axes.facecolor': 'white',
        'savefig.facecolor': 'white',
    })
    # Use the project's local Kaiti font when installed; keep it in place and
    # do not copy or package the font with the report.
    font = ROOT / 'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.is_file():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=str(font)).get_name()
    return plt


def _charts(data, out: Path):
    import numpy as np

    plt = _style_matplotlib()
    summary, monthly, yearly, tau = (
        data['summary'], data['monthly'], data['yearly'], data['tau'])
    figure_dir = out / 'figures'
    figure_dir.mkdir()

    def save(fig, name):
        fig.tight_layout()
        fig.savefig(figure_dir / name, dpi=180, bbox_inches='tight')
        plt.close(fig)

    labels = [_month_label(row['month']) for row in monthly]
    x = np.arange(len(monthly))
    series = [
        ('truth_pp', '公开SCE全国真值', INK, 2.1, '-'),
        ('before_model_pp', '原A82 T0 Core（约512人/月）', BLUE, 1.7, '-'),
        ('expanded_model_pp', f'Core＋Normal，τ={tau}', ORANGE, 2.0, '-'),
        ('baseline_pp', '公开历史基线', GRAY, 1.5, '--'),
    ]
    fig, ax = plt.subplots(figsize=(12.2, 4.8))
    for key, label, color, width, linestyle in series:
        ax.plot(x, [_as_float(row[key], key) for row in monthly], label=label,
                color=color, lw=width, ls=linestyle)
    ax.axvspan(24 - .5, 35 + .5, color=ORANGE, alpha=.09, zorder=0)
    ax.set_title('Q9全国中位数：Core＋Normal扩展与原T0、真人及历史基线', loc='left', fontsize=14)
    ax.set_ylabel('一年期通胀预期（%）')
    ticks = list(range(0, 82, 12))
    ax.set_xticks(ticks, [labels[index] for index in ticks])
    ax.legend(ncol=2, frameon=False, loc='upper left')
    ax.grid(axis='y', color='#D8DCE0', lw=.7, alpha=.8)
    ax.text(.995, .02, '浅橙区域：2021年', transform=ax.transAxes,
            ha='right', va='bottom', color='#7C4A24', fontsize=9)
    save(fig, 'q9_levels_all_82.png')

    selected_2021 = [row for row in monthly if str(row['month']).startswith('2021')]
    xx = np.arange(len(selected_2021))
    fig, ax = plt.subplots(figsize=(10.5, 4.5))
    for key, label, color, width, linestyle in series:
        ax.plot(xx, [_as_float(row[key], key) for row in selected_2021],
                label=label, color=color, lw=width, ls=linestyle, marker='o', ms=3.3)
    ax.set_title('2021年Q9全国中位数：逐月细看', loc='left', fontsize=14)
    ax.set_ylabel('一年期通胀预期（%）')
    ax.set_xlabel('2021年月份')
    ax.set_xticks(xx, [str(row['month'])[-2:] for row in selected_2021])
    ax.legend(ncol=2, frameon=False, loc='upper left')
    ax.grid(axis='y', color='#D8DCE0', lw=.7, alpha=.8)
    save(fig, 'q9_levels_2021.png')

    nat = summary['national']
    before_all = nat['scenarios']['before_t0']['all_period']['mae_pp']
    chosen_all = nat['scenarios'][f'tau_{tau}']['all_period']['mae_pp']
    anchor_all = nat['persistence_anchor']['all_period']['mae_pp']
    years = [int(row['year']) for row in yearly]
    bx = np.arange(len(yearly))
    width = .25
    fig, ax = plt.subplots(figsize=(11.8, 4.9))
    plotted = []
    for offset, key, label, color in (
            (-width, 'before_national_mae_pp', '原A82 T0 Core', BLUE),
            (0, 'expanded_national_mae_pp', f'Core＋Normal τ={tau}', ORANGE),
            (width, 'anchor_national_mae_pp', '公开历史基线', GRAY)):
        values = [_as_float(row[key], key) for row in yearly]
        bars = ax.bar(bx + offset, values, width=width, label=label, color=color)
        plotted.append((bars, values))
    for bars, values in plotted:
        ax.bar_label(bars, labels=[f'{value:.2f}' for value in values],
                     fontsize=8, padding=2, rotation=0)
    ax.set_title('逐年Q9全国中位数 MAE：扩展前、选定τ与公开历史基线', loc='left', fontsize=14)
    ax.set_ylabel('MAE（pp；越低越好）')
    ax.set_xticks(bx, [str(year) + ('*' if year == 2025 else '') for year in years])
    ax.legend(ncol=3, frameon=False, loc='upper left')
    ax.grid(axis='y', color='#D8DCE0', lw=.7, alpha=.8)
    ax.margins(y=.20)
    save(fig, 'q9_yearly_mae.png')

    distribution = summary['full_wave_distribution']['q9_mean']
    before = distribution['before_t0']
    chosen = distribution['expanded_by_tau'][tau]
    observed_iqr = distribution['observed_distribution']['mean_iqr_pp']
    before_w1 = before['mean_w1_pp']
    chosen_w1 = chosen['mean_w1_pp']
    before_iqr = before['mean_predicted_iqr_pp']
    chosen_iqr = chosen['mean_predicted_iqr_pp']
    before_iqr_error = before['mean_iqr_error_pp']
    chosen_iqr_error = chosen['mean_iqr_error_pp']
    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.5))
    axes[0].bar([0, 1], [before_w1, chosen_w1], width=.58,
                color=[BLUE, ORANGE])
    axes[0].set_xticks([0, 1], ['原A82 T0 Core', f'Core＋Normal τ={tau}'])
    axes[0].set_ylabel('月平均 W1（pp；越低越好）')
    axes[0].set_title('跨人Q9分布距离')
    for index, value in enumerate((before_w1, chosen_w1)):
        axes[0].text(index, value, f'{value:.3f}', ha='center', va='bottom', fontsize=10)
    axes[0].grid(axis='y', color='#D8DCE0', lw=.7, alpha=.8)
    vals = [observed_iqr, before_iqr, chosen_iqr]
    names = ['真人全波次', '原A82 T0 Core', f'Core＋Normal τ={tau}']
    cols = [INK, BLUE, ORANGE]
    bars = axes[1].bar(np.arange(3), vals, width=.62, color=cols)
    axes[1].bar_label(bars, labels=[f'{value:.3f}' for value in vals],
                      fontsize=9, padding=3)
    axes[1].set_xticks(np.arange(3), names, rotation=10, ha='right')
    axes[1].set_ylabel('Q9跨人 IQR（pp）')
    axes[1].set_title('分布宽度：真人IQR作同波次参照')
    axes[1].grid(axis='y', color='#D8DCE0', lw=.7, alpha=.8)
    axes[1].text(.98, .96, f'月均绝对IQR差：{before_iqr_error:.3f} → {chosen_iqr_error:.3f} pp',
                 transform=axes[1].transAxes, ha='right', va='top', fontsize=9,
                 bbox=dict(facecolor='white', edgecolor='#D8DCE0', pad=4))
    fig.suptitle('同一全波次真人支持下的Q9 W1与IQR（2019-01—2025-10，82月等权）',
                 x=.02, ha='left', fontsize=14)
    save(fig, 'q9_w1_iqr_full_wave.png')

    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.2))
    tau_values = [int(item) for item in TAUS]
    national_mae = [nat['scenarios'][f'tau_{item}']['all_period']['mae_pp'] for item in TAUS]
    w1_values = [distribution['expanded_by_tau'][item]['mean_w1_pp'] for item in TAUS]
    axes[0].plot(tau_values, national_mae, color=ORANGE, marker='o', lw=2,
                 label='公开全国目标 MAE')
    axes[0].axhline(before_all, color=BLUE, ls='--', lw=1.4, label='原A82 T0 Core')
    axes[0].axhline(anchor_all, color=GRAY, ls=':', lw=1.7, label='公开历史基线')
    axes[0].scatter([int(tau)], [chosen_all], s=75, facecolors='none',
                    edgecolors=ORANGE, linewidths=1.8, zorder=4)
    for xv, value in zip(tau_values, national_mae):
        axes[0].annotate(f'{value:.3f}', (xv, value), xytext=(0, 8),
                         textcoords='offset points', ha='center', fontsize=8)
    axes[0].set_title('全国Q9 MAE')
    axes[0].set_ylabel('MAE（pp）')
    axes[0].set_xlabel('收缩参数 τ')
    axes[0].set_xticks(tau_values)
    axes[0].legend(frameon=False, fontsize=8)
    axes[0].grid(axis='y', color='#D8DCE0', lw=.7, alpha=.8)
    axes[1].plot(tau_values, w1_values, color=ORANGE, marker='o', lw=2,
                 label='全波次真人 Q9 W1')
    axes[1].axhline(before_w1, color=BLUE, ls='--', lw=1.4, label='原A82 T0 Core')
    axes[1].scatter([int(tau)], [chosen_w1], s=75, facecolors='none',
                    edgecolors=ORANGE, linewidths=1.8, zorder=4)
    for xv, value in zip(tau_values, w1_values):
        axes[1].annotate(f'{value:.3f}', (xv, value), xytext=(0, 8),
                         textcoords='offset points', ha='center', fontsize=8)
    axes[1].set_title('跨人Q9 W1')
    axes[1].set_ylabel('月平均 W1（pp）')
    axes[1].set_xlabel('收缩参数 τ')
    axes[1].set_xticks(tau_values)
    axes[1].set_ylim(0, max([before_w1] + w1_values) * 1.14)
    axes[1].legend(frameon=False, fontsize=8)
    axes[1].grid(axis='y', color='#D8DCE0', lw=.7, alpha=.8)
    fig.suptitle('τ敏感性：展示三个预设值，圆圈为早期LLM留出所选值',
                 x=.02, ha='left', fontsize=14)
    save(fig, 'tau_sensitivity.png')


def _readout(data):
    summary, tau = data['summary'], data['tau']
    national = summary['national']
    before = national['scenarios']['before_t0']
    expanded = national['scenarios'][f'tau_{tau}']
    anchor = national['persistence_anchor']
    full = summary['full_wave_distribution']['q9_mean']
    before_iqr = full['before_t0']['mean_iqr_error_pp']
    after_iqr = full['expanded_by_tau'][tau]['mean_iqr_error_pp']
    selection = summary.get('tau_selection_record', {})
    candidates = selection.get('candidates', [])
    if (selection.get('status') != 'frozen_by_early_model_only_holdout'
            or selection.get('selected_tau') != int(tau)
            or {str(row.get('tau')) for row in candidates} != set(TAUS)):
        raise ValueError('Frozen model-only tau selection record missing or inconsistent')
    selected_definition = selection.get('status', '')
    selection_values = [dict(
        tau=_as_int(row['tau'], 'tau_selection_record.tau'),
        validation_cells=_as_int(row['validation_cells'], 'tau_selection_record.validation_cells'),
        center_mae_pp=_as_float(row['center_mae_pp'], 'tau_selection_record.center_mae_pp'),
        w1_pp=_as_float(row['w1_pp'], 'tau_selection_record.w1_pp'),
        iqr_mae_pp=_as_float(row['iqr_mae_pp'], 'tau_selection_record.iqr_mae_pp'))
        for row in sorted(candidates, key=lambda item: int(item['tau']))]
    summary_months = summary.get('monthly', [])
    if len(summary_months) != 82:
        raise ValueError('Expected 82 monthly donor-support audit rows')
    q9_support = [row['quality']['selected_tau_support']['q9'] for row in summary_months]
    q9_parent_pool_share = sum(row['parent_population_fraction'] for row in q9_support) / len(q9_support)
    q9_unsupported_local_share = sum(row['unsupported_local_population_fraction']
                                     for row in q9_support) / len(q9_support)
    prediction_quality = summary.get('prediction_quality', {})
    combinations = summary['national']['chronological_combinations']
    selected_combination = combinations[f'tau_{tau}']
    before_combination = combinations['before_t0']
    return dict(
        status=summary['status'], selected_tau=int(tau),
        selected_tau_source=selected_definition,
        national_mae_before_pp=before['all_period']['mae_pp'],
        national_mae_expanded_pp=expanded['all_period']['mae_pp'],
        national_mae_change_pp=expanded['all_period']['mae_pp'] - before['all_period']['mae_pp'],
        national_mae_anchor_pp=anchor['all_period']['mae_pp'],
        national_mae_2021_before_pp=before['by_year']['2021']['mae_pp'],
        national_mae_2021_expanded_pp=expanded['by_year']['2021']['mae_pp'],
        national_mae_2021_anchor_pp=anchor['by_year']['2021']['mae_pp'],
        full_wave_q9_median_mae_before_pp=full['before_t0']['median_mae_pp'],
        full_wave_q9_median_mae_expanded_pp=full['expanded_by_tau'][tau]['median_mae_pp'],
        full_wave_q9_w1_before_pp=full['before_t0']['mean_w1_pp'],
        full_wave_q9_w1_expanded_pp=full['expanded_by_tau'][tau]['mean_w1_pp'],
        full_wave_q9_iqr_error_before_pp=before_iqr,
        full_wave_q9_iqr_error_expanded_pp=after_iqr,
        full_wave_q9_iqr_human_mean_pp=full['observed_distribution']['mean_iqr_pp'],
        full_wave_q9_iqr_before_mean_pp=full['before_t0']['mean_predicted_iqr_pp'],
        full_wave_q9_iqr_expanded_mean_pp=full['expanded_by_tau'][tau]['mean_predicted_iqr_pp'],
        frame_person_months=data['frame_n'], core_person_months=data['core_n'],
        normal_person_months=data['normal_n'], weighted_frame_person_months=data['weighted_n'],
        missing_weight_person_months=data['missing_weight_n'],
        monthly_frame_min=data['frame_min'], monthly_frame_max=data['frame_max'],
        month_count=82, new_api_calls=0, new_q9_density_fits=0,
        q9_model_donors_total=summary.get('valid_q9_model_donors_total'),
        q8_model_donors_total=summary.get('valid_q8_model_donors_total'),
        q9_unfittable_model_output=prediction_quality.get('q9_unfittable_model_output'),
        q9_not_model_output=prediction_quality.get('q9_not_model_output'),
        q9_parent_pool_share_equal_month=q9_parent_pool_share,
        q9_unsupported_local_share_equal_month=q9_unsupported_local_share,
        excluded_personal_date_core_to_normal_total=
            summary.get('excluded_personal_date_Core_now_statistical_Normal_total'),
        late_34_mae_before_pp=before['late_34']['mae_pp'],
        late_34_mae_expanded_pp=expanded['late_34']['mae_pp'],
        late_34_mae_anchor_pp=anchor['late_34']['mae_pp'],
        late_34_mse_blend_weight_selected=selected_combination['mse']['simulation_weight'],
        late_34_mse_blend_mae_selected=selected_combination['mse']['evaluation']['mae_pp'],
        late_34_mse_blend_weight_before=before_combination['mse']['simulation_weight'],
        late_34_mse_blend_mae_before=before_combination['mse']['evaluation']['mae_pp'],
        late_34_mae_blend_weight_selected=selected_combination['mae']['simulation_weight'],
        limits=summary.get('limits', []),
        tau_selection_candidates=selection_values,
        tau_selection_development=selection.get('development'),
        tau_selection_late_period_used=selection.get('late_period_used_for_selection'),
        source_sha256=data['source_hashes'])


def _html(data, readout):
    import html

    tau = data['tau']
    delta = readout['national_mae_change_pp']
    if delta < -1e-12:
        direction = '下降'
    elif delta > 1e-12:
        direction = '上升'
    else:
        direction = '持平'
    headline = (f"Core＋Normal后全期Q9 MAE{direction} {_fmt(abs(delta))} pp："
                f"{_fmt(readout['national_mae_before_pp'])} → "
                f"{_fmt(readout['national_mae_expanded_pp'])} pp")
    yearly_text = '；'.join(
        f"{html.escape(str(row['year']))}年 {_fmt(row['before_national_mae_pp'])}→"
        f"{_fmt(row['expanded_national_mae_pp'])} pp"
        for row in data['yearly'])
    tau_candidates = {str(row['tau']): row for row in readout['tau_selection_candidates']}
    center_scores = ' / '.join(
        f"τ{key} {_fmt(tau_candidates[key]['center_mae_pp'], 6)}"
        for key in TAUS)
    selection_margin = abs(
        tau_candidates[str(readout['selected_tau'])]['center_mae_pp']
        - tau_candidates['0']['center_mae_pp'])
    selection_period = readout['tau_selection_development']
    if isinstance(selection_period, list) and len(selection_period) == 2:
        selection_period = f"{selection_period[0]}—{selection_period[1]}"
    else:
        selection_period = '预先登记的早期开发期'
    api_ok = readout['new_api_calls'] == 0 and readout['new_q9_density_fits'] == 0
    api_note = '本次评价与报告生成均为0新增API、0次Q9密度重拟合；统计扩展不增加独立LLM回答。' if api_ok else ''
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Core＋Normal扩展是否改善A82</title>
<style>
:root{{--ink:#222;--muted:#555;--blue:#1764AB;--orange:#B75308;--gray:#777;--paper:#faf9f5;--rule:#d8dce0}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:18px/1.72 "Times New Roman","Kaiti SC","STKaiti","KaiTi",serif}}
main{{max-width:1120px;margin:0 auto;padding:34px 26px 60px}}header{{border-bottom:2px solid var(--ink);padding-bottom:20px}}
.eyebrow{{font-size:14px;letter-spacing:.04em;color:var(--muted)}}h1{{font-size:31px;line-height:1.3;margin:8px 0 12px}}h2{{font-size:24px;margin:36px 0 10px;line-height:1.4}}h3{{font-size:19px;margin:22px 0 6px}}
p{{margin:10px 0}}.lead{{font-size:20px;max-width:940px}}.decision{{margin:22px 0;padding:16px 20px;border-left:5px solid var(--orange);background:#f2ece3}}
.metrics{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:20px 0}}
.metric{{padding:14px 16px;background:#fff;border-top:3px solid var(--blue)}}.metric:nth-child(2){{border-color:var(--orange)}}.metric:nth-child(3){{border-color:var(--gray)}}
.metric .label{{font-size:15px;color:var(--muted)}}.metric strong{{display:block;font:600 24px/1.35 "Times New Roman","Kaiti SC",serif;margin-top:3px}}
.delta{{font-size:15px;color:var(--muted)}}figure{{margin:18px 0 26px}}figure img{{display:block;width:100%;height:auto;background:#fff}}figcaption{{font-size:14px;color:var(--muted);margin-top:7px}}
.split{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.split figure{{margin:12px 0}}
.callout{{padding:13px 16px;background:#eef2f5;border-left:4px solid var(--blue);margin:15px 0}}
.note{{font-size:15px;color:var(--muted)}}.nums{{font-variant-numeric:tabular-nums}}.key{{color:var(--orange);font-weight:bold}}
ul{{padding-left:1.4em}}li{{margin:7px 0}}details{{margin-top:24px;border-top:1px solid var(--rule);padding-top:12px}}summary{{cursor:pointer;font-weight:bold}}
code{{font-size:.9em;overflow-wrap:anywhere}}@media(max-width:720px){{main{{padding:22px 16px}}h1{{font-size:26px}}.metrics,.split{{grid-template-columns:1fr}}body{{font-size:17px}}}}
</style></head><body><main>
<header><div class="eyebrow">SCE · A82回顾性重建 · 2019-01—2025-10 · 离线统计扩展</div>
<h1>{html.escape(headline)}</h1>
<p class="lead">主指标先看公开SCE全国Q9中位数 MAE；辅助看同一全波次真人分布上的Q9 W1与跨人IQR。当前结论只描述这82个月，不把统计扩展当作新增LLM证据。</p></header>
<div class="metrics">
<div class="metric"><span class="label">全期公开SCE目标 MAE（pp）</span><strong>{_fmt(readout['national_mae_before_pp'])} → {_fmt(readout['national_mae_expanded_pp'])}</strong><span class="delta">选定 τ={tau}；变化 {_signed(delta)} · 历史基线 {_fmt(readout['national_mae_anchor_pp'])}</span></div>
<div class="metric"><span class="label">2021年公开SCE目标 MAE（pp）</span><strong>{_fmt(readout['national_mae_2021_before_pp'])} → {_fmt(readout['national_mae_2021_expanded_pp'])}</strong><span class="delta">历史基线 {_fmt(readout['national_mae_2021_anchor_pp'])} · 扩展后变化 {_signed(readout['national_mae_2021_expanded_pp'] - readout['national_mae_2021_before_pp'])}</span></div>
<div class="metric"><span class="label">同全波次Q9 W1（pp）</span><strong>{_fmt(readout['full_wave_q9_w1_before_pp'])} → {_fmt(readout['full_wave_q9_w1_expanded_pp'])}</strong><span class="delta">越低越好；月均绝对IQR差 {_fmt(readout['full_wave_q9_iqr_error_before_pp'])} → {_fmt(readout['full_wave_q9_iqr_error_expanded_pp'])} pp</span></div>
</div>
<div class="decision"><strong>一句话判断：</strong>全期主MAE{direction} {_fmt(abs(delta))} pp；同全波次支持下 W1 仅变化 {_signed(readout['full_wave_q9_w1_expanded_pp'] - readout['full_wave_q9_w1_before_pp'])} pp，月均绝对IQR差仅变化 {_signed(readout['full_wave_q9_iqr_error_expanded_pp'] - readout['full_wave_q9_iqr_error_before_pp'])} pp。这些分布指标变化很小，不据此称为显著或实质改善。2021年MAE降低 {_fmt(readout['national_mae_2021_before_pp'] - readout['national_mae_2021_expanded_pp'])} pp，但不能替代全期结果。</div>
<h2>1．82个月水平与2021年细节</h2>
<p>全期曲线同时显示公开SCE全国真值、原A82 T0 Core估计、选定 τ={tau} 的Core＋Normal估计，以及冻结的公开历史基线。原T0以每月约512份已有Core回答和原设计权重汇总形成；扩展保留Core原始调查权重，只对Normal与明确允许的缺失字段作统计预测。</p>
<figure><img src="figures/q9_levels_all_82.png" alt="82个月Q9全国中位数，实际SCE、原T0、Core加Normal及基线"><figcaption>完整82月序列；浅橙区标出2021年。目标为纽约联储SCE公开全国Q9指标，单位百分比。</figcaption></figure>
<figure><img src="figures/q9_levels_2021.png" alt="2021年Q9全国中位数逐月曲线"><figcaption>2021年12个月放大；同样展示真人目标、原Core估计、选定τ扩展与公开历史基线。</figcaption></figure>
<h2>2．逐年主指标：全国Q9中位数 MAE</h2>
<p>全期 MAE：原T0 {_fmt(readout['national_mae_before_pp'])} pp，扩展后 {_fmt(readout['national_mae_expanded_pp'])} pp，公开历史基线 {_fmt(readout['national_mae_anchor_pp'])} pp。逐年原T0→扩展：{yearly_text}。2025年只含1—10月。</p>
<figure><img src="figures/q9_yearly_mae.png" alt="逐年Q9全国中位数MAE比较"><figcaption>逐年平均绝对误差，按每月全国中位数等月计；数值越低越好。主结果来自冻结SCE官方月目标。</figcaption></figure>
<h2>3．分布辅助指标：同一全波次真人支持</h2>
<p>扩展前后均与同月同一份全波次、有效且正权重的真人Q9均值分布比较；W1由经验CDF差的绝对值精确积分。右图把真人月均IQR作为参照，并直接显示原T0与扩展的平均IQR；月均绝对IQR差为 {_fmt(readout['full_wave_q9_iqr_error_before_pp'])} → {_fmt(readout['full_wave_q9_iqr_error_expanded_pp'])} pp。先前的同名单 W1 2.219 pp 来自另一支持口径，与本次全波次支持不同，不能直接比较。</p>
<figure><img src="figures/q9_w1_iqr_full_wave.png" alt="同一全波次真人分布支持上的Q9 W1与IQR"><figcaption>2019-01—2025-10，82个月等权。真人IQR是每月完整波次真人Q9分布IQR的等月平均；IQR越接近该线，宽度越接近。</figcaption></figure>
<h2>4．τ敏感性与选择边界</h2>
<p>τ候选为0、8、24。最终取值 τ={tau} 来自封存预测包：在{html.escape(str(selection_period))}的LLM回答遮蔽留出比较中，先最小化月/种子Q9中位数绝对误差，再以W1打破平局；偏好更小τ。对应中心MAE为 {center_scores} pp；τ={tau}相对τ=0仅差 {_fmt(selection_margin, 6)} pp。选择在读取真人全波次真值之前完成，差异很小，不把τ={tau}称为已确认优越参数。</p>
<figure><img src="figures/tau_sensitivity.png" alt="三个tau候选的全国Q9 MAE和全波次W1敏感性"><figcaption>空心圆标出早期LLM留出所选值。真人目标上的三条曲线仅作固定参数敏感性展示，不用于改选τ；前48月及后34月均是已被查看的历史数据，不称未触碰盲测。</figcaption></figure>
<div class="callout"><strong>数据规模与执行：</strong>82个月实际框架合计 {readout['frame_person_months']:,} 人月（单月 {data['frame_min']:,}—{data['frame_max']:,}）；既有Core {readout['core_person_months']:,} 人月、Normal {readout['normal_person_months']:,} 人月。正权重框架 {readout['weighted_frame_person_months']:,}，权重缺失 {readout['missing_weight_person_months']:,} 仍保持 null、不参与加权。可用Q9模型供体 {readout['q9_model_donors_total']:,} 个，Q8供体 {readout['q8_model_donors_total']:,} 个。原512计划名单里的14个跨月完成者未进入本批Core，在完整P框架中计为统计Normal；另有本批Core内14条Q9字段不可用作供体（1份沿用输入、13份密度拟合失败），两组人数不同，不互相替代。按月等权平均，选定τ下Q9父池供体覆盖人口质量 {_fmt(readout['q9_parent_pool_share_equal_month'] * 100, 2)}%，无本地Core目标格质量 {_fmt(readout['q9_unsupported_local_share_equal_month'] * 100, 2)}%。{api_note}</div>
<p>后34个月 MAE：原T0 {_fmt(readout['late_34_mae_before_pp'])} pp，扩展 {_fmt(readout['late_34_mae_expanded_pp'])} pp，公开历史基线 {_fmt(readout['late_34_mae_anchor_pp'])} pp。组合敏感性：早48月MSE拟权选定τ模拟权重 {_fmt(readout['late_34_mse_blend_weight_selected'], 6)}，后34月 MAE {_fmt(readout['late_34_mse_blend_mae_selected'], 6)} pp；原T0的MSE拟权组合权重 {_fmt(readout['late_34_mse_blend_weight_before'], 6)}，后34月 MAE {_fmt(readout['late_34_mse_blend_mae_before'], 6)} pp。MAE拟权的选定τ模拟权重为 {_fmt(readout['late_34_mae_blend_weight_selected'], 3)}。这些是回顾性组合摘要，不是未观察过的未来测试。</p>
<h2>解释边界</h2><ul><li>Normal统计预测记录已生成；本次没有新增LLM调用或真人答卷，也未重拟Q9密度。</li><li>MAE使用固定公开SCE月指标；扩展前后W1/IQR使用相同的逐月全波次真人分布。</li><li>τ只按预先封存的LLM回答遮蔽留出规则确定，未使用当前真人答案选参。</li><li>全国真值与历史基线沿用原A82 T0评价；48/34月组合是回顾性汇总。</li><li>全波次真人分布仅用于评价，不参与Core＋Normal预测构造。</li><li>Core实际回答-only敏感性分析不替代冻结的原T0对照。</li></ul>
<details><summary>来源文件与复现信息</summary><p>本页从冻结评价目录生成；报告程序先核验 evaluation manifest 中 summary.json、monthly_public.csv、yearly.csv 的哈希。来源清单：</p>
<ul>{''.join(f'<li><code>{html.escape(str(name))}</code> · SHA256 <code>{digest}</code></li>' for name, digest in readout['source_sha256'].items())}</ul>
<p>本页数值见同目录 <code>readout.json</code>；逐月公开聚合仍以原评价目录中的 <code>monthly_public.csv</code> 为准。原始个体答卷、提示与回复未复制进报告。</p></details>
</main></body></html>'''


def render(evaluation=DEFAULT_EVALUATION, report=DEFAULT_REPORT):
    data = _load(Path(evaluation))
    report = Path(report).resolve()
    allowed = (ROOT / 'docs/workstreams/20261026_core_normal_full_a').resolve()
    if not report.is_relative_to(allowed) or report.exists():
        raise ValueError('Report must be a fresh directory under the assigned Core + Normal workstream')
    report.mkdir(parents=True)
    _charts(data, report)
    readout = _readout(data)
    (report / 'readout.json').write_text(
        json.dumps(readout, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
        encoding='utf-8')
    (report / 'index.html').write_text(_html(data, readout), encoding='utf-8')
    return dict(status='completed_core_normal_html_report', selected_tau=int(data['tau']),
                report=str(report.relative_to(ROOT)),
                national_mae_before_pp=readout['national_mae_before_pp'],
                national_mae_expanded_pp=readout['national_mae_expanded_pp'],
                national_mae_change_pp=readout['national_mae_change_pp'],
                full_wave_q9_w1_before_pp=readout['full_wave_q9_w1_before_pp'],
                full_wave_q9_w1_expanded_pp=readout['full_wave_q9_w1_expanded_pp'],
                new_api_calls=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation', type=Path, default=DEFAULT_EVALUATION,
                        help='Completed v3 offline evaluation directory under outputs/')
    parser.add_argument('--report', type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)
    print(json.dumps(render(args.evaluation, args.report), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
