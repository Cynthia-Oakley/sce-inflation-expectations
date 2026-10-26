"""Offline diagnostic of a completed monthly recursion; preserve sealed results.

Reads actual checkpoints and the exact-vector scoring cache. Does not fit Q9,
call a model, optimize parameters, or rewrite the original evaluator outputs.
"""
import argparse
from collections import defaultdict
from datetime import datetime
from html import escape
import json
from pathlib import Path
import shutil

import numpy as np

from ..evaluation.metrics import distribution_summary, headline_errors
from ..experiments.frozen_batch import ROOT, read_json as read, dump, sha
from ..experiments.recent_b_recursion import checked, checked_files, checkpoint
from ..prior_belief_experiment import message_hash
from ..state_continuity_runtime import render_state
from ..submission_tools.reproduce import no_network


SERIES = {
    'recursive_pp': '自主递推',
    'anchor_pp': '最后公开SCE',
    'fixed_blend_pp': '递推＋公开值固定组合',
    'independently_initialized_B_pp': '逐月独立初始化B（描述对照）',
    'independent_fixed_blend_pp': '独立B＋公开值固定组合',
    'root_retention_pp': '始终保留首月模拟值',
}


def build(run, out, report):
    run, out, report = map(lambda x: Path(x).resolve(), (run, out, report))
    if out.exists() or report.exists():
        raise ValueError('Use fresh versioned output and report directories')
    if not out.is_relative_to(ROOT/'outputs') or not report.is_relative_to(ROOT/'docs/workstreams'):
        raise ValueError('Local project outputs and workstream report required')
    p, manifest = checked(run)
    if read(run/'worker_receipt.json')['status'] != 'generation_and_evaluation_complete':
        raise ValueError('Complete actual generation and evaluation required')
    receipt = read(run/'generation_receipt.json')
    if not receipt['actual_model_results']:
        raise ValueError('Fixtures cannot become empirical results')
    checked_files(run/'evaluation', read(run/'evaluation/manifest.json')['files_sha256'])
    source = read(run/'evaluation/summary.json')
    pe = ROOT/p['PE']
    roots = read(pe/'root_answers_private.json')
    weights = read(pe/'weights_private.json')
    people = {r['agent_id']: r['attributes'] for r in read(pe/'population_private.json')['personas']}
    ids = sorted(roots)
    w = np.array([weights[a]['analysis_weight'] for a in ids], dtype=float)
    cache = {tuple(r['bins']): r['score']['mean'] for r in read(run/'evaluation/scoring_cache_private.json')}
    def values(states, field='q9'):
        return np.array([cache[tuple(states[a]['state_after']['fields']['q9']['value'])]
                         if field == 'q9' else states[a]['state_after']['fields']['q8']['value']
                         for a in ids], dtype=float)
    root = values(roots)
    before = roots
    previous_news = None
    rows, groups = [], []
    checks = dict(frozen_source_hashes=len(manifest['source_sha256']),
                  checked_same_id_predecessors=0, checked_rendered_states=0,
                  checked_unique_ordered_histories=0, checked_news_timestamps=0,
                  evaluation_metrics_reproduced=True)
    source_hashes = {str((run/'evaluation/manifest.json').relative_to(ROOT)): sha(run/'evaluation/manifest.json'),
                     str((run/'generation_receipt.json').relative_to(ROOT)): sha(run/'generation_receipt.json')}
    all_states = []
    for original in source['monthly']:
        month = original['month']
        if month == p['months'][0]:
            states = roots
        else:
            states, _ = checkpoint(run/'checkpoints'/month)
            saved_before = read(run/'waves'/month/'states_before_private.json')
            if saved_before != before:
                raise ValueError('Wrong predecessor state')
            prompts = read(run/'waves'/month/'frozen_messages'/month/'prompts.json')['rows']
            for aid in ids:
                row = states[aid]
                if (row['agent_id'] != aid or row['previous_month'] != before[aid]['month']
                        or row['prompt_sha256'] != message_hash(prompts[aid]['messages'])):
                    raise ValueError('Cross-person/changed prompt')
                if render_state(before[aid]['state_after'], month) not in prompts[aid]['messages'][0]['content']:
                    raise ValueError('Prompt did not contain its own exact preceding state')
                checks['checked_same_id_predecessors'] += 1
                checks['checked_rendered_states'] += 1
            source_hashes[str((run/'checkpoints'/month/'manifest.json').relative_to(ROOT))] = sha(run/'checkpoints'/month/'manifest.json')
        if set(states) != set(ids):
            raise ValueError('Fixed roster changed')
        v = values(states)
        desc = distribution_summary(v, w)
        if not np.isclose(desc['median_pp'], original['recursive_pp'], rtol=0, atol=1e-12):
            raise ValueError('Cached individual results do not reproduce original headline')
        context = read(pe/month/'timing_context_private.json')
        current_news, repeats, n_news = {}, 0., 0.
        for aid, weight in zip(ids, w):
            state = states[aid]['state_after']
            hist = [int(x['source_period']) for x in state['history_centers']]
            if hist != sorted(set(hist)) or any(x > int(month) for x in hist):
                raise ValueError('Duplicate or future history state')
            checks['checked_unique_ordered_histories'] += 1
            articles = context[aid]['common_news'] + context[aid]['personal_news']
            cutoff = datetime.fromisoformat(context[aid]['as_of'])
            for article in articles:
                if datetime.fromisoformat(article['pub_date'].replace('Z', '+00:00')) > cutoff:
                    raise ValueError('Future article in a sealed context')
                checks['checked_news_timestamps'] += 1
            current_news[aid] = {a['article_id'] for a in articles}
            if previous_news is not None:
                repeats += weight*len(current_news[aid] & previous_news[aid])
                n_news += weight*len(current_news[aid])
        drift = v-root
        row = dict(original)
        row.update(independent_fixed_blend_pp=(1-source['combination_simulation_weight'])*row['anchor_pp']
                   + source['combination_simulation_weight']*row['independently_initialized_B_pp'],
                   recursive_error_pp=row['recursive_pp']-row['truth_pp'],
                   distribution_descriptive=desc,
                   weighted_signed_root_shift_pp=float(np.average(drift, weights=w)),
                   weighted_share_above_own_root=float(w[drift > 1e-9].sum()/w.sum()),
                   weighted_share_below_own_root=float(w[drift < -1e-9].sum()/w.sum()),
                   repeated_article_exposure_share_vs_previous_month=None if not n_news else repeats/n_news,
                   q9_fallback_population_weight_share=float(sum(weight for aid, weight in zip(ids, w)
                       if not states[aid]['state_after']['transition']['field_updated_from_model']['q9'])/w.sum()))
        rows.append(row)
        for dim in ('education_group', 'numeracy', 'age_group', 'household_income_band'):
            levels = sorted({str(people[a].get(dim) or 'unknown') for a in ids})
            for level in levels:
                ix = [i for i, a in enumerate(ids) if str(people[a].get(dim) or 'unknown') == level]
                ds = distribution_summary(v[ix], w[ix])
                groups.append(dict(month=month, dimension=dim, level=level,
                    **ds, own_root_mean_signed_shift_pp=float(np.average(drift[ix], weights=w[ix])),
                    own_root_mean_abs_shift_pp=float(np.average(np.abs(drift[ix]), weights=w[ix]))))
        all_states.append(states)
        before, previous_news = states, current_news
    def score(rs):
        return {k: headline_errors([r[k] for r in rs], [r['truth_pp'] for r in rs]) for k in SERIES}
    primary = score(rows[1:])
    for k, expected in source['post_root_10_months_primary'].items():
        if any(not np.isclose(primary[k][m], value, rtol=0, atol=1e-12) for m, value in expected.items()):
            raise ValueError('Original primary metric does not reproduce')
    summary = dict(schema='sce_monthly_recursion_readout/v1', status='completed_offline_readout',
        source_run=str(run.relative_to(ROOT)), n_households=len(ids), effective_sample_size=float(w.sum()**2/(w@w)),
        primary_months=[r['month'] for r in rows[1:]], post_root_10_months_primary=primary,
        all_11_months_secondary=score(rows),
        descriptive_equal_halves_not_preregistered={
            'first_five_202512_202604': score(rows[1:6]), 'last_five_202605_202609': score(rows[6:])},
        monthly=rows, groups_descriptive_only=groups, checks=checks,
        call_receipt=receipt, combination_weight=source['combination_simulation_weight'],
        new_api_calls=0, new_q9_fits=0, coefficient_refit=False,
        limits=source['limits']+[
            'Time horizon and calendar environment change together: worsening later error is not a causal estimate of recursion damage.',
            'Equal early/late halves are a post-hoc descriptive view, not separately preregistered train/test samples.',
            'News overlap measures repeated exposure only; it does not identify repeated counting by the model.',
            'Cross-person spread, group paths and Q8 are simulation-only descriptions; no recent micro truth.',
            'One generation chain is available, so differences cannot separate model stochasticity from state dependence.'])
    truth = np.array([r['truth_pp'] for r in rows])
    changes = np.diff(truth)
    summary['continuity_descriptive_including_shared_root'] = {
        key: dict(n_levels=len(rows), n_transitions=len(rows)-1,
            mean_absolute_monthly_change_pp=float(np.abs(np.diff([r[key] for r in rows])).mean()),
            total_variation_pp=float(np.abs(np.diff([r[key] for r in rows])).sum()),
            net_change_pp=float(rows[-1][key]-rows[0][key]),
            level_correlation_with_truth=float(np.corrcoef([r[key] for r in rows], truth)[0, 1]),
            monthly_change_correlation_with_truth=float(np.corrcoef(np.diff([r[key] for r in rows]), changes)[0, 1]),
            monthly_change_rmse_pp=float(np.sqrt(np.mean((np.diff([r[key] for r in rows])-changes)**2))))
        for key in ('recursive_pp', 'independently_initialized_B_pp', 'truth_pp')}
    summary['continuity_descriptive_including_shared_root']['interpretation'] = (
        'Eleven levels and ten transitions, including the shared root, describe smoothness and turning points; '
        'not additional independent validation observations. Level correlation can be driven by the common trend.')
    out.mkdir(parents=True)
    dump(out/'summary.json', summary)
    report.mkdir(parents=True)
    make_charts(rows, groups, report)
    (report/'index.html').write_text(render(summary, out))
    dump(out/'manifest.json', dict(source_sha256=source_hashes,
        renderer_sha256=sha(Path(__file__)), files_sha256={'summary.json': sha(out/'summary.json')},
        report_files_sha256={f.name: sha(f) for f in report.iterdir() if f.is_file()},
        new_api_calls=0, new_q9_fits=0))
    return dict(status=summary['status'], primary=primary, checks=checks, report=str(report/'index.html'))


