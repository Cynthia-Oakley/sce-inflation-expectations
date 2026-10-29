#!/usr/bin/env python3
"""Export and replay the frozen offline SCE downstream regression.

The original panel builder and evaluator remain the source of truth. This
module only stages their inputs, invokes those scripts in fresh Python
processes, and checks the replay against the archived complete result tables.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RAW_DATA_ROOT = Path("outputs/sce_downstream_data_20261026_v1")
REGRESSION_OUTPUT_ROOT = Path("outputs/sce_downstream_regression_20261027_v1")
FROZEN_A_INPUT = Path("outputs/sce_full_a_macro_calibration_20261026_v1/monthly_predictions_public.csv")
FROZEN_B_INPUT = Path("outputs/sce_recent_b_core_normal_evaluation_20261026_v1/monthly_national.csv")
PROTOCOL = Path("docs/workstreams/20261026_downstream/regression_protocol.json")

# These are the 14 public source/derived series files plus the four manifests
# the original builder reads to validate them. Keep the list explicit so a
# package cannot silently gain unrelated repository data.
RAW_FILES = (
    "wages/wage-growth-data.xlsx",
    "wages/wage_growth_overall.csv",
    "wages/manifest.json",
    "durables/PCEDGC96.csv",
    "durables/manifest.json",
    "credit/REVOLSL.csv",
    "credit/TERMCBCCINTNS.csv",
    "credit/TERMCBCCALLNS.csv",
    "credit/manifest.json",
    "expectations/MICH.csv",
    "expectations/manifest.json",
    "controls/UNRATE.csv",
    "controls/JTSJOL.csv",
    "controls/DSPIC96.csv",
    "controls/CPIAUCSL.csv",
    "controls/CPILFESL.csv",
    "controls/UMCSENT.csv",
    "controls/FEDFUNDS.csv",
    "controls/manifest.json",
)
SOURCE_FILES = (
    Path("scripts/prepare_sce_downstream_data.py"),
    Path("scripts/analyze_sce_downstream_regression.py"),
    Path("studies/sce_inflation_expectations/evaluation/downstream_regression.py"),
    Path("studies/sce_inflation_expectations/submission_tools/portable_downstream.py"),
    PROTOCOL,
)
FROZEN_FILES = (
    "predictions.csv",
    "model_metrics.csv",
    "in_sample_metrics.csv",
    "contrasts.csv",
    "coverage.csv",
    "key_contrasts.csv",
)
DEPENDENCIES = ("numpy", "pandas", "matplotlib")
MIN_TRAIN = 36
MANIFEST_NAME = "portable_downstream_manifest.json"
VERIFICATION_NAME = "portable_verification.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _copy_hashed(source: Path, destination: Path, records: dict, role: str, relative_path: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Required {role} file is missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    records[Path(relative_path).as_posix()] = {
        "role": role,
        "sha256": sha256(destination),
        "bytes": destination.stat().st_size,
    }


def _distribution_versions() -> dict[str, str]:
    versions = {}
    for distribution in DEPENDENCIES:
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = "not-installed-at-export"
    return versions


def export(out, root=REPOSITORY_ROOT):
    """Create a self-contained, explicitly hashed offline reproduction bundle.

    The destination is a bundle root: it contains the minimal original source
    tree under ``scripts/``, ``studies/`` and ``docs/``, source data under
    ``data/raw/``, frozen A/B aggregates under ``data/frozen_inputs/``, and
    full archived reference tables under ``data/expected/``.
    """
    root = Path(root).resolve()
    out = Path(out).expanduser().resolve()
    if out.exists():
        if not out.is_dir() or any(out.iterdir()):
            raise FileExistsError(f"Refusing to overwrite non-empty bundle path: {out}")
    required_sources = [root / relative for relative in SOURCE_FILES]
    required_inputs = [root / RAW_DATA_ROOT / relative for relative in RAW_FILES]
    required_inputs.extend(
        [
            root / FROZEN_A_INPUT,
            root / FROZEN_B_INPUT,
            *(root / REGRESSION_OUTPUT_ROOT / name for name in FROZEN_FILES),
        ]
    )
    missing = [path for path in [*required_sources, *required_inputs] if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Required portable downstream files are missing: {missing}")
    out.mkdir(parents=True, exist_ok=True)

    files = {}
    for relative in SOURCE_FILES:
        _copy_hashed(root / relative, out / relative, files, "source", relative)

    raw_root = root / RAW_DATA_ROOT
    for relative in RAW_FILES:
        destination_relative = Path("data/raw") / relative
        _copy_hashed(raw_root / relative, out / destination_relative, files, "public_raw_input", destination_relative)

    _copy_hashed(
        root / FROZEN_A_INPUT,
        out / "data/frozen_inputs/a_monthly_predictions_public.csv",
        files,
        "frozen_a_aggregate_input",
        Path("data/frozen_inputs/a_monthly_predictions_public.csv"),
    )
    _copy_hashed(
        root / FROZEN_B_INPUT,
        out / "data/frozen_inputs/b_monthly_national.csv",
        files,
        "frozen_b_aggregate_input",
        Path("data/frozen_inputs/b_monthly_national.csv"),
    )
    expected_root = root / REGRESSION_OUTPUT_ROOT
    for name in FROZEN_FILES:
        destination_relative = Path("data/expected") / name
        _copy_hashed(expected_root / name, out / destination_relative, files, "archived_reference_output", destination_relative)

    manifest = {
        "schema_version": 1,
        "status": "offline_downstream_reproduction_bundle",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "Reuse the original monthly-panel builder and frozen expanding-window OLS regression; no refit or model search is introduced.",
        "network_or_paid_calls": 0,
        "source_root_layout": "Original repository-relative paths are preserved at bundle root for source_root portability.",
        "protocol": PROTOCOL.as_posix(),
        "raw_source_file_count": 14,
        "raw_series_count": 13,
        "required_public_raw_series": [Path(path).stem for path in RAW_FILES if path.endswith(".csv") and not path.endswith("manifest.json")],
        "frozen_aggregate_inputs": {
            "A": "data/frozen_inputs/a_monthly_predictions_public.csv",
            "B": "data/frozen_inputs/b_monthly_national.csv",
        },
        "expected_reference_outputs": [f"data/expected/{name}" for name in FROZEN_FILES],
        "comparison": {
            "mode": "complete_table_numeric_tolerance",
            "rtol": 1e-10,
            "atol": 1e-12,
            "tables": list(FROZEN_FILES),
            "includes_every_prediction_and_both_signs_of_every_contrast": True,
        },
        "dependencies": {
            "python_at_export": sys.version.split()[0],
            "packages": _distribution_versions(),
            "required": ["Python 3", *DEPENDENCIES],
        },
        "files": files,
    }
    _write_json(out / MANIFEST_NAME, manifest)
    _write_json(
        out / "REPRODUCTION.json",
        {
            "command": (
                "python studies/sce_inflation_expectations/submission_tools/portable_downstream.py "
                "replay --data data --out outputs/downstream_replay"
            ),
            "api": "replay(data, out, source_root=bundle_root)",
            "offline": True,
            "frozen_inputs_are_verified_against_archived_complete_tables": True,
            "custom_monthly_a_b_inputs": "Pass both --a and --b with --no-verify; these are new analyses and are not the frozen-score reproduction.",
        },
    )
    return out


def _package_root_from_data(data: Path) -> Path:
    data = Path(data).expanduser().resolve()
    if (data / "raw").is_dir():
        return data
    if (data / "data/raw").is_dir():
        return data / "data"
    raise FileNotFoundError(f"Cannot find data/raw under {data}")


def _resolve_source_root(source_root, data_root: Path) -> Path:
    if source_root is not None:
        candidate = Path(source_root).expanduser().resolve()
    else:
        candidate = Path(__file__).resolve().parents[3]
        if not (candidate / "scripts/analyze_sce_downstream_regression.py").is_file():
            candidate = data_root.parent
    required = (
        Path("scripts/prepare_sce_downstream_data.py"),
        Path("scripts/analyze_sce_downstream_regression.py"),
        PROTOCOL,
    )
    missing = [str(path) for path in required if not (candidate / path).is_file()]
    if missing:
        raise FileNotFoundError(f"source_root {candidate} is missing required files: {missing}")
    return candidate


def _verify_bundle_manifest(source_root: Path) -> dict | None:
    manifest_path = source_root / MANIFEST_NAME
    if not manifest_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for relative, record in manifest["files"].items():
        path = source_root / relative
        if not path.is_file():
            raise FileNotFoundError(f"Bundle file missing: {relative}")
        actual = sha256(path)
        if actual != record["sha256"]:
            raise ValueError(f"Bundle hash mismatch for {relative}: {actual} != {record['sha256']}")
    return manifest


def _run_script(command: list[str], label: str) -> subprocess.CompletedProcess:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"{label} failed with exit {completed.returncode}: {detail}")
    return completed


def _compare_tables(actual_root: Path, expected_root: Path, tolerance: dict) -> list[dict]:
    try:
        import pandas as pd
        from pandas.testing import assert_frame_equal
    except ImportError as error:
        raise RuntimeError("Portable downstream comparison requires pandas") from error

    results = []
    for name in FROZEN_FILES:
        actual_path = actual_root / name
        expected_path = expected_root / name
        if not actual_path.is_file() or not expected_path.is_file():
            raise FileNotFoundError(f"Missing replay/reference table: {actual_path} / {expected_path}")
        actual = pd.read_csv(actual_path)
        expected = pd.read_csv(expected_path)
        try:
            assert_frame_equal(
                actual,
                expected,
                check_dtype=False,
                check_exact=False,
                check_like=False,
                rtol=tolerance["rtol"],
                atol=tolerance["atol"],
            )
        except AssertionError as error:
            raise ValueError(f"Archived downstream table differs: {name}: {error}") from error
        results.append({
            "file": name,
            "status": "matched",
            "rows": len(actual),
            "columns": list(actual.columns),
            "actual_sha256": sha256(actual_path),
            "reference_sha256": sha256(expected_path),
            "byte_identical": actual_path.read_bytes() == expected_path.read_bytes(),
        })
    return results


def replay(
    data,
    out,
    source_root=None,
    *,
    a_input=None,
    b_input=None,
    verify_reference=True,
):
    """Rebuild the panel, rerun the original regression, and verify the result.

    ``data`` can be either a bundle's ``data/`` directory or the bundle root.
    ``source_root`` points at the package root containing the preserved
    original ``scripts/``, ``studies/`` and protocol paths. To explore newly
    produced monthly A/B aggregates, pass both ``a_input`` and ``b_input`` and
    set ``verify_reference=False`` explicitly; the run is then recorded as an
    unverified new analysis.
    """
    data_root = _package_root_from_data(Path(data))
    source = _resolve_source_root(source_root, data_root)
    custom_inputs = a_input is not None or b_input is not None
    if custom_inputs and (a_input is None or b_input is None):
        raise ValueError("Provide both a_input and b_input for a new A/B aggregate analysis")
    if custom_inputs and verify_reference:
        raise ValueError("Custom A/B aggregates require verify_reference=False; frozen-score comparison does not apply")
    out = Path(out).expanduser().resolve()
    if out.exists():
        raise FileExistsError(f"Replay output must not already exist: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)

    bundle_root = data_root.parent
    data_manifest = _verify_bundle_manifest(bundle_root)
    source_manifest = data_manifest if source == bundle_root else _verify_bundle_manifest(source)
    if verify_reference:
        source_records = (data_manifest or source_manifest or {}).get("files", {})
        for relative in SOURCE_FILES:
            expected = source_records.get(relative.as_posix())
            source_path = source / relative
            if expected is not None and sha256(source_path) != expected["sha256"]:
                raise ValueError(f"Used source differs from the hashed reproduction bundle: {relative}")
    if verify_reference and not (data_root / "expected").is_dir():
        raise FileNotFoundError(f"Frozen comparison tables are missing below {data_root / 'expected'}")

    a_path = Path(a_input).expanduser().resolve() if custom_inputs else data_root / "frozen_inputs/a_monthly_predictions_public.csv"
    b_path = Path(b_input).expanduser().resolve() if custom_inputs else data_root / "frozen_inputs/b_monthly_national.csv"
    for label, path in (("A aggregate input", a_path), ("B aggregate input", b_path)):
        if not path.is_file():
            raise FileNotFoundError(f"Missing {label}: {path}")

    panel_script = source / "scripts/prepare_sce_downstream_data.py"
    regression_script = source / "scripts/analyze_sce_downstream_regression.py"
    protocol_path = source / PROTOCOL
    with tempfile.TemporaryDirectory(prefix="sce-downstream-replay-") as temp:
        temp_root = Path(temp)
        panel_out = temp_root / "data_assembly"
        panel_build = _run_script(
            [
                sys.executable,
                str(panel_script),
                "--raw-root",
                str(data_root / "raw"),
                "--out",
                str(panel_out),
            ],
            "Original public-data panel builder",
        )
        analysis = _run_script(
            [
                sys.executable,
                str(regression_script),
                "--panel",
                str(panel_out / "monthly_panel.csv"),
                "--a",
                str(a_path),
                "--b",
                str(b_path),
                "--protocol",
                str(protocol_path),
                "--min-train",
                str(MIN_TRAIN),
                "--out",
                str(out),
            ],
            "Original expanding-window regression",
        )
        shutil.copytree(panel_out, out / "reconstructed_data")

    comparisons = []
    tolerance = {"rtol": 1e-10, "atol": 1e-12}
    if verify_reference:
        comparisons = _compare_tables(out, data_root / "expected", tolerance)

    record = {
        "status": "completed_and_verified" if verify_reference else "completed_unverified_new_analysis",
        "network_or_paid_calls": 0,
        "method": "Original public-series panel assembly followed by the unchanged original expanding-window OLS evaluator.",
        "source_root": str(source),
        "source_root_relative_to_bundle": "." if source == bundle_root else None,
        "data_root": str(data_root),
        "raw_input_files_sha256": {
            str(Path("raw") / relative): sha256(data_root / "raw" / relative)
            for relative in RAW_FILES
        },
        "frozen_or_custom_aggregate_inputs": {
            "A": {"path": str(a_path), "sha256": sha256(a_path), "custom": custom_inputs},
            "B": {"path": str(b_path), "sha256": sha256(b_path), "custom": custom_inputs},
        },
        "protocol_sha256": sha256(protocol_path),
        "source_code_sha256": {
            str(relative): sha256(source / relative)
            for relative in SOURCE_FILES
            if (source / relative).is_file()
        },
        "panel_builder_stdout": panel_build.stdout.strip(),
        "regression_stdout": analysis.stdout.strip(),
        "min_train": MIN_TRAIN,
        "reference_comparison": {
            "performed": bool(verify_reference),
            "mode": "complete_table_numeric_tolerance" if verify_reference else "not_applicable_to_custom_inputs",
            **tolerance,
            "tables": comparisons,
        },
        "output_sha256": {
            path.relative_to(out).as_posix(): sha256(path)
            for path in sorted(out.rglob("*"))
            if path.is_file() and path.name != VERIFICATION_NAME
        },
    }
    _write_json(out / VERIFICATION_NAME, record)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export", help="Build a hashed offline reproduction bundle")
    export_parser.add_argument("--out", type=Path, required=True)
    export_parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    replay_parser = subparsers.add_parser("replay", help="Rebuild public data and replay regression")
    replay_parser.add_argument("--data", type=Path, required=True, help="Bundle data/ directory or bundle root")
    replay_parser.add_argument("--out", type=Path, required=True)
    replay_parser.add_argument("--source-root", type=Path)
    replay_parser.add_argument("--a", type=Path, help="Optional new monthly A aggregate CSV")
    replay_parser.add_argument("--b", type=Path, help="Optional new monthly B aggregate CSV")
    replay_parser.add_argument("--no-verify", action="store_true", help="Required with custom A/B input files")
    args = parser.parse_args(argv)
    if args.command == "export":
        result = export(args.out, root=args.root)
        print(json.dumps({"status": "ok", "bundle": str(result)}, ensure_ascii=False))
    else:
        result = replay(
            args.data,
            args.out,
            source_root=args.source_root,
            a_input=args.a,
            b_input=args.b,
            verify_reference=not args.no_verify,
        )
        print(json.dumps({"status": result["status"], "out": str(Path(args.out).resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
