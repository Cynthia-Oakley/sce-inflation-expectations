"""Six fixed analysis sections over canonical records; plugins by registry.

Statistical conventions (panel v1 batch 1, per experiment_panel_review_20261020):
1. Primary statistic is the GROUP-CENTER MAE: for each month x repeat cell,
   |weighted median(model) - weighted median(truth)|, averaged with equal
   weight over month x repeat cells. Personal MAE (weighted mean of per-person
   absolute errors) and the personal absolute error median are separate rows.
   Center RMSE and signed center bias are reported alongside.
2. Common support first: the main table uses person-months scorable in ALL
   arms x repeats; per-arm usable supports are a separate sensitivity table.
   Q8 takes its own support and is never dropped because of Q9 failures; the
   persistence baseline (needs a prior) is aligned per question on exactly the
   model's person-month support. Every section reuses the same support.
3. ESS is Kish ESS on person-month units after merging a person's repeats
   inside the effective support: n, ESS, max weight share, covered months and
   the number of unique persons across months are reported separately.
   Display thresholds (design draft): n<10 coverage only; 10-19 exploratory;
   n>=20 with ESS>=10 normal; n>=20 with ESS<10 shown but flagged.
4. Repeat variance decomposition reuses evaluation/temperature.py
   variance_components on the complete same-month repeat support
   (equal-person, unweighted): within-person sample variance and the
   between-person variance of repeat means net of within/R. Negative estimates
   are retained and explained; batches are labelled by their actual repeat
   count (R=2 两遍 / R=4 四遍), never uniformly called "two repeats".
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from studies.sce_inflation_expectations.evaluation.metrics import quantile, wasserstein1
from studies.sce_inflation_expectations.evaluation.response_gap import direction, prior_band
from studies.sce_inflation_expectations.evaluation.temperature import variance_components
from studies.sce_inflation_expectations.panel.adapters import REGISTRY
from studies.sce_inflation_expectations.panel.registry import REFERENCE_BATCH, SECTIONS, entry_for

MIN_COVERAGE_N = 10
EXPLORATORY_MAX_N = 19
ESS_WARN = 10
UPDATE_THRESHOLD_PP = 0.5

CN_LABELS = {
    'six_cell': {
        'high_school|attached': '高中及以下 × 在职',
        'high_school|not_attached': '高中及以下 × 未在职',
        'some_college|attached': '部分大学 × 在职',
        'some_college|not_attached': '部分大学 × 未在职',
        'college|attached': '大学及以上 × 在职',
        'college|not_attached': '大学及以上 × 未在职',
        'unknown': '未知（另池）',
    },
    'age_group': {'Under 40': '40岁以下', '40 to 60': '40–60岁', 'Over 60': '60岁及以上',
                  '60 and Over': '60岁及以上'},
    'household_income_band': {'under_50k': '家庭收入<5万美元', '50k_to_100k': '5–10万美元',
                              'over_100k': '≥10万美元'},
    'numeracy': {'high': '高', 'low': '低'},
    'region': {'Northeast': '东北', 'Midwest': '中西部', 'South': '南部', 'West': '西部'},
    'housing_tenure': {'owner': '自有住房', 'renter': '租房'},
}
GRID_DIMENSIONS = (
    ('six_cell', '六格网格（学历×在职）'),
    ('age_group', '年龄切片'),
    ('household_income_band', '家庭收入切片'),
    ('numeracy', '数理切片'),
    ('region', '地区切片'),
    ('housing_tenure', '住房切片'),
)
SIX_CELL_ORDER = ('high_school|attached', 'high_school|not_attached',
                  'some_college|attached', 'some_college|not_attached',
                  'college|attached', 'college|not_attached', 'unknown')

SECTION_PLUGINS = {}


def section_plugin(name):
    def wrap(fn):
        SECTION_PLUGINS[name] = fn
        return fn
    return wrap


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and np.isfinite(value)


def _cn(dim, label):
    return CN_LABELS.get(dim, {}).get(label, label)


def _kish_ess(weights):
    weights = [float(w) for w in weights if _finite(w) and w > 0]
    if not weights:
        return None
    total = sum(weights)
    return float(total ** 2 / sum(w * w for w in weights))


def _wquantile(values, weights, p):
    return quantile(np.asarray(values, float), np.asarray(weights, float), p)


def _valid_q9(r):
    return (_finite(r.get('model_q9_mean')) and _finite(r.get('truth_q9_mean'))
            and _finite(r.get('weight')) and r['weight'] > 0)


def _valid_q8(r):
    return (_finite(r.get('model_q8_point')) and _finite(r.get('truth_q8_point'))
            and _finite(r.get('weight')) and r['weight'] > 0)


def _design(records):
    arms = sorted({r['arm'] for r in records})
    repeats = sorted({r['repeat'] for r in records if r['repeat'] is not None})
    return arms, repeats


def q9_support(records):
    """Person-months (month, _pid) scorable in every arm x repeat (Q9).

    Falls back to the first arm's own support when the design is unbalanced
    and no person-month is scorable across everything; the note says so.
    """
    arms, repeats = _design(records)
    by_pm = defaultdict(dict)
    for r in records:
        by_pm[(r['month'], r['_pid'])][(r['arm'], r['repeat'])] = r
    full = {pm for pm, grid in by_pm.items()
            if all((a, rep) in grid and _valid_q9(grid[(a, rep)])
                   for a in arms for rep in repeats)}
    note = None
    if not full and arms:
        first = arms[0]
        full = {pm for pm, grid in by_pm.items()
                if all((first, rep) in grid and _valid_q9(grid[(first, rep)])
                       for rep in repeats)}
        note = '设计不平衡或缺失过重：无全臂×遍共同支持，主表退回第一臂 %s 的可用支持。' % first
    return full, arms, repeats, note


def q8_support(records, arms, repeats):
    by_pm = defaultdict(dict)
    for r in records:
        by_pm[(r['month'], r['_pid'])][(r['arm'], r['repeat'])] = r
    return {pm for pm, grid in by_pm.items()
            if all((a, rep) in grid and _valid_q8(grid[(a, rep)])
                   for a in arms for rep in repeats)}


def _person_weights(records, support, arms, repeats):
    """One weight per person-month: the person's repeats merged back.

    (Record weights were split evenly across repeats by the adapter, so the
    sum of one person's repeat weights of a single arm is the design weight.)
    """
    first = arms[0]
    weights = {}
    for r in records:
        pm = (r['month'], r['_pid'])
        if r['arm'] == first and pm in support and _finite(r.get('weight')):
            weights[pm] = weights.get(pm, 0.0) + r['weight']
    return weights


def _support_stats(support, weights):
    w = [weights[pm] for pm in support if pm in weights]
    total = sum(w)
    return {
        'n_person_months': len(support),
        'ess': _kish_ess(w),
        'max_weight_share': (max(w) / total) if w and total > 0 else None,
        'months_covered': sorted({pm[0] for pm in support}),
        'unique_persons': len({pm[1] for pm in support}),
    }


def _cell(recs, pred_key='model_q9_mean', truth_key='truth_q9_mean'):
    """One month x repeat cell: group-center and personal error statistics.

    recs must already sit on a fixed support (same person-months), one arm.
    """
    rows = [(float(r[pred_key]), float(r[truth_key]), float(r['weight'])) for r in recs
            if _finite(r.get(pred_key)) and _finite(r.get(truth_key))
            and _finite(r.get('weight')) and r['weight'] > 0]
    cell = {'n': len({r['_pid'] for r in recs})}
    if not rows:
        return cell
    p = np.asarray([r[0] for r in rows])
    y = np.asarray([r[1] for r in rows])
    w = np.asarray([r[2] for r in rows])
    wn = w / w.sum()
    err = p - y
    med_p, med_y = _wquantile(p, w, .5), _wquantile(y, w, .5)
    cell.update({
        'center_bias_pp': float(med_p - med_y),
        'center_abs_pp': float(abs(med_p - med_y)),
        'person_mae_pp': float(wn @ np.abs(err)),
        'person_abs_error_median_pp': _wquantile(np.abs(err), w, .5),
        'w1_pp': wasserstein1(p, w, y, w),
        'centered_w1_pp': wasserstein1(p - med_p, w, y - med_y, w),
        'pred_median_pp': med_p, 'truth_median_pp': med_y,
        'pred_mean_pp': float(wn @ p), 'truth_mean_pp': float(wn @ y),
        'pred_iqr_pp': _wquantile(p, w, .75) - _wquantile(p, w, .25),
        'truth_iqr_pp': _wquantile(y, w, .75) - _wquantile(y, w, .25),
        'pred_std_pp': float(np.sqrt(wn @ (p - wn @ p) ** 2)),
        'truth_std_pp': float(np.sqrt(wn @ (y - wn @ y) ** 2)),
    })
    return cell


def _arm_cells(records, support, arm, months, repeats,
               pred_key='model_q9_mean', truth_key='truth_q9_mean'):
    """month x repeat cells for one arm, restricted to the support."""
    cells = {}
    for month in months:
        for rep in repeats:
            recs = [r for r in records if r['arm'] == arm and r['month'] == month
                    and r['repeat'] == rep and (month, r['_pid']) in support
                    and _finite(r.get(pred_key)) and _finite(r.get(truth_key))]
            cells[(month, rep)] = _cell(recs, pred_key, truth_key)
    return cells


def _mean(cells, key):
    values = [c[key] for c in cells.values() if _finite(c.get(key))]
    return float(np.mean(values)) if values else None


def _rmse(cells, key):
    values = [c[key] for c in cells.values() if _finite(c.get(key))]
    return float(np.sqrt(np.mean(np.asarray(values) ** 2))) if values else None


def _prior_finite_pm(records, support, arms):
    first = arms[0]
    ok = set()
    for r in records:
        pm = (r['month'], r['_pid'])
        if r['arm'] == first and pm in support and _finite(r.get('prior_q9_mean')):
            ok.add(pm)
    return ok


def _overview(records):
    """Section 1: per-experiment x arm overview on the common Q9 support."""
    support, arms, repeats, support_note = q9_support(records)
    months = sorted({pm[0] for pm in support})
    weights = _person_weights(records, support, arms, repeats)
    stats = _support_stats(support, weights)
    prior_ok = _prior_finite_pm(records, support, arms)
    identical = support & prior_ok
    out, q8 = {}, {}
    per_arm_cells = {}
    for arm in arms:
        cells = _arm_cells(records, support, arm, months, repeats)
        per_arm_cells[arm] = cells
        row = dict(stats)
        row.update({
            'n_cells': len(cells),
            'support_note': support_note,
            'center_mae_pp': _mean(cells, 'center_abs_pp'),
            'center_bias_pp': _mean(cells, 'center_bias_pp'),
            'center_rmse_pp': _rmse(cells, 'center_bias_pp'),
            'person_mae_pp': _mean(cells, 'person_mae_pp'),
            'person_abs_error_median_pp': _mean(cells, 'person_abs_error_median_pp'),
            'w1_pp': _mean(cells, 'w1_pp'),
            'centered_w1_pp': _mean(cells, 'centered_w1_pp'),
            'pred_median_pp': _mean(cells, 'pred_median_pp'),
            'truth_median_pp': _mean(cells, 'truth_median_pp'),
            'pred_iqr_pp': _mean(cells, 'pred_iqr_pp'),
            'truth_iqr_pp': _mean(cells, 'truth_iqr_pp'),
            'pred_std_pp': _mean(cells, 'pred_std_pp'),
            'truth_std_pp': _mean(cells, 'truth_std_pp'),
            'persistence': None,
        })
        if identical:
            pcells = _arm_cells(records, identical, arm, months, repeats,
                                pred_key='prior_q9_mean')
            mcells = _arm_cells(records, identical, arm, months, repeats)
            prow = _support_stats(identical, _person_weights(records, identical, arms, repeats))
            # update-distribution W1 per month x repeat cell on the identical
            # (model + prior + truth) support, then equal-averaged
            dw1 = {}
            for month in months:
                for rep in repeats:
                    dm, dy, dw = [], [], []
                    for r in records:
                        if (r['arm'] == arm and r['month'] == month and r['repeat'] == rep
                                and (month, r['_pid']) in identical
                                and _finite(r.get('model_q9_mean'))
                                and _finite(r.get('truth_q9_mean'))
                                and _finite(r.get('prior_q9_mean'))
                                and _finite(r.get('weight'))):
                            dm.append(r['model_q9_mean'] - r['prior_q9_mean'])
                            dy.append(r['truth_q9_mean'] - r['prior_q9_mean'])
                            dw.append(r['weight'])
                    if len(dm) >= 2:
                        dw1[(month, rep)] = wasserstein1(np.asarray(dm), np.asarray(dw),
                                                         np.asarray(dy), np.asarray(dw))
            row['persistence'] = {
                'n_identical_support': prow['n_person_months'],
                'ess': prow['ess'],
                'center_mae_pp': _mean(pcells, 'center_abs_pp'),
                'center_bias_pp': _mean(pcells, 'center_bias_pp'),
                'center_rmse_pp': _rmse(pcells, 'center_bias_pp'),
                'person_mae_pp': _mean(pcells, 'person_mae_pp'),
                'person_abs_error_median_pp': _mean(pcells, 'person_abs_error_median_pp'),
                'w1_pp': _mean(pcells, 'w1_pp'),
                'model_center_mae_same_support_pp': _mean(mcells, 'center_abs_pp'),
                'model_person_mae_same_support_pp': _mean(mcells, 'person_mae_pp'),
            }
            if dw1:
                row['delta_w1_pp'] = float(np.mean(list(dw1.values())))
        out[arm] = row
    # per-arm usable supports: sensitivity table (each arm alone, all repeats)
    by_pm = defaultdict(dict)
    for r in records:
        by_pm[(r['month'], r['_pid'])][(r['arm'], r['repeat'])] = r
    sensitivity = {}
    for arm in arms:
        usable = {pm for pm, grid in by_pm.items()
                  if all((arm, rep) in grid and _valid_q9(grid[(arm, rep)]) for rep in repeats)}
        w = _person_weights(records, usable, arms, repeats)
        sensitivity[arm] = _support_stats(usable, w)
    # Q8 takes its own support, independent of Q9 failures
    q8s = q8_support(records, arms, repeats)
    if q8s:
        q8w = _person_weights(records, q8s, arms, repeats)
        q8stats = _support_stats(q8s, q8w)
        for arm in arms:
            cells = _arm_cells(records, q8s, arm, months, repeats,
                               pred_key='model_q8_point', truth_key='truth_q8_point')
            q8[arm] = dict(q8stats)
            q8[arm].update({
                'center_mae_pp': _mean(cells, 'center_abs_pp'),
                'center_bias_pp': _mean(cells, 'center_bias_pp'),
                'person_mae_pp': _mean(cells, 'person_mae_pp'),
                'person_abs_error_median_pp': _mean(cells, 'person_abs_error_median_pp'),
                'w1_pp': _mean(cells, 'w1_pp'),
                'pred_median_pp': _mean(cells, 'pred_median_pp'),
                'truth_median_pp': _mean(cells, 'truth_median_pp'),
            })
    return {'q9': out, 'q8': q8, 'support_sensitivity': sensitivity,
            'support_note': support_note,
            'notes': ['主统计量=群体中位数MAE：每月×每遍的 |模型跨人加权中位−真人跨人加权中位|，对月×遍等权平均。',
                      '主表支持=全部所选臂×遍的可评共同支持（Q9）；各臂可用支持见敏感性表；Q8 独立取支持。',
                      'ESS 为支持内合并本人重复后的人×月 Kish ESS；独立人数另列，人×月不当独立个体。',
                      '汇总指标先逐月逐遍计算，再等权平均；缺失与未提供不填零。']}


@section_plugin('overview')
def section_overview(records_by_experiment, regime_lookup):
    return {exp: _overview(recs) for exp, recs in records_by_experiment.items()}


def _monthly_and_regimes(records, regime_lookup):
    support, arms, repeats, support_note = q9_support(records)
    months = sorted({pm[0] for pm in support})
    weights = _person_weights(records, support, arms, repeats)
    prior_ok = _prior_finite_pm(records, support, arms)
    identical = support & prior_ok
    out = {}
    for arm in arms:
        cells = _arm_cells(records, support, arm, months, repeats)
        pcells = _arm_cells(records, identical, arm, months, repeats,
                            pred_key='prior_q9_mean') if identical else {}
        rows = []
        for month in months:
            month_pms = [pm for pm in support if pm[0] == month]
            month_w = [weights[pm] for pm in month_pms if pm in weights]
            for rep in repeats:
                cell = cells.get((month, rep), {})
                pcell = pcells.get((month, rep), {})
                regime = regime_lookup.get(month, {}).get('regime', 'unknown')
                rows.append({
                    'month': month, 'repeat': rep, 'regime': regime,
                    'n': cell.get('n', len(month_pms)),
                    'ess': _kish_ess(month_w),
                    'truth_median_pp': cell.get('truth_median_pp'),
                    'model_median_pp': cell.get('pred_median_pp'),
                    'persist_median_pp': pcell.get('pred_median_pp'),
                    'model_center_mae_pp': cell.get('center_abs_pp'),
                    'persist_center_mae_pp': pcell.get('center_abs_pp'),
                    'model_person_mae_pp': cell.get('person_mae_pp'),
                    'persist_person_mae_pp': pcell.get('person_mae_pp'),
                    'w1_pp': cell.get('w1_pp'),
                })
        table = {}
        for regime in ('calm', 'drastic'):
            group = [r for r in rows if r['regime'] == regime]
            table[regime] = {
                'n_cells': len(group),
                'model_center_mae_pp': (float(np.mean([r['model_center_mae_pp'] for r in group]))
                                        if group and all(_finite(r['model_center_mae_pp']) for r in group) else None),
                'persist_center_mae_pp': (float(np.mean([r['persist_center_mae_pp'] for r in group]))
                                          if group and all(_finite(r['persist_center_mae_pp']) for r in group) else None),
                'model_person_mae_pp': (float(np.mean([r['model_person_mae_pp'] for r in group]))
                                        if group and all(_finite(r['model_person_mae_pp']) for r in group) else None),
                'persist_person_mae_pp': (float(np.mean([r['persist_person_mae_pp'] for r in group]))
                                          if group and all(_finite(r['persist_person_mae_pp']) for r in group) else None),
            }
        drastic = table['drastic']
        skill_center = (drastic['persist_center_mae_pp'] - drastic['model_center_mae_pp']
                        if _finite(drastic['persist_center_mae_pp']) and _finite(drastic['persist_center_mae_pp']) else None)
        skill_person = (drastic['persist_person_mae_pp'] - drastic['model_person_mae_pp']
                        if _finite(drastic['persist_person_mae_pp']) and _finite(drastic['model_person_mae_pp']) else None)
        out[arm] = {'rows': rows, 'regime_table': table,
                    'skill_s_center_pp': skill_center, 'skill_s_person_pp': skill_person,
                    'support_note': support_note,
                    'notes': ['主读数为群体中心口径（月×遍等权）；个人MAE口径的 S 并列标注。',
                              '机制月判定为事后口径（|Δ加权中位|≥0.2pp），非事前识别；剧烈月方向正确即机械占优，必须与平稳月同报。',
                              '批次月份非连续，Δ 不可链式计算；机制标签来自全样本真值序列。']}
    return out


@section_plugin('monthly')
def section_monthly(records_by_experiment, regime_lookup):
    return {exp: _monthly_and_regimes(recs, regime_lookup)
            for exp, recs in records_by_experiment.items()}


def _display_class(n, ess):
    if n < MIN_COVERAGE_N:
        return 'coverage'          # 仅覆盖
    if n <= EXPLORATORY_MAX_N:
        return 'exploratory'       # 10–19 灰色探索
    if ess is not None and ess < ESS_WARN:
        return 'weak_ess'          # n>=20 但 ESS<10：显示并提示
    return 'normal'


def _dimension_cells(records, support, weights, arms, repeats, months, dim, arm):
    key = 'cell' if dim == 'six_cell' else dim
    groups = defaultdict(list)
    for r in records:
        pm = (r['month'], r['_pid'])
        if pm not in support or r['arm'] != arm:
            continue
        label = r.get(key) if dim == 'six_cell' else (r.get(key) or 'missing')
        groups[label].append(r)
    order = (SIX_CELL_ORDER if dim == 'six_cell'
             else sorted(groups, key=lambda x: (x == 'missing', str(x))))
    cells = {}
    for label in order:
        recs = groups.get(label)
        if not recs:
            continue
        monthly = []
        for month in months:
            sub = [r for r in recs if r['month'] == month]
            pms = {(r['month'], r['_pid']) for r in sub}
            n_m = len(pms)
            w_m = [weights[pm] for pm in pms if pm in weights]
            mcells = {}
            for rep in repeats:
                rsub = [r for r in sub if r['repeat'] == rep]
                mcells[rep] = _cell(rsub)
            monthly.append({'month': month, 'n': n_m, 'ess': _kish_ess(w_m),
                            'cells': mcells})
        reportable = [m for m in monthly if m['n'] >= MIN_COVERAGE_N]
        pooled_n = sum(m['n'] for m in monthly)
        pooled_ess = _kish_ess([weights[pm] for pm in
                                {(r['month'], r['_pid']) for r in recs} if pm in weights])

        def mmean(k):
            vals = []
            for m in reportable:
                for rep in repeats:
                    v = m['cells'][rep].get(k)
                    if _finite(v):
                        vals.append(v)
            return float(np.mean(vals)) if vals else None

        pms_all = {(r['month'], r['_pid']) for r in recs}
        prior_ok = {pm for pm in pms_all if any(
            _finite(r.get('prior_q9_mean')) for r in recs if (r['month'], r['_pid']) == pm)}
        identical = pms_all & prior_ok
        isub = [r for r in recs if (r['month'], r['_pid']) in identical]
        pcell = _cell(isub) if identical else {}
        cell = {
            'n': pooled_n, 'ess': pooled_ess,
            'months_covered': len(monthly),
            'months_reportable': len(reportable),
            'min_month_n': min((m['n'] for m in monthly), default=0),
            'unique_persons': len({pm[1] for pm in pms_all}),
            'display_class': _display_class(pooled_n, pooled_ess),
            'distribution_kind': 'cross_month_mixed',
            'label_cn': _cn(dim, label),
            'person_mae_pp': mmean('person_mae_pp'),
            'persist_person_mae_pp': pcell.get('person_mae_pp'),
            'center_mae_pp': mmean('center_abs_pp'),
            'persist_center_mae_pp': pcell.get('center_abs_pp'),
            'bias_pp': mmean('center_bias_pp'),
            'w1_pp': mmean('w1_pp'),
            'truth_median_pp': mmean('truth_median_pp'),
            'model_median_pp': mmean('pred_median_pp'),
        }
        cells[label] = cell
    return cells


def _grid(records):
    support, arms, repeats, _ = q9_support(records)
    months = sorted({pm[0] for pm in support})
    weights = _person_weights(records, support, arms, repeats)
    return {arm: {dim: _dimension_cells(records, support, weights, arms, repeats, months, dim, arm)
                  for dim, _ in GRID_DIMENSIONS}
            for arm in arms}


@section_plugin('grid')
def section_grid(records_by_experiment, regime_lookup):
    return {exp: _grid(recs) for exp, recs in records_by_experiment.items()}


def _group_block(records, support, weights, arms, repeats, months):
    pms = [pm for pm in support if any(
        _finite(r.get('prior_q9_mean')) for r in records if (r['month'], r['_pid']) == pm)]
    sub = [r for r in records if (r['month'], r['_pid']) in set(pms)]
    n = len(set(pms))
    w = [weights[pm] for pm in set(pms) if pm in weights]
    block = {'n': n, 'ess': _kish_ess(w), 'display_class': _display_class(n, _kish_ess(w))}
    if n < MIN_COVERAGE_N:
        return block
    first = arms[0]
    cells = _arm_cells(records, set(pms), first, months, repeats)
    pcells = _arm_cells(records, set(pms), first, months, repeats,
                        pred_key='prior_q9_mean')
    deltas_model, deltas_truth, dw = [], [], []
    for r in sub:
        if not (_finite(r.get('model_q9_mean')) and _finite(r.get('truth_q9_mean'))
                and _finite(r.get('prior_q9_mean')) and _finite(r.get('weight'))
                and r['arm'] == first):
            continue
        deltas_model.append(r['model_q9_mean'] - r['prior_q9_mean'])
        deltas_truth.append(r['truth_q9_mean'] - r['prior_q9_mean'])
        dw.append(r['weight'])
    block.update({
        'prior_mean_pp': _mean(pcells, 'pred_mean_pp'),
        'truth_mean_pp': _mean(cells, 'truth_mean_pp'),
        'model_mean_pp': _mean(cells, 'pred_mean_pp'),
        'prior_median_pp': _mean(pcells, 'pred_median_pp'),
        'person_mae_pp': _mean(cells, 'person_mae_pp'),
        'persist_person_mae_pp': _mean(pcells, 'person_mae_pp'),
        'center_mae_pp': _mean(cells, 'center_abs_pp'),
        'persist_center_mae_pp': _mean(pcells, 'center_abs_pp'),
        'bias_pp': _mean(cells, 'center_bias_pp'),
        'w1_pp': _mean(cells, 'w1_pp'),
        'delta_w1_pp': (wasserstein1(np.asarray(deltas_model), np.asarray(dw),
                                     np.asarray(deltas_truth), np.asarray(dw))
                        if len(deltas_model) >= 2 else None),
    })
    return block


def _priors(records):
    support, arms, repeats, _ = q9_support(records)
    months = sorted({pm[0] for pm in support})
    weights = _person_weights(records, support, arms, repeats)
    band_order = ('below_2', '2_to_below_4', '4_to_below_8', '8_or_above')
    band_cn = {'below_2': '上期预期<2%', '2_to_below_4': '2–4%',
               '4_to_below_8': '4–8%', '8_or_above': '≥8%'}
    out = {}
    first = arms[0]
    prior_pms = {pm for pm in support if any(
        _finite(r.get('prior_q9_mean')) for r in records
        if r['arm'] == first and (r['month'], r['_pid']) == pm)}
    for arm in arms:
        bands, directions = {}, {}
        for band in band_order:
            sub_support = set()
            for pm in prior_pms:
                rec = next((r for r in records if r['arm'] == arm and (r['month'], r['_pid']) == pm
                            and r['repeat'] == repeats[0]), None)
                if rec is not None and prior_band(rec['prior_q9_mean']) == band:
                    sub_support.add(pm)
            block = _group_block(records, sub_support, weights, [arm], repeats, months) \
                if sub_support else {'n': 0, 'ess': None, 'display_class': 'coverage'}
            block['label_cn'] = band_cn[band]
            bands[band] = block
        for bucket in ('up', 'stable', 'down'):
            sub_support = set()
            for pm in prior_pms:
                rec = next((r for r in records if r['arm'] == arm and (r['month'], r['_pid']) == pm
                            and r['repeat'] == repeats[0]), None)
                if rec is None or not _finite(rec.get('truth_q9_mean')):
                    continue
                if direction(rec['truth_q9_mean'] - rec['prior_q9_mean'], UPDATE_THRESHOLD_PP) == bucket:
                    sub_support.add(pm)
            block = _group_block(records, sub_support, weights, [arm], repeats, months) \
                if sub_support else {'n': 0, 'ess': None, 'display_class': 'coverage'}
            block['label_cn'] = {'up': '真人本期上调', 'stable': '真人本期稳定(±0.5pp)',
                                 'down': '真人本期下调'}[bucket]
            directions[bucket] = block
        # drill series: per band, monthly conditional means (month x repeat
        # averaged) for the point-line chart; direction-group amplitudes
        band_series = {}
        for band in band_order:
            by_month = defaultdict(list)
            for pm in prior_pms:
                rec = next((r for r in records if r['arm'] == arm and (r['month'], r['_pid']) == pm
                            and r['repeat'] == repeats[0]), None)
                if rec is not None and _finite(rec.get('prior_q9_mean')) \
                        and prior_band(rec['prior_q9_mean']) == band \
                        and _finite(rec.get('model_q9_mean')) and _finite(rec.get('truth_q9_mean')):
                    by_month[rec['month']].append(
                        (rec['prior_q9_mean'], rec['truth_q9_mean'], rec['model_q9_mean']))
            series = []
            for month in months:
                rows = by_month.get(month)
                if not rows:
                    continue
                series.append({'month': month,
                               'prior': float(np.mean([r[0] for r in rows])),
                               'truth': float(np.mean([r[1] for r in rows])),
                               'model': float(np.mean([r[2] for r in rows])),
                               'n': len(rows)})
            band_series[band] = series
        direction_amp = {}
        for bucket in ('up', 'stable', 'down'):
            by_month = defaultdict(list)
            for pm in prior_pms:
                rec = next((r for r in records if r['arm'] == arm and (r['month'], r['_pid']) == pm
                            and r['repeat'] == repeats[0]), None)
                if rec is None or not (_finite(rec.get('truth_q9_mean'))
                                       and _finite(rec.get('model_q9_mean'))
                                       and _finite(rec.get('prior_q9_mean'))):
                    continue
                if direction(rec['truth_q9_mean'] - rec['prior_q9_mean'], UPDATE_THRESHOLD_PP) == bucket:
                    by_month[rec['month']].append(
                        (abs(rec['truth_q9_mean'] - rec['prior_q9_mean']),
                         abs(rec['model_q9_mean'] - rec['prior_q9_mean'])))
            direction_amp[bucket] = [
                {'month': month,
                 'truth_abs': float(np.mean([r[0] for r in rows])),
                 'model_abs': float(np.mean([r[1] for r in rows])),
                 'n': len(rows)}
                for month, rows in sorted(by_month.items())]
        out[arm] = {'bands': bands, 'directions': directions,
                    'band_series': band_series, 'direction_amplitude': direction_amp,
                    'notes': ['先验四档为前置特征分组（<2、2–4、4–8、≥8%，开发期阈值）。',
                              '上调/稳定/下调分组使用本期真值，仅用于评价，不能用于输入分配。']}
    return out


@section_plugin('priors')
def section_priors(records_by_experiment, regime_lookup):
    return {exp: _priors(recs) for exp, recs in records_by_experiment.items()}


def _histogram(values, labels=None):
    counts = Counter(values)
    keys = labels if labels is not None else sorted(counts)
    return [{'label': str(k), 'n': counts.get(k, 0)} for k in keys]


def _shape_profile(records, support, key):
    flag_key = 'truth_zero_deflation' if key == 'truth_shape' else 'model_zero_deflation'
    pairs = [(r[key], bool(r.get(flag_key))) for r in records
             if r.get(key) and (r['month'], r['_pid']) in support]
    if not pairs:
        return None
    feats = [p[0] for p in pairs]
    max_prob_bucket = lambda v: min(int(v // 20) * 20, 80)  # noqa: E731
    return {
        'n': len(pairs),
        'nz_bins': _histogram([f['nz_bins'] for f in feats], labels=list(range(11))),
        'max_prob': _histogram([max_prob_bucket(f['max_prob']) for f in feats],
                               labels=[0, 20, 40, 60, 80]),
        'mult5_share': _histogram([round(f['mult5_share'], 1) for f in feats],
                                  labels=[x / 10 for x in range(11)]),
        'zero_deflation_share': float(np.mean([flag for _, flag in pairs])),
        'all_zero_share': float(np.mean([f['all_zero'] for f in feats])),
    }


def _repeat_variance(records, support, arm, months, repeats):
    """Reuse evaluation/temperature.variance_components on the complete
    same-month repeat support (equal-person, unweighted)."""
    R = len(repeats)
    if R < 2:
        return {'repeats': R, 'repeat_label': '%d 遍' % R,
                'n_persons': len(support), 'n_months': len(months),
                'note': '只有单遍生成，无法做人内/人际方差分解。'}
    monthly = []
    for month in months:
        by_pid = defaultdict(dict)
        for r in records:
            pm = (r['month'], r['_pid'])
            if r['arm'] == arm and pm in support and r['month'] == month:
                by_pid[r['_pid']][r['repeat']] = r
        matrix = []
        for pid, grid in by_pid.items():
            if all(rep in grid and _finite(grid[rep].get('model_q9_mean')) for rep in repeats):
                matrix.append([grid[rep]['model_q9_mean'] for rep in repeats])
        if len(matrix) >= 2:
            monthly.append({'month': month, 'n_persons': len(matrix),
                            **variance_components(matrix)})
    if not monthly:
        return None

    def avg(key):
        vals = [m[key] for m in monthly if _finite(m.get(key))]
        return float(np.mean(vals)) if vals else None

    noise_adj = avg('noise_adjusted_between_variance_pp2')
    return {
        'repeats': R,
        'repeat_label': '%d 遍重复' % R,
        'n_persons': sum(m['n_persons'] for m in monthly),
        'n_months': len(monthly),
        'within_person_repeat_variance_pp2': avg('within_person_repeat_variance_pp2'),
        'between_person_repeat_mean_variance_pp2': avg('between_person_repeat_mean_variance_pp2'),
        'noise_adjusted_between_variance_pp2': noise_adj,
        'noise_adjusted_negative': bool(noise_adj is not None and noise_adj < 0),
        'note': ('等权人、未加权；与调查加权精度分列（复用 evaluation/temperature.py variance_components）。'
                 '四遍估计的是 API 采样波动而非真人重复变异；稳定的人际差别不自动等于正确预测。'
                 '负估计保留并解释，不截为零。'),
    }


def _structure(records):
    support, arms, repeats, _ = q9_support(records)
    months = sorted({pm[0] for pm in support})
    out = {}
    for arm in arms:
        cells = _arm_cells(records, support, arm, months, repeats)
        model_std = _mean(cells, 'pred_std_pp')
        truth_std = _mean(cells, 'truth_std_pp')
        note = ('本批真人跨人 std（月×遍等权平均）= %.2fpp，模型 = %.2fpp；跨人分布宽度差异以这两个读数为准。'
                % (truth_std, model_std)) if _finite(truth_std) and _finite(model_std) else None
        out[arm] = {
            'cross_person': {
                'model_std_pp': model_std,
                'truth_std_pp': truth_std,
                'model_iqr_pp': _mean(cells, 'pred_iqr_pp'),
                'truth_iqr_pp': _mean(cells, 'truth_iqr_pp'),
                'note': note,
            },
            'model_shape': _shape_profile(records, support, 'model_shape'),
            'truth_shape': _shape_profile(records, support, 'truth_shape'),
            'repeats': _repeat_variance(records, support, arm, months, repeats),
        }
    return out


@section_plugin('structure')
def section_structure(records_by_experiment, regime_lookup):
    return {exp: _structure(recs) for exp, recs in records_by_experiment.items()}


CDF_GRID_PP = list(range(0, 13))     # 0..12pp，加权经验 CDF 的展示网格
QUANTILE_LEVELS = (0.10, 0.25, 0.50, 0.75, 0.90)


def _cdf_curve(values, weights, grid=CDF_GRID_PP):
    """Weighted empirical CDF evaluated at the display grid (aggregate only)."""
    total = float(np.sum(weights))
    return [float(np.sum(weights[np.asarray(values) <= g]) / total) for g in grid]


def _quantile_set(values, weights):
    return {'p%d' % int(p * 100): float(_wquantile(np.asarray(values, float),
                                                   np.asarray(weights, float), p))
            for p in QUANTILE_LEVELS}


def _series_profile(recs, value_key, weight_key='weight'):
    vals, wts = [], []
    for r in recs:
        v, w = r.get(value_key), r.get(weight_key)
        if _finite(v) and _finite(w) and w > 0:
            vals.append(float(v))
            wts.append(float(w))
    if not vals:
        return None
    v = np.asarray(vals)
    w = np.asarray(wts)
    return {'cdf': _cdf_curve(v, w), 'q': _quantile_set(v, w)}


def _drill(records):
    """Month x group drill-down: weighted CDF curves and quantile intervals.

    Everything is computed per month on the common support; sparse cells keep
    the draft discipline (coverage only when n<10). Only aggregates (CDF
    values at a fixed grid, five quantiles) leave this layer.
    """
    support, arms, repeats, _ = q9_support(records)
    months = sorted({pm[0] for pm in support})
    first = arms[0]
    dims = {}
    for dim, title in GRID_DIMENSIONS:
        key = 'cell' if dim == 'six_cell' else dim
        groups = defaultdict(list)
        for r in records:
            pm = (r['month'], r['_pid'])
            if pm not in support or r['arm'] != first:
                continue
            label = r.get(key) if dim == 'six_cell' else (r.get(key) or 'missing')
            groups[label].append(r)
        order = (SIX_CELL_ORDER if dim == 'six_cell'
                 else sorted(groups, key=lambda x: (x == 'missing', str(x))))
        cells = {}
        for label in order:
            recs = groups.get(label)
            if not recs:
                continue
            by_month = defaultdict(list)
            for r in recs:
                by_month[r['month']].append(r)
            month_cells = {}
            for month in months:
                sub = by_month.get(month)
                if not sub:
                    continue
                pms = {(r['month'], r['_pid']) for r in sub}
                n_m = len(pms)
                w_m = [r['weight'] for r in sub if _finite(r.get('weight'))]
                ess_m = _kish_ess(w_m)
                cell = {'n': n_m, 'ess': ess_m, 'display_class': _display_class(n_m, ess_m)}
                if cell['display_class'] != 'coverage':
                    cell['truth'] = _series_profile(sub, 'truth_q9_mean')
                    cell['prior'] = _series_profile(sub, 'prior_q9_mean')
                    if cell['truth'] is None:
                        cell = {'n': n_m, 'ess': ess_m, 'display_class': 'coverage'}
                    else:
                        # model profiles need every arm's own values
                        by_arm = defaultdict(list)
                        for r in records:
                            pm2 = (r['month'], r['_pid'])
                            if pm2 in pms:
                                by_arm[r['arm']].append(r)
                        arms_prof = {}
                        for arm in arms:
                            prof = _series_profile(by_arm.get(arm, []), 'model_q9_mean')
                            if prof is not None:
                                arms_prof[arm] = prof
                        cell['arms'] = arms_prof
                month_cells[str(month)] = cell
            cells[label] = {'label_cn': _cn(dim, label), 'months': month_cells}
        dims[dim] = {'title': title, 'cells': cells}
    # secondary diagnostic: six-cell variance decomposition per month x repeat
    variance = {}
    for month in months:
        per_rep = []
        for rep in repeats:
            cell_means, cell_vars = [], []
            for label in SIX_CELL_ORDER:
                recs = [r for r in records if r['arm'] == first and r['month'] == month
                        and r['repeat'] == rep and (month, r['_pid']) in support
                        and r.get('cell') == label and _finite(r.get('truth_q9_mean'))]
                vals = [r['truth_q9_mean'] for r in recs]
                if len(vals) >= MIN_COVERAGE_N:
                    cell_means.append(float(np.mean(vals)))
                    cell_vars.append(float(np.var(vals, ddof=1)))
            if len(cell_means) >= 2:
                per_rep.append({'between': float(np.var(cell_means, ddof=1)),
                                'within': float(np.mean(cell_vars)),
                                'n_cells': len(cell_means)})
        if per_rep:
            variance[str(month)] = {
                'between_cell_var_pp2': float(np.mean([p['between'] for p in per_rep])),
                'within_cell_var_pp2': float(np.mean([p['within'] for p in per_rep])),
                'n_cells': max(p['n_cells'] for p in per_rep),
            }
    return {'grid': CDF_GRID_PP, 'quantile_note': '加权分位图，非 Tukey 箱线图',
            'dims': dims, 'variance': variance,
            'note': '只分解方差，不把各格中位数MAE相加当作总体误差贡献；CDF 与分位数均为共同支持上的加权聚合。'}


@section_plugin('drill')
def section_drill(records_by_experiment, regime_lookup):
    return {exp: _drill(recs) for exp, recs in records_by_experiment.items()}


def resolve_trials(metas):
    """Match each evaluation batch to its generation trial directory by
    protocol id (read-only local scan of outputs/*_trial_*). Attached onto
    each meta as meta['trial']; absent stays None and the UI shows 未接入.
    """
    by_proto = {}
    for m in metas:
        proto_id = (m.get('protocol') or {}).get('id')
        if proto_id:
            by_proto.setdefault(proto_id, m)
    for m in metas:
        m['trial'] = None
    seen = set()
    for proto_id, m in by_proto.items():
        if proto_id in seen:
            continue
        root = Path(m['summary_path']).resolve().parent.parent
        for trial in sorted(root.glob('*_trial_*')):
            proto_path = trial / 'protocol.json'
            if not proto_path.exists():
                continue
            try:
                proto = json.loads(proto_path.read_text())
            except (OSError, ValueError):
                continue
            if proto.get('id') == proto_id:
                info = {'dir': trial.name, 'protocol': proto,
                        'manifest_path': str(trial / 'manifest.json')}
                for other in metas:
                    if (other.get('protocol') or {}).get('id') == proto_id:
                        other['trial'] = info
                seen.add(proto_id)
                break


def _trial_inputs(meta):
    """Input-exposure facts from the generation trial (manifest/protocol/
    environment only; prompt-level diffs are not structured and are never
    guessed from response text)."""
    trial = meta.get('trial')
    if not trial:
        return {'trial_dir': None,
                'note': '未接入：未找到与协议 id 匹配的 trial 目录；输入暴露不猜测。'}
    proto = trial.get('protocol') or {}
    out = {
        'trial_dir': trial['dir'],
        'mechanism': proto.get('mechanism'),
        'information_change': proto.get('information_change'),
        'interactions': proto.get('interactions'),
        'prespecified_contrasts': proto.get('prespecified_contrasts'),
        'planned_calls': proto.get('planned_calls'),
        'months': {},
        'arm_diff': {
            'shared': '人口画像、本人历史/先验、问卷框架与公共环境层（environment.json layers，臂间共享）',
            'changed': proto.get('mechanism') or '未提供',
            'not_integrated': ['prompt 级逐字段差异未结构化接入（不从理由文本反推输入）'],
        },
        'source': 'trial 目录 manifest/protocol/environment.json（只读本地文件，零 API）',
    }
    manifest_path = trial.get('manifest_path')
    if manifest_path and Path(manifest_path).exists():
        try:
            jobs = json.loads(Path(manifest_path).read_text()).get('jobs', [])
            out['planned_jobs'] = len(jobs)
            caps = [j.get('cap_usd') for j in jobs if _finite(j.get('cap_usd'))]
            out['budget_cap_usd'] = float(np.sum(caps)) if caps else None
        except (OSError, ValueError):
            out['planned_jobs'] = None
    trial_dir = Path(meta['summary_path']).resolve().parent.parent / trial['dir']
    for month in (meta.get('protocol') or {}).get('months') or []:
        month_dir = trial_dir / str(month)
        env_path = month_dir / 'environment.json'
        month_info = {'layers': [], 'n_events': None, 'prompt_arms': []}
        if env_path.exists():
            try:
                env = json.loads(env_path.read_text())
                for layer in env.get('layers', []):
                    month_info['layers'].append({
                        'name': layer.get('name'), 'scope': layer.get('scope'),
                        'dynamics': layer.get('dynamics'), 'source': layer.get('source'),
                        'description': layer.get('description')})
                month_info['n_events'] = len(env.get('scheduled_events') or [])
            except (OSError, ValueError):
                month_info['layers_error'] = 'environment.json 解析失败'
        else:
            month_info['environment'] = '未提供'
        if month_dir.exists():
            for p in sorted(month_dir.glob('prompts_*.json')):
                month_info['prompt_arms'].append(p.stem.replace('prompts_', ''))
        else:
            month_info['month_dir'] = '未提供'
        out['months'][str(month)] = month_info
    return out


@section_plugin('inputs')
def section_inputs(records_by_experiment, regime_lookup, metas_by_experiment):
    return {exp: _trial_inputs(metas_by_experiment[exp])
            for exp in records_by_experiment}


def _quality(records, meta):
    support, arms, repeats, support_note = q9_support(records)
    q9_stats = _support_stats(support, _person_weights(records, support, arms, repeats))
    by_pm = defaultdict(dict)
    for r in records:
        by_pm[(r['month'], r['_pid'])][(r['arm'], r['repeat'])] = r
    usable = {}
    for arm in arms:
        arm_usable = {pm for pm, grid in by_pm.items()
                      if all((arm, rep) in grid and _valid_q9(grid[(arm, rep)]) for rep in repeats)}
        usable[arm] = len(arm_usable)
    q8s = q8_support(records, arms, repeats)
    by_arm = defaultdict(list)
    for r in records:
        by_arm[r['arm']].append(r)
    arms_q = {}
    for arm, recs in sorted(by_arm.items()):
        scorer = Counter(r.get('scorer_status') or 'missing' for r in recs)
        norm_known = [r['normalization_applied'] for r in recs
                      if r.get('normalization_applied') is not None]
        scorable = sum(1 for r in recs if _finite(r.get('model_q9_mean')))
        parsed_known = [r.get('response_parsed') for r in recs
                        if 'response_parsed' in r and r.get('response_parsed') is not None]
        raw_valid_known = [r.get('raw_validation_status') for r in recs
                           if r.get('raw_validation_status') is not None]
        # quality funnel: a stage is None (未接入) when its field is absent
        funnel = {
            'planned': (meta.get('trial') or {}).get('protocol', {}).get('planned_calls'),
            'attempted': len(recs),
            'parsed': (sum(1 for v in parsed_known if v) if parsed_known else None),
            'raw_valid': (sum(1 for v in raw_valid_known if v == 'valid')
                          if raw_valid_known else None),
            'normalized': (sum(1 for v in norm_known if v) if norm_known else None),
            'scorable': scorable,
        }
        arms_q[arm] = {
            'n_records': len(recs),
            'n_scorable': scorable,
            'missing_share': 1. - scorable / len(recs) if recs else None,
            'scorer_status': dict(sorted(scorer.items())),
            'normalization_applied_share': (float(np.mean([bool(v) for v in norm_known]))
                                            if norm_known else None),
            'weight_missing': sum(1 for r in recs if not _finite(r.get('weight'))),
            'q8_truth_coverage': float(np.mean([_finite(r.get('truth_q8_point')) for r in recs])),
            'q8_model_coverage': float(np.mean([_finite(r.get('model_q8_point')) for r in recs])),
            'q9_usable_person_months': usable.get(arm),
            'funnel': funnel,
        }
    # month x arm missing matrix (assigned records vs scorable)
    month_arm = {}
    for arm in arms:
        per_month = {}
        for r in by_arm[arm]:
            cell = per_month.setdefault(r['month'], {'assigned': 0, 'scorable': 0})
            cell['assigned'] += 1
            cell['scorable'] += 1 if _finite(r.get('model_q9_mean')) else 0
        month_arm[arm] = {str(m): {'assigned': c['assigned'], 'scorable': c['scorable'],
                                   'missing_share': (1 - c['scorable'] / c['assigned']
                                                     if c['assigned'] else None)}
                          for m, c in sorted(per_month.items())}
    # cost categories: reported ledger vs estimate vs budget cap vs missing
    summary_cost = meta.get('protocol', {}).get('estimated_cost_usd')
    cost = {'reported_or_estimated_usd': summary_cost,
            'basis': meta.get('protocol', {}).get('estimated_cost_basis'),
            'budget_cap_usd': None}
    trial = meta.get('trial') or {}
    manifest_path = trial.get('manifest_path')
    if manifest_path and Path(manifest_path).exists():
        try:
            jobs = json.loads(Path(manifest_path).read_text()).get('jobs', [])
            caps = [j.get('cap_usd') for j in jobs if _finite(j.get('cap_usd'))]
            if caps:
                cost['budget_cap_usd'] = float(np.sum(caps))
                cost['planned_jobs'] = len(jobs)
        except (OSError, ValueError):
            pass
    cost['display'] = '未接入' if summary_cost is None else (
        '%s %.2f USD' % ('已报告' if cost['basis'] == 'actual_ledger' else '估计', summary_cost))
    return {'arms': arms_q, 'protocol': meta.get('protocol', {}),
            'weight_field': meta.get('weight_field'),
            'q9_common_person_months': q9_stats['n_person_months'],
            'q8_common_person_months': len(q8s),
            'month_arm_missing': month_arm,
            'cost': cost,
            'support_note': support_note}


@section_plugin('quality')
def section_quality(records_by_experiment, regime_lookup, metas_by_experiment):
    return {exp: _quality(recs, metas_by_experiment[exp])
            for exp, recs in records_by_experiment.items()}


def _catalog(metas):
    """Experiment directory: pinned reference/latest plus research-purpose
    groups. Only batches actually discovered are listed."""
    entries = []
    for m in metas:
        entry = entry_for(m['batch'])
        protocol = m.get('protocol', {}) or {}
        entries.append({
            'batch': m['batch'], 'label': entry['label'],
            'section': entry['section'], 'mechanism_group': entry['mechanism_group'],
            'parent': entry['parent'], 'run_status': entry['run_status'],
            'evidence_stage': entry['evidence_stage'], 'note': entry['note'],
            'registered': m['registered'], 'status': m['status'],
            'skip_reason': m['skip_reason'],
            'model': protocol.get('model'),
            'months': len(protocol.get('months') or []),
            'n_per_month': protocol.get('n_per_month'),
            'repeats': len(protocol.get('generation_repeats') or []),
        })
    for e in entries:  # parent labels, only when the parent is in the scan
        e['parent_label'] = next((x['label'] for x in entries if x['batch'] == e['parent']), None)
    latest = None
    for e in entries:
        stamp = e['batch'].split('_evaluation_')[-1]
        if e['status'] == 'ok' and (latest is None or stamp > latest[0]):
            latest = (stamp, e['batch'])
    groups = []
    for section in SECTIONS:
        members = [e for e in entries if e['section'] == section]
        if not members:
            continue
        # within a section: newest first, then parents chained before children
        members.sort(key=lambda e: e['batch'], reverse=True)
        members.sort(key=lambda e: 0 if (e['parent'] is None or e['parent_label'] is None) else 1)
        groups.append({'section': section, 'entries': members})
    return {
        'reference_batch': REFERENCE_BATCH,
        'latest_batch': latest[1] if latest else None,
        'groups': groups,
        'note': '研究用途由登记表人工确定，不按人数自动判定；未登记批次归入待登记，不猜条件。只链接实际存在的实验。',
    }


def sanitize(obj):
    """Recursively replace non-finite floats so JSON output never carries NaN/Inf."""
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    return obj


COMPARABILITY_NOTICE = ('比较资格提醒：不同月份集合 / 不同人数 / 不同模型或采样参数的批次，'
                        '不能按原始均值直接排榜；仅同模型单项机制变化可同列细读。')

CONTROL_PREFERENCE = ('reference', 'baseline', 'shared_price', 'direct')


def pick_control_arm(arms):
    """The arm drawn in the 参考配置 role: a named control when present,
    otherwise the first arm. Never inferred from outcomes."""
    for pref in CONTROL_PREFERENCE:
        if pref in arms:
            return pref
    for arm in arms:
        if 'baseline' in arm:
            return arm
    return sorted(arms)[0]


def _ym(month):
    return '%s-%s' % (str(month)[:4], str(month)[4:])


def auto_facts(sections, arms, control):
    """Rule-based factual readouts for the overview tab (max three).

    Fixed templates only: no LLM, no causal language, no post-hoc findings
    turned into input rules. Each fact carries its evidence numbers so the
    page can show them on expansion.
    """
    primary = next((a for a in sorted(arms) if a != control), control)
    facts = []
    # rule 1: the month where the model's center error regresses most versus
    # the persistence baseline (threshold 0.3pp)
    rows = sections.get('monthly', {}).get(primary, {}).get('rows', [])
    per_month = defaultdict(list)
    for r in rows:
        if _finite(r.get('model_center_mae_pp')) and _finite(r.get('persist_center_mae_pp')):
            per_month[r['month']].append((r['model_center_mae_pp'],
                                          r['persist_center_mae_pp']))
    diffs = []
    for month in sorted(per_month):
        model = float(np.mean([v[0] for v in per_month[month]]))
        persist = float(np.mean([v[1] for v in per_month[month]]))
        diffs.append((month, model, persist, model - persist))
    if diffs:
        month, model, persist, gap = max(diffs, key=lambda t: t[3])
        if _finite(gap) and gap >= 0.3:
            facts.append({
                'id': 'regression_month',
                'text': ('中心误差在 %s 退步最大：模型 %.2fpp vs 照抄上期 %.2fpp'
                         '（模型−照抄 = %+.2fpp）' % (_ym(month), model, persist, gap)),
                'evidence': [
                    {'metric': '该月模型中心MAE（月×遍平均）', 'value_pp': model},
                    {'metric': '该月照抄中心MAE（月×遍平均）', 'value_pp': persist},
                    {'metric': '退步月模型−照抄（pp）', 'value_pp': gap},
                ],
            })
    # rule 2: low-prior band markedly closer to truth than the high band
    bands = sections.get('priors', {}).get(primary, {}).get('bands', {})
    lo, hi = bands.get('below_2', {}), bands.get('8_or_above', {})
    if _finite(lo.get('person_mae_pp')) and _finite(hi.get('person_mae_pp')):
        gap = hi['person_mae_pp'] - lo['person_mae_pp']
        if gap >= 1.0:
            facts.append({
                'id': 'low_prior_closer',
                'text': ('低先验端（<2%%）个人MAE %.2fpp，低于≥8%%档的 %.2fpp：'
                         '低端更接近真人，高端仍被压缩' % (lo['person_mae_pp'],
                                                 hi['person_mae_pp'])),
                'evidence': [
                    {'metric': '先验<2% 档个人MAE（pp）', 'value_pp': lo['person_mae_pp']},
                    {'metric': '先验≥8% 档个人MAE（pp）', 'value_pp': hi['person_mae_pp']},
                    {'metric': '高端−低端差（pp）', 'value_pp': gap},
                ],
            })
    # rule 3: two mechanism arms barely differ on the group-center statistic
    overview = sections.get('overview', {}).get('q9', {})
    pairs = []
    for i, a in enumerate(sorted(arms)):
        for b in sorted(arms)[i + 1:]:
            va, vb = overview.get(a, {}).get('center_mae_pp'), overview.get(b, {}).get('center_mae_pp')
            if _finite(va) and _finite(vb):
                pairs.append((a, b, abs(va - vb)))
    if pairs:
        a, b, gap = min(pairs, key=lambda t: t[2])
        if gap <= 0.1:
            facts.append({
                'id': 'small_arm_gap',
                'text': ('臂 %s 与 %s 的群体中心差异仅 %.2fpp，'
                         '不能据此认定机制有效或无效' % (a, b, gap)),
                'evidence': [
                    {'metric': '%s 群体中位数MAE（pp）' % a, 'value_pp': overview[a]['center_mae_pp']},
                    {'metric': '%s 群体中位数MAE（pp）' % b, 'value_pp': overview[b]['center_mae_pp']},
                    {'metric': '两臂差（pp）', 'value_pp': gap},
                ],
            })
    return facts[:3]


SECTION_GUIDES = {
    'overview': '总览：主读数为群体中位数MAE（每月×每遍的 |模型中位−真人中位| 等权平均），'
                '同支持照抄上期为机械基线；个人MAE与个人绝对误差中位数另列，不与主统计量混称。',
    'monthly': '逐月与剧烈变化期：逐月逐遍先算再等权平均；剧烈月（|Δ真值中位|≥0.2pp）中方向正确即机械占优，'
               '必须与平稳月同报；中心口径与个人口径并列。',
    'grid': '人群网格：六格（学历×在职）与独立单变量切片；每格为跨月混合分布（非月内），'
            '按月报告覆盖，n<10 仅覆盖、10–19 灰色探索、n≥20 且 ESS≥10 正常。',
    'priors': '先验与更新：上期预期四档是前置特征分组；“真人上调/稳定/下调”使用本期真值，仅用于评价。',
    'structure': '回答结构：跨人 std/IQR 为月×遍等权平均；形状特征为跨月混合分布；'
                 '重复波动用 temperature.variance_components 方法，按实际遍数标注，负估计保留。',
    'quality': '质量与元数据：共同支持、各臂可用支持敏感性、scorer 状态、归一化比例与协议信息；'
               '跨批比较前请先核对本表。',
}


def build_panel(records, metas, regime_lookup, only_sections=None):
    records_by_experiment = defaultdict(list)
    for r in records:
        records_by_experiment[r['experiment']].append(r)
    metas_by_experiment = {m['batch']: m for m in metas}
    resolve_trials(metas)      # attach meta['trial'] for inputs/quality plugins
    names = only_sections or [n for n in SECTION_PLUGINS if n != 'catalog']
    META_PLUGINS = ('quality', 'inputs')
    sections = {}
    for name in names:
        plugin = SECTION_PLUGINS[name]
        if name in META_PLUGINS:
            sections[name] = plugin(records_by_experiment, regime_lookup, metas_by_experiment)
        else:
            sections[name] = plugin(records_by_experiment, regime_lookup)
    experiments = {}
    for exp, recs in records_by_experiment.items():
        meta = metas_by_experiment[exp]
        experiments[exp] = {
            'label': meta['label'], 'registered': meta['registered'],
            'description': meta['description'], 'protocol': meta['protocol'],
            'weight_field': meta['weight_field'], 'n_records': meta['n_records'],
            'registry': meta.get('registry', {}),
            'arms': sorted({r['arm'] for r in recs}),
            'months': sorted({r['month'] for r in recs}),
            'repeats': sorted({r['repeat'] for r in recs if r['repeat'] is not None}),
            'q8_available': bool(sections.get('overview', {}).get(exp, {}).get('q8')),
            'control_arm': pick_control_arm(sorted({r['arm'] for r in recs})),
            'facts': auto_facts({name: sections[name][exp] for name in names},
                                sorted({r['arm'] for r in recs}),
                                pick_control_arm(sorted({r['arm'] for r in recs}))),
            'sections': {name: sections[name][exp] for name in names},
        }
    order = sorted(experiments,
                   key=lambda e: (list(REGISTRY).index(e) if e in REGISTRY else len(REGISTRY), e))
    catalog = _catalog(metas) if 'catalog' not in names else sections['catalog']
    panel = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'comparability_notice': COMPARABILITY_NOTICE,
        'section_guides': SECTION_GUIDES,
        'source_batches': [{k: m[k] for k in ('batch', 'label', 'registered', 'status',
                                              'skip_reason', 'n_cases', 'n_records')}
                           for m in metas],
        'experiments': {k: experiments[k] for k in order},
        'catalog': catalog,
        'regime_lookup': {str(k): v for k, v in regime_lookup.items()},
        'notes': ['全部计算离线完成，零 API 调用。',
                  'HTML 仅嵌聚合数据，不含 userid/agent_id、逐人记录或原始十档向量。'],
    }
    return sanitize(panel)
