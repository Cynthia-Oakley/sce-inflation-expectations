"""Evaluation-only Q1 increments given a person's previous official Q9 mean.

Reads one hash-verified cache, writes aggregate results only, and calls no API.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2

from population_associations import (
    BASE, ROOT, contrast, design, dump, fit_month_model, month_residual, sha,
)

CACHE = ROOT / 'outputs/sce_population_associations_20261015_v1/analysis_frame_private.parquet'
PERIODS = {'2020_2022': (202001, 202212), '2023_2025_10': (202301, 202510)}
CONTROLS = {**BASE, 'education_fine': [5, 1, 2, 3, 4, 6, 7, 8, 9]}
STATUS = ['same', 'worse', 'better']
TRANSITIONS = ['same_to_same'] + [
    f'{before}_to_{after}' for before in STATUS for after in STATUS
    if (before, after) != ('same', 'same')
]


def counts(frame):
    return {'rows': len(frame), 'persons': int(frame.userid.nunique()),
            'months': int(frame.date.nunique())}


def attach_adjacent(frame):
    """Build lags before period slicing; December can supply January's lag."""
    f = frame.sort_values(['userid', 'date']).reset_index(drop=True).copy()
    if f.duplicated(['userid', 'date']).any():
        raise ValueError('Duplicate person-month keys')
    previous = f.groupby('userid', sort=False).shift()
    month = f.date // 100 * 12 + f.date % 100
    previous_month = previous.date // 100 * 12 + previous.date % 100
    f['calendar_adjacent'] = month.sub(previous_month).eq(1)
    f['pair_panel_valid'] = (
        f.timeline_consistent.eq(True) & previous.timeline_consistent.eq(True)
        & f.tenure_valid.eq(True) & previous.tenure_valid.eq(True)
    )
    f['lag_q1'] = previous.financial_change.where(f.calendar_adjacent)
    f['previous_q9_official'] = previous.Q9_mean.where(f.calendar_adjacent)
    # Independently reconstructed official lags must agree with the cached join.
    mask = f.calendar_adjacent
    if not np.allclose(f.loc[mask, 'lag_q9'], f.loc[mask, 'previous_q9_official'],
                       rtol=0, atol=0, equal_nan=True):
        raise ValueError('Cached Q9 lag does not match strict-calendar reconstruction')
    for source, target in [('financial_change', 'q1_status'), ('lag_q1', 'lag_q1_status')]:
        f[target] = f[source].map({1: 'worse', 2: 'worse', 3: 'same', 4: 'better', 5: 'better'})
    f['transition'] = f.lag_q1_status + '_to_' + f.q1_status
    f['q9_update'] = f.Q9_mean - f.previous_q9_official
    return f


def joint(model, positions):
    beta = model['coef'][positions]
    covariance = model['cov'][np.ix_(positions, positions)]
    statistic = float(beta @ np.linalg.solve(covariance, beta))
    return {'chi2': statistic, 'df': len(positions),
            'p_unadjusted_exploratory': float(chi2.sf(statistic, len(positions)))}


def fit(frame, finance_specs, outcome='Q9_mean'):
    x, names, blocks = design(frame, {**CONTROLS, **finance_specs})
    x = np.column_stack([x, frame.previous_q9_official])
    names.append('previous_q9_official')
    model = fit_month_model(frame[outcome], x, frame.weight, frame.date, frame.userid)
    finance_positions = [i for field in finance_specs for i in blocks[field]]
    report = {**counts(frame), 'R2_within_month_in_sample': model['R2_within_month'],
              'finance_coefficients_pp': {
                  name: contrast(model, np.eye(len(names))[i])
                  for i, name in enumerate(names) if i in finance_positions},
              'lag_q9_coefficient': contrast(model, np.eye(len(names))[-1]),
              'joint_by_factor': {field: joint(model, blocks[field]) for field in finance_specs}}
    if finance_positions:
        report['joint_all_finance'] = joint(model, finance_positions)
    return report, model, names, x


