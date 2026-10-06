#!/usr/bin/env python3
"""Export a paper-ready Q1 group comparison from completed paired evaluation."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--summary", type=Path, required=True)
    ap.add_argument("--out-prefix", type=Path, required=True)
    a = ap.parse_args()
    destinations = [a.out_prefix.with_suffix(ext) for ext in (".png", ".pdf")]
    if any(p.exists() for p in destinations):
        raise FileExistsError("preserve existing figures; choose a fresh output prefix")
    data = json.loads(a.summary.read_text())
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
    x = list(range(1, 6))
    for ax, (month, m) in zip(axes, sorted(data["months"].items())):
        for arm, label, color, linestyle in [("baseline", "Baseline", "#527184", "--"),
                                             ("q1_state", "+ Household financial experience", "#986934", "-"),
                                             ("real", "Matched SCE respondents", "#252525", "-")]:
            cells = m["arms"]["baseline" if arm == "real" else arm]["Q1_groups"]
            field = "real" if arm == "real" else "simulated"
            y = [cells[str(c)][field]["median"] for c in x]
            ax.plot(x, y, marker="o", color=color, linestyle=linestyle, label=label)
        ax.set_title(f"{month[:4]}-{month[4:]} (complete pairs: {m['n_complete_pairs']}/50)")
        ax.set_xticks(x, ["Much\nworse", "Somewhat\nworse", "About\nthe same", "Somewhat\nbetter", "Much\nbetter"])
        ax.set_xlabel("Reported household finances compared with 12 months earlier")
        ax.grid(axis="y", alpha=.18)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Median individual Q9 fitted expectation (%)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.5, .94), ncol=3, frameon=False, fontsize=9)
    fig.suptitle("Does household financial experience recover differences between respondents?", fontsize=12, y=1.)
    fig.text(.5, .015, "Source: authorized 2026-10-06 Q1 pilot, 2021-05/06 SCE microdata. Same project density scorer for real and simulated answers.\n10 selected per Q1 category before answer inspection; equal-person, complete-case comparison. Development diagnosis, not national estimates.", ha="center", fontsize=8)
    fig.tight_layout(rect=(0, .12, 1, .87))
    a.out_prefix.parent.mkdir(parents=True, exist_ok=True)
    for p in destinations:
        fig.savefig(p, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print("\n".join(str(p.resolve()) for p in destinations))


if __name__ == "__main__":
    main()
