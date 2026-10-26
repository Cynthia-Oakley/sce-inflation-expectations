"""Render the separate, offline tau training-sensitivity follow-up."""
import argparse
import csv
import html
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from ..experiments.full_a_core_normal import ROOT, checked, read, sha, write


def build(source, report):
    source, report = Path(source).resolve(), Path(report).resolve()
    if report.exists() or not report.is_relative_to(ROOT/'docs/workstreams'):
        raise ValueError('Fresh workstream report required')
    manifest = read(source/'manifest.json')
    checked(source, manifest['files_sha256'])
    checked(ROOT, manifest['source_sha256'])
    data, search = read(source/'summary.json'), read(source/'training_search.json')
    report.mkdir(parents=True)
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti','Arial Unicode MS'],
                         'axes.unicode_minus':False,'font.size':11})
    selected = float(data['selection']['selected_tau'])
    r = data['results']
    fig, ax = plt.subplots(figsize=(10, 4.2), constrained_layout=True)
    finite = [x for x in search if x['tau'] != 'infinity']
    ax.plot([float(x['tau']) for x in finite], [x['mae_pp'] for x in finite],
            color='#1764AB', label='早48月训练MAE')
    ax.axhline(r['original_Core']['training48']['mae_pp'], color='#777777',
               ls='--', label='原Core训练MAE')
    ax.scatter([8, selected], [r['tau8']['training48']['mae_pp'],
               r['trained_tau']['training48']['mae_pp']], color=['#1764AB','#C75B12'], zorder=3)
    ax.annotate('原τ=8', (8, r['tau8']['training48']['mae_pp']), xytext=(10,14), textcoords='offset points')
    ax.annotate('训练选择τ≈202', (selected, r['trained_tau']['training48']['mae_pp']),
                xytext=(14,-17), textcoords='offset points')
    ax.set_xscale('symlog', linthresh=1)
    ax.set(xlabel='邻格先验强度 τ（0—1为线性，其后为对数刻度）', ylabel='全国Q9中位数MAE（pp）',
           title='只按早48个月选择τ：宽范围搜索，而非仅比较0/8/24')
    ax.legend(loc='upper right'); ax.grid(alpha=.2)
    fig.savefig(report/'training_search.png', dpi=160); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10,4.5), constrained_layout=True)
    periods = ['training48','later34','all82_descriptive']
    for j,(name,label,color) in enumerate([
        ('original_Core','原Core','#777777'),('tau8','原扩展 τ=8','#1764AB'),
        ('trained_tau','训练选择 τ≈202','#C75B12')]):
        values = [r[name][p]['mae_pp'] for p in periods]
        bars = ax.bar(np.arange(3)+(j-1)*.25, values, width=.24, label=label,color=color)
        ax.bar_label(bars, labels=[f'{v:.4f}' for v in values], padding=3,fontsize=10)
    ax.set_xticks(np.arange(3), ['训练48月\n2019-01—2022-12','后期34月\n2023-01—2025-10','全82月描述性汇总'])
    ax.set(ylabel='全国Q9中位数MAE（pp）',title='训练集收益未在后34个月保留为同样优势',ylim=(0,.44))
    ax.legend(loc='upper right'); ax.grid(axis='y',alpha=.2); ax.set_axisbelow(True)
    fig.savefig(report/'period_mae.png', dpi=160); plt.close(fig)

    minimum = min(x['mae_pp'] for x in search)
    tied = [x for x in finite if abs(x['mae_pp']-minimum)<=1e-12]
    rows = ''.join('<tr><th>'+label+'</th>'+''.join(
        f'<td>{r[name][p]["mae_pp"]:.4f}</td>' for p in periods)+'</tr>'
        for name,label in [('original_Core','原Core'),('tau0','扩展 τ=0'),('tau8','原扩展 τ=8'),
                           ('tau24','扩展 τ=24'),('trained_tau','训练选择 τ≈202'),('parent_limit','完全采用邻格的极限')])
    content = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>扩展参数τ的训练优化</title>
