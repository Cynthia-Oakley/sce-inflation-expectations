"""Build aggregate figures and an insert for the existing SCE reading page."""
from datetime import datetime, timezone
from html import escape
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
GREEN, ORANGE, GREY = '#2e685e', '#a45b38', '#6e7780'
LABELS = {'Under 40': '18—39岁', '40 to 60': '40—59岁', 'Over 60': '60岁及以上',
          'under_50k': '收入低于5万美元', '50k_to_100k': '收入5—10万美元', 'over_100k': '收入高于10万美元',
          'college': '大学及以上', 'some_college': '部分大学教育', 'high_school': '高中及以下',
          'high': '高数理', 'low': '低数理', 'Northeast': '东北', 'Midwest': '中西部', 'South': '南部', 'West': '西部',
          'owner': '自有住房', 'renter': '租房', 'employed': '就业', 'retired': '退休',
          'unemployed': '失业', 'disabled': '因残障未就业', 'homemaker': '照料家庭', 'missing': '未知',
          'on_leave': '休假', 'other': '其他', 'student': '学生'}
DIMENSIONS = {'age': '年龄', 'income': '家庭收入', 'education': '教育', 'numeracy': '数理能力',
              'region': '地区', 'housing': '住房', 'employment': '就业'}
METRICS = ('q9_center_pp', 'q9_center_mae_pp', 'q9_center_bias_pp', 'individual_density_mean_mae_pp',
           'cross_section_w1_pp', 'cross_person_iqr_pp', 'delta_w1_pp', 'delta_abs_mean_pp',
           'individual_mean_mse_pp2', 'mean_error_squared_pp2', 'centered_error_variance_pp2')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compact_cell(row):
    result = {k: row.get(k) for k in ('month', 'n', 'ess', 'suppressed')}
    if not row['suppressed']:
        for name, key in [('truth', 'truth'), ('model', 'model_average_of_repeat_metrics'), ('copy', 'copy_previous')]:
            result[name] = {k: row[key][k] for k in METRICS if k in row[key]}
    return result


def compact_scope(row):
    result = {k: row[k] for k in ('n_months_reported', 'n_person_months', 'months_reported', 'monthly_ess', 'coverage_complete')}
    for name, key in [('truth', 'truth'), ('model', 'model_average_of_month_repeat_metrics'), ('copy', 'copy_previous')]:
        result[name] = {k: row[key][k] for k in METRICS if k in row[key]}
    return result


def build_public(d, controls, details):
    return {'status': 'exploratory_cached_data_no_new_api', 'date_beijing': '2026-10-18',
            'new_api_calls': 0, 'refitted_probability_vectors': 0,
            'coverage': d['coverage'], 'monthly': [compact_cell(r) for r in d['monthly']],
            'scopes': {k: compact_scope(v) for k, v in d['scopes'].items()},
            'demographics': {dim: {label: {'monthly': [compact_cell(r) for r in rows],
                                         'all_months': compact_scope(d['demographics']['scopes'][dim][label]['all_months'])}
                                  for label, rows in labels.items()}
                             for dim, labels in d['demographics']['monthly'].items()},
            'updates': {threshold: {bucket: {'diagnostic': v['scopes']['all_months'],
                                             'detail': details['by_threshold'][threshold][bucket]['scopes']['all_months']}
                                    for bucket, v in groups.items()}
                        for threshold, groups in d['updates']['by_threshold'].items()},
            'prior_levels': {k: compact_scope(v['all_months']) for k,v in d['prior_levels']['scopes'].items()},
            'controls': controls['controls'], 'probability_shape': controls['probability_shape'],
            'q8_secondary_crosscheck': controls['q8_secondary_crosscheck'],
            'environment': controls['environment'], 'method': d['method'], 'limitations': d['limitations']}


def footer(fig, text):
    fig.text(.035, .025, text, va='bottom', fontsize=9, color='#46514e')


def save(fig, path):
    fig.savefig(path.with_suffix('.png'), dpi=170)
    svg = path.with_suffix('.svg')
    fig.savefig(svg)
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    plt.close(fig)


