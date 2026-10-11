"""Missing remains missing; finite scores and valid records are unchanged."""
import math
from studies.sce_inflation_expectations.confidence_analysis_export import json_missing


def test_missing_values_become_null_without_touching_finite_numbers():
    source = {'real': math.nan, 'weight': 1.25, 'bins': [0, 100., None], 'flag': True,
              'nested': {'mean': 3.5, 'infinite_missing': math.inf}}
    assert json_missing(source) == {'real': None, 'weight': 1.25, 'bins': [0, 100., None],
                                    'flag': True, 'nested': {'mean': 3.5, 'infinite_missing': None}}
    assert math.isnan(source['real'])
