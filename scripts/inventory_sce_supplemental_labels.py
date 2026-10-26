"""Inventory mechanism-label coverage for the 93 materialized SCE news pools.

This is an offline, aggregate-only inventory. It reads public NYT archives,
monthly news-label indexes, and completed public-news label ledgers. It never
reads household microdata, target Q8/Q9 values, or makes model/API calls.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

from studies.sce_inflation_expectations.experiments.frozen_batch import ROOT, sha
from studies.sce_inflation_expectations.experiments.media_mechanism_trial import is_sce_report
from studies.sce_inflation_expectations.experiments.media_mechanism_v3_preparation import (
    apply_label_overrides,
    load_supplemental_run,
)
from studies.sce_inflation_expectations.news_mechanism_label_preparation import (
    prepare_public_articles,
)
from studies.sce_inflation_expectations.news_mechanism_labels import (
    PERSISTENCE,
    PUBLIC_FIELDS,
    TONES,
    build_requests,
)


MATERIALIZED = Path("outputs/sce_fullperiod_materialized_20261022_v2")
OLD_LABELS = Path("outputs/sce_news_mechanism_labels_20261025_v1")
OLD_REVIEW = Path("outputs/sce_news_mechanism_label_audit_20261025_v1/review.json")
CURRENT_LABELS = Path("outputs/sce_media_timing_supplemental_labels_20261025_v1")
CURRENT_INPUTS = Path("outputs/sce_media_timing_inputs_20261025_v3/supplemental_label_inputs")
NYT_ARCHIVE = Path("data/raw/nyt_archive")


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def write_json(path: Path, value: dict) -> None:
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def article_id_for_doc(doc: dict) -> str | None:
    identity = doc.get("_id") or doc.get("uri") or doc.get("web_url")
    if not identity:
        return None
    text = {
        "headline": (doc.get("headline") or {}).get("main") or "",
        "abstract": doc.get("abstract") or "",
        "snippet": doc.get("snippet") or "",
    }
    if not any(text.values()):
        return None
    text_hash = hashlib.sha256(
        json.dumps(text, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return hashlib.sha256((identity + "\n" + text_hash).encode("utf-8")).hexdigest()[:24]


def scan_secondary_mechanism_labels(root: Path, excluded: set[Path]) -> tuple[dict, list[dict]]:
    """Find other completed, article-keyed tone/persistence ledgers under outputs."""
    tags = {}
    reports = []
    outputs = root / "outputs"
    for path in outputs.rglob("labels.jsonl"):
        resolved = path.resolve()
        if resolved in excluded or "local_runs" in path.parts:
            continue
        if not any("news" in part.lower() or "mechanism" in part.lower() for part in path.parts):
            continue
        file_tags = {}
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            label = row.get("label", row) if isinstance(row, dict) else {}
            if not isinstance(label, dict):
                continue
            aid, tone, persistence = (
                label.get("article_id"), label.get("tone"), label.get("persistence")
            )
            if aid and tone in TONES and persistence in PERSISTENCE:
                pair = {"tone": tone, "persistence": persistence}
                if aid in file_tags and file_tags[aid] != pair:
                    raise ValueError(f"conflicting mechanism labels in {path}")
                file_tags[aid] = pair
        if file_tags:
            for aid, pair in file_tags.items():
                if aid in tags and tags[aid] != pair:
                    raise ValueError("conflicting completed mechanism-label ledgers")
                tags[aid] = pair
            reports.append({
                "path": str(path.resolve().relative_to(root)),
                "valid_article_labels": len(file_tags),
            })
    return tags, reports


def load_primary_labels(root: Path) -> tuple[dict, dict, dict]:
    old_state = read_json(root / OLD_LABELS / "state.json")
    if old_state.get("status") != "completed":
        raise ValueError("the audited 1,374-article label run is not complete")
    old = load_supplemental_run(root / OLD_LABELS)
    review = read_json(root / OLD_REVIEW)
    old = apply_label_overrides(old, review.get("overrides", {}))

    current_state = read_json(root / CURRENT_LABELS / "state.json")
    if current_state.get("status") != "completed":
        raise ValueError("the current 594-article supplemental run is not complete")
    current = load_supplemental_run(root / CURRENT_LABELS)
    input_summary = read_json(root / CURRENT_INPUTS / "summary.json")
    pending = read_json(root / CURRENT_INPUTS / "pending_public_articles.json")
    pending_ids = {row["article_id"] for row in pending}
    if len(pending_ids) != len(pending) or pending_ids != set(current):
        raise ValueError("completed 594-article labels do not match the prepared input IDs")
    if input_summary.get("unique_articles_to_label") != len(current):
        raise ValueError("supplemental run and preparation counts differ")

    review_path = root / CURRENT_LABELS / "review.json"
    if review_path.is_file():
        current_review = read_json(review_path)
        current = apply_label_overrides(current, current_review.get("overrides", {}))
        current_review_status = "review_record_present"
    else:
        current_review_status = "no_separate_human_review_record"

    if set(old) & set(current) and any(old[aid] != current[aid] for aid in set(old) & set(current)):
        raise ValueError("old and current label runs disagree on shared article IDs")
    return old, current, {
        "old_run": {
            "status": old_state["status"],
            "articles_valid": len(old),
            "audit_path": str(OLD_REVIEW),
            "override_articles": len(review.get("overrides", {})),
        },
        "current_run": {
            "status": current_state["status"],
            "articles_valid": len(current),
            "batches_planned": current_state.get("batches_planned"),
            "batches_attempted": current_state.get("batches_attempted"),
            "errors": current_state.get("errors"),
            "spent_or_reserved_upper_usd": current_state.get("spent_or_reserved_upper_usd"),
            "authorization_cap_usd": current_state.get("cap_usd"),
            "human_review_status": current_review_status,
            "prepared_request_sha256": input_summary.get("request_file_sha256"),
        },
        "old_current_overlap": len(set(old) & set(current)),
    }


def prepare_inventory(out: Path, root: Path = ROOT) -> dict:
    root = Path(root).resolve()
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(root / "outputs"):
        raise ValueError("choose a fresh output directory under outputs/")

    materialized = root / MATERIALIZED
    coverage_path = materialized / "coverage.json"
    coverage = read_json(coverage_path)["months"]
    if len(coverage) != 93:
        raise ValueError(f"expected 93 A/B materialized months; found {len(coverage)}")

    month_ids = {}
    month_records = {}
    expected_index_rows = {}
    source_months = set()
    index_paths = []
    for row in coverage:
        month = row["target_month"].replace("-", "")
        index_path = materialized / month / "news_label_index.json"
        index = read_json(index_path)
        if index.get("target_month") != row["target_month"] or index.get("as_of") != row["as_of"]:
            raise ValueError(f"monthly index/cutoff mismatch for {month}")
        keep_ids = []
        for item in index["pool"]:
            label = item.get("label") or {}
            if label.get("decision") != "keep":
                continue
            aid = item["article_id"]
            if aid in keep_ids:
                raise ValueError(f"duplicate keep article ID within {month}")
            keep_ids.append(aid)
            source_months.add(item["source_month"])
            if aid in expected_index_rows and expected_index_rows[aid]["pub_date"] != item["pub_date"]:
                raise ValueError("same article ID has conflicting index publication dates")
            expected_index_rows.setdefault(aid, item)
        month_ids[month] = keep_ids
        month_records[month] = {
            "sample_line": "A" if row["target_month"] <= "2025-10" else "B",
            "target_month": row["target_month"],
            "as_of": row["as_of"],
            "index_rows": len(index["pool"]),
            "keep_pre_sce": len(keep_ids),
        }
        index_paths.append(index_path)

    # Join the materialized index IDs back to public NYT text once per archive
    # month. This avoids rerunning keyword selection and never touches people.
    candidate_ids = set(expected_index_rows)
    public_by_id = {}
    archive_paths = []
    for source_month in sorted(source_months):
        archive_path = root / NYT_ARCHIVE / f"{source_month}.json"
        archive_paths.append(archive_path)
        docs = read_json(archive_path)["response"]["docs"]
        for doc in docs:
            aid = article_id_for_doc(doc)
            if aid not in candidate_ids:
                continue
            if (doc.get("pub_date") or "")[:10] != expected_index_rows[aid]["pub_date"][:10]:
                # Identical source text can appear in adjacent archive
                # snapshots with a different publication timestamp. The
                # materialized index pins the timestamp used for this pool.
                continue
            public = {
                "article_id": aid,
                "headline": (doc.get("headline") or {}).get("main") or "",
                "abstract": doc.get("abstract") or "",
                "snippet": doc.get("snippet") or "",
                "source": "NYT Archive API",
                "section_name": doc.get("section_name") or "",
                "news_desk": doc.get("news_desk") or "",
            }
            if aid in public_by_id and public_by_id[aid] != public:
                raise ValueError("same article ID maps to conflicting public article fields")
            public_by_id[aid] = public

    missing_source_records = candidate_ids - set(public_by_id)
    if missing_source_records:
        raise ValueError(f"{len(missing_source_records)} kept article IDs lack source text; inventory stopped")

    sce_ids = {aid for aid, row in public_by_id.items() if is_sce_report(row)}
    eligible_ids = candidate_ids - sce_ids
    old_reviewed, current_valid, label_sources = load_primary_labels(root)
    completed_tags = old_reviewed | current_valid
    secondary_path_exclusions = {
        (root / OLD_LABELS / "labels.jsonl").resolve(),
        (root / CURRENT_LABELS / "labels.jsonl").resolve(),
    }
    secondary_tags, secondary_sources = scan_secondary_mechanism_labels(root, secondary_path_exclusions)
    extra_reusable = set(secondary_tags) & eligible_ids - set(completed_tags)
    all_reusable = set(completed_tags) | extra_reusable

    old_ids = set(old_reviewed)
    current_ids = set(current_valid)
    secondary_only_ids = set(secondary_tags) - old_ids - current_ids
    for month, ids in month_ids.items():
        unique_ids = set(ids) & eligible_ids
        record = month_records[month]
        record.update({
            "sce_reports_excluded": len(set(ids) & sce_ids),
            "keep_after_sce": len(unique_ids),
            "reused_old_reviewed": len(unique_ids & old_ids),
            "reused_current_completed": len(unique_ids & current_ids - old_ids),
            "reused_other_completed": len(unique_ids & secondary_only_ids),
            "missing_tone_persistence": len(unique_ids - all_reusable),
        })

    missing_after_current = eligible_ids - all_reusable
    missing_old_only = eligible_ids - old_ids - extra_reusable
    records_after_current = [public_by_id[aid] for aid in sorted(missing_after_current)]
    records_old_only = [public_by_id[aid] for aid in sorted(missing_old_only)]
    current_requests = build_requests(records_after_current)
    old_only_requests = build_requests(records_old_only)
    current_reserve = sum(row["request_usd_reservation"] for row in current_requests)
    old_only_reserve = sum(row["request_usd_reservation"] for row in old_only_requests)

    out.mkdir(parents=True)
    source_paths = [
        coverage_path,
        *index_paths,
        *archive_paths,
        root / OLD_LABELS / "state.json",
        root / OLD_LABELS / "labels.jsonl",
        root / OLD_REVIEW,
        root / CURRENT_LABELS / "state.json",
        root / CURRENT_LABELS / "labels.jsonl",
        root / CURRENT_INPUTS / "summary.json",
        root / CURRENT_INPUTS / "pending_public_articles.json",
        root / "studies/sce_inflation_expectations/experiments/media_timing_inputs.py",
        root / "studies/sce_inflation_expectations/experiments/media_mechanism_trial.py",
        root / "studies/sce_inflation_expectations/experiments/media_mechanism_v3_preparation.py",
        root / "studies/sce_inflation_expectations/news_mechanism_label_preparation.py",
        root / "studies/sce_inflation_expectations/news_mechanism_labels.py",
        root / "studies/sce_inflation_expectations/news_label_compat.py",
    ]
    source_paths.extend(root / source["path"] for source in secondary_sources)
    source_hashes = {
        str(path.resolve().relative_to(root)): sha(path)
        for path in sorted(set(source_paths), key=lambda p: str(p))
    }
    write_json(out / "source_inventory.json", {"source_sha256": source_hashes})

    monthly_rows = [month_records[month] for month in sorted(month_records)]
    csv_path = out / "monthly_inventory.csv"
    columns = [
        "sample_line", "target_month", "as_of", "index_rows", "keep_pre_sce",
        "sce_reports_excluded", "keep_after_sce", "reused_old_reviewed",
        "reused_current_completed", "reused_other_completed", "missing_tone_persistence",
    ]
    with csv_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(monthly_rows)

    queue_dir = out / "public_label_queue_after_current_labels"
    queue_summary = prepare_public_articles(
        records_after_current,
        queue_dir,
        root,
        source_paths,
        "Only public NYT headline/abstract/snippet/source/section/desk and article identifiers from the 93 materialized monthly keep pools; no SCE household data or target answers.",
        label_mode="supplemental2",
    )

    a_rows = [row for row in coverage if row["target_month"] <= "2025-10"]
    b_rows = [row for row in coverage if row["target_month"] >= "2025-11"]
    a_cutoff_days = [int(row["as_of"][8:10]) for row in a_rows]
    label_supplement_months = [201905, 202009, 202106, 202109, 202112, 202206, 202312]
    summary = {
        "schema": "sce_supplemental_full_inventory/v1",
        "status": "offline_inventory_complete_label_queue_prepared_no_api",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "new_api_calls": 0,
        "target_answers_read": False,
        "microdata_read": False,
        "scope": {
            "materialized_months": len(coverage),
            "A_months": len(a_rows),
            "B_months": len(b_rows),
            "month_range": [coverage[0]["target_month"], coverage[-1]["target_month"]],
            "monthly_cutoff_policy": "Use each frozen news_label_index.json as_of; no per-person date expansion.",
        },
        "pool_inventory": {
            "monthly_keep_positions_before_sce_exclusion": sum(row["keep_pre_sce"] for row in monthly_rows),
            "unique_keep_articles_before_sce_exclusion": len(candidate_ids),
            "monthly_sce_report_exclusions": sum(row["sce_reports_excluded"] for row in monthly_rows),
            "unique_sce_report_articles_excluded": len(sce_ids),
            "monthly_keep_positions_after_sce_exclusion": sum(row["keep_after_sce"] for row in monthly_rows),
            "unique_keep_articles_after_sce_exclusion": len(eligible_ids),
            "source_records_missing": len(missing_source_records),
        },
        "reusable_label_sources": {
            **label_sources,
            "old_reviewed_articles_in_current_pool": len(old_ids & eligible_ids),
            "current_completed_articles_in_current_pool": len(current_ids & eligible_ids),
            "old_current_article_overlap": len(old_ids & current_ids),
            "other_completed_article_labels_in_current_pool": len(extra_reusable),
            "other_tagged_label_sources": secondary_sources,
            "fox_mechanism_labels_are_distinct_source_corpus": True,
            "unique_articles_reusable_in_current_pool": len(all_reusable & eligible_ids),
            "unique_articles_missing_tone_and_persistence": len(missing_after_current),
            "monthly_keep_positions_missing_tags": sum(row["missing_tone_persistence"] for row in monthly_rows),
        },
        "label_queue_after_current_completion": {
            "unique_articles": queue_summary["unique_articles_to_label"],
            "batches": queue_summary["batches"],
            "articles_per_batch_max": 8,
            "request_reservation_no_retries_usd": queue_summary["total_usd_reservation_no_retries"],
            "proposed_budget_cap_usd": queue_summary["proposed_budget_usd"],
            "classifier": queue_summary["requested_model"],
            "label_mode": queue_summary["label_mode"],
            "manual_execution_authorized": False,
            "retry_policy": "none; uncertain or failed batches need separate authorization",
            "queue_dir": str(queue_dir.resolve().relative_to(root)),
        },
        "fallback_if_current_594_are_not_accepted_for_reuse": {
            "unique_articles": len(records_old_only),
            "batches": len(old_only_requests),
            "request_reservation_no_retries_usd": old_only_reserve,
            "proposed_budget_cap_usd": max(0.25, round(old_only_reserve * 1.25 + 0.000001, 6)),
        },
        "personal_date_window_gap": {
            "current_A_shared_cutoff_day_range": [min(a_cutoff_days), max(a_cutoff_days)],
            "all_A82_personal_date_windows_counted": False,
            "current_594_supplement_months": label_supplement_months,
            "current_594_supplement_scope": "Seven registered A-line media-timing month windows only; the 594 IDs overlap current 93-month keep pools, but do not cover all A82 respondent dates.",
            "remaining_uninventoried_window": "For each A month, news after its shared materialized as_of through each respondent's previous-day-end personal cutoff, up to that target month's end. The 75 other A months and full-person coverage within the seven tested months were not counted here.",
            "B11_personal_date_expansion_counted": False,
        },
        "months": monthly_rows,
        "source_sha256": source_hashes,
        "limits": [
            "The queue labels current monthly keep pools only; it does not add target-month news beyond the frozen shared as_of.",
            "The 594-article run is structurally complete and matches its prepared input; it has no separate human review record in its run directory.",
            "A full A82 personal-date expansion requires a separate archive-window inventory and new labels; no respondent-level dates were read here.",
            "This is not a simulation authorization or an estimate of simulation calls/cost.",
        ],
    }
    write_json(out / "summary.json", summary)

    handoff = f"""# SCE 机制标签库存与执行任务书

