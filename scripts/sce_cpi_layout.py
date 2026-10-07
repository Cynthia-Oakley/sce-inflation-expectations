"""Deterministically read annual CPI component changes from BLS release PDFs.

The preferred source is the current-reference-month row in Table A. When that
table is not extractable, a dated Table 1 can be read by its explicit annual
column, or a narrowly constrained annual sentence can be used.
"""
from __future__ import annotations

import calendar
import re
from pathlib import Path


ROW_LABELS = {
    "cpi_food_yoy": "Food",
    "cpi_food_at_home_yoy": "Food at home",
    "cpi_energy_yoy": "Energy",
    "cpi_shelter_yoy": "Shelter",
    "cpi_gasoline_yoy": "Gasoline (all types)",
}

MONTHS = {calendar.month_name[i].lower(): i for i in range(1, 13)}
MONTHS.update({calendar.month_abbr[i].lower().rstrip("."): i for i in range(1, 13)})
NUMBER_RE = re.compile(r"(?<![\w.])[-+]?(?:\d+\.\d+|\.\d+)(?![\w.])")


def _period(reference_period: str) -> tuple[int, int, str, str]:
    match = re.fullmatch(r"(\d{4})-(\d{2})", reference_period)
    if not match:
        raise ValueError("reference_period must be YYYY-MM")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError("reference_period month must be 01-12")
    return year, month, calendar.month_name[month], calendar.month_abbr[month]


def _read_pdf_pages(pdf_path: Path) -> list[dict[str, str]]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    result = []
    for page in reader.pages:
        result.append({
            "layout": page.extract_text(extraction_mode="layout") or "",
            "plain": "",
        })
    return result


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _fix_layout_numbers(text: str) -> str:
    # BLS table extraction sometimes separates the fractional digit from its dot.
    return re.sub(r"(?<=\.)\s+(?=\d)", "", text)


def _canonical_header(text: str) -> str:
    text = _collapse(text)
    text = re.sub(r"Un-\s*adjusted", "Un-adjusted", text, flags=re.I)
    text = re.sub(r"12-\s*m\s*o\s*s\s*\.", "12-mos.", text, flags=re.I)
    text = re.sub(r"12-\s*mos\s*\.", "12-mos.", text, flags=re.I)
    text = re.sub(r"([A-Za-z])\s+\.", r"\1.", text)
    return text


def _table_a_header(text: str, reference_period: str) -> str | None:
    year, month, full_month, abbreviated_month = _period(reference_period)
    canonical = _canonical_header(text)
    match = re.search(
        r"Un-adjusted.{0,700}?12-mos\..{0,300}?ended\s+([A-Za-z]+)\.?\s+(\d{4})",
        canonical,
        flags=re.I,
    )
    if not match:
        return None
    header_month = MONTHS.get(match.group(1).lower().rstrip("."))
    if header_month != month or int(match.group(2)) != year:
        return None
    return f"Un-adjusted 12-mos. ended {abbreviated_month}. {year}"


def _table_a_row(line: str, label: str) -> tuple[list[str], str] | None:
    """Return the row's eight monthly/annual decimals and normalized quote."""
    line = _collapse(line)
    escaped = re.escape(label)
    match = re.match(
        rf"^\s*{escaped}\s+(?P<leaders>\.{{3,}})(?P<tail>.*)$",
        line,
        flags=re.I,
    )
    if not match:
        return None
    tail = _fix_layout_numbers(match.group("tail"))
    values = NUMBER_RE.findall(tail)
    if len(values) != 8:
        return None
    return values, _collapse(line)


