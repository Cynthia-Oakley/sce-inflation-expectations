#!/usr/bin/env python3
"""Create static figures from an aggregated SCE cognition evaluation summary."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
ARMS = ("label_only", "question_answer", "faithful_paraphrase")
LABELS = ("Label only", "Question + answer", "Faithful paraphrase")
COLORS = ("#4C78A8", "#F28E2B", "#59A14F")
BIN_LABELS = ("≥12", "8 to 12", "4 to 8", "2 to 4", "0 to 2",
              "−2 to 0", "−4 to −2", "−8 to −4", "−12 to −8", "≤−12")


def read_data(path: Path):
    summary = json.loads(path.read_text(encoding="utf-8"))
    if summary.get("status") != "completed_sce_cognition_development_pilot_evaluation":
        raise ValueError("Input must be a completed cognition evaluation summary.json")
    protocol = summary.get("protocol", {})
    months, repeats = protocol.get("months", []), protocol.get("generation_repeats", [])
    if (len(months) != 4 or repeats != [1, 2] or protocol.get("n_per_month") != 24
            or protocol.get("stratum_n") != {"high": 14, "low": 10}):
        raise ValueError("Expected the registered four-month, two-repeat development pilot")
    arms = summary.get("arms", {})
    if any(arm not in arms for arm in ARMS):
        raise ValueError("Summary is missing one or more registered arms")
    common = summary.get("common_support", {})
    source_hashes = summary.get("source_sha256")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("Summary is missing source SHA-256 provenance")
    manifest = json.dumps(source_hashes, sort_keys=True, separators=(",", ":"))
    source_fingerprint = hashlib.sha256(manifest.encode()).hexdigest()[:16]
    protocol_hash = summary.get("protocol_sha256")
    if not isinstance(protocol_hash, str) or len(protocol_hash) != 64:
        raise ValueError("Summary is missing the protocol SHA-256")

    metrics = [arms[a]["q9"]["aggregate_equal_month_repeat_cells"] for a in ARMS]
    required = ("individual_density_iqr_mae_pp", "q9_center_mae_pp", "cross_section_w1_pp",
                "individual_density_iqr_mean_pp", "real_individual_density_iqr_mean_pp", "cross_person_iqr_pp",
                "real_cross_person_iqr_pp")
    for metric in required:
        if any(not isinstance(row.get(metric), (float, int)) or not math.isfinite(row[metric]) for row in metrics):
            raise ValueError(f"Metric is missing or non-finite: {metric}")

    cells = summary.get("monthly_mean_bin_distributions", {}).get("cells", [])
    repeat_cells = {}
    for month in months:
        matching = [c for c in cells if c.get("month") == month]
        if len(matching) != len(repeats):
            raise ValueError(f"Month {month} does not have both ten-bin repeat cells")
        profiles = []
        for cell in matching:
            data = cell.get("equal_person")
            if not data or cell.get("n_person_months", 0) < 1:
                raise ValueError(f"Month {month} has no common-support ten-bin data")
            profile = {"Human": data.get("actual_mean_bins"), **{
                label: data.get("arms", {}).get(arm, {}).get("mean_bins")
                for arm, label in zip(ARMS, LABELS)}}
            if any(not isinstance(v, list) or len(v) != 10 or any(
                    not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0 or x > 100 for x in v)
                    or abs(sum(v) - 100) > 1e-5 for v in profile.values()):
                raise ValueError(f"Month {month} has incomplete probability vectors")
            profiles.append(profile)
        repeat_cells[month] = profiles
    return summary, months, metrics, repeat_cells, source_fingerprint, protocol_hash, common


def footer(fig, summary, months, source_fingerprint, protocol_hash, common, note=""):
    protocol = summary["protocol"]
    strata = protocol.get("stratum_n", {"high": 14, "low": 10})
    planned_n = len(months) * protocol["n_per_month"]
    month_text = ", ".join(f"{int(m)//100:04d}-{int(m)%100:02d}" for m in months)
    n = common.get("q9_common_scorable_person_months", "NA")
    text = (f"Q9 common support: {n}/{planned_n} person-months. Equal month × repeat weighting; {note}\n"
            f"Months: {month_text}. 24 selected people/month ({strata.get('high')} High, "
            f"{strata.get('low')} Low; Low oversampled); previously inspected development months only, "
            "not independent validation or a national estimate.\n"
            f"Source SHA-256 manifest fingerprint: {source_fingerprint} ({len(summary['source_sha256'])} inputs); "
            f"protocol SHA-256: {protocol_hash[:16]}.")
    fig.text(.055, .018, text, ha="left", va="bottom", fontsize=8, color="#444444")


def plot_accuracy(out, summary, months, metrics, source_fp, protocol_hash, common):
    specs = (("individual_density_iqr_mae_pp", "Individual Q9 IQR MAE"),
             ("q9_center_mae_pp", "Q9 median MAE"),
             ("cross_section_w1_pp", "Across-person W1"))
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.8), sharey=True)
    y = list(range(3))
    for j, (ax, (key, title)) in enumerate(zip(axes, specs)):
        values = [float(row[key]) for row in metrics]
        ax.barh(y, values, color=COLORS, height=.58)
        ax.set_yticks(y)
        if j == 0:
            ax.set_yticklabels(LABELS)
        else:
            ax.tick_params(axis="y", labelleft=False)
        ax.invert_yaxis()
        ax.set_title(title, fontsize=11, weight="bold")
        ax.set_xlabel("Inflation percentage points")
        ax.grid(axis="x", alpha=.2)
        xmax = max(max(values) * 1.27, .05)
        ax.set_xlim(0, xmax)
        for yi, value in zip(y, values):
            ax.text(value + xmax * .025, yi, f"{value:.2f}", va="center", fontsize=9)
    fig.suptitle("Q9 accuracy across the three input conditions (lower is better)", y=.98, fontsize=14)
    fig.subplots_adjust(left=.18, right=.98, top=.84, bottom=.31, wspace=.32)
    footer(fig, summary, months, source_fp, protocol_hash, common,
           "MAE uses individual IQRs; median error compares sample medians of fitted density means; W1 compares their distributions.")
    fig.savefig(out / "01_q9_accuracy.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_profiles(out, summary, months, cells, source_fp, protocol_hash, common):
    fig, axes = plt.subplots(2, 2, figsize=(14, 8.8), sharey=True)
    colors = {"Human": "#222222", **dict(zip(LABELS, COLORS))}
    styles = {"Human": ("-", "o"), LABELS[0]: ("--", "s"),
              LABELS[1]: ("--", "^"), LABELS[2]: ("--", "D")}
    for ax, month in zip(axes.flat, months):
        profiles = cells[month]
        for name in ("Human", *LABELS):
            values = [sum(p[name][i] for p in profiles) / len(profiles) for i in range(10)]
            linestyle, marker = styles[name]
            ax.plot(range(10), values, color=colors[name], linestyle=linestyle, marker=marker,
                    linewidth=2.0 if name == "Human" else 1.6, markersize=4, label=name)
        ax.set_title(f"{int(month)//100:04d}-{int(month)%100:02d}", weight="bold")
        ax.set_xticks(range(10), BIN_LABELS, rotation=42, ha="right", fontsize=8)
        ax.set_ylabel("Mean probability (%)")
        ax.grid(alpha=.22)
    for ax in axes.flat:
        ax.set_ylim(0, 100)
        ax.set_xlabel("12-month expected inflation-rate bin (%)")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(.5, .94))
    fig.suptitle("Mean ten-bin Q9 distributions by development month", y=.99, fontsize=14)
    fig.subplots_adjust(left=.08, right=.98, top=.88, bottom=.29, hspace=.43, wspace=.18)
    footer(fig, summary, months, source_fp, protocol_hash, common,
           "Each monthly curve is the equal average of its two repeat-cell means; bin probabilities are shown as percent.")
    fig.savefig(out / "02_monthly_bin_profiles.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_widths(out, summary, months, metrics, source_fp, protocol_hash, common):
    categories, colors = ("Human", *LABELS), ("#777777", *COLORS)
    within = [float(metrics[0]["real_individual_density_iqr_mean_pp"])] + [
        float(row["individual_density_iqr_mean_pp"]) for row in metrics]
    across = [float(metrics[0]["real_cross_person_iqr_pp"])] + [
        float(row["cross_person_iqr_pp"]) for row in metrics]
    ymax = max(max(within), max(across), .1) * 1.22
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.2), sharey=True)
    for ax, values, title in zip(axes, (within, across),
            ("Within-person Q9 density IQR\n(average individual uncertainty width)",
             "Across-person IQR of Q9 means\n(spread between sampled people)")):
        bars = ax.bar(range(4), values, color=colors, width=.68)
        ax.set_xticks(range(4), categories, rotation=15, ha="right")
        ax.set_title(title, fontsize=11, weight="bold")
        ax.set_ylabel("Inflation percentage points")
        ax.set_ylim(0, ymax)
        ax.grid(axis="y", alpha=.2)
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, value + ymax*.018, f"{value:.2f}",
                    ha="center", va="bottom", fontsize=9)
    fig.suptitle("Two different widths in Q9 responses", y=.98, fontsize=14)
    fig.subplots_adjust(left=.09, right=.98, top=.83, bottom=.32, wspace=.25)
    footer(fig, summary, months, source_fp, protocol_hash, common,
           "Within-person width averages fitted density IQRs; across-person width is the IQR of fitted person-level means.")
    fig.savefig(out / "03_q9_uncertainty_widths.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, type=Path, help="Aggregated evaluation summary.json")
    parser.add_argument("--out", required=True, type=Path, help="Fresh output directory under outputs/")
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() or not out.is_relative_to((ROOT / "outputs").resolve()):
        parser.error("--out must be a fresh directory under the project's outputs/")
    summary, months, metrics, cells, source_fp, protocol_hash, common = read_data(args.summary)
    out.mkdir(parents=True)
    plot_accuracy(out, summary, months, metrics, source_fp, protocol_hash, common)
    plot_profiles(out, summary, months, cells, source_fp, protocol_hash, common)
    plot_widths(out, summary, months, metrics, source_fp, protocol_hash, common)
    print(f"Wrote three static PNG figures to {out}")


if __name__ == "__main__":
    main()
