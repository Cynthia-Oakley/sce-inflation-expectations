"""Tests for the U1 explicit personal-state preparation (spec v2)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from studies.sce_inflation_expectations.belief_state_preparation import (
    MIN_HISTORY,
    STATE_MARKER,
    add_state_block,
    compute_person_state,
    render_state_block,
)
from studies.sce_inflation_expectations.scoring.sce_q9_frozen import score_q9_frozen

MARKER = "Question 1 (point estimate):"
PRIOR_MARKER = "Your earlier survey response"


def toy_frame() -> pd.DataFrame:
    # Person 7 answers four months; moderate right-skewed ten-bin beliefs.
    bins = [0, 5, 20, 30, 25, 10, 5, 3, 1, 1]
    rows = []
    for k, date in enumerate((202101, 202102, 202103, 202104)):
        shift = [min(100, v + 2 * k) if i in (2, 3) else v for i, v in enumerate(bins)]
        shift = [v + (100 - sum(shift)) if i == 4 else v for i, v in enumerate(shift)]
        rows.append({"userid": 7, "date": date,
                     **{f"Q9_bin{i}": float(shift[i - 1]) for i in range(1, 11)}})
    return pd.DataFrame(rows)


def test_state_components_match_scorer():
    frame = toy_frame()
    state = compute_person_state(frame, 7, 202104)
    prev_bins = [float(frame.loc[frame.date.eq(202103), f"Q9_bin{i}"].iloc[0]) for i in range(1, 11)]
    scored = score_q9_frozen(prev_bins)
    assert state["source_month"] == 202103
    assert state["center"] == pytest.approx(scored.mean)
    assert state["low"] == pytest.approx(scored.p25)
    assert state["high"] == pytest.approx(scored.p75)
    assert state["n_earlier_valid"] == 3
    expected_anchor = float(np.mean([
        score_q9_frozen([float(r[f"Q9_bin{i}"]) for i in range(1, 11)]).mean
        for _, r in frame.iterrows() if r["date"] < 202104]))
    assert state["anchor"] == pytest.approx(expected_anchor)


def test_state_has_no_lookahead():
    frame = toy_frame()
    before = compute_person_state(frame, 7, 202104)
    perturbed = frame.copy()
    i = perturbed.index[perturbed["date"] == 202104][0]
    perturbed.loc[i, [f"Q9_bin{k}" for k in range(1, 11)]] = [100.0] + [0.0] * 9
    after = compute_person_state(perturbed, 7, 202104)
    assert before == after


def test_anchor_omitted_below_min_history():
    frame = toy_frame()
    state = compute_person_state(frame, 7, 202102)  # only the t-1 answer exists
    assert state["anchor"] is None and state["n_earlier_valid"] == 1
    assert MIN_HISTORY == 2
    block = render_state_block(state, 202102)
    assert "typically been around" not in block
    with pytest.raises(ValueError):  # the hypothesis sentence requires an anchor
        render_state_block(state, 202102, guidance=True)


def test_render_block_wording_v2():
    state = compute_person_state(toy_frame(), 7, 202104)
    block = render_state_block(state, 202104)
    assert block.startswith(STATE_MARKER)
    assert "Last survey (2021-03)" in block
    assert "probability answers implied an average expectation of about" in block
    assert "about a 50% chance of inflation between" in block
    assert "most likely between" not in block  # v1 wording removed
    assert "your central expectation was" not in block  # Q8/Q9 conflation removed
    assert "past 3 surveys" in block
    assert "roughly halfway" not in block  # state-only arm carries no guidance
    assert block.endswith("\n\n")


def test_render_guidance_is_hypothesis_and_optional():
    state = compute_person_state(toy_frame(), 7, 202104)
    guided = render_state_block(state, 202104, guidance=True)
    assert "One hypothesis about how people usually update" in guided
    assert "a possibility rather than a rule" in guided
    assert "roughly halfway" in guided
    plain = render_state_block(state, 202104, guidance=False)
    assert guided.startswith(plain.rstrip("\n"))  # guidance is appended after the state lines


def test_render_rejects_wrong_month_or_bad_values():
    state = compute_person_state(toy_frame(), 7, 202104)
    with pytest.raises(ValueError):
        render_state_block(state, 202105)
    bad = dict(state, low=5.0, high=2.0)
    with pytest.raises(ValueError):
        render_state_block(bad, 202104)


def toy_messages():
    prior = (f"{PRIOR_MARKER} (2021-03):\n"
             "In that survey, you reported beliefs about the 12 months following that earlier survey.\n"
             '{"point_pct": 3.0, "q9": {"bin1": 0.0}}\n'
             "These were your reported expectations, not measured inflation.\n\n")
    return [{"role": "user", "content": f"You are a U.S. household head.\n\n{prior}{MARKER} rest of questionnaire"}]


def test_add_state_block_keeps_raw_prior_and_questionnaire():
    state = compute_person_state(toy_frame(), 7, 202104)
    base = toy_messages()
    messages, block = add_state_block(base, state, 202104)
    assert messages[0]["content"].replace(block, "", 1) == base[0]["content"]
    assert messages[0]["content"].split(MARKER, 1)[1] == base[0]["content"].split(MARKER, 1)[1]
    assert STATE_MARKER in messages[0]["content"] and STATE_MARKER not in base[0]["content"]
    assert PRIOR_MARKER in messages[0]["content"]  # raw Q8 point + Q9 JSON preserved


def test_add_state_block_rejects_duplicate_or_missing_prior():
    state = compute_person_state(toy_frame(), 7, 202104)
    messages, _ = add_state_block(toy_messages(), state, 202104)
    with pytest.raises(ValueError):
        add_state_block(messages, state, 202104)
    no_prior = [{"role": "user", "content": f"You are a U.S. household head.\n\n{MARKER} q"}]
    with pytest.raises(ValueError):
        add_state_block(no_prior, state, 202104)
