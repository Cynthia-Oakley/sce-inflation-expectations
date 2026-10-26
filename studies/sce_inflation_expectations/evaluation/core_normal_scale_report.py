"""Compare Core budgets using existing frozen checks; no refits or API calls."""
from collections import defaultdict
from html import escape
import json
from pathlib import Path

import numpy as np

from .grid_dimension_selection import ROOT, dump, sha

HUMAN = ROOT / 'outputs/sce_core_normal_human_20261023_v2'
PILOT = ROOT / 'outputs/sce_core_normal_scale_pilot_preparation_20261023_v1'
READOUT = ROOT / 'docs/workstreams/20261023_core_normal/readout.json'
BUDGETS = (256, 384, 512)
PERIODS = {'all': (201901, 202510), 'development': (201901, 202212),
           '2023_2024': (202301, 202412), '2025_01_10': (202501, 202510)}
LABELS = {'all': '2019-01—2025-10，82个月', 'development': '2019—2022，48个月',
          '2023_2024': '2023—2024，24个月', '2025_01_10': '2025-01—10，10个月'}


def summarize(rows):
    counts = {}
    for r in rows:
        n = r['core_n'] + r['normal_n']
        if r['month'] in counts and counts[r['month']] != n:
            raise ValueError('Frame differs across existing budget/seed results')
        counts[r['month']] = n
    result = {'periods': {}, 'months': len(counts),
              'frame_n_min': min(counts.values()), 'frame_n_max': max(counts.values()),
              'frame_n_mean': float(np.mean(list(counts.values()))),
              'positive_weight_person_months': sum(counts.values())}
    for period, (low, high) in PERIODS.items():
        ns = {m: n for m, n in counts.items() if low <= m <= high}
        result['periods'][period] = []
        for budget in BUDGETS:
            part = [r for r in rows if low <= r['month'] <= high
                    and r['core_budget'] == budget and r['method'] == 'joint_tau24']
            if len(part) != len(ns) * 2 or any(r['status'] != 'ok' for r in part):
                raise ValueError('Incomplete fixed two-seed scale comparison')
            by_month = defaultdict(list)
            for r in part:
                by_month[r['month']].append(r['all_q9']['median_mae_pp'])
            month_mae = [float(np.mean(v)) for v in by_month.values()]
            result['periods'][period].append({
                'core_n': budget, 'months': len(ns), 'normal_n_mean': float(np.mean([n-budget for n in ns.values()])),
                'mean_core_fraction': float(np.mean([budget/n for n in ns.values()])),
                'logical_calls_one_generation': budget * len(ns),
                'calls_saved_vs_all_llm_fraction': 1. - budget * len(ns) / sum(ns.values()),
                'q9_median_approximation_mae_pp': float(np.mean(month_mae)),
                'q9_median_approximation_mae_month_p90_pp': float(np.quantile(month_mae, .9)),
                'q9_w1_approximation_pp': float(np.mean([r['all_q9']['w1_pp'] for r in part])),
                'core_only_median_approximation_mae_pp': float(np.mean([
                    r['all_q9']['median_mae_pp'] for r in rows if low <= r['month'] <= high
                    and r['core_budget'] == budget and r['method'] == 'poststratified_Core_only']))})
    return result