<style>body{{margin:0;background:#faf9f5;color:#222;font:18px/1.75 "Times New Roman","Kaiti SC","STKaiti",serif}}
main{{max-width:1080px;margin:auto;padding:32px 24px}}h1{{font-size:29px;line-height:1.4}}h2{{font-size:23px;margin-top:30px}}
.lead{{font-size:21px;border-left:4px solid #C75B12;padding:14px 18px;background:#f2ece3}}
img{{width:100%;height:auto}}table{{border-collapse:collapse;width:100%;background:white;font-variant-numeric:tabular-nums}}
th,td{{padding:9px;border-bottom:1px solid #ddd;text-align:right}}th:first-child{{text-align:left}}small,figcaption{{color:#555;font-size:15px}}a{{color:#1764AB}}</style>
<main><small>SCE · 原结果保留 · 离线监督校准敏感性 · 0 API / 0 新密度拟合</small>
<h1>τ不必限制在0、8、24；扩大搜索后，全期MAE约为0.30pp</h1>
<p class="lead">早48月按真人全国指标训练，扫描{len(search):,}个τ取值并局部细搜，选得τ≈202。全期MAE从原扩展的0.3014降到0.2999pp；仍高于原Core的0.2984pp。后34月并未显示优于原扩展，不能以跨过0.3作为采用理由。</p>
<h2>1．为什么此前只选三个值？</h2><p>0代表同格有供体时不收缩，8和24是适度与较强收缩的粗网格；它们不是经济学或认知理论给定的常数。原τ=8按被遮蔽的LLM回答选参，本页则使用早期真人全国指标，属于另一种监督校准，不能覆盖原选择记录。</p>
<figure><img src="training_search.png" alt="早48月全国Q9中位数MAE随tau变化"><figcaption>来源：冻结A82 Core＋Normal人口/答卷；训练目标仅2019-01—2022-12公开SCE全国Q9。候选0—128间隔0.125、128—1,000,000对数网格、无穷极限，加两轮训练内局部细搜。最小值不是唯一参数点；有{len(tied)}个已扫描τ并列。没有严格全局最优证明。</figcaption></figure>
<h2>2．按同一训练划分比较</h2><table><thead><tr><th>配置</th><th>训练48月 MAE（pp）</th><th>后34月 MAE（pp）</th><th>全82月 MAE（pp）</th></tr></thead><tbody>{rows}</tbody></table>
<figure><img src="period_mae.png" alt="原Core、tau8与训练选参的训练后期和全期MAE"><figcaption>纵轴从0开始；三组严格相同月份和全国目标。后34月早已参与项目探索，因此仅称后期检查，不称新的盲测。</figcaption></figure>
<h2>3．结果意味着什么？</h2><p>训练MAE从原Core的0.3578降到0.3560pp，收益很小；后34月则由0.2146变为0.2206pp。相对原扩展τ8，训练MAE降低0.0035pp，后期MAE增加0.0012pp。τ≈202意味着Normal更依赖邻格，而非该值精确识别了认知机制；Core回答仍保留。2021年MAE为0.5391pp，但仍不能替代全期与后期评价。</p>
<p>呈现上可以写“约0.30pp，扩展前后变化+0.003pp（约1%）”，同时披露精确值。0.3不是预先规定的研究成功阈值，不能仅为首位数字选参。原τ8及原报告不变，本页是额外敏感性分析，不自动切换配置。</p>
<p><a href="../results_v1/index.html">原Core＋Normal结果</a> · <a href="../README.md">方法与复算</a></p>
<small>预测/调参阶段不重新生成模型回答；选择先封存，再读取后期目标。参数搜索仅改τ、没有改变54格、入组池、供体选择或权重。完整数值与训练搜索见 {html.escape(str(source.relative_to(ROOT)))}。</small></main></html>'''
    (report/'index.html').write_text(content)
    write(report/'readout.json', data)
    write(report/'manifest.json', dict(source_manifest_sha256=sha(source/'manifest.json'),
          renderer_sha256=sha(Path(__file__)),
          files_sha256={p.name:sha(p) for p in report.iterdir() if p.is_file()}))
    print(str(report/'index.html'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a=p.parse_args(); build(a.source,a.out)


if __name__=='__main__': main()
