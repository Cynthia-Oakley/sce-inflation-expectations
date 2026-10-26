from pathlib import Path
import importlib.util
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OFFICIAL = ROOT.parent / 'socioverse2_repo'
if str(OFFICIAL) not in sys.path:
    sys.path.append(str(OFFICIAL))
import studies
studies.__path__ = [str(ROOT / 'studies'), *studies.__path__]

# These math-only unit tests do not need package registration against the
# official engine. Some developer Conda environments omit its DuckDB runtime.
if importlib.util.find_spec('duckdb') is None:
    import types
    package_name = 'studies.sce_inflation_expectations'
    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT / 'studies/sce_inflation_expectations')]
    sys.modules[package_name] = package
    evaluation_name = package_name + '.evaluation'
    evaluation = types.ModuleType(evaluation_name)
    evaluation.__path__ = [str(ROOT / 'studies/sce_inflation_expectations/evaluation')]
    sys.modules[evaluation_name] = evaluation

from studies.sce_inflation_expectations.evaluation.full_a_core_normal import (
    EXPECTED_MONTHS,
    _national_readout,
    _checked_masses,
    _numeric_tau,
    score_atom_distribution,
)


def test_weighted_full_wave_cdf_matches_hand_calculated_statistics():
    # Model mass is 3/4 at 0 and 1/4 at 2. The full-wave target has
    # weights 1/4 at 0, 1/2 at 1 and 1/4 at 2. Their CDF gap integrates
    # to 0.5 pp over [0, 1], and zero over [1, 2].
    atoms = [{'q9_mean': 0.}, {'q9_mean': 2.}]
    result = score_atom_distribution(
        atoms, [3., 1.], 'q9_mean', [0., 1., 2.], [1., 2., 1.])
    assert result['simulated']['weight_sum'] == pytest.approx(4.)
    assert result['simulated']['median_pp'] == pytest.approx(0.)
    assert result['observed']['median_pp'] == pytest.approx(1.)
    assert result['w1_pp'] == pytest.approx(.5)
    assert result['median_bias_pp'] == pytest.approx(-1.)
    assert result['simulated']['iqr_pp'] == pytest.approx(0.)
    assert result['observed']['iqr_pp'] == pytest.approx(1.)
    assert result['iqr_error_pp'] == pytest.approx(1.)


def test_zero_mass_null_atom_is_excluded_but_positive_mass_null_is_rejected():
    atoms = [{'q8': 1.}, {'q8': None}]
    result = score_atom_distribution(atoms, [2., 0.], 'q8', [1.], [1.])
    assert result['simulated']['valid_donor_atoms'] == 1
    assert 'effective_atom_mass_size_not_person_ess' in result['simulated']
    with pytest.raises(ValueError, match='Positive mass'):
        score_atom_distribution(atoms, [1., 1.], 'q8', [1.], [1.])


def test_tau_mass_must_conserve_registered_population_mass():
    atoms = [{'q9_mean': 1.}, {'q9_mean': 2.}]
    assert _checked_masses(atoms, [4., 6.], expected_total=10., label='fixture') == 10.
    with pytest.raises(ValueError, match='does not conserve'):
        _checked_masses(atoms, [4., 5.], expected_total=10., label='fixture')


@pytest.mark.parametrize('value,expected', [(0, '0'), (8, '8'), (24, '24')])
def test_only_sealed_registered_numeric_taus_are_accepted(value, expected):
    assert _numeric_tau(value) == expected


@pytest.mark.parametrize('value', [None, '8', 12, -1, 8.5])
def test_tau_selection_rejects_unregistered_or_non_numeric_values(value):
    with pytest.raises(ValueError):
        _numeric_tau(value)


@pytest.mark.skipif(importlib.util.find_spec('duckdb') is None,
                    reason='The existing monthly readout imports the full project runtime.')
def test_national_readout_uses_frozen_48_34_chronological_blend():
    rows = []
    for month in EXPECTED_MONTHS:
        formatted = f'{month[:4]}-{month[4:]}'
        rows.append(dict(month=formatted, sim_pp=3., anchor_pp=1., truth_pp=2.))
    tau_rows = {
        '0': rows,
        '8': [dict(row, sim_pp=3.5) for row in rows],
        '24': [dict(row, sim_pp=2.) for row in rows],
    }
    result = _national_readout(rows, tau_rows)
    combo = result['chronological_combinations']['before_t0']['mae']
    assert len(combo['fit_months']) == 48
    assert len(combo['evaluation_months']) == 34
    assert combo['simulation_weight'] == pytest.approx(.5)
    assert combo['evaluation']['mae_pp'] == pytest.approx(0.)
