"""Export deterministic call-level provenance for the four final SCE tasks.

The exporter joins existing, frozen call ledgers to the already exported model
outputs, effective answers, and complete prompt index. It performs no model
calls and does not modify any source run. Only explicitly named source files
and receipt files are read.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Any, Iterable, Iterator

ROOT = Path(__file__).resolve().parents[3]

RUN_ROOTS = {
    "A": "outputs/sce_full_a_t0_terminal_20261025_v1",
    "B": "outputs/sce_recent_b_sampled_terminal_20261026_v1",
    "monthly": "outputs/sce_recent_b_recursion_terminal_20261026_v2",
    "weekly": "outputs/sce_weekly_terminal_20261027_v1",
}
MICRO_DATA = "outputs/sce_micro_reproduction_20261029_v3/data"
PRIVATE_ID_MAP = "outputs/sce_micro_reproduction_20261029_v3/private_key_map_NOT_FOR_PACKAGE.json"
PRIVATE_SOURCE_MANIFEST = "outputs/sce_micro_reproduction_20261029_v3/source_manifest_private.json"
INPUT_ROOT = "outputs/sce_submission_inputs_exact_20261029_v1"
A_CASES = "outputs/sce_full_a_t0_analysis_20261026_v1/cases_private.json"
A_ACTIONS = RUN_ROOTS["A"] + "/generation_views/view_0001/logical_actions_private.jsonl"

_ALIAS_PATTERNS = {
    "A": re.compile(r"^A_\d{6}$"),
    "B": re.compile(r"^B_\d{6}$"),
    "monthly": re.compile(r"^monthly_\d{6}$"),
    "weekly": re.compile(r"^weekly_\d{6}$"),
}
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{24,}"),
    re.compile(r"(?i)\bauthorization\s*:\s*bearer\b"),
    re.compile(r"(?i)\b(?:OPENROUTER|SILICONFLOW|DEEPSEEK)_API_KEY\s*[:=]"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                yield line_number, json.loads(line)


def _jsonl_gz(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                yield line_number, json.loads(line)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl_gz(path: Path, records: Iterable[dict[str, Any]]) -> int:
    """Write stable JSONL gzip with neither host filename nor wall-clock time."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("xb") as binary:
        with gzip.GzipFile(fileobj=binary, mode="wb", filename="", mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="\n") as stream:
                for record in records:
                    stream.write(
                        json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)
                        + "\n"
                    )
                    count += 1
    return count


def _input_id(run: str, period: str, household: str) -> str:
    return f"input:{run}:{period}:{household}"


def _answer_id(index: int) -> str:
    return f"answer_{index:07d}"


def _safe_rel(root: Path, path: Path) -> str:
    resolved = path.resolve()
    if path.is_symlink() or not resolved.is_relative_to(root):
        raise ValueError("Source path is a symlink or outside the repository root")
    return resolved.relative_to(root).as_posix()


