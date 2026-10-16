"""Offline, response-preserving inputs for the SCE cognition presentation trial.

The existing persona supplies the same High/Low sentence in every arm. This
module adds only earlier answers from that respondent; it neither scores them
nor supplies solutions. This is retrospective A-line information, not evidence
of historical public availability for a B-line forecast.

``load_records(requests)`` returns records in request order, without identifiers.
Keep any request/agent linkage in private preparation artifacts. The association
analysis cache is unsuitable: it discarded the original numeric responses.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree as ET

ARMS = ("label_only", "question_answer", "faithful_paraphrase")
SCHEMA_VERSION = "sce_cognition_input_v1"
ROOT = Path(__file__).resolve().parents[2]
QUESTIONNAIRE_PATH = "data/raw/sce_audit_20260928/questionnaire.pdf"
QUESTIONNAIRE_SHA256 = "e30e2ef1f925cb90aef1d5d6c9b13c6307b1f311e40c5b894ad27ddf69066e93"
QUESTIONNAIRE_URL = "https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/data/frbny-sce-survey-core-module-public-questionnaire.pdf"
SOURCE_SPECS = (
    {"path": "data/raw/sce_p_sources/micro_2017_2019.xlsx", "start": 201701, "end": 201912,
     "sha256": "a88e5a225c9a566dd8cdfdd77abef9ac456eb52d1a120c5ec208184a88c745c9"},
    {"path": "data/raw/sce_audit_20260928/micro_2020_2024.xlsx", "start": 202001, "end": 202412,
     "sha256": "1b57ffb75c2170d767f46a001002db8c40c228fe5691f6dd19e39777ffe469c6"},
    {"path": "data/raw/sce_baselines_latest_20261007/micro_latest.xlsx", "start": 202501, "end": 202510,
     "sha256": "7da4bbcd3f23a4434ab5a94c4c93a255c46df7a57c38eef807b39466bf158f48"},
)

# Transcribed from the locally archived official questionnaire, printed p25-26.
# No answer key, score, or correctness feedback belongs in this catalog.
_QUESTIONS = (
    {"field": "QNUM1", "page": 25, "unit": "dollars", "question":
     "In a sale, a shop is selling all items at half price. Before the sale, a sofa costs $300. How much will it cost in the sale?",
     "paraphrase": "You considered a shop selling all items at half price, including a sofa that cost $300 before the sale, and stated its sale price.", "choices": {}},
    {"field": "QNUM2", "page": 25, "unit": "dollars", "question":
     "Let's say you have $200 in a savings account. The account earns ten per cent interest per year. Interest accrues at each anniversary of the account. If you never withdraw money or interest payments, how much will you have in the account at the end of two years?",
     "paraphrase": "You considered $200 in a savings account earning ten per cent interest per year, with interest accruing at each account anniversary and no withdrawal of money or interest payments, and stated the balance at the end of two years.", "choices": {}},
    {"field": "QNUM3", "page": 25, "unit": "people", "question":
     "In the BIG BUCKS LOTTERY, the chances of winning a $10.00 prize are 1%. What is your best guess about how many people would win a $10.00 prize if 1,000 people each buy a single ticket from BIG BUCKS?",
     "paraphrase": "You considered the BIG BUCKS LOTTERY, with a 1% chance of a $10.00 prize and 1,000 people each buying a single ticket, and gave your best guess for how many people would win a $10.00 prize.", "choices": {}},
    {"field": "QNUM5", "page": 26, "unit": "people", "question":
     "If the chance of getting a disease is 10 percent, how many people out of 1,000 would be expected to get the disease?",
     "paraphrase": "You considered a 10 percent chance of getting a disease and stated how many people out of 1,000 would be expected to get it.", "choices": {}},
    {"field": "QNUM6", "page": 26, "unit": "people", "question":
     "The chance of getting a viral infection is 0.0005. Out of 10,000 people, about how many of them are expected to get infected?",
     "paraphrase": "You considered a 0.0005 chance of getting a viral infection and stated about how many people out of 10,000 would be expected to get infected.", "choices": {}},
    {"field": "QNUM8", "page": 26, "unit": "choice", "question":
     "Imagine that the interest rate on your savings account was 1% per year and inflation was 2% per year. After one year, how much would you be able to buy with the money in this account?",
     "paraphrase": "You considered a savings account earning 1% per year with inflation at 2% per year, and stated how much its money would buy after one year compared with today.",
     "choices": {"1": "More than today", "2": "Exactly the same", "3": "Less than today"}},
    {"field": "QNUM9", "page": 26, "unit": "choice", "question":
     "Please tell me whether this statement is true or false: Buying a single company’s stock usually provides a safer return than a stock mutual fund.",
     "paraphrase": "You judged whether buying a single company’s stock usually provides a safer return than a stock mutual fund.",
     "choices": {"1": "True", "2": "False"}},
)
FIELDS = tuple(q["field"] for q in _QUESTIONS)
RECORD_FIELDS = frozenset(("schema_version", "target_month", "questionnaire_sha256", "catalog_sha256", "items"))
ITEM_FIELDS = frozenset(("field", "raw_answer", "answer_text", "status", "source_month", "source_path", "source_sha256"))
CATALOG_SHA256 = hashlib.sha256(json.dumps(_QUESTIONS, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
CODING_NOTE = (
    "Official questionnaire p25-26 has fixed amounts and no Don't know option; no response invokes E1. "
    "The local 2020-2024 workbook has blank absent cells, no negative or nonnumeric QNUM responses, "
    "and QNUM8/9 nonblank codes only 1-3/1-2. No numeric missing/Don't know sentinel is assumed. "
    "Unexpected values are retained as unmapped, never scored or decoded by guessing."
)


def question_catalog():
    """Return a detached catalog with official wording, choices, provenance and hash."""
    return {"questions": deepcopy(list(_QUESTIONS)), "sha256": CATALOG_SHA256,
            "questionnaire_path": QUESTIONNAIRE_PATH, "questionnaire_sha256": QUESTIONNAIRE_SHA256,
            "questionnaire_url": QUESTIONNAIRE_URL, "verified_at": "2026-10-16", "coding_note": CODING_NOTE}


def _month(value):
    if isinstance(value, bool):
        raise ValueError("Invalid month")
    try:
        n = Decimal(str(value).replace("-", ""))
    except InvalidOperation as exc:
        raise ValueError("Invalid month") from exc
    if not n.is_finite() or n != n.to_integral_value() or not (190001 <= n <= 219912) or not (1 <= int(n) % 100 <= 12):
        raise ValueError("Invalid month")
    return int(n)


def _userid(value):
    try:
        n = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid userid") from exc
    if not n.is_finite() or n != n.to_integral_value():
        raise ValueError("Invalid userid")
    return str(int(n))


def _decode(question, raw):
    if raw is None:
        return "missing", None
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Nonblank raw answers must be strings")
    if raw.strip().lower().replace("’", "'") in ("don't know", "do not know", "dont know", "dk"):
        return "dont_know", raw
    try:
        n = Decimal(raw)
    except InvalidOperation:
        return "unmapped", raw
    if not n.is_finite() or n < 0:
        return "unmapped", raw
    if question["choices"]:
        key = str(int(n)) if n == n.to_integral_value() else ""
        return ("answered", question["choices"][key]) if key in question["choices"] else ("unmapped", raw)
    return "answered", raw + " " + question["unit"]


def _hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_cognition_record(record):
    """Reject unknown fields, altered decoding and same/future-month evidence."""
    if not isinstance(record, dict) or set(record) != RECORD_FIELDS:
        raise ValueError("Cognition record fields differ from the whitelist")
    if record["schema_version"] != SCHEMA_VERSION or record["questionnaire_sha256"] != QUESTIONNAIRE_SHA256 or record["catalog_sha256"] != CATALOG_SHA256:
        raise ValueError("Cognition schema or catalog hash mismatch")
    target = _month(record["target_month"])
    if not isinstance(record["items"], list) or len(record["items"]) != len(FIELDS):
        raise ValueError("Expected exactly seven ordered cognition items")
    for question, item in zip(_QUESTIONS, record["items"]):
        if not isinstance(item, dict) or set(item) != ITEM_FIELDS or item["field"] != question["field"]:
            raise ValueError("Cognition item fields/order differ from the whitelist")
        status, answer = _decode(question, item["raw_answer"])
        if item["status"] != status or item["answer_text"] != answer:
            raise ValueError("Cognition decoding does not match its raw answer")
        if status == "missing":
            if any(item[k] is not None for k in ("source_month", "source_path", "source_sha256")):
                raise ValueError("Missing answer has a spurious source")
        else:
            if _month(item["source_month"]) >= target:
                raise ValueError("Cognition source must strictly precede target month")
            path = item["source_path"]
            if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
                raise ValueError("Cognition source must be a relative provenance path")
            if not isinstance(item["source_sha256"], str) or not re.fullmatch("[0-9a-f]{64}", item["source_sha256"]):
                raise ValueError("Invalid cognition source digest")


def build_records(requests, rows):
    """Build identifier-free records from raw rows, without future backfilling.

    ``requests`` contains userid/month; rows contain userid/date and raw QNUM
    fields, plus ``_source_path`` and ``_source_sha256`` provenance. Blank cells
    are absence of observation, so they do not erase an earlier entry answer.
    Explicit unknown/unmapped nonblank answers do supersede older answers.
    Rows may contain other columns; only seven raw cognition fields are read.
    """
    requests = [(_userid(r["userid"]), _month(r["month"])) for r in requests]
    wanted = {uid for uid, _ in requests}
    past, seen = {}, set()
    for row in rows:
        uid = _userid(row["userid"])
        if uid not in wanted:
            continue
        month = _month(row["date"])
        key = uid, month
        if key in seen:
            raise ValueError("Duplicate respondent-month in cognition sources")
        seen.add(key)
        past.setdefault(uid, []).append((month, row))
    result = []
    for uid, target in requests:
        items = []
        own = sorted((m, r) for m, r in past.get(uid, []) if m < target)
        for question in _QUESTIONS:
            item = dict(field=question["field"], raw_answer=None, answer_text=None, status="missing",
                        source_month=None, source_path=None, source_sha256=None)
            for month, row in own:
                raw = row.get(question["field"])
                if raw is None or str(raw).strip() == "":
                    continue
                # Spreadsheet XML numeric lexemes remain strings; caller floats
                # are serialized as given, never rounded to an integer/score.
                raw = str(raw)
                status, answer = _decode(question, raw)
                item.update(raw_answer=raw, answer_text=answer, status=status, source_month=month,
                            source_path=row.get("_source_path"), source_sha256=row.get("_source_sha256"))
            items.append(item)
        record = dict(schema_version=SCHEMA_VERSION, target_month=target, questionnaire_sha256=QUESTIONNAIRE_SHA256,
                      catalog_sha256=CATALOG_SHA256, items=items)
        validate_cognition_record(record)
        result.append(record)
    return result


def _workbook_rows(path):
    """Stream only identity/month and seven answer columns; retain XML lexemes."""
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            with archive.open("xl/sharedStrings.xml") as stream:
                for _, element in ET.iterparse(stream, events=("end",)):
                    if element.tag == ns + "si":
                        strings.append("".join(t.text or "" for t in element.iter(ns + "t")))
                        element.clear()
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet = next((s for s in workbook.iter(ns+"sheet") if s.attrib.get("name") == "Data"), None)
        if sheet is None:
            raise ValueError("Workbook has no Data worksheet")
        rid = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(r.attrib["Target"] for r in rels if r.attrib["Id"] == rid)
        sheet_path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        columns = {}
        def value(cell):
            if cell.attrib.get("t") == "inlineStr":
                return "".join(t.text or "" for t in cell.iter(ns+"t"))
            v = cell.find(ns+"v")
            if v is None or v.text is None:
                return None
            return strings[int(v.text)] if cell.attrib.get("t") == "s" else v.text
        with archive.open(sheet_path) as stream:
            # Clear each row from its parent, avoiding retention of 100k nodes.
            context = ET.iterparse(stream, events=("start", "end"))
            next(context)
            for event, element in context:
                if event != "end" or element.tag != ns+"row":
                    continue
                rownum = int(element.attrib["r"])
                if rownum == 2:
                    columns = {re.sub(r"[0-9]+$", "", c.attrib["r"]): value(c) for c in element}
                    if not {"userid", "date", *FIELDS} <= set(columns.values()):
                        raise ValueError("Workbook lacks required raw cognition fields")
                    columns = {k: v for k, v in columns.items() if v in {"userid", "date", *FIELDS}}
                elif rownum > 2:
                    row = {columns[re.sub(r"[0-9]+$", "", c.attrib["r"])]: value(c) for c in element
                           if re.sub(r"[0-9]+$", "", c.attrib["r"]) in columns}
                    if row.get("userid") is not None and row.get("date") is not None:
                        yield row
                element.clear()
                # The sheetData parent retains empty rows, but no cell payload.


def load_records(requests, *, root=ROOT, source_specs=None):
    """Read pinned local workbooks once and return records in request order.

    ``requests=[{'userid': 123, 'month': 202004}, ...]``. Sources are restricted
    to their explicit month spans; neither filenames nor cache timestamps are
    treated as historical publication dates. No network or model calls occur.
    ``source_specs`` can pin alternative *local* fixtures using the same keys
    as SOURCE_SPECS. Source and official questionnaire hashes are verified.
    """
    requests = list(requests)
    if not requests:
        return []
    root = Path(root)
    if _hash(root / QUESTIONNAIRE_PATH) != QUESTIONNAIRE_SHA256:
        raise ValueError("Official questionnaire changed; revalidate wording before use")
    wanted = {_userid(r["userid"]) for r in requests}
    last_target = max(_month(r["month"]) for r in requests)
    specs = SOURCE_SPECS if source_specs is None else source_specs
    def rows():
        for spec in specs:
            if spec["start"] >= last_target:
                continue
            source = root / spec["path"]
            digest = _hash(source)
            if digest != spec["sha256"]:
                raise ValueError("Cognition workbook hash differs from pinned source")
            for row in _workbook_rows(source):
                if (_userid(row["userid"]) in wanted and spec["start"] <= _month(row["date"]) <= spec["end"]
                        and _month(row["date"]) < last_target):
                    yield {**row, "_source_path": spec["path"], "_source_sha256": digest}
    return build_records(requests, rows())


def render_cognition_block(arm, record):
    """Render only the incremental block; retain the original label upstream."""
    if arm not in ARMS:
        raise ValueError("Unknown cognition presentation arm")
    validate_cognition_record(record)
    if arm == "label_only":
        return ""
    lines = ["Your earlier survey responses:"]
    for question, item in zip(_QUESTIONS, record["items"]):
        prefix = item["field"]
        if item["source_month"] is not None:
            month = str(item["source_month"])
            prefix += " (" + month[:4] + "-" + month[4:] + ")"
        if arm == "question_answer":
            lines.append(prefix + ". " + question["question"])
        else:
            lines.append(prefix + ". " + question["paraphrase"])
        if question["choices"]:
            lines.append("Options: " + "; ".join(f"{v} ({k})" for k, v in question["choices"].items()) + ".")
        if item["status"] == "missing":
            lines.append("No historical response recorded.")
        elif item["status"] == "answered":
            if question["choices"]:
                lines.append(f"Your response: {item['answer_text']} (recorded code: {item['raw_answer']}).")
            else:
                lines.append("Your response: " + item["answer_text"] + ".")
        elif item["status"] == "dont_know":
            lines.append("Your recorded response: " + json.dumps(item["raw_answer"], ensure_ascii=False) + ".")
        else:
            lines.append("Your recorded response (meaning not mapped): " + json.dumps(item["raw_answer"], ensure_ascii=False) + ".")
    return "\n".join(lines) + "\n"
