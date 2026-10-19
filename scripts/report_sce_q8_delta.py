"""Render the completed Q8-only pilot from cached evaluation; no API or refit."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('MPLCONFIGDIR', '/tmp/sce_q8_delta_mpl')
os.environ.setdefault('XDG_CACHE_HOME', '/tmp/sce_q8_delta_xdg')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import fontManager
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.metrics import quantile

WORK = ROOT/'docs/workstreams/20261019_advisor_followup'
READER = ROOT/'docs/workstreams/20261013_behavior/codex_expansion_diagnostic_20261014.html'
KEY = 'q8-only-delta-results-20261019'
LABELS = {'direct': '直接填写', 'q8_delta': '仅Q8填变化值', 'copy_previous': '照抄本人上期'}
COLORS = {'direct': '#8b969b', 'q8_delta': '#087f80', 'copy_previous': '#a77b3f'}


def read(path):
    return json.loads(path.read_text())


def main(source, trial):
    source, trial = source.resolve(), trial.resolve()
    s = read(source/'summary.json'); manifest = read(trial/'manifest.json')
    dest = WORK/'q8_delta_results_v1'
    if dest.exists() or f'id="{KEY}"' in READER.read_text():
        raise ValueError('Fresh result directory/reading section required')
    if s['status'] != 'completed_frozen_block_evaluation':
        raise ValueError('Completed frozen evaluation required')
    if (s['protocol'] != read(trial/'protocol.json')
            or manifest['protocol_sha256'] != read(WORK/'q8_delta_ready_v1/readiness.json')['protocol_sha256']):
        raise ValueError('This fixed-version readout requires the registered Q8 pilot protocol')
    q = s['q8_independent']; arms = s['protocol']['arms']; months = s['protocol']['months']
    q9 = {a: s['arms'][a]['auxiliary_survey_weighted']['q9']['aggregate_equal_month_repeat_cells'] for a in arms}
    calls = errors = retries = 0; starts = []; ends = []; models = set()
    for job in manifest['jobs']:
        audit = ROOT/'outputs/local_runs'/job['run_id']; receipt = read(audit/'run_manifest.json')
        calls += receipt['cost']['call_count']; starts.append(receipt['started_at_utc']); ends.append(receipt['finished_at_utc'])
        for line in (audit/'llm_calls.jsonl').read_text().splitlines():
            call = json.loads(line); errors += bool(call.get('error')); retries += call['attempt_idx'] > 0
            models.add(call['returned_model'])
    elapsed = (datetime.fromisoformat(max(ends))-datetime.fromisoformat(min(starts))).total_seconds()
    cases = read(source/'cases_private.json')
    # Only a scalar reference width leaves the private evaluation layer.
    human_iqr = []
    for month in months:
        c = [r for r in cases if r['month'] == month and r['repeat'] == 1]
        y = [r['real']['q8_point'] for r in c]
        human_iqr.append(quantile(y, np.ones(len(y)), .75)-quantile(y, np.ones(len(y)), .25))
    gates = {
        'q8_w1_upper95_below_zero': q['paired_person_intervals95']['w1_pp'][1] < 0,
        'q8_center_point_no_worse': q['equal_people']['q8_delta']['center_mae_pp'] <= q['equal_people']['direct']['center_mae_pp'],
        'q9_center_point_no_worse': q9['q8_delta']['q9_center_mae_pp'] <= q9['direct']['q9_center_mae_pp'],
        'q9_w1_point_no_worse': q9['q8_delta']['cross_section_w1_pp'] <= q9['direct']['cross_section_w1_pp'],
        'model_q8_q9_validity_at_least_99pct': min(s['q8_valid_fraction'].values()) >= .99 and all(
            s['coverage'][a].get('valid', 0)/(s['protocol']['planned_calls']/len(arms)) >= .99 for a in arms),
    }
    if bool(all(gates.values())) != s['candidate_continuation_passed']:
        raise ValueError('Readout must match frozen screening decision')
    dest.mkdir(); (dest/'figures').mkdir()
    receipt = {'real_api_calls': calls, 'api_errors': errors, 'retries': retries,
        'estimated_cost_usd': s['estimated_actual_cost_usd'], 'hard_cap_usd': s['protocol']['budget_cap_usd'],
        'api_elapsed_seconds': elapsed, 'evaluation_seconds': s['evaluation_seconds'],
        'returned_model_aliases': sorted(models), 'q8_real_equal_person_iqr_pp': float(np.mean(human_iqr)),
        'candidate_gate_checks': gates, 'protocol_sha256': manifest['protocol_sha256'],
        'source_evaluation': str(source.relative_to(ROOT)), 'source_trial': str(trial.relative_to(ROOT)),
        'source_summary_sha256': hashlib.sha256((source/'summary.json').read_bytes()).hexdigest(),
        'note': 'API cost is a usage-based ledger estimate, not the vendor invoice. No raw person records published.'}
    (dest/'summary.json').write_text(json.dumps(s, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    (dest/'run_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    font = ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists(): fontManager.addfont(font)
    plt.rcParams.update({'font.family': ['Times New Roman', 'Kaiti SC', 'STKaiti'], 'font.size': 12,
                         'axes.spines.top': False, 'axes.spines.right': False, 'axes.unicode_minus': False})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    specs = [('Q8：等人权重，96个人月', ['中心MAE', '个人MAE', '分布W1'],
              {a: [q['equal_people'][a][k] for k in ['center_mae_pp', 'personal_mae_pp', 'w1_pp']] for a in arms}),
             ('Q9：原调查权重敏感性，94个人月', ['中心MAE', '分布W1'],
              {**{a: [q9[a][k] for k in ['q9_center_mae_pp', 'cross_section_w1_pp']] for a in arms},
               'copy_previous': [q['q9_copy_previous_same_q9_support'][k] for k in ['center_mae_pp', 'w1_pp']]})]
    for ax, (title, ticks, values) in zip(axes, specs):
        x = np.arange(len(ticks)); width = .75/len(values)
        for i, (a, v) in enumerate(values.items()):
            bars = ax.bar(x+(i-(len(values)-1)/2)*width, v, width, label=LABELS[a], color=COLORS[a])
            ax.bar_label(bars, fmt='%.2f', fontsize=10, padding=3)
        ax.set_xticks(x, ticks); ax.set_ylabel('误差／距离（百分点；越小越好）'); ax.set_title(title); ax.legend(fontsize=9)
        ax.set_xlabel('评价指标'); ax.set_ylim(0, max(max(v) for v in values.values())*1.22)
    fig.suptitle('只改变Q8回答格式：Q8改善，Q9中心未同步改善', fontsize=15)
    fig.text(.02, .01, '来源：2020-04、2021-05/11、2022-03；24人/月、两遍生成。各月各遍先计分再平均，不将Q8与Q9视为同一指标。', fontsize=9)
    fig.tight_layout(rect=(0,.04,1,.93)); fig.savefig(dest/'figures/metrics.png', dpi=170); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for index, ax in enumerate(axes):
        values = {}
        for a in arms:
            cells = q['monthly_repeat_cells'] if index == 0 else s['arms'][a]['auxiliary_survey_weighted']['q9']['cells']
            values[a] = [float(np.mean([c['metrics'][a]['center_mae_pp'] if index == 0 else c['q9_center_mae_pp']
                                       for c in cells if c['month'] == m])) for m in months]
        x = np.arange(len(months))
        for i, (a, v) in enumerate(values.items()):
            ax.bar(x+(i-.5)*.34, v, .34, label=LABELS[a], color=COLORS[a])
        ax.set_xticks(x, [f'{str(m)[:4]}-{str(m)[4:]}' for m in months], rotation=20)
        ax.set_title('Q8中心误差（等人）' if index == 0 else 'Q9中心误差（调查加权敏感性）')
        ax.set_ylabel('中位数绝对误差（百分点）'); ax.set_xlabel('开发月份（非连续；每点平均两遍误差）'); ax.legend(fontsize=9)
    fig.text(.02,.01,'来源同上。两遍不是两批真人；只适用于本次固定开发月份，不能据此替换十二期主成绩。',fontsize=9)
    fig.tight_layout(rect=(0,.05,1,1)); fig.savefig(dest/'figures/monthly_center_errors.png', dpi=170); plt.close(fig)
    q8rows = ''.join(f'<tr><td>{name}</td><td>{q["equal_people"]["direct"][key]:.3f}</td><td>{q["equal_people"]["q8_delta"][key]:.3f}</td></tr>'
        for name, key in [('群体中位数MAE','center_mae_pp'),('逐人MAE','personal_mae_pp'),('跨人分布W1','w1_pp'),('跨人IQR（不是误差）','iqr_pp')])
    section = f'''<section id="{KEY}" style="font-family:'Times New Roman','Kaiti SC','STKaiti',serif;max-width:1120px;margin:24px auto;padding:24px 28px 36px;border-bottom:1px solid #d7dfdc;line-height:1.75">
<h1>Q8变化值对照：改善点预期分布，尚未改善主Q9中心</h1>
<p>2026-10-19。四个开发月×24人×两组×两遍，<strong>{calls}次调用全部合法，估算费用${receipt['estimated_cost_usd']:.3f}／上限$2</strong>；0接口错误、0重试。官方引擎调用约{elapsed/60:.1f}分钟，评价{s['evaluation_seconds']:.1f}秒；没有重复抓数据或重拟合真人Q9。</p>
<h2>实验只改变一件事</h2><p>对照直接填本期Q8；候选填“本期Q8−本人上期Q8”，程序再加回上期值。例：上期3%、变化−1个百分点，恢复本期2%。<strong>两组Q9始终直接填十档绝对概率</strong>，人口、环境、历史说明完全相同，不裁剪或归一化。1个人月缺上期Q8，两组都直接填本期值。DeepSeek官方Flash别名、温度0.5、关闭思考、最多1024输出token。</p>
<h2>Q8：分布改善比中心改善更明确</h2><div class="table-scroll"><table><thead><tr><th>指标（百分点）</th><th>直接填写</th><th>仅Q8填变化值</th></tr></thead><tbody>{q8rows}</tbody></table></div>
<p>真人Q8跨人IQR为{receipt['q8_real_equal_person_iqr_pp']:.3f}pp；模型恢复了一部分差异，仍未达到真人。Q8分布W1下降约{100*(1-q['equal_people']['q8_delta']['w1_pp']/q['equal_people']['direct']['w1_pp']):.1f}%。按人配对重抽样的W1差95%区间为[−2.346,−0.324]pp，四期固定条件下支持改善；中心误差差区间[−0.613,+0.337]跨0，中心优势还不稳定。两遍的W1均改善，但2021-11的W1反而上升。</p>
<p>照抄比较仅用95个确有上期Q8的人月：中心MAE为直接0.788、候选0.713、照抄0.900；个人MAE为4.850、3.901、3.415，W1为4.207、2.926、2.093。<strong>候选中心较好，但个人和分布仍未胜照抄。</strong>这组95人月不能与上表96人月直接混算。</p>
<figure><img src="../20261019_advisor_followup/q8_delta_results_v1/figures/metrics.png" alt="Q8和Q9分别比较误差和分布距离，权重与样本在图中标明"><figcaption>Q8等人主口径；Q9保留旧调查权重作保护指标。均按每月、每遍先计分后等权平均。</figcaption></figure>
<h2>Q9：中心略差，未过执行前筛选</h2><p>94个共同有效人月：Q9中位数MAE为<strong>1.012→1.037pp</strong>，W1为2.162→1.940pp，跨人IQR为2.575→2.833pp（真人5.681）。照抄上期的中心MAE为0.730、W1为1.784。2个人月真人Q9缺失，仅排出Q9评价，Q8仍保留。模型两组Q8/Q9均100%有效。</p>
<p>Q9中心差95%区间[−0.485,+0.277]、W1差区间[−0.417,+0.052]均跨0，不能称已证实伤害，也不能称保证无退步。预登记要求Q8 W1改善、Q8中心不差、Q9中心和W1均不差及合法率≥99%；<strong>本轮只未满足Q9中心点值不差这一条，所以不升级默认配置。</strong>不是事后新增门槛。</p>
<figure><img src="../20261019_advisor_followup/q8_delta_results_v1/figures/monthly_center_errors.png" alt="四个开发月份两组Q8和Q9中心误差"><figcaption>同一接口改动的效果随月份和题型变化，不能用总体均值掩盖2021-11及2022-03的差别。</figcaption></figure>
<h2>含义与下一步</h2><p>原有信念相同，换一种回答任务即可改变模型分布，说明不能把f(P,E)视为固定的人类推理方式。差值格式让上期答案成为明确计算起点，可能减弱把所有人拉向公共判断的倾向；这是与结果相容的解释，不是已证明真人心理过程。Q8与Q9联合生成，因此Q8格式也可能影响未改格式的Q9。</p>
<p>保留Q8差值作为有信号的开发候选；不重启Q9概率差值、不立刻扩样或反复调措辞。下一主任务仍为采购角色对应的可见价格及匹配／打乱输入预检，随机新闻量等候选另定独立时期。四个月均参与过开发、每月24人、两遍不是新增人、Flash别名不等于固定权重；本轮不是全国或B线预测成绩，十二期主MAE仍0.459／照抄0.239pp。</p>
<p><a href="../20261019_advisor_followup/q8_delta_results_20261019.md">完整结果与复算</a> · <a href="../20261019_advisor_followup/q8_delta_results_v1/summary.json">聚合评价</a> · <a href="../20261019_advisor_followup/q8_delta_results_v1/run_receipt.json">调用与费用收据</a> · <a href="../../current_todo.html">当前清单</a></p></section>'''
    (dest/'reading_section.html').write_text(section+'\n')
    page = READER.read_text(); READER.write_text(page.replace('</body>', section+'\n</body>'))
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True); parser.add_argument('--trial', type=Path, required=True)
    args = parser.parse_args(); main(args.source, args.trial)
