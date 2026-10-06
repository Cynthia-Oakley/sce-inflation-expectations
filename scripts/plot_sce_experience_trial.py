#!/usr/bin/env python3
"""Plot equal-person medians and interquartile ranges from a completed pilot."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--out-prefix", type=Path, required=True)
    args = parser.parse_args()
    destinations = [args.out_prefix.with_suffix(ext) for ext in (".png", ".pdf")]
    if any(path.exists() for path in destinations):
        raise FileExistsError("Retain existing figures; choose a new output prefix")
    summary = json.loads(args.summary.read_text())
    arms = ["v2_baseline", "expression_shared", "basket_shared", "focus_only", "basket_focus"]
    labels = ["Baseline", "Respondent frame", "Basket + frame", "Focus + frame", "Basket + focus + frame", "Matched real"]
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.4), sharey=True)
    for ax, (month, cells) in zip(axes, sorted(summary["monthly_by_arm"].items())):
        stats = [cells[arm]["q9"]["matched_distribution_difference"]["simulated"] for arm in arms]
        stats.append(cells[arms[0]]["q9"]["matched_distribution_difference"]["matched_real"])
        for i, row in enumerate(stats):
            color = "#222222" if i == 5 else "#466981"
            ax.hlines(i, row["quantiles"]["p25"], row["quantiles"]["p75"], color=color, linewidth=5)
            ax.plot(row["median"], i, marker="|", color="white", markersize=12, markeredgewidth=2)
        ax.set_title(f"{month[:4]}-{month[4:]}")
        ax.set_xlabel("Individual Q9 fitted expectation (%)")
        ax.set_yticks(range(6), labels)
        ax.grid(axis="x", alpha=0.18)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].invert_yaxis()
    axes[0].set_ylabel("Experimental condition")
    fig.suptitle("SCE pilot: simulated answers remain more concentrated", fontsize=13)
    fig.text(0.5, 0.015, "Bars: 25th–75th percentiles; white mark: median. Same 20 people within each month; equal-person weights.\nSource: frozen 2026-10-06 pilot and matched SCE microdata, both scored with the project Q9 approximation.", ha="center", fontsize=8)
    fig.tight_layout(rect=(0, 0.10, 1, 0.94))
    args.out_prefix.parent.mkdir(parents=True, exist_ok=True)
    for path in destinations:
        fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print("\n".join(map(str, destinations)))


if __name__ == "__main__":
    main()
