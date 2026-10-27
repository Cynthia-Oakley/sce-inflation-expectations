#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.downstream_regression import (
    CONTRASTS,
    MODELS,
    OUTCOMES,
    build_analysis_frame,
    contrast_metrics,
    evaluate_a_b,
    load_merged_inputs,
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def make_figures(contrasts, summary, figures):
    figures.mkdir()
    labels = {
        "PCEDGC96": "Durable goods",
        "REVOLSL": "Revolving credit",
        "wage_growth_overall": "Wage growth",
        "MICH": "Michigan expectations",
    }
    pairs = [
        ("official_sce", "simulated_sce", "Raw simulation vs official SCE"),
        ("official_sce", "blended_sce", "Final blend vs official SCE"),
        ("domain_arx", "official_plus_simulated", "Official + simulation vs domain ARX"),
    ]
    fig, axes = plt.subplots(4, 3, figsize=(14, 15), constrained_layout=True)
    for row, outcome in enumerate(OUTCOMES):
        for col, horizon in enumerate([1, 2, 3]):
            ax = axes[row, col]
            values = []
            names = []
            for reference, candidate, name in pairs:
                match = contrasts[
                    (contrasts["scope"] == "A")
                    & (contrasts["outcome"] == outcome)
                    & (contrasts["horizon"] == horizon)
                    & (contrasts["reference"] == reference)
                    & (contrasts["candidate"] == candidate)
                ]
                values.append(100 * match.iloc[0]["rmse_improvement"])
                names.append(name)
            ax.bar(range(3), values, color=["#526D82", "#7A8B69", "#A77860"])
            ax.axhline(0, color="black", linewidth=0.8)
            ax.set_xticks(range(3), ["Raw vs SCE", "Blend vs SCE", "Increment vs ARX"], rotation=18, ha="right")
            ax.set_ylabel("RMSE improvement (%)")
            ax.set_title(f"{labels[outcome]} · {horizon} month ahead")
    fig.savefig(figures / "a_rmse_improvement.png", dpi=160)
    plt.close(fig)

    short = {
        "persistence": "Persist",
        "expanding_mean": "Mean",
        "ar1": "AR(1)",
        "domain_arx": "ARX",
        "official_sce": "Official",
        "simulated_sce": "Simulation",
        "blended_sce": "Blend",
        "official_plus_simulated": "Off.+Sim.",
    }
    fig, axes = plt.subplots(4, 3, figsize=(15, 15), constrained_layout=True)
    for row, outcome in enumerate(OUTCOMES):
        for col, horizon in enumerate([1, 2, 3]):
            ax = axes[row, col]
            subset = summary[
                (summary["scope"] == "A")
                & (summary["outcome"] == outcome)
                & (summary["horizon"] == horizon)
            ].set_index("model").loc[MODELS]
            ax.bar(range(len(MODELS)), subset["rmse"], color="#526D82")
            ax.set_xticks(range(len(MODELS)), [short[m] for m in MODELS], rotation=35, ha="right")
            ax.set_ylabel("Rolling RMSE")
            ax.set_title(f"{labels[outcome]} · {horizon} month ahead")
    fig.savefig(figures / "a_all_model_rmse.png", dpi=160)
    plt.close(fig)


