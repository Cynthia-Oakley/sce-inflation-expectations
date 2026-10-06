"""Prepare weekly CE Diary expenditure proxies from one explicit 2020 archive.

These are consumer-unit (CU) diary records, not SCE respondents' observed
purchases. Each NEWID represents one CU-week; the last digit distinguishes
Diary week 1 from week 2. All amounts stay weekly and every row carries its own
FINLWT21. The module never joins Diary NEWIDs to Interview or SCE identifiers.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


TARGET_YEAR = 2020
TARGET_QUARTER = 4
DIARY_ZIP_URL = "https://www.bls.gov/cex/pumd/data/comma/diary20.zip"
DICTIONARY_URL = "https://www.bls.gov/cex/pumd/ce-pumd-interview-diary-dictionary.xlsx"
GETTING_STARTED_URL = "https://www.bls.gov/cex/pumd-getting-started-guide.htm"
ERRATA_URL = "https://www.bls.gov/cex/pumd_errata_2019_2020.htm"
KNOWN_AVAILABLE_BY_DATE = "2021-09-09"
KNOWN_AVAILABLE_BY_URL = "https://www.bls.gov/news.release/archives/cesan_09092021.htm"

AMOUNT_REQUIRED_FIELDS = ("NEWID", "UCC", "COST", "PUB_FLAG")
FMLD_REQUIRED_FIELDS = ("NEWID", "FINLWT21")
DAY_FIELD = "EXPNSQDY"
DAY_FLAG_FIELD = "EXPN_QDY"
VALID_DAY_FLAGS = {"D", "E", "T"}
OPTIONAL_FMLD_FIELDS = (
    "WEEKI", "WEEKN", "AGE_REF", "EDUC_REF", "CUTENURE", "REGION", "STATE",
    "FINCBEFM", "FINCBEFX", "STRTMNTH", "STRTYEAR", "FOODHOME", "FOODAWAY",
    "FOODTOT", "ALCBEV", "HOUSKEEP", "PERSPROD", "PERSSERV",
)

# Exact 2020-valid FMLD codebook formulas are read from the official dictionary.
# FOODAWAY's formula is truncated at 255 characters in the workbook, so that
# category uses the complete 2020-valid 190xxx UCC family in the same codebook.
CATEGORY_FORMULA_ROOTS = {
    "food_at_home": ("FOODHOME",),
    "household_supplies_services": ("HOUSKEEP",),
    "personal_care_products_services": ("PERSPROD", "PERSSERV"),
}
CATEGORY_NAMES = (
    "food_at_home",
    "food_away_from_home",
    "household_supplies_services",
    "personal_care_products_services",
    "other_known_ucc",
    "unknown_ucc",
)
SUMMARY_CROSSCHECKS = {
    "food_at_home": ("food_at_home", ("FOODHOME",)),
    "food_away_from_home": ("food_away_from_home", ("FOODAWAY",)),
    "household_supplies_services": ("household_supplies_services", ("HOUSKEEP",)),
    "personal_care_products_services": ("personal_care_products_services", ("PERSPROD", "PERSSERV")),
}
EXPECTED_FLAG_CODES = {"1", "2"}
WEEK_NUMBER_CODES = {"1", "2"}
DECIMAL_ZERO = Decimal("0")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _int_code(value: Any, field: str) -> int:
    raw = str(value if value is not None else "").strip()
    try:
        number = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError(f"missing or invalid {field}: {raw!r}") from None
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError(f"missing or invalid {field}: {raw!r}")
    return int(number)


def _number(value: Any, field: str) -> Decimal:
    raw = str(value if value is not None else "").strip()
    try:
        number = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError(f"missing or invalid {field}: {raw!r}") from None
    if not number.is_finite():
        raise ValueError(f"nonfinite {field}: {raw!r}")
    return number


def _decimal_text(value: Decimal) -> str:
    # Keep arithmetic exact; remove unnecessary trailing zeros without turning
    # dollar values into scientific notation.
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _normal_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if key is None:
            continue
        field = str(key).strip().upper()
        if field in normalized:
            raise ValueError(f"duplicate normalized CSV field: {field}")
        normalized[field] = value
    return normalized


def _effective(first_year: Any, first_quarter: Any, last_year: Any, last_quarter: Any,
               year: int, quarter: int) -> bool:
    try:
        first = int(first_year)
    except (TypeError, ValueError):
        return False
    if first > year or (first == year and int(first_quarter or 1) > quarter):
        return False
    try:
        last = int(last_year) if last_year not in (None, "") else None
    except (TypeError, ValueError):
        last = None
    if last is None or last > year:
        return True
    if last < year:
        return False
    try:
        return int(last_quarter or 4) >= quarter
    except (TypeError, ValueError):
        return True


def _formula_uccs(name: str, formulas: dict[str, str], *, stack: tuple[str, ...] = ()) -> set[str]:
    if name in stack:
        raise ValueError(f"cyclic FMLD formula in dictionary: {' -> '.join((*stack, name))}")
    formula = formulas.get(name)
    if not formula:
        raise ValueError(f"no active FMLD formula for category variable {name}")
    prefix, separator, body = formula.partition("(")
    if not separator or prefix.strip().upper() != "SUM":
        raise ValueError(f"unsupported FMLD category formula for {name}: {formula!r}")
    body = body.strip()
    if body.endswith(")"):
        body = body[:-1].strip()
    elif len(formula) >= 255:
        raise ValueError(f"possibly truncated FMLD category formula for {name}: {formula!r}")
    if "(" in body or ")" in body:
        raise ValueError(f"unsupported FMLD category formula for {name}: {formula!r}")
    tokens = [token.strip().upper() for token in body.split(",")]
    if not tokens or any(not re.fullmatch(r"(?:\d{6}|[A-Z][A-Z0-9_]*)", token) for token in tokens):
        raise ValueError(f"incomplete or unsupported FMLD category formula for {name}: {formula!r}")
    result: set[str] = set()
    for token in tokens:
        if token.isdigit():
            result.add(token)
        elif token in formulas:
            result.update(_formula_uccs(token, formulas, stack=(*stack, name)))
        else:
            raise ValueError(f"unresolved FMLD formula token {token!r} in {name}")
    if not result:
        raise ValueError(f"empty FMLD UCC mapping for {name}")
    return result


def _xlsx_sheet_rows(path: str | Path, sheet_name: str) -> list[tuple[Any, ...]]:
    """Read a text/numeric worksheet with the standard library (no XLSX dependency)."""
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    q = lambda ns, name: f"{{{ns}}}{name}"
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {rel.attrib["Id"]: rel.attrib["Target"]
                   for rel in relationships.findall(q(pkg_rel_ns, "Relationship"))}
        target = None
        for sheet in workbook.findall(f"{q(main_ns, 'sheets')}/{q(main_ns, 'sheet')}"):
            if sheet.attrib.get("name") == sheet_name:
                target = targets.get(sheet.attrib.get(q(rel_ns, "id")))
                break
        if not target:
            raise ValueError(f"worksheet not found in BLS dictionary: {sheet_name!r}")
        sheet_path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(q(main_ns, "si")):
                shared_strings.append("".join(node.text or "" for node in item.iter(q(main_ns, "t"))))
        root = ET.fromstring(archive.read(sheet_path))

    rows: list[tuple[Any, ...]] = []
    for row_element in root.findall(f".//{q(main_ns, 'sheetData')}/{q(main_ns, 'row')}"):
        values: dict[int, Any] = {}
        for cell in row_element.findall(q(main_ns, "c")):
            reference = cell.attrib.get("r", "")
            letters = re.match(r"([A-Z]+)", reference.upper())
            if not letters:
                continue
            column = 0
            for char in letters.group(1):
                column = column * 26 + ord(char) - ord("A") + 1
            column -= 1
            kind = cell.attrib.get("t")
            value_node = cell.find(q(main_ns, "v"))
            if kind == "inlineStr":
                value = "".join(node.text or "" for node in cell.iter(q(main_ns, "t")))
            elif value_node is None:
                value = None
            elif kind == "s":
                try:
                    value = shared_strings[int(value_node.text or "")]
                except (ValueError, IndexError):
                    raise ValueError(f"invalid shared string in dictionary cell {reference}") from None
            else:
                raw_value = value_node.text or ""
                if kind in (None, "n"):
                    try:
                        number = Decimal(raw_value)
                        value = int(number) if number == number.to_integral_value() else float(number)
                    except (InvalidOperation, ValueError):
                        value = raw_value
                else:
                    value = raw_value
            values[column] = value
        if values:
            rows.append(tuple(values.get(index) for index in range(max(values) + 1)))
        else:
            rows.append(tuple())
    return rows


def category_map_from_dictionary(dictionary_path: str | Path, *, year: int = TARGET_YEAR,
                                 quarter: int = 4) -> tuple[dict[str, str], set[str], dict]:
    """Read active 2020 FMLD category formulas and EXPD UCC codes from BLS XLSX."""
    if year != TARGET_YEAR or quarter not in {1, 2, 3, 4}:
        raise ValueError("Diary preparation is restricted to 2020 Q1-Q4")
    variable_rows = _xlsx_sheet_rows(dictionary_path, "Variables")
    code_rows = _xlsx_sheet_rows(dictionary_path, "Codes ")
    formula_candidates: dict[str, list[tuple[tuple[int, int], str]]] = defaultdict(list)
    for row in variable_rows[2:]:  # Column headings are repeated in the first two rows.
        if len(row) < 13 or row[0] != "DIARY" or row[1] != "FMLD" or not row[2]:
            continue
        if _effective(row[9], row[10], row[11], row[12], year, quarter) and row[4]:
            name, formula = str(row[2]).strip().upper(), str(row[4]).strip()
            try:
                starts = (int(row[9]), int(row[10] or 1))
            except (TypeError, ValueError):
                raise ValueError(f"invalid effective start for FMLD.{name} in dictionary") from None
            formula_candidates[name].append((starts, formula))

    formulas: dict[str, str] = {}
    formula_starts: dict[str, tuple[int, int]] = {}
    for name, candidates in formula_candidates.items():
        latest_start = max(starts for starts, _ in candidates)
        latest_formulas = {formula for starts, formula in candidates if starts == latest_start}
        if len(latest_formulas) != 1:
            raise ValueError(
                f"multiple active dictionary formulas for FMLD.{name} at {latest_start}: "
                f"{sorted(latest_formulas)}"
            )
        formulas[name] = latest_formulas.pop()
        formula_starts[name] = latest_start

    known_ucc: set[str] = set()
    for row in code_rows[1:]:
        if len(row) < 9 or row[0] != "DIARY" or row[1] != "EXPD" or row[2] != "UCC":
            continue
        if row[3] is not None and _effective(row[5], row[6], row[7], row[8], year, quarter):
            known_ucc.add(str(row[3]).strip().zfill(6))
    if not known_ucc:
        raise ValueError(f"no 2020-valid Diary EXPD UCCs found in dictionary: {dictionary_path}")

    mapped: dict[str, set[str]] = {
        name: set().union(*(_formula_uccs(root, formulas) for root in roots))
        for name, roots in CATEGORY_FORMULA_ROOTS.items()
    }
    mapped["food_away_from_home"] = {code for code in known_ucc if code.startswith("190")}
    for category, codes in mapped.items():
        if not codes:
            raise ValueError(f"empty category mapping: {category}")
        missing = codes - known_ucc
        if missing:
            raise ValueError(f"{category} formula contains UCCs not active in 2020: {sorted(missing)}")
    for left_index, left in enumerate(CATEGORY_NAMES[:4]):
        for right in CATEGORY_NAMES[left_index + 1:4]:
            overlap = mapped[left] & mapped[right]
            if overlap:
                raise ValueError(f"overlapping category UCC mappings {left}/{right}: {sorted(overlap)}")

    lookup = {code: category for category, codes in mapped.items() for code in codes}
    used_formula_names: set[str] = set()

    def record_formula_tree(name: str) -> None:
        if name in used_formula_names:
            return
        used_formula_names.add(name)
        prefix, separator, body = formulas[name].partition("(")
        if not separator or prefix.strip().upper() != "SUM":
            return
        body = body.strip().removesuffix(")").strip()
        for token in (part.strip().upper() for part in body.split(",")):
            if token in formulas:
                record_formula_tree(token)

    for roots in CATEGORY_FORMULA_ROOTS.values():
        for root in roots:
            record_formula_tree(root)
    audit = {
        "dictionary_year": year,
        "dictionary_sheet": "Variables + Codes ",
        "formula_version_rule": "when the dictionary has overlapping open-ended rows for a variable, select the unique formula with the latest effective start year and quarter",
        "formula_definitions_used": {
            name: {
                "effective_start_year": formula_starts[name][0],
                "effective_start_quarter": formula_starts[name][1],
                "formula": formulas[name],
            }
            for name in sorted(used_formula_names)
        },
        "active_expd_ucc_count": len(known_ucc),
        "category_ucc_counts": {name: len(codes) for name, codes in mapped.items()},
        "category_ucc_codes": {name: sorted(codes) for name, codes in mapped.items()},
        "food_away_mapping_rule": "all 2020-valid DIARY/EXPD UCC codes with 190 prefix; the official FMLD.FOODAWAY formula cell is truncated in the XLSX dictionary",
        "unmapped_known_code_rule": "a known 2020-valid EXPD UCC outside the five explicit groups is other_known_ucc",
        "unknown_code_rule": "an EXPD UCC absent from the 2020-valid DIARY/EXPD code dictionary is unknown_ucc",
    }
    return lookup, known_ucc, audit


def _hash_key(scope: str, value: str) -> str:
    return sha256_bytes(f"ce-diary-2020|{scope}|{value}".encode("utf-8"))


def _week_number(row: dict[str, Any]) -> int:
    newid = str(row.get("NEWID") or "").strip()
    if not newid or newid[-1:] not in WEEK_NUMBER_CODES:
        raise ValueError(f"2020 Diary NEWID does not end in week code 1/2: {newid!r}")
    from_id = int(newid[-1])
    raw_week = str(row.get("WEEKI") or "").strip()
    if raw_week:
        from_field = _int_code(raw_week, "WEEKI")
        if from_field != from_id:
            raise ValueError(f"NEWID week suffix and FMLD.WEEKI disagree for {newid!r}")
    return from_id


def _parse_csv_member(archive: zipfile.ZipFile, member: str) -> tuple[list[dict[str, Any]], list[str], str]:
    raw = archive.read(member)
    digest = sha256_bytes(raw)
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not reader.fieldnames:
        raise ValueError(f"empty CSV header in ZIP member {member}")
    headers = [str(field).strip().upper() for field in reader.fieldnames]
    if len(headers) != len(set(headers)):
        raise ValueError(f"duplicate headers in ZIP member {member}")
    rows = [_normal_row(row) for row in reader]
    return rows, headers, digest


def _member_index(names: Iterable[str], file_prefix: str) -> dict[int, str]:
    pattern = re.compile(rf"^{re.escape(file_prefix)}20([1-4])\.csv$", re.IGNORECASE)
    found: dict[int, str] = {}
    for name in names:
        match = pattern.fullmatch(Path(name).name)
        if not match:
            continue
        quarter = int(match.group(1))
        if quarter in found:
            raise ValueError(f"multiple {file_prefix}202{quarter} CSV files in Diary ZIP")
        found[quarter] = name
    return found


def _daily_category_totals(detail_rows: list[dict[str, Any]], category_map: dict[str, str],
                           known_ucc: set[str], day_field_available: bool,
                           day_flag_field_available: bool) -> dict:
    totals = {category: DECIMAL_ZERO for category in CATEGORY_NAMES}
    detail_hashes = []
    publication_amounts: dict[str, Decimal] = defaultdict(lambda: DECIMAL_ZERO)
    publication_counts: Counter[str] = Counter()
    allocation_counts: Counter[str] = Counter()
    not_published_by_category: dict[str, Decimal] = defaultdict(lambda: DECIMAL_ZERO)
    unknown_flag_by_category: dict[str, Decimal] = defaultdict(lambda: DECIMAL_ZERO)
    positive_published_days: set[int] = set()
    positive_published_n = 0
    positive_published_missing_day_n = 0
    invalid_cost_n = 0
    invalid_published_cost_n = 0
    missing_ucc_n = 0
    unknown_pub_flag_n = 0
    unknown_pub_flag_positive_n = 0
    known_excluded_cost = DECIMAL_ZERO
    unknown_flag_cost = DECIMAL_ZERO
    included_total = DECIMAL_ZERO
    included_cost_n = 0
    included_record_n = 0
    other_pub_flag_cost_n = 0

    for row in detail_rows:
        detail_hashes.append(canonical_hash(row))
        flag = str(row.get("PUB_FLAG") or "").strip()
        allocation_counts[str(row.get("ALLOC") or "").strip() or "blank"] += 1
        publication_counts[flag or "blank"] += 1
        try:
            cost = _number(row.get("COST"), "EXPD.COST")
        except ValueError:
            invalid_cost_n += 1
            if flag not in EXPECTED_FLAG_CODES:
                unknown_pub_flag_n += 1
            elif flag == "2":
                included_record_n += 1
                invalid_published_cost_n += 1
            continue

        if flag == "2":
            included_record_n += 1
            included_cost_n += 1
            included_total += cost
            ucc = str(row.get("UCC") or "").strip().zfill(6)
            if not str(row.get("UCC") or "").strip():
                missing_ucc_n += 1
                target = "unknown_ucc"
            elif ucc in category_map:
                target = category_map[ucc]
            elif ucc in known_ucc:
                target = "other_known_ucc"
            else:
                target = "unknown_ucc"
            totals[target] += cost
            if cost > 0:
                positive_published_n += 1
                raw_day = str(row.get(DAY_FIELD) or "").strip() if day_field_available else ""
                try:
                    raw_day_flag = str(row.get(DAY_FLAG_FIELD) or "").strip()
                    if day_flag_field_available and raw_day_flag not in VALID_DAY_FLAGS:
                        raise ValueError(f"invalid {DAY_FLAG_FIELD}: {raw_day_flag!r}")
                    day = _int_code(raw_day, f"EXPD.{DAY_FIELD}")
                except ValueError:
                    positive_published_missing_day_n += 1
                else:
                    if 1 <= day <= 7:
                        positive_published_days.add(day)
                    else:
                        positive_published_missing_day_n += 1
        elif flag == "1":
            known_excluded_cost += cost
            ucc = str(row.get("UCC") or "").strip().zfill(6)
            target = category_map.get(ucc)
            if target:
                not_published_by_category[target] += cost
        else:
            unknown_pub_flag_n += 1
            unknown_flag_cost += cost
            ucc = str(row.get("UCC") or "").strip().zfill(6)
            target = category_map.get(ucc)
            if target:
                unknown_flag_by_category[target] += cost
            if cost > 0:
                unknown_pub_flag_positive_n += 1

    if not detail_rows:
        amount_status = "zero_expd_rows"
    elif invalid_published_cost_n or unknown_pub_flag_n:
        amount_status = "partial_due_missing_cost_or_publication_flag"
    elif included_record_n == 0:
        amount_status = "no_pub_flag_2_records"
    elif missing_ucc_n:
        amount_status = "available_with_missing_ucc_assigned_unknown"
    else:
        amount_status = "available_for_pub_flag_2_records"

    if not day_field_available:
        day_status, day_count = "unavailable_schema", None
    elif not detail_rows:
        day_status, day_count = "zero_expd_rows", 0
    elif invalid_published_cost_n or unknown_pub_flag_positive_n:
        if positive_published_n:
            day_status, day_count = "partial_day_support", len(positive_published_days) if positive_published_days else None
        else:
            day_status, day_count = "unmeasurable_cost_or_publication_flag", None
    elif positive_published_n == 0:
        day_status, day_count = "zero_positive_pub_flag_2_cost_records", 0
    elif positive_published_missing_day_n:
        day_status, day_count = "partial_day_support", len(positive_published_days) if positive_published_days else None
    else:
        day_status, day_count = "available", len(positive_published_days)

    return {
        "amount_support_status": amount_status,
        "amount_by_category_usd": {name: _decimal_text(totals[name]) for name in CATEGORY_NAMES},
        "not_published_amount_by_category_usd": {
            name: _decimal_text(not_published_by_category[name]) for name in CATEGORY_NAMES
        },
        "unknown_flag_amount_by_category_usd": {
            name: _decimal_text(unknown_flag_by_category[name]) for name in CATEGORY_NAMES
        },
        "published_cost_sum_usd": _decimal_text(included_total),
        "not_published_cost_sum_usd": _decimal_text(known_excluded_cost),
        "unknown_pub_flag_cost_sum_usd": _decimal_text(unknown_flag_cost),
        "published_cost_record_count": included_cost_n,
        "published_expd_row_count": included_record_n,
        "not_published_expd_row_count": publication_counts.get("1", 0),
        "unrecognized_or_missing_pub_flag_row_count": unknown_pub_flag_n,
        "invalid_cost_row_count": invalid_cost_n,
        "missing_ucc_row_count": missing_ucc_n,
        "publication_flag_counts": dict(sorted(publication_counts.items())),
        "allocation_flag_counts": dict(sorted(allocation_counts.items())),
        "days_with_positive_published_cost_records": day_count,
        "day_support_status": day_status,
        "day_field_flag_counts": dict(sorted(Counter(
            str(row.get(DAY_FLAG_FIELD) or "").strip() or "blank" for row in detail_rows
        ).items())) if day_flag_field_available else {},
        "valid_distinct_positive_cost_day_codes": sorted(positive_published_days),
        "positive_published_cost_record_count": positive_published_n,
        "positive_published_cost_records_missing_valid_day_count": positive_published_missing_day_n,
        "detail_row_count": len(detail_rows),
        "detail_rows_sha256": canonical_hash(detail_hashes),
        "detail_row_hash_order": "source CSV row order within this quarter and NEWID",
    }


def _fmld_category_crosschecks(fmld_row: dict[str, Any], support: dict) -> dict[str, dict]:
    """Compare published EXPD category sums with independent FMLD summary fields."""
    comparisons: dict[str, dict] = {}
    for comparison_name, (amount_category, summary_fields) in SUMMARY_CROSSCHECKS.items():
        try:
            summary_total = sum(
                (_number(fmld_row[field], f"FMLD.{field}") for field in summary_fields),
                DECIMAL_ZERO,
            )
        except (KeyError, ValueError):
            comparisons[comparison_name] = {
                "status": "unavailable_fmld_summary_value",
                "summary_fields": list(summary_fields),
            }
            continue
        published = _number(support["amount_by_category_usd"][amount_category], amount_category)
        not_published = _number(
            support["not_published_amount_by_category_usd"][amount_category], amount_category
        )
        unknown_flag = _number(
            support["unknown_flag_amount_by_category_usd"][amount_category], amount_category
        )
        published_difference = published - summary_total
        including_pub_flag_1_difference = published + not_published - summary_total
        comparisons[comparison_name] = {
            "status": "comparable",
            "summary_fields": list(summary_fields),
            "summary_field_values_raw": {field: fmld_row[field] for field in summary_fields},
            "fmld_summary_sum_usd": _decimal_text(summary_total),
            "published_expd_pub_flag_2_sum_usd": _decimal_text(published),
            "excluded_expd_pub_flag_1_sum_usd": _decimal_text(not_published),
            "unknown_pub_flag_expd_sum_usd": _decimal_text(unknown_flag),
            "published_minus_fmld_summary_usd": _decimal_text(published_difference),
            "published_plus_pub_flag_1_minus_fmld_summary_usd": _decimal_text(including_pub_flag_1_difference),
        }
    return comparisons


def prepare_diary_week_rows(
    fmld_rows_by_quarter: dict[int, list[dict[str, Any]]],
    expd_rows_by_quarter: dict[int, list[dict[str, Any]]],
    category_map: dict[str, str] | dict[int, dict[str, str]],
    known_ucc: set[str] | dict[int, set[str]],
    *,
    source_members: dict[str, dict] | None = None,
) -> tuple[list[dict], dict]:
    """Join FMLD and EXPD within each 2020 quarter and exact Diary NEWID."""
    weekly: list[dict] = []
    quarter_audit: dict[str, dict] = {}
    for quarter in sorted(fmld_rows_by_quarter):
        if quarter not in expd_rows_by_quarter:
            raise ValueError(f"EXPD 2020Q{quarter} is missing")
        fmld = fmld_rows_by_quarter[quarter]
        expd = expd_rows_by_quarter[quarter]
        q_category_map = category_map.get(quarter) if quarter in category_map else category_map
        q_known_ucc = known_ucc.get(quarter) if isinstance(known_ucc, dict) else known_ucc
        if not isinstance(q_category_map, dict) or not isinstance(q_known_ucc, set):
            raise ValueError(f"category UCC mapping unavailable for 2020Q{quarter}")
        fmld_keys: dict[str, dict] = {}
        for raw_row in fmld:
            row = _normal_row(raw_row)
            missing = set(FMLD_REQUIRED_FIELDS) - row.keys()
            if missing:
                raise ValueError(f"FMLD 2020Q{quarter} missing required fields: {sorted(missing)}")
            newid = str(row.get("NEWID") or "").strip()
            if not newid:
                raise ValueError(f"blank FMLD.NEWID in 2020Q{quarter}")
            if newid in fmld_keys:
                raise ValueError(f"duplicate FMLD NEWID in 2020Q{quarter}: {newid}")
            week = _week_number(row)
            weight = _number(row.get("FINLWT21"), "FMLD.FINLWT21")
            if weight <= 0:
                raise ValueError(f"nonpositive FMLD.FINLWT21 for {newid}")
            row["_WEEK_NUMBER"] = week
            row["_WEIGHT_DECIMAL"] = weight
            row["_RAW_ROW_HASH"] = canonical_hash({k: v for k, v in row.items()
                                                     if not k.startswith("_")})
            fmld_keys[newid] = row

        detail_by_newid: dict[str, list[dict]] = defaultdict(list)
        expd_headers: set[str] = set()
        quarter_source_members = source_members or {}
        expd_header_manifest = quarter_source_members.get(f"expd_q{quarter}", {}).get("headers")
        if expd_header_manifest:
            expd_headers.update(expd_header_manifest)
            missing = set(AMOUNT_REQUIRED_FIELDS) - expd_headers
            if missing:
                raise ValueError(f"EXPD 2020Q{quarter} missing required fields: {sorted(missing)}")
        fmld_header_manifest = quarter_source_members.get(f"fmld_q{quarter}", {}).get("headers")
        if fmld_header_manifest:
            missing = set(FMLD_REQUIRED_FIELDS) - set(fmld_header_manifest)
            if missing:
                raise ValueError(f"FMLD 2020Q{quarter} missing required fields: {sorted(missing)}")
        for raw_row in expd:
            row = _normal_row(raw_row)
            expd_headers.update(row)
            missing = set(AMOUNT_REQUIRED_FIELDS) - row.keys()
            if missing:
                raise ValueError(f"EXPD 2020Q{quarter} missing required fields: {sorted(missing)}")
            newid = str(row.get("NEWID") or "").strip()
            if not newid:
                raise ValueError(f"blank EXPD.NEWID in 2020Q{quarter}")
            detail_by_newid[newid].append(row)
        orphan_ids = sorted(set(detail_by_newid) - set(fmld_keys))
        if orphan_ids:
            raise ValueError(f"EXPD rows lack same-quarter FMLD NEWID in 2020Q{quarter}: {len(orphan_ids)} IDs")

        day_field_available = DAY_FIELD in expd_headers
        day_flag_field_available = DAY_FLAG_FIELD in expd_headers
        category_reconciliation: dict[str, dict[str, Any]] = {}
        for comparison_name, (_, summary_fields) in SUMMARY_CROSSCHECKS.items():
            category_reconciliation[comparison_name] = {
                "summary_fields": list(summary_fields),
                "comparable_household_week_count": 0,
                "summary_value_unavailable_count": 0,
                "published_exact_match_household_week_count": 0,
                "exact_match_after_adding_pub_flag_1_household_week_count": 0,
                "published_expd_sum_usd": DECIMAL_ZERO,
                "excluded_pub_flag_1_expd_sum_usd": DECIMAL_ZERO,
                "unknown_pub_flag_expd_sum_usd": DECIMAL_ZERO,
                "fmld_summary_sum_usd": DECIMAL_ZERO,
                "published_minus_summary_sum_usd": DECIMAL_ZERO,
                "published_plus_pub_flag_1_minus_summary_sum_usd": DECIMAL_ZERO,
                "absolute_published_difference_sum_usd": DECIMAL_ZERO,
                "max_absolute_published_difference_usd": DECIMAL_ZERO,
            }
        for newid, row in sorted(fmld_keys.items()):
            detail_rows = detail_by_newid.get(newid, [])
            support = _daily_category_totals(detail_rows, q_category_map, q_known_ucc,
                                              day_field_available, day_flag_field_available)
            category_crosschecks = _fmld_category_crosschecks(row, support)
            for comparison_name, check in category_crosschecks.items():
                audit = category_reconciliation[comparison_name]
                if check["status"] != "comparable":
                    audit["summary_value_unavailable_count"] += 1
                    continue
                published = _number(check["published_expd_pub_flag_2_sum_usd"], "published amount")
                not_published = _number(check["excluded_expd_pub_flag_1_sum_usd"], "PUB_FLAG=1 amount")
                unknown_flag = _number(check["unknown_pub_flag_expd_sum_usd"], "unknown-flag amount")
                summary = _number(check["fmld_summary_sum_usd"], "FMLD category summary")
                difference = _number(check["published_minus_fmld_summary_usd"], "published difference")
                difference_after_pub_flag_1 = _number(
                    check["published_plus_pub_flag_1_minus_fmld_summary_usd"],
                    "PUB_FLAG=1 adjusted difference",
                )
                audit["comparable_household_week_count"] += 1
                audit["published_expd_sum_usd"] += published
                audit["excluded_pub_flag_1_expd_sum_usd"] += not_published
                audit["unknown_pub_flag_expd_sum_usd"] += unknown_flag
                audit["fmld_summary_sum_usd"] += summary
                audit["published_minus_summary_sum_usd"] += difference
                audit["published_plus_pub_flag_1_minus_summary_sum_usd"] += difference_after_pub_flag_1
                audit["absolute_published_difference_sum_usd"] += abs(difference)
                audit["max_absolute_published_difference_usd"] = max(
                    audit["max_absolute_published_difference_usd"], abs(difference)
                )
                if difference == 0:
                    audit["published_exact_match_household_week_count"] += 1
                if difference_after_pub_flag_1 == 0:
                    audit["exact_match_after_adding_pub_flag_1_household_week_count"] += 1
            week = row["_WEEK_NUMBER"]
            week_key = _hash_key(f"week|Q{quarter}", newid)
            cu_key = _hash_key(f"cu|Q{quarter}", newid[:-1])
            demographic_values = {field: row[field] for field in OPTIONAL_FMLD_FIELDS if field in row}
            profile_field_hashes = {field: canonical_hash(row.get(field))
                                    for field in OPTIONAL_FMLD_FIELDS if field in row}
            summary_values = {field: row[field] for field in
                              ("FOODHOME", "FOODAWAY", "FOODTOT", "ALCBEV", "HOUSKEEP", "PERSPROD", "PERSSERV")
                              if field in row}
            members = quarter_source_members
            weekly.append({
                "schema_version": "ce-diary-weekly-experience-v1",
                "survey": "BLS Consumer Expenditure Diary Survey",
                "year": TARGET_YEAR,
                "collection_quarter": quarter,
                "diary_week_number": week,
                "diary_week_key_sha256": week_key,
                "diary_cu_pair_key_sha256": cu_key,
                "sampling_weight_FINLWT21": _decimal_text(row["_WEIGHT_DECIMAL"]),
                "weight_unit": "one NEWID representing one CU-week; retained separately for diary week 1 or 2",
                "consumer_unit_demographics_raw": demographic_values,
                "consumer_unit_demographics_field_sha256": profile_field_hashes,
                "fmld_reported_weekly_summary_raw": summary_values,
                "category_summary_crosschecks": category_crosschecks,
                "source": {
                    "fmld_member": members.get(f"fmld_q{quarter}", {}).get("member"),
                    "expd_member": members.get(f"expd_q{quarter}", {}).get("member"),
                    "fmld_row_sha256": row["_RAW_ROW_HASH"],
                    "expd_detail_row_count": support["detail_row_count"],
                    "expd_detail_rows_sha256": support["detail_rows_sha256"],
                },
                "amounts": {
                    "unit": "USD per reported 7-day Diary week",
                    "definition": "sum of EXPD.COST including sales tax, restricted to PUB_FLAG=2, and categorized by active 2020 BLS Diary UCC formulas",
                    "support_status": support["amount_support_status"],
                    "category_amounts_usd": support["amount_by_category_usd"],
                    "published_cost_sum_usd": support["published_cost_sum_usd"],
                    "not_published_cost_sum_usd": support["not_published_cost_sum_usd"],
                    "unknown_pub_flag_cost_sum_usd": support["unknown_pub_flag_cost_sum_usd"],
                    "detail_record_counts": {
                        "all_expd_rows": support["detail_row_count"],
                        "published_pub_flag_2_rows": support["published_expd_row_count"],
                        "not_published_pub_flag_1_rows": support["not_published_expd_row_count"],
                        "unrecognized_or_missing_pub_flag_rows": support["unrecognized_or_missing_pub_flag_row_count"],
                        "invalid_cost_rows": support["invalid_cost_row_count"],
                        "missing_ucc_rows": support["missing_ucc_row_count"],
                    },
                },
                "purchase_day_support": {
                    "field": DAY_FIELD if day_field_available else None,
                    "field_flag": DAY_FLAG_FIELD if day_flag_field_available else None,
                    "field_flag_counts": support["day_field_flag_counts"],
                    "status": support["day_support_status"],
                    "distinct_days_with_positive_published_cost_records": support["days_with_positive_published_cost_records"],
                    "valid_day_codes_1_to_7": support["valid_distinct_positive_cost_day_codes"],
                    "positive_published_cost_record_count": support["positive_published_cost_record_count"],
                    "positive_published_cost_records_missing_valid_day_count": support["positive_published_cost_records_missing_valid_day_count"],
                    "interpretation": "one overall distinct-day count across all expense categories, from day codes on positive-cost PUB_FLAG=2 records; source rows are not counted as transactions and exact calendar purchase dates are unavailable",
                },
                "scope_limitations": [
                    "Diary CU differs from an SCE individual respondent; this is an external synthetic evidence source, not the target person's observed wallet",
                    "Diary NEWID identifies a Diary CU-week; it is never joined to Interview NEWID or SCE respondent IDs",
                    "Weeks 1 and 2 are separate weighted weekly observations; no weekly value is annualized or multiplied by 13",
                    "A zero detail-record count means zero matching published microdata records, not proof of zero actual spending",
                    "Daily frequency is a diary-recorded-day proxy, not shopping trips, number of transactions, or a stable annual habit",
                ],
            })

        weight_by_week: dict[str, dict] = {}
        for week in (1, 2):
            rows = [r for r in fmld_keys.values() if r["_WEEK_NUMBER"] == week]
            if rows:
                weight_by_week[str(week)] = {
                    "household_week_n": len(rows),
                    "sum_FINLWT21": _decimal_text(sum((r["_WEIGHT_DECIMAL"] for r in rows), DECIMAL_ZERO)),
                    "weight_min": _decimal_text(min(r["_WEIGHT_DECIMAL"] for r in rows)),
                    "weight_max": _decimal_text(max(r["_WEIGHT_DECIMAL"] for r in rows)),
                }
        quarter_audit[str(quarter)] = {
            "fmld_household_week_rows": len(fmld_keys),
            "expd_newid_count": len(detail_by_newid),
            "expd_rows": sum(len(rows) for rows in detail_by_newid.values()),
            "fmld_rows_without_expd_rows": sum(newid not in detail_by_newid for newid in fmld_keys),
            "expd_rows_without_fmld_rows": 0,
            "day_field_available": day_field_available,
            "category_summary_reconciliation": {
                category: {
                    **{
                        key: (_decimal_text(value) if isinstance(value, Decimal) else value)
                        for key, value in audit.items()
                    },
                    "interpretation": "independent FMLD summary check; published-only differences and PUB_FLAG=1 exclusions are retained explicitly",
                }
                for category, audit in category_reconciliation.items()
            },
            "weight_by_diary_week": weight_by_week,
        }

    weekly.sort(key=lambda r: (r["collection_quarter"], r["diary_week_number"], r["diary_week_key_sha256"]))
    return weekly, {"quarter_audit": quarter_audit, "household_week_rows": len(weekly)}


def read_official_diary_zip(zip_path: str | Path, *, quarter: int = TARGET_QUARTER) -> tuple[dict, dict, dict, dict]:
    """Read only the explicit 2020Q4 FMLD and EXPD files from the annual ZIP."""
    if quarter != TARGET_QUARTER:
        raise ValueError("this preparation entry point is fixed to the explicit 2020Q4 Diary wave")
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        fmld_members = _member_index(names, "fmld")
        expd_members = _member_index(names, "expd")
        if quarter not in fmld_members or quarter not in expd_members:
            raise ValueError(
                "Diary ZIP must contain the explicit 2020Q4 FMLD and EXPD CSV files; "
                f"found FMLD quarters={sorted(fmld_members)}, EXPD quarters={sorted(expd_members)}"
            )
        fmld_rows: dict[int, list[dict]] = {}
        expd_rows: dict[int, list[dict]] = {}
        members: dict[str, dict] = {}
        fmember, emember = fmld_members[quarter], expd_members[quarter]
        frows, fheaders, fhash = _parse_csv_member(archive, fmember)
        erows, eheaders, ehash = _parse_csv_member(archive, emember)
        fmld_rows[quarter], expd_rows[quarter] = frows, erows
        members[f"fmld_q{quarter}"] = {"member": fmember, "sha256": fhash,
                                         "row_count": len(frows), "headers": fheaders}
        members[f"expd_q{quarter}"] = {"member": emember, "sha256": ehash,
                                         "row_count": len(erows), "headers": eheaders}
    return fmld_rows, expd_rows, members, {"archive_member_count": len(names), "processed_quarter": quarter}
