"""Budget regressions use the existing fake client; no API calls."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.run_sce_local import _artifact_location, _save_source_snapshot
from studies.sce_inflation_expectations.model import SCEDecision, build_sce_messages
from tests.test_sce_local_model import _env, _obs, _openai_decision, _fake_response


class SCEBudgetTest(unittest.TestCase):
    def test_remaining_budget_checked_before_request(self):
        with tempfile.TemporaryDirectory() as td:
            decision, fake = _openai_decision([], Path(td), cost_cap_usd=.00001)
            action = decision.decide_batch([_obs(_env())], {})[0]
            self.assertEqual(action.payload["llm"]["error"], "cost_cap_exceeded")
            self.assertEqual(decision.call_count, 0)
            self.assertEqual(fake.kwargs_log, [])

    def test_error_without_usage_reserves_bytes_and_full_output(self):
        with tempfile.TemporaryDirectory() as td:
            decision, fake = _openai_decision([RuntimeError("timeout")], Path(td), retry_max=0)
            decision.decide_batch([_obs(_env())], {})
            text = json.dumps(fake.kwargs_log[0]["messages"], ensure_ascii=False)
            expected = ((len(text.encode("utf-8")) + 256) * .30 + 1024 * 1.20) / 1e6
            self.assertAlmostEqual(decision.reserved_cost_usd, expected)

    def test_retry_cannot_spend_beyond_remaining_reserve(self):
        with tempfile.TemporaryDirectory() as td:
            ob = _obs(_env())
            bad = json.dumps({"point_pct": 2, "q9": {f"bin{i}": 5 for i in range(1, 11)}})
            decision, fake = _openai_decision([_fake_response(bad)], Path(td))
            bound = decision._request_cost_bound(json.dumps(build_sce_messages(ob), ensure_ascii=False))
            decision.cost_cap_usd = bound
            action = decision.decide_batch([ob], {})[0]
            self.assertEqual(len(fake.kwargs_log), 1)
            self.assertEqual(action.payload["llm"]["error"], "cost_cap_exceeded")

    def test_cost_cap_requires_prices(self):
        with self.assertRaises(ValueError):
            SCEDecision(llm_kind="openai", model="test", max_calls=1, cost_cap_usd=1)

    def test_external_input_is_recorded_by_actual_absolute_path(self):
        base = Path("/tmp/runtime/study")
        self.assertEqual(_artifact_location(base / "population/p.json", base), "population/p.json")
        self.assertEqual(_artifact_location(Path("/tmp/inputs/p.json"), base), "/private/tmp/inputs/p.json" if Path('/tmp').resolve() == Path('/private/tmp') else "/tmp/inputs/p.json")

    def test_source_snapshot_survives_later_edit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime, audit = root / "runtime", root / "audit"
            runtime.mkdir()
            audit.mkdir()
            (runtime / "model.py").write_text("version = 1\n")
            (runtime / "study.yaml").write_text("study_id: test\n")
            (runtime / ".env").write_text("secret=not-exported\n")
            hashes = _save_source_snapshot(runtime, audit)
            (runtime / "model.py").write_text("version = 2\n")
            self.assertEqual((audit / "source_snapshot/study/model.py").read_text(), "version = 1\n")
            self.assertIn("source_snapshot/study/model.py", hashes)
            self.assertFalse((audit / "source_snapshot/study/.env").exists())


if __name__ == "__main__":
    unittest.main()
