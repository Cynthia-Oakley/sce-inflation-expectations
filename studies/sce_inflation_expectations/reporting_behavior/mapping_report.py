"""Aggregate-only reading page for the registered mapping diagnostic."""
from html import escape
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "sce_mapping_mpl"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .analysis import dump, sha


NAMES = {"native": "原回答", "personal_history_mapping": "本人历史填法",
         "permuted_history_mapping": "打乱填法", "uniform_grid_5": "统一5%刻度",
         "uniform_grid_10": "统一10%刻度"}


def render(root, source, out):
    root, source, out = Path(root).resolve(), Path(source).resolve(), Path(out).resolve()
    if out.exists():
        raise FileExistsError("Use a fresh reading directory")
    s = json.loads((source / "summary.json").read_text())
    audit = json.loads((source / "independent_audit.json").read_text())
    p = s["protocol"]
    first = s["results_by_seed"][str(p["primary_style_seed"])]["arms"][p["primary_model_arm"]]
    a = {k: v["aggregate"] for k, v in first.items()}
    native, own, perm = (a[k] for k in ("native", "personal_history_mapping", "permuted_history_mapping"))
    seeds = []
    for seed in p["style_seeds"]:
        arm = s["results_by_seed"][str(seed)]["arms"][p["primary_model_arm"]]
        seeds.append({"seed": seed, "personal": arm["personal_history_mapping"]["aggregate"],
                      "permutation": arm["permuted_history_mapping"]["aggregate"]})
    intervals = s["primary_bootstrap"]["contrasts"]
    out.mkdir(parents=True)
    plt.rcParams.update({"font.family": "Arial Unicode MS", "axes.unicode_minus": False,
                         "font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                         "svg.fonttype": "none"})
    order = ["native", "personal_history_mapping", "permuted_history_mapping"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.9))
    for ax, metric, title in zip(axes, ["sample_center_mae_pp", "cross_section_w1_pp"],
                                 ["总体中心误差小幅下降", "人群分布距离小幅下降"]):
        values = [a[k][metric] for k in order]
        ax.bar([NAMES[k] for k in order], values, color=["#929c96", "#326a56", "#929c96"])
        for i, value in enumerate(values):
            ax.text(i, value + max(values) * .025, f"{value:.3f}", ha="center")
        ax.set_ylim(0, max(values) * 1.2)
        ax.set_ylabel("误差（百分点，越小越好）")
        ax.set_xlabel("概率填法处理")
        ax.set_title(title)
    fig.text(.02, .012, "来源：SCE/旧先验实验，2022-03/09、2023-03、2024-03；47有效人月，8单元等权，种子42，打乱50次评分平均。", fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, 1))
    fig.savefig(out / "mapping_errors.png", dpi=160)
    fig.savefig(out / "mapping_errors.svg")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.0))
    width = [native["cross_person_iqr_pp"], own["cross_person_iqr_pp"],
             perm["cross_person_iqr_pp"], native["real_cross_person_iqr_pp"]]
    axes[0].bar(["原回答", "本人填法", "打乱填法", "真人"], width,
                color=["#929c96", "#326a56", "#929c96", "#929c96"])
    for i, value in enumerate(width):
        axes[0].text(i, value + .10, f"{value:.2f}", ha="center")
    axes[0].set_ylim(0, max(width) * 1.15)
    axes[0].set_ylabel("人际中间50%跨度（百分点）")
    axes[0].set_xlabel("相同有效人群的预期分布")
    axes[0].set_title("人群差异仍远小于真人")
    keys = ["sample_center_mae_pp", "cross_section_w1_pp", "delta_w1_pp"]
    for pos, key in enumerate(keys):
        result = intervals["personal_minus_native"][key]
        lo, hi = result["interval_95"]
        axes[1].plot([lo, hi], [pos, pos], color="#326a56", lw=2)
        axes[1].plot(result["difference"], pos, "o", color="#326a56")
    axes[1].axvline(0, color="#929c96", ls="--", lw=1)
    axes[1].set_yticks(range(3), ["中心误差差值", "人群分布距离差值", "变化分布距离差值"])
    axes[1].set_xlabel("本人填法减原回答（百分点；负值为改善）")
    axes[1].set_ylabel("评价指标")
    axes[1].set_title("三个误差改善区间均包含0")
    fig.text(.02, .012, "来源：SCE/旧先验实验，2022-03/09、2023-03、2024-03；47人月。经验IQR；整人重抽1000次，固定历史/种子，非全国。", fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, 1))
    fig.savefig(out / "mapping_width_intervals.png", dpi=160)
    fig.savefig(out / "mapping_width_intervals.svg")
    plt.close(fig)

    real_shape = audit["real_current_shape"]["aggregate"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.9))
    shape_labels = ["原回答", "本人填法", "打乱填法", "真人"]
    probabilities = [native["observed_grid_proportions"], own["observed_grid_proportions"],
                     perm["observed_grid_proportions"], real_shape["observed_grid_proportions"]]
    bottom = np.zeros(4)
    for k, label, color in zip(range(3), ["含非5%倍数", "5%倍数但非全10%", "全10%倍数"],
                               ["#cbd2ce", "#799487", "#326a56"]):
        values = np.array([q[k] for q in probabilities]) * 100
        axes[0].bar(shape_labels, values, bottom=bottom, label=label, color=color)
        bottom += values
    axes[0].set_ylim(0, 105)
    axes[0].set_ylabel("问卷占比（%）")
    axes[0].set_xlabel("实际输出刻度（与分配的规则可能不同）")
    axes[0].set_title("数字刻度更接近真人")
    axes[0].legend(loc="lower right", fontsize=8)
    zeros = [native["zero_deflation_fraction"], own["zero_deflation_fraction"],
             perm["zero_deflation_fraction"], real_shape["zero_deflation_fraction"]]
    axes[1].bar(shape_labels, np.array(zeros) * 100, color=["#929c96", "#326a56", "#929c96", "#929c96"])
    for i, value in enumerate(zeros):
        axes[1].text(i, value * 100 + 1.5, f"{value:.1%}", ha="center")
    axes[1].set_ylim(0, 105)
    axes[1].set_ylabel("通缩五档合计填0的占比（%）")
    axes[1].set_xlabel("概率填法处理")
    axes[1].set_title("取整可以产生零概率")
    fig.text(.02, .012, "来源：SCE/旧先验实验，2022-03/09、2023-03、2024-03；47人月。真人为原始Q9；舍去小尾部产生0，非已识别的心理因果。", fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, 1))
    fig.savefig(out / "mapping_format.png", dpi=160)
    fig.savefig(out / "mapping_format.svg")
    plt.close(fig)

    def interval(label, key):
        lo, hi = intervals[label][key]["interval_95"]
        return f"[{lo:.3f}, {hi:.3f}]"
    report = f"""# 个人概率填法：形式改善，信念差异仍未恢复

2026-10-13。零新增API、费用$0。先登记规则，再复用旧回答；不是新LLM模拟，也不是全国预测。

## 结论

程序映射确实改变了概率刻度和小尾部。主种子下中心MAE {native['sample_center_mae_pp']:.3f}→{own['sample_center_mae_pp']:.3f}pp、人群分布W1 {native['cross_section_w1_pp']:.3f}→{own['cross_section_w1_pp']:.3f}pp；改善小且区间跨0。本人填法与打乱填法的中心误差仅差{abs(own['sample_center_mae_pp']-perm['sample_center_mae_pp']):.3f}pp，没有清晰的身份增量证据。

人际IQR {native['cross_person_iqr_pp']:.2f}→{own['cross_person_iqr_pp']:.2f}pp，真人{native['real_cross_person_iqr_pp']:.2f}pp。报告层没有解决同质化，不作为主机制升级，也不据此自动开启新API实验。下一重点仍是个人信念保留与更新。

![中心与分布误差](mapping_errors.png)
![人际差异与区间](mapping_width_intervals.png)

## 输入和实现

四期2022-03/09、2023-03、2024-03各12人、两次生成、三组既有回答。96条Q9配对记录中94条共同有效，即47人月、三组共282份模型问卷；1个真实人月无效在两遍均排除，映射额外失败0。384配对行包含四类指标，不能当384份问卷。所有组用同一有效集。

模式参考只用2017—2019已经拟合的表和本人严格早于目标月的合法问卷。本批每人有1—11次历史，没有新入组冷启动样本；无历史回退机制只经单元检查，未在这批数据得到实证检验。个人分布为 `(3×训练期参考＋本人历史计数)/(3＋历史次数)`，参考包含上次信念形状，因此它不是纯粹识别出的报告人格。

每个种子为每个人分配一个模式，三组及两次生成共享；精细模式保留原概率，5%/10%模式用最大余数法补齐100%。约{audit['roster_tie_break_boundary_fraction_among_grid_variants']:.1%}的5%/10%变体在补齐的截断处出现余数并列。既定规则按原档位顺序处理，会把部分质量优先放在较高通胀档，可能贡献中心上移；没有据结果换另一规则，不能视为中性的人类认知机制。同月12人的分配打乱50次，保留完整名单的模式比例；1个评价排除者仍在名单内，故11人有效子集的比例可能小幅变化。

种子42为主结果，另四个事先登记种子全部报告，未挑最佳。已看到这些月份与旧统一取整实验，属于回顾开发诊断，不能称未见过的项目测试。

## 实际变化

原模型有{native['observed_grid_proportions'][0]:.1%}回答含非5%倍数，本人映射后为{own['observed_grid_proportions'][0]:.1%}；同批真人{real_shape['observed_grid_proportions'][0]:.1%}。通缩五档合计0的占比{native['zero_deflation_fraction']:.1%}→{own['zero_deflation_fraction']:.1%}，真人{real_shape['zero_deflation_fraction']:.1%}。这说明表达格式可改善，不能说明模型获得了更像真人的通胀信念。

![概率刻度与零概率](mapping_format.png)

总体中心平均有符号偏差{native['center_bias_pp']:.3f}→{own['center_bias_pp']:.3f}pp，向上移动{own['center_bias_pp']-native['center_bias_pp']:.3f}pp；其条件差值区间{interval('personal_minus_native','center_bias_pp')}。一些月份绝对误差减小与平均偏差增加可以同时出现。概率合计守恒不保证拟合均值或聚合中位数守恒；本次主结果拟合家族没有切换。

统一5%/10%只是敏感性参照。10%情景中心MAE {a['uniform_grid_10']['sample_center_mae_pp']:.3f}pp，但变化分布W1 {a['uniform_grid_10']['delta_w1_pp']:.3f}pp，高于原{native['delta_w1_pp']:.3f}pp，且仍远小于真人宽度；不能因一个指标更低就挑它作为最优机制。

## 统计学解释

中心和IQR都用项目经验CDF的左逆分位数；本页真人IQR {native['real_cross_person_iqr_pp']:.2f}pp，与之前插值IQR约5.50pp定义不同，样本没有因此改变。每月×生成单元等权，不用SCE全国权重。变化量统一相对本人真实上月中心；无先验组的差值不是模型自身状态的连续更新。

按整个人配对重抽1000次，保留其所有时期和两次生成，在每月重新归一权重，再重新计算中位数和W1。不能把两遍生成、五个分配种子或50次打乱当新真人。区间条件于固定历史、分配和四个时期，不包含全国抽样、未来时期或训练表估计的全部不确定性。

- 本人减原回答：中心误差差值{own['sample_center_mae_pp']-native['sample_center_mae_pp']:.3f}pp，95%区间{interval('personal_minus_native','sample_center_mae_pp')}；人群W1差值{own['cross_section_w1_pp']-native['cross_section_w1_pp']:.3f}pp，区间{interval('personal_minus_native','cross_section_w1_pp')}。
- 本人减50次打乱的平均评分：中心误差差值{own['sample_center_mae_pp']-perm['sample_center_mae_pp']:.3f}pp，区间{interval('personal_minus_permutation_mean','sample_center_mae_pp')}；W1差值{own['cross_section_w1_pp']-perm['cross_section_w1_pp']:.3f}pp，区间{interval('personal_minus_permutation_mean','cross_section_w1_pp')}。
- 五种分配种子下，本人中心MAE {min(r['personal']['sample_center_mae_pp'] for r in seeds):.3f}—{max(r['personal']['sample_center_mae_pp'] for r in seeds):.3f}pp；W1 {min(r['personal']['cross_section_w1_pp'] for r in seeds):.3f}—{max(r['personal']['cross_section_w1_pp'] for r in seeds):.3f}pp；人际IQR {min(r['personal']['cross_person_iqr_pp'] for r in seeds):.2f}—{max(r['personal']['cross_person_iqr_pp'] for r in seeds):.2f}pp。部分种子的变化分布距离略恶化。

区间包含0，表示当前数据既容许小幅改善，也容许恶化，不能判定稳定增益；不等于证明机制绝对无效。置换保持模式比例，但未控制所有信念与人口差异，不是心理因果实验或置换检验p值。

## 复核、路径与下一步

六项单元检查通过。独立Scipy W1与经验分位数重算差异小于1e-10；48个人当前/未来答案扰动均未改变习惯分布；已有历史预测逐项对账。原始回答哈希与15保护文件保持，Q8未改，原/映射答案分开保存在本地。

原生输出仍明显集中。让填法更真实不能替代个人预期与更新机制。将本结果交Kimi，优先继续个人长期基准、本人状态和新信息更新的离线研究；暂不选最优刻度或扩大本映射的付费试验。B版仍需使用可得历史初始化或自己的模拟状态，不能逐月读取未发布真人上期问卷。

复算：`python scripts/analyze_sce_reporting_mapping.py --out outputs/<全新结果目录>`；阅读：`python -m studies.sce_inflation_expectations.reporting_behavior.mapping_report --source outputs/<结果目录> --out outputs/<全新阅读目录>`。源码/协议及输入哈希随结果保存，原文件不覆盖。

Source: Survey of Consumer Expectations, Federal Reserve Bank of New York. FRBNY disclaims responsibility for this analysis and interpretation.
"""
    (out / "report.md").write_text(report, encoding="utf-8")
    rows = "".join(f"<tr><th>{escape(NAMES[k])}</th>" + "".join(f"<td>{a[k][m]:.3f}</td>" for m in
                   ["sample_center_mae_pp", "cross_section_w1_pp", "cross_person_iqr_pp", "delta_w1_pp"]) + "</tr>" for k in NAMES)
    sections = []
    for paragraph in report.split("\n\n"):
        if paragraph.startswith(("# ", "![")):
            continue
        if paragraph.startswith("## "):
            sections.append(f"<h2>{escape(paragraph[3:])}</h2>")
        elif paragraph.startswith("- "):
            sections.append("<ul>" + "".join(f"<li>{escape(line[2:])}</li>" for line in paragraph.splitlines()) + "</ul>")
        else:
            sections.append(f"<p>{escape(paragraph)}</p>")
    body = "".join(sections)
    page = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>个人概率填法离线验证</title><style>
    *{{box-sizing:border-box}}body{{background:#fafaf7;color:#26332f;margin:0;font-family:system-ui,-apple-system,"PingFang SC",sans-serif}}main{{max-width:1040px;margin:auto;padding:32px 24px}}h1{{font-size:26px;line-height:1.4}}p{{line-height:1.85;white-space:pre-wrap}}img{{display:block;width:100%;height:auto;margin:24px 0}}table{{border-collapse:collapse;min-width:680px;width:100%;font-size:15px}}td,th{{padding:12px;text-align:left;border:1px solid #dce2dc}}a{{color:#326a56}}.scroll{{overflow:auto}}.details{{margin-top:32px}}@media(max-width:600px){{main{{padding:22px 16px}}h1{{font-size:23px}}}}
    </style></head><body><main><h1>个人概率填法：形式改善，信念差异仍未恢复</h1><p>四期、47有效人月；API费用 $0。本人匹配与打乱匹配接近；人际差异仍远小于真人。</p>
    <div class="scroll"><table><thead><tr><th>处理方式</th><th>中心MAE（pp）</th><th>人群W1（pp）</th><th>人际IQR（pp）</th><th>变化W1（pp）</th></tr></thead><tbody>{rows}</tbody></table></div>
    <img src="mapping_errors.png" alt="中心与分布误差"><img src="mapping_width_intervals.png" alt="人际差异及配对区间"><img src="mapping_format.png" alt="刻度与零概率"><div class="details">{body}</div>
    <p><a href="../../docs/current_todo.html">返回当前任务清单</a> · <a href="report.md">完整文字稿</a></p></main></body></html>'''
    (out / "index.html").write_text(page, encoding="utf-8")
    curated = {"status": s["status"], "source": str(source.relative_to(root)),
               "source_summary_sha256": sha(source / "summary.json"), "coverage": s["coverage"],
               "history": s["history"], "primary_style_seed": p["primary_style_seed"],
               "primary_model_arm": p["primary_model_arm"],
               "primary_results": {k: v["aggregate"] for k, v in first.items()},
               "primary_bootstrap": s["primary_bootstrap"], "seed_sensitivity": seeds,
               "real_current_shape": real_shape, "independent_audit": {k: v for k, v in audit.items() if k != "real_current_shape"},
               "new_api_calls": 0, "api_cost_usd": 0,
               "interpretation": "Limited measurement-format improvement; no clear identity-specific advantage or recovery of cross-person heterogeneity; no automatic new simulation.",
               "source_hashes": s["source_hashes"], "analysis_code_hashes": s["code_hashes"],
               "report_code_sha256": sha(__file__)}
    dump(out / "public_summary.json", curated)
    print(json.dumps({"reading": str(out), "public_summary": str(out / "public_summary.json")}), flush=True)
    return curated


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    render(Path(__file__).resolve().parents[3], args.source, args.out)
