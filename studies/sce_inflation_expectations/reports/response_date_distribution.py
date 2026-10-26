"""Date distribution figures and the B cutoff engineering readout."""
import argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from ..experiments.full_a_core_normal import ROOT,read,write,sha,checked
from ..evaluation.response_date_distribution import METHODS,LABELS,days


def build(source,out):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'docs/workstreams'):raise ValueError('Fresh workstream report required')
    m=read(source/'manifest.json');checked(source,m['files_sha256']);checked(ROOT,m['source_sha256'])
    s=read(source/'summary.json');out.mkdir(parents=True)
    months=[m for m in s['metadata'] if '201901'<=m<='202510'];meta=s['metadata'];hist=s['monthly_probabilities']['counts']
    a=s['aggregate']['counts'];wa=s['aggregate']['survey_weighted'];rows=s['monthly_comparisons']
    early=np.mean([meta[m]['day1_10_share'] for m in months])*100
    mid=np.mean([meta[m]['day11_20_share'] for m in months])*100
    late=np.mean([meta[m]['day21_end_share'] for m in months])*100
    uniform_mid=np.mean([10/meta[m]['days'] for m in months])*100
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti','Arial Unicode MS'],
                         'font.size':11,'axes.unicode_minus':False})
    fig,axes=plt.subplots(2,1,figsize=(10,7),constrained_layout=True)
    for ax,n in zip(axes,[30,31]):
        mm=[m for m in months if meta[m]['days']==n];p=np.mean([hist[m] for m in mm],axis=0)
        ax.plot(np.arange(1,n+1),100*p,'-o',color='#1764AB',markersize=3,label='真人：各月归一化后等权平均')
        ax.axhline(100/n,color='#C75B12',ls='--',label=f'均匀抽样：每天{100/n:.2f}%')
        ax.set(xticks=range(1,n+1,2),xlabel='完成问卷的日号',ylabel='当日人数比例（%）',ylim=(0,9.2),
               title=f'{n}天月份：{len(mm)}个月，未把不同月长硬拼在一起')
        ax.legend(frameon=False,fontsize=9,loc='upper left');ax.grid(axis='y',alpha=.15)
    fig.savefig(out/'daily_distribution.png',dpi=160);plt.close(fig)

    fig,ax=plt.subplots(figsize=(10,4),constrained_layout=True);x=np.arange(4)
    vals=[a[k]['w1_days'] for k in METHODS]
    bars=ax.barh(x,vals,color=['#777777','#1764AB','#C75B12','#1764AB'],height=.6)
    ax.bar_label(bars,labels=[f'{v:.3f} 天' for v in vals],padding=5)
    ax.axvline(s['mean_512_sampling_w1_days'],color='#333333',ls=':',label='512次独立日期抽样的条件噪声参照')
    ax.set(yticks=x,yticklabels=[LABELS[k] for k in METHODS],xlabel='预测日期分布与真人分布的W1（天；越低越好）',
           xlim=(0,max(vals)*1.25),title='82个月历史检验：均匀抽样比经验分布偏离更大')
    ax.invert_yaxis();ax.legend(frameon=False,fontsize=9,loc='lower right');ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    fig.savefig(out/'sampler_comparison.png',dpi=160);plt.close(fig)

    chosen=[201911,202106,202510]
    rr=[next(r for r in rows if r['month']==m and r['weighting']=='counts' and r['method']=='uniform') for m in chosen]
    fig,ax=plt.subplots(figsize=(10,3.7),constrained_layout=True);x=np.arange(3)
    for delta,key,label,color in [(-.18,'observed_share_after_release','真人实际日期','#1764AB'),(.18,'predicted_share_after_release','均匀日期假设','#C75B12')]:
        v=[100*r[key] for r in rr];b=ax.bar(x+delta,v,width=.34,label=label,color=color);ax.bar_label(b,labels=[f'{v:.1f}%' for v in v],padding=3)
    ax.set(xticks=x,xticklabels=[f'{str(r["month"])[:4]}-{str(r["month"])[4:]}\nCPI发布日：{r["cpi_release_day"]}日' for r in rr],
           ylabel='在发布日之后完成问卷的比例（%）',ylim=(0,100),title='日期差异会改变“有机会看到新CPI”的人群比例')
    ax.legend(frameon=False);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    fig.savefig(out/'cpi_exposure.png',dpi=160);plt.close(fig)
    table=''.join(f'<tr><th>{LABELS[k]}</th><td>{a[k]["w1_days"]:.3f}</td><td>{a[k]["maximum_cdf_gap"]*100:.2f}</td><td>{a[k]["mean_absolute_CPI_exposure_error_pp"]:.2f}</td><td>{wa[k]["w1_days"]:.3f}</td></tr>' for k in METHODS)
    inv=s['B_engineering'];inventory=''.join(f'<tr><td>{r["month"][:4]}-{r["month"][4:]}</td><td>{r["target_archive_observed_day_count"]}／{days(r["month"])}</td><td>{r["target_archive_last_day"]}日</td><td>{r["late_missing_basic_topic_labels"]}</td></tr>' for r in inv['monthly'])
    text=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>真人作答日期、均匀抽样与B改造</title>
