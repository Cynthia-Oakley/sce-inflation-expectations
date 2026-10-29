"""Rebuild outcome-free A inputs from the bundled public sources, offline.

This driver calls the study's original source extraction, prior labeling,
population/environment, grid/donor, family projection, prompt assembly, and
personal-cutoff preparation functions. It changes only output/path bindings;
the frozen A manifest supplies the registered 82-month scope and expected
prompt hashes. It never dispatches model requests or loads current truth files.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import shutil
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
A_REFERENCE_MANIFEST = Path("outputs/sce_full_a_personal_inputs_20261025_v1/manifest.json")
DEFAULT_RUN_NAME = "sce_portable_rebuild_20261029_v1"
OLD_MATERIALIZATION = Path("outputs/sce_fullperiod_data_20261021_v1")
B_NEWS_BASE = Path("outputs/sce_recent_b_news_refresh_20261025_v3")
B_REPAIR = Path("outputs/sce_recent_b_news_repair_20261026_v1/repair_manifest.json")
CPI_RELEASE_TABLE = Path("outputs/sce_full_a_macro_calibration_20261026_v1/monthly_inputs_public.csv")
PORTABLE_RELEASE_PROJECTION = Path("data/portable_metadata/cpi_release_schedule.csv")
WEEKLY_RELEASE_INPUT = Path("data/evaluation/sce_recent_b_evaluation_20261025_v1/aggregate_inputs.json")
WEEKLY_PE_ROOT = Path("outputs/sce_recent_b_recursion_terminal_20261026_v1/PE")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8")


def _stage(name: str, path: Path, detail: dict | None = None) -> dict:
    result = {"name": name, "path": str(path), "file_count": sum(p.is_file() for p in path.rglob("*")) if path.is_dir() else 0}
    if path.is_file():
        result.update(bytes=path.stat().st_size, sha256=sha256(path))
    if detail:
        result.update(detail)
    return result


def _prior_loader_bound_to_q9_cache(prior_module, q9_cache: Path):
    """Bind the original loader to the newly rebuilt cache without editing it."""
    source = inspect.getsource(prior_module.load_reference)
    old = 'cache = root / "outputs/sce_age_reporting_audit_20261012_v1/reference_private.parquet"'
    if source.count(old) != 1:
        raise RuntimeError("Original prior loader cache binding changed; review before running")
    source = source.replace(old, "cache = Path(_fresh_q9_cache).resolve()")
    namespace = dict(prior_module.__dict__)
    namespace["_fresh_q9_cache"] = Path(q9_cache).resolve()
    exec(compile(source, prior_module.__file__, "exec"), namespace)
    return namespace["load_reference"]


def _function_bound_to_food_catalog(function, food_catalog: Path):
    """Bind an original weekly function's fixed food-catalog input in memory."""
    source = inspect.getsource(function)
    old = "foods = load(ROOT / 'outputs/sce_fullperiod_materialized_20261022_v2/food_catalog.json')"
    if source.count(old) != 1:
        raise RuntimeError(f"Original {function.__module__}.{function.__name__} food-catalog binding changed")
    source = source.replace(old, "foods = load(Path(_fresh_food_catalog).resolve())")
    namespace = dict(function.__globals__)
    namespace["_fresh_food_catalog"] = Path(food_catalog).resolve()
    filename = inspect.getsourcefile(function) or function.__code__.co_filename
    exec(compile(source, filename, "exec"), namespace)
    return namespace[function.__name__]


def _b_assembler_bound_to_food_catalog(function, food_catalog: Path):
    """Bind the original B assembler's fixed P/E food input in memory."""
    source = inspect.getsource(function)
    old = "food_path=ROOT/'outputs/sce_fullperiod_materialized_20261022_v2/food_catalog.json'"
    if source.count(old) != 1:
        raise RuntimeError(f"Original {function.__module__}.{function.__name__} food-catalog binding changed")
    source = source.replace(old, "food_path=Path(_fresh_food_catalog).resolve()")
    namespace = dict(function.__globals__)
    namespace["_fresh_food_catalog"] = Path(food_catalog).resolve()
    filename = inspect.getsourcefile(function) or function.__code__.co_filename
    exec(compile(source, filename, "exec"), namespace)
    return namespace[function.__name__]


