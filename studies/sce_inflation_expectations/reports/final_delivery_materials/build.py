"""Assemble an author-facing evidence workbook from already frozen public aggregates.

No generation, density fitting, parameter estimation, or manuscript rewriting.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'sce_paper_materials_matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager
from matplotlib.colors import TwoSlopeNorm, LinearSegmentedColormap
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
BLUE, ORANGE, PURPLE, BLACK, GREY = '#1769aa', '#c46a16', '#9d347b', '#252b33', '#787f88'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text())


def load_csv(path):
    with Path(path).open(newline='') as stream:
        return list(csv.DictReader(stream))


def month(value):
    text = str(value).replace('-', '')
    return text[:4] + '-' + text[4:6]


def stats(rows, field):
    errors = [float(row[field]) - float(row['truth_pp']) for row in rows]
    return {'n': len(errors), 'mae_pp': float(np.mean(np.abs(errors))),
            'rmse_pp': float(np.sqrt(np.mean(np.square(errors)))), 'bias_pp': float(np.mean(errors))}


def close(actual, expected, label):
    if not math.isclose(float(actual), float(expected), rel_tol=1e-10, abs_tol=1e-11):
        raise ValueError(f'Frozen aggregate mismatch: {label}')


def link(path, label=None, out=None):
    import os
    path = Path(path)
    return '[' + (label or path.name) + '](' + os.path.relpath(path, out) + ')'


def figure_style():
    cn = ROOT / 'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if cn.exists():
        font_manager.fontManager.addfont(str(cn))
    plt.rcParams.update({'font.family': ['DejaVu Sans', 'Kaiti SC'], 'font.size': 12,
                         'axes.unicode_minus': False, 'axes.spines.top': False,
                         'axes.spines.right': False, 'axes.titlesize': 14,
                         'legend.fontsize': 10, 'svg.fonttype': 'path'})


def line_plot(ax, rows, series, title, ticks=None):
    x = np.arange(len(rows))
    for key, label, color, style in series:
        ax.plot(x, [float(r[key]) for r in rows], color=color, label=label,
                ls=style, lw=1.9, marker='o' if len(rows) <= 12 else None, ms=3.5)
    if ticks is None:
        ticks = range(len(rows)) if len(rows) <= 12 else list(range(0, len(rows), 12)) + [len(rows)-1]
    ax.set_xticks(list(ticks), [month(rows[i]['month']) for i in ticks], rotation=25, ha='right', fontsize=9)
    ax.set(xlabel='调查目标月', ylabel='一年期通胀预期（%）', title=title)
    ax.grid(axis='y', alpha=.16)
    ax.legend(frameon=False, ncol=2, loc='upper left')


def save_plot(fig, out, stem):
    for suffix in ['png', 'svg']:
        path = out / 'figures' / f'{stem}.{suffix}'
        fig.savefig(path, dpi=175, bbox_inches='tight')
        if suffix == 'svg':
            path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines()) + '\n')
    plt.close(fig)


def build(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'docs/workstreams/20261027_final_delivery'):
        raise ValueError('Use a fresh materials directory inside the final_delivery workstream')
    pointer = load_json(ROOT / 'submission/latest_package.json')
    archive = ROOT / pointer['archive']
    if digest(archive) != pointer['archive_sha256']:
        raise ValueError('Current package hash mismatch')
    package = (ROOT / pointer['readme']).parent
    data = package / 'studies/sce_inflation_expectations/reproduction_data'
    source_paths = set()

    def take(relative):
        path = ROOT / relative
        source_paths.add(path)
        return load_json(path) if path.suffix == '.json' else load_csv(path)

    def frozen(name):
        path = data / name
        source_paths.add(path)
        return load_json(path) if path.suffix == '.json' else load_csv(path)

    base = frozen('aggregate_cases.json')
    ext = frozen('extension_cases.json')
    a = take('outputs/sce_full_a_t0_readout_20261026_v1/monthly_national.csv')
    comparison = frozen('A82_comparison_summary.json')
    grids = take('outputs/sce_grid_dimensions_20261023_v1/summary.json')
    frames = take('outputs/sce_grid_oversampling_20261023_v2/summary.json')
    news = take('docs/workstreams/20261021_fullperiod/news_matching_adoption_20261022.json')
    an = frozen('A82_Core_Normal_tau8.csv')
    micro = frozen('A82_micro_monthly_summaries.csv')
    b = frozen('B11_latest_Core_and_Normal.csv')
    rec = frozen('monthly_autonomous_recursion.csv')
    wp = frozen('weekly47_monthly11_primary.csv')
    weeks = frozen('weekly47_path.csv')
    dm = frozen('downstream_model_metrics.csv')
    dc = frozen('downstream_contrasts.csv')
    bsource = {c['case_id']: c for c in base['cases']}
    esource = {c['case_id']: c for c in ext['cases']}
    validated = []
    for case in ext['cases']:
        path = data / case['file']
        if digest(path) != case['sha256']:
            raise ValueError('Extension CSV changed: ' + case['case_id'])
        rows = load_csv(path)
        for panel in case['panels']:
            selected = [r for r in rows if panel['from'] <= month(r['month']).replace('-', '') <= panel['to']]
            if len(selected) != panel['n']:
                raise ValueError('Panel count mismatch')
            for field, expected in panel['expected'].items():
                result = stats(selected, field)
                for metric in ['mae_pp', 'rmse_pp', 'bias_pp']:
                    close(result[metric], expected[metric], case['case_id'] + '/' + panel['name'] + '/' + field + '/' + metric)
                    validated.append(case['case_id'] + '/' + panel['name'] + '/' + field + '/' + metric)
    for field, key in [('sim_pp', 'model'), ('old_sim_pp', 'old'), ('old_same_roster_pp', 'old_same_roster'), ('anchor_pp', 'persistence')]:
        for metric in ['mae_pp', 'rmse_pp', 'bias_pp']:
            close(stats(a, field)[metric], comparison['official_national'][key][metric], 'A/' + field + '/' + metric)
            validated.append('A/' + field + '/' + metric)
    for key, expected in ext['micro_summary_expected'].items():
        close(np.mean([float(r[key]) for r in micro]), expected, 'micro/' + key)
        validated.append('micro/' + key)
    for case in ext['cases']:
        rows = load_csv(data / case['file'])
        spec = case.get('fixed_blend')
        if spec:
            for row in rows:
                expected = (1-spec['weight'])*float(row[spec['anchor']]) + spec['weight']*float(row[spec['raw']])
                close(row[spec['combined']], expected, case['case_id'] + '/blend')
                validated.append(case['case_id'] + '/blend/' + row['month'])

    out.mkdir(parents=True)
    (out / 'figures').mkdir()
    figure_style()
    figures = []

    def register(stem, title, caption, sources):
        figures.append({'id': stem, 'file': 'figures/' + stem + '.png', 'vector': 'figures/' + stem + '.svg',
                        'title': title, 'caption': caption, 'sources': sources})

    fig, axes = plt.subplots(1, 2, figsize=(13.4, 4.2), layout='constrained')
    names = ['education', 'numeracy', 'income', 'age', 'employment', 'gender', 'housing', 'region']
    labels = ['学历', '数理', '收入', '年龄', '就业', '性别', '住房', '地区']
    uncertainty = [100*grids['conditional_information'][n]['development_domain_loss_increase']['uncertainty'] for n in names]
    axes[0].barh(labels[::-1], uncertainty[::-1], color=BLUE, height=.65)
    axes[0].set(xlabel='移除此变量后损失上升（标准化损失百分点）', title='人口信息主要帮助解释概率宽度')
    axes[0].grid(axis='x', alpha=.15)
    for y, v in enumerate(uncertainty[::-1]): axes[0].text(v+.04, y, f'{v:.2f}', va='center', fontsize=10)
    eigen = grids['associations']['development']['mca']['raw_inertia_fraction']
    axes[1].plot(range(1, len(eigen)+1), np.array(eigen)*100, marker='o', color=ORANGE)
    axes[1].set(xlabel='MCA轴序号', ylabel='原始惯量比例（%）', title='MCA描述人口X，不证明哪些变量预测最好')
    axes[1].grid(alpha=.15)
    save_plot(fig, out, '01_grid_basis')
    register('01_grid_basis', '网格选择的统计依据', '2019—2022开发期，按受访者分组留出。左图为整块移除再拟合后的个人Q9密度宽度损失；右图不是问卷Y解释率。54格另结合年龄/收入解释性、过采样与部分汇聚，并非PCA唯一最优。', ['grid_dimensions'])

    fig, axes = plt.subplots(2, 1, figsize=(13.4, 8.0), layout='constrained')
    series = [('truth_pp','官方SCE（评价真值）',BLACK,'-'),('sim_pp','新版A T0',BLUE,'-'),('old_same_roster_pp','旧A（同名单/权重）',ORANGE,'-'),('anchor_pp','公开历史参照',GREY,'--')]
    line_plot(axes[0], a, series, 'A82：不同通胀阶段的中心路径')
    y21 = [r for r in a if r['month'].startswith('2021')]
    line_plot(axes[1], y21, series, '2021放大：新版减轻低估，但没有跟上全部上行')
    save_plot(fig, out, '02_A_path')
    register('02_A_path', 'A全时期与2021', 'A 2019-01—2025-10，共82个月，41,970个人月，一人一次。旧A按新版名单和权重重算；2021同名单旧A的MAE是0.825607，旧全名单是0.822126。历史参照沿用原截止锚，并非每位受访者同一as_of。', ['A_T0_readout'])

    years = comparison['yearly']
    fig, ax = plt.subplots(figsize=(13.4, 4.0), layout='constrained')
    for key, title, color, style in [('old_same_roster','旧A同名单',ORANGE,'-'),('new','新版T0',BLUE,'-'),('persistence','公开历史参照',GREY,'--')]:
        ax.plot([x['year'] for x in years],[x[key]['mae_pp'] for x in years],marker='o',label=title,color=color,ls=style,lw=2)
    ax.set(xlabel='年份（2025仅1—10月）', ylabel='全国Q9中位数MAE（pp，越低越好）', title='改善随时期变化：2021进步，2020与2025退步')
    ax.set_xticks([x['year'] for x in years]); ax.grid(alpha=.17); ax.legend(frameon=False)
    save_plot(fig,out,'03_A_years')
    register('03_A_years','A逐年MAE', '同一新版名单/权重的版本比较；曲线不是置信区间。新旧同时改变时间、数量与路由，不能识别某个组件的单独因果作用。', ['A_T0_readout'])

    same = comparison['same_roster']['metrics']
    fig, axes = plt.subplots(1, 2, figsize=(13.4,4.1),layout='constrained')
    ax = axes[0]
    vals = [same['old']['q9']['cross_section_w1_pp'],same['new']['q9']['cross_section_w1_pp']]
    bars = ax.bar(['旧A','新版T0'],vals,color=[ORANGE,BLUE],width=.55)
    ax.set(ylabel='W1距离（pp，越低越接近）',title='同支持：分布距离略退步',ylim=(0,2.8))
    for bar,v in zip(bars,vals):ax.text(bar.get_x()+bar.get_width()/2,v+.04,f'{v:.3f}',ha='center')
    ax=axes[1]; vals=[same['old']['q9']['cross_person_iqr_pp'],same['new']['q9']['cross_person_iqr_pp'],same['new']['q9']['real_cross_person_iqr_pp']]
    bars=ax.bar(['旧A','新版T0','真人'],vals,color=[ORANGE,BLUE,BLACK],width=.6)
    ax.set(ylabel='跨人IQR（pp）',title='中心改善，微观分歧仍偏窄',ylim=(0,6.2))
    for bar,v in zip(bars,vals):ax.text(bar.get_x()+bar.get_width()/2,v+.07,f'{v:.3f}',ha='center')
    save_plot(fig,out,'04_A_micro')
    register('04_A_micro','同支持微观诊断', '41,042个共同合法Q9人月，月份等权；同一真人、权重和计分器。跨人IQR不是个人主观概率密度内部IQR。这里不与全波次Normal的W1交叉混算。', ['A_comparison_summary'])

    fig, axes = plt.subplots(1,3,figsize=(13.4,4.0),layout='constrained')
    for ax, key, title in [(axes[0],'mae_pp','A全国MAE'),(axes[1],'w1','A全波次W1'),(axes[2],'iqr','A全波次跨人IQR')]:
        if key=='mae_pp':vals=[stats(a,'sim_pp')['mae_pp'],stats(an,'CoreNormal_tau8_pure')['mae_pp']]
        elif key=='w1':vals=[ext['micro_summary_expected']['before_q9_w1_pp'],ext['micro_summary_expected']['expanded_q9_w1_pp']]
        else:vals=[ext['micro_summary_expected']['before_q9_iqr_pp'],ext['micro_summary_expected']['expanded_q9_iqr_pp']]
        ax.plot([0,1],vals,color=PURPLE,marker='o',lw=2)
        ax.set_xticks([0,1],['Core','Core＋Normal']);ax.set(title=title,xlabel='统计表示',ylabel='pp')
        if key=='iqr': ax.axhline(ext['micro_summary_expected']['truth_q9_iqr_pp'],color=BLACK,ls='--',label='真人IQR'); ax.legend(frameon=False)
        ax.set_ylim(0,5.9 if key=='iqr' else (2.65 if key=='w1' else .36)); ax.grid(axis='y',alpha=.15)
        for i,v in enumerate(vals):ax.annotate(f'{v:.6f}',(i,v),xytext=(0,10 if i==0 else -20),textcoords='offset points',ha='center',fontsize=10)
    save_plot(fig,out,'05_Normal')
    register('05_Normal','统计扩展改变了什么', 'A82、τ8，Core/Normal比较均对同一完整调查波次。纵轴从0起避免放大0.003pp差异。扩展人口表示不等于增加LLM信息；B扩展结果另列。', ['A_Normal','A_micro_monthly'])

    fig, axes=plt.subplots(2,1,figsize=(13.4,7.5),layout='constrained')
    line_plot(axes[0],b,[('truth_pp','官方SCE（评价真值）',BLACK,'-'),('Core_pp','B原始Core',BLUE,'-'),('Core_blend_pp','固定组合',ORANGE,'-'),('baseline_pp','公开历史持续性',GREY,'--')],'B11：原始模拟上偏，组合抑制偏差')
    for field,title,color in [('Core_pp','原始Core',BLUE),('Core_blend_pp','固定组合',ORANGE),('baseline_pp','持续性',GREY)]:
        axes[1].plot(range(11),[abs(float(r[field])-float(r['truth_pp'])) for r in b],marker='o',color=color,label=title)
    axes[1].set_xticks(range(11),[month(r['month']) for r in b],rotation=25,ha='right',fontsize=9)
    axes[1].set(xlabel='目标月',ylabel='绝对误差（pp）',title='相同11个月的逐月误差');axes[1].legend(frameon=False,ncol=3);axes[1].grid(axis='y',alpha=.15)
    save_plot(fig,out,'06_B_path')
    register('06_B_path','最新B11路径与误差', '2025-11—2026-09、每月512 Core，固定组合λ=0.133976257；非本期拟参。合成个人日期只限制E，P/先验按全局D准备；不称完全认证的严格实时预测。', ['B_latest'])

    fig, axes=plt.subplots(2,1,figsize=(13.4,7.3),layout='constrained')
    line_plot(axes[0],rec,[('truth_pp','官方SCE（评价真值）',BLACK,'-'),('recursive_pp','固定家庭月度递推',BLUE,'-'),('independently_initialized_B_pp','独立初始化B',ORANGE,'-')],'月度自主链：共用根月后，后段逐渐上偏')
    axes[0].axvline(.5,color=GREY,ls=':');axes[0].text(.99,.04,'主评价从2025-12开始',transform=axes[0].transAxes,ha='right',va='bottom',fontsize=10)
    post=rec[1:]
    errors=[float(r['recursive_pp'])-float(r['truth_pp']) for r in post]
    axes[1].plot(range(10),errors,marker='o',color=BLUE,label='递推减真实SCE')
    axes[1].axhline(0,color=BLACK,lw=.9); axes[1].set_xticks(range(10),[month(r['month']) for r in post],rotation=25,ha='right',fontsize=9)
    axes[1].set(xlabel='目标月（排除根月）',ylabel='有符号偏差（pp）',title='高估从2026年5月后更明显，并非每月单调累积');axes[1].grid(axis='y',alpha=.15)
    save_plot(fig,out,'07_monthly_recursion')
    register('07_monthly_recursion','月度信念递推与漂移', '固定512户，无进出/Normal，根月后不重新对齐全国先验。主要10个月；与独立B有人口、信息和状态制度差异，属于描述性比较。', ['monthly_recursion'])

    fig, axes=plt.subplots(2,1,figsize=(13.4,7.6),layout='constrained')
    dates=[datetime.fromisoformat(r['cutoff']).replace(tzinfo=None) for r in weeks]
    axes[0].plot(dates,[float(r['q9_median_pp']) for r in weeks],color=BLUE,marker='.',lw=1.9,label='47周原始模拟')
    last={}
    for date,row in zip(dates,weeks):last[row['month']]=date
    end=[last[month(r['month'])] for r in wp]
    axes[0].plot(end,[float(r['truth_pp']) for r in wp],color=BLACK,marker='o',lw=1.5,label='当月官方SCE（事后评价）')
    axes[0].plot(end,[float(r['blend_pp']) for r in wp],color=ORANGE,marker='s',lw=1.3,ls='--',label='月内最后周点固定组合')
    reset=[(d,r) for d,r in zip(dates,weeks) if r['reset_required']=='True']
    axes[0].scatter([d for d,r in reset],[float(r['q9_median_pp']) for d,r in reset],facecolors='white',edgecolors=BLUE,s=45,zorder=4,label='公开历史值可用后的重校准周')
    axes[0].set(xlabel='周截止（每周五纽约日末）',ylabel='一年期通胀预期（%）',title='周度：历史发布后校准，周期内沿自身前态更新');axes[0].legend(frameon=False,ncol=2);axes[0].grid(alpha=.15)
    axes[0].xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    axes[0].xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    axes[0].tick_params(axis='x',rotation=20,labelsize=9)
    for field,title,color in [('raw_pp','原始模拟',BLUE),('blend_pp','固定组合',ORANGE),('anchor_pp','持续性',GREY)]:
        axes[1].plot(range(11),[abs(float(r[field])-float(r['truth_pp'])) for r in wp],color=color,label=title,marker='o')
    axes[1].set_xticks(range(11),[month(r['month']) for r in wp],rotation=25,ha='right',fontsize=9)
    axes[1].set(xlabel='目标月（取最后预定周点）',ylabel='绝对误差（pp）',title='主评价11个月：5个月改善、6个月退步，9月漏判上行');axes[1].legend(frameon=False,ncol=3);axes[1].grid(axis='y',alpha=.15)
    save_plot(fig,out,'08_weekly')
    register('08_weekly','47周路径与11月主评价', '2025-11—2026-09、固定300户、无Normal。重校准只使用当时已公开历史SCE；黑线是事后评价目标，不是提前输入。原始0.151581不是输出层加权组合。', ['weekly_path','weekly_primary'])

    outcomes=['REVOLSL','wage_growth_overall','PCEDGC96','MICH']
    olab=['循环信贷','工资增长','实际耐用品消费','Michigan通胀预期']
    by={(r['outcome'],int(r['horizon']),r['model']):r for r in dm if r['scope']=='A'}
    improvement=[]; blend_gain=[]
    for o in outcomes:
        improvement.append([100*(1-float(by[o,h,'simulated_sce']['rmse'])/float(by[o,h,'official_sce']['rmse'])) for h in [1,2,3]])
    blend_gain=[100*(1-float(by['REVOLSL',h,'blended_sce']['rmse'])/float(by['REVOLSL',h,'official_sce']['rmse'])) for h in [1,2,3]]
    for row in dc:
        if row['scope']=='A' and row['reference']=='official_sce' and row['candidate'] in ['simulated_sce','blended_sce']:
            expected=100*float(row['rmse_improvement'])
            actual=100*(1-float(by[row['outcome'],int(row['horizon']),row['candidate']]['rmse'])/float(by[row['outcome'],int(row['horizon']),'official_sce']['rmse']))
            close(actual,expected,'downstream-improvement')
            validated.append('downstream/'+row['outcome']+'/'+row['horizon']+'/'+row['candidate'])
    fig,axes=plt.subplots(1,2,figsize=(13.4,4.5),layout='constrained',gridspec_kw={'width_ratios':[1,1.1]})
    for values,label,color in [(improvement[0],'月度原始模拟替代官方SCE',BLUE),(blend_gain,'最终组合替代官方SCE',ORANGE)]:
        axes[0].plot([1,2,3],values,marker='o',color=color,lw=2,label=label)
        for h,v in zip([1,2,3],values):axes[0].annotate(f'{v:+.2f}%',(h,v),xytext=(0,9 if color==BLUE else -18),textcoords='offset points',ha='center',fontsize=10)
    axes[0].axhline(0,color=GREY,ls='--');axes[0].set_xticks([1,2,3]);axes[0].set(xlabel='预测期（月）',ylabel='相对官方SCE模型的RMSE改善（%）',title='循环信贷：局部正向用途');axes[0].legend(frameon=False,loc='upper left',fontsize=9);axes[0].set_ylim(-6,12);axes[0].grid(axis='y',alpha=.15)
    matrix=np.array(improvement);bound=max(abs(matrix.min()),abs(matrix.max()),1)
    cmap=LinearSegmentedColormap.from_list('gain',['#cb6116','#f8f7f3','#1769aa'])
    im=axes[1].imshow(matrix,cmap=cmap,norm=TwoSlopeNorm(vmin=-bound,vcenter=0,vmax=bound),aspect='auto')
    axes[1].set_yticks(range(4),olab);axes[1].set_xticks(range(3),['1个月','2个月','3个月']);axes[1].set(xlabel='预测期',ylabel='下游结局',title='所有12项原始模拟对照，5正7负')
    for i in range(4):
        for j in range(3):axes[1].text(j,i,f'{matrix[i,j]:+.2f}%',ha='center',va='center',color='white' if abs(matrix[i,j])>bound*.55 else BLACK,fontsize=11)
    fig.colorbar(im,ax=axes[1],label='RMSE改善（%，正为好）',shrink=.85)
    save_plot(fig,out,'09_downstream')
    register('09_downstream','循环信贷及全部结局', 'A扩展窗口41—44个有效原点，同一结局/预测期各模型共同支持；8模型同结构比较。输入是月度A/B Core＋Normal，不是周度。工资/MICH预测水平变化，信贷/耐用品预测累计对数增长。当前版本控制和上游非嵌套限制保留；信贷历史均值基线仍更强。', ['downstream_metrics','downstream_contrasts'])

    copied=[]
    for src,name,caption in [
        ('docs/reports/final_report_draft_v05/assets/q9_observed_example.png','00_real_Q9.png','2025-06一份真实匿名SCE答卷；密度均值约3.03%、个人密度IQR约2.61pp。不代表总体。'),
        ('docs/reports/final_report_draft_v05/assets/information_routes.png','00_information_routes.png','既有理论路径示意：购物价格和新闻是不同通道；箭头为研究假设，不是已估计的因果系数。具体当前参数以本册T0说明为准。'),
        ('docs/reports/final_report_draft_v05/assets/news_evidence.png','10_news_development.png','历史八期V3.2、1116共同个人月、两遍：随机3/8/20相对固定8篇的开发对照，不是当前四档全量成绩。')]:
        path=ROOT/src;source_paths.add(path);shutil.copyfile(path,out/'figures'/name)
        copied.append({'file':'figures/'+name,'source':src,'sha256':digest(path),'caption':caption})

    metrics=[]
    def metric(group,label,rows,key,scope,source):
        s=stats(rows,key);metrics.append({'group':group,'label':label,'scope':scope,'source':source,**s});return s
    for key,label in [('sim_pp','A新版Core'),('old_same_roster_pp','A旧版同名单'),('old_sim_pp','A旧版原名单参照'),('anchor_pp','A公开历史参照')]:metric('A82',label,a,key,'2019-01—2025-10，82个月','A_T0_readout')
    for key,label in [('CoreNormal_tau8_pure','A Core＋Normal'),('CoreNormal_tau8_blend_mse','A Normal固定组合')]:metric('A82',label,an,key,'全82月描述，不作为留出成绩','A_Normal')
    late_a=[r for r in a if r['month']>='2023-01']; late_an=[r for r in an if month(r['month'])>='2023-01']
    fit=bsource['A82_personal_T0']['chronological_combinations']['mse']
    aa=[{**r,'blend_pp':(1-fit['simulation_weight'])*float(r['anchor_pp'])+fit['simulation_weight']*float(r['sim_pp'])} for r in late_a]
    metric('A_late34','A Core固定组合',aa,'blend_pp','早48拟权，后34检查，非全项目盲测','A_T0_readout')
    metric('A_late34','公开历史参照',aa,'anchor_pp','2023-01—2025-10，34个月','A_T0_readout')
    metric('A_late34','A Normal固定组合',late_an,'CoreNormal_tau8_blend_mse','对应τ8权重0.134964302','A_Normal')
    for key,label in [('Core_pp','B原始Core'),('expanded_pp','B Core＋Normal'),('Core_blend_pp','B固定组合'),('expanded_blend_pp','B Normal固定组合'),('baseline_pp','B持续性')]:metric('B11',label,b,key,'2025-11—2026-09，11个月','B_latest')
    for key,label in [('recursive_pp','月度递推原始'),('fixed_blend_pp','月度递推固定组合'),('anchor_pp','月度持续性'),('independently_initialized_B_pp','独立B原始（同10月）'),('independent_fixed_blend_pp','独立B组合（同10月）')]:metric('monthly10',label,rec[1:],key,'排除共同2025-11根月，后10个月','monthly_recursion')
    for key,label in [('raw_pp','周度原始'),('blend_pp','周度固定组合'),('anchor_pp','周度持续性'),('held_prior_pp','周期起点保持不动'),('macro_pp','周度宏观无模拟'),('macro_sim_pp','周度宏观加模拟')]:metric('weekly11',label,wp,key,'每月最后预定周点，11个月','weekly_primary')

    grid_extract={'candidate_count':len(grids['candidates']),'development_gvif':grids['associations']['development']['within_month_block_gvif'],'cramers_v':grids['associations']['development']['weighted_cramers_v'],'conditional_information':grids['conditional_information'],'original_recommendation':grids['selection'],'current_54':next(x for x in grids['candidates'] if x['name']=='education+numeracy+income+age')}
    # Do not copy respondent or diary records; only selected aggregate candidate scores.
    grid_extract['current_54']={k:v for k,v in grid_extract['current_54'].items() if k in ['name','fields','cartesian_cells','development_cv','temporal','support']}
    dossier={'schema':'sce_author_evidence_workbook/v1','status':'materials_for_author_review_not_manuscript','date':'2026-10-27','new_API_calls':0,'new_parameter_fits':0,'manuscript_modified':False,'package_version':pointer['package_version'],'package_sha256':pointer['archive_sha256'],'metrics':metrics,'micro_full_wave':ext['micro_summary_expected'],'micro_same_roster':comparison['same_roster'],'A_yearly':comparison['yearly'],'A_combinations':bsource['A82_personal_T0']['chronological_combinations'],'figures':figures,'existing_figures':copied,'grid':grid_extract,'news_quantity_evidence':news['evidence'],'credit_rmse_improvement_percent':{'raw':improvement[0],'blend':blend_gain},'all_outcomes_raw_rmse_improvement_percent':dict(zip(outcomes,improvement)),'downstream_positive_cells':{'raw':int(np.sum(matrix>0)),'blend':sum(float(r['rmse_improvement'])>0 for r in dc if r['scope']=='A' and r['reference']=='official_sce' and r['candidate']=='blended_sce'),'total':12},'blend_weights':{'A_Core':fit['simulation_weight'],'A_Normal':esource['A82_Core_Normal_tau8']['fixed_blend']['weight'],'B_monthly_weekly':esource['B11_latest_Core_and_Normal']['fixed_blend']['weight']},'cost_scope':'No new API calls. Historical cost figures must name the run; this workbook is not a whole-project invoice.'}
    # Retain compact public tables for later editorial reuse.
    with (out/'numbers.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(metrics[0]),lineterminator='\n');writer.writeheader();writer.writerows(metrics)
    with (out/'A_yearly.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['year','n_months','old_original_mae_pp','old_same_roster_mae_pp','T0_mae_pp','persistence_mae_pp'],lineterminator='\n');writer.writeheader()
        for row in comparison['yearly']:writer.writerow({'year':row['year'],'n_months':row['n_months'],'old_original_mae_pp':row['old']['mae_pp'],'old_same_roster_mae_pp':row['old_same_roster']['mae_pp'],'T0_mae_pp':row['new']['mae_pp'],'persistence_mae_pp':row['persistence']['mae_pp']})
    source_paths.update([ROOT/'submission/latest_package.json',HERE/'build.py',HERE/'editorial_materials.json',ROOT/'docs/workstreams/20261027_final_delivery/framework.md'])
    editorial=load_json(HERE/'editorial_materials.json')
    for section in editorial['sections']:
        for path in section.get('source_paths',[]):source_paths.add(ROOT/path)
    write_json(out/'materials.json',dossier)
    md=render_markdown(editorial,dossier,out)
    (out/'README.md').write_text(md)
    html_page=render_html(md)
    (out/'index.html').write_text(html_page)
    for p in source_paths:
        if not p.is_file():raise ValueError('Missing evidence source: '+str(p))
    aliases={'grid_dimensions':ROOT/'outputs/sce_grid_dimensions_20261023_v1/summary.json','A_T0_readout':ROOT/'outputs/sce_full_a_t0_readout_20261026_v1/monthly_national.csv','A_comparison_summary':data/'A82_comparison_summary.json','A_Normal':data/'A82_Core_Normal_tau8.csv','A_micro_monthly':data/'A82_micro_monthly_summaries.csv','B_latest':data/'B11_latest_Core_and_Normal.csv','monthly_recursion':data/'monthly_autonomous_recursion.csv','weekly_path':data/'weekly47_path.csv','weekly_primary':data/'weekly47_monthly11_primary.csv','downstream_metrics':data/'downstream_model_metrics.csv','downstream_contrasts':data/'downstream_contrasts.csv'}
    source_index={'schema':'sce_materials_sources/v1','files':[{'path':str(p.relative_to(ROOT)),'sha256':digest(p)} for p in sorted(source_paths)],'figure_source_aliases':{k:str(p.relative_to(ROOT)) for k,p in aliases.items()},'primary_web_checks':editorial['primary_web_checks'],'source_scope':'Frozen public aggregates and already published anonymized figures only; no raw micro records or news text.'}
    write_json(out/'sources.json',source_index)
    validation={'status':'passed_offline_materials_checks','new_API_calls':0,'new_parameter_fits':0,'frozen_metric_or_blend_checks':len(validated),'new_plot_groups':len(figures),'existing_anonymized_figures_reused':len(copied),'local_sources':len(source_paths),'official_report_and_package_modified':False,'dossier_is_a_manuscript':False}
    write_json(out/'validation.json',validation)
    write_json(out/'manifest.json',{'schema':'sce_materials_manifest/v1','files_sha256':{str(p.relative_to(out)):digest(p) for p in sorted(out.rglob('*')) if p.is_file()},'build_source':str(HERE.relative_to(ROOT)),'new_API_calls':0})
    return validation


def write_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def table(headers, rows):
    def clean(x):return str(x).replace('|','／').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(clean(v) for v in r)+' |' for r in rows])


def render_markdown(content,data,out):
    figures={r['id']:r for r in data['figures']}
    parts=['# SCE项目证据材料册','供作者理解和挑选素材 · 2026-10-27 · 非论文正文',content['intro'],
           '**阅读顺序：** 先看01—03的研究对象与设计，再看04—09的分任务结果，最后看10—12的实验取舍、贡献边界和写作讨论。每节把事实、解释和局限分开；方法与来源可展开。',
           '[返回交付框架](../index.html) · [数字清单](numbers.csv) · [结构化材料](materials.json) · [来源与哈希](sources.json) · [离线核对](validation.json)']
    for section in content['sections']:
        parts.extend(['## '+section['title'], '**先抓住这一点：** '+section['takeaway']])
        parts.extend(section.get('paragraphs',[]))
        if section.get('facts'):
            parts.append('### 已有事实')
            parts.extend('- '+x for x in section['facts'])
        if section.get('metric_group'):
            rows=[r for r in data['metrics'] if r['group']==section['metric_group']]
            if section['metric_group']=='A82':rows=[r for r in rows if r['label'] not in ['A Normal固定组合']]
            parts.append(table(['序列/口径','月数','MAE（pp）','RMSE（pp）'],[[r['label'],r['n'],f"{r['mae_pp']:.6f}",f"{r['rmse_pp']:.6f}"] for r in rows]))
        for id in section.get('figures',[]):
            if id.startswith('existing:'):
                f=next(r for r in data['existing_figures'] if id[9:]==Path(r['file']).stem)
                parts.extend(['![已有匿名示例或开发证据]('+f['file']+')','*'+f['caption']+'*'])
            else:
                f=figures[id];parts.extend(['!['+f['title']+']('+f['file']+')','*'+f['caption']+'*','[矢量版]('+f['vector']+')'])
        if section.get('reading'):
            parts.append('### 这组材料怎样理解')
            parts.extend('- '+x for x in section['reading'])
        if section.get('limits'):
            parts.append('### 结论边界')
            parts.extend('- '+x for x in section['limits'])
        if section.get('details'):
            parts.append('<details><summary>展开技术细节与设计依据</summary>\n')
            parts.extend(section['details']);parts.append('</details>')
        if section.get('use'):
            parts.append('**后续写作用途：** '+section['use'])
        if section.get('source_paths'):
            parts.append('**证据入口：**'+' · '.join(link(ROOT/p,Path(p).name,out) for p in section['source_paths']))
    parts.extend(['## 数字与图表使用约定',
                  '- 所有全国误差默认单位为pp，通胀预期水平为%；RMSE改善为百分比，不与pp混淆。下游信贷/耐用品的结局是累计对数增长，不是余额水平。',
                  '- 每张图附时期、人数/统计单位、原始/组合与支持。不同任务的数字不汇总为一个排行榜；没有新的模拟、密度拟合或参数搜索。',
                  '- 原稿v05、研究包v05、原始运行和已验收ZIP均不变。这里的候选论点与图表要经作者讨论后，才进入下一版论文。',
                  '### 复建（全新目录、零API）',
                  '```bash\n/Users/wushuyue/anaconda3/envs/socioverse/bin/python scripts/build_sce_paper_materials.py \\\n  --out docs/workstreams/20261027_final_delivery/materials_rebuild_new\n```'])
    return '\n\n'.join(parts)+'\n'


def render_html(md):
    from markdown_it import MarkdownIt
    renderer=MarkdownIt('commonmark',{'html':True}).enable('table')
    body=renderer.render(md)
    entries=[]
    def heading(match):
        title=match.group(1); ident='part-'+str(len(entries));entries.append((ident,re.sub('<[^>]+>','',title)))
        return '<h2 id="'+ident+'">'+title+'</h2>'
    body=re.sub(r'<h2>(.*?)</h2>',heading,body)
    nav=''.join('<a href="#'+key+'">'+html.escape(label)+'</a>' for key,label in entries)
    css='''*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:22px}body{margin:0;background:#f5f4ef;color:#252b33;font:16px/1.85 system-ui,-apple-system,"PingFang SC",sans-serif}a{color:#175a91;text-underline-offset:3px}main{min-width:0}h1{font-size:30px;line-height:1.35;margin-top:0;letter-spacing:.02em}h2{font-size:25px;line-height:1.45;border-top:2px solid #ccd1d5;padding-top:34px;margin-top:58px}h3{font-size:18px;line-height:1.5;margin-top:24px}p{margin:12px 0}strong{font-weight:650}li{margin:8px 0}ul{padding-left:23px}.layout{max-width:1480px;margin:auto;display:grid;grid-template-columns:238px minmax(0,1060px);gap:42px;padding:38px 28px}nav{position:sticky;top:20px;align-self:start;max-height:92vh;overflow:auto;font-size:13px;line-height:1.65}nav a{display:block;text-decoration:none;padding:8px 6px;border-bottom:1px solid #ddd}nav a.active{color:#a14f09;font-weight:700;background:#efebe1}nav .label{font-size:15px;font-weight:700;margin:0 0 16px}nav .small{font-size:12px;color:#616973;margin-top:15px}img{display:block;width:100%;height:auto;margin:22px 0 8px;background:white;border:1px solid #d8dce0}p:has(> em){font-size:13px;line-height:1.7;color:#505962;margin-top:5px}table{border-collapse:collapse;width:100%;font-size:14px;margin:20px 0;background:#fff}th,td{text-align:left;padding:11px 12px;border-bottom:1px solid #d6dce0;font-variant-numeric:tabular-nums}th{background:#e9edf0;font-weight:650}td:not(:first-child){white-space:nowrap}details{border-top:1px solid #cbd1d6;border-bottom:1px solid #cbd1d6;padding:13px 16px;margin:24px 0;background:#eeefeb}summary{cursor:pointer;color:#235b8e;font-weight:600}details p{font-size:14px}pre{background:#e8ebed;overflow:auto;padding:16px;font-size:12px}code{font-family:ui-monospace,Menlo,monospace;overflow-wrap:anywhere}button{background:#fff;border:1px solid #aaa;padding:8px 12px;border-radius:4px;font:inherit;font-size:12px;cursor:pointer;margin-bottom:14px}.notice{border-left:4px solid #c46a16;background:#efe9dc;padding:15px 20px;margin-bottom:26px;font-size:14px}.footer{color:#626b75;font-size:13px;margin:40px 0}@media(max-width:1000px){.layout{grid-template-columns:1fr;padding:20px;gap:12px}nav{position:static;max-height:none;display:flex;flex-wrap:wrap;gap:5px}nav a{padding:4px 8px;border:1px solid #ddd}nav .small{display:none}nav .label{width:100%}h1{font-size:26px}h2{font-size:22px}table{display:block;overflow:auto}}@media print{nav,.notice,button{display:none}.layout{display:block;padding:0}body{font-size:11px;background:white}h2{break-before:page}img{max-height:18cm;object-fit:contain}details{display:block}details>*{display:block}}'''
    js='''document.querySelector('#toggleDetails').addEventListener('click',()=>{const ds=[...document.querySelectorAll('details')];const on=ds.some(d=>!d.open);ds.forEach(d=>d.open=on)});const obs=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('active',a.hash==='#'+e.target.id))}})},{rootMargin:'0px 0px -78% 0px'});document.querySelectorAll('h2').forEach(x=>obs.observe(x));'''
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SCE项目证据材料册 · 作者审阅</title><style>'+css+'</style></head><body><div class="layout"><nav><p class="label">SCE证据材料册</p><button id="toggleDetails">展开 / 收起全部技术细节</button>'+nav+'<p class="small">先理解材料，再组织论文。<br>数字来自冻结聚合；本册0新API。</p></nav><main><div class="notice">作者审阅版：不受论文8页限制。这份材料册整理数据、图表、设计依据与候选论点，不是新论文，也不替换现有报告和研究包。</div>'+body+'<p class="footer">结构化数字：materials.json / numbers.csv。每张新图同时提供PNG与SVG；来源哈希见sources.json。</p></main></div><script>'+js+'</script></body></html>'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.out),ensure_ascii=False,indent=2))