def _table_a(
    pages: list[dict[str, str]], signal: str, reference_period: str
) -> dict | None:
    label = ROW_LABELS[signal]
    candidates: list[dict] = []
    for page_no, page in enumerate(pages, start=1):
        layout = page["layout"]
        if not re.search(r"Table\s+A\.", layout, flags=re.I):
            continue
        header = _table_a_header(layout, reference_period)
        if header is None:
            continue
        lines = layout.splitlines()
        table_pos = next(
            (i for i, line in enumerate(lines) if re.search(r"Table\s+A\.", line, re.I)),
            0,
        )
        for line in lines[table_pos + 1 :]:
            row = _table_a_row(line, label)
            if row is None:
                continue
            values, quote = row
            candidates.append({
                "value": float(values[-1]),
                "quote": quote,
                "page": page_no,
                "header": header,
                "pattern": f"table_a_layout:{label}:8th_decimal",
                "extraction": "table_a_layout",
            })
    if not candidates:
        return None
    # Some pypdf layouts repeat a row. Accept duplicates only when they agree.
    if len({candidate["value"] for candidate in candidates}) != 1:
        return None
    return candidates[0]


def _table1_header(text: str, reference_period: str) -> str | None:
    year, month, full_month, abbreviated_month = _period(reference_period)
    canonical = _collapse(text)
    if not re.search(r"Table\s+1\.", canonical, flags=re.I):
        return None
    # pypdf layout may put the word "change" on a separate header line; keep
    # the two column-group names and the report month/year as independent
    # checks, then use Table 1's documented fixed column order below.
    if not re.search(r"Unadjusted\s+percent", canonical, flags=re.I):
        return None
    if not re.search(r"Seasonally\s+adjusted\s+percent", canonical, flags=re.I):
        return None
    if not re.search(rf"\b{re.escape(full_month)}\s+{year}\b", canonical, flags=re.I):
        return None
    if not re.search(rf"{year - 1}\s*-\s*{full_month}\.?", canonical, flags=re.I):
        # Layout extraction separates the header's start/end year and month
        # into adjacent column-label rows. Confirm the start year is present;
        # the title and current-month column above anchor the end of the range.
        if str(year - 1) not in canonical:
            return None
    return f"Table 1: Unadjusted percent change; {full_month} {year - 1}–{full_month} {year}"


def _table1_row(line: str, label: str) -> tuple[list[str], str] | None:
    line = _collapse(line)
    match = re.match(
        rf"^\s*{re.escape(label)}\s*(?P<leaders>(?:\.\s*){{3,}}?)(?=\s*[-+]?(?:\d+\.\d+|\.\d+))(?P<tail>.*)$",
        line,
        flags=re.I,
    )
    if not match:
        return None
    values = NUMBER_RE.findall(_fix_layout_numbers(match.group("tail")))
    if len(values) != 9:
        return None
    return values, _collapse(line)


def _table1(
    pages: list[dict[str, str]], signal: str, reference_period: str
) -> dict | None:
    label = ROW_LABELS[signal]
    candidates: list[dict] = []
    for page_no, page in enumerate(pages, start=1):
        layout = page["layout"]
        header = _table1_header(layout, reference_period)
        if header is None:
            continue
        lines = layout.splitlines()
        for line in lines:
            row = _table1_row(line, label)
            if row is None:
                continue
            values, quote = row
            # Table 1 columns: relative importance; three unadjusted index
            # levels; then year-over-year, followed by monthly changes.
            candidates.append({
                "value": float(values[4]),
                "quote": quote,
                "page": page_no,
                "header": header,
                "pattern": f"table1_layout:{label}:unadjusted_yoy_column_1_of_5",
                "extraction": "table1_layout",
            })
    if not candidates or len({candidate["value"] for candidate in candidates}) != 1:
        return None
    return candidates[0]


def _normalize_prose(text: str) -> str:
    text = _collapse(text)
    fixes = (
        ("Th e ", "The "), ("T he ", "The "), ("Ove r ", "Over "),
        ("f ood", "food"), ("F ood", "Food"), ("s helter", "shelter"),
        ("S helter", "Shelter"), ("e nergy", "energy"), ("E nergy", "Energy"),
        ("i ndex", "index"), ("m edical", "medical"),
    )
    for bad, good in fixes:
        text = text.replace(bad, good)
    return text