def _date_analyzer_bound_to_release_projection(function, release_projection: Path):
    """Bind the original B date analyzer to its two-column release input."""
    source = inspect.getsource(function)
    old = "macro=ROOT/'outputs/sce_full_a_macro_calibration_20261026_v1/monthly_inputs_public.csv'"
    if source.count(old) != 1:
        raise RuntimeError(f"Original {function.__module__}.{function.__name__} release binding changed")
    source = source.replace(old, "macro=Path(_fresh_release_projection).resolve()")
    namespace = dict(function.__globals__)
    namespace["_fresh_release_projection"] = Path(release_projection).resolve()
    filename = inspect.getsourcefile(function) or function.__code__.co_filename
    exec(compile(source, filename, "exec"), namespace)
    return namespace[function.__name__]


def rebuild_prior_reference(root: Path, out: Path) -> dict:
    """Re-extract the original Q9 cache and labeled panel from public xlsx files."""
    root, out = Path(root).resolve(), Path(out).resolve()
    if out.exists():
        raise FileExistsError(f"Prior output must be fresh: {out}")
    q9_cache = out / "q9_extraction"
    prior_path = out / "prior_preparation"
    q9_cache.mkdir(parents=True)
    prior_path.mkdir(parents=True)

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    age = importlib.import_module("studies.sce_inflation_expectations.age_reporting_audit")
    prior = importlib.import_module("studies.sce_inflation_expectations.prior_belief_preparation")

    # Original age/Q9 extraction checks the registered source hashes and uses
    # row IDs from the public micro files; it does not anonymize or relabel the
    # raw source values into generation prompts.
    _, q9_sources = age.load_reference(root, q9_cache)
    q9_path = q9_cache / "reference_private.parquet"
    q9_rows = len(__import__("pandas").read_parquet(q9_path, columns=["date", "userid"]))
    q9_receipt = {
        "cache_sha256": sha256(q9_path),
        "rows": q9_rows,
        "sources": q9_sources,
        "fields": list(age.FIELDS),
        "recreated_by": str(Path(age.__file__).resolve().relative_to(root)),
        "new_api_calls": 0,
    }
    _write_json(q9_cache / "extraction_receipt.json", q9_receipt)

    # The original loader has one fixed Q9 cache path. Evaluate its unchanged
    # source with that single binding redirected to this fresh extraction.
    # Its source hash, registry checks, raw XLSX supplement read, and merge all
    # remain the original implementation.
    load_reference = _prior_loader_bound_to_q9_cache(prior, q9_path)
    frame = load_reference(root, prior_path, reuse=None)
    labeled, panel_summary = prior.summarize_panel(frame, prior.MONTHS)
    labeled_path = prior_path / "labeled_reference_private.parquet"
    labeled.to_parquet(labeled_path, index=False)
    source_paths = [root / source["path"] for source in q9_sources]
    summary = {
        "status": "public_source_q9_extract_and_original_prior_panel_labels_rebuilt",
        "source_xlsx": [
            {"path": str(path.relative_to(root)), "sha256": sha256(path), "bytes": path.stat().st_size}
            for path in source_paths
        ],
        "q9_reference": {"rows": q9_rows,
                         "sha256": sha256(q9_path)},
        "labeled_reference": {"rows": len(labeled), "columns": list(labeled.columns),
                               "sha256": sha256(labeled_path)},
        "panel_summary": panel_summary,
        "projection_boundary": {
            "raw_public_workbooks_include_answer_columns": True,
            "answer_bearing_raw_source_role": "public source/evaluation material; not copied directly into generated messages",
            "A_fine_inputs_current_month_reads": ["date", "userid", "weight"],
            "A_fine_inputs_answer_history_filter": "date < target month",
            "personal_cutoff_date_projection": ["date", "userid", "survey_date"],
        },
        "new_api_calls": 0,
    }
    _write_json(out / "summary.json", summary)
    return {"q9_cache": q9_cache, "prior_output": prior_path, "labeled_reference": labeled_path,
            "summary": summary}


