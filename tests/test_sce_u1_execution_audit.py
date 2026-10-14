import pytest

from studies.sce_inflation_expectations.evaluation.u1_execution_audit import response_values


def test_raw_dictionary_bin_order_is_questionnaire_order():
    # Dict iteration order must not silently reverse inflation/deflation bins.
    q9 = {f"bin{i}": 100 if i == 4 else 0 for i in reversed(range(1, 11))}
    point, bins = response_values({"point_pct": 3.5, "q9": q9})
    assert point == 3.5
    assert bins == [0, 0, 0, 100, 0, 0, 0, 0, 0, 0]


@pytest.mark.parametrize("reply", [
    {"point_pct": 3.5, "q9": [0, 0, 0, 99, 0, 0, 0, 0, 0, 0]},
    {"point_pct": 3.5, "q9": [-1, 101] + [0]*8},
    {"point_pct": float('nan'), "q9": [0, 0, 0, 100, 0, 0, 0, 0, 0, 0]},
])
def test_raw_bad_answers_are_rejected_not_normalized_or_filled(reply):
    with pytest.raises(ValueError, match="legal"):
        response_values(reply)
