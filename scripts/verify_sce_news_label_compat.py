#!/usr/bin/env python3
"""Offline verification: old 7-field and new slim 4-field news labels assemble
the SAME prompt structure through the production news renderer.

Codex review item (2026-10-22): prove the slim label schema can feed the
simulation without touching the legacy fields. This script:

  1. builds the candidate pools of one legacy-labeled month (2022-03) and one
     slim-labeled month (2019-06, pilot labels from
     outputs/sce_news_labels_slim_pilot_20261021_v1) with the shared tolerant
     pool builder;
  2. joins each pool with its labels through news_label_compat.normalize_label;
  3. applies the production keep-filter (semantic_label['decision']=='keep');
  4. renders a news block with the PRODUCTION renderer
     (news_exposure_demo.render_news_input) and asserts the output equals an
     independent reconstruction from original text fields only — i.e. no label
     content can leak into the prompt and no KeyError can occur for missing
     legacy fields;
  5. asserts both months' normalized labels expose the identical key set.

No API calls, no paid work. Exit code 0 = compatible.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from label_sce_news_pool import (  # noqa: E402
    LABEL_GLOBS, as_of_for, build_pool_tolerant)
from studies.sce_inflation_expectations.news_label_compat import (  # noqa: E402
    NORMALIZED_FIELDS, normalize_label)
from studies.sce_inflation_expectations.news_exposure_demo import (  # noqa: E402
    render_news_input)
from studies.sce_inflation_expectations.news_selection_trial import (  # noqa: E402
    RULE_FILE, RecallRules)

OLD_MONTH = "2022-03"
NEW_MONTH = "2019-06"
SLIM_LABEL_FILE = ROOT / "outputs/sce_news_labels_slim_pilot_20261021_v1/labels.jsonl"
SAMPLE_N = 5


def legacy_labels_for(article_ids: set[str]) -> dict[str, dict]:
    """Raw legacy 7-field labels for the given ids, from all label stores."""
    found = {}
    for g in LABEL_GLOBS:
        for p in sorted(ROOT.glob(g)):
            for line in p.read_text().splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                row = rec.get("label", rec)
                if row.get("article_id") in article_ids:
                    found[row["article_id"]] = row
    return found


def expected_render(personal: list[dict]) -> str:
    """Independent reconstruction of render_news_input([], personal)."""
    chunks = []
    for heading, rows in [("General news you encountered", []),
                          ("Other news you encountered", personal)]:
        lines = [heading + ":"]
        for row in rows:
            lines.append("- Online publication date " + row["pub_date"][:10]
                         + ": " + row["headline"])
            if row["abstract"]:
                lines.append("  " + row["abstract"])
            if row["snippet"] and row["snippet"] != row["abstract"] \
                    and row["snippet"] not in row["abstract"]:
                lines.append("  Additional source excerpt: " + row["snippet"])
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks)


def check_month(target: str, labels_by_id: dict[str, dict], expect_schema: str) -> dict:
    rules = RecallRules(json.loads(RULE_FILE.read_text()))
    rows, counts = build_pool_tolerant(ROOT, target, as_of_for(target), rules)
    labeled = {r["article_id"]: normalize_label(labels_by_id[r["article_id"]])
               for r in rows if r["article_id"] in labels_by_id}
    schemas = {v["label_schema"] for v in labeled.values()}
    if schemas != {expect_schema}:
        raise ValueError(f"{target}: expected only {expect_schema}, got {schemas}")
    if any(set(v) != set(NORMALIZED_FIELDS) for v in labeled.values()):
        raise ValueError(f"{target}: normalized key sets differ")
    # production keep-filter over normalized labels
    keep_ids = {aid for aid, lab in labeled.items() if lab["decision"] == "keep"}
    keep_rows = [r for r in rows if r["article_id"] in keep_ids][:SAMPLE_N]
    if not keep_rows:
        raise ValueError(f"{target}: no keep-labeled pool articles")
    rendered = render_news_input([], keep_rows)
    if rendered != expected_render(keep_rows):
        raise ValueError(f"{target}: renderer output depends on more than the "
                         f"original text fields (label leak or field access)")
    for lab in labeled.values():
        if lab["label_schema"] == "slim4" and any(
                lab[f] is not None for f in
                ("claim_type", "reason_zh", "evidence_snippet")):
            raise ValueError(f"{target}: slim label carries legacy content")
    return {"target": target, "pool_candidates": counts.get("candidates", 0),
            "labeled_in_pool": len(labeled), "keep": len(keep_ids),
            "rendered_sample": len(keep_rows), "schemas": sorted(schemas)}


def main() -> int:
    if not SLIM_LABEL_FILE.exists():
        raise ValueError(f"slim pilot labels missing: {SLIM_LABEL_FILE}")
    slim_labels = {}
    for line in SLIM_LABEL_FILE.read_text().splitlines():
        if line.strip():
            row = json.loads(line).get("label", {})
            if row.get("article_id"):
                slim_labels[row["article_id"]] = row
    rules = RecallRules(json.loads(RULE_FILE.read_text()))
    new_pool, _ = build_pool_tolerant(ROOT, NEW_MONTH, as_of_for(NEW_MONTH), rules)
    new_ids = {r["article_id"] for r in new_pool}
    slim_for_month = {aid: lab for aid, lab in slim_labels.items()
                      if aid in new_ids}
    old_pool, _ = build_pool_tolerant(ROOT, OLD_MONTH, as_of_for(OLD_MONTH), rules)
    legacy = legacy_labels_for({r["article_id"] for r in old_pool})

    results = [check_month(OLD_MONTH, legacy, "legacy7"),
               check_month(NEW_MONTH, slim_for_month, "slim4")]
    out = {"status": "compatible", "checks": results,
           "note": ("production renderer output is byte-identical to an "
                    "independent reconstruction from original text fields for "
                    "both label schemas; keep-filter works on both; slim "
                    "labels never carry legacy content")}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
