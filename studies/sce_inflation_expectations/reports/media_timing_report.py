"""Render an offline, aggregate-only report for the media timing experiment.

This module reads the already-frozen readout summary. It never opens cases,
fits Q9 again, or sends API requests.
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager, pyplot as plt
from matplotlib.lines import Line2D
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
ARM_ORDER = ["C0", "C1", "T0", "T1"]
ALL_FIVE_ORDER = ["O0", *ARM_ORDER]
MONTH_LABELS = {
    201905: "2019-05",
    202009: "2020-09",
    202106: "2021-06",
    202109: "2021-09",
    202112: "2021-12",
    202206: "2022-06",
    202312: "2023-12",
}
ARM_STYLES = {
    "O0": ("#6b7280", "X", ":"),
    "C0": ("#006da8", "o", "-"),
    "C1": ("#4f9ac2", "s", "--"),
    "T0": ("#d55e00", "D", "-"),
    "T1": ("#a64200", "^", "--"),
    "copy_previous": ("#222222", "*", "-"),
}
Q9_MONTH_FIELDS = [
    "month",
    "n",
    "human_center_pct",
    "model_center_pct",
    "q9_center_mae_pp",
    "q9_center_bias_pp",
    "cross_section_w1_pp",
    "cross_person_iqr_pp",
    "real_cross_person_iqr_pp",
    "individual_density_mean_mae_pp",
    "individual_density_iqr_mae_pp",
    "probability_tv_pct",
]
Q9_METRIC_FIELDS = [
    "q9_center_mae_pp",
    "q9_center_bias_pp",
    "cross_section_w1_pp",
    "cross_person_iqr_pp",
    "real_cross_person_iqr_pp",
    "individual_density_mean_mae_pp",
    "individual_density_iqr_mae_pp",
    "individual_density_iqr_mean_pp",
    "real_individual_density_iqr_mean_pp",
    "probability_tv_pct",
    "zero_deflation_rate",
    "person_mean_spearman",
]
Q8_FIELDS = [
    "q8_person_mae_pp",
    "q8_person_bias_pp",
    "q8_center_mae_pp",
    "q8_center_bias_pp",
    "q8_cross_section_w1_pp",
    "q8_person_spearman",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _pick(source: dict, fields: list[str]) -> dict:
    return {key: source[key] for key in fields if key in source}


def _clean_view(view: dict) -> dict:
    arms = {}
    for arm, values in view["arms"].items():
        arms[arm] = {
            "metrics": _pick(values["metrics"], Q9_METRIC_FIELDS),
            "q8": _pick(values["q8"], Q8_FIELDS),
            "mae_all_pp": values["mae_all_pp"],
            "mae_2021_pp": values["mae_2021_pp"],
            "mae_other_pp": values["mae_other_pp"],
            "rmse_pp": values["rmse_pp"],
            "monthly": [_pick(row, Q9_MONTH_FIELDS) for row in values["monthly"]],
            "repeats": {
                str(repeat): _pick(metrics, Q9_METRIC_FIELDS)
                for repeat, metrics in values["repeats"].items()
            },
        }
    return {
        "q9_person_months": view["q9_person_months"],
        "q8_person_months": view["q8_person_months"],
        "arms": arms,
    }


def _clean_comparison(row: dict) -> dict:
    fields = [
        "view",
        "n",
        "mae_change_pp",
        "mae_2021_change_pp",
        "w1_change_pp",
        "repeat_mae_changes",
        "leave_one_out_mae_changes",
        "per_month",
    ]
    return _pick(row, fields)


def _public_data(source: Path, independent_source: Path) -> dict:
    raw = json.loads(source.read_text(encoding="utf-8"))
    independent = json.loads(independent_source.read_text(encoding="utf-8"))
    required_views = (
        "all_five_common_support",
        "four_new_arms_common_support",
        "all_five_plus_copy_previous_same_support",
    )
    for key in ("months", "labels", "views", "comparisons", "date_groups", "design"):
        if key not in raw:
            raise ValueError(f"Readout is missing required field: {key}")
    for name in required_views:
        if name not in raw["views"]:
            raise ValueError(f"Readout is missing support view: {name}")
    if raw["views"]["four_new_arms_common_support"]["q9_person_months"] != 654:
        raise ValueError("Four-arm Q9 support changed; inspect before publishing")
    if raw["views"]["all_five_common_support"]["q9_person_months"] != 652:
        raise ValueError("Five-arm Q9 support changed; inspect before publishing")
    if raw["views"]["all_five_plus_copy_previous_same_support"]["q9_person_months"] != 532:
        raise ValueError("Five-arm plus baseline Q9 support changed; inspect before publishing")
    if independent.get("schema") != "sce_media_timing_independent_review/v1":
        raise ValueError("Independent bridge readout schema changed; inspect before publishing")
    bridge_source = independent["old_support_bridge"]
    bridge_all = bridge_source["exact_matched_support_contrasts"]["all_seven_c0_to_t0"]
    bridge_2021 = bridge_source["exact_matched_support_contrasts"]["selected_2021_c0_to_t0"]
    bridge_o0c0 = bridge_source["exact_matched_support_contrasts"]["all_seven_o0_to_c0"]
    old_original = bridge_source["old_q3_on_original_old_common_support"]
    old_matched = bridge_source["old_q3_on_exact_matched_support"]
    bridge_arms = bridge_source["v4_o0_c0_t0_on_exact_matched_support"]
    exposure = independent["warning_article_exposure"]["all_seven"]

    comparisons = {
        name: _clean_comparison(raw["comparisons"][name])
        for name in (
            "T0_minus_C0",
            "T1_minus_T0",
            "C1_minus_C0",
            "C0_minus_O0",
            "T0_minus_copy_previous",
        )
        if name in raw["comparisons"]
    }
    date_fields = [
        "group",
        "month",
        "n",
        "effective_n",
        "mean_T0_minus_C0_pp",
        "mean_T1_minus_T0_pp",
        "C0_center_mae_pp",
        "T0_center_mae_pp",
        "T1_center_mae_pp",
        "C0_individual_mae_pp",
        "T0_individual_mae_pp",
        "T1_individual_mae_pp",
    ]
    design = raw["design"]
    execution = design.get("execution", {})
    public_execution = {
        "new_requests_attempts": execution.get("new_requests", {}).get("attempts"),
        "new_requests_completed": execution.get("new_requests", {}).get("completed"),
        "new_requests_usable": execution.get("new_requests", {}).get("usable"),
        "repair_attempts": execution.get("repair_requests", {}).get("attempts"),
        "repair_usable": execution.get("repair_requests", {}).get("usable"),
        "new_request_technical_usable_after_overlay": execution.get("new_request_technical_usable_after_overlay"),
        "old_attempted_failures_retained": execution.get("old_attempted_failures_retained"),
        "reported_cost_usd": execution.get("total_reported_cost_usd"),
        "unknown_fee_reservation_usd": execution.get("unknown_fee_reservation_usd"),
    }
    return {
        "schema": "sce_media_timing_report_aggregate/v1",
        "status": raw.get("status"),
        "reporting_api_calls": raw.get("new_api_calls"),
        "reporting_q9_fits": raw.get("new_q9_fits"),
        "source_summary_sha256": _sha256(source),
        "independent_review_summary_sha256": _sha256(independent_source),
        "months": raw["months"],
        "month_labels": {str(m): MONTH_LABELS[int(m)] for m in raw["months"]},
        "labels": raw["labels"],
        "design": {
            "n_by_month": design.get("n_by_month"),
            "repeats": design.get("repeats"),
            "arms": design.get("arms"),
            "model": design.get("model"),
            "route": design.get("route"),
            "temperature": design.get("temperature"),
            "quantity_tiers": design.get("quantity_tiers"),
            "cpi_boost": design.get("cpi_boost"),
            "alarm_boost": design.get("alarm_boost"),
            "primary_support": design.get("primary_support"),
            "baseline_support": design.get("baseline_support"),
            "execution": public_execution,
        },
        "views": {name: _clean_view(raw["views"][name]) for name in required_views},
        "comparisons": comparisons,
        "date_groups": [_pick(row, date_fields) for row in raw["date_groups"]],
        "old_support_bridge": {
            "old_original_support_n": old_original["support_person_months"],
            "old_original_q3_mae_pp": old_original["metrics"]["mae_pp"],
            "exact_overlap_support_n": bridge_source["exact_old_q3_and_v4_c0_t0_matched_support_person_months"],
            "exact_overlap": {
                "O0_mae_pp": bridge_arms["O0"]["metrics"]["mae_pp"],
                "C0_mae_pp": bridge_arms["C0"]["metrics"]["mae_pp"],
                "T0_mae_pp": bridge_arms["T0"]["metrics"]["mae_pp"],
                "O0_support_n": bridge_arms["O0"]["support_person_months"],
            },
            "C0_to_T0_2021": {
                "support_n": bridge_2021["left"]["support_person_months"],
                "C0_mae_pp": bridge_2021["left"]["metrics"]["mae_pp"],
                "T0_mae_pp": bridge_2021["right"]["metrics"]["mae_pp"],
            },
            "exact_overlap_C0_to_T0_change_pp": bridge_all["delta_right_minus_left"]["mae_pp"],
            "exact_overlap_O0_to_C0_change_pp": bridge_o0c0["delta_right_minus_left"]["mae_pp"],
            "old_q3_exact_mae_pp": old_matched["metrics"]["mae_pp"],
        },
        "warning_article_exposure": {
            "T0_items": exposure["T0"]["personal_items"],
            "T0_warning_tagged_items": exposure["T0"]["alarming_items"],
            "T0_warning_tagged_share": exposure["T0"]["alarming_share"],
            "T1_items": exposure["T1"]["personal_items"],
            "T1_warning_tagged_items": exposure["T1"]["alarming_items"],
            "T1_warning_tagged_share": exposure["T1"]["alarming_share"],
        },
        "limitations": list(raw.get("limitations", [])),
    }


def _configure_plotting() -> None:
    font = ROOT / "outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf"
    if font.is_file():
        font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({
        "font.family": ["Times New Roman", "Kaiti SC", "STKaiti"],
        "font.size": 11,
        "axes.unicode_minus": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titleweight": "normal",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
    })


def _month_ticks(ax, months: list[int]) -> None:
    x = np.arange(len(months))
    ax.set_xticks(x, [MONTH_LABELS[int(month)] for month in months], rotation=0)
    ax.set_xlabel("目标调查月份（7 个离散选期，等距排列）")
    ax.grid(axis="y", alpha=0.18)


def _draw_arms(ax, data: dict, view: dict, months: list[int], field: str, arms: list[str] = ARM_ORDER) -> None:
    x = np.arange(len(months))
    for arm in arms:
        color, marker, line = ARM_STYLES[arm]
        rows = view["arms"][arm]["monthly"]
        by_month = {int(row["month"]): row for row in rows}
        ax.plot(
            x,
            [by_month[int(month)][field] for month in months],
            color=color,
            marker=marker,
            linestyle=line,
            linewidth=2.3,
            markersize=6,
            label=_arm_label(data, arm),
        )


def _arm_label(data: dict, arm: str) -> str:
    return data["labels"].get(arm, arm)


def _plot_monthly_mae(data: dict, path: Path) -> None:
    view = data["views"]["four_new_arms_common_support"]
    fig, ax = plt.subplots(figsize=(12.8, 5.7))
    _draw_arms(ax, data, view, data["months"], "q9_center_mae_pp")
    _month_ticks(ax, data["months"])
    ax.set_ylabel("Q9 群体中心 MAE（pp）")
    ax.set_title("逐月中心误差：2021 三期与 2022-06 走向不同", pad=16)
    ax.set_ylim(bottom=0)
    ax.legend(ncol=2, frameon=False, loc="upper left")
    fig.text(0.01, 0.005, "四组共同 Q9 支持：654 个人月；每个点是两遍等权后的该月 MAE。", fontsize=9, color="#52616b")
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_levels(data: dict, path: Path) -> None:
    view = data["views"]["four_new_arms_common_support"]
    months = data["months"]
    x = np.arange(len(months))
    fig, ax = plt.subplots(figsize=(12.8, 5.7))
    human_rows = {int(row["month"]): row for row in view["arms"]["C0"]["monthly"]}
    ax.plot(x, [human_rows[int(m)]["human_center_pct"] for m in months], color="#222222", marker="*",
            linestyle=":", linewidth=2.6, markersize=8, label="真人同支持中心")
    for arm in ARM_ORDER:
        color, marker, line = ARM_STYLES[arm]
        by_month = {int(row["month"]): row for row in view["arms"][arm]["monthly"]}
        ax.plot(x, [by_month[int(m)]["model_center_pct"] for m in months], color=color,
                marker=marker, linestyle=line, linewidth=2.0, markersize=5.5,
                label=_arm_label(data, arm))
    _month_ticks(ax, months)
    ax.set_ylabel("Q9 预期水平中心（%）")
    ax.set_title("模型与真人的 Q9 预期水平", pad=16)
    ax.set_ylim(bottom=0)
    ax.legend(ncol=3, frameon=False, loc="upper left")
    fig.text(0.01, 0.005, "同一 654 个人月；中心单位为年通胀预期百分比。月份不连续，连线仅连接实际选期。", fontsize=9, color="#52616b")
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_period_mae(data: dict, path: Path) -> None:
    view = data["views"]["four_new_arms_common_support"]
    arms = ARM_ORDER
    groups = [("2021 三个样本月", "mae_2021_pp"), ("其余四个样本月", "mae_other_pp")]
    x = np.arange(len(groups))
    width = 0.17
    fig, ax = plt.subplots(figsize=(10.8, 5.8))
    for i, arm in enumerate(arms):
        values = [view["arms"][arm][key] for _, key in groups]
        color = ARM_STYLES[arm][0]
        ax.bar(x + (i - 1.5) * width, values, width, color=color, label=_arm_label(data, arm))
        for xpos, value in zip(x + (i - 1.5) * width, values):
            ax.text(xpos, value + 0.012, f"{value:.3f}", ha="center", va="bottom", fontsize=8, rotation=90)
    ax.set_xticks(x, [label for label, _ in groups])
    ax.set_ylabel("Q9 群体中心 MAE（pp）")
    ax.set_title("分时期误差：2021 三期不是完整年度", pad=16)
    ax.set_ylim(bottom=0, top=max(view["arms"][arm][key] for arm in arms for _, key in groups) * 1.24)
    ax.grid(axis="y", alpha=0.18)
    ax.legend(ncol=2, frameon=False)
    fig.text(0.01, 0.005, "四组共同 Q9 支持：654 个人月。2021 = 2021-06/09/12；其余 = 2019-05、2020-09、2022-06、2023-12。", fontsize=9, color="#52616b")
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_auxiliary(data: dict, path: Path) -> None:
    view = data["views"]["four_new_arms_common_support"]
    labels = [_arm_label(data, arm) for arm in ARM_ORDER]
    colors = [ARM_STYLES[arm][0] for arm in ARM_ORDER]
    w1 = [view["arms"][arm]["metrics"]["cross_section_w1_pp"] for arm in ARM_ORDER]
    iqr = [view["arms"][arm]["metrics"]["cross_person_iqr_pp"] for arm in ARM_ORDER]
    human_iqr = view["arms"]["C0"]["metrics"]["real_cross_person_iqr_pp"]
    q8_mae = [view["arms"][arm]["q8"]["q8_center_mae_pp"] for arm in ARM_ORDER]
    fig, axes = plt.subplots(2, 2, figsize=(13.0, 8.3))
    x = np.arange(len(ARM_ORDER))
    axes[0, 0].bar(x, w1, color=colors, width=0.62)
    axes[0, 0].set_xticks(x, labels, rotation=12, ha="right")
    axes[0, 0].set_ylabel("跨人 W1（pp）")
    axes[0, 0].set_title("跨人分布距离 · 654 个 Q9 人月")
    axes[0, 0].grid(axis="y", alpha=0.18)
    axes[0, 0].set_ylim(bottom=0)
    axes[0, 1].bar(x, iqr, color=colors, width=0.62)
    axes[0, 1].axhline(human_iqr, color="#222222", linestyle="--", linewidth=1.8,
                       label=f"真人同支持 IQR {human_iqr:.3f} pp")
    axes[0, 1].set_xticks(x, labels, rotation=12, ha="right")
    axes[0, 1].set_ylabel("跨人 Q9 中心 IQR（pp）")
    axes[0, 1].set_title("模拟分布宽度 · 654 个 Q9 人月")
    axes[0, 1].grid(axis="y", alpha=0.18)
    axes[0, 1].set_ylim(bottom=0)
    axes[0, 1].legend(frameon=False, fontsize=9)

    for i, arm in enumerate(ARM_ORDER):
        color = ARM_STYLES[arm][0]
        y1 = view["arms"][arm]["repeats"]["1"]["q9_center_mae_pp"]
        y2 = view["arms"][arm]["repeats"]["2"]["q9_center_mae_pp"]
        axes[1, 0].plot([i - 0.04, i + 0.04], [y1, y2], color=color, linewidth=2.0, alpha=0.8)
        axes[1, 0].scatter([i - 0.04], [y1], color=color, marker="o", s=50, zorder=3)
        axes[1, 0].scatter([i + 0.04], [y2], color=color, marker="s", s=50, zorder=3)
    axes[1, 0].set_xticks(x, labels, rotation=12, ha="right")
    axes[1, 0].set_ylabel("该遍 Q9 中心 MAE（pp）")
    axes[1, 0].set_title("两遍结果 · 不是误差区间")
    axes[1, 0].grid(axis="y", alpha=0.18)
    axes[1, 0].set_ylim(bottom=0)
    axes[1, 0].legend(handles=[
        Line2D([0], [0], color="#333333", marker="o", linestyle="None", label="第 1 遍"),
        Line2D([0], [0], color="#333333", marker="s", linestyle="None", label="第 2 遍"),
    ], frameon=False, fontsize=9)

    axes[1, 1].bar(x, q8_mae, color=colors, width=0.62)
    axes[1, 1].set_xticks(x, labels, rotation=12, ha="right")
    axes[1, 1].set_ylabel("Q8 中心 MAE（pp）")
    axes[1, 1].set_title("独立 Q8 指标 · 664 个 Q8 人月")
    axes[1, 1].grid(axis="y", alpha=0.18)
    axes[1, 1].set_ylim(bottom=0)

    fig.suptitle("辅助分布、重复生成与 Q8（置于核心 MAE 之后）", y=0.995)
    fig.text(0.01, 0.005, "来源：2026-10-25 聚合读数。W1 越低表示距真人分布越小；真人 IQR 仅作宽度参照。两次生成不是新增真人样本。", fontsize=9, color="#52616b")
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _table(headers: list[str], rows: list[list[object]], classes: str = "") -> str:
    header = "".join(f"<th>{html.escape(str(value))}</th>" for value in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f'<div class="table-wrap"><table class="{classes}"><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>'


def _f(value: float | int | None, digits: int = 3) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}"


def _percent_change(new: float, baseline: float) -> float:
    return (new - baseline) / baseline * 100


def _html(data: dict, out: Path) -> str:
    main = data["views"]["four_new_arms_common_support"]
    old = data["views"]["all_five_common_support"]
    baseline = data["views"]["all_five_plus_copy_previous_same_support"]
    c0, c1, t0, t1 = (main["arms"][arm] for arm in ARM_ORDER)
    months = data["months"]

    main_rows = []
    for arm in ARM_ORDER:
        x = main["arms"][arm]
        main_rows.append([
            _arm_label(data, arm),
            _f(x["mae_all_pp"]),
            _f(x["mae_2021_pp"]),
            _f(x["mae_other_pp"]),
            _f(x["rmse_pp"]),
            _f(x["metrics"]["cross_section_w1_pp"]),
            _f(x["metrics"]["cross_person_iqr_pp"]),
        ])
    monthly_rows = []
    for i, month in enumerate(months):
        monthly_rows.append([
            MONTH_LABELS[int(month)],
            *[_f(main["arms"][arm]["monthly"][i]["q9_center_mae_pp"]) for arm in ARM_ORDER],
            str(main["arms"]["C0"]["monthly"][i]["n"]),
        ])
    old_rows = []
    for arm in ALL_FIVE_ORDER:
        x = old["arms"][arm]
        old_rows.append([_arm_label(data, arm), _f(x["mae_all_pp"]), _f(x["mae_2021_pp"]), _f(x["mae_other_pp"])])
    baseline_rows = []
    for arm in ("T0", "copy_previous"):
        x = baseline["arms"][arm]
        baseline_rows.append([_arm_label(data, arm), _f(x["mae_all_pp"]), _f(x["mae_2021_pp"]),
                              _f(x["mae_other_pp"]), _f(x["metrics"]["cross_section_w1_pp"]),
                              _f(x["metrics"]["cross_person_iqr_pp"])])
    repeat_rows = [[_arm_label(data, arm), *[
        _f(main["arms"][arm]["repeats"][str(rep)]["q9_center_mae_pp"]) for rep in (1, 2)
    ]] for arm in ARM_ORDER]
    q8_rows = [[_arm_label(data, arm), _f(main["arms"][arm]["q8"]["q8_center_mae_pp"])] for arm in ARM_ORDER]
    date_rows = []
    group_label = {"earlier": "个人截止早于旧共同截止", "same": "个人截止与旧共同截止同日", "later": "个人截止晚于旧共同截止"}
    for row in sorted(data["date_groups"], key=lambda item: (int(item["month"]), ("earlier", "same", "later").index(item["group"]))):
        date_rows.append([
            MONTH_LABELS[int(row["month"])],
            group_label[row["group"]],
            str(int(row["n"])),
            _f(row["effective_n"], 1),
            _f(row["mean_T0_minus_C0_pp"]),
            _f(row["C0_center_mae_pp"]),
            _f(row["T0_center_mae_pp"]),
            _f(row["T1_center_mae_pp"]),
        ])

    c0_mae, t0_mae = c0["mae_all_pp"], t0["mae_all_pp"]
    c0_2021, t0_2021 = c0["mae_2021_pp"], t0["mae_2021_pp"]
    t1_runs = [main["arms"]["T1"]["repeats"][str(rep)]["q9_center_mae_pp"] for rep in (1, 2)]
    y2022 = next(row for row in data["comparisons"]["T0_minus_C0"]["per_month"] if int(row["month"]) == 202206)
    timing_202206 = [r for r in data["date_groups"] if int(r["month"]) == 202206]
    early_202206 = next(r for r in timing_202206 if r["group"] == "earlier")
    late_202206 = next(r for r in timing_202206 if r["group"] == "later")
    leave_202206 = data["comparisons"]["T0_minus_C0"]["leave_one_out_mae_changes"]["202206"]

    design = data["design"]
    execution = design["execution"]
    bridge = data["old_support_bridge"]
    exposure = data["warning_article_exposure"]
    n_better_months = sum(row["mae_change_pp"] < 0 for row in data["comparisons"]["T0_minus_C0"]["per_month"])
    data_source = f"2026-10-25 聚合读数 · SHA-256 {data['source_summary_sha256']}"
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>个人日期 × 警示新闻：七期结果</title>
<style>
:root{{--ink:#202631;--muted:#52616b;--blue:#006da8;--orange:#d55e00;--paper:#f5f4f0;--line:#d3d9de;--white:#fff}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font:18px/1.72 "Times New Roman","Kaiti SC","STKaiti",serif}}
main{{max-width:1180px;margin:auto;padding:30px 34px 60px}} h1{{font-size:32px;line-height:1.35;margin:.15em 0 .45em}} h2{{font-size:24px;line-height:1.45;margin:42px 0 12px;padding-top:16px;border-top:1px solid var(--line)}} h3{{font-size:20px;margin:24px 0 8px}}
p{{margin:10px 0}} .meta,.caption{{font-size:15px;color:var(--muted)}} .lede{{font-size:20px;max-width:970px}} .callout{{border-left:5px solid var(--orange);background:var(--white);padding:14px 20px;margin:20px 0 24px}} .callout p{{margin:4px 0}}
.kpis{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:22px 0}} .kpi{{background:var(--white);padding:15px 17px;border-top:3px solid var(--blue)}} .kpi:nth-child(2){{border-top-color:#4f9ac2}} .kpi:nth-child(3){{border-top-color:var(--orange)}} .kpi b{{display:block;font:600 25px/1.25 "Times New Roman","Kaiti SC","STKaiti",serif}} .kpi span{{font-size:15px;color:var(--muted)}}
figure{{margin:20px 0 30px;background:var(--white);padding:12px 14px 8px}} figure img{{display:block;width:100%;height:auto}} figcaption{{margin-top:6px;font-size:15px;color:var(--muted)}} .table-wrap{{overflow-x:auto;margin:14px 0 22px}} table{{border-collapse:collapse;width:100%;background:var(--white);font-size:16px;min-width:650px}} th,td{{padding:8px 10px;border-bottom:1px solid #e0e4e7;text-align:right;white-space:nowrap}} th{{background:#eaf0f3;font-weight:600}} th:first-child,td:first-child{{text-align:left}} .note{{font-size:15px;color:var(--muted)}} details{{margin:18px 0}} summary{{cursor:pointer;font-weight:600}} .tag{{display:inline-block;border:1px solid var(--line);padding:2px 9px;font-size:14px;color:var(--muted);margin-right:6px}} ul{{padding-left:1.35em}} li{{margin:7px 0}} code{{font-family:monospace;font-size:.9em}} a{{color:var(--blue)}}
@media(max-width:760px){{main{{padding:20px 16px 40px}}body{{font-size:17px}}h1{{font-size:28px}}.kpis{{grid-template-columns:1fr}}table{{font-size:15px}}}}
</style></head><body><main>
<p class="meta">水上挽月 · 2026-10-25 · 已封存聚合结果的离线整理 · 本报告：0 新增 API / 0 次 Q9 重拟</p>
<h1>个人日期口径与警示权重：七个已看过月份的 Q9 结果</h1>
<p class="lede">T0 与 T1 都是可继续比较的工作候选：T0 的七期 MAE 最低、两遍相对 C0 都改善，但 2021 三期误差变大；T1 相对 C0 的总体与 2021 MAE 都较低，却在两遍间出现反向结果。现有证据支持并列取舍，不支持把警示权重一概打开或一概关掉。</p>
<div class="kpis"><div class="kpi"><b>{_f(c0_mae)} → {_f(t0_mae)} pp</b><span>七期 MAE · C0 → T0 · 654 个共同个人月（{_percent_change(t0_mae,c0_mae):+.1f}%）</span></div>
<div class="kpi"><b>{_f(c0_2021)} → {_f(t0_2021)} pp</b><span>2021-06/09/12 三期 MAE · C0 → T0</span></div>
<div class="kpi"><b>{_f(t1_runs[0])} / {_f(t1_runs[1])} pp</b><span>T1 两遍 MAE · 方向跨遍次不一致</span></div></div>
<div class="callout"><p><b>暂行取舍（待主代理复核）：</b>T0 可作为“总体中心 MAE 与两遍方向一致”的候选；T1 可作为“总体 MAE 与 2021 三期同时低于 C0”的平衡候选。T1 的两遍相对 C0 一好一坏，不能称为稳定或显著。继续时可把 T0/T1 一并带入预先锁定的独立日期复核，再按用户的渐进采纳原则权衡核心收益与可解释代价。</p><p>这里比较的是模拟输入配置，不是对真人暴露或恐惧的因果结论，也不改变 A82/B11 或旧报告。七个目标月都已被此前研究查看，不构成独立时间验证。</p></div>

<h2>1. 比较设计与支持范围</h2>
<p>本轮包含五个视图。O0 是旧 Q3 原始回答；C0 使用旧共同截止，只修复 General news 的先后行；C1 在 C0 上把警示新闻权重设为 2 倍；T0 将个人完成日期换算为纽约时间前一日 23:59:59，并按该日筛选各类 E 信息；T1 在 T0 上再加 2×警示权重。四组 C0/C1/T0/T1 都保留每人 4/8/16/32 篇档位和 CPI 相关度 1.5 倍，其余配置固定。</p>
<p>个人日期由调查完成日推算；问卷没有回答时刻，因此“前一日末”是保守重建约定，不是精确的回答时点。T0 相对 C0 同时改变可见新闻、食品统计、政策和信心信息，不能把这组差异单独称为新闻因果效应。警示权重改变的是可得个人新闻池内的抽样分数，不是实际曝光概率或受访者恐惧程度。</p>
<p>目标月为 {', '.join(MONTH_LABELS[int(m)] for m in months)}。每月原名单 96 人；2022-06 有一名完成日期落到 2022-07-01，按预先规则排除，故七期共 671 个入选个人月。新组各有两遍随机生成；两遍不是额外真人样本。</p>
<p><b>主比较：</b>四个新组在同一批 654 个有效 Q9 个人月、664 个有效 Q8 个人月上比较。O0 五组参照另用 652 个 Q9 / 662 个 Q8 个人月。T0 与照抄本人上期的六组基线视图用 532 个 Q9 / 547 个 Q8 个人月。支持口径不同，不能把各表中的数字直接相减。旧 MAE 审阅报告的 Q3=0.439pp 是 641 个人月，不能作为本轮 C0/T0 的直接基线。</p>
<p><b>中心 MAE 定义：</b>每人十档 Q9 概率按冻结计分器转换为预期水平；在每个目标月，用设计权重计算模型与真人同支持中心，再取两者差的绝对值。最后对“目标月 × 生成遍次”单元等权平均。它不是个人平均误差；两遍也不是新增受访者。Q8 单独统计。</p>
<p class="note">本轮模型：DeepSeek V3.2 / SiliconFlow FP8，温度 0.5；报告整理未调用 API、未重拟 Q9。底层试验有 4,096 个新增请求；53 次技术补跑全部恢复为可用结果，旧档案中 6 个逻辑缺失仍保留。已报告 API 费用 ${execution['reported_cost_usd']:.6f}，另列未知费用预留 ${execution['unknown_fee_reservation_usd']:.6f}。</p>

<h2>2. 首先看总体与 2021 三期</h2>
{_table(['组别（共同 654 人月）','七期 MAE（pp）','2021 三期 MAE（pp）','其余四期 MAE（pp）','RMSE（pp）','W1（pp）','跨人 IQR（pp）'],main_rows)}
<p>T0 相对 C0 的七期 MAE 下降 {_f(abs(t0_mae-c0_mae))}pp（约 7.3%），但 2021 三期从 {_f(c0_2021)} 升到 {_f(t0_2021)}pp；其余四个样本月则从 {_f(c0['mae_other_pp'])} 降到 {_f(t0['mae_other_pp'])}pp。T0 在 {n_better_months}/7 个离散月的 MAE 较低，2022-06 单月下降 {_f(abs(y2022['mae_change_pp']))}pp；删去该月后七期其余 MAE 差为 +{_f(leave_202206)}pp。删月数值说明收益集中，不能抹去全样本上已观察到的平均改善。2021 仅指 6、9、12 月，不能外推成完整年份。</p>
<figure><img src="monthly_q9_mae.png" alt="C0、C1、T0、T1四组在七个离散月份的Q9中心MAE折线图"><figcaption>图 1 · 逐月 Q9 群体中心 MAE（pp）。横轴是七个等距排列的离散目标月，折线只连接实际运行月份。共同支持：654 个个人月。来源：{data_source}。</figcaption></figure>
{_table(['目标月','C0 MAE（pp）','C1 MAE（pp）','T0 MAE（pp）','T1 MAE（pp）','共同有效 n'],monthly_rows)}

<h2>3. 预期水平与真人同支持中心</h2>
<p>下图报告模型与真人 Q9 中心水平，不是误差指标。2022-06 的 C0 中心为 {_f(main['arms']['C0']['monthly'][5]['model_center_pct'])}%，T0 为 {_f(main['arms']['T0']['monthly'][5]['model_center_pct'])}%，真人同支持中心为 {_f(main['arms']['C0']['monthly'][5]['human_center_pct'])}%。T0 相对 C0 的该月 MAE 变化为 {_f(y2022['mae_change_pp'])}pp。</p>
<figure><img src="monthly_q9_level.png" alt="四实验组与真人同支持Q9预期水平中心折线图"><figcaption>图 2 · Q9 预期水平中心（%）。模型与真人使用同一 654 个个人月；月份仍为离散选期。来源：{data_source}。</figcaption></figure>
<figure><img src="period_mae.png" alt="四实验组在2021三个样本月和其他四个月的MAE分组柱状图"><figcaption>图 3 · 2021 三个样本月与其余四个样本月的等权 MAE（pp），四组共同支持 654 个个人月。分组不代表完整年度。来源：{data_source}。</figcaption></figure>

<h2>4. 个人日期的变化集中在哪些人群？</h2>
<p>按个人截止日期相对旧共同截止的早晚作描述性拆分，2022-06 早截止组有 {int(early_202206['n'])} 人、有效样本量 {float(early_202206['effective_n']):.1f}；该组模型个人预期均值的 T0−C0 平均差为 {_f(early_202206['mean_T0_minus_C0_pp'])}pp，组内中心 MAE 从 {_f(early_202206['C0_center_mae_pp'])} 降到 {_f(early_202206['T0_center_mae_pp'])}pp。晚截止组有 {int(late_202206['n'])} 人、有效样本量 {float(late_202206['effective_n']):.1f}，预测均值差为 {_f(late_202206['mean_T0_minus_C0_pp'])}pp，中心 MAE 从 {_f(late_202206['C0_center_mae_pp'])} 到 {_f(late_202206['T0_center_mae_pp'])}pp。</p>
<p>这与“较早回答者在旧共同截止下可能被分配到后来发布的信息，个人日期口径会削弱这类错配”的解释一致；但不能确认单一机制：T0 同时按时间筛选新闻、食品、政策与信心信息，分组中心 MAE 也不能相加还原总体 MAE。2021-06 和 2021-09 的晚截止组 T0−C0 个人均值差分别为 {_f(next(r for r in data['date_groups'] if r['month']==202106 and r['group']=='later')['mean_T0_minus_C0_pp'])}pp 与 {_f(next(r for r in data['date_groups'] if r['month']==202109 and r['group']=='later')['mean_T0_minus_C0_pp'])}pp；都不是正值，说明“晚截止必然抬高预期”也不受这两组数据支持。</p>
<details><summary>展开：全部日期组的 n、有效 n 与组内描述</summary>
<p class="note">同日组样本极少；组内 MAE 是各自子集描述值，不可相加为总体指标，也不用于推断因果方向。</p>
{_table(['月份','个人截止相对旧共同截止','n','有效 n','T0−C0 个人预期均值差（pp）','C0 中心 MAE（pp）','T0 中心 MAE（pp）','T1 中心 MAE（pp）'],date_rows)}
</details>

<h2>5. 警示权重的证据与边界</h2>
<p>在同一 654 人月上，C1 相对 C0 的七期 MAE 几乎不变（{_f(c1['mae_all_pp'])} vs {_f(c0['mae_all_pp'])}pp），2021 三期则略低（{_f(c1['mae_2021_pp'])} vs {_f(c0['mae_2021_pp'])}pp）。加在个人日期口径上的 T1 相对 C0，七期 MAE 为 {_f(t1['mae_all_pp'])} vs {_f(c0['mae_all_pp'])}pp，2021 三期为 {_f(t1['mae_2021_pp'])} vs {_f(c0['mae_2021_pp'])}pp；两项都较低。T1 相对 T0 的七期 MAE 高 {_f(t1['mae_all_pp']-t0['mae_all_pp'])}pp，但 2021 三期低 {_f(t1['mae_2021_pp']-t0['mae_2021_pp'])}pp。因而 T0 与 T1 体现的是核心指标间的不同取舍。</p>
<p>警示标签新闻在 T0 的所选个人新闻条目中占 {_f(100*exposure['T0_warning_tagged_share'],1)}%（{exposure['T0_warning_tagged_items']:,}/{exposure['T0_items']:,}）；T1 占 {_f(100*exposure['T1_warning_tagged_share'],1)}%（{exposure['T1_warning_tagged_items']:,}/{exposure['T1_items']:,}）。2×设置改变了所选警示标签条目比例，但标签描述文章内容，不代表真人实际阅读、恐惧或因果暴露；选择更多警示内容也不保证预测水平单调上升。</p>
<p>逐遍比较更谨慎：在 654 个四组共同个人月上，C0 两遍 MAE 为 {_f(c0['repeats']['1']['q9_center_mae_pp'])}/{_f(c0['repeats']['2']['q9_center_mae_pp'])}pp；T0 为 {_f(t0['repeats']['1']['q9_center_mae_pp'])}/{_f(t0['repeats']['2']['q9_center_mae_pp'])}pp，两遍都较低。T1 为 {_f(t1['repeats']['1']['q9_center_mae_pp'])}/{_f(t1['repeats']['2']['q9_center_mae_pp'])}pp，相对 C0 的方向一好一坏；单次两遍无法表明稳定性。</p>
{_table(['组别','第 1 遍 MAE（pp）','第 2 遍 MAE（pp）'],repeat_rows)}
<p>两遍 MAE 变化可以反映随机生成对当前结果的敏感程度，但不能充当统计区间；在新时间段作出取舍前应重复检查，而不是按目标月挑不同实验组拼出最佳曲线。</p>

<h2>6. 辅助：分布代价与 Q8</h2>
<p>W1 和跨人 IQR 放在核心 MAE 与 2021 分组结果之后阅读。四组主支持真人跨人 IQR 为 {_f(main['arms']['C0']['metrics']['real_cross_person_iqr_pp'])}pp，模型约 {_f(min(main['arms'][a]['metrics']['cross_person_iqr_pp'] for a in ARM_ORDER))}–{_f(max(main['arms'][a]['metrics']['cross_person_iqr_pp'] for a in ARM_ORDER))}pp，模型分布仍明显偏窄。W1 与 IQR回答不同问题；Q8 独立指标使用 664 个共同个人月。</p>
<figure><img src="distribution_auxiliary.png" alt="四组W1、跨人IQR、两遍MAE和Q8中心MAE的四面板辅助图"><figcaption>图 4 · 辅助指标：左上跨人 W1（pp），右上跨人 Q9 中心 IQR（pp，虚线为真人同支持），左下两遍 Q9 中心 MAE（pp，圆点/方点为第 1/2 遍），右下 Q8 中心 MAE（pp，664 个 Q8 人月）。来源：{data_source}。W1 越低表示和真人分布距离越小；IQR 比较宽度。两遍不是误差区间。</figcaption></figure>
{_table(['组别','Q8 中心 MAE（pp）','Q8 支持'],[[row[0],row[1],str(main['q8_person_months'])] for row in q8_rows])}

<h2>7. O0 修复参照与照抄上期基线（另支持）</h2>
<p>O0/C0 只在 652 个五组共同 Q9 支持上比较；C0−O0 MAE 为 {_f(data['comparisons']['C0_minus_O0']['mae_change_pp'])}pp。这个对照用于呈现 General 先后行修复后的差异，不把 O0 改写成重跑结果。</p>
{_table(['组别（五组共同支持 652）','七期 MAE（pp）','2021 三期 MAE（pp）','其余四期 MAE（pp）'],old_rows)}
<p>照抄本人上期的比较只覆盖有真实上期可用的子集。下表只用五组加 baseline 的 532 个共同 Q9 个人月；T0 的 {_f(baseline['arms']['T0']['mae_all_pp'])}pp 与 copy_previous 的 {_f(baseline['arms']['copy_previous']['mae_all_pp'])}pp 不可和主表 654 支持上的结果直接横比。四组 C0/T0/copy_previous 主配对支持另有 534 个个人月。</p>
{_table(['组别（六组共同支持 532）','七期 MAE（pp）','2021 三期 MAE（pp）','其余四期 MAE（pp）','W1（pp）','跨人 IQR（pp）'],baseline_rows)}

<h2>8. 与旧 Q3 结果桥接：精确重叠支持 640</h2>
<p>旧报告的 Q3=0.4388pp 使用 641 人月，新四组主表使用 654 人月，两数不能直接相减。对两轮数据按同一批重叠个人月重新对齐后，精确共同支持为 {bridge['exact_overlap_support_n']} 人月：旧 Q3/O0 为 {_f(bridge['exact_overlap']['O0_mae_pp'])}pp，C0 为 {_f(bridge['exact_overlap']['C0_mae_pp'])}pp，T0 为 {_f(bridge['exact_overlap']['T0_mae_pp'])}pp。这个同支持桥接显示七期平均 MAE 从 O0 到 T0 下降约 {_f(bridge['exact_overlap']['O0_mae_pp']-bridge['exact_overlap']['T0_mae_pp'])}pp；相同 2021 三期子集中（{bridge['C0_to_T0_2021']['support_n']} 人月），C0 {_f(bridge['C0_to_T0_2021']['C0_mae_pp'])}pp → T0 {_f(bridge['C0_to_T0_2021']['T0_mae_pp'])}pp，仍然变差。</p>
<p>这里可说七期平均观察到改善，但七个此前看过的月份不能证明跨期稳定。旧支持原始 641 人月的数值仅作历史参照；不得把它与本轮 654 人月直接比较。</p>

<h2>9. 下一步配置取舍</h2>
<ul><li>支持口径、两遍读数、日期组与历史桥接已完成独立复核；本页不自动修改默认配置。</li>
<li>下一步选择 T0 或 T1 中的一个工作候选，开展完整 A 时间范围复核，并保留本轮两者的对照；先明确总体 MAE、2021 上行期与 2022-06 高估期的权衡，不再扩展参数搜索。完整 A 范围已有结果可见，不能称新的独立盲测。</li>
<li>不按月份挑赢家拼接成绩。可以保留 T0 的总体与跨遍次信号，也可以把 T1 作为兼顾总体和 2021 的工作候选；取舍依据既定核心目标与可接受代价；两遍不一致作为限制保留，独立窗口验证有条件时另做，不把它变成当前收尾的新门槛。</li></ul>
<p class="note">来源：{data_source}。数据仅含聚合评价字段；没有嵌入个人编号、位置列表、案例或原始提示。结果限定在七个此前已查看的目标月，是探索性机制证据，不是独立时间验证，不作因果断言。</p>
</main></body></html>'''


def _canvas(data: dict) -> str:
    # Keep the Canvas payload on a strict whitelist of aggregate values.
    payload = {
        "months": data["months"],
        "labels": data["labels"],
        "source": data["source_summary_sha256"],
        "bridgeSource": data["independent_review_summary_sha256"],
        "views": {
            name: data["views"][name]
            for name in (
                "four_new_arms_common_support",
                "all_five_common_support",
                "all_five_plus_copy_previous_same_support",
            )
        },
        "comparisons": {
            name: data["comparisons"][name]
            for name in ("T0_minus_C0", "T1_minus_T0", "C1_minus_C0", "C0_minus_O0", "T0_minus_copy_previous")
        },
        "date_groups": data["date_groups"],
        "old_support_bridge": data["old_support_bridge"],
        "warning_article_exposure": data["warning_article_exposure"],
        "design": data["design"],
    }
    embedded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f'''import {{H1,H2,Text,Stack,Grid,Stat,Table,LineChart,BarChart,Callout,Divider,useHostTheme}} from "cursor/canvas";
const D={embedded};
const A=["C0","C1","T0","T1"] as const;
const V=D.views.four_new_arms_common_support;
const date=(m:number)=>String(m).slice(0,4)+"-"+String(m).slice(4);
const f=(n:number)=>n.toFixed(3);
const pct=(n:number,d:number)=>((n-d)/d*100).toFixed(1)+"%";
const rows=(field:"mae_all_pp"|"mae_2021_pp"|"mae_other_pp")=>A.map(a=>[D.labels[a],f(V.arms[a][field])]);
const monthly=(a:typeof A[number],k:string)=>V.arms[a].monthly.map((r:any)=>r[k]);
const run1=A.map(a=>V.arms[a].repeats["1"].q9_center_mae_pp);
const run2=A.map(a=>V.arms[a].repeats["2"].q9_center_mae_pp);
const w=D.views.all_five_common_support;
const b=D.views.all_five_plus_copy_previous_same_support;
export default function MediaTimingResults(){{
 const t=useHostTheme();
 const c0=V.arms.C0; const t0=V.arms.T0; const c1=V.arms.C1; const t1=V.arms.T1;
 return <Stack gap={{18}} style={{{{padding:24,maxWidth:1180,margin:"0 auto",fontFamily:'"Times New Roman","Kaiti SC","STKaiti",serif',color:t.text.primary,background:t.bg.editor}}}}>
  <Text size="small" tone="secondary">SCE · 2026-10-25 · 聚合结果离线报告 · 0 新增 API / 0 次 Q9 重拟</Text>
  <H1>个人日期口径与警示权重：七个已看过月份的 Q9 结果</H1>
  <Text>T0 与 T1 都是可继续比较的候选：T0 总体 MAE 最低、两遍相对 C0 都改善，但 2021 三期更差；T1 相对 C0 的总体与 2021 MAE 都较低，不过两遍相对 C0 一好一坏。结果只适用于这些此前已看过的离散月份。</Text>
  <Grid columns={{3}} gap={{12}}>
   <Stat label="七期 MAE · C0 → T0 · 654 人月" value={{`${{f(c0.mae_all_pp)}} → ${{f(t0.mae_all_pp)}} pp · ${{pct(t0.mae_all_pp,c0.mae_all_pp)}}`}} />
   <Stat label="2021 三期 MAE · C0 → T0" value={{`${{f(c0.mae_2021_pp)}} → ${{f(t0.mae_2021_pp)}} pp`}} />
   <Stat label="T1 两遍 MAE" value={{`${{f(t1.repeats["1"].q9_center_mae_pp)}} / ${{f(t1.repeats["2"].q9_center_mae_pp)}} pp`}} />
  </Grid>
  <Callout tone="info" title="候选并列：待主代理复核">可保留 T0 作为总体 MAE 与两遍一致性的候选，也可将 T1 作为兼顾总体与 2021 的候选。T1 两遍一好一坏，不代表稳定或显著。建议在未参与本轮诊断的日期上并列复核；不自动全面打开或关掉警示权重。</Callout>
  <H2>四组主支持：整体与分时期 MAE（pp）</H2>
  <Table headers={{["组别","全部七期","2021 三期","其余四期"]}} rows={{A.map(a=>[D.labels[a],f(V.arms[a].mae_all_pp),f(V.arms[a].mae_2021_pp),f(V.arms[a].mae_other_pp)])}} columnAlign={{["left","right","right","right"]}} />
  <Text size="small" tone="secondary">主比较：654 个有效 Q9 个人月、664 个 Q8 个人月。2021 = 2021-06/09/12；其余四期是 2019-05、2020-09、2022-06、2023-12。七期不是连续时间序列。</Text>
  <H2>逐月 Q9 群体中心 MAE</H2>
  <Text size="small" tone="secondary">横轴：七个离散目标月（等距）；纵轴：该月 Q9 中心 MAE（pp）。每点是两遍等权后的月度值。来源：2026-10-25 聚合读数 · SHA-256 ${{D.source}}。</Text>
  <LineChart categories={{D.months.map(date)}} series={{A.map((a:any)=>({{name:D.labels[a],data:monthly(a,"q9_center_mae_pp"),tone:a==="C0"?"info":a==="T0"?"warning":undefined}}))}} height={{330}} valueSuffix=" pp" />
  <H2>模型与真人 Q9 预期水平中心</H2>
  <Text size="small" tone="secondary">横轴：目标月；纵轴：预期水平中心（%）。黑色真人系列与四组模型使用同一 654 个人月。来源：同一聚合读数与七个月份。</Text>
  <LineChart categories={{D.months.map(date)}} series={{[
   {{name:"真人同支持中心",data:monthly("C0","human_center_pct"),tone:"neutral"}},
   ...A.map((a:any)=>({{name:D.labels[a],data:monthly(a,"model_center_pct"),tone:a==="C0"?"info":a==="T0"?"warning":undefined}}))
  ]}} height={{320}} valueSuffix="%" />
  <H2>2021 三期与其余四期</H2>
  <Text size="small" tone="secondary">纵轴：Q9 群体中心 MAE（pp）；2021 指 6、9、12 月，不是完整年份。来源：同一聚合读数。</Text>
  <BarChart categories={{A.map((a:any)=>D.labels[a])}} series={{[
   {{name:"2021 三个样本月",data:A.map((a:any)=>V.arms[a].mae_2021_pp),tone:"info"}},
   {{name:"其余四个样本月",data:A.map((a:any)=>V.arms[a].mae_other_pp),tone:"warning"}}
  ]}} height={{300}} valueSuffix=" pp" showValues />
  <Text size="small" tone="secondary">四组共同 Q9 支持：654 个个人月；月份等权。</Text>
  <H2>逐遍 MAE：两遍不是误差区间</H2>
  <Text size="small" tone="secondary">两次生成的 MAE（pp）。T0 相对 C0 两遍都改善；T1 两遍为 ${{f(t1.repeats["1"].q9_center_mae_pp)}} / ${{f(t1.repeats["2"].q9_center_mae_pp)}}，相对 C0 一好一坏。两遍不是置信区间。</Text>
  <Table headers={{["组别","第 1 遍 MAE（pp）","第 2 遍 MAE（pp）"]}} rows={{A.map(a=>[D.labels[a],f(V.arms[a].repeats["1"].q9_center_mae_pp),f(V.arms[a].repeats["2"].q9_center_mae_pp)])}} />
  <H2>辅助：跨人分布距离与宽度</H2>
  <Text size="small" tone="secondary">W1 和跨人 IQR 用来解释分布差异，放在中心 MAE 之后；数值单位均为 pp。来源：2026-10-25 聚合读数。</Text>
  <Grid columns={{"1fr 1fr"}} gap={{18}}>
   <Stack gap={{8}}><Text weight="semibold">跨人 W1（pp）</Text><BarChart categories={{A.map((a:any)=>D.labels[a])}} series={{[{{name:"W1",data:A.map((a:any)=>V.arms[a].metrics.cross_section_w1_pp)}}]}} height={{245}} valueSuffix=" pp" /><Text size="small" tone="secondary">W1 越低表示模拟分布与真人分布距离越小。</Text></Stack>
   <Stack gap={{8}}><Text weight="semibold">跨人 Q9 中心 IQR（pp）</Text><BarChart categories={{A.map((a:any)=>D.labels[a])}} series={{[{{name:"模拟",data:A.map((a:any)=>V.arms[a].metrics.cross_person_iqr_pp)}}]}} height={{245}} valueSuffix=" pp" referenceLines={{[{{value:V.arms.C0.metrics.real_cross_person_iqr_pp,label:"真人同支持",tone:"neutral"}}]}} /><Text size="small" tone="secondary">真人同支持 IQR：${{f(V.arms.C0.metrics.real_cross_person_iqr_pp)}} pp；模型分布仍较窄。</Text></Stack>
  </Grid>
  <H2>另列：O0 旧参照与照抄上期</H2>
  <Text size="small" tone="secondary">O0/新组的五组共同支持为 652 个 Q9 个人月；含照抄上期的六组共同支持为 532 个 Q9 个人月。两表不与主表直接横比。</Text>
  <Table headers={{["五组共同支持：组别","七期 MAE（pp）","2021 三期（pp）","其余四期（pp）"]}} rows={{["O0","C0","C1","T0","T1"].map((a:any)=>[D.labels[a],f(w.arms[a].mae_all_pp),f(w.arms[a].mae_2021_pp),f(w.arms[a].mae_other_pp)])}} />
  <Table headers={{["六组共同支持：组别","七期 MAE（pp）","2021 三期（pp）","其余四期（pp）"]}} rows={{["T0","copy_previous"].map((a:any)=>[D.labels[a],f(b.arms[a].mae_all_pp),f(b.arms[a].mae_2021_pp),f(b.arms[a].mae_other_pp)])}} />
  <H2>与旧 Q3 的精确重叠桥接</H2>
  <Text>旧 641 人月与本轮 654 人月支持不同，不能直接相减。在同一 ${{D.old_support_bridge.exact_overlap_support_n}} 人月上，O0 旧 Q3 MAE 为 ${{f(D.old_support_bridge.exact_overlap.O0_mae_pp)}} pp，C0 为 ${{f(D.old_support_bridge.exact_overlap.C0_mae_pp)}} pp，T0 为 ${{f(D.old_support_bridge.exact_overlap.T0_mae_pp)}} pp；其 2021 三期 C0 ${{f(D.old_support_bridge.C0_to_T0_2021.C0_mae_pp)}} → T0 ${{f(D.old_support_bridge.C0_to_T0_2021.T0_mae_pp)}} pp。总体平均观察到改善，2021 仍有代价。</Text>
  <Text size="small" tone="secondary">桥接来源：独立聚合复核 · SHA-256 ${{D.bridgeSource}}。不是独立时间验证。</Text>
  <Text>所选警示标签条目占比：T0 ${{f(D.warning_article_exposure.T0_warning_tagged_share*100)}}% → T1 ${{f(D.warning_article_exposure.T1_warning_tagged_share*100)}}%（各 8,059 条所选个人新闻条目）。标签描述文章内容，不是受访者真实阅读或恐惧度。</Text>
  <Divider />
  <Text size="small" tone="secondary">C0→T0 同步调整新闻、食品统计、政策与信心信息日期，属于信息日期束比较，不是新闻单项因果效应。T0 与 T1 的取舍尚待主代理复核。</Text>
 </Stack>;
}}
'''


def _write_manifest(out: Path, data: dict) -> None:
    files = sorted(path for path in out.iterdir() if path.is_file() and path.name != "manifest.json")
    manifest = {
        "schema": "sce_media_timing_report_manifest/v1",
        "source_summary_sha256": data["source_summary_sha256"],
        "independent_review_summary_sha256": data["independent_review_summary_sha256"],
        "new_api_calls": 0,
        "new_q9_fits": 0,
        "files_sha256": {path.name: _sha256(path) for path in files},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def publish(source: Path, independent_source: Path, out: Path) -> dict:
    source = Path(source).resolve()
    independent_source = Path(independent_source).resolve()
    out = Path(out).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if not independent_source.is_file():
        raise FileNotFoundError(independent_source)
    if out.exists():
        raise FileExistsError(f"Fresh report directory required: {out}")
    data = _public_data(source, independent_source)
    _configure_plotting()
    out.mkdir(parents=True, exist_ok=False)

    _plot_monthly_mae(data, out / "monthly_q9_mae.png")
    _plot_levels(data, out / "monthly_q9_level.png")
    _plot_period_mae(data, out / "period_mae.png")
    _plot_auxiliary(data, out / "distribution_auxiliary.png")

    (out / "summary.json").write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (out / "SCE-media-timing-results-20261025.canvas.tsx").write_text(_canvas(data), encoding="utf-8")
    (out / "index.html").write_text(_html(data, out), encoding="utf-8")
    _write_manifest(out, data)
    return {
        "status": "aggregate_media_timing_report_written",
        "path": str(out / "index.html"),
        "canvas": str(out / "SCE-media-timing-results-20261025.canvas.tsx"),
        "figures": [path.name for path in sorted(out.glob("*.png"))],
        "source_summary_sha256": data["source_summary_sha256"],
        "independent_review_summary_sha256": data["independent_review_summary_sha256"],
        "new_api_calls": 0,
        "new_q9_fits": 0,
    }
