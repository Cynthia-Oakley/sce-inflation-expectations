"""Portable input entry checks, without credentials, network or paid requests."""
import gzip
import hashlib
import importlib.util
import json
import pytest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "studies/sce_inflation_expectations/simulation/reviewer_request.py"
DATA = ROOT / "studies/sce_inflation_expectations/reproduction_data/inputs"
pytestmark = pytest.mark.skipif(not ENTRY.exists(), reason="Only exercised in the independently extracted study package")


def entry_module():
    spec = importlib.util.spec_from_file_location("reviewer_entry_test", ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preview_is_offline_and_uses_exact_archived_input():
    module = entry_module()
    with patch("os.environ.get", side_effect=AssertionError("Preview must not read credentials")):
        result = module.run(DATA)
    assert result["status"] == "offline_input_preview"
    assert result["new_API_calls"] == 0
    assert result["credentials_read"] is False
    assert hashlib.sha256(json.dumps(result["messages"], ensure_ascii=False).encode()).hexdigest() == result["original_prompt_sha256"]


def test_complete_sample_can_be_selected_without_model_call():
    module = entry_module()
    sample = json.loads((DATA / "one_complete_prompt_example.json").read_text())
    selected, _, _ = module.load(DATA, **{k: sample[k] for k in ("run", "period", "household")})
    assert selected["messages"] == sample["messages"]


def test_input_manifest_and_news_distribution_scope():
    m = json.loads((DATA / "manifest.json").read_text())
    assert m["publisher_news_text_included"] is True
    assert m["real_person_linked_date_values_written"] is m.get("public_survey_derived_dates_retained", False)
    assert m["identity_map_included"] is False
    assert m["distribution_scope"] == "confidential_competition_review_only_not_for_public_GitHub"
    for name, info in m["files"].items():
        p = DATA / name
        assert p.stat().st_size == info["bytes"]
        assert hashlib.sha256(p.read_bytes()).hexdigest() == info["sha256"]


def test_complete_collection_is_exact_and_all_inputs_join_archived_replies():
    m = json.loads((DATA / "manifest.json").read_text())
    acceptance = json.loads((DATA / "acceptance.json").read_text())
    assert acceptance["archived_output_joins"] == m["template_rows"] == 66822
    count = 0
    with gzip.open(DATA / "complete_prompts.jsonl.gz", "rt") as stream:
        for line in stream:
            r = json.loads(line)
            assert r["run"] in (("A", "B", "monthly", "weekly") if m.get("public_survey_derived_dates_retained") else ("B", "monthly", "weekly"))
            assert r["withheld"] == []
            assert r["original_prompt_sha256"] == r["delivered_prompt_sha256"]
            assert hashlib.sha256(json.dumps(r["messages"], ensure_ascii=False).encode()).hexdigest() == r["original_prompt_sha256"]
            count += 1
    assert count == (66822 if m.get("public_survey_derived_dates_retained") else 24852)


def test_public_date_A_input_is_directly_selectable_without_missing_fields():
    m = json.loads((DATA / "manifest.json").read_text())
    if not m.get("public_survey_derived_dates_retained"):
        pytest.skip("Earlier profile intentionally masks public survey-derived dates")
    with gzip.open(DATA / "complete_prompts.jsonl.gz", "rt") as stream:
        a = next(json.loads(line) for line in stream if json.loads(line)["run"] == "A")
    module = entry_module()
    with patch("os.environ.get", side_effect=AssertionError("No key needed for A preview")):
        result = module.run(DATA, selection={k: a[k] for k in ("run", "period", "household")})
    assert result["messages"] == a["messages"]
    assert result["original_prompt_sha256"] == a["original_prompt_sha256"]
    assert a["withheld"] == []
    assert "[[WITHHELD_" not in json.dumps(a["messages"])


def test_reviewer_can_list_A_sample_keys_without_API_credentials():
    module = entry_module()
    with patch("os.environ.get", side_effect=AssertionError("No key needed for listing")):
        listing = module.list_inputs(DATA, run="A", period="201901", limit=2)
    assert listing["new_API_calls"] == 0 and listing["credentials_read"] is False
    assert len(listing["samples"]) == 2
    assert all(x["run"] == "A" and x["period"] == "201901" for x in listing["samples"])
