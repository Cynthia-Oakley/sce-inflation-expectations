from collections import Counter

import pytest

from studies.sce_inflation_expectations.experiments import media_mechanism_v3 as v3
from studies.sce_inflation_expectations.experiments.media_mechanism_trial import synthetic_news


def test_four_tiers_are_balanced_and_have_personal_news():
    ids = [f"agent-{index:02d}" for index in range(96)]
    levels = v3.four_tier_levels(ids, 202106)
    assert Counter(levels.values()) == {4: 24, 8: 24, 16: 24, 32: 24}
    assert all(levels[aid] - 3 == personal for aid, personal in zip(ids, [levels[aid] - 3 for aid in ids]))
    assert min(levels.values()) == 4
    assert levels == v3.four_tier_levels(ids, 202106)
    assert levels != v3.four_tier_levels(ids, 202109)


def test_q1_uses_formal_tone_and_q3_has_separate_cpi_boost():
    alarming = dict(synthetic_news("a", "Local economy update"),
                    semantic_label={"decision": "keep", "tone": "alarming", "topics": []})
    direct = dict(synthetic_news("b", "Inflation rises"),
                  semantic_label={"decision": "keep", "tone": "neutral", "topics": ["living_prices"]})
    plain = dict(synthetic_news("c", "Local economy update"),
                 semantic_label={"decision": "keep", "tone": "neutral", "topics": []})
    rows = [alarming, direct, plain]
    q0 = v3.selection_probabilities(rows, frozenset())
    q1 = v3.selection_probabilities(rows, frozenset(), alarming_boost=2.0)
    q3 = v3.selection_probabilities(rows, frozenset(), cpi_boost=1.5)
    assert q1[0] > q0[0]
    assert q1[1] < q0[1]
    assert q3[1] > q0[1]
    assert q3[0] < q0[0]
    assert sum(q1) == pytest.approx(1.0)
    assert sum(q3) == pytest.approx(1.0)


def test_cpi_direct_requires_headline_and_relevant_topic():
    row = dict(synthetic_news("a", "Inflation rises"),
               semantic_label={"decision": "keep", "topics": ["other_economic"]})
    assert not v3.is_cpi_direct(row)
    row["semantic_label"]["topics"] = ["economic_outlook"]
    assert v3.is_cpi_direct(row)


def test_fox_quota_uses_personal_capacity():
    assert [v3.external_count(count) for count in (1, 5, 13, 29)] == [0, 1, 3, 7]


def test_arm_registry_freezes_registered_comparisons():
    assert v3.ARMS == ("R0", "Q0", "Q1", "Q2", "Q3")
    assert v3.ARM_CONFIG["Q0"] == {"alarming_boost": 1.0, "cpi_boost": 1.0, "fox_share": 0.0, "four_tiers": True}
    assert v3.ARM_CONFIG["R0"]["four_tiers"] is False
    assert v3.ARM_CONFIG["Q1"]["alarming_boost"] == 2.0
    assert v3.ARM_CONFIG["Q2"]["fox_share"] == 0.25
    assert v3.ARM_CONFIG["Q3"]["cpi_boost"] == 1.5


def test_supplemental_labels_are_required_and_preserve_base_schema():
    rows = [dict(synthetic_news("a", "H"), semantic_label={"decision": "keep", "topics": [], "scope": "us_national"})]
    supplemented = v3.merge_supplemental_labels(rows, {"a": {"tone": "alarming", "persistence": "uncertain"}})
    assert supplemented[0]["semantic_label"]["tone"] == "alarming"
    assert supplemented[0]["semantic_label"]["persistence"] == "uncertain"
    assert supplemented[0]["semantic_label"]["scope"] == "us_national"
    with pytest.raises(ValueError, match="missing supplemental"):
        v3.merge_supplemental_labels(rows, {})


def test_transport_has_distinct_registered_v32_adapter():
    from studies.sce_inflation_expectations.experiments.model_comparison import validate_v32_transport

    protocol = {
        "mechanism": "v32_news_mechanism_v3", "transport": "openrouter_locked",
        "destination": "https://openrouter.ai/api/v1", "model": "deepseek/deepseek-v3.2",
        "route": "siliconflow/fp8", "expected_provider": "SiliconFlow", "thinking": "disabled",
        "price_input_per_mtok": 0.259, "price_output_per_mtok": 0.8,
        "request_extra_body": {"provider": {"order": ["siliconflow/fp8"], "allow_fallbacks": False,
            "require_parameters": True, "max_price": {"prompt": 0.259, "completion": 0.8}},
            "reasoning": {"enabled": False}},
    }
    validate_v32_transport(protocol)
    assert protocol["mechanism"] != "v32_news_matching"