def make_charts(rows, groups, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font = ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists(): font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family': ['Times New Roman', 'Kaiti SC'], 'font.size': 12,
                         'axes.unicode_minus': False, 'savefig.facecolor': '#faf9f5'})
    x = np.arange(len(rows)); labels = [r['month'][:4]+'-'+r['month'][4:] for r in rows]
    colors = dict(truth_pp='#222222', recursive_pp='#bd5100', anchor_pp='#777777',
                  independently_initialized_B_pp='#2764b2', fixed_blend_pp='#7a4096')
    def finish(fig, axes, name):
        for ax in np.array(axes).flatten():
            ax.grid(axis='y', alpha=.18); ax.spines[['top', 'right']].set_visible(False)
        np.array(axes).flatten()[-1].set_xticks(x, labels, rotation=35, ha='right')
        np.array(axes).flatten()[-1].set_xlabel('调查月份（首月复用；后10月自主递推）')
        fig.savefig(out/name, dpi=180, bbox_inches='tight'); plt.close(fig)
    fig, ax = plt.subplots(2, 1, figsize=(11.2, 8), sharex=True, layout='constrained')
    for key, label in [('truth_pp', '官方SCE真值'), ('recursive_pp', '固定家庭自主递推'),
                       ('independently_initialized_B_pp', '逐月独立初始化B（描述对照）')]:
        ax[0].plot(x, [r[key] for r in rows], color=colors[key], marker='o', markersize=4, label=label)
    ax[0].set_title('前期接近真值，5月后形成持续高估'); ax[0].set_ylabel('全国Q9指标（%）'); ax[0].legend(frameon=False)
    ax[1].bar(x, [r['recursive_error_pp'] for r in rows], color=colors['recursive_pp'], label='递推−官方真值')
    ax[1].plot(x, [r['anchor_pp']-r['truth_pp'] for r in rows], color='#555555', marker='s', linestyle='--', label='最后公开值−真值')
    ax[1].axhline(0, color='#222222', lw=.8); ax[1].set_ylabel('有符号误差（pp）'); ax[1].legend(frameon=False)
    finish(fig, ax, 'national_path.png')
    fig, ax = plt.subplots(2, 1, figsize=(11.2, 7.5), sharex=True, layout='constrained')
    for key, label in [('recursive_pp', '原始递推'), ('anchor_pp', '最后公开SCE'), ('fixed_blend_pp', '固定组合（模拟占13.4%）')]:
        ax[0].plot(x, [abs(r[key]-r['truth_pp']) for r in rows], marker='o', color=colors[key], label=label)
    ax[0].set_title('组合约束了原始漂移，但收益有限且随月份变化'); ax[0].set_ylabel('全国绝对误差（pp）'); ax[0].legend(frameon=False)
    for k, label, color in [('simulated_weighted_mean_abs_root_drift_pp', '每人相对自身首月的平均绝对变化', '#bd5100'),
                            ('simulated_weighted_mean_abs_monthly_change_pp', '每人相对自身上月的平均绝对变化', '#2764b2')]:
        ax[1].plot(x, [r[k] if r[k] is not None else np.nan for r in rows], color=color, marker='o', label=label)
    ax[1].set_ylabel('个人Q9隐含均值变化（pp）'); ax[1].legend(frameon=False)
    finish(fig, ax, 'error_and_drift.png')
    fig, ax = plt.subplots(2, 1, figsize=(11.2, 7.5), sharex=True, layout='constrained')
    for key, label, color in [('iqr_pp', '人群中间50%范围（IQR）', '#2764b2'), ('std_pp', '人群标准差', '#bd5100')]:
        ax[0].plot(x, [r['distribution_descriptive'][key] for r in rows], color=color, marker='o', label=label)
    ax[0].set_title('中心分歧小幅收缩，极端预期的收缩更明显'); ax[0].set_ylabel('跨人分歧（pp，仅模拟）'); ax[0].legend(frameon=False)
    for key, label, color in [('share_below_zero', '个人隐含均值低于0%', '#2764b2'), ('share_above_eight', '个人隐含均值高于8%', '#bd5100')]:
        ax[1].plot(x, [100*r['distribution_descriptive'][key] for r in rows], color=color, marker='o', label=label)
    ax[1].set_ylabel('代表人口占比（%）'); ax[1].legend(frameon=False)
    finish(fig, ax, 'dispersion.png')
    fig, ax = plt.subplots(2, 1, figsize=(11.2, 7.5), sharex=True, layout='constrained')
    for dim, mapping, a in [('numeracy', {'high': '高数理组', 'low': '低数理组'}, ax[0]),
                             ('household_income_band', {'under_50k': '低收入组', '50k_to_100k': '中收入组', 'over_100k': '高收入组'}, ax[1])]:
        for (level, label), color in zip(mapping.items(), ['#2764b2', '#bd5100', '#7a4096']):
            rs = [g for g in groups if g['dimension'] == dim and g['level'] == level]
            a.plot(x, [g['median_pp'] for g in rs], marker='o', color=color, label=label)
        a.set_ylabel('组内Q9加权中位数（%）'); a.legend(frameon=False)
    ax[0].set_title('低数理、低收入组上移更多；缺少近期微观真值，不能据此判断哪组更准确')
    finish(fig, ax, 'groups.png')
    fig, ax = plt.subplots(figsize=(11.2, 4.8), layout='constrained')
    xx = x[1:]; width = .25
    for offset, key, label in [(-width, 'truth_pp', '官方SCE'), (0, 'recursive_pp', '自主递推'),
                                (width, 'independently_initialized_B_pp', '独立初始化B')]:
        ax.bar(xx+offset, np.diff([r[key] for r in rows]), width=width, color=colors[key], label=label)
    ax.axhline(0, color='#333333', lw=.8)
    ax.set_title('递推路径更平滑，但部分月份未能跟随真实转折')
    ax.set_ylabel('全国指标较上月的变化（pp）')
    ax.legend(frameon=False, ncol=3)
    ax.grid(axis='y', alpha=.18); ax.spines[['top', 'right']].set_visible(False)
    ax.set_xticks(xx, labels[1:], rotation=35, ha='right'); ax.set_xlabel('调查月份（10次相邻月变化）')
    fig.savefig(out/'monthly_changes.png', dpi=180, bbox_inches='tight'); plt.close(fig)


