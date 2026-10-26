"""Closed-form check of the proposed combined sampling weight."""
import pytest
from studies.sce_inflation_expectations.experiments.media_mechanism_v3 import selection_probabilities


def test_joint_score_is_three_but_probability_is_mixed_and_normalized():
    rows=[{'headline':'Inflation rises','routing_tags':[],
           'semantic_label':{'tone':'alarming','topics':['living_prices']}},
          {'headline':'Local economy update','routing_tags':[],
           'semantic_label':{'tone':'alarming','topics':[]}},
          {'headline':'Local economy update','routing_tags':[],
           'semantic_label':{'tone':'neutral','topics':[]}}]
    result=selection_probabilities(rows,frozenset(),alarming_boost=2.,cpi_boost=1.5)
    # Scores 3:2:1, with half of exposure uniform: 1/6 + score/12.
    assert result==pytest.approx([5/12,1/3,1/4])
    assert sum(result)==pytest.approx(1.)
    assert result[0] != pytest.approx(3*(1/3))