def render(out):
    out = Path(out).resolve()
    if out.exists():
        raise ValueError('Fresh report directory required')
    data = summarize(json.loads((HUMAN / 'monthly_private.json').read_text()))
    pilot = json.loads((PILOT / 'summary.json').read_text())
    cached = json.loads(READOUT.read_text())
    data.update(status='descriptive_reuse_of_existing_checks_not_new_llm_evidence',
                new_api_calls=0, new_q9_fits=0, pilot=pilot,
                cached_human={'all_saved_llm': cached['full_llm_human'],
                              'reduced_core_normal': cached['cache_human']['joint_tau24']},
                limitations=['Human Core answers are an evaluation-only idealized statistical reference, not LLM forecasts.',
                             'Two fixed allocation seeds; month P90 is descriptive variability, not a confidence bound.',
                             'Saved LLM frames have only 96/192 prior-valid people; do not identify full-wave optimal Core size.',
                             'Larger Normal populations add no independent LLM information.'],
                source_sha256={str(p.relative_to(ROOT)): sha(p) for p in
                    [HUMAN/'monthly_private.json', HUMAN/'summary.json', PILOT/'summary.json', READOUT, Path(__file__)]})
    out.mkdir(parents=True); figures=out/'figures'; figures.mkdir()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'serif', 'font.serif': ['Times New Roman', 'DejaVu Serif'],
                         'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.5))
    for period, color, style, label in [('development', '#777777', 'o--', '2019-2022'),
                                       ('2023_2024', '#7437aa', 's-', '2023-2024'),
                                       ('2025_01_10', '#c76800', '^-', '2025 Jan-Oct')]:
        for ax, metric in zip(axes, ['q9_median_approximation_mae_pp', 'q9_w1_approximation_pp']):
            ax.plot(BUDGETS, [r[metric] for r in data['periods'][period]], style, color=color, label=label)
            ax.set_xticks(BUDGETS); ax.set_xlabel('Different LLM Core people / month (proposed)')
            ax.grid(axis='y', alpha=.2)
    axes[0].set_title('Full-wave median approximation MAE'); axes[1].set_title('Full-wave W1 approximation')
    for ax in axes:
        ax.set_ylabel('Error (pp), lower is better')
        ax.set_ylim(bottom=0)
    axes[1].legend(fontsize=10)
    fig.suptitle('Idealized HUMAN Core: statistical approximation, not LLM fit', fontsize=13)
    fig.subplots_adjust(left=.10, right=.98, bottom=.20, top=.78, wspace=.32)
    for extension in ['png', 'svg']:
        fig.savefig(figures/f'scale_tradeoff.{extension}', dpi=160, bbox_inches='tight', pad_inches=.25)
    plt.close(fig)
    cards=''.join(f'<article><h3>{r["core_n"]}名Core</h3><p>平均占月框架 {r["mean_core_fraction"]:.1%}<br>平均Normal {r["normal_n_mean"]:.0f}人</p><p>82月单遍 {r["logical_calls_one_generation"]:,}次<br>比全员LLM减少 {r["calls_saved_vs_all_llm_fraction"]:.1%}</p><strong>理想Core中位数近似MAE {r["q9_median_approximation_mae_pp"]:.3f}pp</strong></article>' for r in data['periods']['all'])
    month_rows=''.join(f'<tr><td>{r["month"]}</td><td>{r["frame_n"]}</td><td>{r["core_union_n"]}</td><td>{r["audit_n"]}</td><td>{r["unique_llm_positions"]}</td></tr>' for r in pilot['months'])
    page=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Core规模、Normal扩展与验证成本</title><style>
