#!/usr/bin/env python3
"""Publish a compact later-2025 result from the canonical cached readout."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
COLORS={'human':'#25282c','deepseek_v32':'#d56a00','carry':'#783caf'}
LABELS={'human':'真人本期','deepseek_v32':'DeepSeek V3.2','carry':'照抄本人上期'}


def publish(source,dest):
    source,dest=Path(source).resolve(),Path(dest).resolve()
    if dest.exists():raise ValueError('Fresh public report folder required')
    s=json.loads((source/'summary.json').read_text())
    if s['status']!='completed_new2025_design_weighted_readout':raise ValueError('Canonical completed readout required')
    r=s['readout'];metrics=r['metrics'];arm='deepseek_v32';months=s['months'];disp=s['dispersion']
    q8=s['q8_design_weighted'][arm]['aggregate_equal_month_repeat_cells']
    monthly={m:{a:{k:float(np.mean([c['arms'][a][k] for c in r['cells'] if c['month']==m]))
                for k in ('truth_center_pp','predicted_center_pp','center_mae_pp','w1_pp','across_person_iqr_pp')}
                for a in (arm,'carry')} for m in months}
    font=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti'],'font.size':11,
        'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False})
    dest.mkdir(parents=True);(dest/'figures').mkdir()
    x=np.arange(len(months));ticks=[f'{m//100}-{m%100:02}' for m in months]
    fig,axes=plt.subplots(1,2,figsize=(13,4.5))
    axes[0].plot(x,[monthly[m][arm]['truth_center_pp'] for m in months],'o-',color=COLORS['human'],label=LABELS['human'],linewidth=2.3)
    for a,marker in [(arm,'^'),('carry','s')]:
        axes[0].plot(x,[monthly[m][a]['predicted_center_pp'] for m in months],marker+'--',color=COLORS[a],label=LABELS[a],linewidth=2)
    axes[0].set_title('每月同一批家庭的群体中位数');axes[0].set_ylabel('未来12个月通胀预期（%）')
    for j,a in enumerate((arm,'carry')):
        bars=axes[1].bar(x+(j-.5)*.32,[monthly[m][a]['w1_pp'] for m in months],.3,color=COLORS[a],label=LABELS[a])
        axes[1].bar_label(bars,fmt='%.2f',padding=3,fontsize=9)
    axes[1].set_title('跨人分布距离W1');axes[1].set_ylabel('百分点（越低越接近真人）');axes[1].margins(y=.18)
    for ax in axes:ax.set_xticks(x,ticks);ax.legend(fontsize=9);ax.grid(axis='y',alpha=.15)
    fig.tight_layout();fig.savefig(dest/'figures/monthly.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,4.5))
    for j,a in enumerate(('human',arm,'carry')):
        vals=[c['metrics'][a]['variance_pp2'] for c in disp['monthly']]
        axes[0].bar(x+(j-1)*.23,vals,.22,label=LABELS[a],color=COLORS[a])
    axes[0].set_xticks(x,ticks);axes[0].set_title('人际方差：不是同一人的重复波动');axes[0].set_ylabel('百分点平方');axes[0].legend(fontsize=9)
    order=['below_2','2_to_below_4','4_to_below_8','8_or_above']
    groups=s['prior_groups'];bands=[b for b in order if groups[b]['unique_persons']>=8]
    gx=np.arange(len(bands));gnames=dict(zip(order,['上期<2%','上期2—4%','上期4—8%','上期≥8%']))
    if bands:
        axes[1].plot(gx,[groups[b]['metrics'][arm]['truth_mean_pp'] for b in bands],'o-',color=COLORS['human'],label=LABELS['human'],linewidth=2.3)
        for a,marker in [(arm,'^'),('carry','s')]:
            axes[1].plot(gx,[groups[b]['metrics'][a]['model_mean_pp'] for b in bands],marker+'--',color=COLORS[a],label=LABELS[a],linewidth=2)
        axes[1].set_xticks(gx,[gnames[b] for b in bands]);axes[1].legend(fontsize=9)
    axes[1].set_title('不同旧信念人群：本期预期水平');axes[1].set_ylabel('各组个人预期均值（%）')
    for ax in axes:ax.grid(axis='y',alpha=.15)
    fig.tight_layout();fig.savefig(dest/'figures/dispersion.png',dpi=170);plt.close(fig)
    ma,base=metrics[arm],metrics['carry'];dm=disp['equal_month_metrics'];noise=disp['repeat_equal_month_means'][arm]
    fee=s['runtime'];n=s['national_comparison']
    rowhtml=''.join(f'<tr><td>{m//100}-{m%100:02}</td><td>{monthly[m][arm]["center_mae_pp"]:.3f}</td><td>{monthly[m]["carry"]["center_mae_pp"]:.3f}</td><td>{monthly[m][arm]["w1_pp"]:.3f}</td><td>{monthly[m]["carry"]["w1_pp"]:.3f}</td></tr>' for m in months)
    grouphtml=''.join(f'<tr><td>{gnames[b]}</td><td>{groups[b]["person_months"]}</td><td>{groups[b]["unique_persons"]}</td><td>{len(groups[b]["sparse_cells"])}</td></tr>' for b in order)
    better_center=ma['center_mae_pp']<base['center_mae_pp'];better_dist=ma['w1_pp']<base['w1_pp']
    verdict=f'本轮中位数MAE{("低于" if better_center else "未低于")}照抄上期；跨人W1{("也更低" if better_dist else "仍未优于照抄")}。'
    sparse=sum(len(groups[b]['sparse_cells']) for b in order)
    sensitivity_html=''
    if s.get('support_sensitivity'):
        z=s['support_sensitivity'];fixed=z['fixed_human_valid_roster_with_scalar_prior_fallback'];fm=fixed['metrics']
        rep=z['per_repeat_own_valid_support'];verdict='共同有效样本上中位数更接近真人，但胜过照抄的优势对缺失和生成遍数敏感；跨人分布仍落后。'
        sensitivity_html=f'''<h2>3. “胜过照抄”是否稳健？</h2>
<p class="callout">需要保留：网络失败和计分失败改变了共同样本，照抄基线的MAE也从原定人群的0.114变为共同样本的0.230pp。中位数是排序统计量，少量记录的缺失也可能移动其位置。因此不能把顶部的改善直接当成稳定优势。</p>
<p>分别评价每一遍及其有效人群：第一遍模型MAE {rep['1']['metrics'][arm]['center_mae_pp']:.3f}、照抄 {rep['1']['metrics']['carry']['center_mae_pp']:.3f}pp；第二遍模型 {rep['2']['metrics'][arm]['center_mae_pp']:.3f}、照抄 {rep['2']['metrics']['carry']['center_mae_pp']:.3f}pp。两遍的优劣排序不同，且支持人群也不同。</p>
<p>另作零API的事后工程诊断：保留全部{fixed['person_months']}个真人可计分个人月，仅在{z['fallback_slots']}个无有效模型分数的槽上，用本人上期均值作标量后备。得到模型加后备的MAE <strong>{fm[arm]['center_mae_pp']:.3f}</strong>、纯照抄 <strong>{fm['carry']['center_mae_pp']:.3f}pp</strong>，优势仅{fm['carry']['center_mae_pp']-fm[arm]['center_mae_pp']:.3f}pp；RMSE则为<strong>{fm[arm]['center_rmse_pp']:.3f}对{fm['carry']['center_rmse_pp']:.3f}pp</strong>，模型较差。该人群W1为{fm[arm]['w1_pp']:.3f}对{fm['carry']['w1_pp']:.3f}pp。</p>
<p class="note">这是缺失处理敏感性，不是新模型回答或新主成绩：原始回复和主分析不改，不伪造十档概率，也没有新增调用。说明总体中心有信号，但尚不足以宣布稳定胜过基线。</p>'''
    public={k:s[k] for k in ('status','months','n_per_month','person_months','unique_persons','readout','prior_groups',
        'q8_design_weighted','baseline_comparison','national_comparison','dispersion','coverage','scorable_counts',
        'q9_postprocessing','runtime','configuration','limits','leave_one_month_out','correction_note','quarantined_v1_fields',
        'accuracy_descriptive_only')}
    if s.get('support_sensitivity'):public['support_sensitivity']=s['support_sensitivity']
    (dest/'summary.json').write_text(json.dumps(public,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V3.2：2025新增四个月验证</title>
<style>body{{font-family:"Times New Roman","Kaiti SC","STKaiti","KaiTi",serif;background:#faf9f6;color:#25282c;margin:0;line-height:1.75}}main{{max-width:1120px;margin:auto;padding:30px 24px}}h1{{font-size:29px}}h2{{font-size:23px;margin-top:30px}}img{{width:100%;height:auto}}a{{color:#783caf}}.note{{color:#625e58}}.callout{{border-left:4px solid #d56a00;padding:12px 18px;background:#f3eee4}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}.card{{background:white;border:1px solid #dedbd3;border-radius:10px;padding:15px}}.value{{font-size:29px;display:block}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}th,td{{border-bottom:1px solid #d9d7d0;padding:10px;text-align:right}}th:first-child,td:first-child{{text-align:left}}.scroll{{overflow-x:auto}}@media(max-width:700px){{.cards{{grid-template-columns:1fr}}main{{padding:20px 14px}}}}@media print{{.card,figure{{break-inside:avoid}}}}</style><main>
<p><a href="../v32_results/index.html">原四期同输入模型比较</a> · <a href="../v32_variance_check/index.html">旧轨迹方差检查</a></p><h1>V3.2：2025新增四个月验证</h1>
<p class="callout"><strong>{verdict}</strong>这是新月份的条件重建结果，不能据此证明模型没有接触过相关历史信息。完整逐月结果均保留。</p>
<p>2025年4、6、8、10月，每月192名回访者，每人生成两遍。共同可计分{s['person_months']}个人月、{s['unique_persons']}名不同受访者；重复生成不增加真人样本量。温度0.5，OpenRouter → 固定SiliconFlow FP8的DeepSeek V3.2。</p>
<p class="note">接口错误{s['coverage'][arm].get('error',0)}份；输出格式无效{s['coverage'][arm].get('invalid',0)}份；模型Q9连续密度可计分{s['scorable_counts'][arm]}份。{('未满足既有最终覆盖检查，以下仅为有效支持上的描述结果。' if s['accuracy_descriptive_only'] else '已满足既有最终覆盖检查；失败仍保留并从共同支持中排除。')}</p>
<div class="cards"><div class="card">同人群中位数MAE<span class="value">{ma['center_mae_pp']:.3f} pp</span>照抄本人上期 {base['center_mae_pp']:.3f} pp<br>模型RMSE {ma['center_rmse_pp']:.3f} pp</div><div class="card">跨人分布距离W1<span class="value">{ma['w1_pp']:.3f} pp</span>照抄本人上期 {base['w1_pp']:.3f} pp<br>越低越接近真人</div><div class="card">跨人四分位距IQR<span class="value">{ma['across_person_iqr_pp']:.3f} pp</span>真人 {ma['truth_across_person_iqr_pp']:.3f} pp<br>仍需结合尾部与方差判断</div></div>
<h2>1. 各月总体水平与分布</h2><img src="figures/monthly.png" alt="四个月真人、模型与上期基线的中心和分布距离">
<div class="scroll"><table><thead><tr><th>月份</th><th>模型中心MAE</th><th>照抄中心MAE</th><th>模型W1</th><th>照抄W1</th></tr></thead><tbody>{rowhtml}</tbody></table></div>
<p class="note">单位pp。每人Q9十档拟合连续密度并取均值，再计算跨人的设计加权中位数；逐月逐遍先算误差，再等权平均。折线把两遍中位数平均，仅供展示。Q8另报，其中心MAE为{q8['q8_center_mae_pp']:.3f}pp，不与Q9混算。</p>
<h2>2. 人际差异与旧信念人群</h2><img src="figures/dispersion.png" alt="每月人际方差和不同上期信念群体的本期预期">
<p>跨人方差：模型<strong>{dm[arm]['variance_pp2']:.2f}</strong>、真人<strong>{dm['human']['variance_pp2']:.2f}</strong> pp²。同一个人两遍回答的平均绝对差为<strong>{noise['mean_absolute_repeat_gap_pp']:.3f}pp</strong>，这与不同人之间的差异是两件事。</p>
<p>距官方全国中位数±0.5pp内：模型{100*disp['official_center_concentration_equal_month_means'][arm]:.1f}%、真人{100*disp['official_center_concentration_equal_month_means']['human']:.1f}%。集中或分散都不能单独证明记忆真值。先验组采用既有固定边界，不按本轮结果调整。</p>
<details><summary>分组支持与稀疏格</summary><div class="scroll"><table><thead><tr><th>上期预期组</th><th>个人月</th><th>不同受访者</th><th>稀疏月×遍数格</th></tr></thead><tbody>{grouphtml}</tbody></table></div><p class="note">沿用既有提示：每格少于8人、ESS低于5或最大权重超过25%为稀疏。合计{sparse}格，分组只作描述，不作因果解释；同一受访者可跨月出现。</p></details>
{sensitivity_html}<h2>4. 官方全国指标单独比较</h2><p>本轮模拟样本的中位数对官方全国值，MAE为<strong>{n['model_national_mae_pp']:.3f}pp</strong>；全国上月值照抄MAE为<strong>{n['official_national_copy_mae_pp']:.3f}pp</strong>。对全波次、同一项目计分器重算的中心，模型MAE为{n['model_full_wave_mae_pp']:.3f}pp。</p>
<p class="note">这些不是顶部的同人群评分。模型只覆盖合格回访者；完整全国调查还包含新入组者，官方计分与项目冻结近似也有差别，不能把差异全归因于模型。</p>
<h2>5. 本轮保留了哪些配置</h2><p>沿用食品采购角色匹配、食品分类价格视图、3条共同新闻＋5条个人新闻、合成CE支出与美联储信心、本人真实上期Q8/Q9及更早摘要。直接填写本期Q8/Q9，附无数值结构示例。本轮没有加入新心理或频率提示，也没有按本轮结果拟合组合权重。</p>
<p>四个月截止分别为4月10日、6月11日、8月12日、10月24日纽约时间当天结束。10月的9月CPI已经发布，但9月就业尚未发布，因此使用已发布的8月就业；4月的信心分配使用当时已公开的2024年Gallup波次。</p>
<h2>6. 对训练数据担忧的含义</h2><p>AWS同名V3.2服务模型卡列知识截止为2025年3月；DeepSeek V3.2于2025年12月1日发布。两者不能证明本次托管权重的完整训练截止。按SCE微观资料约九个月后公开的规则推断，本轮目标微观回答应晚于模型发布才公开，但原始历史上传日期未逐份核验，而且全国聚合指标当时已经公开。故本轮是补充证据，仍不能称严格无污染预测。</p>
<p class="note">来源：<a href="https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-deepseek-deepseek-v3-2.html">AWS模型卡</a>、<a href="https://api-docs.deepseek.com/news/news251201/">DeepSeek发布说明</a>、<a href="https://www.newyorkfed.org/microeconomics/sce/sce-faq">纽约联储SCE FAQ</a>。后续模型发布后封存、结果尚未公开的预测可提供更强的时间边界。</p>
<h2>7. 调用、成本与复现</h2><p>实际请求{fee['new_calls']:,}次，API报告费用<strong>${fee['api_reported_new_cost_usd']:.4f}</strong>，包含未知失败的保守记账为${fee['combined_spent_or_reserved_usd']:.4f}，运行{fee['seconds']/60:.1f}分钟，硬上限$6。前16份以最多8并发通过格式检查，随后最多16并发，自动重试{fee['automatic_retries']}次；新闻分类用量估算$0.365931另计。22份网络失败与2份模型密度计分失败保留，没有补发；原始概率和归一化另记。</p>
<p class="note">原始提示/个人回答保存在私有outputs；本页仅呈现聚合。主统计使用设计权重，通用评价器的等权分支只作敏感性；v1派生全国字段的分支混用已隔离，本页从原计分缓存按正确权重重算，0新调用、0重新拟合Q9。<a href="summary.json">聚合结果与留一月检查</a>。</p>
<p class="note">旧四期与本轮月份和样本不同，不能将成绩差直接解释成模型变化。仅四个新月份，对时间外推仍有限；不自动升级全量主配置。生成于{datetime.now(timezone.utc).isoformat()}。</p></main></html>'''
    (dest/'index.html').write_text(page)
    return dict(report=str(dest/'index.html'),center_mae_pp=ma['center_mae_pp'],copy_mae_pp=base['center_mae_pp'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--dest',type=Path,required=True)
    a=p.parse_args();print(publish(a.source,a.dest))
