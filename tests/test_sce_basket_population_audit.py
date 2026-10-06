import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from types import SimpleNamespace

from scripts.audit_sce_basket_population import audit
from studies.sce_inflation_expectations.price_experience import (
    BasketAssigner,
    normalize_ce_row,
    prepare_ce_donors,
)


PROFILE = {
    "age_group": "Under 40",
    "education_group": "high_school",
    "household_income_band": "50k_to_100k",
    "housing_tenure": "renter",
    "region": "Northeast",
}


def ce_row(donor_id, *, food, weight):
    return {
        "NEWID": donor_id,
        "AGE_REF": 35,
        "EDUC_REF": 12,
        "CUTENURE": 4,
        "REGION": 1,
        "FINCBTXM": 60000,
        "FINLWT21": weight,
        "TOTEXPPQ": 100,
        "TOTEXPCQ": 0,
        "FOODPQ": food,
        "FOODCQ": 0,
        "GASMOPQ": 10,
        "GASMOCQ": 0,
        "SHELTPQ": 20,
        "SHELTCQ": 0,
    }


class BasketPopulationAuditTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ce_path = self.root / "ce.zip"
        self.member = "2020Q4/FMLI.csv"
        self.rows = [ce_row("a", food=20, weight=1),
                     ce_row("b", food=40, weight=2),
                     ce_row("c", food=60, weight=1)]
        csv_buffer = io.StringIO()
        writer = csv.DictWriter(csv_buffer, fieldnames=list(self.rows[0]))
        writer.writeheader()
        writer.writerows(self.rows)
        self.csv_bytes = csv_buffer.getvalue().encode()
        with zipfile.ZipFile(self.ce_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(self.member, self.csv_bytes)
        self.source = {
            "source_url": "https://example.test/ce.csv",
            "data_sha256": hashlib.sha256(self.ce_path.read_bytes()).hexdigest(),
            "member_sha256": hashlib.sha256(self.csv_bytes).hexdigest(),
            "member": self.member,
            "interview_wave": "2020Q4",
        }
        donors, _ = prepare_ce_donors(self.rows)
        self.assigner = BasketAssigner(donors, self.source, seed=7, min_pool=2)
        self.people = {
            f"sce_u{i}": {"attributes": dict(PROFILE), "weight": 1.0}
            for i in range(1, 4)
        }
        self.population = {
            "materialized_count": len(self.people),
            "provider_args": {"sampling_design": "census", "target_month": 202105},
            "personas": [
                {"agent_id": agent_id, "attributes": person["attributes"], "weight": person["weight"]}
                for agent_id, person in self.people.items()
            ],
        }
        self.full_baskets = {
            agent_id: self.assigner.assign(agent_id, person["attributes"])
            for agent_id, person in self.people.items()
        }
        self.core_baskets = {agent_id: self.full_baskets[agent_id]
                             for agent_id in list(self.people)[:2]}
        self.pop_path = self.root / "population.json"
        self.full_path = self.root / "full_experience.json"
        self.core_path = self.root / "core_experience.json"
        self._write_inputs()

    def tearDown(self):
        self.temp.cleanup()

    def _write_inputs(self):
        self.pop_path.write_text(json.dumps(self.population), encoding="utf-8")
        self.full_path.write_text(json.dumps({
            "target_month": "2021-05",
            "source": self.source,
            "experience_by_id": self.full_baskets,
        }), encoding="utf-8")
        self.core_path.write_text(json.dumps({
            "target_month": "2021-05",
            "source": self.source,
            "experience_by_id": self.core_baskets,
        }), encoding="utf-8")

    def _args(self, out, analysis_weights=None):
        return SimpleNamespace(ce_data=self.ce_path, member=self.member,
                               full_experience=self.full_path,
                               core_experience=self.core_path,
                               population=self.pop_path, output=out, min_pool=2,
                               analysis_weights=analysis_weights)

    def _weights_file(self, rows):
        path = self.root / "analysis_weights.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return path

    def test_weighted_population_and_core_overlap_audit(self):
        out = self.root / "audit"
        result = audit(self._args(out))

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["full_population"]["n"], 3)
        self.assertEqual(result["core_overlap"]["identical_baskets_n"], 2)
        self.assertTrue(result["core_overlap"]["identical_baskets"])
        self.assertEqual(result["synthetic_population"]["primary_weighting"], "persona_equal")
        self.assertIsNone(result["synthetic_population"]["survey_weighted"])
        self.assertAlmostEqual(
            result["ce_source"]["weighted_overall_baskets"]["weighted"]["food"]["mean"],
            0.4,
        )
        diversity = result["full_population"]["weighting"]["persona_equal"]["candidate_pool_vs_synthetic_diversity"]
        self.assertEqual(diversity["candidate_donors_in_any_matched_pool"], 3)
        self.assertEqual(diversity["candidate_basket_signatures_in_any_matched_pool"], 3)
        self.assertIn("region", result["common_broad_groups"])
        self.assertTrue((out / "summary.json").is_file())
        self.assertTrue((out / "report.md").is_file())

    def test_survey_weights_are_posthoc_and_reported_separately(self):
        rows = [{"agent_id": agent_id, "target_month": 202105, "analysis_weight": weight}
                for agent_id, weight in zip(self.people, (1.0, 2.0, 7.0))]
        weight_path = self._weights_file(rows)
        original_baskets = json.loads(json.dumps(self.full_baskets))
        result = audit(self._args(self.root / "weighted_audit", weight_path))

        self.assertEqual(result["synthetic_population"]["primary_weighting"], "survey_weighted")
        self.assertEqual(result["synthetic_population"]["persona_equal"]["weight_sum"], 3.0)
        self.assertEqual(result["synthetic_population"]["survey_weighted"]["weight_sum"], 10.0)
        self.assertEqual(result["full_population"]["weighting"]["survey_weighted"]["weight_sum"], 10.0)
        self.assertEqual(self.full_baskets, original_baskets)
        self.assertIn("analysis_weights", result["input_sha256"])

    def test_rejects_analysis_weight_id_coverage_mismatch(self):
        rows = [{"agent_id": agent_id, "target_month": 202105, "analysis_weight": 1.0}
                for agent_id in list(self.people)[:-1]]
        with self.assertRaisesRegex(ValueError, "IDs do not exactly cover"):
            audit(self._args(self.root / "bad_weight_ids", self._weights_file(rows)))

    def test_rejects_analysis_weights_for_wrong_month(self):
        rows = [{"agent_id": agent_id, "target_month": 202106, "analysis_weight": 1.0}
                for agent_id in self.people]
        with self.assertRaisesRegex(ValueError, "month mismatch"):
            audit(self._args(self.root / "bad_weight_month", self._weights_file(rows)))

    def test_rejects_nonpositive_or_nonfinite_analysis_weight(self):
        rows = [{"agent_id": agent_id, "target_month": 202105, "analysis_weight": weight}
                for agent_id, weight in zip(self.people, (1.0, 0.0, float("nan")))]
        with self.assertRaisesRegex(ValueError, "positive and finite"):
            audit(self._args(self.root / "bad_weight_value", self._weights_file(rows)))

    def test_rejects_corrupt_candidate_pool_audit_fields(self):
        self.full_baskets["sce_u1"]["pool_n"] -= 1
        self._write_inputs()
        with self.assertRaisesRegex(ValueError, "donor, matched pool, fallback or assignment mismatch"):
            audit(self._args(self.root / "bad_audit"))

    def test_rejects_core_basket_that_differs_from_full_assignment(self):
        self.core_baskets["sce_u1"]["spending_shares"]["food"] += 0.01
        self._write_inputs()
        with self.assertRaises(ValueError):
            audit(self._args(self.root / "bad_core_audit"))


if __name__ == "__main__":
    unittest.main()
