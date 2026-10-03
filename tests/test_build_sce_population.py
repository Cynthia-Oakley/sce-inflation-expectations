"""Tests for scripts/build_sce_population.py (real-population sampling from SCE micro data).

Covered: PopulationBundle validation, panel persistence across target months,
P-whitelist hygiene (no weight/Q8v2/Q9_* leakage into persona attributes),
seed determinism, and sampling metadata completeness. Skipped entirely when
the gitignored micro xlsx is absent.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from socioverse.schemas import PopulationBundle  # noqa: E402

from scripts.build_sce_population import (  # noqa: E402
    DEFAULT_DATA, _load_frame, build_from_frame,
)

MONTHS = [202105, 202106]
N_SMALL = 12
SEED = 42

MICRO_AVAILABLE = DEFAULT_DATA.exists()


@unittest.skipUnless(MICRO_AVAILABLE, f"micro data absent: {DEFAULT_DATA}")
class TestBuildSCEPopulation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = _load_frame(DEFAULT_DATA)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "population_real12.json"
        cls.bundle, cls.roster, cls.meta = build_from_frame(
            cls.df, MONTHS, N_SMALL, SEED, housing_window=6, data_path=DEFAULT_DATA)
        PopulationBundle.model_validate(cls.bundle)  # gate as the script does
        cls.by_id = {p["agent_id"]: p for p in cls.bundle["personas"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    # ---- structural --------------------------------------------------------
    def test_bundle_validates_and_size(self):
        bundle = PopulationBundle.model_validate(
            json.loads(json.dumps(self.bundle)))
        self.assertEqual(len(bundle.personas), N_SMALL)
        self.assertEqual(bundle.study_id, "sce_inflation_expectations")
        self.assertEqual(bundle.interaction.kind, "none")
        self.assertEqual(bundle.propagation.value, "independent")
        self.assertEqual(bundle.materialized_count, N_SMALL)
        self.assertTrue(all(p["weight"] == 1.0 for p in self.bundle["personas"]))
        for p in self.bundle["personas"]:
            self.assertEqual(p["init_state"],
                             {"target_month": "", "direction": "",
                              "point_pct": 0.0, "q9_valid": False})

    def test_panel_persistent_across_months(self):
        sub = self.df[self.df["date"].isin(MONTHS)]
        users = {int(u) for u in sub["userid"]}
        for p in self.bundle["personas"]:
            uid = int(p["agent_id"].removeprefix("sce_u"))
            rows = sub[sub["userid"] == uid]
            self.assertEqual(sorted(rows["date"].tolist()), MONTHS,
                             f"userid {uid} not present in all target months")

    def test_no_forbidden_attribute_keys(self):
        allowed = {"age_group", "education_group", "household_income_band",
                   "region", "state", "numeracy", "employment_status",
                   "housing_tenure"}
        for p in self.bundle["personas"]:
            keys = set(p["attributes"])
            self.assertTrue(keys <= allowed, f"unexpected keys: {keys - allowed}")
            self.assertNotIn("weight", {k.lower() for k in keys})
            for k in keys:
                self.assertFalse(k.lower().startswith(("q8", "q9")),
                                 f"answer column leaked as attribute: {k}")

    def test_deterministic_same_seed(self):
        months_by_user = self.df[self.df["date"].isin(MONTHS)].groupby("userid")["date"].nunique()
        pool = sorted(int(u) for u in months_by_user[months_by_user == len(MONTHS)].index)
        expected = random.Random(SEED).sample(pool, N_SMALL)
        self.assertEqual(self.meta["sampled_userids"], expected)

    def test_pool_too_small_fails_loudly(self):
        months_by_user = self.df[self.df["date"].isin(MONTHS)].groupby("userid")["date"].nunique()
        pool_size = int((months_by_user == len(MONTHS)).sum())
        with self.assertRaises(SystemExit):
            build_from_frame(self.df, MONTHS, pool_size + 1, SEED, housing_window=6)

    def test_metadata_complete(self):
        m = self.meta
        self.assertEqual(m["seed"], SEED)
        self.assertEqual(m["target_months"], MONTHS)
        self.assertTrue(m["panel_mode"])
        self.assertEqual(m["n_sampled"], N_SMALL)
        pool = m["candidate_pool"]
        self.assertGreaterEqual(pool["panel_intersection"], N_SMALL)
        self.assertTrue(all(v > 0 for v in pool["per_month_rows"].values()))
        src = m["source_files"][0]
        digest = hashlib.sha256(DEFAULT_DATA.read_bytes()).hexdigest()
        self.assertEqual(src["sha256"], digest)
        for field in ("age_group", "education_group", "household_income_band",
                      "region", "numeracy", "employment_status", "housing_tenure"):
            self.assertIn(field, m["attribute_distributions"])
        self.assertIn("coverage", m["field_mappings"]["housing_tenure"])
        self.assertEqual(sum(m["attribute_distributions"]["age_group"].values()), N_SMALL)

    def test_written_outputs_roundtrip(self):
        from scripts.build_sce_population import main
        out = Path(self.tmp.name) / "population_rt.json"
        rc = main(["--months", "202105,202106", "--n", str(N_SMALL),
                   "--seed", str(SEED), "--out", str(out)])
        self.assertEqual(rc, 0)
        bundle = PopulationBundle.model_validate(json.loads(out.read_text()))
        self.assertEqual(len(bundle.personas), N_SMALL)
        roster_path = out.with_name("roster_rt.jsonl")
        meta_path = out.with_name("population_rt.sampling_meta.json")
        roster = [json.loads(line) for line in roster_path.read_text().splitlines()]
        self.assertEqual(len(roster), N_SMALL)
        self.assertEqual({r["agent_id"] for r in roster},
                         {p.agent_id for p in bundle.personas})
        self.assertTrue(meta_path.exists())
        rt_meta = json.loads(meta_path.read_text())
        self.assertEqual(rt_meta["sampled_userids"], self.meta["sampled_userids"])


if __name__ == "__main__":
    unittest.main()
