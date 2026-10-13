from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from studies.sce_inflation_expectations.evaluation.u1_preparation_audit import (
    BIN_FIELDS, GUIDANCE, QUESTION, independent_block, reconstruct_state,
    verify_messages,
)


def toy():
    rows = []
    for month, index in ((202101, 3), (202102, 4), (202103, 1)):
        probabilities = [0.] * 10
        probabilities[index] = 100.
        rows.append({"userid": 7, "date": month, **dict(zip(BIN_FIELDS, probabilities))})
    return pd.DataFrame(rows)


def assembled(base, state, guided):
    result = deepcopy(base)
    before, after = base[0]["content"].split(QUESTION, 1)
    result[0]["content"] = before + independent_block(state, guided) + QUESTION + after
    return result


def test_independent_state_reconstruction_ignores_current_and_derived_values():
    frame = toy()
    expected = reconstruct_state(frame, 7, 202103)
    assert expected["center"] == 1 and expected["anchor"] == 2
    changed = frame.copy()
    changed.loc[changed.date == 202103, BIN_FIELDS] = np.nan
    changed["Q9_mean"] = 999
    changed["weight"] = -1
    assert reconstruct_state(changed, 7, 202103) == expected


def test_whole_base_and_guidance_difference_checked():
    state = reconstruct_state(toy(), 7, 202103)
    base = [{"role": "user", "content": "Original E and raw prior JSON\n"+QUESTION+" Original questions"}]
    plain, guided = assembled(base, state, False), assembled(base, state, True)
    verdict = verify_messages(base, plain, guided, state)
    assert verdict["guidance_active"] and not verdict["same_message_without_anchor"]
    assert GUIDANCE not in plain[0]["content"] and GUIDANCE in guided[0]["content"]
    wrong = deepcopy(plain)
    wrong[0]["content"] = wrong[0]["content"].replace("Original E", "Changed E")
    with pytest.raises(ValueError, match="changed old inputs"):
        verify_messages(base, wrong, guided, state)


def test_no_anchor_means_identical_two_arm_inputs():
    state = reconstruct_state(toy(), 7, 202102)
    assert state["anchor"] is None
    base = [{"role": "user", "content": "Original raw prior\n"+QUESTION+"questions"}]
    plain, guided = assembled(base, state, False), assembled(base, state, True)
    assert verify_messages(base, plain, guided, state)["same_message_without_anchor"]
    assert GUIDANCE not in guided[0]["content"]
