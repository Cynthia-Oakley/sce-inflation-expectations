"""Offline check whether recent-B base labels resolve A82 October gaps."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

from studies.sce_inflation_expectations.experiments.frozen_batch import ROOT, sha
from studies.sce_inflation_expectations.experiments.media_mechanism_v3_preparation import (
    apply_label_overrides,
    load_supplemental_run,
)
from studies.sce_inflation_expectations.news_label_compat import normalize_label
from studies.sce_inflation_expectations.news_mechanism_label_preparation import (
    prepare_public_articles,
)
from studies.sce_inflation_expectations.news_mechanism_labels import (
    DECISIONS,
    PERSISTENCE,
    PUBLIC_FIELDS,
    SCOPES,
    TONES,
    TOPICS,
)


A_INVENTORY = Path("outputs/sce_a_personal_time_labels_full_inventory_20261025_v1")
B_NEWS_INPUT = Path("outputs/sce_recent_b_news_gap_20261025_v1/news_manifest.jsonl")
B_LABEL_RUN = Path("outputs/sce_news_labels_recent_b_20261025_v1")
OLD_TONE_LABELS = Path("outputs/sce_news_mechanism_labels_20261025_v1")
OLD_TONE_REVIEW = Path("outputs/sce_news_mechanism_label_audit_20261025_v1/review.json")
CURRENT_TONE_LABELS = Path("outputs/sce_media_timing_supplemental_labels_20261025_v1")


def read_json(path: Path):
    return json.loads(Path(path).read_text())


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_json(path: Path, value) -> None:
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def public_record(row: dict) -> dict:
    return {field: row.get(field) or "" for field in PUBLIC_FIELDS}


def verify(out: Path, root: Path = ROOT) -> dict:
    root = Path(root).resolve()
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(root / "outputs"):
        raise ValueError("choose a fresh output directory under outputs/")

    a_dir = root / A_INVENTORY
    gaps_doc = read_json(a_dir / "base_topic_label_gaps.json")
    gaps = gaps_doc["articles"]
    gap_by_id = {row["article_id"]: row for row in gaps}
    if len(gap_by_id) != len(gaps) or len(gaps) != 95:
        raise ValueError("expected the 95 unique October A base-topic gaps")

    b_input_path = root / B_NEWS_INPUT
    b_manifest = read_jsonl(b_input_path)
    protocol_path = root / B_LABEL_RUN / "protocol.json"
    protocol = read_json(protocol_path)
    authorization = read_json(root / B_LABEL_RUN / "authorization.json")
    labels_path = root / B_LABEL_RUN / "labels.jsonl"
    label_rows = read_jsonl(labels_path)
    errors_path = root / B_LABEL_RUN / "errors.jsonl"
    calls_path = root / B_LABEL_RUN / "calls.jsonl"
    call_log_path = root / B_LABEL_RUN / "calls_log.jsonl"
    errors = read_jsonl(errors_path)
    calls = read_jsonl(calls_path)
    call_log = read_jsonl(call_log_path)

    if sha(b_input_path) != protocol.get("manifest_sha256"):
        raise ValueError("recent-B label input manifest hash differs from pinned protocol")
    if sha(protocol_path) != authorization.get("protocol_sha256"):
        raise ValueError("recent-B authorization does not pin the current protocol")
    manifest_ids = [row["article_id"] for row in b_manifest]
    if len(manifest_ids) != len(set(manifest_ids)) or len(manifest_ids) != protocol.get("article_count"):
        raise ValueError("recent-B public input manifest count or IDs are inconsistent")
    if protocol.get("request_count") != len(calls) or len(calls) != len(call_log):
        raise ValueError("recent-B call ledgers do not match the pinned request count")
    if errors:
        raise ValueError("recent-B label run contains errors; do not reuse incomplete labels")

    normalized_by_id = {}
    groups = Counter()
    for row in label_rows:
        normalized = normalize_label(row["label"])
        aid = normalized["article_id"]
        if aid in normalized_by_id:
            raise ValueError("duplicate recent-B article label")
        if (normalized["decision"] not in DECISIONS
                or normalized["scope"] not in SCOPES
                or not isinstance(normalized["topics"], list)
                or any(topic not in TOPICS for topic in normalized["topics"])):
            raise ValueError("recent-B label fails base-label enum validation")
        if normalized["tone"] is not None or normalized["persistence"] is not None:
            raise ValueError("recent-B base labels unexpectedly contain mechanism tags")
        normalized_by_id[aid] = normalized
        groups[row.get("group", "")] += 1
    if set(normalized_by_id) != set(manifest_ids):
        raise ValueError("recent-B labels do not cover the complete 111-ID input manifest")
    if protocol.get("article_count") != 111 or len(label_rows) != 111 or groups != {"full": 111}:
        raise ValueError("unexpected recent-B label run size or group")

    gaps_ids = set(gap_by_id)
    missing_ids = gaps_ids - set(normalized_by_id)
    if missing_ids:
        raise ValueError(f"{len(missing_ids)} A gap IDs are absent from recent-B labels")

    manifest_by_id = {row["article_id"]: row for row in b_manifest}
    public_field_mismatches = []
    for aid, gap in gap_by_id.items():
        source = manifest_by_id[aid]
        if any((gap.get(field) or "") != (source.get(field) or "")
               for field in ("headline", "abstract", "snippet", "section_name", "news_desk")):
            public_field_mismatches.append(aid)
    if public_field_mismatches:
        raise ValueError("A base-gap metadata differs from its recent-B public input")

    decisions = Counter(normalized_by_id[aid]["decision"] for aid in gaps_ids)
    if set(decisions) - DECISIONS:
        raise ValueError("unexpected decision label among recovered gaps")
    recovered_keep_ids = {aid for aid in gaps_ids if normalized_by_id[aid]["decision"] == "keep"}
    recovered_nonkeep_ids = gaps_ids - recovered_keep_ids

    a_summary = read_json(a_dir / "summary.json")
    a_keep_queue_dir = root / a_dir / "known_keep_public_label_queue"
    old_missing = read_json(a_keep_queue_dir / "pending_public_articles.json")
    old_missing_by_id = {row["article_id"]: public_record(row) for row in old_missing}
    if len(old_missing_by_id) != a_summary["known_keep_label_queue"]["unique_articles"]:
        raise ValueError("prior A known-keep tone queue differs from its summary")

    old_tags = apply_label_overrides(
        load_supplemental_run(root / OLD_TONE_LABELS),
        read_json(root / OLD_TONE_REVIEW).get("overrides", {}),
    )
    current_tags = load_supplemental_run(root / CURRENT_TONE_LABELS)
    tone_ids = set(old_tags) | set(current_tags)
    if set(old_tags) & set(current_tags) and any(
        old_tags[aid] != current_tags[aid] for aid in set(old_tags) & set(current_tags)
    ):
        raise ValueError("old and current tone/persistence ledgers conflict")

    already_in_tone_queue = gaps_ids & set(old_missing_by_id)
    already_tagged = gaps_ids & tone_ids
    incremental_tone_ids = recovered_keep_ids - set(old_missing_by_id) - tone_ids
    updated_queue = dict(old_missing_by_id)
    for aid in incremental_tone_ids:
        updated_queue[aid] = public_record(gap_by_id[aid])
    updated_records = [updated_queue[aid] for aid in sorted(updated_queue)]

    # Ensure the planned queue still contains only public fields accepted by
    # the existing classifier. No per-person or outcome columns are allowed.
    if any(set(row) != set(PUBLIC_FIELDS) for row in updated_records):
        raise ValueError("updated tone queue contains a non-public field")

    overlay_rows = []
    for aid in sorted(gaps_ids):
        label = normalized_by_id[aid]
        overlay_rows.append({
            "article_id": aid,
            "target_month": gap_by_id[aid]["months"],
            "base_label_source": str(B_LABEL_RUN / "labels.jsonl"),
            "base_label": label,
            "tone_persistence_status": "not_in_base_label; only keep IDs enter tone queue",
        })

    out.mkdir(parents=True)
    source_paths = [
        root / A_INVENTORY / "base_topic_label_gaps.json",
        root / A_INVENTORY / "summary.json",
        root / a_keep_queue_dir.relative_to(root) / "pending_public_articles.json",
        b_input_path,
        protocol_path,
        root / B_LABEL_RUN / "authorization.json",
        labels_path,
        calls_path,
        call_log_path,
        errors_path,
        root / OLD_TONE_LABELS / "state.json",
        root / OLD_TONE_LABELS / "labels.jsonl",
        root / OLD_TONE_REVIEW,
        root / CURRENT_TONE_LABELS / "state.json",
        root / CURRENT_TONE_LABELS / "labels.jsonl",
        root / "studies/sce_inflation_expectations/news_label_compat.py",
        root / "studies/sce_inflation_expectations/news_mechanism_labels.py",
        root / "studies/sce_inflation_expectations/news_mechanism_label_preparation.py",
        root / "studies/sce_inflation_expectations/experiments/media_mechanism_v3_preparation.py",
        root / "scripts/verify_sce_late2025_label_reuse.py",
    ]
    source_hashes = {
        str(path.resolve().relative_to(root)): sha(path)
        for path in sorted(set(source_paths), key=lambda p: str(p))
    }
    write_json(out / "source_inventory.json", {"source_sha256": source_hashes})
    with (out / "base_label_overlay.jsonl").open("w") as file:
        for row in overlay_rows:
            file.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")

    queue_dir = out / "updated_a_tone_label_queue"
    queue_summary = prepare_public_articles(
        updated_records,
        queue_dir,
        root,
        source_paths,
        "Public NYT headline/abstract/snippet/source/section/desk and article IDs from A82 known keep pools after reusing October 2025 base labels; no SCE microdata or answers.",
    )

    summary = {
        "schema": "sce_late2025_label_reuse_verification/v1",
        "status": "all_95_base_labels_recovered",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "new_api_calls": 0,
        "target_answers_read": False,
        "microdata_read": False,
        "source_run_verification": {
            "manifest_articles": len(b_manifest),
            "manifest_unique_ids": len(set(manifest_ids)),
            "manifest_hash_matches_protocol": sha(b_input_path) == protocol["manifest_sha256"],
            "authorization_pins_protocol": sha(protocol_path) == authorization["protocol_sha256"],
            "recent_b_labels": len(label_rows),
            "recent_b_unique_label_ids": len(normalized_by_id),
            "label_ids_equal_input_manifest": set(normalized_by_id) == set(manifest_ids),
            "calls": len(calls),
            "call_log_rows": len(call_log),
            "errors": len(errors),
            "metadata_field_mismatches_for_95": len(public_field_mismatches),
        },
        "a_base_gap_reconciliation": {
            "gap_article_ids": len(gaps_ids),
            "matched_to_recent_b_base_labels": len(gaps_ids & set(normalized_by_id)),
            "unmatched_article_ids": len(missing_ids),
            "decision_counts": dict(sorted(decisions.items())),
            "keep_recovered": len(recovered_keep_ids),
            "nonkeep_not_sent_for_tone": len(recovered_nonkeep_ids),
            "background_or_exclude_ids_do_not_receive_tone_labels": True,
            "overlap_with_prior_tone_queue": len(already_in_tone_queue),
            "overlap_with_existing_tone_persistence_labels": len(already_tagged),
        },
        "updated_a_tone_queue_candidate": {
            "prior_unique_missing_tone_articles": len(old_missing_by_id),
            "incremental_recovered_keep_ids_missing_tone": len(incremental_tone_ids),
            "unique_articles": queue_summary["unique_articles_to_label"],
            "batches": queue_summary["batches"],
            "request_reservation_no_retries_usd": queue_summary["total_usd_reservation_no_retries"],
            "proposed_budget_cap_usd": queue_summary["proposed_budget_usd"],
            "classifier_model": queue_summary["requested_model"],
            "label_mode": queue_summary["label_mode"],
            "queue_dir": str(queue_dir.resolve().relative_to(root)),
            "executed": False,
        },
        "existing_tone_label_reuse": {
            "old_reviewed_ids": len(old_tags),
            "current_completed_ids": len(current_tags),
            "current_completed_human_review_record": (root / CURRENT_TONE_LABELS / "review.json").is_file(),
            "old_current_overlap": len(set(old_tags) & set(current_tags)),
        },
        "source_sha256": source_hashes,
        "limits": [
            "The recovered labels add only base decision/topics/scope; they do not contain tone or persistence.",
            "Only the 50 recovered keep decisions add tone/persistence candidates. Background and exclude decisions are omitted.",
            "The updated queue is prepared from unique article IDs; final prompt assembly must still apply its registered exact_deduplicate step.",
            "No raw archive window was reprocessed, no old inventory or frozen output was modified, and B inputs were not changed.",
        ],
    }
    write_json(out / "summary.json", summary)

    note = f"""# 2025-10 A base-label reuse check

