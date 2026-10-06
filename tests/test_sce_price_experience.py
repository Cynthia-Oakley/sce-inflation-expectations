"""Independent arithmetic, joint-donor, information and actual fake-client gates."""
from copy import deepcopy
import csv
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from socioverse.schemas import EnvironmentBundle, PopulationBundle
from studies.sce_inflation_expectations.price_experience import (
    normalize_ce_row, prepare_ce_donors, BasketAssigner, profile_hash,
)
from studies.sce_inflation_expectations.experience_mechanism import (
    build_experience_view, build_mechanism_messages, validate_config, PROMPT_VERSION,
)
from studies.sce_inflation_expectations.model import (
    SCEEnvironmentProvider, SCEDecision, build_sce_messages_v2,
)
from scripts.build_sce_price_experience import build
from scripts.prepare_sce_mechanism_pilot import prepare

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "studies/sce_inflation_expectations"


def config(arm="basket_focus"):
    return json.loads((STUDY / "mechanism" / f"{arm}.json").read_text())


def row(id="unit-1", **overrides):
    d = dict(NEWID=id, AGE_REF=35, EDUC_REF=12, CUTENURE=4, REGION=1,
             FINCBTXM=60000, FINLWT21=2, TOTEXPPQ=400, TOTEXPCQ=600,
             FOODPQ=80, FOODCQ=120, GASMOPQ=20, GASMOCQ=30,
             SHELTPQ=120, SHELTCQ=180, QINTRVYR=2020, QINTRVMO=10)
    return {k: str(v) for k, v in {**d, **overrides}.items()}


PROFILE = {"age_group": "Under 40", "education_group": "high_school",
           "housing_tenure": "renter", "region": "Northeast", "household_income_band": "50k_to_100k"}


def basket(profile=PROFILE):
    return BasketAssigner([normalize_ce_row(row())],
                          {"source_url": "https://example.test/public-ce", "data_sha256": "fixture",
                           "interview_wave": "2020Q4"}, min_pool=1).assign("test-1", profile)


def environment(arm="basket_focus"):
    raw = json.loads((STUDY / "environment/environment_dev2021_05_06_v2.json").read_text())
    raw["provider_args"].update(persona_by_id={"test-1": PROFILE},
                                experience_by_id={"test-1": basket()},
                                price_experience_mechanism=config(arm))
    provider = SCEEnvironmentProvider(EnvironmentBundle.model_validate(raw))
    provider.reset(42)
    provider.advance_to(1)
    return provider


class DonorTest(unittest.TestCase):
    def test_hand_computed_three_month_shares_and_codes(self):
        d = normalize_ce_row(row())
        self.assertEqual(d["spending_shares"], {"food": .2, "gasoline": .05, "shelter": .3, "other": .45})
        self.assertEqual(d["reported_expenditure_usd"], 1000)
        self.assertEqual(d["attributes"], PROFILE)
        for code in (0, 10, 11, 12):
            self.assertEqual(normalize_ce_row(row(EDUC_REF=code))["attributes"]["education_group"], "high_school")
        for code in (13, 14):
            self.assertEqual(normalize_ce_row(row(EDUC_REF=code))["attributes"]["education_group"], "some_college")
        for code in (15, 16):
            self.assertEqual(normalize_ce_row(row(EDUC_REF=code))["attributes"]["education_group"], "college")
        self.assertNotIn("education_group", normalize_ce_row(row(EDUC_REF=17))["attributes"])
        self.assertEqual(normalize_ce_row(row(CUTENURE=5))["attributes"]["housing_tenure"], "other")

    def test_invalid_row_is_audited_but_schema_is_fatal(self):
        donors, audit = prepare_ce_donors([row(), row("bad", TOTEXPPQ=-600, TOTEXPCQ=600)])
        self.assertEqual((len(donors), audit["excluded_n"]), (1, 1))
        incomplete = row(); incomplete.pop("FOODPQ")
        with self.assertRaisesRegex(ValueError, "missing CE columns"):
            prepare_ce_donors([incomplete])
        with self.assertRaisesRegex(ValueError, "unique"):
            prepare_ce_donors([row(), row()])

    def test_joint_draw_stability_backoff_and_answer_exclusion(self):
        donors, _ = prepare_ce_donors([row("a"), row("b", FOODPQ=0, FOODCQ=0,
                                      GASMOPQ=100, GASMOCQ=200, SHELTPQ=0, SHELTCQ=0)])
        source = {"source_url": "https://example.test", "data_sha256": "fixture", "interview_wave": "2020Q4"}
        assign = BasketAssigner(donors, source, min_pool=2)
        bad_profile = {**PROFILE, "education_group": "college"}
        b = assign.assign("one", bad_profile)
        self.assertEqual(b["relaxed_fields"], ["education_group"])
        self.assertEqual(b["pool_n"], 2)
        self.assertEqual(b["pool_effective_n"], 2)
        self.assertIn(b["spending_shares"], [d["spending_shares"] for d in donors])
        self.assertEqual(b, BasketAssigner(list(reversed(donors)), source, min_pool=2).assign("one", bad_profile))
        self.assertEqual(b, assign.assign("one", {**bad_profile, "Q8": 999, "Q9": [999], "weight": 99}))
        self.assertEqual(b["profile_sha256"], profile_hash(bad_profile))
        updated = assign.assign("one", {**bad_profile, "numeracy": "low", "employment_status": "retired"})
        self.assertEqual(updated["donor_id"], b["donor_id"])
        self.assertEqual(updated["spending_shares"], b["spending_shares"])
        self.assertNotEqual(updated["profile_sha256"], b["profile_sha256"])
        weighted = deepcopy(donors); weighted[0]["sampling_weight"] = 6
        w = BasketAssigner(weighted, source, min_pool=2).assign("one", bad_profile)
        self.assertEqual(w["conditional_draw_probability"], .75 if w["donor_id"] == "a" else .25)


