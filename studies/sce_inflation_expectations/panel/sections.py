"""Six fixed analysis sections over canonical records; plugins by registry.

Common display discipline (from docs/workstreams/20261020_procurement/
structured_analysis_panel_design.md):
- n<10 cells show only coverage/ESS (suppressed), never distribution judgments;
- missing / not-provided values stay absent, never filled with zero;
- every number carries n and a weight convention note (ESS=(Σw)²/Σw²);
- per-person error metrics and pooled distribution metrics are separate rows.
Weight convention: each person's weight is split equally across that person's
generation repeats, so repeats never multiply people; n counts person-months.
Q9 is the main line; Q8 rides the overview toggle only.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone

import numpy as np

from studies.sce_inflation_expectations.evaluation.metrics import quantile, wasserstein1
from studies.sce_inflation_expectations.evaluation.response_gap import direction, prior_band
from studies.sce_inflation_expectations.panel.adapters import REGISTRY

MIN_CELL_N = 10
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


def _ess(weights):
    weights = [w for w in weights if _finite(w) and w > 0]
    if not weights:
        return None
    total = sum(weights)
    return float(total ** 2 / sum(w * w for w in weights))


def _wquantile(values, weights, p):
    return quantile(np.asarray(values, float), np.asarray(weights, float), p)


def _rows(records, pred_key, truth_key, require_prior=False):
    """(pred, truth, weight) triples with finite positive weights.

    require_prior keeps exactly the model support rows whose prior is finite,
    so persistence is computed on an identical person-month support.
    """
    rows = []
    for r in records:
        pred, truth = r.get(pred_key), r.get(truth_key)
        if not (_finite(pred) and _finite(truth)):
            continue
        if require_prior and not _finite(r.get('prior_q9_mean')):
            continue
        weight = r.get('weight')
        if not (_finite(weight) and weight > 0):
            continue
        rows.append((float(pred), float(truth), float(weight)))
    return rows


def _metrics_from_rows(rows, n_person_months, ess):
    cell = {'n': n_person_months, 'ess': ess,
            'suppressed': n_person_months < MIN_CELL_N}
    if cell['suppressed'] or not rows:
        return cell
    p = np.asarray([r[0] for r in rows])
    y = np.asarray([r[1] for r in rows])
    w = np.asarray([r[2] for r in rows])
    wn = w / w.sum()
    err = p - y
    med_p, med_y = _wquantile(p, w, .5), _wquantile(y, w, .5)
    cell.update({
        'mae_pp': float(wn @ np.abs(err)),
        'median_abs_error_pp': _wquantile(np.abs(err), w, .5),
        'bias_pp': float(wn @ err),
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


def _cell(records, pred_key='model_q9_mean', truth_key='truth_q9_mean',
          require_prior=False):
    rows = _rows(records, pred_key, truth_key, require_prior=require_prior)
    n_pm = len({r['_pid'] for r in records
                if _finite(r.get(pred_key)) and _finite(r.get(truth_key))
                and (not require_prior or _finite(r.get('prior_q9_mean')))})
    ess = _ess([r['weight'] for r in records if _finite(r.get('weight'))])
    return _metrics_from_rows(rows, n_pm, ess)


def _identical_support(records):
    """Records where model, truth and prior are all finite: the persistence
    baseline is only defined on exactly the model's person-month support."""
    return [r for r in records if _finite(r.get('model_q9_mean'))
            and _finite(r.get('truth_q9_mean'))
            and _finite(r.get('prior_q9_mean'))]


def _equal_month_mean(cells, key):
    values = [c[key] for c in cells if not c.get('suppressed') and _finite(c.get(key))]
    return float(np.mean(values)) if values else None