def table_html(frame, columns, headers=None, percent_columns=None):
    percent_columns = set(percent_columns or [])
    headers = headers or columns
    parts = ["<div class='table-wrap'><table><thead><tr>"]
    parts.extend(f"<th>{html.escape(str(label))}</th>" for label in headers)
    parts.append("</tr></thead><tbody>")
    for _, row in frame[columns].iterrows():
        parts.append("<tr>")
        for column in columns:
            value = row[column]
            if pd.isna(value):
                text = "—"
            elif column in percent_columns:
                text = f"{100 * value:+.2f}%"
            elif isinstance(value, (float, np.floating)):
                text = f"{value:.5f}"
            else:
                text = str(value)
            parts.append(f"<td>{html.escape(text)}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def render_report(out, merged, frames, summary, in_sample, contrasts, min_train):
    key_pairs = {
        ("official_sce", "simulated_sce"),
        ("official_sce", "blended_sce"),
        ("domain_arx", "official_plus_simulated"),
        ("persistence", "blended_sce"),
        ("ar1", "blended_sce"),
    }
    key = contrasts[contrasts.apply(lambda row: (row["reference"], row["candidate"]) in key_pairs, axis=1)].copy()
    key["horizon"] = key["horizon"].astype(str)
    key = key.sort_values(["scope", "outcome", "horizon", "reference", "candidate"])
    positive = float((key["rmse_improvement"] > 0).mean())
    coverage = []
    for frame in frames:
        evaluated = summary[(summary["outcome"] == frame.attrs["outcome"]) & (summary["horizon"] == frame.attrs["horizon"])]
        coverage.append({
            "outcome": frame.attrs["outcome"],
            "horizon": frame.attrs["horizon"],
            "A_origins": int((frame["scope"] == "A").sum()),
            "B_origins": int((frame["scope"] == "B").sum()),
            "A_evaluated": int(evaluated[evaluated["scope"] == "A"]["n"].max()),
            "B_evaluated": int(evaluated[evaluated["scope"] == "B"]["n"].max()),
            "first_origin": frame["date"].min().strftime("%Y-%m"),
            "last_origin": frame["date"].max().strftime("%Y-%m"),
        })
    coverage = pd.DataFrame(coverage)
    coverage.to_csv(out / "coverage.csv", index=False)
    key.to_csv(out / "key_contrasts.csv", index=False)
    body = f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>SCE 下游经济用途回归</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',sans-serif;margin:0;background:#f5f6f4;color:#1f2933;line-height:1.55}}
main{{max-width:1400px;margin:auto;padding:32px}}h1{{font-size:28px;margin-bottom:6px}}h2{{margin-top:34px}}.sub{{color:#5d6872}}
.notice{{background:#fff7df;border-left:4px solid #b68b2c;padding:12px 16px;margin:20px 0}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}
.card{{background:white;padding:16px;border:1px solid #dfe3e6;border-radius:8px}}.num{{font-size:24px;font-weight:650}}img{{max-width:100%;background:white;border:1px solid #dfe3e6;margin:8px 0}}
.table-wrap{{overflow:auto;background:white;border:1px solid #dfe3e6}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{padding:7px 9px;border-bottom:1px solid #e7eaec;text-align:right;white-space:nowrap}}th{{background:#edf0ef;position:sticky;top:0}}td:nth-child(-n+6),th:nth-child(-n+6){{text-align:left}}details{{margin-top:18px}}code{{background:#e9edeb;padding:2px 4px}}@media(max-width:850px){{.grid{{grid-template-columns:1fr}}main{{padding:18px}}}}
</style></head><body><main>
<h1>SCE 下游经济用途：ConsumerSim 风格回归</h1>
<div class='sub'>A82 扩展窗口回测＋B11 冻结迁移 · 预测未来 1—3 个月 · 0 Simulation/LLM</div>
<div class='notice'><b>解释边界：</b>这是当前公开版本数据的回顾性分析，不是严格实时预测。B 仅作小样本迁移敏感性；所有结局、预测期、模型和对照均完整保留，正向结果不等于因果效应或稳定经济贡献。</div>
<div class='grid'><div class='card'>结局 × 预测期<div class='num'>4 × 3</div></div><div class='card'>完整模型<div class='num'>8</div></div><div class='card'>A 最少训练标签<div class='num'>{min_train}</div></div><div class='card'>重点对照 RMSE 改善为正<div class='num'>{positive:.1%}</div></div></div>
<h2>方法</h2><p>耐用品与信贷预测未来对数增长；工资与 MICH 预测未来百分点变化。比较零增长、历史均值、AR(1)、领域 ARX、官方 SCE、原始模拟、最终组合和官方＋模拟。A 每个预测日只用当时已经形成的结局标签；B 只用首个 B 原点前可得的 A 标签拟合一次。</p>
<h2>样本覆盖</h2>{table_html(coverage, list(coverage.columns))}
<h2>A 滚动 RMSE 改善</h2><img src='figures/a_rmse_improvement.png' alt='A滚动RMSE改善'>
<h2>A 全部模型 RMSE</h2><img src='figures/a_all_model_rmse.png' alt='A全部模型RMSE'>
<h2>重点对照完整表</h2><p>RMSE/MAE 改善为正值表示候选模型优于参照；ΔR² 为 A 样本内候选减参照。B 没有重估模型。</p>
{table_html(key, ['scope','outcome','horizon','reference','candidate','n','delta_r2','rmse_improvement','mae_improvement'], percent_columns=['rmse_improvement','mae_improvement'])}
<details><summary><b>全部 17 类对照（不筛选）</b></summary>{table_html(contrasts, ['scope','outcome','horizon','reference','candidate','n','delta_r2','rmse_improvement','mae_improvement'], percent_columns=['rmse_improvement','mae_improvement'])}</details>
<details><summary><b>全部模型样本外指标</b></summary>{table_html(summary, ['scope','outcome','horizon','model','n','n_train_min','n_train_max','mae','rmse','bias'])}</details>
<details><summary><b>A 样本内指标</b></summary>{table_html(in_sample, ['outcome','horizon','model','n','mae','rmse','bias','r2'])}</details>
<h2>复算文件</h2><p><code>predictions.csv</code> 保存逐月逐模型预测；<code>model_metrics.csv</code>、<code>in_sample_metrics.csv</code>、<code>contrasts.csv</code> 保存完整指标；<code>manifest.json</code> 记录输入与代码哈希。缺失值按每个结局×预测期的联合特征完整案例剔除，未插值。</p>
</main></body></html>"""
    (out / "index.html").write_text(body, encoding="utf-8")
    return coverage, key


def run(panel_path, a_path, b_path, out, min_train=36, protocol_path=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    merged = load_merged_inputs(panel_path, a_path, b_path)
    merged.to_csv(out / "merged_monthly.csv", index=False)
    frames = []
    predictions = []
    summaries = []
    in_samples = []
    for outcome in OUTCOMES:
        for horizon in [1, 2, 3]:
            frame = build_analysis_frame(merged, outcome, horizon)
            pred, summary, in_sample = evaluate_a_b(frame, min_train=min_train)
            frames.append(frame)
            predictions.append(pred)
            summaries.append(summary)
            in_samples.append(in_sample)
    predictions = pd.concat(predictions, ignore_index=True)
    summary = pd.concat(summaries, ignore_index=True)
    in_sample = pd.concat(in_samples, ignore_index=True)
    contrasts = contrast_metrics(summary, in_sample)
    predictions.to_csv(out / "predictions.csv", index=False)
    summary.to_csv(out / "model_metrics.csv", index=False)
    in_sample.to_csv(out / "in_sample_metrics.csv", index=False)
    contrasts.to_csv(out / "contrasts.csv", index=False)
    make_figures(contrasts, summary, out / "figures")
    coverage, key = render_report(out, merged, frames, summary, in_sample, contrasts, min_train)
    input_paths = [Path(panel_path), Path(a_path), Path(b_path)]
    if protocol_path is not None:
        input_paths.append(Path(protocol_path))
    inputs = {str(path): sha256(path) for path in input_paths}
    summary_json = {
        "status": "completed_retrospective_downstream_regression",
        "new_simulation_or_llm_calls": 0,
        "min_train": min_train,
        "outcomes": list(OUTCOMES),
        "horizons": [1, 2, 3],
        "models": MODELS,
        "contrasts": CONTRASTS,
        "prediction_rows": len(predictions),
        "model_metric_rows": len(summary),
        "contrast_rows": len(contrasts),
        "key_contrast_rows": len(key),
        "coverage_rows": len(coverage),
        "input_sha256": inputs,
        "limits": [
            "Current public vintages; not strict real-time forecasts.",
            "B is a small frozen-transfer sensitivity, not a new blind test.",
            "All comparisons are retained; positive results are not causal effects.",
        ],
    }
    write_json(out / "summary.json", summary_json)
    manifest = {
        **summary_json,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_sha256": {
            "scripts/analyze_sce_downstream_regression.py": sha256(ROOT / "scripts/analyze_sce_downstream_regression.py"),
            "studies/sce_inflation_expectations/evaluation/downstream_regression.py": sha256(ROOT / "studies/sce_inflation_expectations/evaluation/downstream_regression.py"),
        },
        "output_sha256": {str(path.relative_to(out)): sha256(path) for path in out.rglob("*") if path.is_file()},
    }
    write_json(out / "manifest.json", manifest)
    print(json.dumps({"status": "ok", "prediction_rows": len(predictions), "model_metric_rows": len(summary), "contrast_rows": len(contrasts), "out": str(out)}, ensure_ascii=False))
    return {"predictions": predictions, "summary": summary, "in_sample": in_sample, "contrasts": contrasts, "coverage": coverage, "key": key}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--a", type=Path, required=True)
    parser.add_argument("--b", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--min-train", type=int, default=36)
    parser.add_argument("--protocol", type=Path)
    args = parser.parse_args()
    run(args.panel, args.a, args.b, args.out, args.min_train, args.protocol)


if __name__ == "__main__":
    main()
