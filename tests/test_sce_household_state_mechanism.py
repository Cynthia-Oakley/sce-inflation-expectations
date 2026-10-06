from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from socioverse.schemas import EnvironmentBundle, Persona
from studies.sce_inflation_expectations.household_state_mechanism import (
    SCHEMA, PROMPT_VERSION, validate_bundle, build_household_state_messages,
)
from studies.sce_inflation_expectations.model import SCEEnvironmentProvider, SCEDecision, build_sce_messages_v2
from studies.sce_inflation_expectations.price_experience import profile_hash
from scripts.run_sce_household_state_trial import select_ids

ROOT = Path(__file__).resolve().parents[1]
PROFILE = {"age_group": "Under 40", "region": "West", "education_group": "college"}


def bundle():
    return {"schema_version": SCHEMA, "research_line": "A_historical_reconstruction",
            "source": "SCE_Q1_current_microdata", "target_month": "2021-05",
            "state_by_id": {"a": {"agent_id": "a", "target_month": "2021-05",
                                  "financial_change_12m_code": 1, "profile_sha256": profile_hash(PROFILE)}}}


def observation(with_state=True):
    raw = json.loads((ROOT / "studies/sce_inflation_expectations/environment/environment_dev2021_05_06_v2.json").read_text())
    raw["provider_args"]["persona_by_id"] = {"a": PROFILE}
    if with_state:
        raw["provider_args"]["household_state_by_id"] = bundle()["state_by_id"]
    provider = SCEEnvironmentProvider(EnvironmentBundle.model_validate(raw))
    provider.reset(42)
    provider.advance_to(1)
    return provider.observe_batch(["a"], 1)[0]


class HouseholdStateTest(unittest.TestCase):
    def test_rejects_targets_forecast_stale_profile_and_bad_codes(self):
        p = [Persona(agent_id="a", attributes=PROFILE)]
        validate_bundle(bundle(), p, "2021-05")
        for change in ("target", "forecast", "hash", "code", "coverage"):
            bad = bundle()
            if change == "target": bad["state_by_id"]["a"]["Q9_mean"] = 5
            if change == "forecast": bad["research_line"] = "B_forecast"
            if change == "hash": bad["state_by_id"]["a"]["profile_sha256"] = "wrong"
            if change == "code": bad["state_by_id"]["a"]["financial_change_12m_code"] = True
            if change == "coverage": bad["state_by_id"] = {}
            with self.assertRaises(ValueError): validate_bundle(bad, p, "2021-05")

    def test_only_state_block_changes_no_public_facts_question_or_ids(self):
        ob = observation()
        baseline_ob = observation(False)
        self.assertEqual(ob.macro_information, baseline_ob.macro_information)
        base = build_sce_messages_v2(ob, include_event_abstracts=True)
        text = build_household_state_messages(ob, base)[0]["content"]
        prefix, questions = base[0]["content"].split("Question 1 (point estimate):", 1)
        self.assertTrue(text.startswith(prefix))
        self.assertEqual(text.split("Question 1 (point estimate):", 1)[1], questions)
        self.assertIn("financial situation is much worse", text)
        self.assertNotIn("Happiness", text)
        self.assertNotIn("state_sha256", text)
        self.assertEqual(base, build_sce_messages_v2(ob, include_event_abstracts=True))

    def test_actual_decision_provider_receives_state_and_audits_no_real_api(self):
        ob = observation()
        sent = []
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "point_pct": 3, "q9": {f"bin{i}": 10 for i in range(1, 11)}})), finish_reason="stop")],
            model="offline-fake", id="offline-1", system_fingerprint=None,
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10, total_tokens=20))
        def create(**kwargs):
            sent.append(kwargs)
            return response
        with tempfile.TemporaryDirectory() as tmp:
            decision = SCEDecision(llm_kind="openai", model="offline-fake", prompt_version=PROMPT_VERSION,
                                   max_calls=1, audit_dir=tmp, run_id="offline-state")
            decision.llm._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
            action = decision.decide_batch([ob], {})[0]
            self.assertEqual(action.payload["validation_status"], "valid")
            self.assertIn("financial situation is much worse", sent[0]["messages"][0]["content"])
            self.assertEqual(action.payload["household_state_source"], "SCE_Q1_current_microdata")
            self.assertTrue((Path(tmp) / "llm_calls.jsonl").exists())

    def test_silent_unused_treatment_fails_before_request(self):
        d = SCEDecision(llm_kind="openai", model="offline-fake", max_calls=1, prompt_version="sce-q8-q9-v2-abstract")
        with self.assertRaisesRegex(ValueError, "Q1 observation"):
            d.decide_batch([observation()], {})
        self.assertEqual(d.call_count, 0)

    def test_selection_is_order_independent_and_excludes_answer_fields(self):
        rows = [{"date": 202105, "userid": 10*c+i, "Q1": c} for c in range(1, 6) for i in range(3)]
        ids = {f"sce_u{r['userid']}" for r in rows}
        self.assertEqual(select_ids(rows, ids, "202105", 2), select_ids(list(reversed(rows)), ids, "202105", 2))
        bad = deepcopy(rows)
        bad[0]["Q9_mean"] = 10
        with self.assertRaisesRegex(ValueError, "whitelist"):
            select_ids(bad, ids, "202105", 2)
        with self.assertRaisesRegex(ValueError, "insufficient"):
            select_ids(rows, ids, "202105", 4)


if __name__ == "__main__":
    unittest.main()