class MechanismTest(unittest.TestCase):
    def test_all_facts_and_questionnaire_retained_with_changes_isolated(self):
        env = environment()
        ob = env.observe_batch(["test-1"], 1)[0]
        original = ob.macro_information
        info = deepcopy(original)
        info["events"] = [dict(event_id="oil", pub_date="2021-05-01", headline="Oil prices surge", abstract="Fuel prices"),
                          dict(event_id="rent", pub_date="2021-05-01", headline="Rents rise", abstract="Housing costs"),
                          dict(event_id="food", pub_date="2021-05-01", headline="Groceries rise", abstract="Food prices")]
        hashes = set()
        prompts = {}
        for arm in ("expression_shared", "basket_shared", "focus_only", "basket_focus"):
            view, state = build_experience_view(PROFILE, info, config(arm), basket())
            hashes.add(state["public_fact_ledger_sha256"])
            self.assertEqual(view["signals"], info["signals"])
            self.assertEqual({e["event_id"] for e in view["events"]}, {"oil", "rent", "food"})
            if "focus" in arm:
                self.assertEqual([e["event_id"] for e in view["events"]], ["rent", "food", "oil"])
            altered = ob.model_copy(deep=True)
            altered.macro_information = view
            altered.local_information = {"price_experience": state}
            base = build_sce_messages_v2(altered, include_event_abstracts=True)
            text = build_mechanism_messages(altered, base)[0]["content"]
            prompts[arm] = text
            self.assertEqual(text[text.index("Question 1 (point estimate):"):],
                             base[0]["content"][base[0]["content"].index("Question 1 (point estimate):"):])
            self.assertEqual("Synthetic household spending context" in text, "basket" in arm)
            for e in info["events"]:
                self.assertIn(e["headline"], text)
                self.assertIn(e["abstract"], text)
        self.assertEqual(len(hashes), 1)
        focus = prompts["focus_only"]
        self.assertLess(focus.index("- Rent/shelter prices"), focus.index("- Food prices"))
        self.assertLess(focus.index("- Food prices"), focus.index("- Regular gasoline price"))

    def test_no_truth_prior_answer_or_unvalidated_profile(self):
        env = environment()
        env.answers["test-1"] = {"point_pct": 12345}
        ob = env.observe_batch(["test-1"], 1)[0]
        self.assertEqual(ob.local_physical["prior_answer"], {})
        bad = basket(); bad["profile_sha256"] = "different"
        with self.assertRaisesRegex(ValueError, "different profile"):
            build_experience_view(PROFILE, ob.macro_information, config(), bad)
        with self.assertRaisesRegex(ValueError, "materialized"):
            build_experience_view(PROFILE, ob.macro_information, config(), None)
        bad = basket(); bad["spending_shares"]["food"] = float("nan")
        with self.assertRaisesRegex(ValueError, "shares"):
            build_experience_view(PROFILE, ob.macro_information, config(), bad)
        wrong = config(); wrong["research_line"] = "B_forecast"
        with self.assertRaisesRegex(ValueError, "retrospective"):
            validate_config(wrong)

    def test_time_and_source_integrity_gates(self):
        info = environment().observe_batch(["test-1"], 1)[0].macro_information
        future = deepcopy(info); future["signals"][0]["published_at"] = "2022-01-01T00:00:00-05:00"
        with self.assertRaisesRegex(ValueError, "unavailable"):
            build_experience_view(PROFILE, future, config(), basket())
        dupe = deepcopy(info); dupe["signals"].append(dupe["signals"][0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_experience_view(PROFILE, dupe, config(), basket())
        intraday = deepcopy(info); intraday["as_of"] = "2021-05-12T15:00:00-04:00"
        intraday["events"] = [dict(event_id="x", pub_date="2021-05-12", headline="x")]
        with self.assertRaisesRegex(ValueError, "within-day"):
            build_experience_view(PROFILE, intraday, config(), basket())

    def test_actual_llm_provider_uses_mechanism_prompt_and_audit(self):
        ob = environment().observe_batch(["test-1"], 1)[0]
        reply = json.dumps({"point_pct": 2, "q9": {f"bin{i}": 10 for i in range(1,11)}})
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply), finish_reason="stop")],
                                   model="offline-fake", id="fake-1", system_fingerprint=None,
                                   usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10, total_tokens=20))
        sent = []
        def create(**kwargs):
            sent.append(kwargs)
            return response
        with tempfile.TemporaryDirectory() as temp:
            decision = SCEDecision(llm_kind="openai", model="offline-fake", max_calls=1,
                                   prompt_version=PROMPT_VERSION, audit_dir=temp, run_id="offline-test")
            decision.llm._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
            action = decision.decide_batch([ob], {})[0]
            self.assertEqual(action.payload["mechanism_arm"], "basket_focus")
            self.assertEqual(action.payload["point_pct"], 2)
            self.assertIn("food 20.0%", sent[0]["messages"][0]["content"])
            self.assertIn("shelter 30.0%", sent[0]["messages"][0]["content"])
            self.assertTrue((Path(temp)/"llm_calls.jsonl").exists())

    def test_direct_framework_use_cannot_silently_ignore_treatment(self):
        ob = environment().observe_batch(["test-1"], 1)[0]
        decision = SCEDecision(llm_kind="openai", model="offline-fake", max_calls=1,
                               prompt_version="sce-q8-q9-v2-abstract")
        with self.assertRaisesRegex(ValueError, "requires the experience prompt"):
            decision.decide_batch([ob], {})
        self.assertEqual(decision.call_count, 0)


