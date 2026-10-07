"""Source extension gates: real calendar, immutable caches and key-safe errors."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import extend_sce_environment_sources as extension


def test_history_and_news_requirements_include_previous_year():
    req = extension.requirements(["2022-01", "2022-02"])
    assert req["bls_reference_months"] == [
        f"2021-{m:02d}" for m in range(1, 13)] + ["2022-01"]
    assert req["nyt_months"] == ["2021-12", "2022-01", "2022-02"]
    with pytest.raises(ValueError):
        extension.requirements(["2022-13"])


def test_calendar_uses_explicit_reference_not_release_month():
    text = ("L215: Friday, January 07, 2022 08:30 AM Employment Situation for December 2021\n"
            "L216: Wednesday, January 12, 2022 08:30 AM Consumer Price Index for December 2021\n"
            "Friday, January 07, 2022 10:00 AM Unrelated Release for December 2021")
    rows = extension.calendar_entries(text, "calendar.txt")
    assert len(rows) == 2
    assert rows["cpi", "2021-12"]["release_date"] == "2022-01-12"
    assert rows["empsit", "2021-12"]["release_date"] == "2022-01-07"


def test_cached_pdf_is_reverified_not_trusted_by_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(extension.bls, "DEFAULT_RAW_ROOT", tmp_path)
    folder = tmp_path / "2021-12"
    folder.mkdir()
    path = folder / "cpi_2021_12_released_2022_01_12.pdf"
    path.write_bytes(b"wrong document")
    monkeypatch.setattr(extension.bls, "_first_pages_text", lambda _: "Wrong release")
    with pytest.raises(ValueError, match="cached PDF embargo/reference mismatch"):
        extension.prepare_pdf("cpi", "2021-12", {}, False, "")
    assert path.read_bytes() == b"wrong document"


def test_no_calendar_means_no_guessed_download(tmp_path, monkeypatch):
    monkeypatch.setattr(extension.bls, "DEFAULT_RAW_ROOT", tmp_path)
    monkeypatch.setattr(extension, "download_bytes", lambda *a, **k: pytest.fail("must not download"))
    with pytest.raises(ValueError, match="official calendar unavailable"):
        extension.prepare_pdf("empsit", "2022-01", {}, True, "")


def test_download_error_never_contains_credential(monkeypatch):
    import httpx

    class FailingClient:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url):
            raise RuntimeError("bad request " + url)

    monkeypatch.setattr(httpx, "Client", FailingClient)
    with pytest.raises(RuntimeError) as caught:
        extension.download_bytes("https://api.nytimes.com/archive?api-key=test-secret", "", secret=True)
    assert "test-secret" not in str(caught.value)
    assert "api-key" not in str(caught.value)
    assert caught.value.__suppress_context__


def test_malformed_news_is_not_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(extension.nyt, "ROOT", tmp_path)
    monkeypatch.setattr(extension, "download_bytes", lambda *a, **k: b'{"status":"error"}')
    with pytest.raises(ValueError, match="missing response.docs"):
        extension.prepare_news("2022-01", True, "", "test-secret")
    assert not (tmp_path / "data/raw/nyt_archive/2022-01.json").exists()


def test_annual_wording_fallback_rejects_monthly_numbers():
    annual = ["The index rose 5.5 percent over the past 12 months, its largest 12-month "
              "increase since February 1991. Major contributors to this increase include "
              "shelter (+4.1 percent)."]
    hit = extension.component_wording_fallback(annual, "cpi_shelter_yoy")
    assert hit["value"] == 4.1
    monthly = ["The shelter index rose 0.4 percent in December. "
               "Major contributors to this increase include shelter (+0.4 percent)."]
    assert extension.component_wording_fallback(monthly, "cpi_shelter_yoy") is None
    food = ["The energy index rose 29.3 percent over the last year, "
            "and the food index increased 6.3 percent."]
    assert extension.component_wording_fallback(food, "cpi_food_yoy")["value"] == 6.3


def test_news_cache_hash_mismatch_is_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(extension.nyt, "ROOT", tmp_path)
    folder = tmp_path / "data/raw/nyt_archive"
    folder.mkdir(parents=True)
    (folder / "2022-01.json").write_text('{"response":{"docs":[]}}')
    extension.write_json(folder / "2022-01.meta.json", {
        "month": "2022-01", "n_docs": 0, "sha256": "wrong"})
    with pytest.raises(ValueError, match="manifest/hash mismatch"):
        extension.prepare_news("2022-01", False, "", None)


def test_independent_html_check_uses_annual_column(tmp_path, monkeypatch):
    monkeypatch.setattr(extension, "ROOT", tmp_path)
    folder = tmp_path / "data/raw/sce_baselines_20261007"
    folder.mkdir(parents=True)
    (folder / "cpi_20220713.web.txt").write_text(
        "Table A. Percent changes\nL223: Food  | 0.5 | 0.9 | 1.0 | 10.4\n"
        "L224: Food at home | 0.4 | 1.0 | 1.4 | 12.2\n")
    rows = [{"published_at": "2022-07-13", "reference_period": "2022-06",
             "signal_id": "cpi_food_yoy", "value": 10.4},
            {"published_at": "2022-07-13", "reference_period": "2022-06",
             "signal_id": "cpi_food_at_home_yoy", "value": 1.4}]
    checks = extension.check_component_html(rows)
    assert checks[0]["status"] == "agree"
    assert checks[1]["status"] == "disagree"
    assert checks[1]["html_value"] == 12.2


def test_energy_extractor_does_not_match_core_inflation():
    pages = ["The all items less food and energy index rose 5.9 percent over the last 12 months. "
             "The energy index rose 41.6 percent over the last year."]
    assert extension.energy_annual_only(pages)["value"] == 41.6
    assert extension.energy_annual_only([pages[0].split("The energy index")[0]]) is None
    assert extension.energy_annual_only([
        "The energy index fell 9.4 percent over the last 12 months."])["value"] == -9.4


def test_independent_old_ascii_table_keeps_negative_annual_change(tmp_path, monkeypatch):
    monkeypatch.setattr(extension, "ROOT", tmp_path)
    folder = tmp_path / "data/raw/sce_environment_extension_html"
    folder.mkdir(parents=True)
    (folder / "cpi_20210210.web.txt").write_text(
        "L212: Table A. Percent changes\n"
        "L227:       Energy....................   2.1 .9 1.4 .6 .7 2.6 3.5 -3.6\n")
    result = extension.check_component_html([{
        "published_at": "2021-02-10", "reference_period": "2021-01",
        "signal_id": "cpi_energy_yoy", "value": -3.6}])
    assert result[0]["status"] == "agree"
    assert result[0]["html_value"] == -3.6


def test_employment_remained_wording_for_2022_first_release():
    text = ("USDL-22-1125 Total nonfarm payroll employment rose by 390,000 in May, "
            "and the unemployment rate remained at 3.6 percent.")
    got = extension.bls.transcribe_empsit(text, "2022-05")
    assert got["unemployment_rate_pct"]["value"] == 3.6
    assert got["nonfarm_payroll_change_k"]["value"] == 390
    assert "remainedat3.6percent" in got["unemployment_rate_pct"]["quote"]
    assert extension.ev._unemployment_rate_only(text, "2022-05")["value"] == 3.6
