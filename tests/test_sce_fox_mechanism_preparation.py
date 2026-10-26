from pathlib import Path

from studies.sce_inflation_expectations.experiments.fox_mechanism_preparation import load_fox_pool
from studies.sce_inflation_expectations.news_exposure import NEWS_KEYS


def test_existing_fox_pool_is_fox_only_sce_free_and_has_manual_mechanism_labels():
    root = Path(__file__).resolve().parents[1]
    for month, expected in ((202106, 26), (202206, 21)):
        rows = load_fox_pool(root, month, {})
        assert len(rows) == expected
        assert all(set(row) == set(NEWS_KEYS) for row in rows)
        assert all(row["semantic_label"]["source"].startswith("Fox") for row in rows)
        assert all(row["semantic_label"]["tone"] in {"alarming", "reassuring", "neutral", "mixed"} for row in rows)
        assert all(row["semantic_label"]["persistence"] for row in rows)
        assert all("expectation-inflation-worst-2013" not in row["web_url"] for row in rows)


def test_existing_candidate_payload_supports_wayback_without_changing_manual_labels():
    from studies.sce_inflation_expectations.experiments.fox_mechanism_preparation import existing_candidate_payload

    root = Path(__file__).resolve().parents[1]
    payload = existing_candidate_payload(root, 202106)
    assert payload["candidate_count"] == 26
    assert len(payload["candidates"]) == 26
    assert all(row["wayback"]["status"] == "unverified" for row in payload["candidates"])
    assert all(row["label"]["tone"] for row in payload["candidates"])
    assert all(row["label"]["persistence"] for row in payload["candidates"])


def test_english_text_replaces_manual_chinese_summary_but_preserves_labels():
    from studies.sce_inflation_expectations.experiments.fox_mechanism_preparation import apply_english_text

    root = Path(__file__).resolve().parents[1]
    row = load_fox_pool(root, 202106, {})[0]
    updated = apply_english_text(row, {"title": "English title", "excerpt": "English lead", "observed_at": "2026-10-25"})
    assert updated["headline"] == "English title"
    assert updated["abstract"] == "English lead"
    assert updated["text_sha256"] != row["text_sha256"]
    assert updated["semantic_label"] == row["semantic_label"]
    assert updated["text_vintage_status"].startswith("live_english_page_2026-10-25")


def test_fox_label_review_can_exclude_false_positive_without_mutating_raw():
    from studies.sce_inflation_expectations.experiments.fox_mechanism_preparation import apply_fox_label_overrides

    raw = {"a": {"article_id": "a", "decision": "keep", "topics": ["living_prices"],
                 "scope": "us_national", "tone": "alarming", "persistence": "persistent"}}
    reviewed = apply_fox_label_overrides(raw, {"a": {"decision": "exclude", "tone": "neutral", "persistence": "undetermined"}})
    assert reviewed["a"]["decision"] == "exclude"
    assert reviewed["a"]["tone"] == "neutral"
    assert reviewed["a"]["persistence"] == "undetermined"
    assert raw["a"]["decision"] == "keep"