def _overview(records):
    """Section 1: per-experiment x arm overview + persistence + Q8 side line."""
    by_arm = defaultdict(list)
    for r in records:
        by_arm[r['arm']].append(r)
    out, q8 = {}, {}
    for arm, recs in sorted(by_arm.items()):
        monthly, monthly_ident = [], []
        for month in sorted({r['month'] for r in recs}):
            sub = [r for r in recs if r['month'] == month]
            monthly.append({'month': month, **_cell(sub)})
            identical_sub = _identical_support(sub)
            monthly_ident.append({'month': month,
                                  **_cell(identical_sub, pred_key='prior_q9_mean')})
        pooled = [r for m in monthly if not m['suppressed'] for r in recs if r['month'] == m['month']]
        row = {
            'n_person_months': sum(m['n'] for m in monthly),
            'n_months': len([m for m in monthly if not m['suppressed']]),
            'ess': _ess([r['weight'] for r in pooled]),
            'mae_pp': _equal_month_mean(monthly, 'mae_pp'),
            'median_abs_error_pp': _equal_month_mean(monthly, 'median_abs_error_pp'),
            'bias_pp': _equal_month_mean(monthly, 'bias_pp'),
            'w1_pp': _equal_month_mean(monthly, 'w1_pp'),
            'centered_w1_pp': _equal_month_mean(monthly, 'centered_w1_pp'),
            'pred_median_pp': _equal_month_mean(monthly, 'pred_median_pp'),
            'truth_median_pp': _equal_month_mean(monthly, 'truth_median_pp'),
            'pred_iqr_pp': _equal_month_mean(monthly, 'pred_iqr_pp'),
            'truth_iqr_pp': _equal_month_mean(monthly, 'truth_iqr_pp'),
            'pred_std_pp': _equal_month_mean(monthly, 'pred_std_pp'),
            'truth_std_pp': _equal_month_mean(monthly, 'truth_std_pp'),
            'persistence': None,
        }
        if any(not m['suppressed'] for m in monthly_ident):
            row['persistence'] = {
                'n_identical_support': sum(m['n'] for m in monthly_ident),
                'mae_pp': _equal_month_mean(monthly_ident, 'mae_pp'),
                'median_abs_error_pp': _equal_month_mean(monthly_ident, 'median_abs_error_pp'),
                'bias_pp': _equal_month_mean(monthly_ident, 'bias_pp'),
                'w1_pp': _equal_month_mean(monthly_ident, 'w1_pp'),
                'pred_median_pp': _equal_month_mean(monthly_ident, 'pred_median_pp'),
            }
        out[arm] = row
        # Q8 side line: per-person point MAE where both sides provide a point
        q8rows = _rows(recs, 'model_q8_point', 'truth_q8_point')
        q8[arm] = _metrics_from_rows(
            q8rows, len({r['_pid'] for r in recs if _finite(r.get('model_q8_point'))
                         and _finite(r.get('truth_q8_point'))}),
            _ess([r['weight'] for r in recs if _finite(r.get('weight'))]))
    return {'q9': out, 'q8': q8,
            'notes': ['口径：每人权重在其生成遍数间均分，遍数不增人数；n 计人×月。',
                      '汇总指标为逐月计算后等月平均；n/ESS 为合并支持。']}


@section_plugin('overview')
def section_overview(records_by_experiment, regime_lookup):
    return {exp: _overview(recs) for exp, recs in records_by_experiment.items()}


def _monthly_and_regimes(records, regime_lookup):
    by_arm = defaultdict(list)
    for r in records:
        by_arm[r['arm']].append(r)
    out = {}
    for arm, recs in sorted(by_arm.items()):
        rows = []
        for month in sorted({r['month'] for r in recs}):
            sub = [r for r in recs if r['month'] == month]
            cell = _cell(sub)
            regime = regime_lookup.get(month, {}).get('regime', 'unknown')
            row = {'month': month, 'regime': regime,
                   'n': cell['n'], 'ess': cell['ess'], 'suppressed': cell['suppressed']}
            if not cell['suppressed']:
                isub = _identical_support(sub)
                pcell = _cell(isub, pred_key='prior_q9_mean') if isub else {}
                row.update({
                    'truth_median_pp': cell['truth_median_pp'],
                    'model_median_pp': cell['pred_median_pp'],
                    'persist_median_pp': pcell.get('pred_median_pp'),
                    'model_mae_pp': cell['mae_pp'],
                    'persist_mae_pp': pcell.get('mae_pp'),
                    'model_bias_pp': cell['bias_pp'],
                    'w1_pp': cell['w1_pp'],
                })
            rows.append(row)
        table = {}
        for regime in ('calm', 'drastic'):
            group = [r for r in rows if r['regime'] == regime and not r['suppressed']]
            table[regime] = {
                'n_months': len(group),
                'model_mae_pp': float(np.mean([r['model_mae_pp'] for r in group])) if group else None,
                'persist_mae_pp': float(np.mean([r['persist_mae_pp'] for r in group])) if group else None,
            }
        drastic, calm = table['drastic'], table['calm']
        skill = (drastic['persist_mae_pp'] - drastic['model_mae_pp']
                 if _finite(drastic['persist_mae_pp']) and _finite(drastic['model_mae_pp']) else None)
        out[arm] = {'rows': rows, 'regime_table': table,
                    'skill_s_drastic_pp': skill,
                    'notes': ['机制月判定为事后口径（|Δ加权中位|≥0.2pp），非事前识别。',
                              '剧烈月中方向正确即机械占优，必须与平稳月同报。',
                              '批次月份非连续，Δ 不可链式计算；机制标签来自全样本真值序列。']}
    return out