def _prose_fallback(
    pages: list[dict[str, str]], signal: str, reference_period: str
) -> dict | None:
    prose_labels = {
        "cpi_food_yoy": r"food\s+index",
        "cpi_food_at_home_yoy": r"food\s+at\s+home\s+index",
        "cpi_energy_yoy": r"energy\s+index",
        "cpi_shelter_yoy": r"shelter\s+index",
        "cpi_gasoline_yoy": r"(?:gasoline\s+index|index\s+for\s+gasoline)",
    }
    target = prose_labels[signal]
    verb_options = r"rose|rising|increased|increasing|advanced|advancing|grew|growing|climbed|climbing|fell|falling|declined|declining|decreased|decreasing|dropped|dropping"
    verb_re = rf"(?P<verb>{verb_options})"
    annual_suffix = r"(?:over\s+the\s+(?:last|past)\s+12\s+months?|over\s+the\s+past\s+year|over\s+the\s+year)"
    value_re = r"(?P<num>\d+\.\d)\s*(?:-|–)?\s*percent"
    year, month, full_month, abbreviated_month = _period(reference_period)
    direct = re.compile(
        rf"\b{target}\s+{verb_re}\s+{value_re}\s+{annual_suffix}\b",
        re.I,
    )
    inherited_food_home = re.compile(
        rf"\bfood\s+index\s+(?:{verb_options})\s+\d+\.\d\s*(?:-|–)?\s*percent\s+"
        rf"over\s+the\s+(?:past\s+year|(?:last|past)\s+12\s+months?),\s+"
        rf"(?:with\s+)?the\s+food\s+at\s+home\s+index\s+{verb_re}\s+{value_re}",
        re.I,
    ) if signal == "cpi_food_at_home_yoy" else None
    negative_verbs = {"fell", "falling", "declined", "declining", "decreased", "decreasing", "dropped", "dropping"}

    for page_no, page in enumerate(pages, start=1):
        # A plain extraction is used only for narrative fallback pages.
        text = _normalize_prose(page["plain"] or page["layout"])
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
        for sentence in sentences:
            candidates = [(match, "prose_direct_annual_suffix") for match in direct.finditer(sentence)]
            if inherited_food_home is not None:
                candidates.extend((match, "prose_inherited_food_index_annual_scope")
                                  for match in inherited_food_home.finditer(sentence))
            for match, pattern in candidates:
                verb = match.groupdict().get("verb")
                number = match.groupdict().get("num")
                if verb is None or number is None:
                    continue
                if signal == "cpi_energy_yoy":
                    prefix = sentence[max(0, match.start() - 40) : match.start()]
                    if re.search(r"all\s+items\s+less\s+food\s+and\s*$", prefix, re.I):
                        continue
                verb = verb.lower()
                value = float(number)
                if verb in negative_verbs:
                    value = -abs(value)
                else:
                    value = abs(value)
                return {
                    "value": value,
                    "quote": _collapse(match.group(0)),
                    "page": page_no,
                    "header": f"annual narrative for {full_month} {year}",
                    "pattern": pattern,
                    "extraction": "annual_prose",
                }
    return None


def extract_annual_component(
    pdf_path: str | Path, signal: str, reference_period: str
) -> dict | None:
    """Extract an NSA 12-month CPI change for ``signal`` and reference month.

    The returned dictionary has ``value``, ``page``, ``quote``, ``header``,
    ``pattern`` and ``extraction``. A missing or ambiguous source returns None.
    """
    if signal not in ROW_LABELS:
        raise ValueError(f"unsupported signal: {signal}")
    year, month, _, _ = _period(reference_period)
    pdf_path = Path(pdf_path)
    name_match = re.search(r"cpi_(\d{4})_(\d{2})_released_", pdf_path.name)
    if name_match and (int(name_match.group(1)), int(name_match.group(2))) != (year, month):
        return None
    pages = _read_pdf_pages(pdf_path)
    result = _table_a(pages, signal, reference_period)
    if result is not None:
        return result
    result = _table1(pages, signal, reference_period)
    if result is not None:
        return result
    return _prose_fallback(pages, signal, reference_period)