def analyze_period(frame, start, end):
    original = frame.loc[frame.date.between(start, end)].copy()
    adjacent = original.loc[original.calendar_adjacent].copy()
    panel = adjacent.loc[adjacent.pair_panel_valid].copy()
    mask = np.isfinite(panel.weight) & panel.weight.gt(0)
    mask &= np.isfinite(panel.Q9_mean) & np.isfinite(panel.previous_q9_official)
    for field, levels in CONTROLS.items():
        mask &= panel[field].isin(levels)
    before_q1 = panel.loc[mask].copy()
    valid = before_q1.q1_status.isin(STATUS) & before_q1.lag_q1_status.isin(STATUS)
    f = before_q1.loc[valid].copy()
    models = {}
    specs = {
        'base': {},
        'add_previous_q1': {'lag_q1_status': STATUS},
        'add_current_q1': {'q1_status': STATUS},
        'add_both_q1': {'lag_q1_status': STATUS, 'q1_status': STATUS},
        'add_q1_transition': {'transition': TRANSITIONS},
    }
    internals = {}
    for key, fields in specs.items():
        models[key], *internals[key] = fit(f, fields)
        models[key]['R2_increment_vs_base'] = (
            models[key]['R2_within_month_in_sample'] - models['base']['R2_within_month_in_sample'])
    models['add_both_q1']['R2_increment_vs_previous_q1'] = (
        models['add_both_q1']['R2_within_month_in_sample']
        - models['add_previous_q1']['R2_within_month_in_sample'])
    models['add_both_q1']['R2_increment_vs_current_q1'] = (
        models['add_both_q1']['R2_within_month_in_sample']
        - models['add_current_q1']['R2_within_month_in_sample'])
    models['add_q1_transition']['R2_increment_vs_additive_both'] = (
        models['add_q1_transition']['R2_within_month_in_sample']
        - models['add_both_q1']['R2_within_month_in_sample'])
    # Conditioning the Q9 update on its previous level is algebraically the same
    # regression: only the coefficient on the previous Q9 level falls by one.
    updates = {}
    max_beta_difference = 0.
    for key in ['base', 'add_both_q1', 'add_q1_transition']:
        report, update_fit, names, _ = fit(f, specs[key], 'q9_update')
        expected = internals[key][0]['coef'].copy()
        expected[-1] -= 1
        error = float(np.max(np.abs(update_fit['coef'] - expected)))
        max_beta_difference = max(max_beta_difference, error)
        if error > 1e-9:
            raise ValueError('Level/update algebraic equivalence failed')
        updates[key] = {'R2_within_month_in_sample': report['R2_within_month_in_sample'],
                        'lag_q9_coefficient': report['lag_q9_coefficient']}
        updates[key]['R2_increment_vs_base'] = (
            updates[key]['R2_within_month_in_sample'] - updates['base']['R2_within_month_in_sample'])
    transition_counts = {}
    for label in TRANSITIONS:
        group = f.loc[f.transition.eq(label)]
        transition_counts[label] = counts(group)
    return {
        'sample_flow': {'original_period': counts(original), 'calendar_adjacent': counts(adjacent),
                        'also_valid_current_and_previous_panel_tenure': counts(panel),
                        'complete_weight_q9_lag_q9_controls_before_q1': counts(before_q1),
                        'common_complete_both_q1_all_models': counts(f)},
        'current_q1_five_category_counts': {str(k): int(f.financial_change.eq(k).sum()) for k in range(1, 6)},
        'previous_q1_five_category_counts': {str(k): int(f.lag_q1.eq(k).sum()) for k in range(1, 6)},
        'five_category_unchanged_rows': int(f.financial_change.eq(f.lag_q1).sum()),
        'three_category_unchanged_rows': int(f.q1_status.eq(f.lag_q1_status).sum()),
        'transition_counts': transition_counts, 'models_q9_level': models,
        'models_q9_update_given_previous_q9': updates,
        'verification_level_update_max_abs_coefficient_difference': max_beta_difference,
    }


