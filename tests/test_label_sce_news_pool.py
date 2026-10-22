"""Offline tests for scripts/label_sce_news_pool.py (slim news-label pilot).

Covers: per-label enum/field validation, batch id-set validation, resume
dedup of completed batch ids, cost bound arithmetic, and the frozen slim
system prompt content (4 fields only, no legacy口径 fields).
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from label_sce_news_pool import (  # noqa: E402
    BATCH, BUDGET_CAP, DECISIONS, MAX_TOKENS, MODEL, PRICE_IN, PRICE_OUT,
    PROVIDER_ORDER, SCOPES, SYSTEM_PROMPT_V2, SYSTEM_PROMPT_V21, TOPICS,
    VARIANTS, batch_cost_estimates, completed_batch_ids, failed_batch_ids,
    make_payload, prior_spend, validate_batch, validate_label,
)

ART = {
    "article_id": "a" * 24,
    "headline": "Headline", "abstract": "Abstract", "snippet": "",
    "section_name": "Business", "news_desk": "Business",
}


class TestValidateLabel(unittest.TestCase):
    def good(self, **kw):
        row = {"article_id": "x", "decision": "keep", "topics": [],
               "scope": "us_national"}
        row.update(kw)
        return row

    def test_valid_cases(self):
        self.assertIsNone(validate_label(self.good()))
        self.assertIsNone(validate_label(self.good(topics=["living_prices"])))
        self.assertIsNone(validate_label(
            self.good(decision="uncertain", topics=[t for t in sorted(TOPICS)],
                      scope="non_us")))

    def test_field_set_exact(self):
        row = self.good(claim_type="fact")
        self.assertIsNotNone(validate_label(row))
        row = self.good()
        del row["topics"]
        self.assertIsNotNone(validate_label(row))

    def test_enum_rejections(self):
        for bad in ["keep ", "KEEP", "skip", ""]:
            self.assertIsNotNone(validate_label(self.good(decision=bad)))
        for bad in ["us_everywhere", "US", ""]:
            self.assertIsNotNone(validate_label(self.good(scope=bad)))
        self.assertIsNotNone(validate_label(self.good(topics="living_prices")))
        self.assertIsNotNone(validate_label(self.good(topics=["prices"])))
        self.assertIsNotNone(validate_label(self.good(topics=["living_prices", 3])))


class TestValidateBatch(unittest.TestCase):
    def labels_for(self, ids, **kw):
        return [{"article_id": i, "decision": "keep", "topics": [],
                 "scope": "us_national", **kw} for i in ids]

    def test_exact_match(self):
        ids = [f"id{i}" for i in range(8)]
        self.assertIsNone(validate_batch(ids, self.labels_for(ids)))

    def test_missing_and_extra_and_dupe(self):
        ids = [f"id{i}" for i in range(8)]
        self.assertIsNotNone(validate_batch(ids, self.labels_for(ids[:7])))
        self.assertIsNotNone(validate_batch(
            ids, self.labels_for(ids + ["extra"])))
        dupe = self.labels_for(ids)
        dupe[0]["article_id"] = dupe[1]["article_id"]
        self.assertIsNotNone(validate_batch(ids, dupe))

    def test_invalid_label_inside_batch(self):
        ids = [f"id{i}" for i in range(8)]
        labels = self.labels_for(ids)
        labels[3]["decision"] = "nope"
        self.assertIsNotNone(validate_batch(ids, labels))

    def test_not_a_list(self):
        self.assertIsNotNone(validate_batch(["a"], {"labels": []}))


class TestResumeDedup(unittest.TestCase):
    def test_completed_batch_ids(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            (out / "labels.jsonl").write_text(
                json.dumps({"batch_id": 1, "group": "2019-06"}) + "\n"
                + json.dumps({"batch_id": 2, "group": "2019-06"}) + "\n")
            (out / "consistency").mkdir()
            (out / "consistency/labels_new.jsonl").write_text(
                json.dumps({"batch_id": 3, "group": "consistency"}) + "\n")
            self.assertEqual(completed_batch_ids(out), {1, 2, 3})
            # missing files -> empty
            empty = Path(td) / "sub"
            empty.mkdir()
            self.assertEqual(completed_batch_ids(empty), set())


class TestResumeBudgetPersistence(unittest.TestCase):
    """Codex review fix: resume must not reset the spend counter, and failed
    batches must not be silently re-sent."""

    def test_failed_batch_ids_skips_budget_stops(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            (out / "errors.jsonl").write_text(
                json.dumps({"batch_id": 5, "type": "RuntimeError",
                            "error": "non_200"}) + "\n"
                + json.dumps({"batch_id": 6, "type": "budget_stop"}) + "\n"
                + json.dumps({"batch_id": 7, "type": "ValueError",
                              "error": "invalid label"}) + "\n")
            self.assertEqual(failed_batch_ids(out), {5, 7})
            empty = Path(td) / "sub"
            empty.mkdir()
            self.assertEqual(failed_batch_ids(empty), set())

    def test_prior_spend_carries_cost_and_unknown_billing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            (out / "calls_log.jsonl").write_text(
                json.dumps({"batch_id": 1, "http_status": 200,
                            "cost_usd": 0.004}) + "\n"
                + json.dumps({"batch_id": 2, "http_status": 200,
                            "cost_usd": 0.006}) + "\n"
                + json.dumps({"batch_id": 3, "http_status": 200}) + "\n"
                + json.dumps({"batch_id": 4, "http_status": 500,
                              "error": "non_200"}) + "\n")
            spent, paid, unknown = prior_spend(out)
            self.assertAlmostEqual(spent, 0.010, places=6)
            self.assertEqual(paid, 3)       # two priced + one unknown-billing 200
            self.assertEqual(unknown, 1)    # the 200 without cost is flagged
            empty = Path(td) / "sub"
            empty.mkdir()
            self.assertEqual(prior_spend(empty), (0.0, 0, 0))


class TestCostBounds(unittest.TestCase):
    def test_bound_arithmetic(self):
        arts = [dict(ART, article_id=f"a{i:023d}") for i in range(BATCH)]
        est = batch_cost_estimates(arts)
        self.assertGreater(est["input_bytes"], 1000)
        # realistic <= byte envelope, both positive and tiny
        self.assertGreater(est["realistic_usd"], 0)
        self.assertLessEqual(est["realistic_usd"], est["byte_envelope_usd"])
        self.assertLessEqual(est["realistic_bound_usd"], est["byte_envelope_usd"])
        # envelope math: (bytes+1024)*pin + max_tokens*pout, per million
        expect = ((est["input_bytes"] + 1024) * PRICE_IN
                  + MAX_TOKENS * PRICE_OUT) / 1e6
        self.assertAlmostEqual(est["byte_envelope_usd"], expect, places=6)

    def test_payload_lock(self):
        payload = make_payload([ART])
        self.assertEqual(payload["model"], MODEL)
        self.assertEqual(payload["provider"]["order"], PROVIDER_ORDER)
        self.assertFalse(payload["provider"]["allow_fallbacks"])
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["max_tokens"], MAX_TOKENS)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        user = json.loads(payload["messages"][1]["content"])
        self.assertEqual(len(user["articles"]), 1)
        self.assertNotIn("web_url", user["articles"][0])

    def test_pilot_scale_within_cap(self):
        # ~1870 articles / 8 per batch; realistic per-article cost must keep
        # the pilot under the cap with headroom (measured offline estimate)
        per_article_bytes = 900  # measured pilot article JSON ~0.9KB
        in_tokens = per_article_bytes / 3.5
        per_article = (in_tokens * PRICE_IN + 60 * PRICE_OUT) / 1e6
        total = 1870 * per_article
        self.assertLess(total, BUDGET_CAP * 0.75,
                        f"pilot estimate {total:.4f} too close to cap")


class TestSystemPrompt(unittest.TestCase):
    def test_slim_fields_only(self):
        for banned in ("claim_type", "reason_zh", "evidence_snippet"):
            self.assertNotIn(banned, SYSTEM_PROMPT_V2)

    def test_required_content(self):
        for token in ("keep", "background", "exclude", "uncertain",
                      "living_prices", "supply_costs",
                      "employment_income_consumption", "policy",
                      "economic_outlook", "other_economic",
                      "us_national", "us_local", "us_unspecified",
                      "us_and_global", "global", "non_us", "unspecified"):
            self.assertIn(token, SYSTEM_PROMPT_V2)
        self.assertIn("article_id、decision、topics、scope 四个字段",
                      SYSTEM_PROMPT_V2)

    def test_decisions_topics_scopes_consistent_with_enums(self):
        import re
        for topic in TOPICS:
            self.assertIn(topic, SYSTEM_PROMPT_V2)
        for scope in SCOPES:
            self.assertIn(scope, SYSTEM_PROMPT_V2)
        for dec in DECISIONS:
            self.assertRegex(SYSTEM_PROMPT_V2, rf"(?m)^{dec}：")


class TestSystemPromptV21(unittest.TestCase):
    """v2.1 = v2 + the two main-line review clarifications; contract unchanged."""

    def test_adds_decision_clarification(self):
        self.assertIn("不得仅因发生在国外而 exclude", SYSTEM_PROMPT_V21)
        self.assertIn("实质内容弱的降为 background，内容相关的保留 keep",
                      SYSTEM_PROMPT_V21)
        self.assertIn("央行货币政策（如加息抗通胀）", SYSTEM_PROMPT_V21)

    def test_adds_scope_clarification(self):
        self.assertIn("标 us_and_global；纯外国国内事务标 non_us",
                      SYSTEM_PROMPT_V21)

    def test_v2_unchanged_and_v21_is_superset(self):
        self.assertNotIn("不得仅因发生在国外", SYSTEM_PROMPT_V2)
        # v2.1 must contain every v2 paragraph (pure insertion upgrade)
        for para in SYSTEM_PROMPT_V2.split("\n"):
            if para.strip():
                self.assertIn(para, SYSTEM_PROMPT_V21)

    def test_contract_still_four_fields(self):
        for banned in ("claim_type", "reason_zh", "evidence_snippet"):
            self.assertNotIn(banned, SYSTEM_PROMPT_V21)
        self.assertIn("article_id、decision、topics、scope 四个字段",
                      SYSTEM_PROMPT_V21)

    def test_v21_payload_uses_v21_prompt(self):
        payload = make_payload([ART], SYSTEM_PROMPT_V21)
        self.assertEqual(payload["messages"][0]["content"], SYSTEM_PROMPT_V21)
        payload2 = make_payload([ART])
        self.assertEqual(payload2["messages"][0]["content"], SYSTEM_PROMPT_V2)

    def test_variant_config(self):
        v21 = VARIANTS["v21"]
        self.assertEqual(v21["groups"], ["consistency"])
        self.assertEqual(v21["budget_cap"], 0.05)
        self.assertEqual(v21["prompt"], SYSTEM_PROMPT_V21)
        self.assertIn("v21", str(v21["out"]))
        self.assertNotEqual(v21["out"], VARIANTS["v2"]["out"])


if __name__ == "__main__":
    unittest.main()
