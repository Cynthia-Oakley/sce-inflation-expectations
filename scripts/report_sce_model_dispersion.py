#!/usr/bin/env python3
"""Publish cached dispersion diagnostics inside the existing research reports."""
import argparse
import html
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
LABELS={'human':'真人','qwen_cached':'Qwen 2.5-72B','deepseek_v32':'DeepSeek V3.2'}
COLORS={'human':'#25282c','qwen_cached':'#783caf','deepseek_v32':'#d56a00'}


def publish(source,dest,baselines=None):
    source,dest=Path(source).resolve(),Path(dest).resolve()
    if dest.exists():raise ValueError('Fresh public directory required')
    s=json.loads((source/'summary.json').read_text());rows=s['monthly'];metrics=s['equal_month_metrics'];noise=s['repeat_equal_month_means']
    font=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti'],'font.size':11,
        'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False})
    dest.mkdir(parents=True)
    x=np.arange(len(rows));names=['human','qwen_cached','deepseek_v32']
    fig,axes=plt.subplots(1,2,figsize=(13,4.6))
    for j,a in enumerate(names):
        axes[0].bar(x+(j-1)*.25,[r['metrics'][a]['variance_pp2'] for r in rows],.25,color=COLORS[a],label=LABELS[a])
        axes[1].plot(x,[100*(r['share_within_half_pp_of_official_center'][a] if 'share_within_half_pp_of_official_center' in r
                            else r['metrics'][a]['share_within_half_pp_of_human_center']) for r in rows],
                     ['o-','s--','^--'][j],color=COLORS[a],label=LABELS[a],linewidth=2)
    ticks=[f'{r["month"]//100}-{r["month"]%100:02}' for r in rows]
    for ax in axes:ax.set_xticks(x,ticks);ax.set_xlabel('调查月份（四个非连续开发月）');ax.legend(fontsize=9)
    axes[0].set_title('同一人群内，预测值的跨人方差');axes[0].set_ylabel('方差（通胀百分点平方）')
    concentration=s.get('official_center_concentration_equal_month_means')
    axes[1].set_title('接近官方全国中位数的回答占比' if concentration else '接近同批真人中位数的回答占比')
    axes[1].set_ylabel('落在±0.5个百分点内（%）');axes[1].set_ylim(bottom=0)
    fig.tight_layout();fig.savefig(dest/'dispersion.png',dpi=170);plt.close(fig)
    table=''.join('<tr><td>'+LABELS[a]+'</td>'+''.join(f'<td>{metrics[a][k]:.2f}</td>' for k in ('variance_pp2','std_pp','iqr_pp'))+
        f'<td>{100*metrics[a]["share_within_half_pp_of_human_center"]:.1f}%</td><td>{100*concentration[a]:.1f}%</td></tr>' if concentration else
        '<tr><td>'+LABELS[a]+'</td>'+''.join(f'<td>{metrics[a][k]:.2f}</td>' for k in ('variance_pp2','std_pp','iqr_pp'))+
        f'<td>{100*metrics[a]["share_within_half_pp_of_human_center"]:.1f}%</td></tr>' for a in names)
    repeat=''.join(f'<li>{LABELS[a]}：同一个人两遍回答平均相差 {noise[a]["mean_absolute_repeat_gap_pp"]:.3f}pp；'
                  f'人内生成方差 {noise[a]["within_person_generation_variance_pp2"]:.2f}pp²。</li>' for a in names if a in noise)
    baseline_html=''
    if baselines:
        b=json.loads(Path(baselines).read_text())
        public={k:b[k] for k in ('status','months','monthly','national_copy_errors','individual_copy_equal_month_metrics','limits')}
        (dest/'new2025_baselines.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n')
        b_rows=''.join(f'<tr><td>{r["month"]//100}-{r["month"]%100:02}</td><td>{r["selected_n"]}</td><td>{r["q9_valid_n"]}</td>'
            f'<td>{r["official_national"]["q9_headline_pp"]:.3f}</td><td>{r["official_national"]["copy_previous_headline_pp"]:.3f}</td>'
            f'<td>{r["official_national"]["center_mae_pp"]:.3f}</td></tr>' for r in b['monthly'])
        baseline_html=f'''<h2>新增2025月份：真值与基线已准备</h2><p>每月192人，合计768个人月（610名不同受访者），模型计划生成两遍。人口与上期信念先冻结，再单独提取本期真值；本期5份Q9不可计分记录不触发重新选人。当前没有新增模拟结果。</p>
<div class="scroll"><table><thead><tr><th>月份</th><th>预选人数</th><th>Q9可计分</th><th>官方Q9中位数 %</th><th>上月官方值 %</th><th>全国照抄绝对误差 pp</th></tr></thead><tbody>{b_rows}</tbody></table></div>
<p>四个月全国照抄MAE为<strong>{b['national_copy_errors']['mae_pp']:.3f}pp</strong>；同人群“照抄本人上期”的群体中位数MAE为<strong>{b['individual_copy_equal_month_metrics']['center_mae_pp']:.3f}pp</strong>。两种对象单独比较，不能混用。月份按时间覆盖预选，不因基线很强而改选。</p>
<p class="note">全国真值来自纽约联储最新下载chart.xlsx；同人真值使用项目冻结Q9计分器。均为评价资料，不进入本期模型提示。新闻2310篇/289批已完成，0API重试，用量估算$0.366（上限$1.50，非账单）；完整提示、干跑与模拟预算另行封存。<a href="new2025_baselines.json">基线聚合与口径</a>。</p>'''
    page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>V3.2回答方差与中位数集中检查</title><style>body{{font-family:"Times New Roman","Kaiti SC","STKaiti","KaiTi",serif;background:#faf9f6;color:#25282c;margin:0;line-height:1.75}}main{{max-width:1100px;margin:auto;padding:30px 24px}}h1{{font-size:29px}}h2{{font-size:22px;margin-top:30px}}img{{width:100%;height:auto}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}th,td{{border-bottom:1px solid #d9d7d0;padding:10px;text-align:right}}th:first-child,td:first-child{{text-align:left}}.note{{color:#625e58}}.callout{{border-left:4px solid #d56a00;padding:10px 18px;background:#f3eee4}}a{{color:#783caf}}.scroll{{overflow:auto}}</style><main>
<p><a href="../v32_results/index.html">返回原V3.2比较</a></p><h1>V3.2的回答是否集中在真实中位数附近？</h1>
<p class="callout">现有轨迹没有显示这种集中模式：V3.2比Qwen保留了更宽的跨人差异，接近当月真人中位数的回答比例与真人自身接近。<strong>这不能排除训练污染。</strong></p>
<p class="note">同提示、温度0.5；2020-09、2021-09、2022-06、2025-03；共同支持{s['common_person_months']}个人月，各两遍。只读旧计分缓存，0新API、0重新拟合。</p>
<img src="dispersion.png" alt="四个月的跨人方差，以及接近真人当月中位数的回答比例">
<h2>分开看人际差异和随机波动</h2><div class="scroll"><table><thead><tr><th>对象</th><th>跨人方差 pp²</th><th>标准差 pp</th><th>跨人IQR pp</th><th>距同批真人中位数≤0.5pp</th>{'<th>距官方全国中位数≤0.5pp</th>' if concentration else ''}</tr></thead><tbody>{table}</tbody></table></div>
<p class="note">按月使用同一人群及设计权重，模型统计先平均两遍，再等权平均月份。标准差是逐月逐遍标准差的平均，不等于表中平均方差再开方。同批中位数与官方全国中位数分别列出，不混用。</p><ul>{repeat}</ul>
<h2>能够说明什么</h2><p>V3.2增加的跨人差异，没有伴随同等幅度的人内生成噪声增加。这与“更保留个人原有信念”的解释相容，但不是对模型内部机制的因果证明。</p>
<h2>仍不能说明什么</h2><p>模型即使接触过全国中位数，也可能根据提示生成分散的个人回答；反过来，共同输入也可能使一个没有记忆真值的模型回答集中。因此方差与集中比例是描述性检查，不能据此给出“未记忆真值”的概率。</p>
<p>下一步冻结其他2025月份的同人基线与真值，观察逐月中心、分布和先验组表现；2026发布后结果用于补充总体层面证据。新月份不用于调提示或拟合组合权重。</p>
{baseline_html}<p class="note">机器可读：<a href="summary.json">统计与口径</a>。2026-10-21。</p></main></html>'''
    (dest/'index.html').write_text(page)
    (dest/'summary.json').write_text(json.dumps(s,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--dest',type=Path,required=True)
    p.add_argument('--baselines',type=Path)
    a=p.parse_args();publish(a.source,a.dest,a.baselines)
