import json
from collections import Counter
from pathlib import Path
import tempfile

import pytest

from studies.sce_inflation_expectations.experiments.media_mechanism_v3_preparation import (
    apply_label_overrides,
    load_supplemental_run,
)


def test_supplemental_run_requires_complete_unique_labels(tmp_path):
    (tmp_path / "state.json").write_text(json.dumps({"status": "completed", "articles_valid": 1}))
    (tmp_path / "labels.jsonl").write_text(json.dumps({"batch_id": 1, "label": {
        "article_id": "a", "tone": "alarming", "persistence": "uncertain"}}) + "\n")
    labels = load_supplemental_run(tmp_path)
    assert labels["a"] == {"tone": "alarming", "persistence": "uncertain"}


def test_supplemental_run_rejects_incomplete_or_duplicate(tmp_path):
    (tmp_path / "state.json").write_text(json.dumps({"status": "stopped_on_error"}))
    with pytest.raises(ValueError, match="complete"):
        load_supplemental_run(tmp_path)
    (tmp_path / "state.json").write_text(json.dumps({"status": "completed", "articles_valid": 2}))
    row = json.dumps({"label": {"article_id": "a", "tone": "neutral", "persistence": "undetermined"}})
    (tmp_path / "labels.jsonl").write_text(row + "\n" + row + "\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_supplemental_run(tmp_path)


def test_month_assembly_uses_four_tiers_and_news_only_changes():
    from studies.sce_inflation_expectations.experiments import media_mechanism_trial as old
    from studies.sce_inflation_expectations.experiments import media_mechanism_v3 as v3
    from studies.sce_inflation_expectations.experiments.media_mechanism_v3_preparation import build_month_prompts

    root = Path(__file__).resolve().parents[1]
    base_dir = root / old.ASSEMBLY / "202106"
    base = {name: json.loads((base_dir / f"{name}.json").read_text()) for name in (
        "initial_previews_private", "timing_context_private", "initial_states_private",
        "news_quantity_frame_private", "baskets_private", "population", "environment")}
    ids = old.roster(list(base["initial_previews_private"]), 4)
    rows = []
    for index in range(40):
        row = old.synthetic_news(f"nyt-{index:02d}", f"Inflation rises in report {index}")
        row["pub_date"] = "2021-06-10T12:00:00-04:00" if index < 3 else "2021-06-01T12:00:00-04:00"
        row["semantic_label"] = {"decision": "keep", "topics": ["living_prices"], "scope": "us_national",
                                 "tone": "alarming" if index % 2 else "neutral", "persistence": "uncertain"}
        if index < 3:
            row.update(placement="a1", print_section="A", print_page="1")
        rows.append(row)
    fox = []
    for index in range(10):
        row = old.synthetic_news(f"fox-{index:02d}", f"Inflation Fox report {index}")
        row["semantic_label"] = {"decision": "keep", "topics": ["living_prices"], "scope": "us_national",
                                 "tone": "alarming", "persistence": "persistent", "source": "Fox Business"}
        fox.append(row)
    prompts, contexts, receipt = build_month_prompts(202106, ids, rows, fox, base, "2021-06-10")
    assert set(prompts) == set(v3.ARMS)
    assert all(set(prompts[arm]) == set(ids) for arm in v3.ARMS)
    expected_tiers = v3.four_tier_levels(ids, 202106)
    for arm in ("Q0", "Q1", "Q2", "Q3"):
        for aid in ids:
            assert contexts[arm][aid]["news_count"] == expected_tiers[aid]
            assert len(contexts[arm][aid]["article_ids"]) == expected_tiers[aid] - 3
    assert Counter(contexts["Q2"][aid]["sources"].count("Fox Business") for aid in ids) == Counter(
        v3.external_count(expected_tiers[aid] - 3) for aid in ids)
    assert len(receipt["common_news"]) == 3
    assert all(contexts["Q1"][aid]["alarming_boost"] == 2.0 for aid in ids)


def test_label_overrides_are_validated_and_do_not_mutate_raw_labels():
    raw = {"a": {"tone": "alarming", "persistence": "persistent"}}
    reviewed = apply_label_overrides(raw, {"a": {"tone": "neutral"}})
    assert reviewed["a"] == {"tone": "neutral", "persistence": "persistent"}
    assert raw["a"]["tone"] == "alarming"
    with pytest.raises(ValueError, match="unknown article"):
        apply_label_overrides(raw, {"missing": {"tone": "neutral"}})
    with pytest.raises(ValueError, match="enum"):
        apply_label_overrides(raw, {"a": {"tone": "negative"}})


def test_full_seven_month_prepare_attach_and_verify_with_engineering_fox():
    from studies.sce_inflation_expectations.evaluation.media_mechanism_v3 import attach_evaluation
    from studies.sce_inflation_expectations.experiments import media_mechanism_trial as old
    from studies.sce_inflation_expectations.experiments.frozen_batch import verify, worker
    from studies.sce_inflation_expectations.experiments.media_mechanism_v3 import MONTHS
    from studies.sce_inflation_expectations.experiments.media_mechanism_v3_preparation import audit_preparation, prepare

    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(dir=root / "outputs") as directory:
        workspace = Path(directory)
        fox_labels = workspace / "fox_labels"
        fox_labels.mkdir()
        (fox_labels / "state.json").write_text("{}")
        (fox_labels / "labels.jsonl").write_text("")
        fox_by_month = {}
        fox_candidate_paths = {}
        for month in MONTHS:
            fox_candidate_paths[month] = workspace / f"fox-{month}.json"
            fox_candidate_paths[month].write_text("{}")
            env = json.loads((root / old.ASSEMBLY / str(month) / "environment.json").read_text())
            published = env["provider_args"]["targets"][0]["as_of"][:10] + "T00:00:00-04:00"
            rows = []
            for index in range(40):
                row = old.synthetic_news(f"engineering-fox-{month}-{index}", f"Inflation engineering {index}")
                row["pub_date"] = published
                row["text_vintage_status"] = "synthetic_engineering_only"
                row["semantic_label"] = {"decision": "keep", "topics": ["living_prices"], "scope": "us_national",
                    "tone": "neutral", "persistence": "undetermined", "source": "Fox Business", "article_type": "news"}
                rows.append(row)
            fox_by_month[month] = rows
        package = workspace / "package"
        manifest = prepare(package, fox_by_month, fox_labels_dir=fox_labels, fox_candidate_paths=fox_candidate_paths)
        assert manifest["planned_calls"] == 6720
        assert len(manifest["jobs"]) == 70
        result = attach_evaluation(package, root / "outputs/sce_monthly_main_six_repair_20261024_v1/evaluation/cases_private.json")
        assert result["evaluation_links"] == 672
        assert result["a82_original_rows"] == 672
        verified_manifest, protocol = verify(package)
        assert protocol["mechanism"] == "v32_news_mechanism_v3"
        assert len(verified_manifest["jobs"]) == 70
        acceptance = audit_preparation(package)
        assert acceptance["status"] == "offline_acceptance_passed"
        assert acceptance["prompt_positions"] == 3360
        assert acceptance["physical_call_cap"] == 6720
        audit = root / "outputs/local_runs" / (verified_manifest["jobs"][0]["run_id"] + "-engineering")
        try:
            worker(package, 0, True)
            receipt = json.loads((audit / "run_manifest.json").read_text())
            assert receipt["status"] == "completed"
            assert receipt["llm_kind"] == "scripted"
            assert receipt["actual_input_hashes_match"] is True
            assert receipt["cost"]["call_count"] == 0
        finally:
            import shutil
            if audit.exists():
                shutil.rmtree(audit)
