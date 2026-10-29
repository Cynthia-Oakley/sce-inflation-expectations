"""No external requests: prove default preview, bounds, and credential handling."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from studies.sce_inflation_expectations.submission_tools.reviewer_single_request import MODEL, ROUTE, DESTINATION, load, run


def fixture(base):
    folder = base / "inputs"; folder.mkdir()
    messages = [dict(role="user", content="A synthetic offline-test questionnaire")]
    sha = hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()
    sample = dict(messages=messages, ready_for_exact_single_request=True, withheld=[],
                  original_prompt_sha256=sha, delivered_prompt_sha256=sha)
    settings = dict(model=MODEL, destination=DESTINATION, route=ROUTE, expected_provider="SiliconFlow",
        temperature=.5, max_tokens=1024, response_format="json_object",
        request_extra_body={"provider": dict(order=[ROUTE], allow_fallbacks=False, require_parameters=True,
            max_price=dict(prompt=.259, completion=.8)), "reasoning": dict(enabled=False)})
    (folder / "one_complete_prompt_example.json").write_text(json.dumps(sample))
    (folder / "generation_settings.json").write_text(json.dumps(settings))
    refresh(folder)
    return folder


def refresh(folder):
    files = {name: dict(sha256=hashlib.sha256((folder / name).read_bytes()).hexdigest())
             for name in ("one_complete_prompt_example.json", "generation_settings.json")}
    (folder / "candidate_manifest.json").write_text(json.dumps(dict(files=files)))


class ReviewerRequestTests(unittest.TestCase):
    def test_default_preview_does_not_read_credentials_or_invoke_sender(self):
        with tempfile.TemporaryDirectory() as temp:
            inputs = fixture(Path(temp))
            with patch("os.environ.get", side_effect=AssertionError("No credential read in preview")):
                result = run(inputs, sender=lambda *x: self.fail("No request in preview"))
            self.assertEqual(result["new_API_calls"], 0)
            self.assertFalse(result["credentials_read"])

    def test_one_injected_attempt_is_saved_without_secret_or_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); inputs = fixture(base); calls = []
            def send(messages, settings, key):
                calls.append(True)
                return dict(model=MODEL, provider="SiliconFlow", response_text='{"point_pct":3}',
                    usage=dict(cost=.0001, Authorization=key), Authorization=key)
            with patch.dict("os.environ", {"OPENROUTER_API_KEY": "private-test-credential"}):
                result = run(inputs, confirm_paid=True, out=base / "run", sender=send)
                with self.assertRaises(FileExistsError):
                    run(inputs, confirm_paid=True, out=base / "run", sender=send)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result["api_attempts"], 1)
            self.assertEqual(result["automatic_retries"], 0)
            self.assertFalse(result["actual_model_results"])
            self.assertNotIn("private-test-credential", "".join(p.read_text() for p in (base / "run").iterdir()))

    def test_error_text_cannot_leak_key_and_no_second_attempt_is_made(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); inputs = fixture(base); calls = []
            def send(messages, settings, key):
                calls.append(True)
                raise TimeoutError("Authorization: " + key)
            with patch.dict("os.environ", {"OPENROUTER_API_KEY": "private-test-credential"}):
                result = run(inputs, confirm_paid=True, out=base / "run", sender=send)
            self.assertEqual(result["status"], "request_failed_no_retry")
            self.assertEqual(len(calls), 1)
            self.assertNotIn("private-test-credential", "".join(p.read_text() for p in (base / "run").iterdir()))

    def test_modified_endpoint_and_missing_slots_are_rejected_before_key_read(self):
        with tempfile.TemporaryDirectory() as temp:
            inputs = fixture(Path(temp)); p = inputs / "generation_settings.json"
            settings = json.loads(p.read_text()); settings["destination"] = "https://untrusted.invalid"
            p.write_text(json.dumps(settings)); refresh(inputs)
            with self.assertRaisesRegex(ValueError, "Frozen model"):
                load(inputs)
        with tempfile.TemporaryDirectory() as temp:
            inputs = fixture(Path(temp)); p = inputs / "one_complete_prompt_example.json"
            sample = json.loads(p.read_text()); sample["withheld"] = [dict(token="[[NEWS]]")]
            p.write_text(json.dumps(sample)); refresh(inputs)
            with self.assertRaisesRegex(ValueError, "complete original"):
                load(inputs)

    def test_oversized_request_cannot_be_sent(self):
        with tempfile.TemporaryDirectory() as temp:
            inputs = fixture(Path(temp)); p = inputs / "one_complete_prompt_example.json"
            sample = json.loads(p.read_text()); sample["messages"][0]["content"] = "x" * 100000
            sha = hashlib.sha256(json.dumps(sample["messages"], ensure_ascii=False).encode()).hexdigest()
            sample.update(original_prompt_sha256=sha, delivered_prompt_sha256=sha)
            p.write_text(json.dumps(sample)); refresh(inputs)
            with self.assertRaisesRegex(ValueError, "exceeds one cent"):
                load(inputs)


if __name__ == "__main__":
    unittest.main()
