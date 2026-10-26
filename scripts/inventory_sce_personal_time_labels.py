"""Offline upper-bound inventory for A82 personal-date news labels.

The cutoff is the day before each target month's final calendar day at
23:59:59 America/New_York. No person-level dates, survey answers, or API
clients are read or called.
"""
from __future__ import annotations

import argparse
import calendar
import csv
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

from studies.sce_inflation_expectations.experiments.frozen_batch import ROOT, sha
from studies.sce_inflation_expectations.experiments.fullperiod_materialization import (
    news_pool_for_prompts,
)
from studies.sce_inflation_expectations.experiments.media_mechanism_trial import (
    is_sce_report,
)
from studies.sce_inflation_expectations.experiments.media_mechanism_v3_preparation import (
    apply_label_overrides,
    load_supplemental_run,
)
from studies.sce_inflation_expectations.news_exposure import NEWS_KEYS
from studies.sce_inflation_expectations.news_exposure_demo import (
    exact_deduplicate,
    news_tags,
)
from studies.sce_inflation_expectations.news_label_compat import normalize_label
from studies.sce_inflation_expectations.news_mechanism_label_preparation import (
    prepare_public_articles,
)
from studies.sce_inflation_expectations.news_mechanism_labels import (
    PUBLIC_FIELDS,
    build_requests,
)
from studies.sce_inflation_expectations.news_selection_trial import RecallRules, RULE_FILE


MATERIALIZED = Path("outputs/sce_fullperiod_materialized_20261022_v2")
FULL_INVENTORY = Path("outputs/sce_supplemental_full_inventory_20261025_v1")
OLD_LABELS = Path("outputs/sce_news_mechanism_labels_20261025_v1")
OLD_REVIEW = Path("outputs/sce_news_mechanism_label_audit_20261025_v1/review.json")
CURRENT_LABELS = Path("outputs/sce_media_timing_supplemental_labels_20261025_v1")
CURRENT_INPUTS = Path("outputs/sce_media_timing_inputs_20261025_v3/supplemental_label_inputs")
NYT_ARCHIVE = Path("data/raw/nyt_archive")
NY = ZoneInfo("America/New_York")


def read_json(path: Path):
    return json.loads(Path(path).read_text())


def write_json(path: Path, value) -> None:
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def target_months() -> list[str]:
    result = []
    year, month = 2019, 1
    while (year, month) <= (2025, 10):
        result.append(f"{year:04d}-{month:02d}")
        year += month == 12
        month = 1 if month == 12 else month + 1
    if len(result) != 82:
        raise ValueError(f"expected 82 A months, found {len(result)}")
    return result


def month_int(month: str) -> int:
    return int(month.replace("-", ""))


def next_month(month: str) -> str:
    year, mon = map(int, month.split("-"))
    year += mon == 12
    mon = 1 if mon == 12 else mon + 1
    return f"{year:04d}-{mon:02d}"


def max_personal_cutoff(month: str) -> str:
    year, mon = map(int, month.split("-"))
    month_last_day = date(year, mon, calendar.monthrange(year, mon)[1])
    cutoff_day = month_last_day - timedelta(days=1)
    return datetime.combine(cutoff_day, time(23, 59, 59), NY).isoformat()


def public_fields(row: dict) -> dict:
    return {field: row.get(field) or "" for field in PUBLIC_FIELDS}