def _message_sha256(messages: object) -> str:
    payload = json.dumps(messages, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _compare_expected_prompts(expected_manifest: dict, output: Path,
                              expected_message_hashes: dict | Path | None = None) -> dict:
    """Compare exact per-agent messages and report serialized-file hashes separately.

    A prompts.json object can be semantically identical while its outer rows
    mapping has a different insertion order. The digest-only registry stores
    each frozen row's exact messages hash, so this comparison never needs to
    package the original prompt payloads.
    """
    expected_files = {relative: digest for relative, digest in expected_manifest.get("files_sha256", {}).items()
                      if str(relative).endswith("/prompts.json")}
    if isinstance(expected_message_hashes, (str, Path)):
        registry = _read_json(Path(expected_message_hashes))
    else:
        registry = expected_message_hashes or {}
    expected_months = registry.get("months", {})
    exact_file_matches, file_hash_differences, missing_files = [], [], []
    matching_messages = 0
    mismatched_messages, missing_messages, unexpected_messages = [], [], []

    for month, month_hashes in sorted(expected_months.items()):
        relative = f"{month}/prompts.json"
        path = Path(output) / relative
        if not path.is_file():
            missing_files.append(relative)
            missing_messages.extend(f"{month}/{agent_id}" for agent_id in month_hashes)
            continue
        observed_file = sha256(path)
        expected_file = expected_files.get(relative)
        file_row = {"path": relative, "expected_sha256": expected_file,
                    "observed_sha256": observed_file}
        if expected_file is not None and observed_file == expected_file:
            exact_file_matches.append(file_row)
        else:
            file_hash_differences.append(file_row)

        rows = _read_json(path).get("rows")
        if not isinstance(rows, dict):
            missing_messages.extend(f"{month}/{agent_id}" for agent_id in month_hashes)
            continue
        expected_ids = set(month_hashes)
        observed_ids = set(rows)
        missing_messages.extend(f"{month}/{agent_id}" for agent_id in sorted(expected_ids - observed_ids))
        unexpected_messages.extend(f"{month}/{agent_id}" for agent_id in sorted(observed_ids - expected_ids))
        for agent_id in sorted(expected_ids & observed_ids):
            row = rows[agent_id]
            messages = row.get("messages") if isinstance(row, dict) else None
            if not isinstance(messages, list):
                mismatched_messages.append(f"{month}/{agent_id}")
            elif _message_sha256(messages) == month_hashes[agent_id]:
                matching_messages += 1
            else:
                mismatched_messages.append(f"{month}/{agent_id}")

    expected_message_count = sum(len(month_hashes) for month_hashes in expected_months.values())
    complete_file_set = bool(expected_months) and not missing_files and len(expected_months) == len(expected_files)
    all_match = (complete_file_set and matching_messages == expected_message_count
                 and not mismatched_messages and not missing_messages and not unexpected_messages)
    return {
        "comparison_basis": "exact per-agent message-list SHA-256; outer JSON row ordering reported separately",
        "expected_prompt_month_count": len(expected_months),
        "exact_file_hash_match_count": len(exact_file_matches),
        "file_hash_difference_count": len(file_hash_differences),
        "missing_prompt_file_count": len(missing_files),
        "expected_message_count": expected_message_count,
        "matched_message_count": matching_messages,
        "mismatched_message_count": len(mismatched_messages),
        "missing_message_count": len(missing_messages),
        "unexpected_message_count": len(unexpected_messages),
        "exact_file_hash_matches": exact_file_matches,
        "file_hash_differences": file_hash_differences,
        "missing_prompt_files": missing_files,
        "mismatched_messages": mismatched_messages[:100],
        "missing_messages": missing_messages[:100],
        "unexpected_messages": unexpected_messages[:100],
        "all_match": all_match,
    }


def prepare_full_a(workspace_root: Path = REPOSITORY_ROOT, *, run_name: str = DEFAULT_RUN_NAME,
                   out: Path | None = None) -> dict:
    """Run the original 82-month A input chain in a fresh portable workspace."""
    root = Path(workspace_root).expanduser().resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    expected_path = root / A_REFERENCE_MANIFEST
    expected_manifest = _read_json(expected_path)
    months = [str(value) for value in expected_manifest.get("months", [])]
    if len(months) != 82 or len(set(months)) != 82:
        raise ValueError("Frozen expected manifest does not register the original 82-month A scope")
    run_root = (Path(out).expanduser().resolve() if out is not None else root / "outputs" / run_name)
    if not run_root.is_relative_to(root / "outputs"):
        raise ValueError("Portable preparation output must remain under workspace outputs")
    if run_root.exists():
        raise FileExistsError(f"Portable rebuild run path already exists: {run_root}")
    if not (root / OLD_MATERIALIZATION / "coverage.json").is_file():
        raise FileNotFoundError("Original full-period coverage/source seed is missing")
    run_root.mkdir(parents=True)

    modules = {
        key: importlib.import_module(module_name)
        for key, module_name in {
            "age": "studies.sce_inflation_expectations.age_reporting_audit",
            "prior": "studies.sce_inflation_expectations.prior_belief_preparation",
            "fine": "studies.sce_inflation_expectations.experiments.monthly_fine_inputs",
            "continuity": "studies.sce_inflation_expectations.experiments.state_continuity_inputs",
            "materializer": "studies.sce_inflation_expectations.experiments.fullperiod_materialization",
            "pipeline": "studies.sce_inflation_expectations.experiments.monthly_fine_pipeline",
            "personal": "studies.sce_inflation_expectations.experiments.full_a_personal_inputs",
            "timing": "studies.sce_inflation_expectations.experiments.media_timing_inputs",
        }.items()
    }
    prior_output = run_root / "prior_reference_rebuild"
    stages: list[dict] = []
    report_path = run_root / "portable_prepare_report.json"
    report = {
        "schema_version": 1,
        "status": "running_offline_source_rebuild",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "new_api_calls": 0,
        "workspace_root": str(root),
        "run_root": str(run_root),
        "expected_manifest": str(A_REFERENCE_MANIFEST),
        "months": months,
        "stages": stages,
        "answer_boundary": {
            "public_raw_sce_workbooks_are_answer_bearing": True,
            "raw_workbooks_are_source_material_separate_from_generated_prompts": True,
            "target_Q8_Q9_are_never_projected_into_A_generated_messages": True,
            "current_targets_remain_separate_evaluation_data": True,
        },
    }
    _write_json(report_path, report)

    # Bind all regenerated outputs inside this invocation's fresh run folder.
    old_constants = {
        "fine.FRAME": modules["fine"].FRAME,
        "continuity.FRAME": modules["continuity"].FRAME,
        "timing.FRAME": modules["timing"].FRAME,
        "timing.DELIVERY": modules["timing"].DELIVERY,
        "personal.FRAME": modules["personal"].FRAME,
        "personal.ASSEMBLY": modules["personal"].ASSEMBLY,
        "personal.OLD_INPUTS": modules["personal"].OLD_INPUTS,
        "personal.DELIVERY": modules["personal"].DELIVERY,
        "personal.DEFAULT_OUT": modules["personal"].DEFAULT_OUT,
    }
    try:
        ref = rebuild_prior_reference(root, prior_output)
        labeled_reference = ref["labeled_reference"]
        stages.append(_stage("raw_public_xlsx_to_q9_and_labeled_reference", prior_output,
                              {"labeled_reference_sha256": sha256(labeled_reference),
                               "source_row_count": ref["summary"]["labeled_reference"]["rows"]}))

        delivery = run_root / "fullperiod_materialized"
        if delivery.exists():
            raise FileExistsError(f"Expected fresh regenerated P/E output path: {delivery}")
        materialized = modules["materializer"].materialize(delivery)
        stages.append(_stage("original_fullperiod_population_and_environment_materialization", delivery, materialized))

        modules["fine"].FRAME = labeled_reference
        modules["continuity"].FRAME = labeled_reference
        modules["timing"].FRAME = labeled_reference
        modules["personal"].FRAME = labeled_reference

        fine_inputs = run_root / "monthly_fine_inputs"
        fine_summary = modules["fine"].prepare(fine_inputs, months=months, delivery=delivery)
        stages.append(_stage("original_54_cell_grid_and_past_only_donor_preparation", fine_inputs,
                             {"person_months": fine_summary["person_months"],
                              "score_cache": fine_summary["score_cache"],
                              "current_answer_columns_loaded": False}))

        families = run_root / "family_profile_projection"
        family_summary = modules["continuity"].prepare_families(fine_inputs, families, delivery=delivery)
        stages.append(_stage("original_pre_target_household_profile_projection", families,
                             {"source_rows": family_summary["rows"],
                              "physical_projection_excludes": family_summary["physical_projection_excludes"]}))

        assembly = run_root / "monthly_fine_assembly"
        assembly_summary = modules["pipeline"].assemble(
            fine_inputs,
            families,
            delivery,
            assembly,
            delivery=delivery,
            policy_supplement=root / "data/raw/sce_fullperiod_supplement_20261022/policy_sources_full_v2.json",
            confidence_supplement=root / "data/raw/sce_fullperiod_supplement_20261022/confidence_supplement.json",
        )
        stages.append(_stage("original_monthly_prompt_and_official_core_check", assembly,
                             {"official_core": assembly_summary.get("official_core"),
                              "new_api_calls": assembly_summary.get("new_api_calls")}))

        modules["personal"].ASSEMBLY = assembly
        modules["personal"].OLD_INPUTS = fine_inputs
        modules["personal"].DELIVERY = delivery
        modules["timing"].DELIVERY = delivery
        personal_out = run_root / "personal_cutoff_A_inputs"
        modules["personal"].prepare(personal_out)
        expected_message_registry = root / "data/portable_metadata/a_prompt_message_hashes.json"
        if not expected_message_registry.is_file():
            raise FileNotFoundError(f"Digest-only A prompt reference registry is missing: {expected_message_registry}")
        prompt_comparison = _compare_expected_prompts(expected_manifest, personal_out, expected_message_registry)
        stages.append(_stage("original_personal_completion_cutoff_and_prompt_preparation", personal_out,
                             {"prompt_hash_comparison": prompt_comparison}))

        report.update(status="complete" if prompt_comparison["all_match"] else "complete_with_prompt_hash_differences",
                      completed_at_utc=datetime.now(timezone.utc).isoformat(),
                      stages=stages, prompt_hash_comparison=prompt_comparison,
                      outputs={"prior_reference": str(labeled_reference.relative_to(root)),
                               "fullperiod": str(delivery.relative_to(root)),
                               "monthly_fine_inputs": str(fine_inputs.relative_to(root)),
                               "families": str(families.relative_to(root)),
                               "assembly": str(assembly.relative_to(root)),
                               "personal_cutoff_inputs": str(personal_out.relative_to(root))})
        _write_json(report_path, report)
        return report
    except Exception as exc:
        report.update(status="failed", failed_at_utc=datetime.now(timezone.utc).isoformat(),
                      failure={"type": type(exc).__name__, "message": str(exc)}, stages=stages)
        _write_json(report_path, report)
        raise
    finally:
        modules["fine"].FRAME = old_constants["fine.FRAME"]
        modules["continuity"].FRAME = old_constants["continuity.FRAME"]
        modules["timing"].FRAME = old_constants["timing.FRAME"]
        modules["timing"].DELIVERY = old_constants["timing.DELIVERY"]
        modules["personal"].FRAME = old_constants["personal.FRAME"]
        modules["personal"].ASSEMBLY = old_constants["personal.ASSEMBLY"]
        modules["personal"].OLD_INPUTS = old_constants["personal.OLD_INPUTS"]
        modules["personal"].DELIVERY = old_constants["personal.DELIVERY"]
        modules["personal"].DEFAULT_OUT = old_constants["personal.DEFAULT_OUT"]


def _compare_manifest_files(expected_manifest_path: Path, output: Path, *, prefixes: tuple[str, ...]) -> dict:
    expected = _read_json(expected_manifest_path).get("files_sha256", {})
    selected = {relative: digest for relative, digest in expected.items()
                if str(relative).startswith(prefixes)
                and Path(str(relative)).name != "summary.json"}
    matches, semantic_matches, mismatches, missing = [], [], [], []
    for relative, digest in sorted(selected.items()):
        path = output / relative
        if not path.is_file():
            missing.append(relative)
        else:
            observed = sha256(path)
            row = {"path": relative, "expected_sha256": digest, "observed_sha256": observed}
            if observed == digest:
                matches.append(row)
            elif str(relative).endswith(".json"):
                if _read_json(path) == _read_json(expected_manifest_path.parent / relative):
                    semantic_matches.append(row)
                else:
                    mismatches.append(row)
            else:
                mismatches.append(row)
    successful = len(matches) + len(semantic_matches)
    return {"comparison_basis": "raw SHA-256, with parsed JSON equality for mapping-order differences",
            "expected_file_count": len(selected), "matched_file_count": successful,
            "exact_file_hash_match_count": len(matches),
            "semantic_json_match_count": len(semantic_matches),
            "mismatched_file_count": len(mismatches), "missing_file_count": len(missing),
            "exact_matches": matches, "semantic_json_matches": semantic_matches,
            "mismatches": mismatches, "missing": missing,
            "manifest_report_files_excluded": [relative for relative in expected
                                                 if str(relative).startswith(prefixes)
                                                 and Path(str(relative)).name == "summary.json"],
            "all_match": bool(selected) and successful == len(selected)}


def prepare_b(workspace_root: Path, out: Path, *, prior_reference: Path,
              food_catalog: Path) -> dict:
    """Rebuild B dates, candidate matching, and prompts with original functions."""
    root, out, prior_reference = map(lambda value: Path(value).resolve(),
                                     (workspace_root, out, prior_reference))
    if not out.is_relative_to(root / "outputs"):
        raise ValueError("B preparation output must remain under workspace outputs")
    if out.exists():
        raise FileExistsError(f"B preparation output must be fresh: {out}")
    out.mkdir(parents=True)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    # The original date-distribution analysis projects date, interview day,
    # and weight from the raw public SCE panel, then reads just CPI release
    # dates from this two-column public projection.
    schedule_path = root / PORTABLE_RELEASE_PROJECTION
    if not schedule_path.is_file():
        raise FileNotFoundError(f"Public CPI release-date projection is missing: {schedule_path}")
    food_path = Path(food_catalog).resolve()
    if not food_path.is_file() or not food_path.is_relative_to(root):
        raise FileNotFoundError(f"A freshly materialized workspace-local food catalog is required: {food_path}")
    date_module = importlib.import_module(
        "studies.sce_inflation_expectations.evaluation.response_date_distribution"
    )
    b_module = importlib.import_module(
        "studies.sce_inflation_expectations.experiments.recent_b_sampled_dates"
    )
    old_frame, old_base, old_date_source = date_module.FRAME, date_module.B_INPUT, b_module.DATE_SOURCE
    date_distribution = out / "response_date_distribution"
    date_plan = out / "sampled_date_plan"
    b_assembly = out / "sampled_B_generation_inputs"
    try:
        date_module.FRAME = prior_reference
        date_module.B_INPUT = root / B_NEWS_BASE
        _date_analyzer_bound_to_release_projection(date_module.analyze, schedule_path)(date_distribution)
        b_module.BASE = root / B_NEWS_BASE
        b_module.DATE_SOURCE = date_distribution
        b_module.prepare_dates(date_plan, lag_months=12)
        _b_assembler_bound_to_food_catalog(b_module.assemble, food_path)(
            date_plan, b_assembly, repair_manifest=root / B_REPAIR
        )
    finally:
        date_module.FRAME, date_module.B_INPUT = old_frame, old_base
        b_module.DATE_SOURCE = old_date_source

    prompt_hashes = _compare_manifest_files(
        root / "outputs/sce_recent_b_sampled_dates_complete_20261026_v1/manifest.json",
        b_assembly,
        prefixes=("prompts/", "inputs/"),
    )
    report = {
        "status": "B_original_date_distribution_matching_and_prompt_functions_rebuilt_offline",
        "new_api_calls": 0,
        "sources": {"prior_reference": str(prior_reference.relative_to(root)),
                    "public_cpi_release_projection": str(schedule_path.relative_to(root)),
                    "B_candidates": str(B_NEWS_BASE), "repair_overlay": str(B_REPAIR),
                    "fresh_food_catalog": str(food_path.relative_to(root))},
        "outputs": {"response_date_distribution": str(date_distribution.relative_to(root)),
                    "sampled_date_plan": str(date_plan.relative_to(root)),
                    "generation_inputs": str(b_assembly.relative_to(root))},
        "expected_prompt_hash_comparison": prompt_hashes,
    }
    _write_json(out / "portable_B_prepare_report.json", report)
    return report


def prepare_weekly(workspace_root: Path, out: Path, *, release_input: Path | None = None,
                   food_catalog: Path) -> dict:
    """Rebuild weekly roster, dated anchors, state cycles, news matching and prompts."""
    root, out = Path(workspace_root).resolve(), Path(out).resolve()
    if not out.is_relative_to(root / "outputs"):
        raise ValueError("Weekly preparation output must remain under workspace outputs")
    if out.exists():
        raise FileExistsError(f"Weekly preparation output must be fresh: {out}")
    out.mkdir(parents=True)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    release_path = Path(release_input).resolve() if release_input is not None else root / WEEKLY_RELEASE_INPUT
    if not release_path.is_file() or not release_path.is_relative_to(root):
        raise FileNotFoundError(f"A workspace-local dated public anchor table is required: {release_path}")
    food_path = Path(food_catalog).resolve()
    if not food_path.is_file() or not food_path.is_relative_to(root):
        raise FileNotFoundError(f"A freshly materialized workspace-local food catalog is required: {food_path}")

    preflight = importlib.import_module("studies.sce_inflation_expectations.experiments.weekly_preflight")
    weekly = importlib.import_module("studies.sce_inflation_expectations.experiments.weekly_inputs")
    original_release_path = preflight.RELEASES
    try:
        preflight.RELEASES = release_path
        preflight_output = out / "weekly_preflight"
        weekly_output = out / "weekly_generation_inputs"
        _function_bound_to_food_catalog(preflight.prepare, food_path)(preflight_output, n=300)
        _function_bound_to_food_catalog(weekly.prepare, food_path)(
            preflight_output, weekly_output, official_core=True
        )
    finally:
        preflight.RELEASES = original_release_path

    comparisons = _compare_manifest_files(
        root / "outputs/sce_weekly_inputs_20261027_v2/manifest.json",
        weekly_output,
        prefixes=("weeks/", "priors/"),
    )
    report = {
        "status": "weekly_original_preflight_prior_cycle_and_prompt_functions_rebuilt_offline",
        "new_api_calls": 0,
        "dated_anchor_source": str(release_path.relative_to(root)),
        "fresh_food_catalog_source": str(food_path.relative_to(root)),
        "dated_anchor_projection": "weekly_preflight reads only headline_releases and weekly_release_protocol enforces release time <= each cutoff",
        "outputs": {"preflight": str(preflight_output.relative_to(root)),
                    "generation_inputs": str(weekly_output.relative_to(root))},
        "expected_template_hash_comparison": comparisons,
    }
    _write_json(out / "portable_weekly_prepare_report.json", report)
    return report


def prepare(workspace_root: Path, out: Path, *, task: str = "all",
            release_input: Path | None = None) -> dict:
    """Run selected original offline preparation stages in a fresh workspace."""
    root, out = Path(workspace_root).expanduser().resolve(), Path(out).expanduser()
    if not out.is_absolute():
        out = root / out
    out = out.resolve()
    if not out.is_relative_to(root / "outputs"):
        raise ValueError("--out must be a fresh path under <workspace>/outputs")
    if task not in {"a", "b", "weekly", "all"}:
        raise ValueError("task must be a, b, weekly, or all")
    if out.exists():
        raise FileExistsError(f"Portable preparation output must be fresh: {out}")
    out.mkdir(parents=True)
    stages = {}
    fresh_inputs = {
        "a_personal_cutoff": None,
        "a_assembly": None,
        "b_generation_inputs": None,
        "b_prompts": None,
        "weekly_inputs": None,
    }
    prior_reference = None
    fullperiod_delivery = None
    if task in {"a", "all"}:
        a_report = prepare_full_a(root, out=out / "a")
        stages["a"] = {"status": a_report["status"], "report": str((out / "a/portable_prepare_report.json").relative_to(root))}
        prior_reference = root / a_report["outputs"]["prior_reference"]
        fullperiod_delivery = root / a_report["outputs"]["fullperiod"]
        fresh_inputs["a_personal_cutoff"] = a_report["outputs"]["personal_cutoff_inputs"]
        fresh_inputs["a_assembly"] = a_report["outputs"]["assembly"]
    if task == "b":
        prior_dir = out / "prior_preparation"
        prior_result = rebuild_prior_reference(root, prior_dir)
        prior_reference = prior_result["labeled_reference"]
        fullperiod_delivery = out / "fullperiod_materialized"
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        materializer = importlib.import_module(
            "studies.sce_inflation_expectations.experiments.fullperiod_materialization"
        )
        stages["fullperiod_materialization"] = materializer.materialize(fullperiod_delivery)
    if task in {"b", "all"}:
        assert fullperiod_delivery is not None
        b_report = prepare_b(
            root, out / "b", prior_reference=prior_reference,
            food_catalog=fullperiod_delivery / "food_catalog.json",
        )
        stages["b"] = b_report
        b_generation = b_report["outputs"]["generation_inputs"]
        fresh_inputs["b_generation_inputs"] = b_generation
        # The B generator stores period directories under its prompts/ child;
        # the adopter consumes the period root, not the enclosing manifest root.
        fresh_inputs["b_prompts"] = str(Path(b_generation) / "prompts")
    if task == "weekly":
        fullperiod_delivery = out / "fullperiod_materialized"
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        materializer = importlib.import_module(
            "studies.sce_inflation_expectations.experiments.fullperiod_materialization"
        )
        stages["fullperiod_materialization"] = materializer.materialize(fullperiod_delivery)
    if task in {"weekly", "all"}:
        assert fullperiod_delivery is not None
        weekly_report = prepare_weekly(
            root, out / "weekly", release_input=release_input,
            food_catalog=fullperiod_delivery / "food_catalog.json",
        )
        stages["weekly"] = weekly_report
        fresh_inputs["weekly_inputs"] = weekly_report["outputs"]["generation_inputs"]
    hash_comparisons = {}
    if "a" in stages:
        hash_comparisons["a"] = a_report["prompt_hash_comparison"]
    if "b" in stages:
        hash_comparisons["b"] = stages["b"]["expected_prompt_hash_comparison"]
    if "weekly" in stages:
        hash_comparisons["weekly"] = stages["weekly"]["expected_template_hash_comparison"]
    hashes_match = bool(hash_comparisons) and all(
        item.get("all_match", False) for item in hash_comparisons.values()
    )
    preparation_status = "complete" if hashes_match else "complete_with_hash_differences"
    index = {
        "schema_version": 1,
        "status": preparation_status,
        "execution_complete": True,
        "all_expected_hashes_match": hashes_match,
        "task": task,
        "workspace_root": str(root),
        "output_root": str(out.relative_to(root)),
        "fresh_inputs": fresh_inputs,
        "hash_comparisons": hash_comparisons,
        "absolute_paths": {
            key: (str(root / value) if value is not None else None)
            for key, value in fresh_inputs.items()
        },
        "reports": {
            "a": str((out / "a/portable_prepare_report.json").relative_to(root)) if "a" in stages else None,
            "b": str((out / "b/portable_B_prepare_report.json").relative_to(root)) if "b" in stages else None,
            "weekly": str((out / "weekly/portable_weekly_prepare_report.json").relative_to(root)) if "weekly" in stages else None,
        },
    }
    _write_json(out / "preparation_index.json", index)
    result = {
        "schema_version": 1,
        "status": preparation_status,
        "execution_complete": True,
        "all_expected_hashes_match": hashes_match,
        "task": task,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(root),
        "output_root": str(out.relative_to(root)),
        "new_api_calls": 0,
        "stages": stages,
        "preparation_index": str((out / "preparation_index.json").relative_to(root)),
        "limitations": [
            "Full-period coverage and the 201906 environment schema plus three original sample persona rows remain the registered historical seeds used by fullperiod_materialization.",
            "B and weekly rebuilt prompts are compared with, but are not replaced by, their archived original hash manifests.",
            "Weekly public headline releases are read from the separate anchor table; only releases published by each cutoff enter prompt construction.",
        ],
    }
    _write_json(out / "portable_prepare_report.json", result)
    return result


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--task", choices=("a", "b", "weekly", "all"), default="all")
    parser.add_argument("--release-input", type=Path,
                        help="Optional workspace-local public anchor table for weekly preparation")
    args = parser.parse_args(argv)
    result = prepare(args.workspace, args.out, task=args.task, release_input=args.release_input)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