body{{margin:0;background:#faf9f5;color:#252525;font-family:"Times New Roman","Kaiti SC","STKaiti","KaiTi",serif;line-height:1.85}}main{{max-width:1100px;margin:auto;padding:32px 24px}}h1{{font-size:28px}}h2{{font-size:23px;margin-top:32px}}aside{{background:#f4ede0;padding:14px 20px;border-left:4px solid #c76800}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}article{{padding:10px 0;border-bottom:1px solid #aaa}}img{{width:100%}}table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}a{{color:#7437aa}}.note{{color:#555}}@media(max-width:650px){{.cards{{grid-template-columns:1fr}}}}</style></head><body><main>
<p>SCE · 2026-10-23 · 复用已有结果／新增API 0</p><h1>先确定需要多少Core，再决定扩展多少Normal</h1>
<aside><strong>研究目标：</strong>重建每月SCE加权人群分布。历史框架实际每月{data['frame_n_min']}—{data['frame_n_max']}名有效权重受访者，平均{data['frame_n_mean']:.0f}人。Normal补足该月框架；不为复制别人的五万人规模而增加展示人数。扩展人数增加不会增加独立信息。</aside>
<h2>1．三种Core规模的已知取舍</h2><div class="cards">{cards}</div>
<p class="note">来源：2019-01—2025-10，82个月、两个固定抽样种子，既有真人Core留出v2，固定τ24。这里只读取原统计结果，未重抽样或重新计分。调用数按一遍计算，不含审计、失败或精确缓存复用。Core占比按各月人数计算；人口质量比例仍由权重决定。</p>
<img src="figures/scale_tradeoff.png" alt="三时期中位数近似MAE和W1随Core人数增加而变化">
<p><strong>解释：</strong>Core增加时，通常能更好地保留完整波次分布。384人是值得验证的折中档；256人是低成本候选，512人是较高精度参照。以上使用真人答卷充当理想Core，不能承诺相应的LLM拟合误差，更不能把近似误差从模型误差中扣除。</p>
<h2>2．现有LLM答卷能复用什么</h2><p>已有八个月V3.2答卷可用来检验“隐藏部分LLM回答后，Normal能否恢复原分布”，不需要新API。已有结果：同一小框架完整LLM的中位数MAE约0.229pp，缩小Core并扩展后约0.353pp。它提醒我们必须评价近似代价；旧96/192人、主要回访者的框架不足以决定完整波次的最佳Core规模。</p>
<p>真人微观当前答案只用于隔离评价，不发送模型，也不作为生产Core。复用旧模型回答必须同时匹配完整提示、模型、供应商与参数，不能只凭“同一个人、同一个月”复用。</p>
<h2>3．一次真实调用，离线比较三种Core规模</h2><p>三个预定月份的256／384／512名册均已检查为逐级包含；每月只取得512人一次LLM回答。分析256或384人方案时，把额外回答隐藏，按该规模自己的抽样概率和校准权重估计Normal。原256人名单未改变。</p>
<table><thead><tr><th>月份</th><th>有效权重框架</th><th>共用Core回答</th><th>独立审计回答</th><th>最多LLM位置</th></tr></thead><tbody>{month_rows}</tbody></table>
<p>共最多<strong>{pilot['maximum_unique_requests_before_exact_prompt_reuse']:,}个唯一调用位置</strong>，一遍；同三期三种规模分别做独立批次将需{pilot['separate_size_pilots_without_sharing']:,}个位置。按拟用的OpenRouter→固定SiliconFlow FP8→DeepSeek V3.2、温度0.5和相同P/E准备。现阶段没有发起请求；完整提示去重与预算核算后另申请授权。</p>
<p><strong>审计边界：</strong>额外64人来自所有Core名册以外，只用于评价。三种规模都比较同一个留出人口池；它不是小Core方案全部Normal的代表样本。总体拟合另外对照整波真人，中位数/W1/组内分歧分别报告。不能用审计回答帮助拟合，也不能把已有的额外Core回答偷放入小规模模型。</p>
<h2>4．下一步与Kimi分工</h2><p>Codex负责规模取舍、扩展与评价；Kimi可负责三期完整框架的角色无关起点/P/E模板及运行输入适配。先准备一份全框架输入，再接不同Core名单，避免每个规模重复造一套输入。详见<a href="../kimi_engineering_tasks.md">可转交的工程任务</a>。最终比例以小试后的成本—精度取舍确定，不自动采纳256人或固定比例。</p>
<p class="note">本页是开发性规模比较；后期月份此前已研究，不称盲测。Normal不是新增独立受访者。未启动82个月全量，也未解决近期11月的严格B资格。</p><p><a href="../index.html">Core＋Normal总览</a> · <a href="readout.json">聚合结果与来源哈希</a></p></main></body></html>'''
    (out/'index.html').write_text(page)
    dump(out/'readout.json',data)
    canvas='''import {H1,H2,Text,Stack,Select,BarChart,Table,useState,useHostTheme} from "cursor/canvas";
const D=__DATA__;
export default function CoreScale(){const t=useHostTheme();const[p,setP]=useState("all");const rows=D.periods[p as keyof typeof D.periods];return <Stack gap={18} style={{padding:24,maxWidth:1100,margin:"auto",background:t.bg.editor,color:t.text.primary,fontFamily:'"Times New Roman","Kaiti SC","KaiTi",serif'}}>
<Text>SCE · 2026-10-23 · 新增API 0</Text><H1>Core规模：成本与分布近似的取舍</H1><Text>目标是当月SCE加权框架。Normal补足未直接调用LLM的人；复制到五万人不增加独立信息。以下为真人理想Core的统计参照，不能当LLM拟合成绩。</Text>
<Select value={p} onChange={setP} options={[{value:"all",label:"82个月总体"},{value:"development",label:"2019—2022"},{value:"2023_2024",label:"2023—2024"},{value:"2025_01_10",label:"2025年1—10月"}]}/>
<H2>完整波次中位数近似MAE</H2><Text>横轴：每月不同Core人数；纵轴：近似MAE（pp，越低越好）。来源：2019-01—2025-10既有82月结果，两抽样种子、固定τ24；各时期均已见。</Text>
<BarChart categories={rows.map(r=>String(r.core_n)+"人")} series={[{name:"真人Core＋Normal，中位数近似MAE",data:rows.map(r=>r.q9_median_approximation_mae_pp)}]} height={260} showValues={true} valueSuffix="pp"/>
<Table headers={["每月Core","平均Core占比","一遍调用位置","中位数近似MAE pp","W1近似 pp"]} rows={rows.map(r=>[String(r.core_n),(100*r.mean_core_fraction).toFixed(1)+"%",String(r.logical_calls_one_generation),r.q9_median_approximation_mae_pp.toFixed(3),r.q9_w1_approximation_pp.toFixed(3)])}/>
<H2>一批回答比较三种规模</H2><Text>2021-09、2022-06、2025-06：每月512人共用回答＋64人独立审计，最多1728个调用位置、一遍；还需完整提示、精确缓存检查与预算授权。评估较小Core时隐藏额外Core回答。审计只代表所有Core以外的共同留出人口池。</Text>
<Text>已有小框架LLM缓存：全调用对真人MAE0.229pp，缩小Core＋Normal后0.353pp。统计扩展存在代价，384是待验证折中档，尚未确定最终人数。</Text>
<a style={{color:t.text.link}} href="/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/docs/workstreams/20261023_core_normal/scale_comparison/index.html">完整图文与来源</a></Stack>}
'''.replace('__DATA__',json.dumps(data,ensure_ascii=False))
    (out/'SCE-core-scale-20261023.canvas.tsx').write_text(canvas)
    return data