@section_plugin('monthly')
def section_monthly(records_by_experiment, regime_lookup):
    return {exp: _monthly_and_regimes(recs, regime_lookup)
            for exp, recs in records_by_experiment.items()}


def _dimension_cells(records, dim):
    key = 'cell' if dim == 'six_cell' else dim
    groups = defaultdict(list)
    for r in records:
        label = r.get(key) if dim == 'six_cell' else (r.get(key) or 'missing')
        groups[label].append(r)
    order = (SIX_CELL_ORDER if dim == 'six_cell'
             else sorted(groups, key=lambda x: (x == 'missing', str(x))))
    cells = {}
    for label in order:
        recs = groups.get(label)
        if not recs:
            continue
        cell = _cell(recs)
        identical = _identical_support(recs)
        pcell = _cell(identical, pred_key='prior_q9_mean') if identical else None
        cell['persist_mae_pp'] = pcell.get('mae_pp') if pcell else None
        cell['persist_bias_pp'] = pcell.get('bias_pp') if pcell else None
        cell['label_cn'] = _cn(dim, label)
        cells[label] = cell
    return cells


def _grid(records):
    by_arm = defaultdict(list)
    for r in records:
        by_arm[r['arm']].append(r)
    return {arm: {dim: _dimension_cells(recs, dim) for dim, _ in GRID_DIMENSIONS}
            for arm, recs in sorted(by_arm.items())}


@section_plugin('grid')
def section_grid(records_by_experiment, regime_lookup):
    return {exp: _grid(recs) for exp, recs in records_by_experiment.items()}


def _group_block(records):
    """Shared metric block for prior-band and truth-direction cells."""
    cell = _cell(records)
    identical = _identical_support(records)
    pcell = _cell(identical, pred_key='prior_q9_mean') if identical else None
    block = {'n': cell['n'], 'ess': cell['ess'], 'suppressed': cell['suppressed']}
    if cell['suppressed']:
        return block
    rows = _rows(records, 'model_q9_mean', 'truth_q9_mean')
    deltas_model, deltas_truth, dw = [], [], []
    for r in records:
        if not (_finite(r.get('model_q9_mean')) and _finite(r.get('truth_q9_mean'))
                and _finite(r.get('prior_q9_mean')) and _finite(r.get('weight'))):
            continue
        deltas_model.append(r['model_q9_mean'] - r['prior_q9_mean'])
        deltas_truth.append(r['truth_q9_mean'] - r['prior_q9_mean'])
        dw.append(r['weight'])
    block.update({
        'truth_mean_pp': cell['truth_mean_pp'],
        'model_mean_pp': cell['pred_mean_pp'],
        'prior_mean_pp': float(np.sum([r['prior_q9_mean'] * r['weight'] for r in identical])
                               / np.sum([r['weight'] for r in identical])) if identical else None,
        'model_mae_pp': cell['mae_pp'],
        'persist_mae_pp': pcell.get('mae_pp') if pcell else None,
        'model_bias_pp': cell['bias_pp'],
        'w1_pp': cell['w1_pp'],
        'delta_w1_pp': (wasserstein1(np.asarray(deltas_model), np.asarray(dw),
                                     np.asarray(deltas_truth), np.asarray(dw))
                        if len(deltas_model) >= 2 else None),
    })
    return block