def run(out, cache=CACHE):
    out, cache = Path(out).resolve(), Path(cache).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('A fresh output directory under outputs/ is required')
    source_summary = cache.parent / 'summary.json'
    receipt = json.loads(source_summary.read_text())
    actual_hash = sha(cache)
    if actual_hash != receipt['analysis_frame_sha256']:
        raise ValueError('Input cache does not match its source summary hash')
    frame = attach_adjacent(pd.read_parquet(cache))
    summary = {
        'status': 'completed_exploratory_observational_increment_not_causal_or_out_of_sample',
        'new_api_calls': 0, 'input_cache': str(cache.relative_to(ROOT)),
        'input_cache_sha256': actual_hash, 'input_cache_hash_verified': True,
        'source_summary_sha256': sha(source_summary),
        'analysis_source_sha256': sha(Path(__file__)),
        'reused_statistics_source_sha256': sha(Path(__file__).with_name('population_associations.py')),
        'outcome': 'Official published Q9_mean, percentage points; no new density fitting',
        'controls': CONTROLS,
        'specification': {
            'fixed_effects': 'current calendar month',
            'baseline': 'month + categorical demographic/education/numeracy controls + strict previous official Q9_mean',
            'q1_categories': {'worse': [1, 2], 'same_reference': [3], 'better': [4, 5]},
            'transition': 'nine categorical previous-to-current groups; same_to_same reference',
            'weights': 'current official positive weight, equal total weight in each month within each common sample',
            'inference': 'person-cluster CR1; absorbed month count included in residual degrees of freedom; 95% t intervals',
            'R2': 'within-month sample fit on identical observations in all nested comparisons',
            'multiplicity': 'exploratory unadjusted intervals and joint p values; no isolated significance claims',
            'pair_rule': 'same userid and exactly one calendar month; current and previous timeline_consistent and tenure_valid',
            'lag_boundary': 'formed on full cached history before period slicing; preceding December retained for January',
        },
        'periods': {key: analyze_period(frame, start, end) for key, (start, end) in PERIODS.items()},
        'limitations': [
            'Both periods have already been examined; neither is a new independent validation period.',
            'Q1 is a subjective rolling comparison with 12 months earlier, not an observed income shock.',
            'Q1 category levels and transitions are modeled categorically; no numeric 1-to-5 subtraction.',
            'Current Q1 and current inflation answers are contemporaneous; reverse causality and changing omitted factors remain.',
            'Conditioning on previous Q9 does not identify causal effects or demonstrate LLM improvements.',
            'This official-derived Q9 truth differs from the later simulation evaluation requirement to score both human and model raw bins with one frozen scorer.',
            'Cluster intervals do not capture every aspect of the survey design; R2 increments are not held-out prediction gains.',
        ],
    }
    out.mkdir(parents=True)
    dump(out / 'summary.json', summary)
    (out / 'methods.md').write_text(METHODS, encoding='utf-8')
    print(json.dumps({'output': str(out), 'new_api_calls': 0,
                      'period_samples': {k: v['sample_flow'] for k, v in summary['periods'].items()}}, ensure_ascii=False))
    return summary


METHODS = """# 家庭财务处境：给定本人上期信念的离线增量

2026-10-16；零API。只读已有analysis_frame_private.parquet，读取前与其summary的SHA256严格核对；不重新读取Excel，不保存或输出个人行。

分别分析2020—2022及2023—2025年10月。两段均已探索，不是独立验证。先在完整历史按userid与日历月配对，只保留严格相邻月、两期时间线与tenure标记有效的记录，再按当前月切段。因此1月可用上一年12月，不将断档最近一行当上月。重建上期官方Q9均值与缓存lag_q9逐值一致。所有模型共用本期Q9、上期Q9、正权重、控制变量及两期Q1均有效的样本，summary逐步保留原样本和排除后的行数、人数、月数。

Q1主分组为差(1/2)、相同(3)、好(4/5)，每档单独虚拟变量；基准为相同。比较只含控制/上期Q9、加上期Q1、加本期Q1、加两期Q1、加九档类别转移五个模型。转移模型基准为相同→相同，报告全部八个转移对比，尤其相同→差、相同→好与差→差。它不假定五档等距，也不把类别数字相减。

控制当前月、年龄、收入档、性别、地区、就业、官方High/Low数理标签及细学历；上期Q9为连续官方个人均值。WLS使用当前月官方权重，在每个共同样本内将每月总权重归一到相同。月份吸收后估计；按userid聚类CR1，计入吸收月份的残差自由度，以聚类人数减一自由度的t分布给95%区间。复用已有经显式月份虚拟变量核对的统计函数；完整系数/区间为财务因素对比及上期Q9系数，控制因素仅作为调整项。联合Wald与区间均为未作多重校正的探索描述。

报告样本内月内R²及同样本增量，不进行时间外预测或模型选择。另以Q9本期减严格上期为结果，仍控制上期Q9；除上期Q9系数减一外，其余系数与水平模型代数相同，程序验证该等价性。因此水平模型的财务系数也描述给定上期信念后的预期更新关联；不是未经调整的同人因果效应。更新结果使用不同因变量方差，R²水平与Q9水平均不可直接相互比较。

真值使用官方微观公布的Q9_mean派生字段，单位为百分点，本轮不重拟合真人密度。后续真实模拟应以同一冻结计分器处理真人及模型的原始Q9十档，不能把本轮官方派生值直接冒充该同口径结果。Q1是当前相对12个月前的主观财务评价；两次年度窗口滚动，转移不是识别出的本月收入冲击。同期通胀感受、遗漏时变因素与反向关系仍可能解释关联。结果不能转成提示中的固定加点规则，也不证明LLM可利用它改善。

复算（必须换新输出路径）：

```bash
OPENBLAS_NUM_THREADS=1 /Users/wushuyue/anaconda3/bin/python scripts/analyze_sce_household_finance_associations.py --out outputs/sce_household_finance_associations_NEW
```
"""
