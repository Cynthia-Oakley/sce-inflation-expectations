import json
from pathlib import Path

import pytest

from studies.sce_inflation_expectations.news_mechanism_labels import (
    MAX_TOKENS,
    PUBLIC_FIELDS,
    build_requests,
    validate_supplemental_labels,
)


def article(article_id="a1", headline="Inflation surges"):
    return {
        "article_id": article_id,
        "headline": headline,
        "abstract": "Prices rose sharply.",
        "snippet": "",
        "source": "NYT Archive API",
        "section_name": "Business Day",
        "news_desk": "Business",
    }


def test_request_builder_preserves_public_fields_and_conservative_budget():
    rows = build_requests([article(str(i)) for i in range(9)], batch_size=8)
    assert len(rows) == 2
    assert [row["batch_id"] for row in rows] == [1, 2]
    assert rows[0]["article_ids"] == [str(i) for i in range(8)]
    payload = rows[0]["payload"]
    assert payload["model"] == "deepseek-flash"
    assert payload["temperature"] == 0
    assert payload["max_tokens"] == MAX_TOKENS
    sent = json.loads(payload["messages"][1]["content"])["articles"]
    assert all(set(row) == set(PUBLIC_FIELDS) for row in sent)
    assert rows[0]["request_usd_reservation"] > 0
    assert rows[0]["input_token_reservation"] > 0


def test_request_builder_rejects_duplicate_ids_and_non_public_fields():
    with pytest.raises(ValueError, match="duplicate"):
        build_requests([article("same"), article("same")])
    with pytest.raises(ValueError, match="whitelist"):
        build_requests([dict(article(), answer=3)])


def test_supplemental_label_validation_accepts_exact_ids_and_enums():
    content = json.dumps({"labels": [
        {"article_id": "a1", "tone": "alarming", "persistence": "uncertain"}
    ]})
    assert validate_supplemental_labels(content, [article()]) == [
        {"article_id": "a1", "tone": "alarming", "persistence": "uncertain"}
    ]


def test_supplemental_label_validation_rejects_missing_extra_or_unknown_fields():
    with pytest.raises(ValueError, match="IDs"):
        validate_supplemental_labels('{"labels": []}', [article()])
    bad = {"labels": [{"article_id": "a1", "tone": "negative", "persistence": "uncertain"}]}
    with pytest.raises(ValueError, match="enum"):
        validate_supplemental_labels(json.dumps(bad), [article()])
    extra = {"labels": [{"article_id": "a1", "tone": "neutral", "persistence": "uncertain", "reason": "no"}]}
    with pytest.raises(ValueError, match="fields"):
        validate_supplemental_labels(json.dumps(extra), [article()])


def test_seven_month_nyt_keep_inventory_is_deduplicated_and_public_only():
    from studies.sce_inflation_expectations.news_mechanism_label_preparation import collect_nyt_articles

    root = Path(__file__).resolve().parents[1]
    articles, receipt = collect_nyt_articles(root)
    assert len(articles) == 1374
    assert len({row["article_id"] for row in articles}) == 1374
    assert all(set(row) == set(PUBLIC_FIELDS) for row in articles)
    assert receipt["unique_keep_articles"] == 1374
    assert sum(row["keep"] for row in receipt["months"]) == 1374


def test_public_label_package_can_be_reused_for_fox_without_nyt_content(tmp_path):
    from studies.sce_inflation_expectations.news_mechanism_label_preparation import prepare_public_articles

    source = tmp_path / "fox.json"
    source.write_text("[]")
    out = tmp_path / "outputs/fox_labels"
    summary = prepare_public_articles([article()], out, tmp_path, [source], "public Fox metadata only", "slim4_mechanism6")
    assert summary["unique_articles_to_label"] == 1
    assert summary["label_mode"] == "slim4_mechanism6"
    assert summary["data_scope"] == "public Fox metadata only"
    assert summary["new_api_calls"] == 0
    assert (out / "requests_prepared.jsonl").exists()
    assert summary["source_sha256"]["fox.json"]


def test_fox_label_mode_returns_slim4_and_mechanism_fields_without_legacy_text():
    from studies.sce_inflation_expectations.news_mechanism_labels import build_requests, validate_label_payload

    row = build_requests([article()], label_mode="slim4_mechanism6")[0]
    assert row["label_mode"] == "slim4_mechanism6"
    response = json.dumps({"labels": [{"article_id": "a1", "decision": "keep",
        "topics": ["living_prices"], "scope": "us_national",
        "tone": "alarming", "persistence": "uncertain"}]})
    labels = validate_label_payload(response, [article()], "slim4_mechanism6")
    assert set(labels[0]) == {"article_id", "decision", "topics", "scope", "tone", "persistence"}
    assert "reason_zh" not in labels[0] and "evidence_snippet" not in labels[0]


def test_fox_validator_accepts_id_indexed_json_without_changing_classifications():
    from studies.sce_inflation_expectations.news_mechanism_labels import validate_label_payload

    response = json.dumps({"a1": {"article_id": "a1", "decision": "keep",
        "topics": ["living_prices"], "scope": "us_national",
        "tone": "alarming", "persistence": "uncertain"}})
    labels = validate_label_payload(response, [article()], "slim4_mechanism6")
    assert labels == [{"article_id": "a1", "decision": "keep", "topics": ["living_prices"],
                       "scope": "us_national", "tone": "alarming", "persistence": "uncertain"}]


def test_fox_validator_accepts_articles_alias_without_other_changes():
    from studies.sce_inflation_expectations.news_mechanism_labels import validate_label_payload

    response = json.dumps({"articles": [{"article_id": "a1", "decision": "keep",
        "topics": ["living_prices"], "scope": "us_national",
        "tone": "neutral", "persistence": "undetermined"}]})
    labels = validate_label_payload(response, [article()], "slim4_mechanism6")
    assert labels[0]["article_id"] == "a1"
    assert labels[0]["tone"] == "neutral"
