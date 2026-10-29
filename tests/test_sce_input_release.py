"""Input-release safeguards, with synthetic fixtures and no provider calls."""
import json
from pathlib import Path
import tempfile
import unittest

from studies.sce_inflation_expectations.submission_tools.input_release_audit import audit, digest
from studies.sce_inflation_expectations.submission_tools.input_release_projection import project, restore, materialize


class InputReleaseTests(unittest.TestCase):
    def test_publisher_text_and_linkable_dates_are_removed_without_changing_source(self):
        text = ("Survey cutoff January 22, 2019; completed 2019-01-23.\n\n"
                "General news you encountered:\n- Online publication date 2019-01-20: UNIQUE_PUBLISHER_TEXT\n\n"
                "Other news you encountered:\n\nPublic policy news brief (2018-12-19):\n- Public numeric fact\n")
        messages = [dict(role="user", content=text)]
        projected, withheld, count = project(messages, "A", "2019-01-22T23:59:59-05:00", "2019-01-23")
        self.assertEqual(messages[0]["content"], text)
        self.assertEqual(count, 1)
        delivered = json.dumps(dict(messages=projected, withheld=withheld))
        for value in ("UNIQUE_PUBLISHER_TEXT", "January 22, 2019", "2019-01-23"):
            self.assertNotIn(value, delivered)
        self.assertIn("Public numeric fact", delivered)
        self.assertEqual({x["kind"] for x in withheld}, {"publisher_text", "real_person_linked_date"})

    def test_news_free_week_is_byte_equivalent_at_the_message_contract(self):
        messages = [dict(role="user", content="Weekly cutoff 2026-01-30.\nGeneral news you encountered:\n\n"
                         "Other news you encountered:\n\nPublic policy news brief (2026-01-28):\n- Public fact")]
        projected, withheld, count = project(messages, "weekly")
        self.assertEqual(projected, messages)
        self.assertEqual(withheld, [])
        self.assertEqual(count, 0)
        self.assertEqual(digest(projected), digest(messages))

    def test_author_selected_public_dates_preserve_exact_full_A_input(self):
        messages = [dict(role="user", content=("Cutoff January 22, 2019; survey 2019-01-23.\n"
            "General news you encountered:\n- Online publication date 2019-01-22: ORIGINAL_NEWS\n"
            "Public policy news brief (2018-12-19):\nPublic fact"))]
        delivered, withheld, count = project(messages, "A", include_news=True, retain_public_dates=True)
        self.assertEqual(delivered, messages)
        self.assertEqual(withheld, [])
        self.assertEqual(count, 1)
        self.assertEqual(digest(delivered), digest(messages))
        with self.assertRaisesRegex(ValueError, "restricted"):
            project(messages, "A", retain_public_dates=True)

    def test_confidential_news_preserves_exact_B_and_only_masks_linked_A_date(self):
        text = ("Survey cutoff January 22, 2019; completed 2019-01-23.\n"
                "General news you encountered:\n- Online publication date 2019-01-22: ORIGINAL_NEWS\n\n"
                "Public policy news brief (2018-12-19):\nPublic fact")
        messages = [dict(role="user", content=text)]
        b, withheld, count = project(messages, "B", include_news=True)
        self.assertEqual(b, messages)
        self.assertEqual(withheld, [])
        self.assertEqual(count, 1)
        a, withheld, count = project(messages, "A", "2019-01-22T23:59:59-05:00", "2019-01-23", include_news=True)
        self.assertIn("- Online publication date 2019-01-22: ORIGINAL_NEWS", a[0]["content"])
        self.assertNotIn("Survey cutoff January 22, 2019", a[0]["content"])
        self.assertNotIn("completed 2019-01-23", a[0]["content"])
        self.assertEqual({x["kind"] for x in withheld}, {"real_person_linked_date"})

    def test_unknown_layout_and_unmasked_credential_are_not_silently_released(self):
        with self.assertRaisesRegex(ValueError, "Unrecognized news"):
            project([dict(role="user", content="Some unknown layout")], "weekly")
        fake = "sk-" + "x" * 25
        with self.assertRaisesRegex(ValueError, "credential-like"):
            project([dict(role="user", content="General news you encountered:\n\nPublic policy news brief (2026-01-28):\n" + fake)], "weekly")

    def test_restore_is_single_pass_when_publisher_text_contains_slot_like_words(self):
        source = [dict(role="user", content="prefix [[A]] suffix [[B]]")]
        actual = restore(source, {"[[A]]": "literal [[B]]", "[[B]]": "value"})
        self.assertEqual(actual[0]["content"], "prefix literal [[B]] suffix value")

    def test_materializer_rejects_missing_or_changed_source_slots(self):
        original = [dict(role="user", content="one original article")]
        record = dict(messages=[dict(role="user", content="one [[NEWS]]")],
                      withheld=[dict(token="[[NEWS]]")], original_prompt_sha256=digest(original))
        with self.assertRaisesRegex(ValueError, "All and only"):
            materialize(record)
        with self.assertRaisesRegex(ValueError, "differs"):
            materialize(record, {"[[NEWS]]": "changed article"})
        self.assertEqual(materialize(record, {"[[NEWS]]": "original article"}), original)

    def test_inventory_matches_call_hashes_without_exporting_identity_or_text(self):
        from studies.sce_inflation_expectations.submission_tools.input_release_audit import RUNS
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for run, period in (("A", "201901"), ("B", "202511"), ("monthly", "202512"), ("weekly", "w20251107")):
                folder = root / RUNS[run]
                if run == "A":
                    prompt = root / "outputs/sce_full_a_personal_inputs_20261025_v1/201901/prompts.json"
                elif run == "B":
                    prompt = folder / "frozen_messages/202511/prompts.json"
                else:
                    prompt = folder / f"waves/{period}/frozen_messages/202511/prompts.json"
                prompt.parent.mkdir(parents=True)
                secret = "sk-" + "z" * 25
                text = ("PRIVATE_SOURCE_KEY " + secret + " demo@example.invalid\nGeneral news you encountered:\n"
                        "- Online publication date 2025-10-31: PRIVATE_TITLE\nPublic policy news brief (2025-10-29):\n")
                messages = [dict(role="user", content=text)]
                prompt.write_text(json.dumps(dict(rows={"PRIVATE_SOURCE_KEY": dict(messages=messages, prompt_sha256=digest(messages))})))
                ledger = folder / (f"waves/{period}/main/calls_private.jsonl" if run in ("monthly", "weekly") else "main/calls_private.jsonl")
                ledger.parent.mkdir(parents=True, exist_ok=True)
                ledger.write_text(json.dumps(dict(month=period, agent_id="PRIVATE_SOURCE_KEY", prompt_sha256=digest(messages))) + "\n")
            out = root / "outputs/audit"
            result = audit(out, root)
            self.assertEqual(result["totals"]["call_input_hash_matches"], 4)
            self.assertEqual(result["totals"]["credential_like_text"], 4)
            self.assertEqual(result["totals"]["source_agent_key_in_prompt"], 4)
            public = "".join(p.read_text() for p in out.iterdir())
            for value in ("PRIVATE_SOURCE_KEY", "PRIVATE_TITLE", "demo@example.invalid", secret):
                self.assertNotIn(value, public)


if __name__ == "__main__":
    unittest.main()
