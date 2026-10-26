"""Read-only comparison of completed A82 versions; no LLM or density fitting."""
import argparse
import csv
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path

import numpy as np

from ..evaluation.aggregate_blend import evaluate as blend_metrics, fit_weight
from ..evaluation.metrics import distribution_summary, headline_errors, paired_month_mae_interval
from ..experiments.frozen_batch import ROOT, sha

ARM = 'monthly_reconstruction'


def read(p):
    return json.loads(Path(p).read_text())


def write(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def csv_rows(path, rows):
    with Path(path).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def score(rows, key):
    return headline_errors([r[key] for r in rows], [r['truth_pp'] for r in rows])


def metric_side(result, arm):
    return result['arms'][arm]['auxiliary_survey_weighted']


def compare(evaluation, out):
    evaluation, out = Path(evaluation).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('A fresh outputs directory is required')
    source = read(evaluation / 'summary.json')
    manifest = read(evaluation / 'manifest.json')
    if source['status'] != 'completed_full_a_personal_evaluation' or source['new_api_calls'] != 0:
        raise ValueError('Completed, isolated real-model evaluation required')
    for name, digest in manifest['files_sha256'].items():
        if sha(evaluation / name) != digest:
            raise ValueError('Evaluation artifact changed: ' + name)
    old_path = ROOT / 'outputs/sce_fullperiod_analysis_20261024_v1/summary.json'
    old = read(old_path)
    old_index = {r['month']: r for r in old['official_national']['monthly']}
    rows = []
    # Old and new macro medians use all operational outputs, never selection by
    # current human response validity. Read only the already isolated case file.
    cases = read(evaluation / 'cases_private.json')
    by_month = {}
    for r in cases:
        by_month.setdefault(str(r['month']), []).append(r)
    for r in source['official_national']['monthly']:
        key = r['month']; month = key.replace('-', ''); same = by_month[month]
        old_valid = [c for c in same if type(c['arms']['old_A82']['mean']) in (float, int)
                     and np.isfinite(c['arms']['old_A82']['mean'])]
        old_same = distribution_summary([c['arms']['old_A82']['mean'] for c in old_valid],
                                        [c['survey_weight'] for c in old_valid])['median_pp']
        previous = old_index[key]
        if any(r[k] != previous[k] for k in ('truth_pp', 'anchor_pp')):
            raise ValueError('The registered national target/baseline changed')
        rows.append(dict(month=key, sim_pp=r['sim_pp'], old_sim_pp=previous['sim_pp'],
            old_same_roster_pp=old_same, anchor_pp=r['anchor_pp'], truth_pp=r['truth_pp'],
            new_error_pp=r['sim_pp'] - r['truth_pp'],
            old_error_pp=previous['sim_pp'] - r['truth_pp'],
            anchor_error_pp=r['anchor_pp'] - r['truth_pp'],
            anchor_reference=r.get('anchor_reference', ''),
            anchor_published_date=r.get('anchor_published_date', ''),
            truth_published_date=r.get('truth_published_date', '')))
    if len(rows) != 82 or rows[0]['month'] != '2019-01' or rows[-1]['month'] != '2025-10':
        raise ValueError('Expected all 82 fixed historical months')
    years = []
    for year in range(2019, 2026):
        selected = [r for r in rows if r['month'].startswith(str(year))]
        item = dict(year=year, n_months=len(selected), new=score(selected, 'sim_pp'),
                    old=score(selected, 'old_sim_pp'), old_same_roster=score(selected, 'old_same_roster_pp'),
                    persistence=score(selected, 'anchor_pp'))
        item['new_minus_old_mae_pp'] = item['new']['mae_pp'] - item['old']['mae_pp']
        item['new_better_months'] = sum(abs(r['new_error_pp']) < abs(r['old_error_pp']) for r in selected)
        years.append(item)
    roster = {}
    for name, side in [('new', ARM), ('old', 'old_A82')]:
        s = metric_side(source['old_new_same_roster'], side)
        roster[name] = {f: s[f]['aggregate_equal_month_repeat_cells'] for f in ('q8', 'q9')}
    reference = {}
    for name, side in [('new', ARM), ('initial_reference', 'monthly_past_reference')]:
        s = metric_side(source['fixed_roster'], side)
        reference[name] = {f: s[f]['aggregate_equal_month_repeat_cells'] for f in ('q8', 'q9')}
    # This is a descriptive fit only. The preregistered 48/34 chronological
    # comparison from the frozen evaluator remains the main combination result.
    in_sample = {}
    for loss in ('mae', 'mse'):
        weight = fit_weight([r['truth_pp'] for r in rows], [r['anchor_pp'] for r in rows],
                            [r['sim_pp'] for r in rows], loss)
        in_sample[loss] = dict(simulation_weight=weight, metrics=blend_metrics(rows, weight),
                              interpretation='descriptive full-period calibration, not validation')
    national = dict(model=score(rows, 'sim_pp'), old=score(rows, 'old_sim_pp'),
                    old_same_roster=score(rows, 'old_same_roster_pp'),
                    persistence=score(rows, 'anchor_pp'),
                    chronological_combinations=source['official_national']['chronological_combinations'])
    delta = national['model']['mae_pp'] - national['old']['mae_pp']
    generation = read(ROOT / 'outputs/sce_full_a_t0_terminal_20261025_v1/generation_receipt.json')
    result = dict(status='completed_readonly_A82_comparison', new_api_calls=0, new_q9_density_fits=0,
        generated_at_utc=datetime.now(timezone.utc).isoformat(), selected_person_months=len(cases),
        official_national=national, monthly=rows, yearly=years,
        mae_change_pp=delta, mae_reduction_fraction=-delta / national['old']['mae_pp'],
        new_better_months=sum(abs(r['new_error_pp']) < abs(r['old_error_pp']) for r in rows),
        paired_new_old_interval=paired_month_mae_interval(
            [r['new_error_pp'] for r in rows], [r['old_error_pp'] for r in rows],
            block_length=6, draws=2000, seed=20261023),
        same_roster=dict(q9_person_months=source['old_new_same_roster']['q9_person_months'],
                         q8_person_months=source['old_new_same_roster']['q8_person_months'], metrics=roster),
        initial_reference_comparison=reference, quality=source['quality'],
        full_wave_center_errors=source['full_wave_center_errors'],
        descriptive_all_period_blend=in_sample,
        execution=dict(main_new_api_calls=generation['main']['new_api_calls'],
            historical_reuse=generation['historical_import_rows'],
            repair_attempts=generation['repair']['attempts'],
            total_new_physical_api_attempts=generation['physical_api_attempts'],
            reported_cost_usd=generation['main']['reported_cost_usd'] + generation['repair']['reported_cost_usd'],
            historical_cost_already_excluded=True,
            unknown_fee_reservation_usd=generation['main']['unknown_fee_reservation_usd'],
            automatic_evaluation_launch_bug='subprocess block incorrectly nested under engineering-only branch; frozen generation kept unchanged; isolated evaluator invoked offline'),
        limits=['The two A configurations change news count, sampling/routing and personal information time together; differences cannot identify one causal component.',
                '14 prespecified out-of-month completion records excluded; old full-roster and recalibrated same-roster estimates both supplied.',
                'National headline, same-roster micro, full-wave micro and truly observed-prior baselines use different supports.',
                '2021 and the late 34 months have already informed exploratory development; chronology alone does not make them untouched test data.',
                'One response per person-month; interval resamples months conditional on realized people, model and environment, not all sources of uncertainty.',
                'A is retrospective reconstruction, not strict sealed forecasting; original B11 retained separately.'])
    out.mkdir(parents=True)
    write(out / 'summary.json', result)
    csv_rows(out / 'monthly_national.csv', rows)
    csv_rows(out / 'yearly.csv', [dict(year=y['year'], n_months=y['n_months'],
        old_mae_pp=y['old']['mae_pp'], new_mae_pp=y['new']['mae_pp'],
        baseline_mae_pp=y['persistence']['mae_pp'], change_pp=y['new_minus_old_mae_pp']) for y in years])
    write(out / 'manifest.json', dict(new_api_calls=0,
        source_sha256={str(p.relative_to(ROOT)): sha(p) for p in [evaluation / 'manifest.json',
            evaluation / 'summary.json', old_path, Path(__file__)]},
        files_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file()}))
    return result


