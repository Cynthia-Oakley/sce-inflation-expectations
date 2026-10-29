"""Build an allowlisted local review bundle without modifying frozen studies."""
from datetime import datetime, timezone
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies/sce_inflation_expectations"
TEMPLATES = ROOT / "submission/package_templates"
A_SOURCE = ROOT / "outputs/sce_fullperiod_analysis_20261024_v1"
B_SOURCE = ROOT / "outputs/sce_recent_b_readout_20261025_v2"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def _source_files():
    # Explicit code-only roots/suffix. No outputs, raw data, population cache,
    # prompts, credentials, personal trajectories or entire third-party repo.
    files = list(STUDY.rglob("*.py")) + list((ROOT / "scripts").glob("*.py"))
    return sorted(p for p in files if p.is_file() and "__pycache__" not in p.parts)


def _source_bytes(src):
    if src.is_symlink() or not src.resolve().is_relative_to(ROOT):
        raise ValueError("Source symlink/outside project not allowed")
    content = src.read_bytes()
    # Reject apparent embedded credentials without printing the matched value.
    if re.search(rb"\bsk-[A-Za-z0-9_-]{24,}", content):
        raise ValueError("Potential embedded key needs review: " + str(src.relative_to(ROOT)))
    return content


def _copy_source(src, root, copied):
    content = _source_bytes(src)
    dest = root / src.relative_to(ROOT); dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    copied[str(src.relative_to(ROOT))] = hashlib.sha256(content).hexdigest()


def _monthly_export(src, dest):
    allowed = ["month", "sim_pp", "anchor_pp", "truth_pp", "anchor_reference", "anchor_reference_period",
               "anchor_published_date", "truth_published_date", "as_of"]
    with src.open(newline="") as f:
        reader = csv.DictReader(f); columns = [x for x in allowed if x in reader.fieldnames]
        rows = [{k: row[k] for k in columns} for row in reader]
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns); writer.writeheader(); writer.writerows(rows)
    return rows


def _aggregate_evidence(package, a_refresh=None):
    a = read(A_SOURCE / "summary.json")["official_national"]
    b = read(B_SOURCE / "summary.json")["evaluation"]
    dest = package / "studies/sce_inflation_expectations/reproduction_data"
    dest.mkdir(parents=True, exist_ok=True)
    cases = []
    for case_id, folder, count, first, last, data, note in (
        ("A82_original_reference", A_SOURCE, 82, 201901, 202510, a,
         "Original completed A: monthly fixed release cutoff, random 3/8/20 news; retained as the old reference."),
        ("B11_original_reference", B_SOURCE, 11, 202511, 202609, b,
         "Original completed B: assumed historical micro availability and synthetic priors; retrospective as-of backtest.")):
        file = dest / (case_id + ".csv")
        _monthly_export(folder / "monthly_national.csv", file)
        case = {"case_id": case_id, "scope": note, "n_months": count, "first_month": first,
                "last_month": last, "monthly_file": file.name, "monthly_sha256": sha(file),
                "expected": {k: {m: data[k][m] for m in ("mae_pp", "rmse_pp", "bias_pp")}
                             for k in ("model", "persistence")},
                "source_files_sha256": {str((folder / name).relative_to(ROOT)): sha(folder / name)
                                        for name in ("summary.json", "monthly_national.csv")}}
        if case_id.startswith("A"):
            case["chronological_combinations"] = data["chronological_combinations"]
        cases.append(case)
    if a_refresh is not None:
        a_refresh = Path(a_refresh).resolve()
        summary = read(a_refresh / "summary.json")
        provenance = read(a_refresh / "manifest.json")
        if summary.get("status") != "completed_readonly_A82_comparison":
            raise ValueError("Only a completed A82 comparison may be added")
        for name, digest in provenance["files_sha256"].items():
            if sha(a_refresh / name) != digest:
                raise ValueError("A comparison source changed: " + name)
        file = dest / "A82_personal_T0.csv"
        _monthly_export(a_refresh / "monthly_national.csv", file)
        national = summary["official_national"]
        cases.append({"case_id": "A82_personal_T0", "scope": "Completed personal-date T0 A82; 41,970 eligible person-months, including 182 exact historical response reuses. Retrospective reconstruction.",
            "n_months": 82, "first_month": 201901, "last_month": 202510,
            "monthly_file": file.name, "monthly_sha256": sha(file),
            "expected": {k: {m: national[k][m] for m in ("mae_pp", "rmse_pp", "bias_pp")}
                         for k in ("model", "persistence")},
            "chronological_combinations": national["chronological_combinations"],
            "expected_yearly": {str(y["year"]): {"model": y["new"], "persistence": y["persistence"]}
                                for y in summary["yearly"]},
            "source_files_sha256": {str((a_refresh / n).relative_to(ROOT)): sha(a_refresh / n)
                                     for n in ("summary.json", "monthly_national.csv", "manifest.json")}})
        # Aggregate-only comparison: no IDs, dates of personal answers, weights,
        # source paths or text. Micro summaries are disclosed, not replayed.
        write(dest / "A82_comparison_summary.json", {k: summary[k] for k in (
            "official_national", "yearly", "mae_change_pp", "mae_reduction_fraction", "new_better_months",
            "same_roster", "quality", "execution", "limits")})
    write(dest / "aggregate_cases.json", {"cases": cases, "privacy_level": "month-level public headline + simulated aggregate only",
        "input_answers": "No individual SCE responses, IDs, weights or news text are present.",
        "truth_isolation": "Used only by replay after/independently from the scripted simulation; not a generation input.",
        "publication_status": "local review bundle; final source/licensing and full micro reproduction remain open"})