def _priors(records):
    by_arm = defaultdict(list)
    for r in records:
        by_arm[r['arm']].append(r)
    band_order = ('below_2', '2_to_below_4', '4_to_below_8', '8_or_above')
    band_cn = {'below_2': '上期预期<2%', '2_to_below_4': '2–4%',
               '4_to_below_8': '4–8%', '8_or_above': '≥8%'}
    out = {}
    for arm, recs in sorted(by_arm.items()):
        with_prior = [r for r in recs if _finite(r.get('prior_q9_mean'))]
        bands, directions = {}, {}
        for band in band_order:
            sub = [r for r in with_prior
                   if prior_band(r['prior_q9_mean']) == band]
            block = _group_block(sub) if sub else {'n': 0, 'ess': None, 'suppressed': True}
            block['label_cn'] = band_cn[band]
            bands[band] = block
        with_delta = [r for r in with_prior if _finite(r.get('truth_q9_mean'))]
        for bucket in ('up', 'stable', 'down'):
            sub = [r for r in with_delta
                   if direction(r['truth_q9_mean'] - r['prior_q9_mean'], UPDATE_THRESHOLD_PP) == bucket]
            block = _group_block(sub) if sub else {'n': 0, 'ess': None, 'suppressed': True}
            block['label_cn'] = {'up': '真人本期上调', 'stable': '真人本期稳定(±0.5pp)',
                                 'down': '真人本期下调'}[bucket]
            directions[bucket] = block
        out[arm] = {'bands': bands, 'directions': directions,
                    'notes': ['先验四档为前置特征分组（<2、2–4、4–8、≥8%，开发期阈值）。',
                              '上调/稳定/下调分组使用本期真值，仅用于评价，不能用于分配输入。']}
    return out


@section_plugin('priors')
def section_priors(records_by_experiment, regime_lookup):
    return {exp: _priors(recs) for exp, recs in records_by_experiment.items()}


def _histogram(values, labels=None):
    counts = Counter(values)
    keys = labels if labels is not None else sorted(counts)
    return [{'label': str(k), 'n': counts.get(k, 0)} for k in keys]


def _shape_profile(records, key):
    flag_key = 'truth_zero_deflation' if key == 'truth_shape' else 'model_zero_deflation'
    pairs = [(r[key], bool(r.get(flag_key))) for r in records if r.get(key)]
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


def _repeat_diagnostics(records):
    groups = defaultdict(list)
    for r in records:
        if _finite(r.get('model_q9_mean')) and _finite(r.get('weight')):
            groups[r['_pid']].append(r)
    persons = {pid: rs for pid, rs in groups.items() if len(rs) >= 2}
    if not persons:
        return None
    by_month = defaultdict(list)
    for pid, rs in persons.items():
        by_month[rs[0]['month']].append((pid, rs))
    within_month, between_month = [], []
    for month in sorted(by_month):
        rows = by_month[month]
        person_mean, person_w, within = [], [], []
        for pid, rs in rows:
            means = np.asarray([r['model_q9_mean'] for r in rs])
            w = float(np.sum([r['weight'] for r in rs]))
            person_mean.append(float(means.mean()))
            person_w.append(w)
            within.append(float(means.std()))
        wn = np.asarray(person_w) / np.sum(person_w)
        within_month.append(float(np.dot(wn, within)))
        pm = np.asarray(person_mean)
        between_month.append(float(np.sqrt(np.dot(wn, (pm - np.dot(wn, pm)) ** 2))))
    between = float(np.mean(between_month))
    within = float(np.mean(within_month))
    return {'within_person_std_pp': within,
            'between_person_std_pp': between,
            'deducted_between_var_pp2': between ** 2 - within ** 2,
            'n_persons': len(persons), 'n_months': len(by_month),
            'note': '两遍重复只能给有限的波动诊断；扣除项为负时保留并解释，不截为零。'}


def _structure(records):
    by_arm = defaultdict(list)
    for r in records:
        by_arm[r['arm']].append(r)
    out = {}
    for arm, recs in sorted(by_arm.items()):
        monthly = []
        for month in sorted({r['month'] for r in recs}):
            cell = _cell([r for r in recs if r['month'] == month])
            if not cell['suppressed']:
                monthly.append(cell)
        repeat = _repeat_diagnostics(recs)
        out[arm] = {
            'cross_person': {
                'model_std_pp': _equal_month_mean(monthly, 'pred_std_pp'),
                'truth_std_pp': _equal_month_mean(monthly, 'truth_std_pp'),
                'model_iqr_pp': _equal_month_mean(monthly, 'pred_iqr_pp'),
                'truth_iqr_pp': _equal_month_mean(monthly, 'truth_iqr_pp'),
            },
            'model_shape': _shape_profile(recs, 'model_shape'),
            'truth_shape': _shape_profile(recs, 'truth_shape'),
            'repeats': repeat,
            'note': '跨人 std 是本项目核心痛点：真人跨人 std 约 5.5–7.6pp，模型普遍不足 1pp。',
        }
    return out