def charts(out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    out = Path(out); s = read(out / 'summary.json'); figdir = out / 'figures'; figdir.mkdir()
    font = ROOT / 'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    cn = FontProperties(fname=str(font))
    plt.rcParams.update({'font.family': cn.get_name(), 'font.size': 11,
                          'axes.spines.top': False, 'axes.spines.right': False})
    # Register the local font without redistributing it.
    from matplotlib import font_manager
    font_manager.fontManager.addfont(str(font))
    blue, orange, gray, black = '#1764AB', '#DC6B19', '#858B92', '#222222'
    rows = s['monthly']; x = np.arange(len(rows))
    def save(fig, name):
        fig.tight_layout(); fig.savefig(figdir / name, dpi=170, bbox_inches='tight'); plt.close(fig)
    fig, ax = plt.subplots(figsize=(11.5, 3.8))
    for k, label, color, ls in [('truth_pp', 'SCE公开真值', black, '-'),
                              ('old_sim_pp', '旧A', blue, '-'), ('sim_pp', '新版A T0', orange, '-')]:
        ax.plot(x, [r[k] for r in rows], label=label, color=color, lw=1.8, ls=ls)
    ax.axvspan(23.5, 35.5, color=orange, alpha=.10, label='2021年')
    ax.set_xticks(list(range(0,82,12)), [rows[i]['month'] for i in range(0,82,12)])
    ax.set_ylabel('一年期通胀预期（%）'); ax.legend(ncol=4, frameon=False, loc='upper left')
    ax.grid(alpha=.15); save(fig, 'a82_levels.png')
    fig, ax = plt.subplots(figsize=(10.5, 3.6)); years=s['yearly']; xx=np.arange(len(years)); w=.24
    for off, key, label, color in [(-w,'old','旧A',blue),(0,'new','新版T0',orange),(w,'persistence','公开历史基线',gray)]:
        bars=ax.bar(xx+off,[y[key]['mae_pp'] for y in years],width=w,label=label,color=color)
        ax.bar_label(bars,fmt='%.2f',fontsize=9,padding=3)
    ax.set_xticks(xx,[str(y['year'])+('¹' if y['year']==2025 else '') for y in years]);ax.set_ylabel('全国Q9中位数 MAE（pp）')
    ax.legend(ncol=3,frameon=False); ax.margins(y=.22);save(fig,'a82_yearly_mae.png')
    selected=[r for r in rows if r['month'].startswith('2021')];xx=np.arange(12)
    fig, axes=plt.subplots(1,2,figsize=(11.5,3.7))
    for key,label,color in [('truth_pp','SCE真值',black),('old_sim_pp','旧A',blue),('sim_pp','新版T0',orange),('anchor_pp','公开历史基线',gray)]:
        axes[0].plot(xx,[r[key] for r in selected],label=label,color=color,marker='o',ms=3,lw=1.5)
    for key,label,color in [('old_error_pp','旧A',blue),('new_error_pp','新版T0',orange)]:
        axes[1].plot(xx,[r[key] for r in selected],label=label,color=color,marker='o',ms=3)
    for ax in axes:ax.set_xticks(xx[::2], [r['month'][5:] for r in selected][::2]);ax.set_xlabel('2021年月');ax.grid(alpha=.15)
    axes[0].set_ylabel('通胀预期（%）');axes[1].set_ylabel('模拟减真值（pp）');axes[1].axhline(0,color=gray,ls='--')
    axes[0].legend(ncol=2,frameon=False,fontsize=9);axes[1].legend(frameon=False)
    save(fig,'a2021_levels_errors.png')


def html_report(out, destination):
    out, destination = Path(out), Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    import shutil
    shutil.copytree(out / 'figures', destination / 'figures')
    s=read(out/'summary.json');nat=s['official_national'];y21=next(y for y in s['yearly'] if y['year']==2021)
    def f(x):return f'{x:.3f}'
    yearly=''.join(f'<tr><td>{y["year"]}</td><td>{f(y["old"]["mae_pp"])}</td><td>{f(y["new"]["mae_pp"])}</td><td>{f(y["persistence"]["mae_pp"])}</td><td>{y["new_minus_old_mae_pp"]:+.3f}</td></tr>' for y in s['yearly'])
    micro=s['same_roster']['metrics'];q8old=micro['old']['q8']['q8_center_mae_pp'];q8new=micro['new']['q8']['q8_center_mae_pp']
    body=f'''<h1>新版路线A：82个月结果与旧版对照</h1><p>2019-01—2025-10；主指标为个人Q9密度均值的跨人设计加权中位数，与公开全国SCE指标比较。单位pp。</p>
    <div class="cards"><div>全期MAE<br><b>{f(nat['old']['mae_pp'])} → {f(nat['model']['mae_pp'])}</b></div><div>2021年MAE<br><b>{f(y21['old']['mae_pp'])} → {f(y21['new']['mae_pp'])}</b></div><div>全期公开历史基线<br><b>{f(nat['persistence']['mae_pp'])}</b></div></div>
    <h2>1. 比较对象与执行</h2><p>新版T0采用个人作答日前一日截止，新闻、价格、政策等按同一日期筛选；采用4/8/16/32档新闻与CPI相关度1.5，个人警示权重仍为1。旧A为共同月中截止、3/8/20篇随机新闻。其他人口、历史信念、主模型与评分算法沿用。多个环节一起变化，不能把总差异归因于某一个环节。</p>
    <p>原名单排除14份跨标称月完成记录，保留41,970个人月并恢复原54格人口质量；182份相同提示旧答复用，新增主请求41,788次、补跑241次，合计42,029次。最终Q8全部得到模型输出，Q9有1份沿用输入起点。新调用API实报${s['execution']['reported_cost_usd']:.4f}，未知费预留另列；没有为本次分析新增API。</p>
    <h2>2. 全期与2021年</h2><img src="figures/a82_levels.png"><img src="figures/a82_yearly_mae.png">
    <table><tr><th>年份</th><th>旧A MAE</th><th>新版 MAE</th><th>历史基线</th><th>新版减旧版</th></tr>{yearly}</table><p>2025年仅含1—10月。旧A完整名单与新版合格名单略有不同；将旧答卷放到新版相同名单和权重后，全国MAE为{f(nat['old_same_roster']['mae_pp'])}，可检查14份排除是否改变结论。新版有{s['new_better_months']}/82个月的绝对误差低于旧版。</p>
    <img src="figures/a2021_levels_errors.png"><h2>3. 同名单微观与组合</h2>
    <p>严格同名单/同权重、真人Q9合法的支持上：Q9中心MAE旧{f(micro['old']['q9']['q9_center_mae_pp'])}、新{f(micro['new']['q9']['q9_center_mae_pp'])}；W1旧{f(micro['old']['q9']['cross_section_w1_pp'])}、新{f(micro['new']['q9']['cross_section_w1_pp'])}；人际IQR旧{f(micro['old']['q9']['cross_person_iqr_pp'])}、新{f(micro['new']['q9']['cross_person_iqr_pp'])}、真人{f(micro['new']['q9']['real_cross_person_iqr_pp'])}。Q8中心MAE旧{f(q8old)}、新{f(q8new)}。这些与全国headline采用不同支持，不能混算。</p>'''
    for loss,c in nat['chronological_combinations'].items():
        body+=f'<p>{loss.upper()}拟权：2019—2022早48月拟合模拟权重λ={c["simulation_weight"]:.4f}；2023-01—2025-10后34月冻结组合MAE {f(c["evaluation"]["mae_pp"])}，同段历史基线{f(c["persistence"]["mae_pp"])}，纯模拟{f(c["pure_simulation"]["mae_pp"])}。历史月份参与过研究开发，不能称未触碰的独立盲测。</p>'
    body+='<h2>4. 解释边界</h2><ul>'+''.join('<li>'+escape(t)+'</li>' for t in s['limits'])+'</ul><p>自动评价未启动属于控制器缩进问题，原生成/补跑与原收据未改；本次调用封存评价器独立离线计算。原始回答和技术失败全部保留。研究配置未因结果再调整，路线B仍是旧B11结果，另行更新。</p>'
    (destination/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>新版A82全量比较</title><style>body{max-width:1100px;margin:32px auto;padding:20px;font:19px/1.7 "Times New Roman","Kaiti SC",serif;color:#242424;background:#fafafa}h1{font-size:32px}h2{margin-top:34px;font-size:25px}img{width:100%;background:white;margin:14px 0}.cards{display:flex;gap:20px}.cards div{background:#eef3f7;padding:18px;flex:1}b{font-size:25px}table{border-collapse:collapse;width:100%;background:white}td,th{padding:8px;border-bottom:1px solid #ccc;text-align:right}th{background:#eaeef1}p{text-indent:2em}li{margin:10px 0}</style>'+body+'</html>')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evaluation',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    result=compare(a.evaluation,a.out);charts(a.out);html_report(a.out,a.report)
    print(json.dumps({k:result[k] for k in ('status','new_api_calls','mae_change_pp','yearly')},ensure_ascii=False))


if __name__=='__main__': main()
