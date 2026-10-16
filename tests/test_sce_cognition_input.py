"""Synthetic-only checks of the cognition input boundary and presentation."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "studies/sce_inflation_expectations"))
import cognition_input as c


def row(uid, month, **answers):
    return {"userid": uid, "date": month, "_source_path": "synthetic/raw.xlsx",
            "_source_sha256": "a" * 64, **answers}


def test_own_strictly_past_answers_only_and_no_backfill():
    rows = [row(1, 202002, QNUM1="00150.00", QNUM8="2"),
            row(2, 202001, QNUM2="900"),
            row(1, 202004, QNUM2="220.50", QNUM8="3"),
            row(1, 202003, QNUM1=None, QNUM9="1", Q9_mean="999", gender="Female")]
    early, later = c.build_records([{"userid": "1", "month": 202002},
                                    {"userid": 1, "month": "2020-04"}], rows)
    assert all(i["status"] == "missing" for i in early["items"])
    items = {i["field"]: i for i in later["items"]}
    assert items["QNUM1"]["raw_answer"] == "00150.00"
    assert items["QNUM1"]["source_month"] == 202002
    assert items["QNUM2"]["status"] == "missing"
    assert items["QNUM8"]["raw_answer"] == "2"
    assert items["QNUM8"]["answer_text"] == "Exactly the same"
    assert items["QNUM9"]["source_month"] == 202003
    encoded = json.dumps(later)
    assert "userid" not in encoded and "gender" not in encoded and "Q9_mean" not in encoded


def test_missing_dont_know_and_unmapped_codes_are_never_scored():
    record = c.build_records([{"userid": 1, "month": 202004}], [
        row(1, 202001, QNUM1="999", QNUM8="1"),
        row(1, 202003, QNUM2="Don't know", QNUM8="99", QNUM9="-999")])[0]
    items = {i["field"]: i for i in record["items"]}
    assert items["QNUM1"]["status"] == "answered"  # 999 is not an invented sentinel.
    assert items["QNUM2"]["status"] == "dont_know"
    assert items["QNUM3"]["status"] == "missing"
    assert items["QNUM8"]["raw_answer"] == "99"
    assert items["QNUM8"]["status"] == "unmapped"
    assert items["QNUM9"]["status"] == "unmapped"
    for arm in c.ARMS:
        text = c.render_cognition_block(arm, record).lower()
        for forbidden in ("correct", "incorrect", "score", "242", "poor at", "make mistakes"):
            assert forbidden not in text


def test_detailed_arms_preserve_scenarios_units_choices_and_personal_answer():
    record = c.build_records([{"userid": 1, "month": 202004}], [row(
        1, 202001, QNUM1="120.75", QNUM2="220", QNUM3="11", QNUM5="10",
        QNUM6="50", QNUM8="1", QNUM9="1")])[0]
    assert c.render_cognition_block("label_only", record) == ""
    qa = c.render_cognition_block("question_answer", record)
    paraphrase = c.render_cognition_block("faithful_paraphrase", record)
    assert qa != paraphrase
    for text in (qa, paraphrase):
        for token in ("$300", "$200", "$10.00", "1%", "1,000", "10 percent", "0.0005", "10,000", "2%", "120.75 dollars", "220 dollars", "11 people", "50 people"):
            assert token in text
        assert "ten per cent" in text and "two years" in text and "anniversary" in text
        assert "More than today (1); Exactly the same (2); Less than today (3)" in text
        assert "True (1); False (2)" in text
        assert "Your response: True (recorded code: 1)" in text
        assert "High" not in text and "Low" not in text
        assert text.count("2020-01") == 7
    for q in c.question_catalog()["questions"]:
        assert q["question"] in qa


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(userid=1),
    lambda r: r.update(truth={"Q9_mean": 5}),
    lambda r: r["items"][0].update(correct=True),
    lambda r: r["items"][0].update(answer_text="150 dollars"),
    lambda r: r["items"][0].update(source_month=202004),
    lambda r: r["items"][0].update(source_month=202005),
    lambda r: r["items"][0].update(source_path="../private.xlsx"),
    lambda r: r.update(catalog_sha256="0" * 64),
    lambda r: r["items"].reverse(),
])
def test_runtime_validator_rejects_truth_extra_fields_tampering_and_future(mutation):
    record = c.build_records([{"userid": 1, "month": 202004}], [row(1, 202003, QNUM1="120")])[0]
    mutation(record)
    with pytest.raises(ValueError):
        c.validate_cognition_record(record)
    with pytest.raises(ValueError):
        c.render_cognition_block("question_answer", record)


def test_catalog_detached_and_duplicate_rows_rejected():
    catalog = c.question_catalog()
    catalog["questions"][0]["question"] = "changed"
    assert c.question_catalog()["questions"][0]["question"].startswith("In a sale")
    with pytest.raises(ValueError, match="Duplicate"):
        c.build_records([{"userid": 1, "month": 202004}], [row(1, 202001), row(1, 202001)])
    with pytest.raises(ValueError, match="arm"):
        c.render_cognition_block("invented", c.build_records([{"userid": 1, "month": 202004}], [])[0])


def workbook(path):
    # Data is intentionally sheet2; QNUM1 uses an exact numeric XML lexeme.
    headers = ["userid", "date", *c.FIELDS, "Q9_mean"]
    letters = [chr(ord("A") + i) for i in range(len(headers))]
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    head = ''.join(f'<c r="{l}2" t="inlineStr"><is><t>{v}</t></is></c>' for l, v in zip(letters, headers))
    values = ["1", "202001", "00120.7500", "220", "11", "10", "50", "1", "2", "98765"]
    body = ''.join(f'<c r="{l}3"><v>{v}</v></c>' for l, v in zip(letters, values))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" sheetId="2" r:id="rId2"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet2.xml", f'<worksheet xmlns="{ns}"><sheetData><row r="2">{head}</row><row r="3">{body}</row></sheetData></worksheet>')


def test_stream_reads_raw_numeric_lexemes_and_whitelist_only(tmp_path):
    path = tmp_path / "synthetic.xlsx"
    workbook(path)
    rows = list(c._workbook_rows(path))
    assert len(rows) == 1
    assert rows[0]["QNUM1"] == "00120.7500"
    assert set(rows[0]) == {"userid", "date", *c.FIELDS}


def test_load_records_verifies_pinned_files_and_preserves_request_order(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.xlsx"
    workbook(path)
    q = tmp_path / "questionnaire.pdf"
    q.write_bytes(b"synthetic official-questionnaire fixture")
    monkeypatch.setattr(c, "QUESTIONNAIRE_PATH", "questionnaire.pdf")
    monkeypatch.setattr(c, "QUESTIONNAIRE_SHA256", hashlib.sha256(q.read_bytes()).hexdigest())
    specs = [{"path": path.name, "start": 202001, "end": 202012, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]
    records = c.load_records([{"userid": 2, "month": 202004}, {"userid": "1", "month": 202002}], root=tmp_path, source_specs=specs)
    assert records[0]["items"][0]["status"] == "missing"
    assert records[1]["items"][0]["raw_answer"] == "00120.7500"
    assert records[1]["items"][0]["source_sha256"] == specs[0]["sha256"]
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="workbook hash"):
        c.load_records([{"userid": 1, "month": 202002}], root=tmp_path, source_specs=specs)
    q.write_bytes(b"changed")
    with pytest.raises(ValueError, match="questionnaire changed"):
        c.load_records([{"userid": 1, "month": 202002}], root=tmp_path, source_specs=specs)
