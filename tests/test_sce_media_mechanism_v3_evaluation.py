import json
from pathlib import Path
import tempfile

import pytest

from studies.sce_inflation_expectations.evaluation.media_mechanism_v3 import attach_evaluation, evaluation_inputs, prior_groups


def case(month=202106, agent="a", repeat=1):
    return {"month": month, "agent_id": agent, "userid": 7, "profile": {"age": 40},
            "stratum": "s", "survey_weight": 2.0, "repeat": repeat,
            "real": {"q9_mean": 3.0}, "arms": {"monthly_reconstruction": {"mean": 2.5}}}


def test_evaluation_inputs_duplicate_only_truth_for_new_repeats_not_a82():
    links, truth, a82 = evaluation_inputs([case(), case(agent="b")], {"a", "b"}, [202106], [1, 2])
    assert len(links) == 2
    assert len(truth) == 4
    assert {(row["agent_id"], row["repeat"]) for row in truth} == {("a", 1), ("a", 2), ("b", 1), ("b", 2)}
    assert all(row["real"] == {"q9_mean": 3.0} for row in truth)
    assert len(a82) == 2
    assert all(row["repeat"] == 1 for row in a82)
    assert all(row["design_survey_weight"] == 2.0 for row in links)


def test_evaluation_inputs_require_complete_selected_support():
    with pytest.raises(ValueError, match="missing A82"):
        evaluation_inputs([case()], {"a", "b"}, [202106], [1, 2])


def test_attach_evaluation_preserves_prompt_bytes_and_a82_single_repeat():
    root = Path(__file__).resolve().parents[1]
    a82_path = root / "outputs/sce_monthly_main_six_repair_20261024_v1/evaluation/cases_private.json"
    a82 = json.loads(a82_path.read_text())
    selected = [row for row in a82 if row["month"] == 202106][:2]
    with tempfile.TemporaryDirectory(dir=root / "outputs") as directory:
        package = Path(directory)
        prompt_path = package / "202106/prompts_R0.json"
        prompt_path.parent.mkdir()
        prompt_path.write_text(json.dumps({"rows": {row["agent_id"]: {"messages": [], "prompt_sha256": "x"} for row in selected}}))
        before = prompt_path.read_bytes()
        (package / "protocol.json").write_text(json.dumps({
            "months": [202106], "arms": ["R0"], "generation_repeats": [1, 2],
            "budget_cap_usd": 1, "planned_calls": 4, "destination": "https://openrouter.ai/api/v1"}))
        (package / "manifest.json").write_text(json.dumps({
            "status": "prepared_requires_engine_checks_and_new_authorization", "source_sha256": {}}))
        result = attach_evaluation(package, a82_path)
        assert result["evaluation_links"] == 2
        assert result["truth_rows"] == 4
        assert result["a82_original_rows"] == 2
        assert prompt_path.read_bytes() == before
        reference = json.loads((package / "a82_reference_private.json").read_text())
        assert [row["repeat"] for row in reference] == [1, 1]
        manifest = json.loads((package / "manifest.json").read_text())
        assert manifest["source_sha256"][str((package / "evaluation_truth/cases_private.json").relative_to(root))]


def test_prior_groups_split_each_month_into_ordered_thirds():
    rows = []
    for index, value in enumerate((5.0, 1.0, 3.0, 2.0, 4.0, 0.0)):
        rows.append({"month": 202106, "agent_id": str(index), "repeat": 1,
                     "real": {"previous_q9_mean": value}})
    groups = prior_groups(rows, 202106)
    assert groups["5"] == "low"
    assert groups["0"] == "high"
    assert [groups[str(index)] for index in (5, 1, 3, 2, 4, 0)] == ["low", "low", "middle", "middle", "high", "high"]