@section_plugin('structure')
def section_structure(records_by_experiment, regime_lookup):
    return {exp: _structure(recs) for exp, recs in records_by_experiment.items()}


def _quality(records, meta):
    by_arm = defaultdict(list)
    for r in records:
        by_arm[r['arm']].append(r)
    arms = {}
    for arm, recs in sorted(by_arm.items()):
        scorer = Counter(r.get('scorer_status') or 'missing' for r in recs)
        norm_known = [r['normalization_applied'] for r in recs
                      if r.get('normalization_applied') is not None]
        scorable = sum(1 for r in recs if _finite(r.get('model_q9_mean')))
        arms[arm] = {
            'n_records': len(recs),
            'n_scorable': scorable,
            'missing_share': 1. - scorable / len(recs) if recs else None,
            'scorer_status': dict(sorted(scorer.items())),
            'normalization_applied_share': (float(np.mean([bool(v) for v in norm_known]))
                                            if norm_known else None),
            'weight_missing': sum(1 for r in recs if not _finite(r.get('weight'))),
            'q8_truth_coverage': float(np.mean([_finite(r.get('truth_q8_point')) for r in recs])),
            'q8_model_coverage': float(np.mean([_finite(r.get('model_q8_point')) for r in recs])),
        }
    return {'arms': arms, 'protocol': meta.get('protocol', {}),
            'weight_field': meta.get('weight_field')}


@section_plugin('quality')
def section_quality(records_by_experiment, regime_lookup, metas_by_experiment):
    return {exp: _quality(recs, metas_by_experiment[exp])
            for exp, recs in records_by_experiment.items()}


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

SECTION_GUIDES = {
    'overview': '总览：逐人误差（|模型−真人| 的加权均值与中位数）回答“总体差多少”，'
                '跨人 W1/去心 W1 回答“分布差多少”；照抄上期是同支持下的机械基线，模型须先赢过它。',
    'monthly': '逐月与剧烈变化期：折线给出真人/模型/照抄的逐月中位与 MAE；剧烈月（|Δ真值中位|≥0.2pp）'
               '中方向正确即机械占优，必须与平稳月同报。',
    'grid': '人群网格：六格（学历×在职）用于稳定覆盖与抽样，不认定解释力最强；'
            '年龄/收入/数理/地区/住房为独立切片，n<10 只显示覆盖灰显。',
    'priors': '先验与更新：上期预期四档是前置特征分组；“真人上调/稳定/下调”使用本期真值，仅用于评价。',
    'structure': '回答结构：跨人 std 是核心痛点——真人跨人 std 约 5.5–7.6pp，模型普遍不足 1pp；'
                 '形状特征与两遍重复用来区分“随机撒宽”与“真实异质性”。',
    'quality': '质量与元数据：scorer 状态、归一化比例、缺失率与协议信息；跨批比较前请先核对本表。',
}


def build_panel(records, metas, regime_lookup, only_sections=None):
    records_by_experiment = defaultdict(list)
    for r in records:
        records_by_experiment[r['experiment']].append(r)
    metas_by_experiment = {m['batch']: m for m in metas}
    names = only_sections or list(SECTION_PLUGINS)
    sections = {}
    for name in names:
        plugin = SECTION_PLUGINS[name]
        if name == 'quality':
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
            'arms': sorted({r['arm'] for r in recs}),
            'months': sorted({r['month'] for r in recs}),
            'repeats': sorted({r['repeat'] for r in recs if r['repeat'] is not None}),
            'q8_available': any(_finite(r.get('model_q8_point')) and _finite(r.get('truth_q8_point'))
                                for r in recs),
            'sections': {name: sections[name][exp] for name in names},
        }
    order = sorted(experiments,
                   key=lambda e: (list(REGISTRY).index(e) if e in REGISTRY else len(REGISTRY), e))
    panel = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'comparability_notice': COMPARABILITY_NOTICE,
        'section_guides': SECTION_GUIDES,
        'source_batches': [{k: m[k] for k in ('batch', 'label', 'registered', 'status',
                                              'skip_reason', 'n_cases', 'n_records')}
                           for m in metas],
        'experiments': {k: experiments[k] for k in order},
        'regime_lookup': {str(k): v for k, v in regime_lookup.items()},
        'notes': ['全部计算离线完成，零 API 调用。', 'HTML 仅嵌聚合数据，不含 userid/agent_id 或逐人记录。'],
    }
    return sanitize(panel)
