import json

from studies.sce_inflation_expectations.output_format_example import (
    append_format_example, structure_example,
)


def test_complete_nested_shape_and_no_probability_values():
    example = structure_example()
    # Test only syntax and field nesting after substituting placeholders; this
    # all-zero object is never included in a model prompt or used as an answer.
    shape = json.loads(example.replace("<signed_number>", "0").replace("<probability>", "0"))
    assert set(shape) == {"point_pct", "q9", "reason"}
    assert list(shape["q9"]) == [f"bin{i}" for i in range(1, 11)]
    assert example.count("<probability>") == 10
    assert "..." not in example
    assert ": 0" not in example
    assert "q9.bin1" not in example


def test_q9_only_shape_does_not_request_q8_or_reason():
    example = structure_example(include_point=False, include_reason=False)
    shape = json.loads(example.replace("<probability>", "0"))
    assert set(shape) == {"q9"}
    assert len(shape["q9"]) == 10


def test_appending_preserves_all_original_messages_and_content():
    original = [{"role": "system", "content": "existing instruction"},
                {"role": "user", "content": "existing P/E, prior and questionnaire"}]
    out = append_format_example(original)
    assert original[-1]["content"] == "existing P/E, prior and questionnaire"
    assert out[0] == original[0]
    assert out[-1]["content"].startswith(original[-1]["content"] + "\n\n")
    assert '<probability>' in out[-1]["content"]