def _check_secrets(value: Any) -> None:
    """Fail closed on credential-like text without printing or rewriting it."""
    if isinstance(value, str):
        if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
            raise ValueError("Credential-like value found in an allowlisted field")
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_secrets(str(key))
            _check_secrets(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _check_secrets(item)


def _portable_receipt(value: Any, root: Path) -> tuple[Any, int]:
    """Keep receipt fields while replacing the repository's absolute prefix."""
    normalized = 0
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            cleaned, replacements = _portable_receipt(item, root)
            clean[key] = cleaned
            normalized += replacements
        return clean, normalized
    if isinstance(value, list):
        clean = []
        for item in value:
            cleaned, replacements = _portable_receipt(item, root)
            clean.append(cleaned)
            normalized += replacements
        return clean, normalized
    if isinstance(value, tuple):
        clean, normalized = _portable_receipt(list(value), root)
        return clean, normalized
    if isinstance(value, str):
        prefix = root.as_posix()
        if value == prefix:
            return ".", 1
        absolute_prefix = prefix.rstrip("/") + "/"
        count = value.count(absolute_prefix)
        return value.replace(absolute_prefix, ""), count
    return value, normalized


class _SourceIndex:
    """Track source paths and exact hashes, including their manifest bindings."""

    def __init__(self, root: Path):
        self.root = root
        self.entries: dict[str, dict[str, Any]] = {}

    def add(
        self,
        path: Path,
        role: str,
        *,
        expected_sha256: str | None = None,
        bound_by: str | None = None,
        row_count: int | None = None,
    ) -> str:
        if not path.is_file():
            raise ValueError("Required source file is missing: " + _safe_rel(self.root, path))
        relative = _safe_rel(self.root, path)
        actual = _sha256(path)
        if expected_sha256 and actual != expected_sha256:
            raise ValueError("Source checksum differs from its manifest: " + relative)
        entry = self.entries.setdefault(relative, {"source_path": relative, "sha256": actual, "roles": []})
        if entry["sha256"] != actual:
            raise ValueError("Source file changed during export: " + relative)
        if role not in entry["roles"]:
            entry["roles"].append(role)
            entry["roles"].sort()
        if bound_by:
            bindings = entry.setdefault("bound_by", [])
            if bound_by not in bindings:
                bindings.append(bound_by)
                bindings.sort()
        if row_count is not None:
            entry["rows"] = row_count
        return relative

    def manifest(self) -> dict[str, Any]:
        return {
            "schema": "sce_portable_evidence_sources/v1",
            "path_convention": "Repository-relative paths; no absolute local paths are recorded.",
            "sources": [self.entries[key] for key in sorted(self.entries)],
        }


def _check_manifest_binding(source_index: _SourceIndex, manifest_path: Path, target: Path) -> str | None:
    """Verify and index one file against its adjacent source manifest if present."""
    if not manifest_path.is_file():
        raise ValueError("Required adjacent source manifest is missing: " + _safe_rel(source_index.root, manifest_path))
    manifest = _json(manifest_path)
    expected = manifest.get("files_sha256", {}).get(target.name)
    if not expected:
        raise ValueError("Adjacent source manifest does not bind " + _safe_rel(source_index.root, target))
    manifest_rel = source_index.add(manifest_path, "segment_manifest")
    source_index.add(
        target,
        "frozen_source",
        expected_sha256=expected,
        bound_by=manifest_rel,
    )
    return manifest_rel


def _load_expected_map(
    source_index: _SourceIndex, root: Path
) -> tuple[dict[str, str], dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    map_path = root / PRIVATE_ID_MAP
    source_index.add(map_path, "export_alias_to_internal_agent_id_map")
    raw_map = _json(map_path)
    if not isinstance(raw_map, dict) or not raw_map:
        raise ValueError("The original alias-to-agent map must be a nonempty object")
    source_to_alias: dict[str, dict[str, str]] = {run: {} for run in RUN_ROOTS}
    alias_to_source: dict[str, dict[str, str]] = {run: {} for run in RUN_ROOTS}
    for alias, source_id in raw_map.items():
        for run, pattern in _ALIAS_PATTERNS.items():
            if pattern.fullmatch(alias):
                if source_id in source_to_alias[run] or alias in alias_to_source[run]:
                    raise ValueError(f"Duplicate original source ID in {run} alias map")
                source_to_alias[run][str(source_id)] = alias
                alias_to_source[run][alias] = str(source_id)
                break
    return {str(k): str(v) for k, v in raw_map.items()}, source_to_alias, alias_to_source


def _load_public_sce_ids(source_index: _SourceIndex, root: Path) -> dict[str, int]:
    path = root / A_CASES
    source_index.add(path, "public_sce_anonymous_id_crosswalk")
    case_rows = _json(path)
    result: dict[str, int] = {}
    public_to_agent: dict[int, str] = {}
    for row in case_rows:
        agent = str(row["agent_id"])
        public_id = int(row["userid"])
        if agent in result and result[agent] != public_id:
            raise ValueError("A source Agent ID maps to conflicting public SCE userids")
        if public_id in public_to_agent and public_to_agent[public_id] != agent:
            raise ValueError("A public SCE userid maps to conflicting A source Agent IDs")
        result[agent] = public_id
        public_to_agent[public_id] = agent
    return result


def _validate_data_manifest(source_index: _SourceIndex, root: Path, filenames: tuple[str, ...]) -> tuple[Path, dict[str, Any]]:
    data_root = root / MICRO_DATA
    manifest_path = data_root / "manifest.json"
    manifest = _json(manifest_path)
    source_index.add(manifest_path, "micro_reproduction_data_manifest")
    for filename in filenames:
        expected = manifest.get("files_sha256", {}).get(filename)
        if not expected:
            raise ValueError("Micro reproduction manifest does not list " + filename)
        source_index.add(data_root / filename, "existing_micro_reproduction_data", expected_sha256=expected,
                         bound_by=_safe_rel(root, manifest_path))
    return data_root, manifest


def _read_actions(source_index: _SourceIndex, root: Path) -> dict[tuple[str, str], tuple[int, dict[str, Any]]]:
    path = root / A_ACTIONS
    manifest_path = path.parent / "manifest.json"
    _check_manifest_binding(source_index, manifest_path, path)
    actions: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
    for line_number, action in _jsonl(path):
        key = (str(action["month"]), str(action["agent_id"]))
        if key in actions:
            raise ValueError("Duplicate A logical action for a source person-month")
        actions[key] = (line_number, action)
    source_index.add(path, "A_logical_action_ledger", row_count=len(actions))
    return actions


def _read_historical_sources(
    source_index: _SourceIndex,
    root: Path,
    actions: dict[tuple[str, str], tuple[int, dict[str, Any]]],
) -> dict[tuple[str, str], tuple[int, dict[str, Any]]]:
    """Resolve the pinned source rows behind A's exact historical imports."""
    wanted: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    action_keys: dict[tuple[str, str], dict[str, Any]] = {}
    for (period, agent_id), (_, action) in actions.items():
        imported = (action.get("main") or {}).get("historical_source")
        if imported:
            relative = str(imported["reply_path"])
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError("Historical import source path is not repository-relative")
            wanted[relative][str(imported["key"])] = imported
            action_keys[(period, agent_id)] = imported

    resolved: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
    for relative, expected_items in sorted(wanted.items()):
        source_path = root / relative
        manifest_path = source_path.parent / "manifest.json"
        if not source_path.is_file() or not manifest_path.is_file():
            raise ValueError("Pinned historical import ledger or its manifest is missing")
        expected_file = next(iter(expected_items.values()))["source_file_sha256"]
        if any(item["source_file_sha256"] != expected_file for item in expected_items.values()):
            raise ValueError("Historical imports disagree on their source file hash")
        manifest = _json(manifest_path)
        expected_from_manifest = manifest.get("files_sha256", {}).get(source_path.name)
        if expected_from_manifest != expected_file:
            raise ValueError("Historical source file is not bound by its adjacent manifest")
        manifest_rel = source_index.add(manifest_path, "historical_source_segment_manifest")
        source_rel = source_index.add(source_path, "historical_import_attempt_ledger",
                                     expected_sha256=expected_file, bound_by=manifest_rel)
        found: dict[str, tuple[int, dict[str, Any]]] = {}
        line_count = 0
        with source_path.open("rb") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                line_count += 1
                if not line.endswith(b"\n"):
                    raise ValueError("Pinned historical source ledger has a torn final row")
                row = json.loads(line)
                item = expected_items.get(str(row.get("key")))
                if item is None:
                    continue
                if hashlib.sha256(line).hexdigest() != item["source_record_sha256"]:
                    raise ValueError("Pinned historical source record checksum differs")
                if row.get("raw_response_sha256") != item["source_raw_response_sha256"]:
                    raise ValueError("Pinned historical source response hash differs")
                found[str(row["key"])] = (line_number, row)
        source_index.entries[source_rel]["rows"] = line_count
        if set(found) != set(expected_items):
            raise ValueError("Could not resolve every pinned historical import record")
        for action_key, imported in action_keys.items():
            if imported["reply_path"] == relative:
                resolved[action_key] = found[str(imported["key"])]
    if set(resolved) != set(action_keys):
        raise ValueError("Historical import source references are incomplete")
    return resolved


def _read_inputs(
    source_index: _SourceIndex,
    root: Path,
    alias_to_source: dict[str, dict[str, str]],
    public_ids: dict[str, int],
) -> tuple[dict[tuple[str, str, str], dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    input_root = root / INPUT_ROOT
    candidate_path = input_root / "candidate_manifest.json"
    candidate_manifest = _json(candidate_path)
    source_index.add(candidate_path, "complete_input_candidate_manifest")
    prompt_filename = candidate_manifest.get("complete_prompt_file")
    if not prompt_filename or Path(prompt_filename).name != prompt_filename:
        raise ValueError("Input manifest has an unsafe complete prompt filename")
    prompt_path = input_root / prompt_filename
    expected = candidate_manifest.get("files", {}).get(prompt_filename, {}).get("sha256")
    if not expected:
        raise ValueError("Input candidate manifest does not hash the complete prompt file")
    prompt_path_rel = source_index.add(prompt_path, "complete_prompt_source", expected_sha256=expected,
                                       bound_by=_safe_rel(root, candidate_path))
    inputs: dict[tuple[str, str, str], dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for line_number, row in _jsonl_gz(prompt_path):
        run = str(row["run"])
        if run not in RUN_ROOTS:
            raise ValueError("Unexpected run in exact input source")
        period, household = str(row["period"]), str(row["household"])
        source_agent_id = alias_to_source[run].get(household)
        if source_agent_id is None:
            raise ValueError("Exact input household alias is missing from the source ID map")
        public_id = public_ids.get(source_agent_id) if run == "A" else None
        item = {
            "input_id": _input_id(run, period, household),
            "run": run,
            "period": period,
            "household": household,
            "source_agent_id": source_agent_id,
            "public_sce_userid": public_id,
            "original_prompt_sha256": row["original_prompt_sha256"],
            "delivered_prompt_sha256": row["delivered_prompt_sha256"],
            "complete_prompt_source_path": prompt_path_rel,
            "complete_prompt_source_sha256": expected,
            "complete_prompt_source_line": line_number,
        }
        key = (run, period, household)
        if key in inputs:
            raise ValueError("Duplicate complete input slot")
        if item["original_prompt_sha256"] != item["delivered_prompt_sha256"]:
            raise ValueError("Complete prompt hashes differ; exact input preservation is unverified")
        inputs[key] = item
        records.append(item)
        counts[run] += 1
    expected_total = int(candidate_manifest.get("full_prompt_rows", -1))
    if len(records) != expected_total:
        raise ValueError("Complete prompt row count differs from candidate manifest")
    for run, details in candidate_manifest.get("runs", {}).items():
        if run in RUN_ROOTS and counts[run] != int(details.get("complete_prompts", -1)):
            raise ValueError("Complete prompt run count differs from candidate manifest")
    source_index.entries[prompt_path_rel]["rows"] = len(records)
    return inputs, records, candidate_manifest


def _read_model_outputs(source_index: _SourceIndex, data_root: Path) -> tuple[list[dict[str, Any]], dict[tuple[str, str, str, str], dict[str, Any]]]:
    path = data_root / "model_outputs.jsonl.gz"
    records = [row for _, row in _jsonl_gz(path)]
    by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    response_ids: set[str] = set()
    for row in records:
        key = (str(row["run"]), str(row["period"]), str(row["household"]), str(row["stage"]))
        if key in by_key:
            raise ValueError("Duplicate exported response for a run/period/alias/stage")
        if row["response_id"] in response_ids:
            raise ValueError("Duplicate response_id in existing micro export")
        by_key[key] = row
        response_ids.add(row["response_id"])
    return records, by_key


def _read_effective_answers(
    source_index: _SourceIndex,
    data_root: Path,
    model_by_id: dict[str, dict[str, Any]],
    alias_to_source: dict[str, dict[str, str]],
    public_ids: dict[str, int],
    inputs: dict[tuple[str, str, str], dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    path = data_root / "effective_answers.jsonl.gz"
    answers: list[dict[str, Any]] = []
    selected_by_response: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unique_slots: set[tuple[str, str, str]] = set()
    for index, (line_number, source) in enumerate(_jsonl_gz(path), 1):
        row = dict(source)
        run, period, household = str(row["run"]), str(row["period"]), str(row["household"])
        source_agent_id = alias_to_source[run].get(household)
        if source_agent_id is None:
            raise ValueError("Effective answer alias is missing from the source ID map")
        slot = (run, period, household)
        if slot in unique_slots:
            raise ValueError("Duplicate effective answer for a run/period/alias")
        unique_slots.add(slot)
        input_row = inputs.get(slot)
        input_join_kind = "same_run_period_household"
        if input_row is None and run == "monthly" and row.get("shared_B_root"):
            shared = row["shared_B_root"]
            shared_slot = ("B", str(shared["period"]), str(shared["household"]))
            input_row = inputs.get(shared_slot)
            if input_row is None:
                raise ValueError("Monthly shared-root answer has no matching B input")
            if input_row["source_agent_id"] != source_agent_id:
                raise ValueError("Monthly shared-root alias does not identify the B root agent")
            input_join_kind = "shared_B_root"
        if input_row is None:
            raise ValueError("Effective answer has no canonical input row")
        row["answer_id"] = _answer_id(index)
        row["source_agent_id"] = source_agent_id
        row["public_sce_userid"] = public_ids.get(source_agent_id) if run == "A" else None
        row["input_id"] = input_row["input_id"]
        row["input_join_kind"] = input_join_kind
        row["input_origin"] = {
            "run": input_row["run"],
            "period": input_row["period"],
            "household": input_row["household"],
            "source_agent_id": input_row["source_agent_id"],
            "public_sce_userid": input_row["public_sce_userid"],
        }
        row["source_effective_answer_path"] = "outputs/sce_micro_reproduction_20261029_v3/data/effective_answers.jsonl.gz"
        row["source_effective_answer_line"] = line_number
        for field in ("q8", "q9"):
            response_id = (row.get("selected_responses") or {}).get(field)
            if response_id is not None:
                if response_id not in model_by_id:
                    raise ValueError("Effective answer selects a missing model output")
                selected_by_response[response_id].append({"answer_id": row["answer_id"], "field": field})
        answers.append(row)
    return answers, selected_by_response


def _discover_call_files(root: Path) -> dict[str, list[Path]]:
    result: dict[str, list[Path]] = {}
    for run, relative in RUN_ROOTS.items():
        folder = root / relative
        if run in ("A", "B"):
            search_roots = [folder / "main", folder / "repair"]
        else:
            search_roots = [folder / "waves"]
        paths = sorted(path for search_root in search_roots if search_root.is_dir()
                       for path in search_root.rglob("calls_private.jsonl"))
        if not paths:
            raise ValueError("No final call ledgers were found for " + run)
        result[run] = paths
    return result


def _stage_and_period(run: str, folder: Path, path: Path, row: dict[str, Any]) -> tuple[str, str]:
    parts = path.relative_to(folder).parts
    stage = "repair" if "repair" in parts else "main"
    wave = parts[1] if parts[0] == "waves" else None
    return stage, str(wave or row["month"])


def _export_actual_receipts(source_index: _SourceIndex, root: Path, out_data: Path,
                            call_files: dict[str, list[Path]]) -> tuple[int, dict[str, int], int]:
    paths: dict[str, tuple[Path, str]] = {}
    for run, call_paths in call_files.items():
        folder = root / RUN_ROOTS[run]
        for call_path in call_paths:
            receipt = call_path.parent / "receipt.json"
            paths[_safe_rel(root, receipt)] = (receipt, "call_segment")
        for name in ("main_receipt.json", "repair_receipt.json", "generation_receipt.json", "worker_receipt.json"):
            receipt = folder / name
            if receipt.is_file():
                paths[_safe_rel(root, receipt)] = (receipt, "run")
        if run in ("monthly", "weekly"):
            for wave_dir in sorted((folder / "waves").glob("*")):
                for name in ("main_receipt.json", "repair_receipt.json"):
                    receipt = wave_dir / name
                    if receipt.is_file():
                        paths[_safe_rel(root, receipt)] = (receipt, "wave")
        if run == "A":
            generation_receipt = folder / "generation_views/view_0001/receipt.json"
            if generation_receipt.is_file():
                paths[_safe_rel(root, generation_receipt)] = (generation_receipt, "generation_view")

    counts: Counter[str] = Counter()
    records = []
    normalized_paths = 0
    for source_path, (path, scope) in sorted(paths.items()):
        source_index.add(path, "actual_call_receipt")
        value, normalized = _portable_receipt(_json(path), root)
        normalized_paths += normalized
        _check_secrets(value)
        run = next(run for run, rel in RUN_ROOTS.items() if source_path.startswith(rel + "/"))
        record = {
            "receipt_id": f"receipt_{len(records) + 1:06d}",
            "run": run,
            "scope": scope,
            "source_path": source_path,
            "source_sha256": _sha256(path),
            "receipt": value,
            "normalized_repository_path_values": normalized,
        }
        records.append(record)
        counts[run] += 1
    count = _write_jsonl_gz(out_data / "actual_call_receipts.jsonl.gz", records)
    return count, dict(sorted(counts.items())), normalized_paths


def _iter_raw_call_receipts(source_index: _SourceIndex, root: Path,
                            call_files: dict[str, list[Path]],
                            alias_by_run: dict[str, dict[str, str]],
                            public_ids: dict[str, int],
                            model_by_key: dict[tuple[str, str, str, str], dict[str, Any]],
                            model_by_id: dict[str, dict[str, Any]],
                            inputs: dict[tuple[str, str, str], dict[str, Any]],
                            selected_by_response: dict[str, list[dict[str, Any]]],
                            actions: dict[tuple[str, str], tuple[int, dict[str, Any]]],
                            historical_sources: dict[tuple[str, str], tuple[int, dict[str, Any]]],
                            ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    request_ids: set[str] = set()
    request_id_rows = 0
    missing_request_id_rows = 0
    request_id_on_reused_rows = 0
    physical_with_request_id = 0
    fingerprint_present = 0
    started_present = 0
    finished_present = 0
    latency_present = 0
    usage_present = 0
    error_rows = 0
    missing_id_error_rows = 0
    missing_id_nonerror_rows = 0
    input_hash_matches = 0
    input_hash_differs = 0
    main_input_hash_mismatches = 0

    for run in RUN_ROOTS:
        folder = root / RUN_ROOTS[run]
        for call_path in call_files[run]:
            segment_manifest_path = call_path.parent / "manifest.json"
            segment_manifest_rel = _check_manifest_binding(source_index, segment_manifest_path, call_path)
            dispatch_path = call_path.parent / "dispatch_private.jsonl"
            if not dispatch_path.is_file():
                raise ValueError("Call segment has no dispatch ledger")
            dispatch_manifest_hash = _json(segment_manifest_path).get("files_sha256", {}).get(dispatch_path.name)
            if not dispatch_manifest_hash:
                raise ValueError("Segment manifest does not bind its dispatch ledger")
            dispatch_rel = source_index.add(dispatch_path, "dispatch_ledger", expected_sha256=dispatch_manifest_hash,
                                           bound_by=segment_manifest_rel)
            dispatch_rows: dict[str, tuple[int, dict[str, Any]]] = {}
            for line_number, dispatch in _jsonl(dispatch_path):
                key = str(dispatch["key"])
                if key in dispatch_rows:
                    raise ValueError("Duplicate dispatch key in a call segment")
                dispatch_rows[key] = (line_number, dispatch)
            source_index.entries[_safe_rel(root, dispatch_path)]["rows"] = len(dispatch_rows)

            file_row_count = 0
            for line_number, raw in _jsonl(call_path):
                file_row_count += 1
                if raw.get("actual_model_results") is not True:
                    raise ValueError("Call ledger contains a non-production fixture")
                stage, period = _stage_and_period(run, folder, call_path, raw)
                source_agent_id = str(raw["agent_id"])
                household = alias_by_run[run].get(source_agent_id)
                if household is None:
                    raise ValueError(f"Source Agent ID has no {run} alias in the original data-code map")
                key = (run, period, household, stage)
                model = model_by_key.get(key)
                if model is None:
                    raise ValueError("Raw ledger row has no existing model response_id join")
                input_row = inputs.get((run, period, household))
                if input_row is None:
                    raise ValueError("Raw attempt has no canonical input position")
                if raw.get("prompt_sha256") != model.get("prompt_sha256"):
                    raise ValueError("Raw ledger prompt hash differs from existing model output")
                if raw.get("raw_response_sha256") != model.get("original_response_sha256"):
                    raise ValueError("Raw ledger response hash differs from existing model output")
                if raw.get("raw_response_text") != model.get("response_text"):
                    raise ValueError("Raw ledger response text differs from existing model output")
                if model.get("response_text_redacted") is not False:
                    raise ValueError("Existing response export is not an unredacted source projection")
                if raw.get("raw_response_sha256") and hashlib.sha256(
                    str(raw.get("raw_response_text") or "").encode("utf-8")
                ).hexdigest() != raw.get("raw_response_sha256"):
                    raise ValueError("Raw ledger response text fails its recorded SHA-256")
                dispatch_pair = dispatch_rows.get(str(raw["key"]))
                if dispatch_pair is None:
                    raise ValueError("Raw call row has no exact dispatch key")
                dispatch_line, dispatch = dispatch_pair
                if dispatch.get("prompt_sha256") != raw.get("prompt_sha256"):
                    raise ValueError("Dispatch and response prompt hashes differ")
                if input_row["original_prompt_sha256"] == raw.get("prompt_sha256"):
                    input_hash_matches += 1
                    input_hash_equal = True
                else:
                    input_hash_differs += 1
                    input_hash_equal = False
                    if stage == "main":
                        main_input_hash_mismatches += 1

                logical_action = None
                historical_source_ref = None
                if run == "A":
                    action_key = (period, source_agent_id)
                    action_pair = actions.get(action_key)
                    if action_pair is None:
                        raise ValueError("A raw call has no original logical action record")
                    action_line, action = action_pair
                    stage_action = action.get(stage) or {}
                    expected_reply_ref = call_path.relative_to(folder).as_posix() + f"#key={raw['key']}"
                    expected_dispatch_ref = dispatch_path.relative_to(folder).as_posix() + f"#key={raw['key']}"
                    if stage_action.get("raw_reply_ref") != expected_reply_ref:
                        raise ValueError("A logical action raw_reply_ref does not identify this call row")
                    if stage_action.get("dispatch_ref") != expected_dispatch_ref:
                        raise ValueError("A logical action dispatch_ref does not identify this dispatch row")
                    if stage_action.get("historical_source"):
                        historical_key = (period, source_agent_id)
                        historical_pair = historical_sources.get(historical_key)
                        if historical_pair is None:
                            raise ValueError("Historical import source row could not be resolved")
                        historical_line, historical_row = historical_pair
                        historical_record = stage_action["historical_source"]
                        if (raw.get("request_id") != historical_row.get("request_id")
                                or raw.get("raw_response_sha256") != historical_row.get("raw_response_sha256")
                                or raw.get("source_api_reported_cost_usd") != historical_row.get("api_reported_cost_usd")
                                or raw.get("source_request_reservation_usd") != historical_row.get("request_reservation_usd")):
                            raise ValueError("Imported call receipt differs from its pinned historical source row")
                        historical_source_ref = {
                            "path": historical_record["reply_path"],
                            "line": historical_line,
                            "source_file_sha256": historical_record["source_file_sha256"],
                            "source_record_sha256": historical_record["source_record_sha256"],
                            "source_raw_response_sha256": historical_record["source_raw_response_sha256"],
                        }
                    logical_action = {
                        "source_path": A_ACTIONS,
                        "source_line": action_line,
                        "stage": stage,
                        "attempt_state": action.get("attempt_state"),
                        "execution_kind": stage_action.get("execution_kind"),
                        "dispatch_ref": stage_action.get("dispatch_ref"),
                        "raw_reply_ref": stage_action.get("raw_reply_ref"),
                        "historical_source": stage_action.get("historical_source"),
                        "action_error": stage_action.get("error"),
                        "field_source": action.get("field_source"),
                        "field_updated": action.get("field_updated"),
                        "needs_initial_fallback": action.get("needs_initial_fallback"),
                        "effective_q8": action.get("effective_q8"),
                        "effective_q9_bins": action.get("effective_q9_bins"),
                        "q9_normalization": action.get("q9_normalization"),
                    }

                request_id = raw.get("request_id")
                if request_id is None:
                    missing_request_id_rows += 1
                    if raw.get("error") is not None:
                        missing_id_error_rows += 1
                    else:
                        missing_id_nonerror_rows += 1
                else:
                    request_id_rows += 1
                    request_id = str(request_id)
                    if request_id in request_ids:
                        raise ValueError("Duplicate original request_id in final-task ledgers")
                    request_ids.add(request_id)
                    if model.get("historical_exact_prompt_reuse") is True:
                        request_id_on_reused_rows += 1
                    if model.get("physical_new_api_attempt") is True:
                        physical_with_request_id += 1
                started_present += raw.get("started_at_utc") is not None
                finished_present += raw.get("finished_at_utc") is not None
                latency_present += raw.get("latency_ms") is not None
                usage_present += raw.get("usage") is not None
                fingerprint_present += raw.get("system_fingerprint") is not None
                error_rows += raw.get("error") is not None
                _check_secrets(raw.get("error"))

                response_id = str(model["response_id"])
                item = {
                    "attempt_id": f"attempt_{len(records) + 1:07d}",
                    "response_id": response_id,
                    "run": run,
                    "period": period,
                    "household": household,
                    "source_agent_id": source_agent_id,
                    "public_sce_userid": public_ids.get(source_agent_id) if run == "A" else None,
                    "stage": stage,
                    "key": raw.get("key"),
                    "arm": raw.get("arm"),
                    "repeat": raw.get("repeat"),
                    "attempt_idx": raw.get("attempt_idx"),
                    "request_id": request_id,
                    "request_id_source_status": "present" if request_id is not None else "missing_in_source",
                    "started_at_utc": raw.get("started_at_utc"),
                    "finished_at_utc": raw.get("finished_at_utc"),
                    "latency_ms": raw.get("latency_ms"),
                    "returned_model": raw.get("returned_model"),
                    "returned_provider": raw.get("returned_provider"),
                    "system_fingerprint": raw.get("system_fingerprint"),
                    "usage": raw.get("usage"),
                    "api_reported_cost_usd": raw.get("api_reported_cost_usd"),
                    "request_reservation_usd": raw.get("request_reservation_usd"),
                    "source_api_reported_cost_usd": raw.get("source_api_reported_cost_usd"),
                    "source_request_reservation_usd": raw.get("source_request_reservation_usd"),
                    "prompt_sha256": raw.get("prompt_sha256"),
                    "raw_response_sha256": raw.get("raw_response_sha256"),
                    "finish_reason": raw.get("finish_reason"),
                    "error": raw.get("error"),
                    "fatal": raw.get("fatal"),
                    "technical_usable": raw.get("technical_usable"),
                    "field_usable": raw.get("field_usable"),
                    "actual_model_results": raw.get("actual_model_results"),
                    "physical_new_api_attempt": model.get("physical_new_api_attempt"),
                    "historical_exact_prompt_reuse": model.get("historical_exact_prompt_reuse"),
                    "input_id": input_row["input_id"],
                    "input_original_prompt_sha256": input_row["original_prompt_sha256"],
                    "input_hash_equal_to_canonical_prompt": input_hash_equal,
                    "selected_by_effective_answers": selected_by_response.get(response_id, []),
                    "logical_action": logical_action,
                    "historical_source_ref": historical_source_ref,
                    "source_attempt_ref": {"path": _safe_rel(root, call_path), "line": line_number,
                                           "segment_manifest_path": segment_manifest_rel},
                    "source_dispatch_ref": {"path": dispatch_rel, "line": dispatch_line,
                                            "dispatch_at_utc": dispatch.get("at_utc"),
                                            "reserved_usd": dispatch.get("reserved_usd")},
                }
                _check_secrets(item)
                records.append(item)
                counts[run + "_attempts"] += 1
            source_index.entries[_safe_rel(root, call_path)]["rows"] = file_row_count

    expected_keys = set(model_by_key)
    observed_keys = {
        (row["run"], row["period"], row["household"], row["stage"])
        for row in records
    }
    if observed_keys != expected_keys or len(records) != len(model_by_key):
        raise ValueError("Raw call rows do not exactly join one-to-one to exported response IDs")
    stats = {
        "attempts": len(records),
        "attempts_by_run": {run: counts[run + "_attempts"] for run in RUN_ROOTS},
        "request_id_rows": request_id_rows,
        "unique_request_ids": len(request_ids),
        "missing_request_id_rows": missing_request_id_rows,
        "request_id_on_historical_reuse_rows": request_id_on_reused_rows,
        "physical_new_api_attempts": sum(row["physical_new_api_attempt"] is True for row in records),
        "physical_new_api_attempts_with_request_id": physical_with_request_id,
        "started_at_rows": started_present,
        "finished_at_rows": finished_present,
        "latency_rows": latency_present,
        "usage_rows": usage_present,
        "error_rows": error_rows,
        "missing_request_id_rows_with_error": missing_id_error_rows,
        "missing_request_id_rows_without_error": missing_id_nonerror_rows,
        "system_fingerprint_present_rows": fingerprint_present,
        "system_fingerprint_null_rows": len(records) - fingerprint_present,
        "canonical_input_hash_equal_rows": input_hash_matches,
        "canonical_input_hash_different_rows": input_hash_differs,
        "main_input_hash_mismatches": main_input_hash_mismatches,
        "all_request_ids_unique": len(request_ids) == request_id_rows,
    }
    if request_id_rows != len(request_ids):
        raise ValueError("Original request IDs are not unique")
    if started_present != len(records) or finished_present != len(records):
        raise ValueError("At least one raw attempt is missing a timestamp")
    if missing_id_nonerror_rows:
        raise ValueError("A raw attempt without request_id has no recorded source error")
    if main_input_hash_mismatches:
        raise ValueError("At least one main call prompt hash differs from its canonical complete input")
    return records, stats


def export(out: str | Path, root: str | Path = ROOT) -> dict[str, Any]:
    """Export a deterministic, allowlisted evidence bundle for four final runs.

    Args:
        out: A new directory for the export. Existing directories are rejected.
        root: Repository root containing the frozen sources; defaults to this repo.

    Returns:
        The written manifest with relative paths, byte counts, hashes, and row counts.
    """
    root = Path(root).resolve()
    out = Path(out)
    out = (root / out).resolve() if not out.is_absolute() else out.resolve()
    if out.exists():
        raise ValueError("Choose a fresh output directory")
    if out == root or root.is_relative_to(out):
        raise ValueError("Output path cannot replace or contain the source repository")
    for source_rel in (*RUN_ROOTS.values(), MICRO_DATA, INPUT_ROOT):
        if out.is_relative_to((root / source_rel).resolve()):
            raise ValueError("Output path cannot be inside a frozen source directory")
    out.mkdir(parents=True)
    data_out = out / "data"
    data_out.mkdir()
    source_index = _SourceIndex(root)

    alias_map, source_to_alias, alias_to_source = _load_expected_map(source_index, root)
    public_ids = _load_public_sce_ids(source_index, root)
    data_root, data_manifest = _validate_data_manifest(
        source_index, root, ("model_outputs.jsonl.gz", "effective_answers.jsonl.gz")
    )
    inputs, input_records, candidate_manifest = _read_inputs(source_index, root, alias_to_source, public_ids)
    model_records, model_by_key = _read_model_outputs(source_index, data_root)
    model_by_id = {str(row["response_id"]): row for row in model_records}
    if len(model_by_id) != len(model_records):
        raise ValueError("Response IDs are not unique")
    answer_records, selected_by_response = _read_effective_answers(
        source_index, data_root, model_by_id, alias_to_source, public_ids, inputs
    )
    actions = _read_actions(source_index, root)
    historical_sources = _read_historical_sources(source_index, root, actions)
    call_files = _discover_call_files(root)

    # Bind the original run-level manifests where available, plus the private
    # exporter map and its detailed source ledger.
    for run, relative in RUN_ROOTS.items():
        run_manifest = root / relative / "manifest.json"
        if run_manifest.is_file():
            source_index.add(run_manifest, "frozen_run_manifest")
    private_source_manifest = root / PRIVATE_SOURCE_MANIFEST
    if private_source_manifest.is_file():
        source_index.add(private_source_manifest, "existing_micro_export_source_manifest")
    source_index.add(root / A_ACTIONS, "A_logical_action_ledger")
    exporter_path = Path(__file__).resolve()
    if exporter_path.is_relative_to(root):
        source_index.add(exporter_path, "portable_evidence_exporter_source")

    # Keep the exact alias map as a data-code map; original internal IDs are
    # opaque SCE/proxy identifiers, not names or credentials.
    map_path = root / PRIVATE_ID_MAP
    (data_out / "source_agent_id_map.json").write_bytes(map_path.read_bytes())
    used_sources = {(str(row["run"]), row["source_agent_id"]) for row in input_records}
    used_id_rows = []
    for run in RUN_ROOTS:
        for source_agent_id, alias in sorted(source_to_alias[run].items(), key=lambda pair: pair[1]):
            if (run, source_agent_id) not in used_sources:
                continue
            used_id_rows.append({
                "run": run,
                "household": alias,
                "source_agent_id": source_agent_id,
                "public_sce_userid": public_ids.get(source_agent_id) if run == "A" else None,
            })
    public_map = {
        row["household"]: row["public_sce_userid"]
        for row in used_id_rows if row["run"] == "A"
    }
    _write_json(data_out / "public_sce_userid_map.json", public_map)
    agent_id_rows = _write_jsonl_gz(data_out / "agent_id_crosswalk.jsonl.gz", used_id_rows)
    input_rows = _write_jsonl_gz(data_out / "input_index.jsonl.gz", input_records)
    enriched_models = []
    for source in model_records:
        row = dict(source)
        run, period, household = str(row["run"]), str(row["period"]), str(row["household"])
        source_agent_id = alias_to_source[run].get(household)
        if source_agent_id is None:
            raise ValueError("Existing model output alias is missing from the original source map")
        input_row = inputs.get((run, period, household))
        if input_row is None:
            raise ValueError("Existing model output has no complete prompt input row")
        row["source_agent_id"] = source_agent_id
        row["public_sce_userid"] = public_ids.get(source_agent_id) if run == "A" else None
        row["input_id"] = input_row["input_id"]
        enriched_models.append(row)
    _check_secrets(enriched_models)
    model_rows = _write_jsonl_gz(data_out / "model_outputs.jsonl.gz", enriched_models)
    effective_rows = _write_jsonl_gz(data_out / "effective_answers.jsonl.gz", answer_records)
    receipt_rows, receipt_counts, normalized_receipt_paths = _export_actual_receipts(source_index, root, data_out, call_files)
    call_records, call_stats = _iter_raw_call_receipts(
        source_index, root, call_files, source_to_alias, public_ids,
        model_by_key, model_by_id, inputs, selected_by_response, actions, historical_sources,
    )
    call_rows = _write_jsonl_gz(data_out / "call_receipts.jsonl.gz", call_records)

    # Validate exact answer coverage and preserve explicit metadata for empty
    # fingerprints/missing vendor IDs instead of filling either field.
    answer_counts = Counter(str(row["run"]) for row in answer_records)
    input_counts = Counter(str(row["run"]) for row in input_records)
    expected_inputs = {
        run: int(candidate_manifest.get("runs", {}).get(run, {}).get("complete_prompts", -1))
        for run in RUN_ROOTS
    }
    if dict(input_counts) != expected_inputs:
        raise ValueError("Exact prompt input run counts changed")
    expected_answers = {
        run: int(data_manifest.get("counts", {}).get(f"{run}_answers", -1))
        for run in RUN_ROOTS
    }
    if dict(answer_counts) != expected_answers:
        raise ValueError("Effective answer run counts changed")
    expected_attempts = {
        run: int(data_manifest.get("counts", {}).get(f"{run}_attempts", -1))
        for run in RUN_ROOTS
    }
    if call_stats["attempts_by_run"] != expected_attempts:
        raise ValueError("Raw call attempt counts differ from the final task scope")
    if call_rows != model_rows or call_rows != len(model_records):
        raise ValueError("Call receipts and model outputs are not one-to-one")

    provenance = source_index.manifest()
    provenance_path = out / "source_provenance.json"
    _write_json(provenance_path, provenance)

    output_paths = [
        data_out / "source_agent_id_map.json",
        data_out / "public_sce_userid_map.json",
        data_out / "agent_id_crosswalk.jsonl.gz",
        data_out / "input_index.jsonl.gz",
        data_out / "model_outputs.jsonl.gz",
        data_out / "effective_answers.jsonl.gz",
        data_out / "actual_call_receipts.jsonl.gz",
        data_out / "call_receipts.jsonl.gz",
        provenance_path,
    ]
    row_counts = {
        "data/source_agent_id_map.json": len(alias_map),
        "data/public_sce_userid_map.json": len(public_map),
        "data/agent_id_crosswalk.jsonl.gz": agent_id_rows,
        "data/input_index.jsonl.gz": input_rows,
        "data/model_outputs.jsonl.gz": model_rows,
        "data/effective_answers.jsonl.gz": effective_rows,
        "data/actual_call_receipts.jsonl.gz": receipt_rows,
        "data/call_receipts.jsonl.gz": call_rows,
        "source_provenance.json": len(provenance["sources"]),
    }
    files = {}
    for path in output_paths:
        relative = path.relative_to(out).as_posix()
        files[relative] = {"bytes": path.stat().st_size, "sha256": _sha256(path), "records": row_counts[relative]}
    manifest = {
        "schema": "sce_portable_call_evidence/v1",
        "scope": list(RUN_ROOTS),
        "files": files,
        "counts": {
            "input_positions": len(input_records),
            "effective_answers": len(answer_records),
            **call_stats,
            "actual_receipt_files": receipt_rows,
            "actual_receipt_files_by_run": receipt_counts,
            "receipt_repository_path_values_normalized": normalized_receipt_paths,
        },
        "join_contract": {
            "input_to_call": "input_id + (run, period, household alias); main prompt SHA-256 was checked against the complete input hash.",
            "raw_call_to_model_output": "response_id; one-to-one exact match on (run, period, household alias, stage) and verified response SHA-256/text.",
            "model_output_to_effective_answer": "effective_answers.selected_responses.q8/q9 contain response_id; call_receipts.selected_by_effective_answers lists those answer-field references.",
            "source_id_map": "source_agent_id_map.json preserves alias -> original internal Agent ID; public_sce_userid_map.json maps A aliases to original public SCE userid values from A cases.",
            "repair_and_fallback": "stage plus source_dispatch_ref identifies each dispatch; A logical_action preserves original repair/raw_reply refs; effective_answers retains field source and any fallback record.",
            "receipt_path_projection": "Receipt values are preserved; an absolute prefix matching the repository root is written repository-relative, while each original receipt file hash is retained.",
        },
        "integrity": {
            "original_response_text_redactions": 0,
            "request_id_fabricated": False,
            "system_fingerprint_fabricated": False,
            "credentials_or_auth_headers_included": False,
            "receipt_repository_path_values_normalized": normalized_receipt_paths,
            "new_api_calls": 0,
            "external_provider_signature_verified": False,
            "claim": "Source bytes and manifest bindings were checked locally; no external signature verification is claimed.",
        },
        "source_provenance_path": "source_provenance.json",
        "source_provenance_sha256": files["source_provenance.json"]["sha256"],
    }
    _write_json(out / "manifest.json", manifest)
    return manifest

