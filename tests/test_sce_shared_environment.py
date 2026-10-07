import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "studies/sce_inflation_expectations"))
from evaluation.shared_environment import extract_shared_rows


def fixture():
    return {"provider_args": {"targets": [{"target_month": "2021-05", "as_of": "2021-05-12T23:59:59-04:00"}],
            "signals_by_step": {"0": [{"signal_id": "cpi", "measure": "CPI", "unit": "percent", "role": "latest_release", "value": 4.2,
            "reference_period": "2021-04", "published_at": "2021-05-12T08:30:00-04:00", "eligibility": "eligible", "source_url": "https://www.bls.gov/", "source_version": "release"}]},
            "events_by_step": {"0": [{"event_id": "news", "pub_date": "2021-05-12", "headline": "Gasoline", "abstract": "Prices rise."}]}}}


class SharedEnvironmentTest(unittest.TestCase):
    def test_lossless_export_no_input_mutation(self):
        data = fixture(); original = copy.deepcopy(data)
        row = extract_shared_rows(data)[0]
        self.assertEqual(row["signals"], original["provider_args"]["signals_by_step"]["0"])
        self.assertEqual(list(row["numeric_features"].values()), [4.2])
        self.assertEqual(row["news_text"], "Gasoline\nPrices rise.")
        self.assertEqual(data, original)

    def test_future_signal_rejected(self):
        data = fixture(); data["provider_args"]["signals_by_step"]["0"][0]["published_at"] = "2021-05-13T08:30:00-04:00"
        with self.assertRaises(ValueError): extract_shared_rows(data)

    def test_unknown_news_time_not_invented_before_day_end(self):
        data = fixture(); data["provider_args"]["targets"][0]["as_of"] = "2021-05-12T12:00:00-04:00"
        with self.assertRaises(ValueError): extract_shared_rows(data)

    def test_duplicate_features_rejected(self):
        data = fixture(); records = data["provider_args"]["signals_by_step"]["0"]
        records.append({**records[0], "signal_id": "another"})
        with self.assertRaises(ValueError): extract_shared_rows(data)

    def test_uncertain_evidence_retained_not_certified(self):
        data = fixture(); data["provider_args"]["signals_by_step"]["0"][0]["note"] = "last weekly obs + 3 days (conservative)"
        row = extract_shared_rows(data)[0]
        self.assertEqual(len(row["evidence_uncertainties"]), 1)
        self.assertEqual(len(row["signals"]), 1)

    def test_flagged_gas_requires_opt_in_and_remains_flagged(self):
        data = fixture()
        record = data["provider_args"]["signals_by_step"]["0"][0]
        record.update(signal_id="eia_gasoline_retail_regular_mean_2021_04",
                      source_version="FRED GASREGW (EIA weekly retail, Monday obs)",
                      eligibility="vintage_unverified")
        with self.assertRaises(ValueError):
            extract_shared_rows(data)
        row = extract_shared_rows(data, allow_unverified_vintage=True)[0]
        self.assertEqual(row["signals"][0]["eligibility"], "vintage_unverified")
        self.assertEqual(len(row["evidence_uncertainties"]), 1)

    def test_opt_in_does_not_admit_unknown_or_non_gas_evidence(self):
        for status in ("vintage_unverified", "unknown_as_of"):
            data = fixture()
            data["provider_args"]["signals_by_step"]["0"][0]["eligibility"] = status
            with self.assertRaises(ValueError):
                extract_shared_rows(data, allow_unverified_vintage=True)


if __name__ == "__main__": unittest.main()
