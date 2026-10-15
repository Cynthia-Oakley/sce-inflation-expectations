"""Create aggregate-only figures for the 2026-10-15 progress briefing.

No new model calls, no personal records in outputs. This is presentation
preparation, not a new estimator or a replacement for the frozen evaluation.
"""
from pathlib import Path
import hashlib
import json
import os
from fontTools.ttLib import TTCollection

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/sce_progress_report_mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, fontManager
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/sce_progress_report_20261015_v2"
ASSETS = OUT / "assets"
SOURCE = ROOT / "studies/sce_inflation_expectations/reports/progress_20261015_v2"
ASSETS.mkdir(parents=True, exist_ok=True)
kaiti_path = next(Path('/System/Library/AssetsV2').rglob('Kaiti.ttc'))
kaiti = TTCollection(kaiti_path).fonts[0]  # Kaiti SC Regular; embedding permission fsType=8.
kaiti.save(ASSETS / 'kaiti_sc.ttf')
fontManager.addfont(ASSETS / 'kaiti_sc.ttf')
fontManager.addfont('/System/Library/Fonts/Supplemental/Times New Roman.ttf')
FONT = FontProperties(family=["Times New Roman", "Kaiti SC"])
plt.rcParams.update({"font.family": ["Times New Roman", "Kaiti SC"], "font.size": 13,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.labelcolor": "#243b43", "text.color": "#18343d",
                     "axes.edgecolor": "#cad6d8", "svg.fonttype": "none"})
C = {"actual": "#18343d", "self_update": "#087f80", "copy_previous": "#bf8b3c",
     "history_anchor_half": "#7695ab", "new_signal": "#b4665d"}
ledger = []


