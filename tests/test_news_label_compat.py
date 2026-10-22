"""Offline tests for studies/sce_inflation_expectations/news_label_compat.py.

Covers: schema detection, normalization of both label schemas (wrapped and
bare rows), rejection of incomplete cores, no fabrication of legacy content,
and byte-identical rendering of the production news block for both schemas.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from studies.sce_inflation_expectations.news_label_compat import (  # noqa: E402
    LEGACY_EXTRA_FIELDS, NORMALIZED_FIELDS, SLIM_FIELDS, label_schema,
    load_label_rows, normalize_label)
from studies.sce_inflation_expectations.news_exposure_demo import (  # noqa: E402
    render_news_input)

SLIM = {"article_id": "a" * 24, "decision": "keep",
        "topics": ["living_prices"], "scope": "us_national"}
LEGACY = {**SLIM, "claim_type": "fact", "reason_zh": "理由",
          "evidence_snippet": "quoted text"}
ROW = {"article_id": "a" * 24, "headline": "H", "abstract": "A",
       "snippet": "S extra", "pub_date": "2022-03-15"}


class TestNormalizeLabel(unittest.TestCase):
    def test_slim4(self):
        out = normalize_label(SLIM)
        self.assertEqual(out["label_schema"], "slim4")
        for f in LEGACY_EXTRA_FIELDS:
            self.assertIsNone(out[f])
        self.assertEqual(set(out), set(NORMALIZED_FIELDS))
        self.assertEqual({k: out[k] for k in SLIM_FIELDS},
                         {k: SLIM[k] for k in SLIM_FIELDS})

    def test_legacy7(self):
        out = normalize_label(LEGACY)
        self.assertEqual(out["label_schema"], "legacy7")
        self.assertEqual(out["reason_zh"], "理由")

    def test_wrapped_row(self):
        wrapped = {"batch_id": 3, "group": "2019-06", "label": SLIM}
        self.assertEqual(normalize_label(wrapped)["label_schema"], "slim4")

    def test_missing_core_raises(self):
        for f in SLIM_FIELDS:
            bad = {k: v for k, v in SLIM.items() if k != f}
            with self.assertRaises(ValueError):
                normalize_label(bad)

    def test_schema_detection(self):
        self.assertEqual(label_schema(SLIM), "slim4")
        self.assertEqual(label_schema(LEGACY), "legacy7")
        # legacy keys present but all None still count as slim
        self.assertEqual(label_schema(
            {**SLIM, "claim_type": None, "reason_zh": None,
             "evidence_snippet": None}), "slim4")

    def test_load_label_rows(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "labels.jsonl"
            p.write_text(json.dumps({"label": LEGACY}) + "\n"
                         + json.dumps({"batch_id": 1, "label": SLIM}) + "\n")
            rows = load_label_rows(p)
        self.assertEqual([r["label_schema"] for r in rows],
                         ["legacy7", "slim4"])
        self.assertEqual({frozenset(r) for r in rows},
                         {frozenset(NORMALIZED_FIELDS)})


class TestRendererSchemaEquivalence(unittest.TestCase):
    """The production news renderer must produce byte-identical output for a
    slim-labeled and a legacy-labeled copy of the same article (labels never
    enter prompt text)."""

    def test_render_ignores_label_schema(self):
        rendered_slim = render_news_input(
            [], [{**ROW, "semantic_label": normalize_label(SLIM)}])
        rendered_legacy = render_news_input(
            [], [{**ROW, "semantic_label": normalize_label(LEGACY)}])
        self.assertEqual(rendered_slim, rendered_legacy)
        self.assertIn("H", rendered_slim)
        self.assertIn("A", rendered_slim)
        self.assertIn("S extra", rendered_slim)
        # no label content leaks
        self.assertNotIn("keep", rendered_slim)
        self.assertNotIn("理由", rendered_slim)
        self.assertNotIn("quoted text", rendered_slim)


if __name__ == "__main__":
    unittest.main()
