"""Independent date/identity boundary checks for new-period source preparation."""
import json

import pytest

from studies.sce_inflation_expectations.coverage_preparation import (
    build_news_pool, latest_wave, national_confidence,
)


def test_latest_wave_excludes_survey_not_yet_published():
    waves = [
        {"wave_id": "old", "published_date": "2021-04-26"},
        {"wave_id": "new", "published_date": "2022-05-02"},
    ]
    # A new wave's fieldwork can have finished, while public results are absent.
    assert latest_wave(waves, "2022-04-30T23:59:59-04:00")["wave_id"] == "old"
    assert latest_wave(waves, "2022-05-02T12:00:00-04:00")["wave_id"] == "old"
    assert latest_wave(waves, "2022-09-13T23:59:59-04:00")["wave_id"] == "new"


def test_news_uses_ny_instant_and_keeps_later_event_coverage(tmp_path):
    folder = tmp_path / "data/raw/nyt_archive"
    folder.mkdir(parents=True)
    def article(identity, stamp):
        return {"_id": identity, "document_type": "article", "pub_date": stamp,
                "headline": {"main": "Same event covered again"}, "abstract": "Same summary"}
    # 02:30 UTC next day is 22:30 NY on cutoff date and is still admissible.
    docs = [article("a", "2022-09-14T02:30:00Z"),
            article("b", "2022-09-14T04:01:00Z"),
            article("c", "2022-09-12T12:00:00Z"),
            article("unknown", "2022-09-12")]
    (folder / "2022-08.json").write_text(json.dumps({"response": {"docs": []}}))
    (folder / "2022-09.json").write_text(json.dumps({"response": {"docs": docs}}))
    class Rules:
        def classify(self, doc):
            return []
    rows, counts, _ = build_news_pool(tmp_path, "2022-09", "2022-09-13T23:59:59-04:00", Rules())
    assert {r["canonical_source_id"] for r in rows} == {"a", "c"}
    assert counts["unknown_publication_time_quarantined"] == 1


def test_confidence_unknown_does_not_invent_a_belief_and_invalid_probabilities_fail():
    from studies.sce_inflation_expectations.belief_trial_preparation import confidence_block
    # Entire source mass in no-opinion: no fabricated political view is inserted.
    label = national_confidence("person", 42, {"national_source_percent": [0, 0, 0, 0, 100]})
    assert confidence_block(label) == ""
    with pytest.raises(ValueError):
        national_confidence("person", 42, {"national_source_percent": [float("nan"), 20, 20, 20, 20]})