class BuilderTest(unittest.TestCase):
    def test_actual_offline_builder_and_wrong_wave(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            data = temp / "fmli204.csv"
            with data.open("w") as f:
                writer = csv.DictWriter(f, fieldnames=list(row()))
                writer.writeheader(); writer.writerow(row())
            raw = json.loads((STUDY / "population/population.json").read_text())
            raw["personas"] = raw["personas"][:1]
            PopulationBundle.model_validate(raw)
            pop = temp / "population.json"; pop.write_text(json.dumps(raw))
            e = json.loads((STUDY / "environment/environment_dev2021_05_06_v2.json").read_text())
            e["provider_args"]["targets"] = e["provider_args"]["targets"][:1]
            e["information_program"]["broadcasts"] = [b for b in e["information_program"]["broadcasts"] if b["at_step"] == 0]
            env = temp / "environment.json"; env.write_text(json.dumps(e))
            args = SimpleNamespace(ce_data=str(data), member=None, wave="2020Q4", source_url="https://example.test",
                                   official_url=None, release_date="2021-09-09", population=str(pop),
                                   environment=str(env), output=str(temp/"built"), seed=42, min_pool=1)
            summary = build(args)
            self.assertEqual(summary["agent_count"], 1)
            self.assertEqual(summary["llm_calls"], 0)
            self.assertEqual(len(summary["arms"]), 4)
            self.assertTrue((temp/"built/experience.json").exists())
            sim_raw = json.loads((STUDY / "simulation/simulation.json").read_text())
            sim_raw["n_steps"] = 1
            sim = temp / "simulation.json"; sim.write_text(json.dumps(sim_raw))
            pilot = prepare(pop, env, sim, temp/"built/experience.json", temp/"pilot", n=1)
            self.assertEqual(pilot["n"], 1)
            self.assertFalse(pilot["outcomes_read"])
            self.assertFalse(pilot["normal_expansion"])
            original_baskets = json.loads((temp/"built/experience.json").read_text())["experience_by_id"]
            self.assertEqual(json.loads((temp/"pilot/experience.json").read_text())["experience_by_id"], original_baskets)
            with self.assertRaisesRegex(ValueError, "invalid pilot"):
                prepare(pop, env, sim, temp/"built/experience.json", temp/"bad-pilot", n=2)
            self.assertFalse((temp/"bad-pilot").exists())
            args.wave = "2020Q3"; args.output = str(temp/"wrong-wave")
            with self.assertRaisesRegex(ValueError, "declared single"):
                build(args)
            self.assertFalse((temp/"wrong-wave").exists())


if __name__ == "__main__":
    unittest.main()