def load_mechanism_labels(root: Path) -> tuple[dict, dict]:
    old_state = read_json(root / OLD_LABELS / "state.json")
    if old_state.get("status") != "completed":
        raise ValueError("old reviewed tone/persistence labels are not complete")
    old = load_supplemental_run(root / OLD_LABELS)
    review = read_json(root / OLD_REVIEW)
    old = apply_label_overrides(old, review.get("overrides", {}))

    current_state = read_json(root / CURRENT_LABELS / "state.json")
    if current_state.get("status") != "completed":
        raise ValueError("current 594-article supplemental run is not complete")
    current = load_supplemental_run(root / CURRENT_LABELS)
    pending = read_json(root / CURRENT_INPUTS / "pending_public_articles.json")
    pending_ids = {row["article_id"] for row in pending}
    if len(pending_ids) != len(pending) or pending_ids != set(current):
        raise ValueError("current supplemental labels do not match the prepared IDs")
    if set(old) & set(current) and any(old[aid] != current[aid] for aid in set(old) & set(current)):
        raise ValueError("old and current supplemental labels conflict")
    return old | current, {
        "old_reviewed": {
            "articles": len(old),
            "audit_overrides": len(review.get("overrides", {})),
        },
        "current_completed": {
            "articles": len(current),
            "status": current_state.get("status"),
            "batches_planned": current_state.get("batches_planned"),
            "batches_attempted": current_state.get("batches_attempted"),
            "errors": current_state.get("errors"),
            "spent_or_reserved_upper_usd": current_state.get("spent_or_reserved_upper_usd"),
            "authorization_cap_usd": current_state.get("cap_usd"),
            "human_review_record": (root / CURRENT_LABELS / "review.json").is_file(),
        },
        "overlap": len(set(old) & set(current)),
    }


def merge_month_indexes(root: Path, month: str, source_hashes: dict) -> tuple[dict, int]:
    """Target index wins via setdefault; next index only fills missing IDs."""
    labels = {}
    conflicts = set()
    for label_month in (month, next_month(month)):
        path = root / MATERIALIZED / label_month.replace("-", "") / "news_label_index.json"
        source_hashes[str(path.relative_to(root))] = sha(path)
        index = read_json(path)
        if index.get("target_month") != label_month:
            raise ValueError(f"wrong target month in {path}")
        for row in index["pool"]:
            if not row.get("label"):
                continue
            normalized = normalize_label(row["label"])
            aid = row["article_id"]
            if aid in labels and labels[aid] != normalized:
                conflicts.add(aid)
            labels.setdefault(aid, normalized)
    return labels, len(conflicts)


