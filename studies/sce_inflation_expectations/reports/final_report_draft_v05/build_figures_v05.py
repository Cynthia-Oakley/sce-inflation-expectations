"""Build report-only A/T0 versus old-A and legacy-B comparison figures."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent / "figures"
READOUT = ROOT / "outputs/sce_full_a_t0_readout_20261026_v1"
ANALYSIS = ROOT / "outputs/sce_full_a_t0_analysis_20261026_v1"
OLD_A = ROOT / "outputs/sce_fullperiod_analysis_20261024_v1/summary.json"
OLD_B = ROOT / "outputs/sce_recent_b_readout_20261025_v2/summary.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def font_setup():
    cn = ROOT / "outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf"
    font_manager.fontManager.addfont(str(cn))
    plt.rcParams.update({
        "font.family": ["Times New Roman", "Kaiti SC"],
        "font.size": 11,
        "axes.unicode_minus": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })


def make_national(rows, b_rows):
    assert len(rows) == 82 and rows[0]["month"] == "2019-01" and rows[-1]["month"] == "2025-10"
    assert len(b_rows) == 11 and str(b_rows[0]["month"]).replace("-", "") == "202511"
    old_b = json.loads(OLD_B.read_text())
    b_months = old_b["evaluation"]["monthly"]
    assert len(b_months) == 11
    b_months = [
        {**r, "month": (str(r["month"])[:4] + "-" + str(r["month"])[4:])
         if "-" not in str(r["month"]) else str(r["month"])}
        for r in b_months
    ]
    assert b_months[0]["month"] == "2025-11" and b_months[-1]["month"] == "2026-09"

    x = np.arange(len(rows))
    fig, axes = plt.subplots(
        2, 1, figsize=(12.6, 6.2),
        gridspec_kw={"height_ratios": [1.18, 0.72]}, layout="constrained",
    )
    ax = axes[0]
    ax.axvspan(23.5, 35.5, color="#c76800", alpha=.08, zorder=0)
    ax.plot(x, [float(r["truth_pp"]) for r in rows], color="#242424", lw=1.8, label="官方全国SCE")
    ax.plot(x, [float(r["anchor_pp"]) for r in rows], color="#777777", ls="--", lw=1.3, label="公开历史基线")
    ax.plot(x, [float(r["old_same_roster_pp"]) for r in rows], color="#0078b5", lw=1.6, label="旧A（新版名单/权重）")
    ax.plot(x, [float(r["sim_pp"]) for r in rows], color="#c76800", lw=1.7, label="新版A T0")
    ticks = list(range(0, 73, 12)) + [81]
    ax.set_xticks(ticks, [rows[i]["month"] for i in ticks], fontsize=9, rotation=12)
    ax.set(xlim=(-.5, 81.5), ylabel="一年期通胀预期（%）",
           title="A：2019-01—2025-10（82月；新版T0与旧A对照）")
    ax.legend(frameon=False, ncol=4, loc="upper left", fontsize=9)
    ax.text(.99, .90, "MAE：旧A 0.318 · T0 0.298 · 基线 0.223 pp",
            transform=ax.transAxes, ha="right", va="top", fontsize=9)
    ax.grid(axis="y", alpha=.17)

    ax = axes[1]
    bx = np.arange(len(b_months))
    ax.plot(bx, [r["truth_pp"] for r in b_months], color="#242424", marker="o", ms=3, lw=1.5, label="官方SCE")
    ax.plot(bx, [r["anchor_pp"] for r in b_months], color="#777777", ls="--", marker=".", lw=1.2, label="公开历史基线")
    ax.plot(bx, [r["sim_pp"] for r in b_months], color="#c76800", marker="s", ms=3, lw=1.5, label="旧B11（未刷新）")
    ax.set_xticks(bx, [r["month"][2:] for r in b_months], fontsize=8)
    ax.set(xlim=(-.4, 10.4), ylabel="一年期通胀预期（%）",
           title="B：2025-11—2026-09（沿用v0.4旧结果；未重新评价）")
    ax.legend(frameon=False, ncol=3, loc="upper left", fontsize=8)
    ax.text(.99, .90, "旧B11 MAE 0.241 / 基线 0.173 pp",
            transform=ax.transAxes, ha="right", va="top", fontsize=8)
    ax.grid(axis="y", alpha=.17)
    fig.savefig(OUT / "national_A82_T0_B11_legacy.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def make_micro(summary):
    same = summary["same_roster"]["metrics"]
    new = same["new"]["q9"]
    old = same["old"]["q9"]
    initial = summary["initial_reference_comparison"]["initial_reference"]["q9"]
    colors = ["#92979d", "#0078b5", "#c76800"]
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 3.35), layout="constrained")
    ax = axes[0]
    vals = [initial["cross_section_w1_pp"], old["cross_section_w1_pp"], new["cross_section_w1_pp"]]
    bars = ax.bar(["保留起点", "旧A", "新版T0"], vals, color=colors, width=.64)
    ax.set_title("跨人W1：模型分布与真人分布的距离")
    ax.set_ylabel("W1（pp，越低越接近）")
    ax.set_ylim(0, max(vals) * 1.28)
    ax.grid(axis="y", alpha=.17)
    for bar, value in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + .035, f"{value:.2f}", ha="center", va="bottom", fontsize=10)

    ax = axes[1]
    vals = [initial["cross_person_iqr_pp"], old["cross_person_iqr_pp"], new["cross_person_iqr_pp"], new["real_cross_person_iqr_pp"]]
    bars = ax.bar(["保留起点", "旧A", "新版T0", "真人"], vals,
                  color=["#92979d", "#0078b5", "#c76800", "#242424"], width=.64)
    ax.set_title("跨人IQR：模拟分歧仍明显偏窄")
    ax.set_ylabel("跨人IQR（pp）")
    ax.set_ylim(0, max(vals) * 1.22)
    ax.grid(axis="y", alpha=.17)
    for bar, value in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + .06, f"{value:.2f}", ha="center", va="bottom", fontsize=10)
    fig.savefig(OUT / "microstructure_old_A_T0.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    font_setup()
    rows = read_csv(READOUT / "monthly_national.csv")
    b = json.loads(OLD_B.read_text())["evaluation"]["monthly"]
    new_summary = json.loads((READOUT / "summary.json").read_text())
    make_national(rows, b)
    make_micro(new_summary)
    sources = [
        READOUT / "summary.json", READOUT / "monthly_national.csv", READOUT / "yearly.csv",
        READOUT / "manifest.json", ANALYSIS / "summary.json", ANALYSIS / "manifest.json",
        OLD_A, OLD_B,
    ]
    data = {
        "status": "report_only_A82_old_A_vs_T0_and_legacy_B11",
        "new_api_calls": 0,
        "new_q9_density_fits": 0,
        "A_months": len(rows), "B_months": len(b),
        "A_B_joint_error_metric_computed": False,
        "A_B_continuous_line": False,
        "B11_refreshed": False,
        "strict_ex_ante_forecast": False,
        "old_A_curve_basis": "old_same_roster_pp; recalculated on new T0 roster and weights",
        "old_A_headline_table_basis": "original full roster; 82-month MAE 0.317092535",
        "figures": ["national_A82_T0_B11_legacy.png", "microstructure_old_A_T0.png"],
        "sources_sha256": {str(p.relative_to(ROOT)): sha(p) for p in sources},
        "scope_note": "A is a retrospective reconstruction; B is the unchanged v0.4 lagged-proxy backtest. Different input regimes are displayed in separate panels, with no combined score.",
    }
    (Path(__file__).resolve().parent / "figure_data_v05.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps({"figures": data["figures"], "new_api_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