def figures(public, out):
    out.mkdir(parents=True)
    plt.rcParams.update({'font.family': ['Times New Roman', 'Kaiti SC', 'STKaiti'], 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False, 'axes.unicode_minus': False})
    m = public['monthly']; x = np.arange(len(m)); labels = [f"{r['month']//100}-{r['month']%100:02d}" for r in m]
    fig, axes = plt.subplots(2, 1, figsize=(12, 7.3), sharex=True, gridspec_kw={'height_ratios': [1.6, 1]})
    for name, label, color, marker in [('truth', '真人同样本', GREY, 'o'), ('model', 'Simulation', GREEN, 's'), ('copy', '照抄本人上期', ORANGE, '^')]:
        axes[0].plot(x, [r[name]['q9_center_pp'] for r in m], marker=marker, color=color, label=label, linewidth=1.8)
    axes[0].set_ylabel('Q9群体中位数（%）'); axes[0].legend(ncol=3, frameon=False); axes[0].set_title('总体水平偏差随时期改变，不能用统一加减常数消除')
    axes[1].bar(x-.15, [r['model']['q9_center_bias_pp'] for r in m], .3, color=GREEN, label='Simulation − 真人')
    axes[1].bar(x+.15, [r['copy']['q9_center_bias_pp'] for r in m], .3, color=ORANGE, label='上期 − 真人')
    axes[1].axhline(0, color=GREY, linewidth=.8); axes[1].set_ylabel('带符号偏差（pp）'); axes[1].set_xlabel('预选调查月份（非连续月）')
    axes[1].set_xticks(x, labels, rotation=40, ha='right'); axes[1].legend(frameon=False, ncol=2)
    for ax in axes: ax.grid(axis='y', alpha=.16)
    fig.subplots_adjust(left=.085, right=.98, top=.92, bottom=.20, hspace=.18)
    footer(fig, '来源：2020—2025年12个预选月，2,284个共同有效回访者人月；设计×调查权重，月等权。\n模型两遍分别计算指标后平均；连线仅帮助阅读，不表示连续轨迹。Q9中心为个人拟合均值的加权中位数。')
    save(fig, out/'monthly_gaps')

    selected = []
    for dim in ('age', 'income', 'education', 'numeracy'):
        for key, item in public['demographics'][dim].items():
            a = item['all_months']
            if a['n_months_reported'] == 12:
                selected.append((LABELS.get(key, key), a))
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 7.4), gridspec_kw={'width_ratios': [1, 1]})
    y = np.arange(len(selected))
    for name, label, color, shift in [('model', 'Simulation', GREEN, -.14), ('copy', '照抄上期', ORANGE, .14)]:
        axes[0].barh(y+shift, [r[name]['q9_center_mae_pp'] for _,r in selected], height=.27, color=color, label=label)
    axes[0].set_yticks(y, [name for name,_ in selected]); axes[0].invert_yaxis(); axes[0].set_xlabel('组内群体中位数MAE（pp）'); axes[0].set_ylabel('预先指定的人口分组')
    for name, label, color, shift in [('truth', '真人', GREY, -.14), ('model', 'Simulation', GREEN, .14)]:
        axes[1].barh(y+shift, [r[name]['cross_person_iqr_pp'] for _,r in selected], height=.27, color=color, label=label)
    axes[1].set_yticks(y, [name for name,_ in selected]); axes[1].invert_yaxis(); axes[1].set_xlabel('组内人际IQR（pp）'); axes[1].set_ylabel('预先指定的人口分组')
    for ax in axes: ax.legend(frameon=False); ax.grid(axis='x', alpha=.15); ax.set_axisbelow(True)
    fig.suptitle('多个群体内部都存在差异压缩；低数理、低学历群体的中心误差较大', y=.98)
    fig.subplots_adjust(left=.14, right=.98, top=.91, bottom=.17, wspace=.55)
    footer(fig, '来源同上；每个组均报告相同12月，单月n≥10，先逐遍计算后月等权。组间误差不是因果效应；\n不同组的真人分布宽度也不同。数值不包含样本不足的小组；七维度完整表见阅读页。')
    save(fig, out/'population_gaps')

    groups = public['updates']['0.5']; keys = ['stable', 'up', 'down']; names = ['真人变化≤0.5pp', '真人上调>0.5pp', '真人下调>0.5pp']
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    for name, label, color, shift in [('model_person_mae_pp', 'Simulation', GREEN, -.16), ('copy_person_mae_pp', '照抄上期', ORANGE, .16)]:
        axes[0].bar(np.arange(3)+shift, [groups[k]['diagnostic']['metrics'][name] for k in keys], width=.3, label=label, color=color)
    axes[0].set_xticks(np.arange(3), names); axes[0].set_ylabel('个人Q9均值MAE（pp）'); axes[0].set_xlabel('按本期真人实际变化划分（事后）'); axes[0].legend(frameon=False)
    for name, label, color, shift in [('truth_abs_update_mean_pp', '真人', GREY, -.16), ('model_abs_update_mean_pp', 'Simulation', GREEN, .16)]:
        axes[1].bar(np.arange(3)+shift, [groups[k]['diagnostic']['metrics'][name] for k in keys], width=.3, label=label, color=color)
    axes[1].set_xticks(np.arange(3), names); axes[1].set_ylabel('平均绝对更新幅度（pp）'); axes[1].set_xlabel('按本期真人实际变化划分（事后）'); axes[1].legend(frameon=False)
    for ax in axes: ax.grid(axis='y', alpha=.15); ax.set_axisbelow(True)
    fig.suptitle('并非所有人都改动过多：真正稳定者改多，真正大幅调整者又改少', y=.97)
    fig.subplots_adjust(left=.08, right=.98, top=.86, bottom=.23, wspace=.25)
    footer(fig, '来源同上；真人稳定/上调/下调组加权占比约32.0%/34.1%/33.9%。阈值0.25与1pp时方向相同。\n稳定组照抄较准由分组定义部分保证；这些组不能提前观察，不可直接据此选择模型或宣称可部署增益。')
    save(fig, out/'updating_gaps')

    reg = public['controls']['specifications']['month_prior_history_P']
    shape = public['probability_shape']['all_months_equal_weight']
    fig, axes = plt.subplots(1, 2, figsize=(12, 6.4))
    xx = np.arange(2)
    for name, label, color, shift in [('truth', '真人', GREY, -.16), ('model', 'Simulation', GREEN, .16)]:
        axes[0].bar(xx+shift, [reg[name]['coefficients'][k] for k in ['prior', 'anchor_gap']], .3, color=color, label=label)
    axes[0].set_xticks(xx, ['本人上期预期', '更早常态相对上期的偏离']); axes[0].set_ylabel('自变量高1pp，本期预期高多少（pp）'); axes[0].set_xlabel('控制月份、历史及七类人口特征'); axes[0].legend(frameon=False)
    for name, label, color, shift in [('real', '真人', GREY, -.16), ('model', 'Simulation', GREEN, .16)]:
        axes[1].bar(np.arange(10)+shift, shape[name]['mean_probabilities_pct'], .3, color=color, label=label)
    axes[1].set_xticks(np.arange(10), ['>12','8–12','4–8','2–4','0–2','−2–0','−4–−2','−8–−4','−12–−8','<−12'], rotation=45, ha='right')
    axes[1].set_ylabel('平均分配概率（%）'); axes[1].set_xlabel('Q9通胀区间（%）'); axes[1].legend(frameon=False)
    for ax in axes: ax.grid(axis='y', alpha=.15); ax.set_axisbelow(True)
    fig.suptitle('个人历史的关联未充分保留；模型多填小概率，也少给极端档较大概率', y=.97)
    fig.subplots_adjust(left=.085, right=.98, top=.87, bottom=.25, wspace=.28)
    footer(fig, '左：2,284人月，两遍模型均值；描述性WLS，非因果更新权重，不直接用于加减预测。\n右：原始十档概率，模型逐遍后月等权；真人通缩全零者更多，但平均通缩概率反而较高，不能只看零值频率。')
    save(fig, out/'history_and_probability')


