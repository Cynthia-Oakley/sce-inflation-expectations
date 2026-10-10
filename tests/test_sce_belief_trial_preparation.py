import json
from collections import Counter
from pathlib import Path

import pytest

from studies.sce_inflation_expectations.belief_trial_preparation import (
    MARKER, assign_confidence, augment_messages, audit_news,
    confidence_block, shuffled_labels, validate_distribution,
)


def distribution():
    root = Path(__file__).resolve().parents[1]
    return json.loads((root / "docs/literature/sce/belief_proxies/fed_confidence_candidate_2021.json").read_text())


def test_rounding_is_explicit_and_not_recalibrated():
    data = distribution()
    validate_distribution(data)
    assert data["education_tables"]["college_graduate"]["source_sum"] == 99
    assert data["education_tables"]["college_graduate"]["candidate_probabilities"][0] == pytest.approx(18 / 99)
    data["education_tables"]["college_graduate"]["candidate_probabilities"][0] = 0.3
    with pytest.raises(ValueError):
        validate_distribution(data)
    data = distribution()
    data["education_tables"]["college_graduate"]["source_percent"][0] = -18
    with pytest.raises(ValueError):
        validate_distribution(data)


def test_unknowns_and_derived_answers_are_not_inferred():
    data = distribution()
    assert assign_confidence({}, "one", 42, data) is None
    assert confidence_block("dont_know_or_refused") == ""
    with pytest.raises(ValueError):
        assign_confidence({"education_group": "college", "Q9_mean": 6}, "one", 42, data)
    assert assign_confidence({"education_group": "college"}, "one", 42, data) == assign_confidence({"education_group": "college"}, "one", 42, data)


def test_only_the_confidence_sentence_changes():
    text = "Public CPI: +4.2% year-over-year, +0.8% month-over-month.\n" + MARKER + " Future 12 months.\nQuestion 2: probabilities."
    base = [{"role": "user", "content": text}]
    messages = augment_messages(base, "almost_none")
    assert messages[0]["content"].replace(confidence_block("almost_none"), "", 1) == text
    assert messages[0]["content"].split(MARKER, 1)[1] == base[0]["content"].split(MARKER, 1)[1]
    assert "lower inflation" not in messages[0]["content"]
    assert augment_messages(base, "dont_know_or_refused") == base
    with pytest.raises(ValueError):
        augment_messages([{"role": "user", "content": "Q9_mean=6\n" + text}], None)


def test_permutation_preserves_counts_and_does_not_claim_everyone_mismatched():
    labels = {"a": "fair_amount", "b": "fair_amount", "c": "almost_none", "d": "dont_know_or_refused"}
    permutation = shuffled_labels(labels, 100042, "month")
    assert Counter(labels.values()) == Counter(permutation.values())
    assert shuffled_labels(labels, 100042, "month") == permutation


def test_news_detects_real_lexical_failure_without_deleting_articles():
    events = [{"event_id": "a", "pub_date": "2021-06-05", "web_url": "https://example.com/a",
               "headline": "U.S. Waged Secret Legal Battle to Obtain Emails of 4 Times Reporters",
               "abstract": "A legal battle.", "matched_keywords": ["wage"]},
              {"event_id": "b", "pub_date": "2021-06-03", "web_url": "https://example.com/b",
               "headline": "Wage Growth Is Holding Up", "abstract": "Wages increased.", "matched_keywords": ["wage"]}]
    audit = audit_news(events, "2021-06-10T23:59:59-04:00")
    assert audit["event_count"] == 2
    assert audit["events"][0]["flags"] == ["lexical_false_positive_wage_matches_waged"]
    assert audit["events"][1]["flags"] == []
    with pytest.raises(ValueError):
        audit_news(events, "2021-06-04T23:59:59-04:00")


def test_related_titles_are_only_duplicate_candidates():
    common = {"pub_date": "2021-05-07", "web_url": "https://example.com/a", "abstract": "", "matched_keywords": []}
    events = [dict(common, event_id="a", headline="Biden and Republicans Spar Over Unemployment as Job Gains Disappoint"),
              dict(common, event_id="b", headline="Biden and Republicans spar over unemployment as the jobs report disappoints.")]
    audit = audit_news(events, "2021-05-12T23:59:59-04:00")
    assert audit["event_count"] == 2
    assert len(audit["candidate_duplicate_pairs"]) == 1
    assert audit["candidate_duplicate_pairs"][0]["status"] == "candidate_duplicate_not_deduplicated"