库存路径：`{out.relative_to(root)}`。本任务只核查已物化月度新闻池和公开新闻标签，没有读取微观样本、目标 Q8/Q9，也没有 API 调用。

## 当前库存

- 月度池覆盖 {len(a_rows)} 个 A 月（{a_rows[0]['target_month']} 至 {a_rows[-1]['target_month']}）和 {len(b_rows)} 个 B 月（{b_rows[0]['target_month']} 至 {b_rows[-1]['target_month']}），共 {len(coverage)} 月。
- 93 个现有 `news_label_index.json` 含 {sum(row['keep_pre_sce'] for row in monthly_rows):,} 个 keep 月度位置、{len(candidate_ids):,} 个唯一文章；识别出 {len(sce_ids)} 篇 SCE 报道并从标签范围排除。剩 {len(eligible_ids):,} 个唯一文章、{sum(row['keep_after_sce'] for row in monthly_rows):,} 个跨月 keep 位置。
- 复用 {len(old_ids & eligible_ids):,} 篇已审核旧标签，来自 `sce_news_mechanism_labels_20261025_v1`；再复用 {len(current_ids & eligible_ids):,} 篇已完成新补标。两批无重复，后者与准备输入逐 ID 相等、75/75 批、错误数 {label_sources['current_run']['errors']}。新 594 篇没有独立人工审核记录，下一步应先抽样复核并登记必要覆盖值。
- 完成这两批复用后，剩 {len(missing_after_current):,} 篇唯一文章缺 tone/persistence；重复计入月度池是 {sum(row['missing_tone_persistence'] for row in monthly_rows):,} 个月度位置。Fox 标签属于另一来源文章，未与 NYT 月度池 ID 重合。