<style>body{{margin:0;background:#faf9f5;color:#242424;font:18px/1.8 "Times New Roman","Kaiti SC","STKaiti",serif}}main{{max-width:1100px;margin:auto;padding:30px 24px}}h1{{font-size:29px;line-height:1.4}}h2{{font-size:23px;margin-top:32px}}p{{text-indent:2em}}.lead{{text-indent:0;font-size:20px;border-left:4px solid #1764AB;background:#edf2f6;padding:15px 20px}}img{{width:100%;height:auto}}small,figcaption{{color:#555;font-size:15px}}table{{width:100%;border-collapse:collapse;background:white;font-size:16px}}th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:right}}th:first-child,td:first-child{{text-align:left}}.scroll{{overflow:auto}}a{{color:#1764AB}}</style>
<main><small>SCE · B配置审阅补充 · 日期元数据分析 · 2026-10-26 · 0 API</small>
<h1>真人日期并非均匀，经验分布能改善日期匹配；B的主要工作在环境接线</h1>
<p class="lead">2019-01—2025-10共82个月、98,340份合法月内日期显示明显月中集中。均匀分布的日期偏移平均1.475天，前一年同月0.939天，最近6个可得月份0.884天。经验分布不会增加LLM请求数。改B不必重写引擎，但必须同步重建个人可见环境；另发现2026-01新闻档只到1月7日，需要先核实补齐。</p>
<h2>1．真人到底在什么时候作答？</h2>
<p>只投影现有数据中的调查月、完成日期和权重，不使用通胀答案。82个月共98,382份记录，日期缺失0份；42份完成日期落在标称月之外，单列排除、不挪回原月。主图按人数统计；有效月内日期另有30份权重缺失，调查加权敏感性中排除并登记。</p>
<p>各月等权平均，1—10日占{early:.1f}%，11—20日占{mid:.1f}%，21日至月底占{late:.1f}%；均匀分布对应的月中占比仅{uniform_mid:.1f}%。12日及19—21日前后出现较明显峰值，但不同月份峰的位置和大小会变，不应只套一个固定“三峰模板”。</p>
<p>这与<a href="https://www.newyorkfed.org/medialibrary/media/research/epr/2017/epr_2017_survey-consumer-expectations_armantier.pdf">纽约联储2017年方法说明3.2节</a>一致：调查分批邀请并发提醒，日期不是全月均匀。该说明解释机制；当前具体比例来自本地2019—2025数据，不把2017日程当成所有年份不变的规则。</p>
<figure><img src="daily_distribution.png" alt="30天和31天月份的实际每日作答占比与均匀分布"><figcaption>每月先归一化，再跨月等权，避免大样本月份自动占更高比重。30天与31天月份分别展示，2月不进入这两幅图，但仍进入全部82月指标。日期没有可靠小时信息。</figcaption></figure>
<h2>2．能否用连续均匀抽样替代？</h2>
<p>按日构造环境时，连续均匀时间取整成日期，等价于每个日号概率1／月长。本次比较的不是数学上能不能抽，而是这种简化会丢失多少信息。均匀方案与实际日期分布的平均最大CDF差为{a['uniform']['maximum_cdf_gap']*100:.1f}个百分点，日期W1为{a['uniform']['w1_days']:.3f}天；并非几乎相同。</p>
<p>日期W1表示把一个日期分布移动到另一个日期分布的最小平均天数，不是通胀预期W1的百分点。512人从真实经验分布独立抽日期的条件模拟噪声约{s['mean_512_sampling_w1_days']:.3f}天，均匀偏离更大；这只给数量尺度，不是考虑面板相关性的总体置信区间。</p>
<figure><img src="sampler_comparison.png" alt="四种日期分布预测方法的历史日期W1与512人抽样噪声参照"><figcaption>历史目标82个月。各目标月只能使用按九个月公开滞后假设已可得的更早月份，没有使用目标月日期来拟合抽样器，也未按SCE误差选参数。</figcaption></figure>
<div class="scroll"><table><tr><th>日期方案</th><th>日期W1（天）</th><th>最大CDF差（百分点）</th><th>CPI可见比例平均绝对误差（百分点）</th><th>调查加权日期W1（天）</th></tr>{table}</table></div>
<p>前一年同月比均匀更接近真人；本次四种候选中，最近6个可得月份的等权混合在平均日期W1上更好。过去最多3年同月也作了比较，并未优于近期混合。它们的CPI可见比例误差改善较小，不能把日期分布改善等同于SCE的MAE已经下降。</p>
<figure><img src="cpi_exposure.png" alt="三个月份实际与均匀作答日期下有机会接触当月CPI发布的人群比例"><figcaption>只计发布日之后的完成日期，与项目前一日截止约定一致；不推断当天上午或下午是否看到发布。2019-11为差距较大的示例，2021-06为既有重点，2025-10有延迟发布特殊背景，均非代表所有月份。能看到不等于实际关注或吸收。</figcaption></figure>
<p>因此，均匀方案可以保留为简化对照，但目前没有“二者几乎等价”的证据。若要随机日期，优先考虑历史经验分布；抽取一组31个以内的日期概率与均匀抽取，工程差别很小。真正费工的是后面的环境筛选，而不是这几个概率。</p>
<h2>3．怎样用历史日期，不引入未来信息？</h2>
<p>两种简单可行的候选是：使用前一年同月的日期分布；或使用截止前最新可得6个月的混合分布。本次后一方案以各来源月等权，并按月长把日概率区间映射到目标日，概率守恒；没有额外拟合工作日、节假日或人口条件。它能平滑偶然尖峰，但不保证精确恢复目标月的邀请安排。</p>
<p>例如2025-11的原截止下，最新可得源波次按既定规则推定为2025-01，最近6个源月为2024-08—2025-01；前一年同月为2024-11。不能因为现在下载到了2025-10日期，就给2025-11提前使用这些尚未按规则公开的日期。11期四种候选概率已离线保存，仅供审阅，尚未分配到运行代理或改变提示。</p>
<h2>4．B需要改多少工程？</h2>
<p><strong>改动属于输入层的中等适配，不必重写模型引擎。</strong>现有A已实现个人日期、逐日价格／政策／新闻快照、截止检查和提示重渲染；B可复用，但要保留其旧人口、合成先验与全局预测边界，不能直接把A当前真实人口搬过来。</p>
<p>第一步，给512户分配有固定种子的合成日期，并单独保存来源月份、抽样概率和全局D。第二步，按个人日期生成可见新闻、最新价格、政策与信心，再更新提示的日期和先后标签；按“月份×截止日”缓存，不重复读档。第三步，校验合成先验参考日期、四档新闻数量、实际发布时间、SCE泄漏过滤与原权重守恒。最后另冻新提示、来源哈希、预算和执行包，复用原容错及评价。</p>
<p>若保留当前月中D，个人截止为min(合成作答日前一天,D)，11期最多约148种日快照；抽到D之后的人不能读未来新闻。若改为整月受访、月底即时回测，最多334个日期快照，并重新核查全局人口来源资格、历史锚、宏观基线与后处理口径。两种方案都仍是每户一次回答，不会乘以30；若两套都跑，则是两个不同实验组。</p>
<h2>5．本次查到的具体资料缺口</h2>
<p><strong>2026-01原始新闻档只有694篇，日期为1月1—7日。</strong>元数据记录抓取于2026-10-07；本地没有找到其他同月NYT档。1月8—13日连原共同截止也未覆盖，1月8—31日更不能视为全月已齐。它是来源完整性问题，不是模型拒绝吸收信息；需要重新核实取得完整档案，并按新文件另留版本，不能覆盖旧运行证据。</p>
<p>现有本地文件可见范围内，扩到月底另有297篇新闻缺基础主题标签，全部落在2026-09后半月。这个数字<strong>不包含</strong>补齐2026-01后可能新增的缺标签。个人警示倍数仍为1时，不必因此重标所有警示标签。当前仅查库存，没有下载、打标或调用Simulation。</p>
<details><summary>查看11个月新闻档与基础标签库存</summary><table><tr><th>目标月</th><th>目标月观测日期数／月长</th><th>档案最后日</th><th>原截止之后缺主题标签</th></tr>{inventory}</table><p>“有记录到月底”仅说明文件日期覆盖，不证明历史字节版本完整或无文章遗漏，也不替代严格事前可得性核验。</p></details>
<p>在完整档案核实后，可以先离线生成一种随机日期候选，核对几个代表日期的实际可见内容，再给新范围与Terminal命令。尚不能在没有重跑的情况下承诺SCE误差会下降。本轮不改变B截止、原始A/B或已固定统计参数。</p>
<p><a href="../README.md">方法、复算与工程任务</a> · <a href="../../20261025_recent_b/refresh_review_20261026/index.html">原B配置审阅</a></p>
<small>来源：{source.relative_to(ROOT)}。只使用日期／权重元数据及公开新闻库存；0新API，0Q9密度拟合，当前输入包未改。</small></main></html>'''
    (out/'index.html').write_text(text)
    write(out/'manifest.json',dict(source_manifest_sha256=sha(source/'manifest.json'),renderer_sha256=sha(Path(__file__)),
       files_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print(out/'index.html')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();build(a.source,a.out)


if __name__=='__main__':main()
