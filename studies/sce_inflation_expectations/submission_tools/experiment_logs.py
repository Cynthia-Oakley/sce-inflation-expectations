"""Build a privacy-aware index of selected SCE experiment receipts.

The registry is intentionally allowlist-driven. It reads only explicitly named
small JSON metadata receipts, protocols, run manifests, and token ledgers. It
never opens simulation replies, private call JSONL files, or model answer data.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SCHEMA_VERSION = "sce-submission-experiment-registry/v2"

PUBLIC_RECORD_FIELDS = (
    "experiment_id",
    "title",
    "category",
    "status",
    "period",
    "month_count",
    "n_per_month",
    "logical_person_months",
    "condition_person_months",
    "planned_generation_slots",
    "main_physical_requests",
    "repair_physical_requests",
    "physical_requests_total",
    "snapshot_physical_requests",
    "snapshot_logical_attempts",
    "snapshot_completed_returns",
    "snapshot_in_flight",
    "historical_reuse_slots",
    "planned_historical_reuse_slots",
    "repeat_count",
    "arm_count",
    "model",
    "provider",
    "temperature",
    "arm_settings",
    "seed_summary",
    "reported_api_cost_usd",
    "unknown_fee_reserve_usd",
    "token_usage_estimate_usd",
    "combined_cost_unseparated_usd",
    "duration_seconds",
    "duration_scope",
    "snapshot_as_of_utc",
    "usable_responses",
    "main_usable_responses",
    "repair_usable_responses",
    "final_q8_updated",
    "final_q9_updated",
    "final_both_fields_updated",
    "final_q9_initial_fallback_needed",
    "unresolved_responses",
    "evaluation_status",
    "evaluation_new_api_calls",
    "evaluation_person_months",
    "evaluation_new_q9_density_fits",
    "evaluation_q9_density_fit_fallbacks",
    "evaluation_q9_retained_input_count",
    "evaluation_q8_complete",
    "historical_source_reported_cost_usd",
    "failure_summary",
    "repair_summary",
    "snapshot_only",
    "cost_coverage_note",
)

PRIVATE_CSV_FIELDS = (
    "experiment_id",
    "title",
    "category",
    "status",
    "period",
    "month_count",
    "n_per_month",
    "logical_person_months",
    "condition_person_months",
    "planned_generation_slots",
    "main_physical_requests",
    "repair_physical_requests",
    "physical_requests_total",
    "snapshot_physical_requests",
    "snapshot_logical_attempts",
    "snapshot_completed_returns",
    "snapshot_in_flight",
    "historical_reuse_slots",
    "planned_historical_reuse_slots",
    "repeat_count",
    "arm_count",
    "model",
    "provider",
    "temperature",
    "arm_settings",
    "seed_summary",
    "reported_api_cost_usd",
    "unknown_fee_reserve_usd",
    "token_usage_estimate_usd",
    "combined_cost_unseparated_usd",
    "duration_seconds",
    "duration_scope",
    "snapshot_as_of_utc",
    "usable_responses",
    "main_usable_responses",
    "repair_usable_responses",
    "final_q8_updated",
    "final_q9_updated",
    "final_both_fields_updated",
    "final_q9_initial_fallback_needed",
    "unresolved_responses",
    "evaluation_status",
    "evaluation_new_api_calls",
    "evaluation_person_months",
    "evaluation_new_q9_density_fits",
    "evaluation_q9_density_fit_fallbacks",
    "evaluation_q9_retained_input_count",
    "evaluation_q8_complete",
    "historical_source_reported_cost_usd",
    "failure_summary",
    "repair_summary",
    "snapshot_only",
    "included_in_cost_subtotal",
    "charge_group",
    "cost_coverage_note",
    "notes",
    "source_fingerprints_json",
    "receipt_components_json",
)


def _safe_repo_path(repo_root: Path, relative_path: str) -> Path:
    rel = PurePosixPath(relative_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"Source path must be repository-relative: {relative_path!r}")
    resolved_root = repo_root.resolve()
    resolved = (resolved_root / Path(*rel.parts)).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Source path escapes repository root: {relative_path!r}") from exc
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fingerprint(repo_root: Path, relative_path: str, role: str) -> dict[str, Any]:
    path = _safe_repo_path(repo_root, relative_path)
    if not path.is_file():
        return {"path": relative_path, "role": role, "exists": False}
    return {
        "path": relative_path,
        "role": role,
        "exists": True,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _read_metadata_json(repo_root: Path, relative_path: str) -> Any:
    """Read a specifically allowlisted JSON metadata file, with a size guard."""
    path = _safe_repo_path(repo_root, relative_path)
    size = path.stat().st_size
    if size > 8 * 1024 * 1024:
        raise ValueError(f"Refusing oversized metadata JSON ({size} bytes): {relative_path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _dotted_value(obj: Any, dotted_path: str) -> Any:
    current = obj
    if not dotted_path:
        return current
    for part in dotted_path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return None
    return current


def _extract_value(obj: Any, expression: Any) -> Any:
    if expression is None:
        return None
    if isinstance(expression, str):
        return _dotted_value(obj, expression)
    if not isinstance(expression, dict):
        return expression
    if "subtract" in expression:
        left, right = expression["subtract"]
        a, b = _extract_value(obj, left), _extract_value(obj, right)
        return None if a is None or b is None else float(a) - float(b)
    if "sum" in expression:
        values = [_extract_value(obj, item) for item in expression["sum"]]
        return None if any(item is None for item in values) else sum(float(item) for item in values)
    if "multiply" in expression:
        left, right = expression["multiply"]
        a, b = _extract_value(obj, left), _extract_value(obj, right)
        return None if a is None or b is None else float(a) * float(b)
    raise ValueError(f"Unsupported field expression: {expression!r}")


def _receipt_components(repo_root: Path, record_spec: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    components: list[dict[str, Any]] = []
    fingerprints: list[dict[str, Any]] = []
    seen_fingerprints: set[tuple[str, str]] = set()
    for spec in record_spec.get("receipt_components", []):
        rel = spec["path"]
        path = _safe_repo_path(repo_root, rel)
        if not path.is_file():
            fingerprints.append({"path": rel, "role": spec.get("role", "receipt"), "exists": False})
            continue
        fingerprint_key = (rel, spec.get("role", "receipt"))
        if fingerprint_key not in seen_fingerprints:
            fingerprints.append(_fingerprint(repo_root, rel, spec.get("role", "receipt")))
            seen_fingerprints.add(fingerprint_key)
        obj = _read_metadata_json(repo_root, rel)
        base_path = spec.get("base_path", "")
        view = _dotted_value(obj, base_path) if base_path else obj
        if view is None:
            raise ValueError(f"Missing receipt view {base_path!r} in {rel}")
        fields = {name: _extract_value(view, expr) for name, expr in spec.get("fields", {}).items()}
        fields.update({
            "layer": spec.get("layer", "total"),
            "source_path": rel,
            "role": spec.get("role", "receipt"),
        })
        components.append(fields)
    for spec in record_spec.get("evidence_files", []):
        rel = spec["path"]
        key = (rel, spec.get("role", "evidence"))
        if key not in seen_fingerprints:
            fingerprints.append(_fingerprint(repo_root, rel, spec.get("role", "evidence")))
            seen_fingerprints.add(key)
    return components, fingerprints


def _local_run_group(repo_root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Aggregate only explicitly matched run_manifest.json and cost_ledger.json files."""
    manifest_paths = sorted(repo_root.glob(spec["run_manifest_glob"]))
    ledger_paths = sorted(repo_root.glob(spec["cost_ledger_glob"]))
    exclude_suffixes = tuple(spec.get("exclude_parent_suffixes", ["-engineering"]))
    manifest_paths = [p for p in manifest_paths if not p.parent.name.endswith(exclude_suffixes)]
    ledger_paths = [p for p in ledger_paths if not p.parent.name.endswith(exclude_suffixes)]
    min_run_manifests = int(spec.get("minimum_run_manifests", 0))
    if len(manifest_paths) < min_run_manifests:
        raise ValueError(
            f"Expected at least {min_run_manifests} run manifests for {spec.get('id', 'group')}, "
            f"found {len(manifest_paths)}"
        )

    manifests: list[dict[str, Any]] = []
    ledgers: list[dict[str, Any]] = []
    fingerprints: list[dict[str, Any]] = []
    for paths, target, role in (
        (manifest_paths, manifests, "local_run_manifest"),
        (ledger_paths, ledgers, "token_usage_ledger"),
    ):
        for path in paths:
            rel = path.resolve().relative_to(repo_root.resolve()).as_posix()
            data = _read_metadata_json(repo_root, rel)
            if not isinstance(data, dict):
                raise ValueError(f"Expected metadata object: {rel}")
            target.append(data)
            fingerprints.append(_fingerprint(repo_root, rel, role))

    starts = [m.get("started_at_utc") for m in manifests if m.get("started_at_utc")]
    finishes = [m.get("finished_at_utc") for m in manifests if m.get("finished_at_utc")]
    elapsed_span_seconds = None
    if starts and finishes:
        start = datetime.fromisoformat(min(starts).replace("Z", "+00:00"))
        finish = datetime.fromisoformat(max(finishes).replace("Z", "+00:00"))
        elapsed_span_seconds = max(0.0, (finish - start).total_seconds())

    statuses: dict[str, int] = {}
    for manifest in manifests:
        status = str(manifest.get("status", "unknown"))
        statuses[status] = statuses.get(status, 0) + 1
    new_api_calls = sum(int(m.get("new_api_calls") or 0) for m in manifests)
    token_cost = sum(float(x.get("estimated_cost_usd") or 0.0) for x in ledgers)
    unknown_reserve = sum(float(x.get("reserved_cost_usd") or 0.0) for x in ledgers)
    prompt_tokens = sum(int(x.get("total_prompt_tokens") or 0) for x in ledgers)
    completion_tokens = sum(int(x.get("total_completion_tokens") or 0) for x in ledgers)
    ledger_calls = sum(int(x.get("call_count") or 0) for x in ledgers)
    return {
        "run_count": len(manifests),
        "cost_ledger_count": len(ledgers),
        "run_status_counts": statuses,
        "main_physical_requests": new_api_calls,
        "repair_physical_requests": 0,
        "token_usage_estimate_usd": token_cost,
        "unknown_fee_reserve_usd": unknown_reserve,
        "api_reported_cost_usd": None,
        "ledger_call_count": ledger_calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "duration_seconds": elapsed_span_seconds,
        "wall_seconds_sum": sum(float(m.get("wall_seconds") or 0.0) for m in manifests),
        "fingerprints": fingerprints,
    }


