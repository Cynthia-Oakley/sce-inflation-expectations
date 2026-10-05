import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from studies.sce_inflation_expectations.core_normal import build_expansion, distribution_errors
from scripts.expand_sce_core_normal import validate_packages


def population():
    def person(uid, age, education="college", employment="employed"):
        return {"agent_id": uid, "attributes": {"age_group": age, "education_group": education,
                                                "employment_status": employment}, "weight": 1.}
    return {"personas": [person("a", "young"), person("b", "old"),
                         person("c", "young"), person("d", "old")]}


class CoreNormalTest(unittest.TestCase):
    def setUp(self):
        self.pop = population()
        self.weights = {"a": 1., "b": 3., "c": 2., "d": 4.}

    def test_unpooled_exact_groups_and_mass_conservation(self):
        p = build_expansion(self.pop, ["a", "b"], ["a", "b"], self.weights, prior_strength=0)
        np.testing.assert_allclose(p.atom_weights(), [3., 7.])
        self.assertEqual(p.sample_normal_donors(seed=42, month=202105), {"c": "a", "d": "b"})
        self.assertEqual(p.report()["normal_n"], 2)

    def test_shrinkage_parent_excludes_own_cell(self):
        p = build_expansion(self.pop, ["a", "b"], ["a", "b"], self.weights, prior_strength=1)
        np.testing.assert_allclose(p.atom_weights(), [4., 6.])
        np.testing.assert_allclose(p.probabilities[p.cells["c"]], [.5, .5])
        self.assertEqual(p.support[p.cells["c"]]["parent_donors"], 1)

    def test_effective_sample_size_accounts_for_unequal_weights(self):
        self.pop["personas"][1]["attributes"]["age_group"] = "young"
        p = build_expansion(self.pop, ["a", "b"], ["a", "b"], self.weights, prior_strength=1)
        self.assertAlmostEqual(p.support[p.cells["c"]]["fine_effective_n"], 1.6)
        # No outside donor: use the local distribution even for positive strength.
        self.assertEqual(p.support[p.cells["c"]]["local_fraction"], 1)
        np.testing.assert_allclose(p.atom_weights(), [2.5, 7.5])

    def test_no_fine_support_explicitly_falls_back(self):
        self.pop["personas"][2]["attributes"]["education_group"] = "high_school"
        p = build_expansion(self.pop, ["a", "b"], ["a", "b"], self.weights)
        self.assertEqual(p.support[p.cells["c"]]["parent_level"], "global_other_cell")
        self.assertEqual(p.report()["normal_without_fine_support_n"], 1)
        self.assertAlmostEqual(p.report()["normal_without_fine_support_weight_fraction"], 1 / 3)
        np.testing.assert_allclose(p.probabilities[p.cells["c"]], [.25, .75])

    def test_invalid_core_is_excluded_not_converted_to_normal(self):
        p = build_expansion(self.pop, ["a", "b"], ["a"], self.weights)
        self.assertEqual(p.normal_ids, ("c", "d"))
        self.assertEqual(p.report()["core_without_joint_donor_n"], 1)
        self.assertAlmostEqual(p.atom_weights().sum(), 7)

    def test_census_does_not_invent_normal_or_prior(self):
        p = build_expansion(self.pop, list(self.weights), list(self.weights), self.weights)
        self.assertEqual(p.normal_ids, ())
        np.testing.assert_allclose(p.atom_weights(), [1, 3, 2, 4])
        self.assertEqual(p.sample_normal_donors(month=202105), {})

    def test_target_mask_is_evaluation_only(self):
        p = build_expansion(self.pop, ["a", "b"], ["a", "b"], self.weights, prior_strength=0)
        np.testing.assert_allclose(p.atom_weights(target_ids=["c"]), [2, 0])
        np.testing.assert_allclose(p.atom_weights(), [3, 7])

    def test_seed_and_input_order_are_reproducible(self):
        p = build_expansion(self.pop, ["a", "b"], ["a", "b"], self.weights)
        shuffled = copy.deepcopy(self.pop); shuffled["personas"].reverse()
        q = build_expansion(shuffled, ["b", "a"], ["b", "a"], self.weights)
        self.assertEqual(p.sample_normal_donors(seed=7, month=202105), q.sample_normal_donors(seed=7, month=202105))
        np.testing.assert_allclose(p.atom_weights(), q.atom_weights())

    def test_normal_outcomes_are_not_inputs(self):
        p = build_expansion(self.pop, ["a", "b"], ["a", "b"], self.weights)
        changed = copy.deepcopy(self.pop)
        for person in changed["personas"]:
            person["Q9_mean"] = 999
            person["attributes"]["real_q8"] = -999
        q = build_expansion(changed, ["a", "b"], ["a", "b"], self.weights)
        np.testing.assert_allclose(p.atom_weights(), q.atom_weights())

    def test_invalid_inputs_fail(self):
        for strength in [-1, float("nan")]:
            with self.assertRaises(ValueError):
                build_expansion(self.pop, ["a"], ["a"], self.weights, prior_strength=strength)
        for core, donors in [(["a"], []), (["a"], ["b"]), (["a", "a"], ["a"]), (["z"], ["z"])]:
            with self.assertRaises(ValueError):
                build_expansion(self.pop, core, donors, self.weights)
        with self.assertRaises(ValueError):
            build_expansion(self.pop, ["a"], ["a"], {**self.weights, "c": 0})

    def test_distribution_error_has_independent_expected_value(self):
        d = distribution_errors([0., 10.], [1., 1.], [5.], [1.])
        self.assertAlmostEqual(d["wasserstein_1_pp"], 5)
        self.assertAlmostEqual(d["std_bias_pp"], 5)
        self.assertAlmostEqual(d["mean_bias_pp"], 0)
        self.assertIn("effective_donor_mass_size", d["simulated"])
        self.assertNotIn("effective_sample_size", d["simulated"])


class CoreNormalPackageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.full, self.core = [Path(self.tmp.name) / p for p in ["full", "core"]]
        self.full.mkdir(); self.core.mkdir()
        p = population()
        meta = {"research_line": "A_historical_reconstruction", "design": "census", "selected_n": 4,
                "frame_n": 4, "target_month": 202105, "inclusion_probability": 1}
        for folder, pop, m in [(self.full, p, meta), (self.core, {"personas": p["personas"][:2]},
                                {**meta, "selected_n": 2, "design": "independent_srs", "inclusion_probability": .5})]:
            (folder / "population.json").write_text(json.dumps(pop))
            (folder / "sampling_meta.json").write_text(json.dumps(m))
        (self.full / "analysis_weights.jsonl").write_text("".join(json.dumps({"agent_id": r["agent_id"],
             "target_month": 202105, "inclusion_probability": 1, "survey_weight": 2, "analysis_weight": 2}) + "\n" for r in p["personas"]))

    def test_weights_are_separate_from_neutral_population(self):
        _, _, _, w = validate_packages(self.full, self.core)
        self.assertEqual(w, dict.fromkeys(["a", "b", "c", "d"], 2))

    def test_wrong_month_or_non_srs_design_fails(self):
        path = self.core / "sampling_meta.json"; old = json.loads(path.read_text())
        for change in [{"target_month": 202106}, {"design": "unknown_stratified"}, {"inclusion_probability": .8},
                       {"research_line": "B_future_prediction"}]:
            path.write_text(json.dumps({**old, **change}))
            with self.assertRaises(ValueError):
                validate_packages(self.full, self.core)

    def test_changed_core_profile_fails(self):
        path = self.core / "population.json"; p = json.loads(path.read_text())
        p["personas"][0]["attributes"]["age_group"] = "different"
        path.write_text(json.dumps(p))
        with self.assertRaises(ValueError):
            validate_packages(self.full, self.core)

    def test_duplicate_or_non_census_sidecar_fails(self):
        path = self.full / "analysis_weights.jsonl"; lines = path.read_text().splitlines()
        path.write_text("\n".join(lines + [lines[0]]))
        with self.assertRaises(ValueError):
            validate_packages(self.full, self.core)
        rows = [json.loads(s) for s in lines]; rows[0]["inclusion_probability"] = .5
        path.write_text("\n".join(json.dumps(r) for r in rows))
        with self.assertRaises(ValueError):
            validate_packages(self.full, self.core)


if __name__ == "__main__":
    unittest.main()
