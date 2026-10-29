#!/usr/bin/env python3
"""Portable offline replay of the frozen A macro-calibration workflow.

The replay copies original source and public/macro inputs into an isolated
workspace, then invokes the unmodified original analysis script there. The
optional fresh-evaluation mode substitutes only A Core and A Core+Normal
centers before the original early-48 calibration/refit; all public target,
anchor, CPI-vintage and feature definitions remain frozen.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
CN_DIR = Path("outputs/sce_full_a_core_normal_evaluation_20261026_v3")
CORE_DIR = Path("outputs/sce_full_a_t0_analysis_20261026_v1")
ENV_DIR = Path("outputs/sce_fullperiod_materialized_20261022_v2")
B_DIR = Path("outputs/sce_recent_b_core_normal_evaluation_20261026_v1")
PROTOCOL = Path("docs/workstreams/20261026_core_normal_full_a/macro_calibration_protocol.json")
EXPECTED_DIR = Path("outputs/sce_full_a_macro_calibration_20261026_v1")
MANIFEST_NAME = "portable_calibration_manifest.json"
RECEIPT_NAME = "portable_calibration_receipt.json"

SOURCE_FILES = (
    Path("scripts/analyze_sce_full_a_macro_calibration.py"),
    Path("studies/sce_inflation_expectations/submission_tools/portable_calibration.py"),
    Path("studies/sce_inflation_expectations/evaluation/full_a_macro_calibration.py"),
    Path("studies/sce_inflation_expectations/evaluation/aggregate_blend.py"),
    Path("studies/sce_inflation_expectations/evaluation/metrics.py"),
    Path("studies/sce_inflation_expectations/experiments/full_a_core_normal.py"),
    Path("studies/sce_inflation_expectations/experiments/frozen_batch.py"),
    Path("studies/sce_inflation_expectations/experiments/staged_rosters.py"),
    Path("studies/sce_inflation_expectations/experiments/state_continuity_inputs.py"),
    Path("studies/sce_inflation_expectations/experiments/state_continuity.py"),
    Path("studies/sce_inflation_expectations/age_reporting_audit.py"),
    Path("studies/sce_inflation_expectations/monthly_analysis.py"),
    Path("studies/sce_inflation_expectations/prior_belief_preparation.py"),
    Path("studies/sce_inflation_expectations/core_normal_joint.py"),
    Path("studies/sce_inflation_expectations/population/monthly_fine_grid.py"),
    Path("studies/sce_inflation_expectations/population/grid_sampling.py"),
    Path("studies/sce_inflation_expectations/population_stratification.py"),
    Path("studies/sce_inflation_expectations/scoring/sce_q9_frozen.py"),
    Path("studies/sce_inflation_expectations/scoring/sce_q9.py"),
    Path("studies/sce_inflation_expectations/scoring/beta_fit_kernel.py"),
    Path("studies/sce_inflation_expectations/submission_tools/reproduce.py"),
)

CN_FILES = (
    CN_DIR / "manifest.json",
    CN_DIR / "monthly_public.csv",
    CN_DIR / "summary.json",
    CN_DIR / "yearly.csv",
)
CORE_FILES = (CORE_DIR / "summary.json",)
B_FILES = (
    B_DIR / "acceptance.json",
    B_DIR / "manifest.json",
    B_DIR / "monthly_national.csv",
    B_DIR / "summary.json",
)
EXPECTED_FILES = tuple(
    EXPECTED_DIR / name for name in (
        "manifest.json",
        "monthly_inputs_public.csv",
        "monthly_predictions_public.csv",
        "protocol.json",
        "summary.json",
        "training_fits_sealed_before_later_scores.json",
    )
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, value) -> None:
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _copy_files(root: Path, out: Path, files, roles: dict, records: dict) -> None:
    for relative in files:
        source = (root / relative).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise FileNotFoundError(f"Missing or unsafe calibration source: {relative}")
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        records[str(relative)] = {"sha256": _sha256(target), "role": roles.get(str(relative), "original_code")}


def _original_months(root: Path) -> list[str]:
    path = root / CN_DIR / "monthly_public.csv"
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    months = [str(row["month"]) for row in rows]
    if len(months) != 82 or len(set(months)) != 82 or months != sorted(months):
        raise ValueError("Frozen A calibration input must contain 82 chronological months")
    return months


def export(out, root=ROOT) -> dict:
    """Copy the unmodified calibration program and its required inputs.

    The archive keeps the exact relative paths referenced by the original
    evaluator. Top-level/experiment initializers are intentionally omitted so
    the scorer's package import does not register unrelated simulator models.
    """
    root = Path(root).expanduser().resolve()
    out = Path(out).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    if out.exists():
        raise FileExistsError(f"New calibration bundle directory required: {out}")
    months = _original_months(root)
    files = list(SOURCE_FILES) + [PROTOCOL] + list(CN_FILES) + list(CORE_FILES) + list(B_FILES) + list(EXPECTED_FILES)
    files.extend(ENV_DIR / month / "environment.json" for month in months)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=False)

    roles = {}
    for path in SOURCE_FILES:
        roles[str(path)] = "original_calibration_or_dependency_code"
    roles[str(PROTOCOL)] = "frozen_A_calibration_protocol"
    for path in CN_FILES:
        roles[str(path)] = "frozen_A_Core_and_CoreNormal_aggregate"
    for path in CORE_FILES:
        roles[str(path)] = "frozen_A_national_truth_anchor_and_common_score_bridge"
    for path in B_FILES:
        roles[str(path)] = "frozen_B_CoreNormal_downstream_aggregate"
    for path in EXPECTED_FILES:
        roles[str(path)] = "archived_calibration_result_for_replay_verification"
    for month in months:
        roles[str(ENV_DIR / month / "environment.json")] = "public_CPI_release_vintage_and_monthly_asof"

    records = {}
    _copy_files(root, out, files, roles, records)
    # The output of the original evaluator must be a fresh path inside the
    # isolated workspace. The archive is copied to its original relative path
    # solely as an immutable reference; no replay writes there.
    manifest = {
        "schema": "sce_portable_macro_calibration/v1",
        "status": "exported_portable_offline_calibration_bundle",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_root_label": "original_source_workspace",
        "a_month_count": len(months),
        "a_months": months,
        "public_CPI_environment_count": len(months),
        "frozen_B_aggregate_included": True,
        "fresh_mode": {
            "input": "portable_evaluate output directory",
            "uses": ["monthly_series.csv A q9_median_pp", "normal_summary.json A_Normal q9 median_pp"],
            "replaces": ["CN monthly_public.csv before_model_pp", "CN monthly_public.csv expanded_model_pp"],
            "preserves": ["truth_pp", "baseline_pp", "as_of", "public CPI feature vintages", "protocol"],
        },
        "runtime_requirements": {
            "python": ">=3.10",
            "packages": ["numpy", "pandas", "scipy", "openpyxl"],
            "network_calls": 0,
        },
        "files": records,
    }
    _write_json(out / MANIFEST_NAME, manifest)
    return manifest


def _verify_bundle(data: Path) -> dict:
    manifest_path = data / MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Calibration package manifest is missing: {manifest_path}")
    manifest = _read_json(manifest_path)
    if manifest.get("schema") != "sce_portable_macro_calibration/v1":
        raise ValueError("Unsupported calibration package schema")
    for relative, row in manifest.get("files", {}).items():
        path = (data / relative).resolve()
        if not path.is_relative_to(data) or not path.is_file() or _sha256(path) != row["sha256"]:
            raise ValueError(f"Calibration package file hash mismatch: {relative}")
    return manifest


def _finite_number(value, label):
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise ValueError(f"Missing {label}")
        value = float(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"Invalid finite number for {label}")
    return float(value)


def _read_csv_rows(path: Path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _load_fresh_centers(fresh_evaluation: Path, original_rows: list[dict]) -> tuple[dict, dict]:
    summary_path = fresh_evaluation / "summary.json"
    series_path = fresh_evaluation / "monthly_series.csv"
    normal_path = fresh_evaluation / "normal_summary.json"
    if not all(path.is_file() for path in (summary_path, series_path, normal_path)):
        raise FileNotFoundError("Fresh evaluator directory needs summary.json, monthly_series.csv and normal_summary.json")
    summary = _read_json(summary_path)
    if summary.get("status") != "completed_fresh_model_evaluation" or summary.get("actual_model_results") is not True:
        raise ValueError("Calibration accepts only a complete fresh model evaluation, not fixture-only or partial output")
    direct = {}
    for row in _read_csv_rows(series_path):
        if row.get("task") != "A":
            continue
        period = str(row.get("period", ""))
        if period in direct:
            raise ValueError(f"Duplicate fresh A center: {period}")
        direct[period] = _finite_number(row.get("q9_median_pp"), f"A q9 median {period}")
    normal_summary = _read_json(normal_path)
    normal_rows = {}
    for row in normal_summary.get("monthly", []):
        if row.get("run") != "A_Normal":
            continue
        period = str(row.get("period", ""))
        if period in normal_rows:
            raise ValueError(f"Duplicate fresh A_Normal center: {period}")
        if row.get("status") != "completed_fresh_joint_expansion":
            raise ValueError(f"A_Normal is unavailable for {period}; full early48 refit cannot silently drop periods")
        normal_rows[period] = _finite_number(row.get("q9", {}).get("median_pp"), f"A_Normal q9 median {period}")
    expected_periods = {str(row["month"]) for row in original_rows}
    if set(direct) != expected_periods:
        raise ValueError(f"Fresh A direct centers must cover exactly the frozen 82 months; missing={sorted(expected_periods-set(direct))[:5]}, extra={sorted(set(direct)-expected_periods)[:5]}")
    if set(normal_rows) != expected_periods:
        raise ValueError(f"Fresh A_Normal centers must cover exactly the frozen 82 months; missing={sorted(expected_periods-set(normal_rows))[:5]}, extra={sorted(set(normal_rows)-expected_periods)[:5]}")
    # Check the public evaluator CSVs agree, so a hand-edited/partial Normal
    # file cannot silently enter the trained macro path.
    downstream_path = fresh_evaluation / "monthly_predictions_public.csv"
    if downstream_path.is_file():
        downstream = {str(row["month"]): _finite_number(row["CoreNormal_tau8_pure"], f"A downstream Normal {row['month']}")
                      for row in _read_csv_rows(downstream_path)}
        if set(downstream) != expected_periods:
            raise ValueError("Fresh downstream A Normal CSV has a different 82-month support")
        for period in expected_periods:
            if not math.isclose(downstream[period], normal_rows[period], rel_tol=1e-12, abs_tol=1e-10):
                raise ValueError(f"Fresh Normal score files disagree at {period}")
    # The original expected national target and anchor are authoritative. The
    # evaluator's duplicate fields must match before its centers are used.
    fresh_series = {str(row["period"]): row for row in _read_csv_rows(series_path) if row.get("task") == "A"}
    for row in original_rows:
        period = str(row["month"])
        fresh = fresh_series[period]
        for expected_key, fresh_key in (("truth_pp", "truth_pp"), ("baseline_pp", "anchor_pp")):
            old = _finite_number(row[expected_key], expected_key)
            new = _finite_number(fresh[fresh_key], fresh_key)
            if not math.isclose(old, new, rel_tol=0, abs_tol=1e-10):
                raise ValueError(f"Fresh evaluator changed the frozen {expected_key} target at {period}")
    return direct, normal_rows


def _stage_fresh_a(stage: Path, fresh_evaluation: Path) -> dict:
    cn_path = stage / CN_DIR / "monthly_public.csv"
    cn_rows = _read_csv_rows(cn_path)
    direct, normal = _load_fresh_centers(fresh_evaluation, cn_rows)
    for row in cn_rows:
        period = str(row["month"])
        row["before_model_pp"] = direct[period]
        row["expanded_model_pp"] = normal[period]
    with cn_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(cn_rows[0]))
        writer.writeheader()
        writer.writerows(cn_rows)
    cn_manifest_path = stage / CN_DIR / "manifest.json"
    cn_manifest = _read_json(cn_manifest_path)
    cn_manifest["files_sha256"]["monthly_public.csv"] = _sha256(cn_path)
    _write_json(cn_manifest_path, cn_manifest)
    return {
        "mode": "fresh_A_answer_centers_recalibrated",
        "fresh_evaluation_summary_sha256": _sha256(fresh_evaluation / "summary.json"),
        "fresh_monthly_series_sha256": _sha256(fresh_evaluation / "monthly_series.csv"),
        "fresh_normal_summary_sha256": _sha256(fresh_evaluation / "normal_summary.json"),
        "fresh_downstream_a_csv_sha256": _sha256(fresh_evaluation / "monthly_predictions_public.csv"),
        "fresh_a_core_months": len(direct),
        "fresh_a_normal_months": len(normal),
        "changed_cn_monthly_public_sha256": _sha256(cn_path),
        "frozen_truth_anchor_and_public_cpi_inputs_preserved": True,
        "reference_value_assertions_on_fresh_results": False,
    }


def _numeric_or_exact_equal(expected, actual, label, tolerance):
    if isinstance(expected, bool) or isinstance(actual, bool):
        if expected != actual:
            raise ValueError(f"Archived calibration mismatch at {label}: {expected!r} != {actual!r}")
        return
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if not (math.isfinite(float(expected)) and math.isfinite(float(actual))
                and math.isclose(float(expected), float(actual), rel_tol=tolerance[0], abs_tol=tolerance[1])):
            raise ValueError(f"Archived calibration numeric mismatch at {label}: {expected!r} != {actual!r}")
        return
    if type(expected) is not type(actual) or expected != actual:
        raise ValueError(f"Archived calibration mismatch at {label}: {expected!r} != {actual!r}")


def _compare_json(expected, actual, label, tolerance):
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(expected) != set(actual):
            raise ValueError(f"Archived calibration JSON keys changed at {label}")
        for key in expected:
            _compare_json(expected[key], actual[key], f"{label}.{key}", tolerance)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            raise ValueError(f"Archived calibration JSON list changed at {label}")
        for index, (left, right) in enumerate(zip(expected, actual)):
            _compare_json(left, right, f"{label}[{index}]", tolerance)
    else:
        _numeric_or_exact_equal(expected, actual, label, tolerance)


def _compare_csv(expected: Path, actual: Path, tolerance=(1e-10, 1e-12)) -> dict:
    left_rows, right_rows = _read_csv_rows(expected), _read_csv_rows(actual)
    if not left_rows or len(left_rows) != len(right_rows) or list(left_rows[0]) != list(right_rows[0]):
        raise ValueError(f"Archived calibration CSV shape changed: {expected.name}")
    for index, (left, right) in enumerate(zip(left_rows, right_rows)):
        for name in left:
            try:
                left_num, right_num = float(left[name]), float(right[name])
                if not (math.isfinite(left_num) and math.isfinite(right_num)
                        and math.isclose(left_num, right_num, rel_tol=tolerance[0], abs_tol=tolerance[1])):
                    raise ValueError(f"Archived CSV numeric mismatch {expected.name}:{index+2}:{name}")
            except ValueError as error:
                # Non-numeric strings (month/category labels) must match exactly.
                if "numeric mismatch" in str(error):
                    raise
                if left[name] != right[name]:
                    raise ValueError(f"Archived CSV value mismatch {expected.name}:{index+2}:{name}") from error
    return {"rows": len(left_rows), "columns": list(left_rows[0])}


def _verify_archived_run(stage: Path, result_path: Path) -> dict:
    comparisons = {}
    for name in ("protocol.json", "summary.json", "training_fits_sealed_before_later_scores.json"):
        expected = _read_json(stage / EXPECTED_DIR / name)
        actual = _read_json(result_path / name)
        _compare_json(expected, actual, name, (1e-10, 1e-12))
        comparisons[name] = {"status": "matched", "sha256_expected": _sha256(stage / EXPECTED_DIR / name),
                             "sha256_actual": _sha256(result_path / name)}
    expected_manifest = _read_json(stage / EXPECTED_DIR / "manifest.json")
    actual_manifest = _read_json(result_path / "manifest.json")
    if (expected_manifest.get("source_sha256") != actual_manifest.get("source_sha256")
            or set(expected_manifest.get("files_sha256", {})) != set(actual_manifest.get("files_sha256", {}))):
        raise ValueError("Archived calibration source hashes or output manifest shape changed")
    for filename, digest in actual_manifest["files_sha256"].items():
        if _sha256(result_path / filename) != digest:
            raise ValueError(f"Generated calibration manifest does not hash its output: {filename}")
    comparisons["manifest.json"] = {
        "status": "source_hashes_matched_and_generated_output_hashes_verified",
        "source_files": len(actual_manifest["source_sha256"]),
        "output_files": len(actual_manifest["files_sha256"]),
        "archived_manifest_sha256": _sha256(stage / EXPECTED_DIR / "manifest.json"),
        "generated_manifest_sha256": _sha256(result_path / "manifest.json"),
    }
    for name in ("monthly_inputs_public.csv", "monthly_predictions_public.csv"):
        comparisons[name] = {"status": "matched_numeric_tolerance",
                             **_compare_csv(stage / EXPECTED_DIR / name, result_path / name)}
    return {"status": "matched_archived_calibration", "rtol": 1e-10, "atol": 1e-12,
            "files": comparisons}


def replay(data, out, fresh_evaluation=None) -> dict:
    """Run the original calibration in an isolated source workspace.

    ``fresh_evaluation`` optionally points to a completed ``portable_evaluate``
    output. In that mode fresh A centers feed the original early48 fit and
    macro/ridge refit, while the exported data bundle remains untouched.
    """
    data = Path(data).expanduser().resolve()
    out = Path(out).expanduser().resolve()
    if not data.is_dir():
        raise FileNotFoundError(data)
    if out.exists():
        raise FileExistsError(f"Fresh calibration output path required: {out}")
    if out.is_relative_to(data):
        raise ValueError("Calibration replay output must not mutate the exported input bundle")
    package = _verify_bundle(data)
    fresh_evaluation = Path(fresh_evaluation).expanduser().resolve() if fresh_evaluation is not None else None
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="sce_portable_calibration_") as temp_name:
        stage = Path(temp_name) / "workspace"
        shutil.copytree(data, stage, dirs_exist_ok=False)
        mode = {"mode": "frozen_archived_A_aggregate_refit",
                "reference_value_assertions_on_fresh_results": False}
        if fresh_evaluation is not None:
            if not fresh_evaluation.is_dir():
                raise FileNotFoundError(fresh_evaluation)
            mode = _stage_fresh_a(stage, fresh_evaluation)
        internal_out = stage / "outputs" / out.name
        script = stage / "scripts/analyze_sce_full_a_macro_calibration.py"
        if not script.is_file():
            raise FileNotFoundError(script)
        completed = subprocess.run(
            [sys.executable, str(script), "--out", str(internal_out)],
            cwd=stage,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            raise RuntimeError(
                "Original offline calibration failed in isolated workspace.\n"
                + completed.stderr[-12000:]
            )
        if fresh_evaluation is None:
            comparison = _verify_archived_run(stage, internal_out)
        else:
            comparison = {"status": "not_compared_to_archived_results",
                          "reason": "Fresh answer centers were recalibrated; no expected-value assertions are made."}
        shutil.move(str(internal_out), str(out))
        receipt = {
            "schema": "sce_portable_macro_calibration_receipt/v1",
            "status": "completed_frozen_calibration_replay" if fresh_evaluation is None else "completed_fresh_A_recalibration",
            "original_program": "scripts/analyze_sce_full_a_macro_calibration.py",
            "original_evaluator": "studies/sce_inflation_expectations/evaluation/full_a_macro_calibration.py",
            "mode": mode,
            "reference_comparison": comparison,
            "input_bundle_manifest_sha256": _sha256(data / MANIFEST_NAME),
            "fresh_evaluation_input": str(fresh_evaluation) if fresh_evaluation else None,
            "fresh_evaluation_new_llm_or_network_calls": 0,
            "subprocess_stdout": completed.stdout.strip(),
            "subprocess_stderr": completed.stderr.strip(),
            "runtime": {"python": platform.python_version()},
        }
        _write_json(out / RECEIPT_NAME, receipt)
    original_summary = _read_json(out / "summary.json")
    return {
        "status": receipt["status"],
        "out": str(out),
        "comparison": comparison,
        "fits": original_summary.get("fits", {}),
        "results": original_summary.get("results", {}),
        "new_api_calls": 0,
        "new_q9_fits": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export", help="Export frozen source and public calibration inputs")
    export_parser.add_argument("--out", type=Path, required=True)
    export_parser.add_argument("--root", type=Path, default=ROOT)
    replay_parser = subparsers.add_parser("replay", help="Rerun original early48/macro calibration offline")
    replay_parser.add_argument("--data", type=Path, required=True, help="Calibration bundle root")
    replay_parser.add_argument("--out", type=Path, required=True)
    replay_parser.add_argument("--fresh-evaluation", type=Path,
                               help="Optional completed portable_evaluate result directory")
    args = parser.parse_args(argv)
    if args.command == "export":
        result = export(args.out, root=args.root)
        print(json.dumps({"status": result["status"], "out": str(args.out.resolve()),
                          "files": len(result["files"])}, ensure_ascii=False))
    else:
        result = replay(args.data, args.out, fresh_evaluation=args.fresh_evaluation)
        print(json.dumps({"status": result["status"], "out": result["out"],
                          "comparison": result["comparison"]["status"],
                          "new_api_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