## 可执行标签批次（准备完成，未执行）

`public_label_queue_after_current_labels/` 仅含 NYT headline/abstract/snippet/source metadata 和 article ID，不含个人记录。沿用 `deepseek-flash`、原 supplemental2 classifier、每批最多 8 篇、无重试，准备了 {queue_summary['batches']:,} 批；请求预留上界为 ${queue_summary['total_usd_reservation_no_retries']:.6f}，按既有 1.25 倍规则建议预算帽 ${queue_summary['proposed_budget_usd']:.6f}。当前 594 补标的授权不覆盖这批；本任务没有发送这些请求。

若 594 篇不能通过后续复核，则 fallback 上界为 {len(records_old_only):,} 篇、{len(old_only_requests):,} 批、预留 ${old_only_reserve:.6f}、建议帽 ${max(0.25, round(old_only_reserve * 1.25 + 0.000001, 6)):.6f}。

## A82 个人完成日期的缺口

本清点按每月冻结的共享 `as_of` 计算。A82 的 `as_of` 日在每月第 {min(a_cutoff_days)} 至第 {max(a_cutoff_days)} 日之间。若改用每人的完成日减一天，后续每个 A 月仍需从该月共享截止后追到各人的个人截止；上限可到目标月最后一天。本次没有按 82 月逐人查日期或统计额外原始新闻。当前 594 补标只覆盖 {', '.join(str(m) for m in label_supplement_months)} 七个既有机制窗口，不能作为全 A82 后半月覆盖。B11 个人日期扩展也未纳入。

