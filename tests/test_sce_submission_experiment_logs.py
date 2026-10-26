"""Offline checks for cost separation, receipt layering, deduplication, and snapshots."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "studies" / "sce_inflation_expectations" / "submission_tools"
sys.path.insert(0, str(MODULES))

from experiment_logs import aggregate_costs, build_registry, public_projection  # noqa: E402


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _source_registry(tmp_path: Path, records: list[dict]) -> Path:
    path = tmp_path / "submission" / "sources.json"
    _write_json(
        path,
        {
            "coverage": {"scope": "test", "complete_project_cost_total": False},
            "counting_rules": {"reported": "reported", "reserve": "separate"},
            "records": records,
        },
    )
    return path


def test_duplicate_charge_group_is_counted_once() -> None:
    rows = [
        {
            "experiment_id": "canonical",
            "charge_group": "run-1",
            "included_in_cost_subtotal": True,
            "reported_api_cost_usd": 2.0,
            "unknown_fee_reserve_usd": 0.4,
            "token_usage_estimate_usd": None,
        },
        {
            "experiment_id": "wrapper",
            "charge_group": "run-1",
            "included_in_cost_subtotal": True,
            "reported_api_cost_usd": 2.0,
            "unknown_fee_reserve_usd": 0.4,
            "token_usage_estimate_usd": None,
        },
    ]
    summary = aggregate_costs(rows)
    assert summary["reported_api_cost_usd"] == 2.0
    assert summary["unknown_fee_reserve_usd"] == 0.4
    assert summary["included_record_count"] == 1
    assert summary["duplicate_charge_groups_ignored"] == ["run-1"]


def test_api_report_reserve_token_estimate_and_unseparated_amount_stay_distinct() -> None:
    summary = aggregate_costs(
        [
            {
                "experiment_id": "main",
                "charge_group": "main",
                "included_in_cost_subtotal": True,
                "reported_api_cost_usd": 3.0,
                "unknown_fee_reserve_usd": 0.25,
                "token_usage_estimate_usd": 0.0,
                "combined_cost_unseparated_usd": 0.0,
            },
            {
                "experiment_id": "token-ledger",
                "charge_group": "token-ledger",
                "included_in_cost_subtotal": True,
                "reported_api_cost_usd": None,
                "unknown_fee_reserve_usd": 0.0,
                "token_usage_estimate_usd": 1.75,
                "combined_cost_unseparated_usd": None,
            },
            {
                "experiment_id": "combined-only",
                "charge_group": "combined-only",
                "included_in_cost_subtotal": False,
                "reported_api_cost_usd": None,
                "unknown_fee_reserve_usd": None,
                "token_usage_estimate_usd": None,
                "combined_cost_unseparated_usd": 0.05,
            },
        ]
    )
    assert summary["reported_api_cost_usd"] == 3.0
    assert summary["unknown_fee_reserve_usd"] == 0.25
    assert summary["token_usage_estimate_usd"] == 1.75
    assert summary["combined_cost_unseparated_usd"] == 0.05
    assert summary["included_record_count"] == 2
    assert summary["complete_project_cost_total"] is False


def test_nested_main_and_repair_receipt_sums_each_layer_once(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    receipt = {
        "main": {
            "attempts": 10,
            "reported_cost_usd": 2.0,
            "unknown_fee_reservation_usd": 0.3,
            "usable": 9,
            "unresolved": 1,
        },
        "repair": {
            "attempts": 1,
            "reported_cost_usd": 0.2,
            "unknown_fee_reservation_usd": 0.0,
            "usable": 1,
            "unresolved": 0,
        },
    }
    _write_json(repo / "outputs/run/generation_receipt.json", receipt)
    source_registry = _source_registry(
        repo,
        [
            {
                "record": {
                    "experiment_id": "nested-run",
                    "title": "nested",
                    "status": "completed",
                    "included_in_cost_subtotal": True,
                    "charge_group": "nested-run",
                },
                "receipt_components": [
                    {
                        "path": "outputs/run/generation_receipt.json",
                        "base_path": "main",
                        "layer": "main",
                        "fields": {
                            "physical_requests": "attempts",
                            "reported_api_cost_usd": "reported_cost_usd",
                            "unknown_fee_reserve_usd": "unknown_fee_reservation_usd",
                            "usable_responses": "usable",
                            "unresolved_responses": "unresolved",
                        },
                    },
                    {
                        "path": "outputs/run/generation_receipt.json",
                        "base_path": "repair",
                        "layer": "repair",
                        "fields": {
                            "physical_requests": "attempts",
                            "reported_api_cost_usd": "reported_cost_usd",
                            "unknown_fee_reserve_usd": "unknown_fee_reservation_usd",
                            "usable_responses": "usable",
                            "unresolved_responses": "unresolved",
                        },
                    },
                ],
            }
        ],
    )

    registry = build_registry(repo, source_registry)
    row = registry["records"][0]
    assert row["main_physical_requests"] == 10
    assert row["repair_physical_requests"] == 1
    assert row["physical_requests_total"] == 11
    assert row["reported_api_cost_usd"] == 2.2
    assert row["unknown_fee_reserve_usd"] == 0.3
    assert row["usable_responses"] == 10
    assert row["unresolved_responses"] == 1


def test_in_progress_snapshot_is_visible_but_excluded_from_totals(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_json(
        repo / "outputs/live/progress.json",
        {
            "at_utc": "2026-10-25T16:24:16Z",
            "main_attempts": 23,
            "main_completed": 20,
            "in_flight": 3,
            "total_reported_cost_usd": 4.0,
            "unknown_fee_reservation_usd": 0.6,
        },
    )
    source_registry = _source_registry(
        repo,
        [
            {
                "record": {
                    "experiment_id": "live-snapshot",
                    "title": "snapshot",
                    "status": "running_snapshot",
                    "snapshot_only": True,
                    "included_in_cost_subtotal": False,
                    "charge_group": "live",
                    "main_physical_requests": None,
                    "repair_physical_requests": None,
                    "snapshot_physical_requests": None,
                    "historical_reuse_slots": None,
                    "planned_historical_reuse_slots": 182,
                },
                "receipt_components": [
                    {
                        "path": "outputs/live/progress.json",
                        "layer": "snapshot",
                        "fields": {
                            "reported_api_cost_usd": "total_reported_cost_usd",
                            "unknown_fee_reserve_usd": "unknown_fee_reservation_usd",
                            "snapshot_logical_attempts": "main_attempts",
                            "snapshot_completed_returns": "main_completed",
                            "snapshot_in_flight": "in_flight",
                            "snapshot_as_of_utc": "at_utc",
                        },
                    }
                ],
            }
        ],
    )
    registry = build_registry(repo, source_registry)
    row = registry["records"][0]
    assert row["snapshot_only"] is True
    assert row["snapshot_logical_attempts"] == 23
    assert row["snapshot_completed_returns"] == 20
    assert row["snapshot_in_flight"] == 3
    assert row["main_physical_requests"] is None
    assert row["repair_physical_requests"] is None
    assert row["snapshot_physical_requests"] is None
    assert row["physical_requests_total"] is None
    assert row.get("usable_responses") is None
    assert row["historical_reuse_slots"] is None
    assert row["planned_historical_reuse_slots"] == 182
    assert row["reported_api_cost_usd"] == 4.0
    assert row["unknown_fee_reserve_usd"] == 0.6
    assert row["snapshot_as_of_utc"] == "2026-10-25T16:24:16Z"
    assert registry["cost_summary_usd"]["reported_api_cost_usd"] == 0
    assert registry["cost_summary_usd"]["unknown_fee_reserve_usd"] == 0


def test_public_projection_uses_whitelist_and_drops_local_sources(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_json(repo / "outputs/r/receipt.json", {"reported": 1.0})
    source_registry = _source_registry(
        repo,
        [
            {
                "record": {
                    "experiment_id": "public-row",
                    "title": "safe summary",
                    "status": "completed",
                    "model": "model-x",
                    "notes": "private notes",
                    "charge_group": "private-group",
                    "included_in_cost_subtotal": True,
                },
                "receipt_components": [
                    {
                        "path": "outputs/r/receipt.json",
                        "layer": "main",
                        "fields": {"physical_requests": "missing", "reported_api_cost_usd": "reported"},
                    }
                ],
            }
        ],
    )
    public = public_projection(build_registry(repo, source_registry))
    row = public["records"][0]
    assert row["experiment_id"] == "public-row"
    assert "notes" not in row
    assert "charge_group" not in row
    assert "source_fingerprints" not in row
    assert "receipt_components" not in row


def test_full_a_completed_generation_excludes_historical_import_cost_and_uses_overlay_counts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    generation = {
        "main": {
            "attempts": 41970,
            "new_api_calls": 41788,
            "historical_import_rows": 182,
            "historical_source_reported_cost_usd": 0.122813158,
            "reported_cost_usd": 32.914646577,
            "unknown_fee_reservation_usd": 0.904153418,
            "usable": 41729,
            "unresolved": 0,
        },
        "repair": {
            "attempts": 241,
            "reported_cost_usd": 0.145562965,
            "unknown_fee_reservation_usd": 0.0,
            "usable": 240,
            "unresolved": 0,
        },
    }
    overlay = {
        "counters": {
            "q8_updated": 41970,
            "q9_updated": 41969,
            "both_fields_updated": 41969,
            "q9_initial_fallback_needed": 1,
        }
    }
    _write_json(repo / "outputs/full-a/generation_receipt.json", generation)
    _write_json(repo / "outputs/full-a/overlay_receipt.json", overlay)
    _write_json(
        repo / "outputs/full-a-evaluation/manifest.json",
        {"new_api_calls": 0, "files_sha256": {"summary.json": "f" * 64}},
    )
    source_registry = _source_registry(
        repo,
        [
            {
                "record": {
                    "experiment_id": "full-a",
                    "title": "Full A T0",
                    "status": "completed",
                    "snapshot_only": False,
                    "historical_reuse_slots": 182,
                    "included_in_cost_subtotal": True,
                    "charge_group": "full-a",
                    "evaluation_status": "completed_full_a_personal_evaluation",
                    "evaluation_person_months": 41970,
                    "evaluation_new_q9_density_fits": 9262,
                    "evaluation_q9_density_fit_fallbacks": 13,
                    "evaluation_q9_retained_input_count": 1,
                    "evaluation_q8_complete": True,
                },
                "receipt_components": [
                    {
                        "path": "outputs/full-a/generation_receipt.json",
                        "base_path": "main",
                        "layer": "main",
                        "fields": {
                            "physical_requests": "new_api_calls",
                            "main_usable_responses": "usable",
                            "reported_api_cost_usd": "reported_cost_usd",
                            "unknown_fee_reserve_usd": "unknown_fee_reservation_usd",
                            "historical_source_reported_cost_usd": "historical_source_reported_cost_usd",
                            "unresolved_responses": "unresolved",
                        },
                    },
                    {
                        "path": "outputs/full-a/generation_receipt.json",
                        "base_path": "repair",
                        "layer": "repair",
                        "fields": {
                            "physical_requests": "attempts",
                            "repair_usable_responses": "usable",
                            "reported_api_cost_usd": "reported_cost_usd",
                            "unknown_fee_reserve_usd": "unknown_fee_reservation_usd",
                            "unresolved_responses": "unresolved",
                        },
                    },
                    {
                        "path": "outputs/full-a/overlay_receipt.json",
                        "layer": "overlay",
                        "fields": {
                            "usable_responses": "counters.both_fields_updated",
                            "final_q8_updated": "counters.q8_updated",
                            "final_q9_updated": "counters.q9_updated",
                            "final_both_fields_updated": "counters.both_fields_updated",
                            "final_q9_initial_fallback_needed": "counters.q9_initial_fallback_needed",
                        },
                    },
                    {
                        "path": "outputs/full-a-evaluation/manifest.json",
                        "layer": "evaluation_manifest",
                        "fields": {
                            "evaluation_new_api_calls": "new_api_calls",
                        },
                    },
                ],
            }
        ],
    )

    registry = build_registry(repo, source_registry)
    row = registry["records"][0]
    assert row["status"] == "completed"
    assert row["main_physical_requests"] == 41788
    assert row["repair_physical_requests"] == 241
    assert row["physical_requests_total"] == 42029
    assert row["main_usable_responses"] == 41729
    assert row["repair_usable_responses"] == 240
    assert row["usable_responses"] == 41969
    assert row["final_q8_updated"] == 41970
    assert row["final_q9_updated"] == 41969
    assert row["final_both_fields_updated"] == 41969
    assert row["final_q9_initial_fallback_needed"] == 1
    assert row["historical_source_reported_cost_usd"] == 0.122813158
    assert row["evaluation_status"] == "completed_full_a_personal_evaluation"
    assert row["evaluation_new_api_calls"] == 0
    assert row["evaluation_person_months"] == 41970
    assert row["evaluation_new_q9_density_fits"] == 9262
    assert row["evaluation_q9_density_fit_fallbacks"] == 13
    assert row["evaluation_q9_retained_input_count"] == 1
    assert row["evaluation_q8_complete"] is True
    assert abs(row["reported_api_cost_usd"] - 33.060209542) < 1e-12
    assert abs(row["unknown_fee_reserve_usd"] - 0.904153418) < 1e-12
    assert abs(registry["cost_summary_usd"]["reported_api_cost_usd"] - 33.060209542) < 1e-12

