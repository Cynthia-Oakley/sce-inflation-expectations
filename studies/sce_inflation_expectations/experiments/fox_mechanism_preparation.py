"""Fox-only public label and prompt-pool adapters for media mechanism V3."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .frozen_batch import ROOT, read_json
from .media_mechanism_trial import external_row, is_sce_report, load_external_pool
from ..news_exposure import NEWS_KEYS
from ..news_exposure_demo import news_tags
from ..news_mechanism_label_preparation import prepare_public_articles
from ..news_mechanism_labels import DECISIONS, FOX_LABEL_FIELDS, PERSISTENCE, PUBLIC_FIELDS, SCOPES, TONES, TOPICS

FOX_OUTPUT = "outputs/sce_fox_news_20261025_v1"
NEW_MONTHS = (201905, 202009, 202109, 202112, 202312)
EXISTING_MONTHS = (202106, 202206)


def public_article(raw):
    return {
        "article_id": raw["article_id"], "headline": raw["title"],
        "abstract": raw["excerpt_lead"], "snippet": "", "source": raw["source"],
        "section_name": raw.get("article_type", ""), "news_desk": "Fox",
    }


def collect_fox_public_articles(root=ROOT):
    root = Path(root)
    unique = {}
    source_paths = []
    for month in NEW_MONTHS:
        path = root / FOX_OUTPUT / str(month) / "candidates.json"
        candidates = read_json(path)["candidates"]
        source_paths.append(path)
        for raw in candidates:
            if is_sce_report(raw):
                continue
            article = public_article(raw)
            if set(article) != set(PUBLIC_FIELDS):
                raise ValueError("Fox public whitelist mismatch")
            if article["article_id"] in unique and unique[article["article_id"]] != article:
                raise ValueError("Fox text differs across windows")
            unique[article["article_id"]] = article
    return [unique[key] for key in sorted(unique)], source_paths


def prepare_fox_labels(out, root=ROOT):
    root = Path(root)
    articles, _ = collect_fox_public_articles(root)
    sources = [
        root / "studies/sce_inflation_expectations/news_mechanism_labels.py",
        root / "studies/sce_inflation_expectations/news_mechanism_label_preparation.py",
        root / "studies/sce_inflation_expectations/news_mechanism_label_runner.py",
        root / "studies/sce_inflation_expectations/experiments/fox_mechanism_preparation.py",
    ]
    return prepare_public_articles(articles, out, root, sources,
        "public Fox headline/lead/source metadata only; no personas or SCE answers", "slim4_mechanism6")


def load_fox_labels(directory, review_path=None):
    directory = Path(directory)
    state = read_json(directory / "state.json")
    if state.get("status") != "completed" or state.get("label_mode") != "slim4_mechanism6":
        raise ValueError("complete six-field Fox label run required")
    labels = {}
    for line in (directory / "labels.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        label = json.loads(line)["label"]
        if set(label) != FOX_LABEL_FIELDS or label["article_id"] in labels:
            raise ValueError("invalid or duplicate Fox label")
        labels[label["article_id"]] = label
    if len(labels) != state["articles_valid"]:
        raise ValueError("Fox label count differs from receipt")
    if review_path is not None:
        labels = apply_fox_label_overrides(labels, read_json(review_path)["overrides"])
    return labels


def apply_fox_label_overrides(labels, overrides):
    reviewed = {article_id: dict(label) for article_id, label in labels.items()}
    validators = {"decision": DECISIONS, "tone": TONES, "persistence": PERSISTENCE, "scope": SCOPES}
    for article_id, changes in overrides.items():
        if article_id not in reviewed:
            raise ValueError("Fox override references unknown article")
        if not changes or set(changes) - {"decision", "tone", "persistence", "topics", "scope"}:
            raise ValueError("unexpected Fox override fields")
        for field, value in changes.items():
            if field == "topics":
                if not isinstance(value, list) or len(value) != len(set(value)) or any(topic not in TOPICS for topic in value):
                    raise ValueError("invalid Fox override topics")
            elif value not in validators[field]:
                raise ValueError("invalid Fox override enum")
            reviewed[article_id][field] = value
    return reviewed


def new_fox_row(raw, label):
    row = {
        "article_id": raw["article_id"], "headline": raw["title"], "abstract": raw["excerpt_lead"],
        "snippet": "", "pub_date": raw["published_at"], "web_url": raw["original_url"],
        "text_sha256": raw["text_sha256"], "text_vintage_status": raw["text_vintage_status"],
        "print_section": None, "print_page": None, "placement": "external_online",
        "routing_tags": [], "semantic_label": {**label, "source": raw["source"], "article_type": raw["article_type"]},
    }
    row["routing_tags"] = news_tags(row)
    if set(row) != NEWS_KEYS:
        raise ValueError("Fox news schema mismatch")
    return row


def apply_english_text(row, entry):
    headline = entry["title"]
    abstract = entry["excerpt"]
    return dict(row, headline=headline, abstract=abstract,
        text_sha256=hashlib.sha256((headline + "\n" + abstract).encode()).hexdigest(),
        text_vintage_status="live_english_page_" + entry["observed_at"][:10] + "_not_archive_certified")


def refresh_existing_english(root, fetcher, months=EXISTING_MONTHS):
    import gzip
    from ..fox_news_archive import parse_article_html, record_http, utc_now_iso

    root = Path(root)
    results = {}
    for month in months:
        rows = load_fox_pool(root, month, {})
        raw_dir = root / FOX_OUTPUT / str(month) / "raw" / "existing_english"
        raw_dir.mkdir(parents=True, exist_ok=True)
        entries = {}
        for row in rows:
            path = raw_dir / f"{row['article_id']}.html.gz"
            if path.exists():
                body = gzip.decompress(path.read_bytes())
            else:
                try:
                    body = fetcher.fetch(row["web_url"])
                    record_http(root / FOX_OUTPUT / str(month), row["web_url"], 200, len(body))
                    path.write_bytes(gzip.compress(body))
                except Exception as exc:
                    record_http(root / FOX_OUTPUT / str(month), row["web_url"], None, 0, str(exc))
                    raise
            parsed = parse_article_html(body, row["web_url"])
            entries[row["article_id"]] = {"title": parsed["title"], "excerpt": parsed["excerpt"],
                "published_at_from_page": parsed["published_at"], "observed_at": utc_now_iso(),
                "original_url": row["web_url"]}
        payload = {"schema": "sce_fox_existing_english/v1", "month": month, "entries": entries}
        target = root / FOX_OUTPUT / "existing_english" / f"{month}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        results[month] = entries
    return results


def load_fox_pool(root, month, supplemental, require_english=False):
    root = Path(root)
    if month in EXISTING_MONTHS:
        rows, _ = load_external_pool(root, month)
        manual = {row["original_url"]: row["manual_judgment"] for row in
                  read_json(root / FOX_OUTPUT / "existing_months" / f"{month}.json")["candidates"]}
        pool = []
        for row in rows:
            label = row["semantic_label"]
            if not label["source"].startswith("Fox"):
                continue
            judgment = manual[row["web_url"]]
            label["tone"] = label.pop("trial_tone")
            label["persistence"] = judgment["persistence"]
            pool.append(row)
        english_path = root / FOX_OUTPUT / "existing_english" / f"{month}.json"
        if require_english and not english_path.exists():
            raise ValueError("English Fox source text required")
        if english_path.exists():
            entries = read_json(english_path)["entries"]
            if set(entries) != {row["article_id"] for row in pool}:
                raise ValueError("English Fox source coverage differs")
            pool = [apply_english_text(row, entries[row["article_id"]]) for row in pool]
        return pool
    candidates = read_json(root / FOX_OUTPUT / str(month) / "candidates.json")["candidates"]
    pool = []
    for raw in candidates:
        if is_sce_report(raw):
            continue
        label = supplemental.get(raw["article_id"])
        if not label:
            raise ValueError("missing Fox six-field label")
        if label["decision"] == "keep":
            pool.append(new_fox_row(raw, label))
    return sorted(pool, key=lambda row: (row["pub_date"], row["article_id"]))


def existing_candidate_payload(root, month):
    if month not in EXISTING_MONTHS:
        raise ValueError("only the two manual-sample months have existing candidates")
    candidates = []
    for row in load_fox_pool(root, month, {}):
        label = row["semantic_label"]
        candidates.append({
            "source": label["source"], "article_type": label["article_type"],
            "title": row["headline"], "original_url": row["web_url"], "published_at": row["pub_date"],
            "excerpt_lead": row["abstract"], "text_vintage_status": row["text_vintage_status"],
            "article_id": row["article_id"], "text_sha256": row["text_sha256"],
            "wayback": {"status": "unverified"},
            "label": {"decision": "keep", "topics": label["topics"], "scope": label.get("scope", "us_unspecified"),
                      "tone": label["tone"], "persistence": label["persistence"], "label_method": "existing_manual"},
        })
    from ..fox_news_archive import window_for_month
    window_start, as_of = window_for_month(root, month)
    return {"schema": "sce_fox_existing_candidates/v1", "month": month,
            "window_start": window_start, "as_of": as_of,
            "funnel": {"imported_fox_only": len(candidates), "excluded_sce_report": 1},
            "candidate_count": len(candidates), "candidates": candidates}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = prepare_fox_labels(args.out)
    print(json.dumps({key: result[key] for key in ("unique_articles_to_label", "batches", "total_usd_reservation_no_retries", "proposed_budget_usd")}))


if __name__ == "__main__":
    main()
