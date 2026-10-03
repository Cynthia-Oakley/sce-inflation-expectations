"""Tests for the local SCE study model (studies/sce_inflation_expectations/model.py).

Covers: scripted parity with the cloud v3 golden answers, the observation audit
sidecar (real newlines + self-consistent hashes), response parsing/validation,
and the audited openai decision path with an injected fake client (no network).
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from socioverse.schemas import EnvironmentBundle  # noqa: E402

from studies.sce_inflation_expectations.model import (  # noqa: E402
    Q9_KEYS, SCEDecision, SCEEnvironmentProvider, build_sce_messages,
    parse_sce_response, validate_sce_bins,
)

STUDY_DIR = REPO_ROOT / "studies" / "sce_inflation_expectations"


def _env(audit_dir: Path | None = None, run_id: str = "") -> SCEEnvironmentProvider:
    bundle = EnvironmentBundle.model_validate(
        json.loads((STUDY_DIR / "environment" / "environment.json").read_text(encoding="utf-8")))
    if audit_dir is not None:
        bundle.provider_args["audit_dir"] = str(audit_dir)
        bundle.provider_args["run_id"] = run_id
    env = SCEEnvironmentProvider(bundle)
    env.reset(42)
    return env


def _obs(env: SCEEnvironmentProvider, agent_id: str = "smoke_001", t: int = 1):
    env.advance_to(t)
    return env.observe_batch([agent_id], t)[0]


# ---- fake OpenAI client -----------------------------------------------------

def _fake_response(content: str, model: str = "deepseek-flash", req_id: str = "req-1"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")],
        model=model, id=req_id, system_fingerprint="fp-test",
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150))


class _FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.kwargs_log = []

    def create(self, **kwargs):
        self.kwargs_log.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _openai_decision(outcomes, audit_dir: Path, run_id: str = "test-run", **overrides):
    args = dict(llm_kind="openai", model="deepseek-flash", max_calls=10, retry_max=1,
                extra_body={"thinking": {"type": "disabled"}},
                price_input_per_mtok=0.30, price_output_per_mtok=1.20,
                run_id=run_id, audit_dir=str(audit_dir))
    args.update(overrides)
    decision = SCEDecision(**args)
    fake = _FakeCompletions(outcomes)
    decision.llm._client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return decision, fake


def _llm_rows(audit_dir: Path):
    path = audit_dir / "llm_calls.jsonl"
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


class ScriptedParityTest(unittest.TestCase):
    """Golden values from the cloud v3 archive (2026-10-01, 40 answers)."""

    def test_smoke_001_month1(self):
        env = _env()
        action = SCEDecision(seed=42).decide_batch([_obs(env, t=1)], {})[0]
        p = action.payload
        self.assertEqual(action.source, "rule")
        self.assertEqual(p["point_pct"], 1.28)
        self.assertEqual([p[k] for k in Q9_KEYS], [0, 0, 0, 28, 52, 20, 0, 0, 0, 0])
        self.assertEqual(p["validation_status"], "valid")
        self.assertEqual(p["target_month"], "2021-05")

    def test_smoke_001_month2(self):
        env = _env()
        action = SCEDecision(seed=42).decide_batch([_obs(env, t=2)], {})[0]
        p = action.payload
        self.assertEqual(p["point_pct"], 2.26)
        self.assertEqual(p["target_month"], "2021-06")
        self.assertEqual(p["e_snapshot_id"], "bls_initial_release_e_2021-06")


class ObservationAuditTest(unittest.TestCase):
    def test_real_newlines_and_self_consistent_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _env(Path(tmp), "audit-run")
            _obs(env, t=1)
            text = (Path(tmp) / "observations.jsonl").read_text(encoding="utf-8")
            rows = text.splitlines()
            self.assertEqual(len(rows), 1)
            self.assertNotIn("\\n", rows[0][-3:])
            row = json.loads(rows[0])
            self.assertEqual(row["run_id"], "audit-run")
            import hashlib
            raw = json.dumps(row["observation"], ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"))
            self.assertEqual(row["observation_sha256"],
                             hashlib.sha256(raw.encode()).hexdigest())


class ParseValidateTest(unittest.TestCase):
    def test_valid_json(self):
        obj, err = parse_sce_response(json.dumps({
            "point_pct": 2.5, "q9": {f"bin{i}": 10 for i in range(1, 11)}, "reason": "ok"}))
        self.assertIsNone(err)
        self.assertEqual(obj["point_pct"], 2.5)
        self.assertEqual(len(obj["bins"]), 10)

    def test_fenced_json(self):
        obj, err = parse_sce_response('```json\n{"point_pct": 1.0, "q9": {' +
                                      ", ".join(f'"bin{i}": 10' for i in range(1, 11)) + '}}```')
        self.assertIsNone(err)

    def test_bad_inputs(self):
        self.assertEqual(parse_sce_response("")[1], "empty_response")
        self.assertEqual(parse_sce_response("hello")[1], "not_json")
        self.assertTrue(parse_sce_response('{"q9": {}}')[1].startswith("missing_or_bad_point"))
        self.assertTrue(parse_sce_response('{"point_pct": 1}')[1].startswith("missing_q9"))
        self.assertTrue(parse_sce_response('{"point_pct": 1, "q9": {"bin1": 50}}')[1]
                        .startswith("missing_or_bad_q9_bin2"))

    def test_validate_bins(self):
        ok, err, s = validate_sce_bins([10.0] * 10)
        self.assertTrue(ok)
        self.assertEqual(s, 100.0)
        ok, err, _ = validate_sce_bins([101.0] + [0.0] * 9)
        self.assertFalse(ok)
        self.assertEqual(err, "bin_out_of_range")
        ok, err, _ = validate_sce_bins([10.0] * 9 + [20.0])
        self.assertFalse(ok)
        self.assertTrue(err.startswith("q9_sum_"))


class OpenAIDecisionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.audit = Path(self.tmp.name)
        self.env = _env()

    def _valid_reply(self, point=2.5):
        return json.dumps({"point_pct": point,
                           "q9": {f"bin{i}": 10 for i in range(1, 11)},
                           "reason": "test reason"})

    def test_requires_model_and_budget(self):
        with self.assertRaises(ValueError):
            SCEDecision(llm_kind="openai", max_calls=10)
        with self.assertRaises(ValueError):
            SCEDecision(llm_kind="openai", model="x", max_calls=0)

    def test_valid_first_try(self):
        decision, fake = _openai_decision([_fake_response(self._valid_reply())], self.audit)
        action = decision.decide_batch([_obs(self.env, t=1)], {})[0]
        p = action.payload
        self.assertEqual(action.source, "llm")
        self.assertEqual(p["validation_status"], "valid")
        self.assertEqual(p["point_pct"], 2.5)
        self.assertEqual(p["llm"]["returned_model"], "deepseek-flash")
        self.assertEqual(p["llm"]["attempts"], 1)
        self.assertEqual(fake.kwargs_log[0]["extra_body"], {"thinking": {"type": "disabled"}})
        self.assertEqual(fake.kwargs_log[0]["response_format"], {"type": "json_object"})
        rows = _llm_rows(self.audit)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        for key in ("prompt_text", "prompt_sha256", "raw_response_text", "raw_response_sha256",
                    "requested_model", "returned_model", "request_id", "system_fingerprint",
                    "usage", "finish_reason", "code_sha256", "timestamp_utc"):
            self.assertIn(key, row)
        self.assertEqual(row["usage"]["total_tokens"], 150)
        self.assertIsNone(row["error"])
        self.assertEqual(decision.call_count, 1)
        self.assertAlmostEqual(decision.estimated_cost_usd(),
                               (100 * 0.30 + 50 * 1.20) / 1e6, places=9)

    def test_invalid_then_retry_valid(self):
        bad = json.dumps({"point_pct": 2.0, "q9": {f"bin{i}": 5 for i in range(1, 11)}})
        decision, _ = _openai_decision(
            [_fake_response(bad), _fake_response(self._valid_reply(), req_id="req-2")], self.audit)
        action = decision.decide_batch([_obs(self.env, t=1)], {})[0]
        self.assertEqual(action.payload["validation_status"], "valid")
        self.assertEqual(action.payload["llm"]["attempts"], 2)
        self.assertEqual(decision.call_count, 2)
        self.assertEqual(len(_llm_rows(self.audit)), 2)

    def test_invalid_twice_keeps_raw_no_normalization(self):
        bad = json.dumps({"point_pct": 2.0, "q9": {f"bin{i}": 5 for i in range(1, 11)}})
        decision, _ = _openai_decision([_fake_response(bad), _fake_response(bad)], self.audit)
        action = decision.decide_batch([_obs(self.env, t=1)], {})[0]
        p = action.payload
        self.assertEqual(action.source, "llm")
        self.assertEqual(p["llm"]["outcome"], "invalid")
        self.assertEqual(p["validation_status"], "invalid")
        self.assertEqual(p["q9_sum"], 50.0)  # raw evidence, NOT renormalized to 100
        self.assertEqual([p[k] for k in Q9_KEYS], [5.0] * 10)

    def test_api_error_no_fallback(self):
        decision, _ = _openai_decision([RuntimeError("boom"), RuntimeError("boom2")], self.audit)
        action = decision.decide_batch([_obs(self.env, t=1)], {})[0]
        p = action.payload
        self.assertEqual(action.source, "llm")
        self.assertEqual(p["llm"]["outcome"], "error")
        self.assertEqual(p["validation_status"], "error")
        self.assertIn("boom2", p["llm"]["error"])
        rows = _llm_rows(self.audit)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["error"] for r in rows))
        self.assertGreater(decision.reserved_cost_usd, 0.0)  # conservative reservation

    def test_max_calls_cap(self):
        bad = json.dumps({"point_pct": 2.0, "q9": {f"bin{i}": 5 for i in range(1, 11)}})
        decision, fake = _openai_decision([_fake_response(bad)], self.audit, max_calls=1)
        action = decision.decide_batch([_obs(self.env, t=1)], {})[0]
        self.assertEqual(action.payload["llm"]["error"], "max_calls_exceeded")
        self.assertEqual(len(fake.kwargs_log), 1)

    def test_prompt_too_long_rejected_without_call(self):
        decision, fake = _openai_decision([], self.audit, max_prompt_chars=10)
        action = decision.decide_batch([_obs(self.env, t=1)], {})[0]
        self.assertEqual(action.payload["validation_status"], "error")
        self.assertEqual(action.payload["llm"]["error"], "prompt_too_long")
        self.assertEqual(len(fake.kwargs_log), 0)
        self.assertEqual(decision.call_count, 0)


class PromptTest(unittest.TestCase):
    def test_prompt_contains_whitelist_only(self):
        env = _env()
        ob = _obs(env, t=1)
        text = build_sce_messages(ob)[0]["content"]
        self.assertIn("2021-05", text)
        self.assertIn("2.6%", text)  # BLS CPI y/y signal
        self.assertIn("under $35,000", text)  # smoke_001 income band
        self.assertNotIn("weight", text.lower())
        self.assertNotIn("SCE", text)  # no survey results leak


if __name__ == "__main__":
    unittest.main()