def render(s, out):
    metrics = s['post_root_10_months_primary']; rows = s['monthly']; c = s['checks']
    def metric_rows():
        return ''.join(f'<tr><td>{escape(label)}</td><td>{metrics[k]["mae_pp"]:.4f}</td><td>{metrics[k]["rmse_pp"]:.4f}</td><td>{metrics[k]["bias_pp"]:+.4f}</td></tr>' for k, label in SERIES.items())
    month_rows = ''.join(f'<tr><td>{r["month"][:4]}-{r["month"][4:]}</td><td>{r["truth_pp"]:.3f}</td><td>{r["recursive_pp"]:.3f}</td><td>{r["recursive_error_pp"]:+.3f}</td><td>{r["independently_initialized_B_pp"]:.3f}</td><td>{r["fixed_blend_pp"]:.3f}</td></tr>' for r in rows)
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>月度个人信念递推：误差与漂移</title>
<style>body{{margin:0;background:#faf9f5;color:#242424;font:18px/1.85 "Times New Roman","Kaiti SC","STKaiti",serif}}main{{max-width:1120px;margin:auto;padding:32px 24px}}h1{{font-size:30px;line-height:1.4}}h2{{font-size:23px;margin-top:32px}}p{{text-indent:2em}}.lead{{text-indent:0;border-left:4px solid #bd5100;background:#f8eee4;padding:16px 20px;font-size:20px}}.flow{{background:white;padding:14px 20px}}figure{{margin:24px 0}}img{{width:100%;height:auto}}figcaption,small{{font-size:15px;color:#555}}table{{width:100%;border-collapse:collapse;background:white;font-size:16px}}td,th{{border-bottom:1px solid #ddd;padding:8px;text-align:right}}td:first-child,th:first-child{{text-align:left}}.scroll{{overflow:auto}}a{{color:#2764b2}}summary{{cursor:pointer;font-weight:bold}}.numbers{{display:flex;gap:30px;flex-wrap:wrap;margin:24px 0}}.numbers div{{flex:1;min-width:190px}}.numbers strong{{display:block;font-size:27px}}.note{{border-top:1px solid #ccc;padding-top:12px}}</style>
<main><small>SCE · 月度连续递推 · 2026-10-26 · 完成后的离线分析 · 本轮0 API</small>
<h1>前期接近真值，后期向上漂移；连续递推需要定期校准</h1>
<p class="lead">这条链可以持续运行，但不能长期视为自动校准的调查替代。后10期原始MAE为0.306pp，高于最后公开值基线的0.190pp；误差主要集中在后半段的持续高估。它并非每一步都变差，9月已有回落；现有结果支持漂移风险，还不能将后期误差全部归因于递推。</p>
<div class="numbers"><div><small>前五次递推MAE</small><strong>0.111pp</strong><small>2025-12—2026-04</small></div><div><small>后五次递推MAE</small><strong>0.500pp</strong><small>2026-05—09，均为高估</small></div><div><small>最高单月偏差</small><strong>+0.753pp</strong><small>2026-08：4.353% vs 3.6%</small></div></div>
<h2>1．研究的是哪一个环节？</h2>
<p>固定2025年11月的512个代理家庭，复用该月512份实际模型回答。2025年12月至2026年9月，每人以自身上一个模拟月的Q8、Q9和更早模拟摘要为起点，再读取当月截止前的新闻、价格与政策，生成新答卷。画像、权重、食品采购角色和关注档位固定；没有新旧受访者进出，也没有按月重新对齐全国SCE。</p>
<div class="flow">同一家庭上月模拟答卷＋模拟历史摘要 → 更新后的可见环境 → 本月Q8/Q9 → 保存状态 → 下一月<br>模型：OpenRouter → SiliconFlow FP8 → DeepSeek V3.2；温度0.5，JSON，关闭思考；每人每月一遍。</div>
<p>这是<strong>无外部先验刷新、自主传递个人状态</strong>的动态实验。首月复用，不作为新的独立验证；主要比较根月之后10期。所有家庭均由LLM作答，本批没有Core＋Normal扩展，512户用固定设计权重汇总。</p>
<h2>2．误差是否累积？</h2>
<p>前五次递推的平均偏差只有+0.003pp，3月与4月误差分别仅0.040和0.015pp。5月开始连续高估，误差依次为+0.286、+0.467、+0.628、+0.753、+0.369pp。7—8月真值为3.6%，模拟仍从4.228%升到4.353%；9月模拟降至4.269%，真值升至3.9%，因此误差收窄。表现是阶段性的偏差积累，不是误差单调增长或数值爆炸。</p>
<figure><img src="national_path.png" alt="逐月全国指标和有符号误差"><figcaption>同一全国官方首发Q9口径；Q9由每人十档概率拟合连续密度并取隐含均值，再取跨人加权中位数。独立B的初始化与名单同时不同，仅作描述对照。</figcaption></figure>
<p>前后各五期只是观察结果后的等长描述，不是预先划定的训练／测试集。递推步数增加与经济环境变化同时发生；只有一条链，因此不能断言“每递推一次就增加多少误差”。前期准确也不能外推为固定的安全递推期限。</p>
<h2>补充：连续性改善体现在哪里？</h2>
<p>4月开始直到9月均为高估，但4月仅高0.015pp；5月偏差扩大到0.286pp，6月达到0.467pp，此后形成明显的持续偏离。这个起点来自事后观察，不能据此设定一个已经验证的重置阈值。</p>
<p>从11个月水平值及10次相邻月变化看，递推平均每月变化0.135pp，真值为0.190pp，独立初始化B为0.392pp。递推的曲线更连续，减少了独立初始化B的大幅跳动；但平滑本身不是准确性。递推与真值的水平相关为0.844，月度变化相关只有0.223；独立B分别为0.601与0.491。共同上升趋势能提高水平相关，未必意味着抓住了月内外的转折。</p>
<figure><img src="monthly_changes.png" alt="官方SCE、自主递推和独立B的相邻月变化对比"><figcaption>每月仅一个全国指标，比较10次相邻月差分；没有拟合ARIMA或新增预测参数。平稳方向中的微小变化仍按原数值展示。</figcaption></figure>
<p>例如5月真值下降0.1pp，递推仍上升0.172pp；7月真值下降0.1pp，递推上升0.061pp；8月真值不变，递推继续上升0.125pp；9月真值上升0.3pp，递推却下降0.084pp。递推累计净上升1.055pp，真实指标净上升0.700pp。这些事实适合报告为实验性扩展的边界：保留身份和历史能增加路径连续性，但还缺少可靠的转向和外部纠偏机制。独立B虽然变化相关更高，变化幅度仍过大，其变化误差RMSE0.438pp高于递推0.227pp，不能据单个相关系数判定哪条路径全面更好。</p>
<h2>3．与基线及原路线B相比如何？</h2>
<div class="scroll"><table><tr><th>方法（同后10期）</th><th>MAE（pp）</th><th>RMSE（pp）</th><th>平均偏差（pp）</th></tr>{metric_rows()}</table></div>
<p>自主递推原始MAE比独立B的0.382pp低约20%，但仍比持续性基线高。其固定组合沿用A线预定模拟权重13.3976%，不在这10期重新拟权：MAE为0.1827pp，比基线0.1900pp低约3.8%，改善很小。独立B用同样权重组合为0.1585pp，仍优于递推组合。<strong>单独模拟更准，不等于与公开值组合后的增量更大</strong>；还取决于模拟在何时修正、何时放大基线误差。</p>
<figure><img src="error_and_drift.png" alt="原始及组合绝对误差与个人变化"><figcaption>组合Z＝0.866024×最后已公开SCE＋0.133976×递推指标。组合只在评价时加入公开锚，未写回个人递推状态，不能用组合成绩掩盖原始链的漂移。</figcaption></figure>
<p>若连复用首月也计算，11期原始MAE为0.2792pp、组合0.1663pp、基线0.1727pp。这组数字单列为补充；与上述10期成绩不能混用。</p>
<h2>4．个人结构发生了什么？</h2>
<p>到最后一月，67.5%的代表人口高于自身首月预期；每人相对自身首月的平均绝对变化约2.00pp。跨人标准差从4.059降到1.848pp，收缩约54.5%；IQR从2.299降到2.113pp，收缩约8.1%。这两个结果并不矛盾：极端预期的收缩比中间50%人群更明显，分布整体还向上移动。</p>
<figure><img src="dispersion.png" alt="跨人IQR、标准差及极端预期占比"><figcaption>这里是不同家庭的Q9隐含均值分布，不是每份Q9概率分布内部的不确定性。没有近期真人微观资料，因此不能把模拟分歧收缩直接判定为微观准确率下降。</figcaption></figure>
<p>低数理组的组内中位数从3.403%升到5.210%，高数理组从3.163%升到3.790%；低收入组从3.403%升到4.879%，高收入组从3.153%升到3.887%。漂移不是所有人共同加上同一个常数。各属性相关，当前分组是边际描述，不能把差异解释为数理能力或收入的独立因果作用。Q8中位数也从3.5%升至4.4%，方向与Q9一致，但没有对应近期Q8真值可评价误差。</p>
<figure><img src="groups.png" alt="按数理能力和收入分组的模拟路径"><figcaption>固定身份、固定权重；图示分组不是本轮新增的分层抽样，也不是对近期真实人群的独立验证。</figcaption></figure>
<h2>5．机制解释与后续调整</h2>
<p>本轮结果与一种反馈机制相容：当月判断偏高，会成为下月的起点，同时进入个人历史均值；后续判断由此承接偏高状态，而缺少新公开SCE对合成总体的纠偏。初始极端信念逐步收缩，中心随后上移，说明“原有分歧收缩”和“中心偏差积累”可以同时发生。环境冲击、起始人口与模型更新特征仍混在一起，现有数据不能分离其贡献。</p>
<p>新闻窗口也允许同一篇文章再次出现；已统计相邻月重复曝光，但提示已区分其相对上一状态的公开先后，重复出现不能直接证明模型把信息重复计算。周度任务应保留已见新闻记录、约束接触预算，并明确哪些是新增证据，避免机械地把月度新闻量每周重复投放。</p>
<p><strong>后续采用你已确定的周度方案：</strong>同一批家庭在两个SCE发布时点之间连续传递信念；一旦新的过去月份SCE公布，按既有B方法校准合成起点后再递推。校准后贴合公开值只是约束满足，成绩应取新目标发布前已保存的预测。此实验提供采用定期校准的动机，但尚未证明周度校准一定提高预测精度。</p>
<h2>6．运行、核查与适用边界</h2>
<p>新增5,120主请求＋40次技术补跑，共5,160次新尝试；API已报费用$4.2752，未知费用预留$0.1735另列，合计记账$4.4487，低于$10上限。5月1户Q8/Q9在补跑后仍技术失败，按原规则保留其上月状态；原始答复、补批和字段来源均保留，不继续重跑。</p>
<p>本次核查{c['frozen_source_hashes']}项冻结来源，复算全部11个月中位数和原主指标；检查{c['checked_same_id_predecessors']:,}次同人前驱连接及实际提示中的原状态、{c['checked_unique_ordered_histories']:,}份历史无重复／未来月份，并核查{c['checked_news_timestamps']:,}次新闻时间。没有发现串人、跳月、历史重复追加或未来新闻进入可见输入。该核查不等于认证模型训练知识和历史文本版本。</p>
<details><summary>查看逐月全国数值</summary><div class="scroll"><table><tr><th>调查月</th><th>真值（%）</th><th>递推（%）</th><th>偏差（pp）</th><th>独立B（%）</th><th>固定组合（%）</th></tr>{month_rows}</table></div></details>
<p class="note">数据来源：{escape(s['source_run'])}；固定512户、加权ESS约{s['effective_sample_size']:.0f}，不是每月真实调查全名单。结果为事后按历史信息截止进行的回顾性诊断，只有10个新增宏观月份，不能按5,120户月当作独立预测样本。本页0新API、0新Q9拟合、0参数重估；原评价及运行文件不改。</p>
<p><a href="{out.as_uri()}/summary.json">机器可读完整分析</a> · <a href="../MONTHLY_RUNBOOK_20261026.md">冻结运行说明</a> · <a href="../NEXT_MONTHLY_AND_WEEKLY_20261026.md">周度校准方案</a></p></main></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    with no_network():
        result = build(args.run, args.out, args.report)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