def _demo_artifacts(package):
    target = package / "studies/sce_inflation_expectations"
    pop = read(STUDY / "population/population.json")
    if len(pop["personas"]) != 20 or not all(p["agent_id"].startswith("smoke_") for p in pop["personas"]):
        raise ValueError("Only the original 20 hand-authored synthetic demo personas may ship")
    env = read(STUDY / "environment/environment.json")
    env["provider_args"]["targets"] = [
        {"target_month": "2021-05", "as_of": "2021-04-30T23:59:59-04:00"},
        {"target_month": "2021-06", "as_of": "2021-05-31T23:59:59-04:00"}]
    # Original fixtures contain BLS numeric releases and no NYT/person records.
    if env["provider_args"].get("events_by_step"):
        raise ValueError("Unexpected article content in the hand-authored Core demo")
    for layer in env["layers"]:
        layer["source"] = "embedded:public_BLS_numbers_or_hand_authored_synthetic_personas"
    sim = read(STUDY / "simulation/simulation.json")
    if sim["decision_args"]["llm_kind"] != "scripted":
        raise ValueError("Demo must not have a real LLM client")
    for name, value in (("population/population_demo.json", pop), ("environment/environment_demo.json", env),
                        ("simulation/simulation_demo.json", sim)):
        write(target / name, value)
    # These standard names make the package discoverable by study tooling.
    for directory in ("population", "environment", "simulation"):
        shutil.copyfile(target / directory / (directory + "_demo.json"), target / directory / (directory + ".json"))
    study = read(STUDY / "study.yaml")
    study.update(status="submission-review-draft", n_steps=2, seed=42,
        step_meaning="Two-step scripted engineering fixture; empirical A82/B11 are reproduced separately from aggregate caches.",
        run_note={"zh": "默认离线：官方Core的20人两步工程干跑＋已完成A82/B11月度聚合误差重算；不冒充重新生成完整微观结果。"})
    write(target / "study.yaml", study)
    write(target / "resources.json", {"demo_data": "20 hand-authored synthetic personas plus short public BLS numeric facts",
        "real_aggregate_results": "reproduction_data/aggregate_cases.json", "raw_microdata_and_news_included": False})


