from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sce_cpi_layout as cpi  # noqa: E402


def _page(layout: str, plain: str = "") -> dict[str, str]:
    return {"layout": layout, "plain": plain}


@pytest.mark.parametrize(
    ("signal", "label", "annual_value"),
    [
        ("cpi_food_yoy", "Food", "2.4"),
        ("cpi_food_at_home_yoy", "Food at home", "1.2"),
        ("cpi_energy_yoy", "Energy", "-4.8"),
        ("cpi_shelter_yoy", "Shelter", "3.2"),
        ("cpi_gasoline_yoy", "Gasoline (all types)", "-10.1"),
    ],
)
def test_table_a_reads_eighth_decimal_for_exact_row(signal, label, annual_value):
    layout = f"""Table A. Percent changes in CPI for All Urban Consumers (CPI-U)
Un-adjusted 12-mos. ended Jan. 2019
{label} .................................... .1 .2 .3 .4 .5 .6 .7 {annual_value}
"""
    result = cpi._table_a([_page(layout)], signal, "2019-01")
    assert result is not None
    assert result["value"] == float(annual_value)
    assert result["header"] == "Un-adjusted 12-mos. ended Jan. 2019"
    assert result["extraction"] == "table_a_layout"
    assert result["page"] == 1
    assert label in result["quote"]


def test_table_a_rejects_a_header_for_the_wrong_reference_month():
    layout = """Table A. Percent changes in CPI for All Urban Consumers (CPI-U)
Un-adjusted 12-mos. ended Feb. 2019
Shelter .................................... .1 .2 .3 .4 .5 .6 .7 3.2
"""
    assert cpi._table_a([_page(layout)], "cpi_shelter_yoy", "2019-01") is None


def test_table1_uses_year_over_year_column_not_row_end():
    layout = """Table 1. Consumer Price Index for All Urban Consumers, March 2019
Unadjusted percent change; Seasonally adjusted percent change
Mar. 2018–Mar. 2019
Gasoline (all types). . . . . 3.556 226.872 206.749 225.282 -0.7 9.0 -5.5 1.5 6.5
"""
    result = cpi._table1([_page(layout)], "cpi_gasoline_yoy", "2019-03")
    assert result is not None
    assert result["value"] == -0.7
    assert result["value"] != 6.5
    assert result["extraction"] == "table1_layout"


def test_direct_annual_prose_preserves_decline_sign():
    pages = [
        _page(
            "",
            "The gasoline index declined 5.5 percent over the last 12 months.",
        )
    ]
    result = cpi._prose_fallback(pages, "cpi_gasoline_yoy", "2019-03")
    assert result is not None
    assert result["value"] == -5.5
    assert result["pattern"] == "prose_direct_annual_suffix"


@pytest.mark.parametrize(
    ("signal", "sentence"),
    [
        (
            "cpi_shelter_yoy",
            "The shelter index rose 0.3 percent in March. Over the past 12 months, all items rose 2.0 percent.",
        ),
        (
            "cpi_energy_yoy",
            "The all items less food and energy index increased 1.2 percent over the year.",
        ),
    ],
)
def test_prose_fallback_rejects_monthly_and_core_energy_false_hits(signal, sentence):
    assert cpi._prose_fallback([_page("", sentence)], signal, "2019-03") is None


def test_food_at_home_can_inherit_annual_scope_only_from_exact_food_sentence():
    pages = [
        _page(
            "",
            "The food index rose 2.0 percent over the past year, with the food at home index increasing 1.2 percent.",
        )
    ]
    result = cpi._prose_fallback(pages, "cpi_food_at_home_yoy", "2019-05")
    assert result is not None
    assert result["value"] == 1.2
    assert result["pattern"] == "prose_inherited_food_index_annual_scope"


ACTUAL_HANDOFF_VALUES = {
    ("2019-01", "cpi_shelter_yoy"): 3.2,
    ("2019-02", "cpi_gasoline_yoy"): -9.1,
    ("2019-03", "cpi_shelter_yoy"): 3.4,
    ("2019-03", "cpi_gasoline_yoy"): -0.7,
    ("2019-04", "cpi_food_at_home_yoy"): 0.7,
    ("2019-04", "cpi_shelter_yoy"): 3.4,
    ("2019-04", "cpi_gasoline_yoy"): 3.1,
    ("2019-05", "cpi_food_at_home_yoy"): 1.2,
    ("2019-05", "cpi_shelter_yoy"): 3.3,
    ("2019-06", "cpi_food_at_home_yoy"): 0.9,
    ("2019-06", "cpi_shelter_yoy"): 3.5,
    ("2019-07", "cpi_food_at_home_yoy"): 0.6,
    ("2019-07", "cpi_shelter_yoy"): 3.5,
    ("2019-09", "cpi_shelter_yoy"): 3.5,
}


def test_actual_2019_handoff_values_extract_when_local_archive_is_present():
    pytest.importorskip("pypdf")
    handoff = ROOT / "outputs/sce_e_extension_20261007T084913Z/components_handoff.jsonl"
    if not handoff.exists():
        pytest.skip("local BLS first-release archive is not present")
    rows = [json.loads(line) for line in handoff.read_text().splitlines() if line.strip()]
    assert len(rows) == 14
    observed = {}
    for row in rows:
        result = cpi.extract_annual_component(
            ROOT / row["source_pdf"], row["signal_id"], row["reference_period"]
        )
        assert result is not None, (row["reference_period"], row["signal_id"])
        observed[(row["reference_period"], row["signal_id"])] = result["value"]
    assert observed == ACTUAL_HANDOFF_VALUES


def test_actual_2025_september_gasoline_uses_matching_table1_annual_column():
    pytest.importorskip("pypdf")
    handoff = ROOT / "outputs/sce_e_extension_2024_2025_bls_20261007/components_handoff.jsonl"
    if not handoff.exists():
        pytest.skip("local 2024-2025 BLS archive is not present")
    rows = [json.loads(line) for line in handoff.read_text().splitlines() if line.strip()]
    target = next(
        row for row in rows
        if row["reference_period"] == "2025-09" and row["signal_id"] == "cpi_gasoline_yoy"
    )
    result = cpi.extract_annual_component(
        ROOT / target["source_pdf"], target["signal_id"], target["reference_period"]
    )
    assert result is not None
    assert result["value"] == -0.5
    assert result["page"] == 8
    assert result["header"] == "Table 1: Unadjusted percent change; September 2024–September 2025"
    assert result["extraction"] == "table1_layout"
