import pytest

from studies.sce_inflation_expectations.evaluation.anchor_direction import older_center, alignment


def test_remove_last_answer_from_frozen_historical_mean():
    # [2, 4, 12] mean 6: older-only center is 3, not 6 or last answer 12.
    assert older_center(6., 3, 12.) == 3.
    assert older_center(None, 1, 12.) is None


def test_disagreeing_anchors_separate_opposite_updates_and_boundary():
    # Previous 5, own older center 8, common signal 2: disjoint directions.
    assert alignment(5., 7., 8., 2.)['label'] == 'personal_direction'
    assert alignment(5., 3., 8., 2.)['label'] == 'common_direction'
    assert alignment(5., 5.5, 8., 2.)['label'] == 'stable'
    # Matching directions cannot distinguish the two accounts.
    assert alignment(5., 7., 8., 9.)['label'] == 'not_identifiable'


def test_pointing_towards_anchor_does_not_guarantee_ending_closer():
    # Overshooting own center 8 from previous 5 to 12 increases distance.
    value = alignment(5., 12., 8., 2.)
    assert value['label'] == 'personal_direction'
    assert value['personal_distance_change_pp'] == pytest.approx(1.)