def _dependency_lock(package):
    names = ["SocioVerse2", "pydantic", "duckdb", "pyarrow", "pandas", "PyYAML", "numpy", "scipy", "openai", "httpx", "openpyxl", "matplotlib", "pypdf", "requests"]
    versions = {name: importlib.metadata.version(name) for name in names}
    (package / "requirements.lock.txt").write_text("# Versions validated in the project's Python environment; Python >=3.11\n" +
        "\n".join(f"{name}=={version}" for name, version in versions.items()) + "\n")
    official = ROOT.parent / "socioverse2_repo"
    commit = subprocess.run(["git", "-C", str(official), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    write(package / "DEPENDENCIES.json", {"python": __import__("platform").python_version(),
        "packages": versions, "official_repository": "https://github.com/sii-research/SocioVerse2",
        "official_repository_commit_used_locally": commit,
        "external_workspace_required_for_offline_modes": False,
        "platform_changes_bundled": False})


def _production_references(package, a_refresh=None):
    # Metadata only: never include raw prompts, individual dates or P/Q records.
    records = []
    allowed = {"mechanism", "research_line", "strict_B_eligible", "months", "arms", "generation_repeats",
        "n_per_month", "planned_calls", "planned_new_api_calls", "logical_positions", "model", "route", "expected_provider",
        "temperature", "thinking", "response_format", "max_tokens", "retry_max", "provider_fallback",
        "q9_postprocessing", "model_knowledge_cutoff_verified", "text_original_vintages_verified",
        "population_source_waves", "micro_availability_basis", "frozen_combination_simulation_share"}
    for label, relative, status in (
        ("A82_new_T0", "outputs/sce_full_a_t0_terminal_20261025_v1/protocol.json", "completed_isolated_evaluation_in_replay" if a_refresh else "running_or_pending_final_evaluation_not_in_replay"),
        ("B11_original", "outputs/sce_recent_b_overnight_20261025_v3/package/protocol.json", "completed_original_B_replayed")):
        src = ROOT / relative
        records.append({"configuration_id": label, "result_status": status, "source_sha256": sha(src),
                        "configuration": {k: v for k, v in read(src).items() if k in allowed}})
    write(package / "studies/sce_inflation_expectations/simulation/production_references.json", records)
    # Paths/hashes explain how full regeneration differs from aggregate replay;
    # the protected data themselves remain in the authorized local workspace.
    requirements = []
    for label, relative in (
        ("A_new_T0_input_manifest", "outputs/sce_full_a_personal_inputs_20261025_v1/manifest.json"),
        ("B_original_input_manifest", "outputs/sce_recent_b_overnight_20261025_v3/package/manifest.json")):
        src = ROOT / relative
        requirements.append({"id": label, "workspace_relative_path": relative, "sha256": sha(src),
                             "included_in_zip": False, "access": "authorized_data_complete_workspace_required"})
    write(package / "PRIVATE_INPUTS_REQUIRED.json", {"requirements": requirements,
        "not_a_public_download_bundle": True,
        "instructions": "Restore legal sources and per-person inputs in a new workspace, prepare a new frozen run and verify its hashes before paid regeneration. Original absolute-path packages are not portable as-is."})


def build(out, *, public_log_registry, a_refresh=None, draft_version="v01", micro_data=None, input_data=None):
    out = Path(out).resolve(); registry = Path(public_log_registry).resolve()
    if draft_version not in {"v01", "v02", "v03", "v04", "v05", "v06", "v07", "v08", "v09", "v10"}:
        raise ValueError("Unknown review-bundle version")
    allowed_out = out.is_relative_to(ROOT / "outputs") or (
        draft_version in {"v05", "v06", "v07", "v08", "v09", "v10"} and out.is_relative_to(ROOT / "deliverables/research_package"))
    if out.exists() or not allowed_out or not registry.is_file():
        raise ValueError("Fresh permitted project build directory and public log registry required")
    required = [TEMPLATES / "README.md", TEMPLATES / "study_README.md", TEMPLATES / "run.py",
                ROOT / "submission/data_release_policy.json"]
    if not all(p.is_file() for p in required):
        raise ValueError("README/entry/data-release review materials are not complete")
    if draft_version in {"v06", "v07", "v08", "v09", "v10"} and (micro_data is None or not (Path(micro_data)/"manifest.json").is_file()):
        raise ValueError("v06-v09 requires a frozen --micro-data directory")
    out.mkdir(parents=True); package = out / "package"; package.mkdir()
    copied = {}
    source_plan = None
    if draft_version == "v04":
        from .source_layout import layout
        source_plan = layout(ROOT)
    relocations = None
    if draft_version in {"v05", "v06", "v07", "v08", "v09", "v10"}:
        from .release_layout import export
        release_plan, relocations, release_archive = export(package, root=ROOT, source_bytes=_source_bytes)
    else:
        for source in source_plan["selected"] if source_plan else _source_files():
            _copy_source(source, package, copied)
    archive_info = None
    if source_plan:
        from .source_layout import export_supplement
        archive_info = export_supplement(package, ROOT, source_plan, source_bytes=_source_bytes)
    # All source copies are frozen byte-for-byte; packaging adapters are listed.
    target = package / "studies/sce_inflation_expectations"
    shutil.copyfile(TEMPLATES / "run.py", target / "run.py")
    shutil.copyfile(TEMPLATES / ("README_v04.md" if source_plan else "README.md"), package / "README.md")
    shutil.copyfile(TEMPLATES / ("study_README_v04.md" if source_plan else "study_README.md"), target / "README.md")
    if source_plan:
        shutil.copyfile(TEMPLATES / "PACKAGE_DIRECTORY_GUIDE.md", package / "DIRECTORY_GUIDE.md")
        shutil.copyfile(STUDY / "FILE_GUIDE.md", target / "FILE_GUIDE.md")
    for directory in ("population", "environment", "simulation", "trajectory", "reports"):
        (target / directory).mkdir(parents=True, exist_ok=True)
    (target / "trajectory/README.md").write_text("Offline Core trajectories are generated under the chosen output directory.\nReal main runs use their original append-only JSONL ledgers; no fake DuckDB trajectory is supplied for them.\n")
    (target / "reports/README.md").write_text("Run the study entry to generate the offline receipt, metrics and index.html.\nFinal research PDF is submitted separately; aggregate_cases.json explicitly lists the completed A/B versions included in replay.\n")
    _demo_artifacts(package)
    _aggregate_evidence(package, a_refresh)
    if draft_version in {"v03", "v04", "v05", "v06", "v07", "v08", "v09", "v10"}:
        from .release_evidence import export_v03
        export_v03(package)
    _dependency_lock(package)
    _production_references(package, a_refresh)
    shutil.copyfile(ROOT / "submission/data_release_policy.json", package / "DATA_RELEASE_POLICY.json")
    (package / "experiment_logs").mkdir()
    shutil.copyfile(registry, package / "experiment_logs/registry_public.json")
    public_csv = registry.with_name("experiment_registry_public.csv")
    if public_csv.exists():
        shutil.copyfile(public_csv, package / "experiment_logs/registry_public.csv")
    # The internal receipt-to-source map is intentionally not public. A complete
    # log rebuild requires the original authorized metadata workspace.
    evidence = ROOT / ("docs/sources/challenge_requirements_20261027.json" if draft_version in {"v03", "v04", "v05", "v06", "v07", "v08", "v09", "v10"}
                       else "docs/sources/challenge_requirements_20261026.json")
    if evidence.exists():
        shutil.copyfile(evidence, package / "OFFICIAL_REQUIREMENTS.json")
    truth_evidence = ROOT / "submission/truth_isolation_evidence.json"
    if truth_evidence.exists():
        shutil.copyfile(truth_evidence, package / "TRUTH_ISOLATION_EVIDENCE.json")
    if draft_version in {"v03", "v04", "v05", "v06", "v07", "v08", "v09", "v10"}:
        # Acceptance tests are code, not copies of private caches/fixtures.
        for name in ("test_sce_submission_reproduce.py", "test_sce_submission_experiment_logs.py",
                     "test_sce_submission_release_evidence.py"):
            dest = package / "tests" / name
            dest.parent.mkdir(exist_ok=True)
            shutil.copyfile(ROOT / "tests" / name, dest)
        (package / "pytest.ini").write_text("[pytest]\npythonpath = .\ntestpaths = tests\n")
        if source_plan:
            shutil.copyfile(ROOT / "tests/test_sce_source_layout.py", package / "tests/test_sce_source_layout.py")
    if draft_version in {"v05", "v06", "v07", "v08", "v09", "v10"}:
        from .release_layout import complete_artifacts, relocate
        release_notes = complete_artifacts(package, root=ROOT)
        for name, dest in (("README.md", package / "README.md"),
                           ("STUDY_README.md", target / "README.md"),
                           ("DIRECTORY_GUIDE.md", package / "DIRECTORY_GUIDE.md"),
                           ("FILE_GUIDE.md", target / "FILE_GUIDE.md"),
                           ("REPORT.md", target / "reports/report.md")):
            shutil.copyfile(TEMPLATES / draft_version / name, dest)
        # Include code tests, adapting their imports to the same export map.
        for name in ("test_sce_source_layout.py", "test_sce_release_layout.py",
                     "test_sce_core_normal_joint.py", "test_sce_grid_sampling.py", "test_sce_q9_normalization.py"):
            shutil.copyfile(ROOT / "tests" / name, package / "tests" / name)
        for test in (package / "tests").glob("*.py"):
            test.write_text(relocate(test.read_text(), "tests/"+test.name,
                                     "tests/"+test.name, release_plan["mapping"]))
        (package / "studies/__init__.py").write_text('"""Portable SCE study collection."""\n')
        for record in relocations:
            record["exported_sha256"] = sha(package / record["exported"])
        copied = {str(p.relative_to(package)): sha(p) for p in (package / "studies").rglob("*.py")}
        archive_info = release_archive
    source_index = {"source_files_sha256": copied, "source_file_count": len(copied),
        "packaging_adapters": ["studies/sce_inflation_expectations/run.py", "studies/sce_inflation_expectations/README.md", "README.md",
            "studies/sce_inflation_expectations/study.yaml", "studies/sce_inflation_expectations/resources.json"],
        "historical_source_scripts": "See archive/research_source_supplement.zip; optional supporting and historical code." if source_plan else "Included as implementation evidence. Full empirical regeneration still needs authorized original inputs and a newly frozen workspace.",
        "source_selection_basis": "Curated current study entries plus static import closure; independently exercised by offline acceptance." if source_plan else "All project study/scripts Python sources.",
        "source_entry_groups": source_plan["groups"] if source_plan else None,
        "archived_source_supplement": archive_info,
        "exclusions": ["all original outputs/raw data", "credentials", "individual population/Q8/Q9/weights", "NYT/full article text",
                       "real individual model trajectories", "entire third-party repositories"]}
    write(package / "SOURCE_INDEX.json", source_index)
    if draft_version in {"v05", "v06", "v07", "v08", "v09", "v10"}:
        source_index.update(source_selection_basis="Current entry/import closure without obsolete eager registrations; physical topic directories; all original source archived.",
            source_relocations=relocations, source_entry_groups=release_plan["entries"],
            historical_source_scripts="All original development source in archive; not loaded at runtime.",
            packaging_adapters=source_index["packaging_adapters"] + ["physical import/path relocation", "explicit example fixture separation", "minimal registration scaffolding"],
            release_layout=release_notes)
        write(package / "SOURCE_INDEX.json", source_index)
    if draft_version in {"v06", "v07", "v08", "v09", "v10"}:
        from .micro_export import install
        install(package,micro_data,package_version=draft_version)
        shutil.copyfile(ROOT/"tests/test_sce_micro_reproduction.py",package/"tests/test_sce_micro_reproduction.py")
    if draft_version in {"v07", "v08", "v09", "v10"}:
        for name, dest in (("PAPER_METRIC_GUIDE.md", target / "reports/PAPER_METRIC_GUIDE.md"),
                           ("paper_metric_crosswalk.json", target / "reproduction_data/paper_metric_crosswalk.json"),
                           ("paper_A82_comparison.csv", target / "reproduction_data/paper_A82_comparison.csv")):
            shutil.copyfile(TEMPLATES / draft_version / name, dest)
    if draft_version in {"v08", "v09", "v10"}:
        shutil.copyfile(TEMPLATES / draft_version / "REPRODUCIBILITY.md", package / "REPRODUCIBILITY.md")
        private_inputs = read(package / "PRIVATE_INPUTS_REQUIRED.json")
        private_inputs["instructions"] = (
            "Default all mode independently replays the engineering demo, archived aggregates, "
            "answer-level scoring and Normal statistics. Full historical paid regeneration is separate: "
            "obtain legal sources and restore protected inputs in a new authorized workspace, freeze "
            "and validate a new run, and explicitly approve API costs. See REPRODUCIBILITY.md.")
        write(package / "PRIVATE_INPUTS_REQUIRED.json", private_inputs)
    if draft_version in {"v09", "v10"}:
        shutil.copyfile(TEMPLATES / draft_version / "EXTERNAL_MODEL_AND_API.md", package / "EXTERNAL_MODEL_AND_API.md")
    input_acceptance = None
    if draft_version == "v10":
        if input_data is None:
            raise ValueError("v10 requires a frozen --input-data directory")
        from .input_install import install as install_inputs
        input_acceptance = install_inputs(package, input_data, root=ROOT)
        shutil.copyfile(ROOT / "tests/test_sce_packaged_inputs.py", package / "tests/test_sce_packaged_inputs.py")
    files = {str(p.relative_to(package)): sha(p) for p in package.rglob("*") if p.is_file()}
    write(package / "PACKAGE_MANIFEST.json", {"schema": "sce_research_review_bundle/v1",
        "status": "answer_level_review_candidate_pending_final_delivery" if draft_version in {"v06", "v07", "v08", "v09", "v10"} else "development_review_not_final_submission_ready", "files_sha256": files,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "new_API_calls": 0,
        "generation_input_acceptance": input_acceptance,
        "distribution_scope": "confidential_competition_review_only_not_for_public_GitHub" if input_acceptance else "review_bundle",
        "fully_runnable_offline_modes": ["official_Core_scripted_demo", "real_archived_national_aggregate_recompute"]+(["answer_level_micro_and_Normal_recompute"] if draft_version in {"v06", "v07", "v08", "v09", "v10"} else []),
        "micro_reproduction_scope": "Four canonical final tasks plus A/B Normal; raw replies, field overlays, A paired/full-wave W1/IQR and conditional metrics; no paid regeneration" if draft_version in {"v06", "v07", "v08", "v09", "v10"} else None,
        "answer_level_reproduction_included": draft_version in {"v06", "v07", "v08", "v09", "v10"},
        "latest_A_T0_results_included": a_refresh is not None,
        "latest_extensions_included": draft_version in {"v03", "v04", "v05", "v06", "v07", "v08", "v09", "v10"},
        "reviewer_source_layout": "physically organised components with separate explicit examples" if draft_version in {"v05", "v06", "v07", "v08", "v09", "v10"} else ("main plus optional source archive" if source_plan else "full source tree"),
        "not_claimed": (["Original complete generation inputs restored", "all exploratory run outputs included", "all project invoices reconciled", "third-party news redistribution cleared"] if draft_version in {"v06", "v07", "v08", "v09", "v10"} else
                        ["full private micro trajectory reproduction", "all project invoices reconciled", "data redistribution clearance for raw inputs"])})
    archive = out / f"SCE_research_package_draft_{draft_version}.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(package.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(package))
    receipt = {"package": str(package), "archive": str(archive), "archive_sha256": sha(archive),
               "file_count": len(files) + 1, "source_files": len(copied), "archive_bytes": archive.stat().st_size,
               "new_API_calls": 0, "status": "built_review_bundle_awaiting_independent_execution"}
    write(out / "build_receipt.json", receipt)
    return receipt
