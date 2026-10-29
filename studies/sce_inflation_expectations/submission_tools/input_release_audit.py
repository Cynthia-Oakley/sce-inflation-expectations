"""Inventory frozen generation inputs without exporting prompts or credentials.

Counts and hashes are review evidence. A rights assessment is kept separate:
presence of a local file is not permission to redistribute its contents.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import zlib


ROOT = Path(__file__).resolve().parents[3]
RUNS = {
    "A": "outputs/sce_full_a_t0_terminal_20261025_v1",
    "B": "outputs/sce_recent_b_sampled_terminal_20261026_v1",
    "monthly": "outputs/sce_recent_b_recursion_terminal_20261026_v2",
    "weekly": "outputs/sce_weekly_terminal_20261027_v1",
}
PATTERNS = {
    "credential_like_text": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}|(?:api[-_]?key|authorization)\s*[=:]\s*[\"']?[A-Za-z0-9_-]{16,}", re.I),
    "email_like_text": re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
    "local_absolute_path": re.compile(r"/Users/[^\s\"']+"),
    "source_id_like_text": re.compile(r"\b(?:fine|sce_person|proxy_person)_[A-Za-z0-9_:-]{6,}\b"),
}
NEWS = "General news you encountered:\n"
POLICY = "Public policy news brief ("
MONTH_DATE = re.compile(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2}\b")


def read(path):
    return json.loads(Path(path).read_text())


def digest(messages):
    # Exact message serialization used by the frozen production runners.
    return hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()


def input_files(root, run):
    folder = root / RUNS[run]
    if run == "A":
        base = root / "outputs/sce_full_a_personal_inputs_20261025_v1"
        return [(p.parent.name, p) for p in sorted(base.glob("*/prompts.json"))]
    if run == "B":
        return [(p.parent.name, p) for p in sorted((folder / "frozen_messages").glob("*/prompts.json"))]
    return [(p.relative_to(folder).parts[1], p)
            for p in sorted(folder.glob("waves/*/frozen_messages/*/prompts.json"))]


def audit(out, root=ROOT):
    root, out = Path(root).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(root / "outputs"):
        raise ValueError("Use a fresh ignored outputs directory")
    totals, results, source_catalog = Counter(), {}, []
    selected_title_fingerprints = set()
    for run in RUNS:
        counts = Counter()
        expected = {}
        compressor = zlib.compressobj(level=6, wbits=31)
        projected_gzip_bytes = 0
        for period, path in input_files(root, run):
            blob = path.read_bytes()
            doc = json.loads(blob)
            rows = doc["rows"]
            if not isinstance(rows, dict):
                raise ValueError("A keyed frozen input file is required")
            source_catalog.append(dict(run=run, period=period, path=str(path.relative_to(root)),
                                       sha256=hashlib.sha256(blob).hexdigest(), rows=len(rows)))
            counts["frozen_prompt_files"] += 1
            for aid, row in rows.items():
                key = (period, str(aid))
                if key in expected:
                    raise ValueError("Duplicate input position")
                messages = row["messages"]
                sha = digest(messages)
                if sha != row["prompt_sha256"]:
                    raise ValueError("A frozen prompt differs from its recorded hash")
                expected[key] = sha
                encoded = json.dumps(messages, ensure_ascii=False).encode()
                counts["prompt_positions"] += 1
                counts["message_json_utf8_bytes"] += len(encoded)
                projected_gzip_bytes += len(compressor.compress(encoded + b"\n"))
                text = "\n".join(m["content"] for m in messages)
                for name, pattern in PATTERNS.items():
                    counts[name] += bool(pattern.search(text))
                counts["source_agent_key_in_prompt"] += str(aid) in text
                counts["calendar_date_text_present"] += bool(MONTH_DATE.search(text) or re.search(r"20\d{2}-\d{2}-\d{2}", text))
                counts["profile_paragraph_present"] += "You are a U.S. household head" in text
                counts["grocery_context_present"] += "Household grocery context for this simulation:" in text
                counts["belief_block_present"] += "Earlier belief state (expectations, not measured inflation):" in text
                start, end = text.find(NEWS), text.find(POLICY)
                if start >= 0 and end > start:
                    block = text[start:end]
                    counts["news_sections_present"] += 1
                    counts["news_text_utf8_bytes"] += len(block.encode())
                    lines = [line for line in block.splitlines() if line.startswith("- Online publication date ")]
                    counts["news_exposures"] += len(lines)
                    counts["prompts_with_news_articles"] += bool(lines)
                    for line in lines:
                        selected_title_fingerprints.add(hashlib.sha256(line.encode()).hexdigest())
                else:
                    counts["unrecognized_news_boundary"] += 1
        projected_gzip_bytes += len(compressor.flush())
        ledger_paths = sorted((root / RUNS[run]).glob("waves/*/**/calls_private.jsonl")) if run in ("monthly", "weekly") else sorted(
            p for part in ("main", "repair") for p in (root / RUNS[run] / part).rglob("calls_private.jsonl"))
        for path in ledger_paths:
            wave = path.relative_to(root / RUNS[run]).parts[1] if run in ("monthly", "weekly") else None
            with path.open() as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    key = (wave or str(row["month"]), str(row["agent_id"]))
                    counts["archived_call_records"] += 1
                    if key not in expected:
                        counts["call_without_input_position"] += 1
                    elif row["prompt_sha256"] != expected[key]:
                        counts["call_prompt_hash_mismatch"] += 1
                    else:
                        counts["call_input_hash_matches"] += 1
        counts["gzip_bytes_of_messages_only_estimate"] = projected_gzip_bytes
        for name in PATTERNS:
            counts.setdefault(name, 0)
        for name in ("source_agent_key_in_prompt", "call_without_input_position", "call_prompt_hash_mismatch", "unrecognized_news_boundary"):
            counts.setdefault(name, 0)
        results[run] = dict(counts)
        totals.update(counts)
        print(run, "frozen prompts", counts["prompt_positions"], "call/input matches", counts["call_input_hash_matches"],
              "of", counts["archived_call_records"], flush=True)
    shared_root = 0
    monthly_protocol = root / RUNS["monthly"] / "package/protocol.json"
    if monthly_protocol.exists():
        root_answers = root / read(monthly_protocol)["PE"] / "root_answers_private.json"
        shared_root = len(read(root_answers))
    summary = {
        "schema": "sce_input_release_inventory/v1",
        "status": "inventory_complete_no_new_release_authorized_by_this_inventory",
        "runs": results, "totals": dict(totals),
        "unique_selected_dated_headline_fingerprints": len(selected_title_fingerprints),
        "shared_monthly_root_states": shared_root,
        "effective_states_including_shared_root": totals["prompt_positions"] + shared_root,
        "compression_note": "Measured streaming gzip of full message JSON only, without writing any message text; excludes P/E sidecars, archive overhead and any new release transformation.",
        "rights_conclusion": "No rights inference is made by these counts; third-party text and real person-linked dates require separate treatment.",
        "new_API_calls": 0, "model_credentials_read": False,
        "full_prompt_or_identity_map_exported": False,
    }
    if totals["call_without_input_position"] or totals["call_prompt_hash_mismatch"]:
        summary["status"] = "inventory_requires_provenance_repair"
    out.mkdir(parents=True)
    for name, data in (("inventory.json", summary), ("source_catalog.json", source_catalog)):
        (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.out), ensure_ascii=False, indent=2))