## 后续交接顺序

1. 人工抽样复核当前 594 标签；新批结束后对新增标签按来源、月份和 tone/persistence 分层抽样，记录独立审阅及覆盖值。
2. 在获新预算授权后执行上述 1,504 批标签请求；保留逐批输入/输出/失败账本，不重发失败或状态不明批次。
3. 基于 `article_id` 生成新的派生 tone/persistence 标签版本；保持旧 `news_label_index`、旧标签批次和冻结 prompt 不变，继续排除 SCE 报道。
4. 另行清点 A82 每位样本完成日前日末需要的当月新增新闻；至少补清其余 75 个月，并核对七个既有窗口是否覆盖了所有拟运行样本。
5. 将新派生标签接入 93 个月输入包，做无 API 的 Core 干跑、行数和文章 ID 对账，再冻结 prompt、模型、重试与预算方案。
6. 全量模拟调用数及费用由冻结后的 A/B roster、arm 和 repeats 计算；本标签库存不构成模拟授权。

## 重跑库存

```bash
/Users/wushuyue/anaconda3/envs/socioverse/bin/python scripts/inventory_sce_supplemental_labels.py --out outputs/sce_supplemental_full_inventory_20261025_v2
```

本版输出路径已占用，重跑使用新的 `v2` 目录；脚本会校验当前 594 完成状态并拒绝覆盖。
"""
    (out / "EXECUTION_TASKS.md").write_text(handoff)

    manifest = {
        "schema": "sce_supplemental_full_inventory_manifest/v1",
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
    summary = prepare_inventory(args.out)
    print(json.dumps({
        "status": summary["status"],
        "unique_keep_articles_after_sce_exclusion": summary["pool_inventory"]["unique_keep_articles_after_sce_exclusion"],
        "reusable_articles": summary["reusable_label_sources"]["unique_articles_reusable_in_current_pool"],
        "unique_articles_missing_tone_and_persistence": summary["reusable_label_sources"]["unique_articles_missing_tone_and_persistence"],
        "batches_prepared": summary["label_queue_after_current_completion"]["batches"],
        "new_api_calls": summary["new_api_calls"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
