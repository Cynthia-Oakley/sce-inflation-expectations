"""Compatibility between legacy 7-field and frozen slim 4-field news labels.

Label schemas in the repo:
  legacy7: article_id, decision, topics, scope, claim_type, reason_zh,
           evidence_snippet  (7,157 articles labeled by deepseek-flash before
           the 2026-10-21 slim freeze)
  slim4:   article_id, decision, topics, scope
           (frozen 2026-10-21; claim_type/reason_zh/evidence_snippet dropped
           by user decision — they cost tokens and are never consumed)

Production truth (verified by reading the loaders): every simulation loader
(expanded_state_inputs, personal_information_views, reference/finance
preparation, post2025_trial, news_exposure_demo) only reads
``semantic_label['decision'] == 'keep'``. Prompt rendering
(news_exposure_demo.render_news_input) uses only the ORIGINAL article text
fields (pub_date/headline/abstract/snippet) — labels never enter prompt text.
Only analysis/report/finalize tooling touched the legacy fields; those sites
now read them via .get() so both schemas pass.

This module is the single place that knows about both schemas. It does not
call any API and does not modify labels; missing legacy fields normalize to
None (they are unknown for slim labels, never fabricated).
"""
from __future__ import annotations

import json
from pathlib import Path

SLIM_FIELDS = ("article_id", "decision", "topics", "scope")
LEGACY_EXTRA_FIELDS = ("claim_type", "reason_zh", "evidence_snippet")
NORMALIZED_FIELDS = SLIM_FIELDS + LEGACY_EXTRA_FIELDS + ("label_schema",)


def label_schema(label: dict) -> str:
    """'legacy7' when any legacy-only field carries a value, else 'slim4'."""
    if any(label.get(f) is not None for f in LEGACY_EXTRA_FIELDS):
        return "legacy7"
    return "slim4"


def normalize_label(raw: dict) -> dict:
    """Accept an inner label dict or a jsonl row wrapping one under 'label'.

    Returns a dict with exactly NORMALIZED_FIELDS: slim4 fields as stored,
    legacy fields None when absent, plus the detected label_schema.
    Raises ValueError when the slim4 core is incomplete.
    """
    label = raw.get("label", raw)
    missing = [f for f in SLIM_FIELDS if f not in label]
    if missing:
        raise ValueError(f"label missing core fields: {missing}")
    out = {f: label[f] for f in SLIM_FIELDS}
    for f in LEGACY_EXTRA_FIELDS:
        out[f] = label.get(f)
    out["label_schema"] = label_schema(label)
    return out


def load_label_rows(path: Path) -> list[dict]:
    """Read a labels.jsonl of either schema into normalized dicts."""
    rows = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            rows.append(normalize_label(json.loads(line)))
    return rows
