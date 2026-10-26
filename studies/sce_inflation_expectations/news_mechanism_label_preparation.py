"""Freeze the seven-month NYT supplemental-label request package offline."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .experiments.frozen_batch import ROOT, dump, sha
from .experiments.fullperiod_materialization import news_pool_for_prompts
from .news_label_compat import normalize_label
from .news_mechanism_labels import (
    INPUT_USD_PER_MTOK,
    OUTPUT_USD_PER_MTOK,
    PUBLIC_FIELDS,
    SYSTEM_PROMPT,
    build_requests,
)
from .news_selection_trial import RecallRules, RULE_FILE

MONTHS = (201905, 202009, 202106, 202109, 202112, 202206, 202312)
MATERIALIZED = "outputs/sce_fullperiod_materialized_20261022_v2"
ASSEMBLY = "outputs/sce_monthly_fine_full_assembly_20261023_v3/prompts"


def read_json(path):
    return json.loads(Path(path).read_text())


def collect_nyt_articles(root=ROOT, months=MONTHS):
    root = Path(root)
    unique = {}
    sources = {}
    month_receipts = []
    for month in months:
        target = f"{month // 100}-{month % 100:02}"
        environment_path = root / ASSEMBLY / str(month) / "environment.json"
        label_path = root / MATERIALIZED / str(month) / "news_label_index.json"
        cutoff = read_json(environment_path)["provider_args"]["targets"][0]["as_of"]
        raw, counts, raw_sources = news_pool_for_prompts(root, target, cutoff, RecallRules(read_json(RULE_FILE)))
        labels = {
            row["article_id"]: normalize_label(row["label"])
            for row in read_json(label_path)["pool"] if row["label"]
        }
        keep = 0
        for original in raw:
            label = labels.get(original["article_id"])
            if not label or label["decision"] != "keep":
                continue
            keep += 1
            public = {field: original.get(field) or "" for field in PUBLIC_FIELDS}
            public["article_id"] = original["article_id"]
            if public["article_id"] in unique and unique[public["article_id"]] != public:
                raise ValueError("cross-window public article text differs")
            unique[public["article_id"]] = public
        for path in (environment_path, label_path):
            sources[str(path.resolve().relative_to(root))] = sha(path)
        sources.update(raw_sources)
        month_receipts.append({
            "month": month, "as_of": cutoff, "window_unique_articles": counts["unique_articles"],
            "keyword_candidates": counts["coarse_candidates"], "keep": keep,
        })
    articles = [unique[key] for key in sorted(unique)]
    receipt = {"months": month_receipts, "unique_keep_articles": len(articles), "source_sha256": sources}
    return articles, receipt


def prepare_public_articles(articles, out, root, source_paths, data_scope, label_mode="supplemental2"):
    root = Path(root)
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(root / "outputs"):
        raise ValueError("fresh output under outputs required")
    requests = build_requests(articles, label_mode=label_mode)
    out.mkdir(parents=True)
    (out / "pending_public_articles.json").write_text(json.dumps(articles, ensure_ascii=False, indent=2) + "\n")
    request_path = out / "requests_prepared.jsonl"
    request_path.write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in requests))
    sources = {str(Path(path).resolve().relative_to(root)): sha(path) for path in source_paths}
    reserved = sum(row["request_usd_reservation"] for row in requests)
    summary = {
        "schema": "sce_news_mechanism_label_preparation/v1",
        "status": "offline_prepared_new_budget_required", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "unique_articles_to_label": len(articles), "batches": len(requests),
        "request_file_sha256": sha(request_path), "pending_articles_sha256": sha(out / "pending_public_articles.json"),
        "system_prompt_sha256": requests[0]["system_prompt_sha256"] if requests else hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "label_mode": label_mode, "source_sha256": sources,
        "total_usd_reservation_no_retries": reserved,
        "proposed_budget_usd": max(0.25, round(reserved * 1.25 + 0.000001, 6)),
        "pricing_basis": {"input_usd_per_mtok": INPUT_USD_PER_MTOK, "output_usd_per_mtok": OUTPUT_USD_PER_MTOK,
                          "basis": "conservative peak uncached rates reused from existing DeepSeek label pipeline"},
        "destination": "https://api.deepseek.com/v1/chat/completions", "requested_model": "deepseek-flash",
        "data_scope": data_scope, "retry_policy": "none; resume only never-attempted batches; failures need separate authorization",
        "new_api_calls": 0,
    }
    dump(out / "summary.json", summary)
    return summary


def prepare(out, root=ROOT):
    root = Path(root)
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(root / "outputs"):
        raise ValueError("fresh output under outputs required")
    articles, receipt = collect_nyt_articles(root)
    requests = build_requests(articles)
    out.mkdir(parents=True)
    (out / "pending_public_articles.json").write_text(json.dumps(articles, ensure_ascii=False, indent=2) + "\n")
    request_path = out / "requests_prepared.jsonl"
    request_path.write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in requests))
    sources = dict(receipt["source_sha256"])
    for path in (Path(__file__), ROOT / "studies/sce_inflation_expectations/news_mechanism_labels.py", RULE_FILE):
        sources[str(path.resolve().relative_to(root))] = sha(path)
    summary = {
        "schema": "sce_news_mechanism_label_preparation/v1",
        "status": "offline_prepared_new_budget_required",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "months": receipt["months"], "unique_articles_to_label": len(articles), "batches": len(requests),
        "request_file_sha256": sha(request_path), "pending_articles_sha256": sha(out / "pending_public_articles.json"),
        "system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "source_sha256": sources, "total_usd_reservation_no_retries": sum(row["request_usd_reservation"] for row in requests),
        "proposed_budget_usd": max(0.25, round(sum(row["request_usd_reservation"] for row in requests) * 1.25 + 0.000001, 6)),
        "pricing_basis": {"input_usd_per_mtok": INPUT_USD_PER_MTOK, "output_usd_per_mtok": OUTPUT_USD_PER_MTOK,
                          "basis": "conservative peak uncached rates reused from existing DeepSeek label pipeline"},
        "destination": "https://api.deepseek.com/v1/chat/completions", "requested_model": "deepseek-flash",
        "data_scope": "public NYT headline/abstract/snippet/source/section metadata only; no personas or SCE answers",
        "retry_policy": "none; resume only never-attempted batches; failed or uncertain batches require separate authorization",
        "new_api_calls": 0,
    }
    dump(out / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.out)
    print(json.dumps({key: result[key] for key in ("unique_articles_to_label", "batches", "total_usd_reservation_no_retries", "proposed_budget_usd")}))


if __name__ == "__main__":
    main()