def report_html(public, out):
    dataset = json.dumps({'monthly': public['monthly'], 'groups': public['demographics'], 'labels': LABELS}, ensure_ascii=False).replace('<', '\\u003c')
    rows = ''.join(f"<tr><td>{r['month']//100}-{r['month']%100:02d}</td><td>{r['n']}</td><td>{r['truth']['q9_center_pp']:.2f}</td><td>{r['model']['q9_center_pp']:.2f}</td><td>{r['model']['q9_center_bias_pp']:+.2f}</td><td>{r['model']['q9_center_mae_pp']:.2f}</td><td>{r['copy']['q9_center_mae_pp']:.2f}</td></tr>" for r in public['monthly'])
    options = ''.join(f'<option value="{k}">{v}</option>' for k,v in DIMENSIONS.items())
    prefix = '../20261018_response_gap/'
    figs = [('monthly_gaps', '逐月水平与偏差：疫情、通胀上行、回落与较近时期都有覆盖。'),
            ('population_gaps', '按组比较总体中位数误差，以及组内人与人的差异。'),
            ('updating_gaps', '分开观察真人稳定、上调和下调时，模型做了什么。'),
            ('history_and_probability', '左为控制变量后的历史关联，右为原始十档概率；两者是不同诊断。')]
    img = {name: f'<figure><img loading="lazy" src="{prefix}figures/{name}.png" alt="{escape(caption)}"><figcaption>{escape(caption)}</figcaption></figure>' for name,caption in figs}
    section = f'''<section id="response-gap-diagnostic-20261018" class="rg-review" style="font-family:'Times New Roman','Kaiti SC','STKaiti',serif;max-width:1120px;margin:24px auto;padding:24px 28px 40px;border-bottom:1px solid #d7dfdc">
<style>.rg-review p,.rg-review li{{max-width:1020px}}.rg-review table{{font-size:15px;min-width:740px}}.rg-review select{{font:inherit;padding:6px 10px;margin:4px 12px 4px 0;max-width:100%}}.rg-review figcaption{{color:#596774;line-height:1.6}}.rg-note{{border-left:3px solid #366b5e;padding:8px 16px;background:#f3f6f4}}@media(max-width:700px){{.rg-review{{padding:18px 14px!important}}}}</style>
<h1>真人和模型究竟差在哪里？</h1>
<p>2026-10-18。复用12个月、每月192人的两遍回答；共同有效<strong>2,284个人月</strong>，没有新增API调用、没有重新拟合Q9。以下是<strong>回访者条件历史重建</strong>，不是全国预测或未看结果的盲测。</p>
<p class="rg-note"><strong>当前最值得研究的是：模型没有正确区分“该保持的人”和“该明显调整的人”。</strong>它把人与人的差异拉近，既可能让稳定者多改，也可能让真正大幅变化者少改。继续给所有人增加相同信息或统一加减预测，难以同时解决这两种情况。</p>
<nav><a href="{prefix}results.md">完整结论与后续任务</a> · <a href="{prefix}literature_mechanisms.md">文献及逐期背景</a> · <a href="{prefix}reply_audit.md">实际输入与回复审计</a> · <a href="../../current_todo.html">任务清单</a></nav>
<h2>一、逐期看：模型并非一直偏高或一直偏低</h2>
<p>十二期群体中位数MAE为<strong>模型0.459、照抄本人上期0.239pp</strong>。2020年两期、2021年9月、2025年3月偏低，2022年两期偏高。下面将同一批真人、模型及上期值对齐；不同时间的正负偏差不能相互抵消后当作准确。</p>
{img['monthly_gaps']}
<details><summary>展开十二个月的具体数字</summary><div class="table-scroll"><table><thead><tr><th>月份</th><th>有效人数</th><th>真人中位数</th><th>模型中位数</th><th>模型偏差</th><th>模型MAE</th><th>照抄MAE</th></tr></thead><tbody>{rows}</tbody></table></div><p>中心单位为%，误差为pp。模型两遍中心与两遍绝对误差分别平均，未先将回答混合再计算主指标。</p></details>
<h2>二、分组看：差距广泛存在，不能只给某类人加一个偏差</h2>
<p>高数理组中心MAE约<strong>0.322</strong>，低数理约<strong>1.241pp</strong>；大学组约<strong>0.388</strong>，高中及以下约<strong>1.246pp</strong>。但低数理组十二期平均带符号偏差仅+0.239pp，说明它并非每个月都统一低报或高报。组内真人的分布也更宽。</p>
{img['population_gaps']}
<p>可切换七类分组、展开任一组的逐月结果。n&lt;10只显示人数；ESS&lt;10标为弱支持。ESS表示权重不均衡后相当于多少名等权受访者。少月份的小组不能直接与完整十二期的小组排名。</p>
<label>人口维度 <select id="rg-dimension">{options}</select></label><label>组别 <select id="rg-level"></select></label><p id="rg-support"></p>
<div class="table-scroll"><table><thead><tr><th>月份</th><th>人数 / ESS</th><th>真人中心</th><th>模型中心</th><th>中心MAE<br>模型 / 照抄</th><th>分布W1<br>模型 / 照抄</th><th>人际IQR<br>真人 / 模型</th></tr></thead><tbody id="rg-group-body"></tbody></table></div>
<h2>三、更新看：真正稳定者改多，真正大幅调整者改少</h2>
<p>以真人相对上期变化不超过0.5pp为“稳定”，这组占加权样本约<strong>32%</strong>。其中模型约<strong>59%</strong>却移动到0.5pp之外，个人MAE约2.580pp。真人确实上调、下调的两组中，模型个人误差分别为3.995、3.731pp，小于照抄的4.368、4.567pp；但约19%的模型变化方向相反，平均调整幅度也偏小。</p>
{img['updating_gaps']}
<p><strong>重要限制：</strong>这些组用本期真人答案事后划分。稳定组照抄很准部分由定义决定，不能直接用来部署“稳定者照抄、其他人用模型”。下一步要检验的是：只凭当时已有资料，能否预先识别这种差别。0.25和1pp阈值下定位方向相同。</p>
<h2>四、控制其他特征后，个人历史仍是明确线索</h2>
<p>给真人与模型使用完全相同的回归：控制月份、上期预期、更早历史及七类人口特征。上期预期高1pp，本期真人平均高约<strong>0.744pp</strong>，模型只高约<strong>0.429pp</strong>；更早常态相对上期的偏离，关联为真人0.442、模型0.258。每次排除一个年份，保留不足的方向仍在。</p>
<p>这不是可以直接写入提示的更新系数。低数理标签也并非完全无反应：控制上述条件后，它对应的水平差异在模型中约+0.698pp、真人约+0.428pp。因此，粗组误差更大不等于“再强调低数理就会好”，首先需要处理个人原有位置的压缩。</p>
{img['history_and_probability']}
<h2>五、概率填法与信息理解，也有具体差距</h2>
<ul><li><strong>模型倾向到处填一点。</strong>平均非零档数7.82，真人4.69；通缩全部填0者模型8.8%、真人54.7%。但平均通缩概率反而是真人17.6%、模型10.6%——少数真人给了很大的通缩概率。不能把“更常填一点通缩”说成“整体更悲观”。</li>
<li><strong>人与人更像，不等于每个人都更确信。</strong>人际IQR模型2.424、真人5.055pp；个人拟合概率密度的平均IQR为模型4.474、真人5.762pp。原始概率的非零档数、个人不确定性、人际分歧分别报告。</li>
<li><strong>Q8也存在压缩，不能只归咎于Q9拟合。</strong>在另有有效上期/本期Q8的2,277个人月中，Q8人际IQR为真人7.275、模型1.650pp；模型/照抄的中心MAE为0.971/0.283pp。这是独立的Q8子样本检查，不与Q9指标混算。</li>
<li><strong>实际问卷时距基本对齐。</strong>同比、当月环比、未来12个月和上期回答均有说明，未发现把环比乘错或错用预测月的明确算式证据。模型接收6条序列各12个月、8篇新闻、3条政策摘要和39条发布时间标签；先验不是没有给。</li>
<li><strong>发现局部可疑复述。</strong>2023年12月有38条理由使用食品价格下降的说法，而最新食品同比和当月涨幅均为正。可能混淆“涨得慢了”和“价格下降”；理由未注明时距，尚不能据此解释全部预测偏差。完整规则与分母见回复审计。</li></ul>
<h2>六、接下来做什么，何时扩样？</h2>
<ol><li><strong>先估计真人的保持与更新规律。</strong>从已有连续SCE历史中检查原始十档完全不变、近零变化及明显变化，检验本人既往变化/答题方式是否能提前区分。短历史者采用有标记的群体回退。先与照抄、经验转移及已有线性组合做离线对照，不先让LLM再猜一次。</li>
<li><strong>把可疑信息理解做成小型检查。</strong>用同一事实分别明确表达“仍涨但涨得慢”和“价格下降”，保持题目及其他信息不变；若需真实调用，另冻结范围和预算。历史起点措辞、统一取整、线性加权等已做过的试验不重新包装。</li>
<li><strong>按证据扩样。</strong>常见群体当前每月有效权重约有数十人，足以发现这次明显差距；失业、残障等组不够。先补某个明确机制需要的小组，或在机制冻结后扩到未参与调整的月份，不在这十二期反复换seed追求好结果。</li></ol>
<p>随机信息实验中也有不少居民不改预期，为保持/更新并存提供依据，但不能直接照搬别的调查比例。<a href="https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr543.pdf">纽约联储原始实验</a>；<a href="{prefix}literature_mechanisms.md">其他理论与逐月历史边界</a>。所有原因目前都是有待区分的解释，尚未证明某一个就是唯一根源。</p>
<p><strong>统计口径：</strong>设计×调查权重、月份等权，两个生成重复不算新增真人；全部12期均已看过结果。控制变量回归描述条件关联，无因果或新盲测声明。本轮只新增诊断、图表和文档，旧配置与输出保持冻结。</p>
<script type="application/json" id="rg-data">{dataset}</script>
<script>(function(){{const d=JSON.parse(document.getElementById('rg-data').textContent),dim=document.getElementById('rg-dimension'),level=document.getElementById('rg-level'),body=document.getElementById('rg-group-body');const f=x=>Number.isFinite(x)?x.toFixed(2):'—';function render(){{const item=d.groups[dim.value][level.value];body.replaceChildren();document.getElementById('rg-support').textContent='本组共 '+item.all_months.n_person_months+' 个人月；可报告 '+item.all_months.n_months_reported+'/12 个月。';for(const r of item.monthly){{const tr=document.createElement('tr');let v=[String(r.month).slice(0,4)+'-'+String(r.month).slice(4),r.n+' / '+f(r.ess)+(r.ess<10?'（弱支持）':'')];if(r.suppressed)v.push('样本不足','—','—','—','—');else v.push(f(r.truth.q9_center_pp),f(r.model.q9_center_pp),f(r.model.q9_center_mae_pp)+' / '+f(r.copy.q9_center_mae_pp),f(r.model.cross_section_w1_pp)+' / '+f(r.copy.cross_section_w1_pp),f(r.truth.cross_person_iqr_pp)+' / '+f(r.model.cross_person_iqr_pp));for(const text of v){{const td=document.createElement('td');td.textContent=text;tr.appendChild(td)}}body.appendChild(tr)}}}}function populate(){{level.replaceChildren();for(const [key,item]of Object.entries(d.groups[dim.value])){{if(!item.all_months.n_person_months)continue;const option=document.createElement('option');option.value=key;option.textContent=d.labels[key]||key;level.appendChild(option)}}render()}}dim.addEventListener('change',populate);level.addEventListener('change',render);populate()}})();</script>
</section>'''
    (out/'reading_section.html').write_text(section+'\n')


def run(diagnostic, control_folder, out):
    diagnostic, control_folder, out = map(Path, (diagnostic, control_folder, out))
    if out.exists():
        raise ValueError('Fresh report folder required')
    d = json.loads((diagnostic/'summary.json').read_text())
    controls = json.loads((control_folder/'summary.json').read_text())
    details = json.loads((diagnostic/'update_details.json').read_text())
    public = build_public(d, controls, details)
    out.mkdir(parents=True)
    (out/'analysis_summary.json').write_text(json.dumps(public, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    figures(public, out/'figures')
    report_html(public, out)
    receipt = {'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'new_api_calls': 0,
               'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in
                                 (diagnostic/'summary.json', diagnostic/'update_details.json', control_folder/'summary.json')},
               'generated_sha256': {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()},
               'module_sha256': sha(__file__)}
    (out/'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    print(out)