def inventory(out: Path, root: Path = ROOT) -> dict:
    root = Path(root).resolve()
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(root / "outputs"):
        raise ValueError("choose a fresh output directory under outputs/")

    full_inventory_path = root / FULL_INVENTORY / "summary.json"
    full_inventory = read_json(full_inventory_path)
    full_pool_expected = full_inventory["pool_inventory"]["unique_keep_articles_before_sce_exclusion"]
    if full_pool_expected != 13996:
        raise ValueError("the prior 93-month inventory no longer has the expected keep-ID count")

    # This set is only for a coverage comparison against the prior 93 monthly
    # indexes. The index labels are topic/scope decisions, not mechanism tags.
    full_month_keep_ids = set()
    all_months = read_json(root / MATERIALIZED / "coverage.json")["months"]
    if len(all_months) != 93:
        raise ValueError("expected the existing 93-month A/B materialized index")
    full_index_paths = []
    for cov in all_months:
        month_path = root / MATERIALIZED / cov["target_month"].replace("-", "") / "news_label_index.json"
        full_index_paths.append(month_path)
        index = read_json(month_path)
        if index.get("target_month") != cov["target_month"] or index.get("as_of") != cov["as_of"]:
            raise ValueError("coverage/index mismatch in the 93-month reference pool")
        full_month_keep_ids.update(
            row["article_id"] for row in index["pool"]
            if row.get("label") and row["label"].get("decision") == "keep"
        )
    if len(full_month_keep_ids) != full_pool_expected:
        raise ValueError("93-month keep ID union differs from its prior inventory")

    mechanism_tags, tag_source_summary = load_mechanism_labels(root)
    rules = RecallRules(read_json(RULE_FILE))
    months = target_months()
    source_hashes = {
        str((root / MATERIALIZED / "coverage.json").relative_to(root)):
            sha(root / MATERIALIZED / "coverage.json"),
        str(RULE_FILE.resolve().relative_to(root)): sha(RULE_FILE),
        str(full_inventory_path.relative_to(root)): sha(full_inventory_path),
    }
    source_hashes.update({
        str(path.relative_to(root)): sha(path)
        for path in [
            root / OLD_LABELS / "state.json",
            root / OLD_LABELS / "labels.jsonl",
            root / OLD_REVIEW,
            root / CURRENT_LABELS / "state.json",
            root / CURRENT_LABELS / "labels.jsonl",
            root / CURRENT_INPUTS / "summary.json",
            root / CURRENT_INPUTS / "pending_public_articles.json",
            root / "studies/sce_inflation_expectations/experiments/media_timing_inputs.py",
            root / "studies/sce_inflation_expectations/experiments/media_mechanism_trial.py",
            root / "studies/sce_inflation_expectations/experiments/fullperiod_materialization.py",
            root / "studies/sce_inflation_expectations/news_exposure.py",
            root / "studies/sce_inflation_expectations/news_exposure_demo.py",
            root / "studies/sce_inflation_expectations/news_label_compat.py",
            root / "studies/sce_inflation_expectations/news_mechanism_label_preparation.py",
            root / "studies/sce_inflation_expectations/news_mechanism_labels.py",
            root / "scripts/inventory_sce_personal_time_labels.py",
        ]
    })
    source_hashes[str(RULE_FILE.resolve().relative_to(root))] = sha(RULE_FILE)

    monthly = []
    a_keep_by_id = {}
    base_gap_by_id = {}
    all_sce_ids = set()
    for month in months:
        labels, conflict_n = merge_month_indexes(root, month, source_hashes)
        cutoff = max_personal_cutoff(month)
        raw, counts, raw_hashes = news_pool_for_prompts(root, month, cutoff, rules)
        source_hashes.update(raw_hashes)
        pool = []
        public_by_id = {}
        gap_ids_this_month = set()
        sce_raw_ids = set()
        sce_keep_ids = set()
        for row in raw:
            aid = row["article_id"]
            if is_sce_report(row):
                sce_raw_ids.add(aid)
                if labels.get(aid, {}).get("decision") == "keep":
                    sce_keep_ids.add(aid)
                all_sce_ids.add(aid)
                continue
            label = labels.get(aid)
            if not label:
                if row.get("new_hits"):
                    gap_ids_this_month.add(aid)
                    public_by_id[aid] = public_fields(row)
                    entry = base_gap_by_id.setdefault(aid, {"article": public_fields(row), "months": []})
                    if month not in entry["months"]:
                        entry["months"].append(month)
                continue
            if label["decision"] != "keep":
                continue
            public_by_id[aid] = public_fields(row)
            news_row = {key: row[key] for key in NEWS_KEYS - {"routing_tags", "semantic_label"}}
            news_row.update(
                routing_tags=news_tags(row),
                semantic_label=dict(label, **mechanism_tags.get(aid, {})),
            )
            pool.append(news_row)

        deduped = exact_deduplicate(pool)
        keep_ids = {row["article_id"] for row in deduped}
        if len(keep_ids) != len(deduped):
            raise ValueError("exact_deduplicate retained duplicate article IDs")
        for row in deduped:
            aid = row["article_id"]
            record = public_fields(row)
            if aid in a_keep_by_id and a_keep_by_id[aid] != record:
                raise ValueError("A windows disagree on public metadata for an article ID")
            a_keep_by_id[aid] = record

        reusable = keep_ids & set(mechanism_tags)
        monthly.append({
            "target_month": month,
            "max_personal_cutoff": cutoff,
            "raw_unique_articles": counts.get("unique_articles", len(raw)),
            "raw_keyword_candidates": counts.get("coarse_candidates"),
            "sce_reports_excluded_raw": len(sce_raw_ids),
            "sce_reports_excluded_if_keep": len(sce_keep_ids),
            "known_keep_before_exact_dedup": len(pool),
            "known_keep_after_exact_dedup": len(deduped),
            "base_topic_label_gap_candidates": len(gap_ids_this_month),
            "existing_tone_persistence_reuse": len(reusable),
            "known_keep_missing_tone_persistence": len(keep_ids - set(mechanism_tags)),
            "target_next_index_label_conflicts_target_wins": conflict_n,
        })
        print(
            f"{month} cutoff={cutoff} raw={len(raw)} keep={len(deduped)} "
            f"base_gaps={len(gap_ids_this_month)}",
            flush=True,
        )

    a_keep_ids = set(a_keep_by_id)
    known_missing_ids = a_keep_ids - set(mechanism_tags)
    extra_beyond_93_ids = a_keep_ids - full_month_keep_ids
    base_gap_ids = set(base_gap_by_id)
    conditional_keep_ids = a_keep_ids | (base_gap_ids - set(mechanism_tags))
    conditional_missing_ids = conditional_keep_ids - set(mechanism_tags)

    known_missing_articles = [a_keep_by_id[aid] for aid in sorted(known_missing_ids)]
    known_requests = build_requests(known_missing_articles)
    known_reservation = sum(row["request_usd_reservation"] for row in known_requests)

    possible_gap_articles = [
        base_gap_by_id[aid]["article"]
        for aid in sorted(base_gap_ids - set(mechanism_tags) - known_missing_ids)
    ]
    conditional_articles = known_missing_articles + possible_gap_articles
    conditional_requests = build_requests(conditional_articles)
    conditional_reservation = sum(row["request_usd_reservation"] for row in conditional_requests)

    out.mkdir(parents=True)
    known_queue_dir = out / "known_keep_public_label_queue"
    queue_summary = prepare_public_articles(
        known_missing_articles,
        known_queue_dir,
        root,
        [root / relative for relative in source_hashes],
        "Public NYT headline/abstract/snippet/source/section/desk and article IDs only, for known keep articles in the A82 month-end-minus-one-day news windows; no household data or survey answers.",
    )

    if base_gap_by_id:
        write_json(
            out / "base_topic_label_gaps.json",
            {
                "status": "blocking_base_topic_decision_required",
                "unique_articles": len(base_gap_by_id),
                "monthly_gap_occurrences": sum(len(row["months"]) for row in base_gap_by_id.values()),
                "articles": [
                    {"article_id": aid, "months": row["months"], **row["article"]}
                    for aid, row in sorted(base_gap_by_id.items())
                ],
                "instruction": "These records were not silently removed or sent to the tone/persistence queue. Resolve the base topic/keep labels first.",
            },
        )

    if extra_beyond_93_ids:
        write_json(
            out / "articles_beyond_existing_93_month_keep_union.json",
            {
                "unique_articles": len(extra_beyond_93_ids),
                "articles": [
                    {"article_id": aid, **a_keep_by_id[aid]}
                    for aid in sorted(extra_beyond_93_ids)
                ],
            },
        )

    monthly_path = out / "monthly_inventory.csv"
    columns = list(monthly[0])
    with monthly_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(monthly)

    old_tags_count = tag_source_summary["old_reviewed"]["articles"]
    current_tags_count = tag_source_summary["current_completed"]["articles"]
    full_keep_expected = full_inventory["pool_inventory"]["unique_keep_articles_after_sce_exclusion"]
    summary = {
        "schema": "sce_a_personal_time_labels_full_inventory/v1",
        "status": "blocked_by_base_topic_label_gaps" if base_gap_by_id else "offline_inventory_complete_label_queue_prepared_no_api",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "new_api_calls": 0,
        "target_answers_read": False,
        "microdata_read": False,
        "B_inputs_changed": False,
        "cutoff_policy": {
            "target_months": [months[0], months[-1]],
            "target_month_count": len(months),
            "max_cutoff": "target month final calendar day minus one day at 23:59:59 America/New_York",
            "window_start": "previous calendar month day 1 at 00:00 America/New_York (news_pool_for_prompts convention)",
            "meaning": "Conservative per-month upper-bound candidate; actual respondent completion dates were not read or matched.",
        },
        "a_personal_window_pool": {
            "monthly_known_keep_positions_after_exact_deduplicate": sum(row["known_keep_after_exact_dedup"] for row in monthly),
            "unique_known_keep_articles_after_sce_exclusion": len(a_keep_ids),
            "unique_known_keep_articles_missing_tone_persistence": len(known_missing_ids),
            "unique_articles_with_reusable_tone_persistence": len(a_keep_ids & set(mechanism_tags)),
            "old_reviewed_reuse_in_a_pool": len(a_keep_ids & set(load_supplemental_run(root / OLD_LABELS))),
            "current_594_reuse_in_a_pool": len(a_keep_ids & set(load_supplemental_run(root / CURRENT_LABELS))),
            "unique_base_topic_label_gap_candidates": len(base_gap_ids),
            "base_topic_gap_month_occurrences": sum(len(row["months"]) for row in base_gap_by_id.values()),
            "sce_reports_excluded_unique": len(all_sce_ids),
            "unique_a_keep_articles_covered_by_93_month_keep_union": len(a_keep_ids & full_month_keep_ids),
            "unique_a_keep_articles_beyond_93_month_keep_union": len(extra_beyond_93_ids),
            "93_month_keep_union_unique_pre_sce": len(full_month_keep_ids),
            "93_month_keep_union_unique_post_sce_from_prior_inventory": full_keep_expected,
            "93_month_union_coverage_complete_for_known_a_keep": not extra_beyond_93_ids,
        },
        "reusable_label_ledgers": tag_source_summary,
        "known_keep_label_queue": {
            "unique_articles": queue_summary["unique_articles_to_label"],
            "batches": queue_summary["batches"],
            "request_reservation_no_retries_usd": queue_summary["total_usd_reservation_no_retries"],
            "proposed_budget_cap_usd": queue_summary["proposed_budget_usd"],
            "queue_dir": str(known_queue_dir.resolve().relative_to(root)),
            "new_api_calls": queue_summary["new_api_calls"],
            "complete_for_known_keep_only": True,
        },
        "conditional_upper_bound_if_every_base_gap_is_keep": {
            "additional_unique_articles_over_known_keep": len(possible_gap_articles),
            "total_unique_articles_requiring_tone_persistence": len(conditional_missing_ids),
            "batches": len(conditional_requests),
            "request_reservation_no_retries_usd": conditional_reservation,
            "proposed_budget_cap_usd": max(0.25, round(conditional_reservation * 1.25 + 0.000001, 6)),
            "condition": "Not executable until base topic/keep labels for every listed gap are resolved.",
        },
        "base_topic_label_blocker": {
            "status": "blocking" if base_gap_by_id else "none",
            "unique_gap_articles": len(base_gap_by_id),
            "month_occurrences": sum(len(row["months"]) for row in base_gap_by_id.values()),
            "per_month": {
                row["target_month"]: row["base_topic_label_gap_candidates"]
                for row in monthly if row["base_topic_label_gap_candidates"]
            },
            "detail_file": "base_topic_label_gaps.json" if base_gap_by_id else None,
            "not_silently_dropped": True,
        },
        "current_run_context": {
            "existing_594_run_spent_or_reserved_upper_usd": tag_source_summary["current_completed"].get("spent_or_reserved_upper_usd"),
            "existing_594_human_review_record": tag_source_summary["current_completed"]["human_review_record"],
            "base_scope_tags_are_not_tone_or_persistence": True,
        },
        "months": monthly,
        "source_sha256": source_hashes,
        "limits": [
            "No person-level completion date was loaded; the window is a conservative candidate upper bound, not matched individual timing.",
            "Known keep articles are counted only after the target-month plus next-month base-label merge and exact_deduplicate.",
            "Base-topic gaps are not treated as keep and are listed separately; resolve them before claiming a fully exact label total.",
            "This task prepares tone/persistence requests only for known keep articles and does not execute them.",
            "The B line remains unchanged; it was read only as the existing 93-month index-union reference for the coverage check.",
        ],
    }
    write_json(out / "summary.json", summary)

    notes = f"""# A82 个人日期新闻标签上界清点

范围：2019-01 至 2025-10，共 82 个 A 月。每月候选截止取目标月最后一天的前一日 23:59:59（纽约）；窗口从上月 1 日开始。没有读取个人完成日期或问卷答案，也没有 API 调用。B11 未改动。

已按 `media_timing_inputs` 的次序，用目标月、下月 `news_label_index.json` 做 `setdefault` 合并，raw 新闻通过 `news_pool_for_prompts`，先排除 SCE 报道，再按 base topic `decision=keep` 形成池并 `exact_deduplicate`。旧 `scope/topics` 字段没有代替 tone/persistence。

## 清点结果

- 可确认 keep 池：{len(a_keep_ids):,} 篇唯一文章，{sum(row['known_keep_after_exact_dedup'] for row in monthly):,} 个月度位置。
- 可复用机制标签：旧审核标签 {len(a_keep_ids & set(load_supplemental_run(root / OLD_LABELS))):,} 篇；已完成新补标 {len(a_keep_ids & set(load_supplemental_run(root / CURRENT_LABELS))):,} 篇。
- 已知 keep 中 tone/persistence 唯一缺口 {len(known_missing_ids):,} 篇，队列 {queue_summary['batches']:,} 批，请求预留上界 ${queue_summary['total_usd_reservation_no_retries']:.6f}，建议帽 ${queue_summary['proposed_budget_usd']:.6f}。队列只含公开 NYT 字段，未执行。
- 与 93 月现有 keep union 对账：A 已知 keep 中 {len(a_keep_ids & full_month_keep_ids):,} 篇被覆盖，额外 {len(extra_beyond_93_ids):,} 篇；93 月唯一 keep 池之前库存为 {full_keep_expected:,} 篇（SCE 报道已排除）。
- Base-topic 缺口 {len(base_gap_ids):,} 篇、{sum(len(row['months']) for row in base_gap_by_id.values()):,} 次月度出现；详见 `base_topic_label_gaps.json`。这些文章未当成 keep，也未静默删除。若全部最终判为 keep，条件性 tone/persistence 请求上界为 {len(conditional_requests):,} 批、${conditional_reservation:.6f} 预留、建议帽 ${max(0.25, round(conditional_reservation * 1.25 + 0.000001, 6)):.6f}；在 topic/keep 决策完成前不能执行。

本结果是月度日期上界，不代表个体实际答卷截止。现有 594 补标只覆盖七个机制窗口；这次覆盖 A82 最大候选截止。全 A82 个人截止已知但具体日期仍未知，因此在执行前仍需用实际响应日做最终筛选。2019-01 的食物 catalog 覆盖限制由并行预检另行登记，本清点没有读取该预检微观行。

## 重跑

```bash
/Users/wushuyue/anaconda3/envs/socioverse/bin/python scripts/inventory_sce_personal_time_labels.py --out outputs/sce_a_personal_time_labels_full_inventory_20261025_v2
```
"""
    (out / "EXECUTION_TASKS.md").write_text(notes)

    manifest = {
        "schema": "sce_a_personal_time_labels_inventory_manifest/v1",
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
    summary = inventory(args.out)
    print(json.dumps({
        "status": summary["status"],
        "a_unique_known_keep_articles": summary["a_personal_window_pool"]["unique_known_keep_articles_after_sce_exclusion"],
        "base_topic_gaps": summary["base_topic_label_blocker"]["unique_gap_articles"],
        "known_unique_tone_persistence_gap": summary["known_keep_label_queue"]["unique_articles"],
        "known_gap_batches": summary["known_keep_label_queue"]["batches"],
        "known_gap_budget_cap_usd": summary["known_keep_label_queue"]["proposed_budget_cap_usd"],
        "new_api_calls": summary["new_api_calls"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
