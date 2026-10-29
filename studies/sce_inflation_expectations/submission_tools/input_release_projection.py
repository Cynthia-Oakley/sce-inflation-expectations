"""Prepare review-only input candidates: exact news-free or explicit templates.

No provider calls, raw publisher articles, credentials, source identity map,
or evaluation truth are written. A real regeneration chain is not simulated.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil

from .input_release_audit import ROOT, NEWS, POLICY, PATTERNS, digest, input_files, read


def project(messages, run, cutoff=None, survey_date=None, *, include_news=False):
    """Return explicit slot templates, and private in-memory restore values."""
    projected, values, metadata = deepcopy(messages), {}, []
    news_count = 0
    for number, message in enumerate(projected):
        text = message["content"]
        start, end = text.find(NEWS), text.find(POLICY)
        if start < 0 or end <= start:
            raise ValueError("Unrecognized news section; do not release by guessing")
        block = text[start:end]
        count = sum(line.startswith("- Online publication date ") for line in block.splitlines())
        news_count += count
        if count:
            token = f"[[WITHHELD_NEWS_BLOCK_{number}]]"
            if token in text:
                raise ValueError("Slot marker collision")
            values[token] = block
            metadata.append(dict(token=token, kind="publisher_text", utf8_bytes=len(block.encode()),
                                 original_sha256=hashlib.sha256(block.encode()).hexdigest(), articles=count))
            text = text[:start] + token + "\n\n" + text[end:]
            # Restore consumes the exact token plus its explicit placeholder gap.
            values[token + "\n\n"] = values.pop(token)
            metadata[-1]["token"] = token + "\n\n"
        if run == "A":
            if not cutoff:
                raise ValueError("Actual per-person cutoff must be available for privacy masking")
            d = datetime.fromisoformat(str(cutoff).replace("Z", "+00:00"))
            survey = datetime.fromisoformat(str(survey_date).replace("Z", "+00:00")) if survey_date else d + timedelta(days=1)
            candidates = set()
            for date in (d, survey):
                candidates.update((date.date().isoformat(), f"{date.strftime('%B')} {date.day}, {date.year}",
                                   date.strftime("%B %d, %Y")))
            candidates.add(str(cutoff))
            for i, value in enumerate(sorted(candidates, key=lambda x: (-len(x), x))):
                if value not in text:
                    continue
                token = f"[[WITHHELD_PERSON_LINKED_DATE_{number}_{i}]]"
                if token in text:
                    raise ValueError("Date marker collision")
                occurrences = text.count(value)
                text = text.replace(value, token)
                values[token] = value
                metadata.append(dict(token=token, kind="real_person_linked_date", occurrences=occurrences))
        if count and include_news:
            # Retain actual publisher text only in the explicitly restricted
            # submission layer. Public article dates are not person-level dates.
            item = next(x for x in metadata if x["kind"] == "publisher_text"
                        and x["token"].startswith(f"[[WITHHELD_NEWS_BLOCK_{number}]]"))
            text = text.replace(item["token"], values.pop(item["token"]))
            metadata.remove(item)
        message["content"] = text
    for message in projected:
        for pattern in PATTERNS.values():
            if pattern.search(message["content"]):
                raise ValueError("Unexpected identifier/credential-like text in candidate")
    if run == "A" and not any(x["kind"] == "real_person_linked_date" for x in metadata):
        raise ValueError("No expected real-person date was masked; inspect date rendering")
    restored = restore(projected, values)
    if restored != messages:
        raise ValueError("Candidate cannot be exactly restored in memory")
    return projected, metadata, news_count


def restore(messages, values):
    """Restore explicit slots from a legally obtained local value dictionary."""
    output = deepcopy(messages)
    # One pass avoids treating a bracket sequence in restored text as a slot.
    if values:
        pattern = re.compile("|".join(re.escape(k) for k in sorted(values, key=len, reverse=True)))
        for row in output:
            row["content"] = pattern.sub(lambda m: values[m[0]], row["content"])
    return output


def materialize(record, legally_restored_slots=None):
    """Fail closed rather than send placeholders as if they were original news."""
    slots = legally_restored_slots or {}
    expected = {item["token"] for item in record["withheld"]}
    if set(slots) != expected:
        raise ValueError("All and only the declared slots must be supplied")
    messages = restore(record["messages"], slots)
    if digest(messages) != record["original_prompt_sha256"]:
        raise ValueError("Restored input differs from the archived message hash")
    return messages


def section(text, start, end):
    a, b = text.find(start), text.find(end)
    return text[a:b] if a >= 0 and b > a else None


class Writer:
    def __init__(self, path):
        self.raw = Path(path).open("xb")
        self.gz = gzip.GzipFile(filename="", mode="wb", fileobj=self.raw, mtime=0, compresslevel=6)
        self.stream = io.TextIOWrapper(self.gz, encoding="utf-8")
        self.rows = 0

    def append(self, row):
        self.stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
        self.rows += 1

    def close(self):
        self.stream.close()
        self.raw.close()


def prepare(out, root=ROOT, *, include_news=False):
    root, out = Path(root).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(root / "outputs"):
        raise ValueError("Fresh ignored review-candidate directory required")
    keymap_path = root / "outputs/sce_micro_reproduction_20261029_v3/private_key_map_NOT_FOR_PACKAGE.json"
    private_map = read(keymap_path)
    lookup = {}
    for public, original in private_map.items():
        run = public.rsplit("_", 1)[0]
        lookup[(run, original)] = public
    out.mkdir(parents=True)
    full_name = "complete_prompts.jsonl.gz" if include_news else "complete_news_free_prompts.jsonl.gz"
    full = Writer(out / full_name)
    templates = Writer(out / "prompt_templates.jsonl.gz")
    components = Writer(out / "population_belief_environment.jsonl.gz")
    counts, examples = {}, []
    try:
        for run in ("A", "B", "monthly", "weekly"):
            positions = complete = date_masked = news_masked = 0
            for period, path in input_files(root, run):
                contexts, roster = {}, {}
                if run == "A":
                    contexts = read(path.parent / "contexts_private.json")
                    source_rows = read(path.parent / "roster_private.json")["rows"]
                    roster = source_rows if isinstance(source_rows, dict) else {r["agent_id"]: r for r in source_rows}
                for aid, row in read(path)["rows"].items():
                    messages = row["messages"]
                    if digest(messages) != row["prompt_sha256"]:
                        raise ValueError("Original prompt hash changed")
                    identity = lookup[(run, str(aid))]
                    context = contexts.get(aid, {})
                    projected, withheld, news_count = project(messages, run,
                        cutoff=context.get("as_of") or context.get("information_cutoff"),
                        survey_date=roster.get(aid, {}).get("survey_date"), include_news=include_news)
                    fields = dict(run=run, period=period, household=identity,
                                  original_prompt_sha256=digest(messages))
                    delivered = digest(projected)
                    candidate = dict(**fields, messages=projected, delivered_prompt_sha256=delivered,
                        withheld=withheld, original_news_articles=news_count,
                        ready_for_exact_single_request=not withheld,
                        scope="Historical conditional single-request input, not a fresh multi-step rollout")
                    templates.append(candidate)
                    positions += 1
                    date_masked += any(x["kind"] == "real_person_linked_date" for x in withheld)
                    news_masked += any(x["kind"] == "publisher_text" for x in withheld)
                    text = "\n".join(m["content"] for m in projected)
                    components.append(dict(**fields,
                        population_text=text.split("\n\n", 1)[0],
                        prices_and_synthetic_spending_text=section(text, "Household grocery context for this simulation:", NEWS)
                            or section(text, "Household grocery context for this simulation:", "[[WITHHELD_NEWS_BLOCK_"),
                        policy_and_timing_text=section(text, POLICY, "Earlier belief state (expectations, not measured inflation):"),
                        earlier_belief_text=section(text, "Earlier belief state (expectations, not measured inflation):", "Question 1 (point estimate):"),
                        questionnaire_and_format_text=text[text.index("Question 1 (point estimate):"):],
                        **({"news_text": section(text, NEWS, POLICY)} if include_news else {}),
                        actual_person_dates_removed=run == "A"))
                    if not withheld:
                        if run == "A" or (news_count and not include_news) or projected != messages or delivered != fields["original_prompt_sha256"]:
                            raise ValueError("Invalid full-prompt candidate")
                        full.append(candidate)
                        complete += 1
                        if not examples:
                            examples.append(candidate)
            counts[run] = dict(prompt_positions=positions, complete_prompts=complete,
                               news_withheld=news_masked, person_date_withheld=date_masked)
            print(run, counts[run], flush=True)
    finally:
        full.close(); templates.close(); components.close()
    if examples:
        (out / "one_complete_prompt_example.json").write_text(json.dumps(examples[0], ensure_ascii=False, indent=2) + "\n")
    protocol = read(root / "outputs/sce_full_a_t0_terminal_20261025_v1/protocol.json")
    settings = {k: protocol[k] for k in ("model", "destination", "route", "expected_provider", "temperature",
                                        "max_tokens", "thinking", "response_format", "request_extra_body")}
    settings.update(credential_environment="OPENROUTER_API_KEY", automatic_retries=0,
                    intended_reproduction="Conditional single-request generation using the declared prior state; not a new autonomous chain",
                    new_API_calls=0)
    (out / "generation_settings.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
    notice = root / "submission/package_templates/v09/SCE_DATA_NOTICE.md"
    shutil.copyfile(notice, out / "SCE_DATA_NOTICE.md")
    summary = dict(status="prepared_restricted_submission_inputs" if include_news else "prepared_candidates_not_installed_in_submission", runs=counts,
        full_prompt_rows=full.rows, template_rows=templates.rows, component_rows=components.rows,
        reversible_in_memory_positions=templates.rows,
        publisher_news_text_included=include_news, real_person_linked_date_values_written=False,
        publisher_text_or_private_date_values_written=include_news, identity_map_included=False,
        credentials_read_or_written=False, new_API_calls=0,
        ready_for_full_historical_regeneration=False,
        complete_prompt_file=full_name,
        distribution_scope="confidential_competition_review_only_not_for_public_GitHub" if include_news else "shareable_candidates",
        rights_basis="News excerpts included at author's explicit direction for confidential review; no publisher redistribution license is asserted. Real person-linked dates and private mappings withheld." if include_news else "Self-authored instructions, attributed public SCE-derived fields, BLS numerical inputs and attributed Federal Reserve Board policy excerpts; publisher news text and real per-person dates withheld",
        files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
               for p in out.iterdir() if p.is_file()})
    (out / "candidate_manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def validate_candidates(candidate, archived_outputs):
    """Independently check the delivered projection and its archived-answer joins."""
    candidate = Path(candidate)
    manifest = read(candidate / ("manifest.json" if (candidate / "manifest.json").exists() else "candidate_manifest.json"))
    checked_bytes = 0
    for name, item in manifest["files"].items():
        path = candidate / name
        if path.is_symlink() or path.name != name:
            raise ValueError("Unexpected candidate path")
        blob = path.read_bytes()
        if len(blob) != item["bytes"] or hashlib.sha256(blob).hexdigest() != item["sha256"]:
            raise ValueError("Candidate file differs from its manifest")
        checked_bytes += len(blob)

    def rows(name):
        with gzip.open(candidate / name, "rt", encoding="utf-8") as stream:
            for line in stream:
                yield json.loads(line)

    answers = set()
    with gzip.open(archived_outputs, "rt", encoding="utf-8") as stream:
        for line in stream:
            r = json.loads(line)
            answers.add((r["run"], r["period"], r["household"], r["prompt_sha256"]))
    include_news = manifest.get("publisher_news_text_included", False)
    keys, exact_keys, runs = set(), set(), {}
    for r in rows("prompt_templates.jsonl.gz"):
        key = (r["run"], r["period"], r["household"], r["original_prompt_sha256"])
        if key in keys or key not in answers:
            raise ValueError("Input is duplicated or cannot be joined to archived model output")
        keys.add(key)
        if not re.fullmatch(re.escape(r["run"]) + r"_\d{6}", r["household"]):
            raise ValueError("Unexpected household identifier")
        if digest(r["messages"]) != r["delivered_prompt_sha256"]:
            raise ValueError("Delivered prompt hash mismatch")
        text = json.dumps(r, ensure_ascii=False)
        if any(p.search(text) for p in PATTERNS.values()):
            raise ValueError("Unexpected private or credential-like string")
        news = [s for s in r["withheld"] if s["kind"] == "publisher_text"]
        dates = [s for s in r["withheld"] if s["kind"] == "real_person_linked_date"]
        if bool(news) != (bool(r["original_news_articles"]) and not include_news):
            raise ValueError("Publisher-text mask missing")
        if (r["run"] == "A") != bool(dates):
            raise ValueError("Real-person date mask disagrees with input type")
        if not include_news and "- Online publication date " in "\n".join(m["content"] for m in r["messages"]):
            raise ValueError("Publisher news item remains")
        if r["ready_for_exact_single_request"] != (not r["withheld"]):
            raise ValueError("A template is incorrectly labelled complete")
        if not r["withheld"]:
            if r["original_prompt_sha256"] != r["delivered_prompt_sha256"]:
                raise ValueError("Exact input changed")
            exact_keys.add(key)
        runs[r["run"]] = runs.get(r["run"], 0) + 1
    full_keys = set()
    for r in rows(manifest.get("complete_prompt_file", "complete_news_free_prompts.jsonl.gz")):
        key = (r["run"], r["period"], r["household"], r["original_prompt_sha256"])
        if key in full_keys or r["withheld"] or not r["ready_for_exact_single_request"]:
            raise ValueError("Invalid complete input")
        if digest(r["messages"]) != r["original_prompt_sha256"]:
            raise ValueError("Complete input is not the archived original")
        full_keys.add(key)
    component_keys = set()
    for r in rows("population_belief_environment.jsonl.gz"):
        key = (r["run"], r["period"], r["household"], r["original_prompt_sha256"])
        if key in component_keys or key not in keys:
            raise ValueError("Component input join mismatch")
        if any(p.search(json.dumps(r, ensure_ascii=False)) for p in PATTERNS.values()):
            raise ValueError("Unexpected identifier in input components")
        for field in ("population_text", "prices_and_synthetic_spending_text", "policy_and_timing_text",
                      "earlier_belief_text", "questionnaire_and_format_text"):
            if not isinstance(r[field], str) or not r[field]:
                raise ValueError("A required model-visible component is missing")
        component_keys.add(key)
    if full_keys != exact_keys or component_keys != keys:
        raise ValueError("Candidate files do not cover the same positions")
    if len(keys) != manifest["template_rows"] or len(full_keys) != manifest["full_prompt_rows"]:
        raise ValueError("Candidate counts differ from the manifest")
    return dict(status="offline_candidate_validation_passed", template_positions=len(keys),
                exact_complete_positions=len(full_keys), component_positions=len(component_keys), runs=runs,
                archived_output_joins=len(keys), complete_output_joins=len(full_keys),
                manifest_file_hashes_checked=len(manifest["files"]), manifest_file_bytes=checked_bytes,
                publisher_news_text_included=include_news, actual_person_dates_exported=False, credentials_read=False,
                identity_map_included=False, new_API_calls=0,
                limitations="Local audit, not a new independent installation or live provider test")
