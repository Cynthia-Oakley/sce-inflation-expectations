import copy
import json
from pathlib import Path
import unittest

import pandas as pd

from socioverse.schemas import PopulationBundle
from studies.sce_inflation_expectations.monthly_population import (
    PROFILE_COLUMNS, build_analysis_weights, build_monthly_population,
)
from scripts.prepare_sce_monthly_inputs import slice_environment


def person(uid, date, **changes):
    row = {key: None for key in PROFILE_COLUMNS}
    row.update(userid=uid, date=date, _AGE_CAT="Under 40", _EDU_CAT="College",
               _HH_INC_CAT="Under 50k", _REGION_CAT="West", _NUM_CAT="High",
               _STATE="California", Q43=1, D3=0, Q10_1=1)
    row.update(changes)
    return row


class MonthlyPopulationTest(unittest.TestCase):
    def test_monthly_roster_and_current_employment(self):
        df = pd.DataFrame([person(1, 202105), person(2, 202105),
                           person(2, 202106, Q10_1=0, Q10_7=1), person(3, 202106)])
        may, _ = build_monthly_population(df, 202105)
        june, _ = build_monthly_population(df, 202106)
        self.assertEqual([p["agent_id"] for p in may["personas"]], ["sce_u1", "sce_u2"])
        self.assertEqual([p["agent_id"] for p in june["personas"]], ["sce_u2", "sce_u3"])
        self.assertEqual(june["personas"][0]["attributes"]["employment_status"], "retired")
        PopulationBundle.model_validate(june)

    def test_future_housing_not_used_and_moved_housing_omitted(self):
        df = pd.DataFrame([person(1, 202104, Q43=2), person(1, 202105, Q43=None, D3=1),
                           person(2, 202105, Q43=None), person(2, 202106, Q43=1)])
        pop, meta = build_monthly_population(df, 202105)
        self.assertTrue(all("housing_tenure" not in p["attributes"] for p in pop["personas"]))
        self.assertEqual(meta["housing_audit"][0]["status"], "moved_since_answer")
        self.assertEqual(meta["housing_audit"][1]["status"], "unobserved")

    def test_answers_and_weights_do_not_change_population(self):
        df = pd.DataFrame([person(uid, 202105) for uid in range(10)])
        df["Q9_mean"] = 0
        df["weight"] = 1
        first, meta = build_monthly_population(df, 202105, n=4, seed=42)
        df["Q9_mean"] = 10000
        df["weight"] = 10000
        second, _ = build_monthly_population(df, 202105, n=4, seed=42)
        self.assertEqual(first, second)
        self.assertTrue(all(p["weight"] == 1 for p in first["personas"]))
        weights = pd.DataFrame({"userid": range(10), "date": [202105] * 10, "weight": [2.] * 10})
        rows = build_analysis_weights(first, meta, weights)
        self.assertTrue(all(row["analysis_weight"] == 5 for row in rows))

    def test_invalid_frame_size_and_weights_fail(self):
        df = pd.DataFrame([person(1, 202105)])
        with self.assertRaises(ValueError):
            build_monthly_population(df, 202105, n=2)
        with self.assertRaises(ValueError):
            build_monthly_population(pd.concat([df, df]), 202105)
        pop, meta = build_monthly_population(df, 202105)
        with self.assertRaises(ValueError):
            build_analysis_weights(pop, meta, pd.DataFrame({"userid": [1], "date": [202105], "weight": [0]}))

    def test_stable_ranking_preserves_same_population_across_months(self):
        df = pd.DataFrame([person(uid, month) for month in [202105, 202106] for uid in range(20)])
        may, mmeta = build_monthly_population(df, 202105, n=5, design="stable_priority_srs")
        june, _ = build_monthly_population(df, 202106, n=5, design="stable_priority_srs")
        self.assertEqual([p["agent_id"] for p in may["personas"]], [p["agent_id"] for p in june["personas"]])
        self.assertEqual(mmeta["inclusion_probability"], .25)

    def test_stable_ranking_does_not_require_future_participation(self):
        may_only = pd.DataFrame([person(uid, 202105) for uid in range(20)])
        with_future = pd.concat([may_only, pd.DataFrame([person(99, 202106)])])
        first, _ = build_monthly_population(may_only, 202105, n=5, design="stable_priority_srs")
        second, _ = build_monthly_population(with_future, 202105, n=5, design="stable_priority_srs")
        self.assertEqual(first, second)


class MonthlyEnvironmentTest(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.env = json.loads((root / "studies/sce_inflation_expectations/environment/environment_dev2021_05_06_v2.json").read_text())

    def test_june_reindexes_without_mutating_source(self):
        before = copy.deepcopy(self.env)
        out = slice_environment(self.env, 202106)
        self.assertEqual(self.env, before)
        self.assertEqual(out["provider_args"]["targets"][0]["target_month"], "2021-06")
        self.assertEqual(out["provider_args"]["signals_by_step"]["0"], self.env["provider_args"]["signals_by_step"]["1"])
        self.assertEqual(len(out["information_program"]["broadcasts"]), 1)
        self.assertEqual(out["information_program"]["broadcasts"][0]["at_step"], 0)

    def test_future_signal_rejected(self):
        self.env["provider_args"]["signals_by_step"]["1"][0]["published_at"] = "2021-07-01T08:30:00-04:00"
        with self.assertRaises(ValueError):
            slice_environment(self.env, 202106)

    def test_date_only_same_day_news_cannot_prove_daytime_availability(self):
        self.env["provider_args"]["targets"][1]["as_of"] = "2021-06-10T12:00:00-04:00"
        self.env["provider_args"]["events_by_step"]["1"][0]["pub_date"] = "2021-06-10"
        with self.assertRaises(ValueError):
            slice_environment(self.env, 202106)


if __name__ == "__main__":
    unittest.main()
