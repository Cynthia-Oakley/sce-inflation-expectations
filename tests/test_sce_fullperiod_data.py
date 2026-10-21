"""Tests for the SCE full-period sample delivery (phase 2).

Covers scripts/build_sce_fullperiod_sample_environments.py and
scripts/build_sce_fullperiod_sample_data.py outputs under
outputs/sce_fullperiod_data_20261021_v1/<YYYYMM>/ for 2019-06, 2023-03,
2026-06: official-schema validation (population + environment), raw-userid
leak scan across every delivered file, as_of consistency with coverage.json,
file completeness, anonymized-id set consistency across private files, and
the sample-month acceptance numbers (1330 / 172 entrants / all-synthetic).
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OUT = REPO_ROOT / "outputs/sce_fullperiod_data_20261021_v1"
TARGETS = ["201906", "202303", "202606"]
MICRO_FILES = [
    "data/raw/sce_p_sources/micro_2017_2019.xlsx",
    "data/raw/sce_audit_20260928/micro_2020_2024.xlsx",
    "data/raw/sce_audit_20260928/micro_latest.xlsx",
]
MONTH_FILES = [
    "population.json",
    "population_state_private.json",
    "belief_state_private.json",
    "sampling_private.json",
    "environment.json",
    "news_label_index.json",
]

DELIVERY_PRESENT = (OUT / "coverage.json").is_file() and all(
    (OUT / t / "population.json").is_file() for t in TARGETS)


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _walk_strings(v)


@unittest.skipUnless(DELIVERY_PRESENT, "full-period sample delivery absent")
class TestSampleDelivery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.coverage = json.loads((OUT / "coverage.json").read_text())
        cls.months = {}
        for t in TARGETS:
            mdir = OUT / t
            cls.months[t] = {
                "population": json.loads((mdir / "population.json").read_text()),
                "pop_state": json.loads((mdir / "population_state_private.json").read_text()),
                "belief": json.loads((mdir / "belief_state_private.json").read_text()),
                "sampling": json.loads((mdir / "sampling_private.json").read_text()),
                "environment": json.loads((mdir / "environment.json").read_text()),
                "news": json.loads((mdir / "news_label_index.json").read_text()),
            }
        # raw userid universe for the leak scan (skip files that are absent)
        import pandas as pd
        cls.userids = set()
        for rel in MICRO_FILES:
            p = REPO_ROOT / rel
            if not p.exists():
                continue
            df = pd.read_excel(p, skiprows=1, usecols=["userid"])
            cls.userids.update(int(u) for u in df["userid"].dropna())

    def test_root_files_present(self):
        for name in ("coverage.json", "sources.json", "README.md"):
            self.assertTrue((OUT / name).is_file(), name)

    def test_month_file_completeness(self):
        for t in TARGETS:
            for name in MONTH_FILES:
                self.assertTrue((OUT / t / name).is_file(), f"{t}/{name}")
            tdir = OUT / t / "evaluation_truth"
            self.assertTrue(tdir.is_dir(), f"{t}/evaluation_truth")
            self.assertTrue(
                any(tdir.iterdir()), f"{t}/evaluation_truth empty")

    def test_population_official_schema(self):
        from socioverse.schemas import PopulationBundle
        for t in TARGETS:
            bundle = self.months[t]["population"]
            PopulationBundle.model_validate(bundle)
            ids = [p["agent_id"] for p in bundle["personas"]]
            self.assertEqual(len(ids), len(set(ids)), f"{t}: duplicate agent_id")
            self.assertEqual(bundle["materialized_count"], len(ids))

    def test_environment_official_schema(self):
        from socioverse.schemas import EnvironmentBundle
        for t in TARGETS:
            EnvironmentBundle.model_validate(self.months[t]["environment"])

    def test_as_of_matches_coverage(self):
        for t in TARGETS:
            key = f"{t[:4]}-{t[4:]}"
            cov = next(m for m in self.coverage["months"]
                       if m["target_month"] == key)
            data = self.months[t]
            self.assertEqual(data["population"]["provider_args"]["as_of"],
                             cov["as_of"], f"{t} population as_of")
            self.assertEqual(data["belief"]["as_of"], cov["as_of"],
                             f"{t} belief as_of")
            env_target = data["environment"]["provider_args"]["targets"][0]
            self.assertEqual(env_target["as_of"], cov["as_of"],
                             f"{t} environment as_of")
            self.assertEqual(env_target["target_month"], key)

    def test_no_raw_userid_leak(self):
        if not self.userids:
            self.skipTest("micro files absent; cannot define userid universe")
        uid_strings = {str(u) for u in self.userids}
        for t in TARGETS:
            mdir = OUT / t
            files = [mdir / n for n in MONTH_FILES]
            files += sorted((mdir / "evaluation_truth").glob("*.json"))
            for path in files:
                payload = json.loads(path.read_text())
                hits = [s for s in _walk_strings(payload) if s in uid_strings]
                self.assertEqual(hits, [], f"{path.relative_to(REPO_ROOT)}: "
                                           f"{hits[:3]} raw userids leaked")
                # numeric leak: exact int match
                def walk_nums(v):
                    if isinstance(v, bool):
                        return
                    if isinstance(v, int):
                        yield v
                    elif isinstance(v, dict):
                        for x in v.values():
                            yield from walk_nums(x)
                    elif isinstance(v, (list, tuple)):
                        for x in v:
                            yield from walk_nums(x)
                num_hits = [n for n in walk_nums(payload) if n in self.userids]
                self.assertEqual(num_hits, [], f"{path.relative_to(REPO_ROOT)}: "
                                                f"numeric userid leak {num_hits[:3]}")

    def test_salt_not_in_population(self):
        for t in TARGETS:
            salt = self.months[t]["pop_state"]["anon_salt"]
            pub = (OUT / t / "population.json").read_text()
            self.assertNotIn(salt, pub)

    def test_anon_id_sets_consistent(self):
        for t in TARGETS:
            data = self.months[t]
            pop_ids = {p["agent_id"] for p in data["population"]["personas"]}
            self.assertEqual({r["agent_id"] for r in data["pop_state"]["persons"]},
                             pop_ids, f"{t} pop_state ids")
            self.assertEqual({r["agent_id"] for r in data["belief"]["persons"]},
                             pop_ids, f"{t} belief ids")
            self.assertEqual({r["agent_id"] for r in data["sampling"]["persons"]},
                             pop_ids, f"{t} sampling ids")

    def test_acceptance_population_numbers(self):
        pop19 = self.months["201906"]["population"]
        self.assertEqual(len(pop19["personas"]), 1330)
        pop23 = self.months["202303"]["pop_state"]
        entrants = sum(1 for r in pop23["persons"]
                       if r["survey_entry_status"] == "entrant")
        self.assertEqual(entrants, 172)
        self.assertEqual(pop23["entry_status_counts"].get("entrant"), 172)
        # 2026-06: every persona synthetic
        pop26 = self.months["202606"]["population"]
        self.assertEqual(len(pop26["personas"]), 1300)
        self.assertTrue(all(p["init_state"]["synthetic"] for p in pop26["personas"]))
        self.assertTrue(all(r["synthetic"] for r in
                            self.months["202606"]["pop_state"]["persons"]))

    def test_belief_source_kinds(self):
        for t in ("201906", "202303"):
            kinds = {r["source_kind"] for r in self.months[t]["belief"]["persons"]}
            self.assertIn("observed_previous", kinds)
            self.assertIn("donor_initial", kinds)
            for r in self.months[t]["belief"]["persons"]:
                if r["source_kind"] == "donor_initial":
                    self.assertIn("donor", r)
                    self.assertLess(r["donor"]["donor_period"],
                                    int(t), "donor must be strictly past")
        kinds26 = {r["source_kind"] for r in self.months["202606"]["belief"]["persons"]}
        self.assertEqual(kinds26, {"simulated_previous"})
        self.assertTrue(all(r["q8_q9"] is None for r in
                            self.months["202606"]["belief"]["persons"]))

    def test_environment_timing_guard(self):
        from datetime import datetime
        for t in TARGETS:
            env = self.months[t]["environment"]
            as_of = env["provider_args"]["targets"][0]["as_of"]
            for step, records in env["provider_args"]["signals_by_step"].items():
                for rec in records:
                    self.assertLess(datetime.fromisoformat(rec["published_at"]),
                                    datetime.fromisoformat(as_of),
                                    f"{t}/{rec['signal_id']} not before as_of")
            events = env["provider_args"]["events_by_step"]["0"]
            self.assertGreater(len(events), 0, f"{t}: no events")
            for e in events:
                self.assertLessEqual(e["pub_date"], as_of[:10])

    def test_environment_documented_gaps(self):
        env26 = self.months["202606"]["environment"]["provider_args"]["data_gaps"]
        gap_refs = {g["reference_period"] for g in env26["gaps"]}
        self.assertIn("2025-10", gap_refs)
        env19 = self.months["201906"]["environment"]["provider_args"]["data_gaps"]
        gap_refs19 = {g["reference_period"] for g in env19["gaps"]}
        self.assertIn("2018-06", gap_refs19)
        env23 = self.months["202303"]["environment"]["provider_args"]["data_gaps"]
        self.assertLessEqual(len(env23["gaps"]), 1)

    def test_news_label_index_matches_coverage(self):
        for t in TARGETS:
            key = f"{t[:4]}-{t[4:]}"
            cov = next(m for m in self.coverage["months"]
                       if m["target_month"] == key)
            news = self.months[t]["news"]
            self.assertEqual(news["n_missing_labels"], cov["news_labels_missing"],
                             f"{t} label gap mismatch vs coverage")
            self.assertEqual(news["n_selected"],
                             news["n_labeled"] + news["n_missing_labels"])
        self.assertEqual(self.months["202303"]["news"]["n_missing_labels"], 0)

    def test_evaluation_truth(self):
        t19 = json.loads((OUT / "201906/evaluation_truth/micro_truth.json").read_text())
        t23 = json.loads((OUT / "202303/evaluation_truth/micro_truth.json").read_text())
        for payload, yyyymm, n in ((t19, "201906", 1330), (t23, "202303", 1254)):
            self.assertEqual(payload["manifest"]["layer"], "evaluation_only")
            self.assertEqual(len(payload["per_person"]), n)
            monthly = payload["monthly_full_sample"][yyyymm]
            self.assertIsNotNone(monthly["official_point_median"])
            self.assertIsNotNone(monthly["official_density_median"])
            self.assertAlmostEqual(monthly["q8point_interp_median"],
                                   monthly["official_point_median"], places=4)
        t26 = json.loads((OUT / "202606/evaluation_truth/aggregate_only.json").read_text())
        self.assertEqual(t26["manifest"]["status"], "aggregate_only_no_micro")
        self.assertIsNone(t26["per_person"])
        self.assertIsNotNone(t26["monthly_official_aggregate"]["official_point_median"])

    def test_sampling_private(self):
        for t in TARGETS:
            s = self.months[t]["sampling"]
            pop = self.months[t]["population"]
            self.assertEqual(s["frame_n"], len(pop["personas"]))
            self.assertEqual(sum(c["n"] for c in s["strata"]), s["frame_n"])
            self.assertEqual(s["core_selection"], "NOT performed (frozen by Codex)")
            pri = [p["stable_priority"] for p in s["persons"]]
            self.assertEqual(len(pri), len(set(pri)))
            # deterministic stable priority
            import hashlib
            salt = s["stable_priority"]["salt"]
            for p in s["persons"][:50]:
                expect = int(hashlib.sha256(
                    f"{p['agent_id']}|{salt}".encode()).hexdigest()[:16], 16)
                self.assertEqual(p["stable_priority"], expect)


if __name__ == "__main__":
    unittest.main()