def read(rel):
    p = ROOT / rel
    ledger.append({"path": rel, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    return json.loads(p.read_text())


def save(fig, name):
    for ext in ("png", "svg"):
        fig.savefig(ASSETS / f"{name}.{ext}", dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def style(ax):
    ax.grid(axis="y", alpha=.18)
    ax.set_axisbelow(True)


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    SOURCE.mkdir(parents=True, exist_ok=True)
    headline = read("docs/sources/sce_baseline_aggregate_sources_latest_20261007.json")
    h = pd.DataFrame(headline["headline_releases"])
    h = h[(h.reference_period >= "2020-01") & (h.reference_period <= "2026-08")]
    h = h.sort_values("reference_period")
    fig, ax = plt.subplots(figsize=(8, 3.5))
    dt = pd.to_datetime(h.reference_period)
    ax.plot(dt, h.value_pp.astype(float), color=C["self_update"], lw=2.5)
    ax.set_ylabel("一年期通胀预期（%）", fontproperties=FONT)
    ax.set_ylim(0, 8)
    style(ax)
    fig.tight_layout()
    save(fig, "headline")

    rel = "outputs/sce_behavior_mechanism_audit_20261014_v3/reference_with_controls_private.parquet"
    p = ROOT / rel
    ledger.append({"path": rel, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    reference = pd.read_parquet(p)
    r = reference[reference.date.astype(int).eq(202206)].copy()
    vals = pd.to_numeric(r.Q9_mean, errors="coerce")
    weights = pd.to_numeric(r.weight, errors="coerce")
    good = vals.notna() & weights.gt(0)
    bins = [-np.inf, 0, 2, 4, 8, 12, np.inf]
    counts = np.histogram(vals[good], bins=bins, weights=weights[good])[0]
    shares = counts / counts.sum() * 100
    fig, ax = plt.subplots(figsize=(6.2, 3.5))
    ax.bar(range(6), shares, color=["#a8c9c8", "#79b7b6", "#469e9e", "#087f80", "#376d78", "#18343d"], width=.66)
    ax.set_xticks(range(6), ["<0", "0–2", "2–4", "4–8", "8–12", "≥12"])
    ax.set_ylabel("调查权重占比（%）", fontproperties=FONT)
    ax.set_xlabel("个人Q9密度均值（%）", fontproperties=FONT)
    style(ax)
    fig.tight_layout()
    save(fig, "real_distribution")

    summary = read("outputs/sce_expanded_state_evaluation_20261014_v1/summary.json")
    cases = pd.DataFrame(read("outputs/sce_expanded_state_evaluation_20261014_v1/cases_private.json"))
    development_cases = pd.DataFrame(read("outputs/sce_expanded_state_trial_20261014_v3/development_cases_private.json"))
    execution = read("outputs/sce_expanded_state_evaluation_20261014_v1/execution_receipt.json")
    coverage = read("outputs/sce_expanded_state_evaluation_20261014_v1/coverage_clarification.json")
    cases = cases[cases.common.eq(True)].copy()
    columns = ["actual", "self_update", "copy_previous", "history_anchor_half"]
    medians = cases.groupby(["month", "repeat"])[columns].agg(
        lambda v: float(np.quantile(v.astype(float), .5, method="inverted_cdf")))
    # Verify the plotted centers reproduce the frozen error definition.
    mae = (medians.self_update - medians.actual).abs().mean()
    expected = summary["results"]["self_update"]["aggregate"]["sample_center_mae_pp"]
    assert abs(mae - expected) < 1e-10, (mae, expected)
    months = summary["evaluation_months"]
    plotmed = medians.groupby(level=0).mean()
    fig, ax = plt.subplots(figsize=(7, 3.5))
    names = {"actual": "真人", "self_update": "LLM + 本人历史", "copy_previous": "照抄上期", "history_anchor_half": "个人历史锚"}
    for key in columns:
        ax.plot(range(4), plotmed.loc[months, key], color=C[key], lw=2.4,
                marker="o", ms=5, label=names[key], ls="--" if key == "copy_previous" else "-")
    ax.set_xticks(range(4), [f"{str(m)[:4]}-{str(m)[4:]}" for m in months])
    ax.set_ylabel("同样本中心（%）", fontproperties=FONT)
    ax.legend(frameon=False, ncol=2, fontsize=11, loc="upper right")
    ax.set_ylim(0, 9)
    style(ax)
    fig.tight_layout()
    save(fig, "main_centers")

    # Present the full completed experiment, keeping development and evaluation
    # phases visible. No new fit or pooled success claim is introduced.
    all_cases = pd.concat([development_cases, cases], ignore_index=True)
    all_cases = all_cases[all_cases.common.eq(True)]
    eight_medians = all_cases.groupby(["month", "repeat"])[columns].agg(
        lambda v: float(np.quantile(v.astype(float), .5, method="inverted_cdf")))
    eight_centers = eight_medians.groupby(level=0).mean()
    fig, ax = plt.subplots(figsize=(7.1, 3.5))
    for key in ["actual", "self_update", "copy_previous"]:
        ax.plot(range(8), eight_centers[key], color=C[key], lw=2.25, marker="o", ms=4,
                label=names[key], ls="--" if key == "copy_previous" else "-")
    ax.axvline(3.5, color="#9fb4b8", ls=":", lw=1.3)
    ax.axvspan(-.3, 3.5, color="#f1f5f4", zorder=-5)
    ax.text(1.6, 8.8, "开发期", ha="center", fontproperties=FONT, fontsize=12, color="#526970")
    ax.text(5.5, 8.8, "固定后评价期", ha="center", fontproperties=FONT, fontsize=12, color="#526970")
    ax.set_xticks(range(8), [str(m)[:4]+"-"+str(m)[4:] for m in eight_centers.index], rotation=25, ha="right", fontsize=11)
    ax.set_xlim(-.3, 7.3); ax.set_ylim(0, 10)
    ax.set_ylabel("同样本Q9中位数（%）", fontproperties=FONT)
    ax.legend(frameon=False, ncol=3, fontsize=10, loc="upper center", bbox_to_anchor=(.5, 1.16))
    style(ax); fig.tight_layout(); save(fig, "eight_centers")

    c = cases[(cases.month == 202206) & (cases["repeat"] == 1)]
    fig, ax = plt.subplots(figsize=(6.5, 3.5))
    for key in ["actual", "self_update", "copy_previous"]:
        v = np.sort(c[key].astype(float).to_numpy())
        ax.step(v, np.arange(1, len(v)+1)/len(v)*100, where="post", label=names[key], color=C[key], lw=2.2)
    # Display bounds are explicit; all scoring still uses full tails.
    ax.set_xlim(-5, 25)
    ax.set_ylim(0, 101)
    ax.set_ylabel("累计人数占比（%）", fontproperties=FONT)
    ax.set_xlabel("个人Q9密度均值（%）", fontproperties=FONT)
    ax.legend(frameon=False, fontsize=11, loc="lower right")
    style(ax)
    fig.tight_layout()
    save(fig, "main_ecdf")

    association = read("outputs/sce_population_associations_20261015_v1/summary.json")
    evidence = []
    for period, label in [("2020_2022", "2020–2022"), ("2023_2025", "2023–2025.10")]:
        # The period key is read explicitly below to avoid assuming file naming.
        if period not in association["periods"]:
            period = next(k for k in association["periods"] if k.startswith("2023"))
        models = association["periods"][period]["models"]
        for field, outcome, title in [("education_fine", "Q9_iqr", "高中相对本科：个人不确定性"),
                                       ("financial_change", "Q9_mean", "财务差一些相对相同：预期水平")]:
            model = models[outcome]
            v = model["contrasts"][field]
            evidence.append({"period": label, "contrast": title, **v})
    fig, axs = plt.subplots(1, 2, figsize=(12, 3.3), sharex=True)
    for j, ax in enumerate(axs):
        for k in range(2):
            v = evidence[k*2+j]
            lo, hi = v["ci95"]
            ax.errorbar(v["estimate"], 1-k, xerr=[[v["estimate"]-lo], [hi-v["estimate"]]],
                        fmt="o", ms=8, capsize=4, color=["#087f80", "#bf8b3c"][k])
        ax.set_yticks([1, 0], ["2020–2022", "2023–2025.10"])
        ax.axvline(0, color="#b8c6c8", ls="--")
        ax.set_xlabel("条件关联与95%区间（百分点）", fontproperties=FONT)
        ax.set_title(["高中相对本科：个人不确定性", "财务差一些相对相同：预期水平"][j], fontproperties=FONT, fontsize=15)
        ax.set_ylim(-.6, 1.6)
        ax.set_xlim(-.1, 2.8)
        ax.spines["left"].set_visible(False)
    fig.tight_layout()
    save(fig, "population_evidence")

    revision = read("outputs/sce_revision_format_evaluation_20261015_v1/summary.json")
    confidence = read("outputs/sce_confidence_analysis_20261011_v2/summary.json")
    prior = read("docs/literature/sce/factual_mechanisms_20261013/prior_trial_summary.json")
    frequency = read("docs/workstreams/20261014_mechanism/purchase_frequency_budget_card_20261015.json")
    u1 = read("outputs/sce_u1_trial_20261014_v2/trial_manifest.json")
    read("outputs/sce_behavior_comparison_u1_20261014_v1/summary.json")
    old_models = read("outputs/sce_qwen_reuse_comparison_20261008_v1/summary.json")
    cpi_by_month = {r['reference_period']: r for r in headline['cpi_first_releases']}
    memory_rows = []
    for month, v in old_models['months'].items():
        future_month = f"{int(month[:4])+1}-{month[4:]}"
        cpi = cpi_by_month[future_month]
        q9 = v['Q9']
        memory_rows.append({'survey_month': month, 'future_cpi_month': future_month,
            'future_cpi_yoy': cpi['value'], 'future_cpi_source_url': cpi['archive_url'],
            'actual_sample_center': q9['matched_real']['median'],
            **{m+'_center': q9['arms'][m]['distribution']['median'] for m in ('deepseek','qwen')}})
    memory_aggregate = {m: {
        'mae_against_sce_sample_pp': float(np.mean([abs(r[m+'_center']-r['actual_sample_center']) for r in memory_rows])),
        'mae_against_t_plus_12_cpi_yoy_pp': float(np.mean([abs(r[m+'_center']-r['future_cpi_yoy']) for r in memory_rows]))
    } for m in ('deepseek','qwen')}
    for rel in ["docs/workstreams/20261013_behavior/codex_u1_real_results_20261014.md",
                "docs/workstreams/20261013_behavior/codex_mapping_results.md",
                "docs/workstreams/20261013_behavior/codex_expanded_protocol_20261014.json",
                "docs/sources/sce_progress_report_planning_20261015.json"]:
        p = ROOT / rel
        ledger.append({"path": rel, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    report_data = {
        "report_date": "2026-10-15", "new_api_calls": 0,
        "reference": {"months": int(reference.date.nunique()), "person_months": len(reference),
                      "people": int(reference.userid.nunique()), "first_month": int(reference.date.min()),
                      "last_month": int(reference.date.max()), "example_month": 202206,
                      "example_month_rows": int(good.sum()), "example_weighted_shares": shares.tolist()},
        "headline": {"months": len(h), "through": "2026-08", "source_snapshot": "2026-10-07"},
        "main": {"evaluation_months": months, "aggregates": {k:v["aggregate"] for k,v in summary["results"].items()},
                 "unique_common_person_months": len(cases[["month", "userid"]].drop_duplicates()),
                 "common_generation_rows": len(cases),
                 "monthly_centers_mean_of_repeats": plotmed.reset_index().to_dict(orient="records"),
                 "all_eight_monthly_centers": eight_centers.reset_index().to_dict(orient="records"),
                 "all_eight_common_person_months": len(all_cases[['month','userid']].drop_duplicates()),
                 "execution": execution, "coverage_clarification": coverage,
                 "gate_passed": summary["predefined_success_gate_passed"]},
        "population_associations": evidence,
        "historical_knowledge_diagnostic": {'sample': '2021, old same-message 20-person panel; not current P/E or an independent recursive trajectory',
            'aggregates': memory_aggregate, 'monthly_aggregate_rows': memory_rows,
            'interpretation': 'No stable reproduction of SCE or realised next-12-month CPI; does not exclude partial historical knowledge. t+12 monthly CPI YoY is only an approximate realised horizon.'},
        "experiment_index": {
            "confidence": {"calls": confidence["actual_calls"], "token_cost_estimate_usd": confidence["conservative_cost_usd"], "months": list(confidence["months"])},
            "prior": {"calls": prior["actual_calls"], "token_cost_estimate_usd": prior["conservative_cost_usd"], "months": list(prior["months"])},
            "frequency": {"calls": frequency["actual_api_calls"], "token_cost_estimate_usd": frequency["recorded_peak_token_cost_estimate_usd"]},
            "u1": {"calls": u1["new_api_calls"], "months": u1["months"], "cost_source": "docs/workstreams/20261013_behavior/codex_u1_real_results_20261014.md"}
        },
        "revision_format": {"coverage": revision["coverage"],
                            "cost_peak_estimate_usd": revision["new_peak_cost_estimate_usd"],
                            "adopted": False},
        "sources": ledger,
        "privacy": "Only aggregates and scientific charts are exported; no respondent rows, identifiers or keys.",
        "limits": ["Retrospective returner A diagnostic, not national or recursive B forecast.",
                   "Four evaluation months were held after development freeze; now inspected and not fresh holdout.",
                   "Report preparation does not run simulations, refit scorers or retune mechanisms."]
    }
    (SOURCE / "aggregate_data.json").write_text(json.dumps(report_data, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"output": str(OUT), "reference": report_data["reference"],
                      "main_common_pm": report_data["main"]["unique_common_person_months"],
                      "plotted_center_mae": mae, "aggregate_only": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
