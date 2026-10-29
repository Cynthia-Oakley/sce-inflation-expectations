"""Create and materialize the offline source-data supplement for the SCE study.

The supplement keeps repository-relative data paths, hashes and source roles.
Public survey workbooks may contain outcomes at rest; the generation pipeline
reads only whitelisted population fields and strictly earlier belief records.
Model-answer artifacts are supplied separately as explicitly archived evidence.
It does not package Python source; the caller can add the source snapshot chosen
for its own review separately.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_NAME = "portable_source_manifest.json"
A_REFERENCE_MANIFEST = Path("outputs/sce_full_a_personal_inputs_20261025_v1/manifest.json")
A_REFERENCE_PROMPTS = Path("outputs/sce_full_a_personal_inputs_20261025_v1")
A_PROMPT_MESSAGE_HASHES = Path("data/portable_metadata/a_prompt_message_hashes.json")
A_ASSEMBLY = Path("outputs/sce_monthly_fine_full_assembly_20261023_v3")
A_MONTHLY_INPUTS = Path("outputs/sce_monthly_fine_full_inputs_20261023_v2")
A_DELIVERY = Path("outputs/sce_fullperiod_materialized_20261022_v2")
B_TEMPLATES = Path("outputs/sce_recent_b_sampled_dates_complete_20261026_v1")
B_ROOT_PROTOCOLS = (
    Path("outputs/sce_recent_b_sampled_terminal_20261026_v1/package/protocol.json"),
    Path("outputs/sce_recent_b_recursion_terminal_20261026_v2/package/protocol.json"),
)
MONTHLY_PE = Path("outputs/sce_recent_b_recursion_terminal_20261026_v1/PE")
Q9_SCORE_CACHE = Path("outputs/sce_monthly_reconstruction_full_inputs_20261022_v1/score_cache_private.json")
ATUS_ROLE_DONORS = Path("outputs/sce_atus_roles_attention_support_20261019_v1/role_donors_2022_private.parquet")
CE_EXPERIENCE_RECEIPT = Path("outputs/ce_population_baskets_20261006T063749Z_a8be0d98/202105/experience.json")
CE_EXPERIENCE_SOURCE = Path("data/raw/ce_experience/20261006/intrvw20.zip")
A_CORE_SAMPLE_SIMULATION = Path("outputs/sce_v32_new2025_trial_20261022_v4/202506/simulation.json")
WEEKLY_TEMPLATES = Path("outputs/sce_weekly_inputs_20261027_v2")
WEEKLY_PROTOCOL = Path("outputs/sce_weekly_terminal_20261027_v1/package/protocol.json")
OLD_MATERIALIZATION = Path("outputs/sce_fullperiod_data_20261021_v1")
B_NEWS_BASE = Path("outputs/sce_recent_b_news_refresh_20261025_v3")
B_ROLLING_PREFLIGHT = Path("outputs/sce_recent_b_rolling_preflight_20261025_v1/monthly_input_plan.json")
WEEKLY_RELEASE_INPUT = Path("data/evaluation/sce_recent_b_evaluation_20261025_v1/aggregate_inputs.json")
B_WEEKLY_DONOR_POOL = Path("outputs/sce_recent_b_rolling_preflight_20261025_v1/old_joint_donor_pool_private.parquet")
B_WEEKLY_Q9_SCORE_CACHE = Path("outputs/sce_monthly_fine_full_truth_20261023_v3/scoring_cache_private.json")
CPI_RELEASE_TABLE = Path("outputs/sce_full_a_macro_calibration_20261026_v1/monthly_inputs_public.csv")
PORTABLE_RELEASE_PROJECTION = Path("data/portable_metadata/cpi_release_schedule.csv")
B_DATE_PROTOCOL = Path("docs/workstreams/20261026_response_dates/protocol.json")
BLS_RELEASE_ROOT = Path("data/raw/bls_initial_releases")
EIA_GASOLINE_ROOT = Path("data/raw/eia_gasoline_support")

_OLD_MATERIALIZATION_SEEDS = (
    OLD_MATERIALIZATION / "coverage.json",
    OLD_MATERIALIZATION / "201906/environment.json",
    OLD_MATERIALIZATION / "201906/external_events.json",
    OLD_MATERIALIZATION / "201906/population.json",
    OLD_MATERIALIZATION / "202303/population.json",
    OLD_MATERIALIZATION / "202606/population.json",
)
_PUBLIC_SCE_SOURCE_FILES = (
    "data/raw/sce_p_sources/micro_2017_2019.xlsx",
    "data/raw/sce_audit_20260928/micro_2020_2024.xlsx",
    "data/raw/sce_audit_20260928/micro_latest.xlsx",
    "data/raw/sce_baselines_latest_20261007/micro_latest.xlsx",
    "data/raw/sce_audit_20260928/chart.xlsx",
    "data/raw/sce_micro_refresh_20261021/chart.xlsx",
)
_WEEKLY_ROOT_FILES = (
    "manifest.json",
    "summary.json",
    "population_private.json",
    "weights_private.json",
    "archive_aliases.json",
    "policies_weekly_overlay.json",
    "weekly_plan.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _message_sha256(messages: object) -> str:
    """Hash one exact message list, independent of outer JSON row ordering."""
    payload = json.dumps(messages, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _relative(path: str | Path) -> str:
    candidate = PurePosixPath(str(path).replace("\\", "/"))
    if candidate.is_absolute() or not candidate.parts or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError(f"Unsafe repository-relative path: {path}")
    if ":" in candidate.parts[0]:
        raise ValueError(f"Drive-qualified path is not allowed: {path}")
    return candidate.as_posix()


def _is_separate_evaluation_or_outcome(path: str) -> bool:
    lowered = f"/{path.lower()}/"
    if path == "data/evaluation/sce_baselines_latest_20261007/micro_reference_sources.json":
        return False  # source-hash registry only; no survey outcomes
    if path == WEEKLY_RELEASE_INPUT.as_posix():
        return False  # original weekly preparation projects only dated public headline releases
    if "/data/evaluation/" in lowered:
        return True
    forbidden = (
        "/evaluation_truth/", "/model_answers/", "/responses/", "/results/",
        "/combined/", "/model_runs/", "/calls/",
    )
    return any(token in lowered for token in forbidden)


def _role(path: str) -> str:
    p = PurePosixPath(path)
    if path.startswith("data/raw/"):
        if "/sce_" in f"/{path}" and p.suffix.lower() in {".xlsx", ".xls", ".csv", ".parquet"}:
            return "public_raw_sce_snapshot_answers_separate_from_generation_projection"
        return "public_raw_source_snapshot"
    if path.startswith("outputs/sce_monthly_fine_full_assembly_20261023_v3/prompts/"):
        if p.name == "initial_states_private.json":
            return "derived_A_initial_state_input"
        if p.name == "initial_previews_private.json":
            return "derived_A_preview_input"
        if p.name == "timing_context_private.json":
            return "derived_A_timing_input"
        if p.name == "population.json":
            return "derived_A_population_input"
        if p.name == "baskets_private.json":
            return "derived_A_basket_input"
        return "derived_A_prompt_assembly_input"
    if path.startswith("outputs/sce_monthly_fine_full_inputs_20261023_v2/"):
        return "derived_A_donor_probability_and_weight_table"
    if path.startswith("outputs/sce_fullperiod_materialized_20261022_v2/"):
        if p.name.endswith("label_index.json") or "label" in p.name:
            return "derived_public_candidate_label_index"
        if p.name == "population.json" or p.name == "population_state_private.json":
            return "derived_A_population_PE_input"
        return "derived_A_environment_PE_input"
    if path.startswith("outputs/sce_prior_preparation_20261013_v4/"):
        return "derived_public_survey_history_reference_cache"
    if path.startswith("outputs/sce_recent_b_sampled_dates_complete_20261026_v1/"):
        return "prepared_B_generation_template_or_source"
    if path.startswith("outputs/sce_recent_b_recursion_terminal_20261026_v1/PE/"):
        return "prepared_monthly_PE_and_initial_state_template"
    if path.startswith("outputs/sce_weekly_inputs_20261027_v2/"):
        if "/priors/" in path:
            return "prepared_weekly_prior_cycle_table"
        if "/weeks/" in path:
            return "prepared_weekly_generation_template_and_initial_state"
        return "prepared_weekly_roster_or_manifest"
    if "labels" in p.name or "/labels_" in path:
        return "public_news_candidate_label_source"
    if path.startswith("outputs/"):
        return "derived_generation_source_or_manifest"
    if path.startswith("data/evaluation/"):
        return "evaluation_metadata_not_generation_truth"
    return "public_or_study_configuration_source"


class _Collector:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.files: dict[str, dict] = {}
        self.excluded: dict[str, dict] = {}
        self.generated: dict[str, bytes] = {}

    def add(self, relative: str | Path, *, role: str | None = None, lineage: str = "explicit source list",
            expected_sha256: str | None = None, omit_evaluation: bool = True) -> None:
        rel = _relative(relative)
        if omit_evaluation and _is_separate_evaluation_or_outcome(rel):
            self.excluded[rel] = {"reason": "evaluation truth or model outcome remains a separate evaluator input"}
            return
        source = self.root / rel
        if not source.is_file() or source.is_symlink():
            raise FileNotFoundError(f"Required portable source is missing or not a regular file: {rel}")
        digest = sha256(source)
        if expected_sha256 is not None and digest != expected_sha256:
            raise ValueError(f"Source hash differs from registered manifest for {rel}: {digest} != {expected_sha256}")
        record = self.files.get(rel)
        if record is None:
            self.files[rel] = {
                "role": role or _role(rel),
                "sha256": digest,
                "bytes": source.stat().st_size,
                "source_lineage": [lineage],
            }
        else:
            if record["sha256"] != digest:
                raise ValueError(f"Conflicting hashes for {rel}")
            if lineage not in record["source_lineage"]:
                record["source_lineage"].append(lineage)

    def add_manifest_sources(self, manifest_path: Path, key: str) -> dict:
        rel = _relative(manifest_path)
        manifest = _json(self.root / rel)
        sources = manifest.get(key)
        if not isinstance(sources, dict):
            raise ValueError(f"{rel} has no {key} path/hash map")
        self.add(rel, role="reproduction_hash_manifest", lineage=f"manifest container for {key}")
        for source, digest in sources.items():
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError(f"Invalid SHA-256 in {rel}: {source}")
            self.add(source, lineage=f"{rel}:{key}", expected_sha256=digest)
        return manifest

    def add_generated(self, relative: str | Path, content: bytes, *, role: str, lineage: str) -> None:
        rel = _relative(relative)
        if _is_separate_evaluation_or_outcome(rel):
            raise ValueError(f"Generated preparation input cannot target an evaluation path: {rel}")
        self.generated[rel] = content
        self.files[rel] = {
            "role": role,
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
            "source_lineage": [lineage],
        }


def collect_sources(source_root: Path = REPOSITORY_ROOT) -> tuple[dict[str, dict], dict[str, dict], dict[str, bytes]]:
    """Build the exact closure of the frozen A inputs and reusable B/weekly templates."""
    root = Path(source_root).expanduser().resolve()
    collector = _Collector(root)

    # The original A manifest is both the full direct-input closure and the
    # frozen prompt hash reference. The closure includes public raw sources,
    # public candidate labels, and original P/E/donor/initial-state sidecars.
    a_manifest = _json(root / A_REFERENCE_MANIFEST)
    collector.add(A_REFERENCE_MANIFEST, role="expected_A_prompt_hash_manifest",
                  lineage="frozen A output/input hash reference; no archived A prompt outputs")
    a_inputs = a_manifest.get("input_files_sha256", {})
    if not isinstance(a_inputs, dict):
        raise ValueError(f"{A_REFERENCE_MANIFEST} has no input_files_sha256 map")
    for source, digest in a_inputs.items():
        if source.startswith(f"{A_DELIVERY.as_posix()}/"):
            collector.excluded[source] = {
                "reason": "full-period P/E is regenerated from registered public sources by portable_prepare"
            }
            continue
        if source == "outputs/sce_prior_preparation_20261013_v4/labeled_reference_private.parquet":
            collector.excluded[source] = {
                "reason": "labeled reference is rebuilt from the public microdata xlsx by portable_prepare"
            }
            continue
        collector.add(source, lineage=f"{A_REFERENCE_MANIFEST}:input_files_sha256", expected_sha256=digest)

    # The full original A prompts are intentionally not shipped. Include only
    # per-person message digests so a reviewer can distinguish exact message
    # reproduction from harmless JSON dictionary insertion-order changes.
    # Validate every source file against the frozen manifest before extracting
    # these digest-only expectations.
    prompt_file_hashes = a_manifest.get("files_sha256", {})
    expected_messages = {}
    for month in a_manifest.get("months", []):
        relative = f"{month}/prompts.json"
        expected_file_hash = prompt_file_hashes.get(relative)
        if not isinstance(expected_file_hash, str):
            raise ValueError(f"Frozen A manifest has no registered prompt-file hash for {relative}")
        prompt_path = root / A_REFERENCE_PROMPTS / relative
        if not prompt_path.is_file() or sha256(prompt_path) != expected_file_hash:
            raise ValueError(f"Frozen A prompt file is absent or differs from its registered hash: {relative}")
        rows = _json(prompt_path).get("rows")
        if not isinstance(rows, dict):
            raise ValueError(f"Frozen A prompt file has no rows mapping: {relative}")
        month_hashes = {}
        for agent_id, row in rows.items():
            if not isinstance(row, dict) or not isinstance(row.get("messages"), list):
                raise ValueError(f"Frozen A row has no exact messages list: {relative}/{agent_id}")
            month_hashes[str(agent_id)] = _message_sha256(row["messages"])
        expected_messages[str(month)] = month_hashes
    digest_registry = {
        "schema_version": 1,
        "source_manifest": A_REFERENCE_MANIFEST.as_posix(),
        "source_manifest_sha256": sha256(root / A_REFERENCE_MANIFEST),
        "source_prompt_root": A_REFERENCE_PROMPTS.as_posix(),
        "hash_method": "sha256(json.dumps(messages, ensure_ascii=False).encode('utf-8'))",
        "prompt_file_sha256": {
            f"{month}/prompts.json": prompt_file_hashes[f"{month}/prompts.json"]
            for month in a_manifest.get("months", [])
        },
        "expected_agent_count": sum(len(rows) for rows in expected_messages.values()),
        "months": expected_messages,
    }
    collector.add_generated(
        A_PROMPT_MESSAGE_HASHES,
        (json.dumps(digest_registry, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"),
        role="expected_A_prompt_message_hash_registry",
        lineage=f"hashes only, derived from prompt files registered by {A_REFERENCE_MANIFEST}; prompt text and archived outputs are not included",
    )

    # The full-period materializer uses only this old coverage registry and
    # a schema seed plus three sample persona rows. Target truth sidecars are
    # purposefully omitted.
    for seed in _OLD_MATERIALIZATION_SEEDS:
        collector.add(seed, role="original_materializer_public_seed",
                      lineage="fullperiod_materialization.OLD schema/coverage or persona reuse")

    collector.add(Q9_SCORE_CACHE, role="deterministic_Q9_scoring_lookup_cache",
                  lineage="monthly_fine_inputs uses the original exact-vector scorer memo; it contains no model outcomes")
    collector.add(ATUS_ROLE_DONORS, role="derived_public_ATUS_role_donor_table",
                  lineage="state_continuity_prompts uses the original 2022 conditional-role donor table")
    ce_receipt = _json(root / CE_EXPERIENCE_RECEIPT)
    ce_source = ce_receipt.get("source", {})
    collector.add(CE_EXPERIENCE_RECEIPT, role="derived_CE_basket_donor_features_and_source_receipt",
                  lineage="state_continuity_prompts.BasketAssigner source and CE member/hash receipt")
    collector.add(CE_EXPERIENCE_SOURCE, role="public_raw_CE_microdata_donor_source",
                  lineage="state_continuity_prompts rebuilds its historical basket donors from the receipted public CE member",
                  expected_sha256=ce_source.get("data_sha256"))
    collector.add(A_CORE_SAMPLE_SIMULATION, role="official_core_check_simulation_fixture",
                  lineage="state_continuity_core runs the installed SDK against this registered simulation configuration")

    collector.add("data/evaluation/sce_baselines_latest_20261007/micro_reference_sources.json",
                  role="public_source_hash_registry", lineage="age_reporting_audit.load_reference validates xlsx vintages")
    for source in _PUBLIC_SCE_SOURCE_FILES:
        collector.add(source, role=("public_raw_sce_snapshot_answers_separate_from_generation_projection"
                                    if source.endswith(".xlsx") and "/chart.xlsx" not in source
                                    else "public_raw_sce_chart_snapshot"),
                      lineage="original SCE source-to-population/prior pipeline")

    # P/E materialization reads the full archived BLS release set for both
    # CPI component extraction and employment history. These public source
    # files are not all named in the frozen A prompt manifest.
    for source_root, role, lineage in (
        (BLS_RELEASE_ROOT, "public_BLS_initial_release_archive",
         "fullperiod_materialization builds CPI/environment histories from archived first releases"),
        (EIA_GASOLINE_ROOT, "public_EIA_gasoline_release_archive",
         "fullperiod_materialization reads the consolidated public gasoline weekly series"),
    ):
        absolute_root = root / source_root
        if not absolute_root.is_dir():
            raise FileNotFoundError(f"Required public P/E source directory is missing: {source_root}")
        for path in sorted(absolute_root.rglob("*")):
            if path.is_file() and not path.is_symlink():
                collector.add(path.relative_to(root), role=role, lineage=lineage)

    # Recent B is rebuilt from the original recent-news candidate base rather
    # than from its final sampled-date prompts. Core fixture outputs are
    # excluded, and the local manifest is narrowed to the exact pre-answer
    # inputs consumed by the original B date/assembly functions.
    base_root = root / B_NEWS_BASE
    if not base_root.is_dir():
        raise FileNotFoundError(f"Required B candidate source root is missing: {B_NEWS_BASE}")
    original_base_manifest = _json(base_root / "manifest.json")
    kept_base_files = {
        name: digest for name, digest in original_base_manifest.get("files_sha256", {}).items()
        if not name.startswith(("core_engineering/", "archive_view/"))
    }
    allowed_source = {}
    for name, digest in original_base_manifest.get("source_sha256", {}).items():
        if "/core_engineering/" in f"/{name.lower()}/" or name.startswith("data/raw/mcp_checks/"):
            collector.excluded[name] = {"reason": "Core check artifact or endpoint configuration is not needed for B input preparation"}
            continue
        if name.startswith((
            "studies/", "scripts/", "data/raw/", "outputs/sce_multiperiod_news_labels_",
            "outputs/sce_news_", "outputs/sce_expanded_news_run_", "outputs/sce_nyt_label_trial_",
            "outputs/sce_recent_b_news_repair_", "outputs/sce_recent_b_rolling_assembly_",
            "outputs/sce_recent_b_rolling_preflight_",
        )):
            allowed_source[name] = digest
    filtered_base_manifest = dict(original_base_manifest)
    filtered_base_manifest["files_sha256"] = kept_base_files
    filtered_base_manifest["source_sha256"] = allowed_source
    collector.add_generated(
        B_NEWS_BASE / "manifest.json",
        (json.dumps(filtered_base_manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        role="filtered_B_candidate_manifest",
        lineage="original B manifest narrowed to non-Core candidate and prompt inputs",
    )
    for name, digest in kept_base_files.items():
        collector.add(B_NEWS_BASE / name, role="B_candidate_pool_or_preflight_input",
                      lineage=f"original {B_NEWS_BASE}/manifest.json:files_sha256", expected_sha256=digest)
    for source, digest in allowed_source.items():
        collector.add(source, lineage=f"filtered {B_NEWS_BASE}/manifest.json:source_sha256",
                      expected_sha256=digest)
    collector.add(B_ROLLING_PREFLIGHT, role="B_population_and_date_plan",
                  lineage="recent_b_sampled_dates.prepare_dates reads monthly_input_plan")

    # The date sampler consumes only historical completion-date counts and
    # public CPI release dates. Retain just the fields used from the broader
    # frozen macro table; omit all unrelated macro values.
    release_table = root / CPI_RELEASE_TABLE
    with release_table.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required_columns = {"month", "cpi_published_at"}
        if not required_columns.issubset(reader.fieldnames or []):
            raise ValueError(f"{CPI_RELEASE_TABLE} lacks {sorted(required_columns)}")
        projected = io.StringIO(newline="")
        writer = csv.DictWriter(projected, fieldnames=["month", "cpi_published_at"], lineterminator="\n")
        writer.writeheader()
        projected_rows = 0
        for row in reader:
            writer.writerow({key: row.get(key, "") for key in ("month", "cpi_published_at")})
            projected_rows += 1
    collector.add_generated(
        PORTABLE_RELEASE_PROJECTION,
        projected.getvalue().encode("utf-8"),
        role="public_CPI_release_date_projection",
        lineage=f"{CPI_RELEASE_TABLE} sha256={sha256(release_table)}; fields=month,cpi_published_at; rows={projected_rows}",
    )

    # B and weekly prompt inputs are retained at their original output paths.
    # Terminal checking directories and archived authorizations are not inputs
    # to a fresh own-key execution.
    b_root = root / B_TEMPLATES
    if not b_root.is_dir():
        raise FileNotFoundError(f"Required B template root is missing: {B_TEMPLATES}")
    b_manifest = _json(b_root / "manifest.json")
    b_hashes = b_manifest.get("files_sha256", {})
    for path in sorted(b_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        inside = path.relative_to(b_root).as_posix()
        if inside.startswith(("core_engineering/", "archive_view/")):
            continue
        expected = b_hashes.get(inside)
        collector.add(rel, role=_role(rel), lineage="frozen B template package; pre-answer input",
                      expected_sha256=expected)

    # Include the exact monthly PE/state rows that weekly preparation and the
    # user's API runner consume. NYT archives are separately kept under their
    # registered data/raw paths, so the nested archive_view copy is excluded.
    pe_root = root / MONTHLY_PE
    if not pe_root.is_dir():
        raise FileNotFoundError(f"Required monthly PE root is missing: {MONTHLY_PE}")
    for path in sorted(pe_root.rglob("*")):
        if path.is_file() and "archive_view" not in path.relative_to(pe_root).parts:
            collector.add(path.relative_to(root), role=_role(path.relative_to(root).as_posix()),
                          lineage="monthly recursion PE template used by weekly preparation")

    weekly_root = root / WEEKLY_TEMPLATES
    if not weekly_root.is_dir():
        raise FileNotFoundError(f"Required weekly template root is missing: {WEEKLY_TEMPLATES}")
    weekly_manifest = _json(weekly_root / "manifest.json")
    weekly_hashes = weekly_manifest.get("files_sha256", {})
    for path in sorted(weekly_root.rglob("*")):
        if not path.is_file():
            continue
        inside = path.relative_to(weekly_root).as_posix()
        if inside.startswith(("core_engineering/", "archive_view/")):
            continue
        collector.add(path.relative_to(root), role=_role(path.relative_to(root).as_posix()),
                      lineage="frozen weekly preparation package; pre-answer input",
                      expected_sha256=weekly_hashes.get(inside))

    for protocol in (*B_ROOT_PROTOCOLS, WEEKLY_PROTOCOL):
        collector.add(protocol, role="generation_protocol", lineage="protocol needed to reproduce original runner inputs")
    collector.add("outputs/sce_recent_b_recursion_terminal_20261026_v2/package/manifest.json",
                  role="monthly_terminal_source_manifest",
                  lineage="weekly_preflight validates the declared monthly PE source set")
    collector.add(WEEKLY_RELEASE_INPUT, role="dated_public_anchor_table",
                  lineage="weekly_preflight reads headline_releases; the original schedule applies each release only after publication",
                  omit_evaluation=False)
    collector.add(B_DATE_PROTOCOL, role="B_response_date_sampling_protocol",
                  lineage="response_date_distribution.analyze loads the registered protocol into its generated report")
    collector.add(B_WEEKLY_DONOR_POOL, role="derived_public_joint_Q8_Q9_donor_pool",
                  lineage="weekly_priors.prepare_cycles redoes original release-cycle matching from this prior donor pool")
    collector.add(B_WEEKLY_Q9_SCORE_CACHE, role="deterministic_Q9_scoring_lookup_cache",
                  lineage="weekly_priors uses original exact-vector density means and known-unscorable markers")

    # Add the non-evaluation raw/label/data sources explicitly hashed by the
    # original B and weekly input manifests. This retains unselected candidate
    # pools and repair labels needed to redo matching, without copying model or
    # truth outputs.
    for manifest_rel in (B_TEMPLATES / "manifest.json", WEEKLY_TEMPLATES / "manifest.json"):
        manifest = _json(root / manifest_rel)
        for source, digest in manifest.get("source_sha256", {}).items():
            if not isinstance(digest, str) or len(digest) != 64:
                continue
            if source == WEEKLY_RELEASE_INPUT.as_posix():
                continue  # explicitly added with the dated-public-anchor role above
            if source.startswith("data/raw/") or "label" in Path(source).name.lower():
                collector.add(source, lineage=f"{manifest_rel}:source_sha256", expected_sha256=digest)
            elif source.startswith("outputs/sce_multiperiod_news_labels_") or source.startswith("outputs/sce_recent_b_news_repair_"):
                collector.add(source, lineage=f"{manifest_rel}:source_sha256", expected_sha256=digest)

    return collector.files, collector.excluded, collector.generated


def export_package(archive_path: Path, source_root: Path = REPOSITORY_ROOT) -> dict:
    """Write a compressed, hash-manifested repository-relative data archive."""
    root = Path(source_root).expanduser().resolve()
    destination = Path(archive_path).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite portable source archive: {destination}")
    files, excluded, generated = collect_sources(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "status": "offline_portable_generation_source_data",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "Original source-file closure with path/hash verification; raw public SCE answer-bearing workbooks stay separately role-tagged and original generation projections enforce their own target-answer exclusion.",
        "network_or_paid_calls": 0,
        "weekly_public_anchor_projection": {
            "path": WEEKLY_RELEASE_INPUT.as_posix(),
            "role": "dated_public_anchor_table",
            "consumer": "weekly_preflight reads headline_releases; weekly_release_protocol applies only releases published by each prompt cutoff",
            "individual_current_survey_truth_included": False,
        },
        "public_cpi_release_schedule_projection": PORTABLE_RELEASE_PROJECTION.as_posix(),
        "source_root_layout": "Every archive member preserves its original repository-relative path.",
        "included_file_count": len(files),
        "uncompressed_bytes": sum(record["bytes"] for record in files.values()),
        "role_counts": dict(Counter(record["role"] for record in files.values())),
        "excluded_paths": excluded,
        "files": files,
    }
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    import os
    os.close(fd)
    temporary = Path(temp_name)
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            for rel, record in sorted(files.items()):
                if rel in generated:
                    content = generated[rel]
                    if hashlib.sha256(content).hexdigest() != record["sha256"]:
                        raise ValueError(f"Generated source projection changed while exporting: {rel}")
                    archive.writestr(rel, content)
                else:
                    path = root / rel
                    if sha256(path) != record["sha256"]:
                        raise ValueError(f"Source changed while exporting: {rel}")
                    archive.write(path, rel)
            archive.writestr(MANIFEST_NAME,
                             json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        # Re-open and verify the completed archive before publishing it.
        with ZipFile(temporary, "r") as archive:
            _verify_zip_manifest(archive)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    manifest["archive_path"] = str(destination)
    manifest["archive_bytes"] = destination.stat().st_size
    return manifest


def _manifest_from_zip(archive: ZipFile) -> tuple[dict, dict[str, object]]:
    infos: dict[str, object] = {}
    for info in archive.infolist():
        if info.is_dir():
            continue
        rel = _relative(info.filename)
        mode = (info.external_attr >> 16) & 0xFFFF
        file_type = stat.S_IFMT(mode)
        if stat.S_ISLNK(mode) or file_type not in {0, stat.S_IFREG}:
            raise ValueError(f"Non-regular ZIP member is not allowed: {info.filename}")
        if rel in infos:
            raise ValueError(f"Duplicate ZIP member: {rel}")
        infos[rel] = info
    if MANIFEST_NAME not in infos:
        raise ValueError(f"Archive has no {MANIFEST_NAME}")
    manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), dict):
        raise ValueError("Unsupported portable source manifest")
    return manifest, infos


def _verify_zip_manifest(archive: ZipFile) -> dict:
    manifest, infos = _manifest_from_zip(archive)
    expected = set(manifest["files"])
    actual = set(infos) - {MANIFEST_NAME}
    if expected != actual:
        raise ValueError(f"Archive member set differs from manifest: missing={sorted(expected-actual)[:5]}, extra={sorted(actual-expected)[:5]}")
    for rel, record in manifest["files"].items():
        if archive.getinfo(rel).file_size != record.get("bytes"):
            raise ValueError(f"ZIP size differs from manifest: {rel}")
        digest = hashlib.sha256(archive.read(rel)).hexdigest()
        if digest != record.get("sha256"):
            raise ValueError(f"ZIP hash differs from manifest: {rel}")
    return manifest


def materialize(package_data: Path, workspace_root: Path) -> dict:
    """Validate a package archive/directory and extract it into a fresh workspace.

    The destination must be absent or an empty directory. Extraction uses a
    temporary sibling and an atomic rename; path traversal and ZIP symlinks are
    rejected before any member is written.
    """
    package = Path(package_data).expanduser().resolve()
    destination = Path(workspace_root).expanduser().resolve()
    if not package.exists():
        raise FileNotFoundError(package)
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise FileExistsError(f"Workspace destination must be absent or empty: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        if package.is_dir():
            manifest_path = package / MANIFEST_NAME
            manifest = _json(manifest_path)
            if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), dict):
                raise ValueError("Unsupported portable source manifest")
            for rel, record in sorted(manifest["files"].items()):
                safe = _relative(rel)
                source = package / safe
                if not source.is_file() or source.is_symlink():
                    raise FileNotFoundError(f"Package source is missing or not regular: {safe}")
                if source.stat().st_size != record.get("bytes") or sha256(source) != record.get("sha256"):
                    raise ValueError(f"Package hash or size mismatch: {safe}")
                target = temporary / safe
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            shutil.copyfile(manifest_path, temporary / MANIFEST_NAME)
        else:
            with ZipFile(package, "r") as archive:
                manifest = _verify_zip_manifest(archive)
                for rel, record in sorted(manifest["files"].items()):
                    safe = _relative(rel)
                    target = temporary / safe
                    target.parent.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256()
                    with archive.open(safe, "r") as source, target.open("wb") as output:
                        for block in iter(lambda: source.read(1024 * 1024), b""):
                            digest.update(block)
                            output.write(block)
                    if digest.hexdigest() != record["sha256"]:
                        raise ValueError(f"Extracted file hash mismatch: {safe}")
                (temporary / MANIFEST_NAME).write_bytes(archive.read(MANIFEST_NAME))
        if destination.exists():
            destination.rmdir()
        temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "materialized_to": str(destination),
        "file_count": len(manifest["files"]),
        "manifest_sha256": sha256(destination / MANIFEST_NAME),
        "role_counts": dict(Counter(record["role"] for record in manifest["files"].values())),
    }


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export_parser = sub.add_parser("export", help="write the portable source data ZIP")
    export_parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    export_parser.add_argument("--out", type=Path, required=True)
    extract_parser = sub.add_parser("materialize", help="validate/extract a source ZIP")
    extract_parser.add_argument("--package-data", type=Path, required=True)
    extract_parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args(argv)
    result = (export_package(args.out, args.root) if args.command == "export"
              else materialize(args.package_data, args.workspace))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