The 95 October A gaps match the recent-B `news_manifest.jsonl` and its completed label ledger. The manifest hash matches the pinned protocol; all 111 input IDs have exactly one normalized label, with 14 calls, 0 errors, and exact public-text field matches for all 95 overlapping IDs.

- Recovered base labels: 50 `keep`, 25 `background`, 20 `exclude`.
- Only the 50 `keep` records add tone/persistence candidates; the 45 background/exclude records are not sent for mechanism tags.
- Updated A tone candidate queue: {queue_summary['unique_articles_to_label']:,} unique IDs, {queue_summary['batches']:,} batches; reserve ${queue_summary['total_usd_reservation_no_retries']:.6f}, proposed cap ${queue_summary['proposed_budget_usd']:.6f}. Prepared only; no API call.
- Overlay file `base_label_overlay.jsonl` uses the existing `normalize_label` schema and contains base labels only.

The original A82 inventory, its script, and the recent-B label run were not modified.
"""
    (out / "REUSE_NOTE.md").write_text(note)

    manifest = {
        "schema": "sce_late2025_label_reuse_manifest/v1",
        "status": summary["status"],
        "new_api_calls": 0,
        "files_sha256": {
            str(path.relative_to(out)): sha(path)
            for path in sorted(out.rglob("*"))
            if path.is_file() and path.name != "manifest.json"
        },
    }
    write_json(out / "manifest.json", manifest)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    summary = verify(args.out)
    print(json.dumps({
        "status": summary["status"],
        "gap_ids_recovered": summary["a_base_gap_reconciliation"]["matched_to_recent_b_base_labels"],
        "keep_ids_added_to_tone_candidate": summary["a_base_gap_reconciliation"]["keep_recovered"],
        "updated_unique_tone_candidate": summary["updated_a_tone_queue_candidate"]["unique_articles"],
        "updated_batches": summary["updated_a_tone_queue_candidate"]["batches"],
        "new_api_calls": summary["new_api_calls"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