def _sum_non_null(components: Iterable[dict[str, Any]], key: str) -> float | None:
    values = [float(component[key]) for component in components if component.get(key) is not None]
    return sum(values) if values else None


def _materialize_record(repo_root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    record = dict(spec.get("record", {}))
    components, fingerprints = _receipt_components(repo_root, spec)
    run_group = None
    if spec.get("local_run_group"):
        run_group = _local_run_group(repo_root, spec["local_run_group"])
        fingerprints.extend(run_group.pop("fingerprints"))

    # Physical requests are summed from disjoint main/repair layers. Cumulative
    # cost-only layers intentionally carry no request count, preventing wrapper
    # receipts and nested totals from being counted a second time.
    main_requests = sum(int(c.get("physical_requests") or 0) for c in components if c.get("layer") == "main")
    repair_requests = sum(int(c.get("physical_requests") or 0) for c in components if c.get("layer") == "repair")
    snapshot_physical_values = [
        int(c["physical_requests"])
        for c in components
        if c.get("layer") == "snapshot" and c.get("physical_requests") is not None
    ]
    snapshot_requests = sum(snapshot_physical_values) if snapshot_physical_values else None
    if run_group:
        main_requests = int(run_group["main_physical_requests"])
        repair_requests = int(run_group["repair_physical_requests"])

    direct_reported = _sum_non_null(components, "reported_api_cost_usd")
    direct_unknown = _sum_non_null(components, "unknown_fee_reserve_usd")
    direct_token_estimate = _sum_non_null(components, "token_usage_estimate_usd")
    combined_unseparated = _sum_non_null(components, "combined_cost_unseparated_usd")
    duration_values = [float(c["duration_seconds"]) for c in components if c.get("duration_seconds") is not None]
    duration = sum(duration_values) if duration_values else None
    usable = _sum_non_null(components, "usable_responses")
    unresolved = _sum_non_null(components, "unresolved_responses")
    main_usable = _sum_non_null(components, "main_usable_responses")
    repair_usable = _sum_non_null(components, "repair_usable_responses")
    historical_source_cost = _sum_non_null(components, "historical_source_reported_cost_usd")
    evaluation_new_api_calls = _sum_non_null(components, "evaluation_new_api_calls")
    evaluation_person_months = _sum_non_null(components, "evaluation_person_months")
    final_counts = (
        "final_q8_updated",
        "final_q9_updated",
        "final_both_fields_updated",
        "final_q9_initial_fallback_needed",
    )

    for fee_spec in spec.get("derived_reserve_sources", []):
        rel = fee_spec["path"]
        role = fee_spec.get("role", "cumulative_cost_source")
        fingerprints.append(_fingerprint(repo_root, rel, role))
        data = _read_metadata_json(repo_root, rel)
        spent_or_reserved = _extract_value(data, fee_spec["spent_or_reserved_field"])
        if spent_or_reserved is not None and direct_reported is not None:
            derived_reserve = float(spent_or_reserved) - direct_reported
            direct_unknown = (direct_unknown or 0.0) + derived_reserve

    if run_group:
        direct_reported = run_group["api_reported_cost_usd"]
        direct_unknown = run_group["unknown_fee_reserve_usd"]
        direct_token_estimate = run_group["token_usage_estimate_usd"]
        duration = run_group["duration_seconds"]
        record["run_count"] = run_group["run_count"]
        record["cost_ledger_count"] = run_group["cost_ledger_count"]
        record["run_status_counts"] = run_group["run_status_counts"]
        record["ledger_call_count"] = run_group["ledger_call_count"]
        record["prompt_tokens"] = run_group["prompt_tokens"]
        record["completion_tokens"] = run_group["completion_tokens"]
        record["wall_seconds_sum"] = run_group["wall_seconds_sum"]

    if "main_physical_requests" in record and main_requests == 0 and not record.get("snapshot_only"):
        # Registry can state main counts from a report when individual execution
        # receipts were not retained; these values remain source-cited.
        main_requests = int(record["main_physical_requests"] or 0)
    if "repair_physical_requests" in record and repair_requests == 0:
        repair_requests = int(record["repair_physical_requests"] or 0)
    if "duration_seconds" in record and duration is None:
        duration = record["duration_seconds"]

    if record.get("snapshot_only"):
        main_requests = record.get("main_physical_requests")
        repair_requests = record.get("repair_physical_requests")
    record["main_physical_requests"] = main_requests
    record["repair_physical_requests"] = repair_requests
    record["physical_requests_total"] = None if record.get("snapshot_only") else main_requests + repair_requests
    record["snapshot_physical_requests"] = snapshot_requests
    record["reported_api_cost_usd"] = direct_reported if direct_reported is not None else record.get("reported_api_cost_usd")
    record["unknown_fee_reserve_usd"] = direct_unknown if direct_unknown is not None else record.get("unknown_fee_reserve_usd")
    record["token_usage_estimate_usd"] = direct_token_estimate if direct_token_estimate is not None else record.get("token_usage_estimate_usd")
    record["combined_cost_unseparated_usd"] = combined_unseparated if combined_unseparated is not None else record.get("combined_cost_unseparated_usd")
    record["duration_seconds"] = duration
    for field_name, value in (
        ("main_usable_responses", main_usable),
        ("repair_usable_responses", repair_usable),
        ("historical_source_reported_cost_usd", historical_source_cost),
        ("evaluation_new_api_calls", evaluation_new_api_calls),
        ("evaluation_person_months", evaluation_person_months),
    ):
        if value is not None:
            record[field_name] = int(value) if field_name.endswith("responses") or field_name.endswith("calls") or field_name.endswith("months") else value
    for field_name in final_counts:
        value = _sum_non_null(components, field_name)
        if value is not None:
            record[field_name] = int(value)
    evaluation_statuses = [c.get("evaluation_status") for c in components if c.get("evaluation_status") is not None]
    if evaluation_statuses:
        record["evaluation_status"] = evaluation_statuses[-1]
    snapshot_times = [c.get("snapshot_as_of_utc") for c in components if c.get("snapshot_as_of_utc")]
    if snapshot_times:
        record["snapshot_as_of_utc"] = max(snapshot_times)
    for field_name in ("snapshot_logical_attempts", "snapshot_completed_returns", "snapshot_in_flight"):
        snapshot_values = [
            float(c[field_name])
            for c in components
            if c.get("layer") == "snapshot" and c.get(field_name) is not None
        ]
        if snapshot_values:
            total = sum(snapshot_values)
            record[field_name] = int(total) if total.is_integer() else total
    if usable is not None:
        record["usable_responses"] = int(usable)
    if unresolved is not None:
        record["unresolved_responses"] = int(unresolved)
    record["receipt_components"] = components
    record["source_fingerprints"] = sorted(fingerprints, key=lambda item: (item.get("path", ""), item.get("role", "")))
    record["included_in_cost_subtotal"] = bool(record.get("included_in_cost_subtotal", False))
    record["charge_group"] = record.get("charge_group") or record["experiment_id"]
    return record


def aggregate_costs(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum disjoint charge groups once and keep accounting types separate."""
    used_groups: set[str] = set()
    included: list[dict[str, Any]] = []
    duplicate_groups: list[str] = []
    for record in records:
        if not record.get("included_in_cost_subtotal") or record.get("snapshot_only"):
            continue
        group = str(record.get("charge_group", record["experiment_id"]))
        if group in used_groups:
            duplicate_groups.append(group)
            continue
        used_groups.add(group)
        included.append(record)
    unseparated_by_group: dict[str, float] = {}
    for record in records:
        if record.get("snapshot_only") or record.get("combined_cost_unseparated_usd") is None:
            continue
        group = str(record.get("charge_group", record["experiment_id"]))
        unseparated_by_group.setdefault(group, float(record["combined_cost_unseparated_usd"]))
    return {
        "reported_api_cost_usd": sum(float(r["reported_api_cost_usd"]) for r in included if r.get("reported_api_cost_usd") is not None),
        "unknown_fee_reserve_usd": sum(float(r["unknown_fee_reserve_usd"]) for r in included if r.get("unknown_fee_reserve_usd") is not None),
        "token_usage_estimate_usd": sum(float(r["token_usage_estimate_usd"]) for r in included if r.get("token_usage_estimate_usd") is not None),
        "combined_cost_unseparated_usd": sum(unseparated_by_group.values()),
        "unseparated_charge_group_count": len(unseparated_by_group),
        "included_record_count": len(included),
        "charge_group_count": len(used_groups),
        "duplicate_charge_groups_ignored": sorted(set(duplicate_groups)),
        "complete_project_cost_total": False,
    }


def public_projection(registry: dict[str, Any]) -> dict[str, Any]:
    public_records = []
    for record in registry["records"]:
        public_records.append({key: record.get(key) for key in PUBLIC_RECORD_FIELDS if key in record})
    coverage = {
        key: registry["coverage"].get(key)
        for key in ("scope", "complete_project_cost_total", "omissions", "cost_interpretation")
        if key in registry["coverage"]
    }
    summary = registry["cost_summary_usd"]
    public_cost_summary = {
        key: summary.get(key)
        for key in (
            "reported_api_cost_usd",
            "unknown_fee_reserve_usd",
            "token_usage_estimate_usd",
            "combined_cost_unseparated_usd",
            "included_record_count",
            "unseparated_charge_group_count",
            "complete_project_cost_total",
        )
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": registry["generated_at_utc"],
        "coverage": coverage,
        "selected_records_cost_summary_usd": public_cost_summary,
        "counting_rules": registry["counting_rules"],
        "records": public_records,
    }


def build_registry(repo_root: Path, source_registry_path: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    spec = json.loads(source_registry_path.read_text(encoding="utf-8"))
    records = [_materialize_record(repo_root, item) for item in spec.get("records", [])]
    ids = [record.get("experiment_id") for record in records]
    if None in ids or len(ids) != len(set(ids)):
        raise ValueError("Experiment ids must be present and unique")
    registry = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "coverage": spec.get("coverage", {}),
        "counting_rules": spec.get("counting_rules", {}),
        "records": records,
    }
    try:
        source_ref = source_registry_path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        source_ref = None
    registry["source_registry_fingerprint"] = {
        "path": source_ref,
        "size_bytes": source_registry_path.stat().st_size,
        "sha256": _sha256(source_registry_path),
    }
    registry["cost_summary_usd"] = aggregate_costs(records)
    return registry


def write_registry(registry: dict[str, Any], output_dir: Path, *, overwrite: bool = False) -> None:
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"Refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    private_json = output_dir / "experiment_registry_private.json"
    private_csv = output_dir / "experiment_registry_private.csv"
    public_json = output_dir / "experiment_registry_public.json"
    public_csv = output_dir / "experiment_registry_public.csv"
    readme = output_dir / "README.md"
    private_json.write_text(json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with private_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PRIVATE_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for record in registry["records"]:
            row = {key: record.get(key) for key in PRIVATE_CSV_FIELDS}
            for key in ("failure_summary", "repair_summary", "notes", "seed_summary", "cost_coverage_note"):
                if isinstance(row.get(key), (dict, list)):
                    row[key] = json.dumps(row[key], ensure_ascii=False, sort_keys=True)
            row["source_fingerprints_json"] = json.dumps(record.get("source_fingerprints", []), ensure_ascii=False, sort_keys=True)
            row["receipt_components_json"] = json.dumps(record.get("receipt_components", []), ensure_ascii=False, sort_keys=True)
            writer.writerow(row)
    public_json.write_text(json.dumps(public_projection(registry), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    public_records = public_projection(registry)["records"]
    with public_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PUBLIC_RECORD_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for record in public_records:
            writer.writerow({
                key: json.dumps(record.get(key), ensure_ascii=False, sort_keys=True)
                if isinstance(record.get(key), (dict, list)) else record.get(key)
                for key in PUBLIC_RECORD_FIELDS
            })

    costs = registry["cost_summary_usd"]
    full_a_record = next(
        (record for record in registry["records"] if record.get("experiment_id") == "full_a_t0_20261026"),
        None,
    )
    full_a_note = (
        "- Full A T0 generation is included once using the canonical main and repair receipts; "
        "its independent evaluation status is recorded separately."
        if full_a_record and not full_a_record.get("snapshot_only")
        else "- In-progress A T0 appears as a timestamped snapshot and is excluded from those subtotals."
    )
    readme.write_text(
        "\n".join(
            [
                "# Experiment log index",
                "",
                f"Generated: {registry['generated_at_utc']}",
                "",
                str(registry["coverage"].get("scope", "Selected experiment records.")),
                "",
                "This is a selected-record index, not a complete project-cost total.",
                "",
                "- API-reported spend: ${:,.6f}".format(costs["reported_api_cost_usd"]),
                "- Unknown-fee reserve: ${:,.6f}".format(costs["unknown_fee_reserve_usd"]),
                "- Token-usage estimate: ${:,.6f} (not an invoice)".format(costs["token_usage_estimate_usd"]),
                "- Charged-or-reserved amount that could not be split: ${:,.6f} (not added to the other fields)".format(costs["combined_cost_unseparated_usd"]),
                full_a_note,
                "",
                "Public JSON and CSV contain only the registry field whitelist. The private JSON/CSV retain repository-relative receipt paths and file hashes; no raw reply or private call ledger is read.",
                "",
                "Rebuild from the repository root with `python scripts/build_sce_submission_experiment_logs.py --out outputs/<new_run_id>`.",
                "",
            ]
        ),
        encoding="utf-8",
    )


__all__ = ["aggregate_costs", "build_registry", "public_projection", "write_registry"]
