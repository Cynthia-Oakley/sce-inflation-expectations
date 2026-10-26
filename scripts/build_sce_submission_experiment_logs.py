#!/usr/bin/env python3
"""Build private and public-whitelist SCE experiment log indexes (offline)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "studies" / "sce_inflation_expectations" / "submission_tools"
if str(MODULES) not in sys.path:
    sys.path.insert(0, str(MODULES))

from experiment_logs import build_registry, write_registry  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Hash explicitly allowlisted experiment receipts and token ledgers, "
            "then write private JSON/CSV plus a field-whitelisted public JSON. "
            "No model calls or raw answer parsing are performed."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--sources",
        type=Path,
        default=ROOT / "submission" / "experiment_registry_sources.json",
        help="Repository-relative or absolute path to the curated source registry.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "outputs" / "sce_submission_experiment_logs_20261026_v1",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace files in an existing output directory. Prefer a new run directory instead.",
    )
    args = parser.parse_args()

    source_path = args.sources
    if not source_path.is_absolute():
        source_path = args.repo_root / source_path
    if not source_path.is_file():
        parser.error(f"Source registry not found: {source_path}")

    registry = build_registry(args.repo_root, source_path)
    write_registry(registry, args.out, overwrite=args.overwrite)
    summary = registry["cost_summary_usd"]
    print(f"records={len(registry['records'])}")
    print(f"api_reported_selected_usd={summary['reported_api_cost_usd']:.9f}")
    print(f"unknown_fee_reserve_selected_usd={summary['unknown_fee_reserve_usd']:.9f}")
    print(f"token_usage_estimate_selected_usd={summary['token_usage_estimate_usd']:.9f}")
    print(f"complete_project_cost_total={summary['complete_project_cost_total']}")
    print(f"output={args.out.resolve()}")


if __name__ == "__main__":
    main()
