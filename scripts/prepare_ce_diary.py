#!/usr/bin/env python3
"""Prepare weekly 2020 CE Diary experience records offline; this script never calls an LLM."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DIARY_MODULE_PATH = ROOT / "studies/sce_inflation_expectations/diary_experience.py"
DIARY_MODULE_SPEC = importlib.util.spec_from_file_location("_ce_diary_experience", DIARY_MODULE_PATH)
if DIARY_MODULE_SPEC is None or DIARY_MODULE_SPEC.loader is None:
    raise ImportError(f"cannot load Diary processing module: {DIARY_MODULE_PATH}")
diary_module = importlib.util.module_from_spec(DIARY_MODULE_SPEC)
sys.modules[DIARY_MODULE_SPEC.name] = diary_module
DIARY_MODULE_SPEC.loader.exec_module(diary_module)

DIARY_ZIP_URL = diary_module.DIARY_ZIP_URL
DICTIONARY_URL = diary_module.DICTIONARY_URL
ERRATA_URL = diary_module.ERRATA_URL
GETTING_STARTED_URL = diary_module.GETTING_STARTED_URL
KNOWN_AVAILABLE_BY_DATE = diary_module.KNOWN_AVAILABLE_BY_DATE
KNOWN_AVAILABLE_BY_URL = diary_module.KNOWN_AVAILABLE_BY_URL
TARGET_QUARTER = diary_module.TARGET_QUARTER
TARGET_YEAR = diary_module.TARGET_YEAR
category_map_from_dictionary = diary_module.category_map_from_dictionary
file_sha256 = diary_module.file_sha256
prepare_diary_week_rows = diary_module.prepare_diary_week_rows
read_official_diary_zip = diary_module.read_official_diary_zip
sha256_bytes = diary_module.sha256_bytes


DEFAULT_ZIP = ROOT / "data/raw/ce_experience/20261006/diary/diary20.zip"
DEFAULT_DICTIONARY = ROOT / "data/raw/ce_experience/20261006/ce_pumd_dictionary_official.xlsx"
PROFILE_FIELDS = ("AGE_REF", "EDUC_REF", "CUTENURE", "REGION", "STATE", "FINCBEFM", "FINCBEFX")
SUMMARY_FIELDS = ("FOODHOME", "FOODAWAY", "FOODTOT", "ALCBEV", "HOUSKEEP", "PERSPROD", "PERSSERV")


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False) + "\n")


def _readme(run_id: str, zip_sha: str, dictionary_sha: str, retrieved_date: str,
            source_url: str, dictionary_url: str, mapping_audit: dict,
            source_members: dict, run_audit: dict) -> str:
    map_lines = []
    for quarter, detail in sorted(mapping_audit.items()):
        map_lines.append(
            f"- 2020 Q{quarter}: " + ", ".join(
                f"`{name}` {count} UCCs" for name, count in detail["category_ucc_counts"].items()
            )
        )
    input_lines = []
    for key, entry in sorted(source_members.items()):
        input_lines.append(
            f"- `{entry['member']}`: {entry['row_count']:,} CSV rows; SHA-256 `{entry['sha256']}`"
        )
    quarter_lines = []
    reconciliation_lines = []
    for quarter, audit in sorted(run_audit["quarter_audit"].items()):
        week_parts = []
        for week, weights in sorted(audit["weight_by_diary_week"].items()):
            week_parts.append(
                f"week {week}: n={weights['household_week_n']:,}, "
                f"sum FINLWT21={weights['sum_FINLWT21']}"
            )
        quarter_lines.append(f"- 2020 Q{quarter}: " + "; ".join(week_parts))
        for category, crosscheck in sorted(audit["category_summary_reconciliation"].items()):
            reconciliation_lines.append(
                f"- 2020 Q{quarter} `{category}` vs FMLD {', '.join(crosscheck['summary_fields'])}: "
                f"comparable CU-weeks={crosscheck['comparable_household_week_count']:,}; "
                f"published-only exact matches={crosscheck['published_exact_match_household_week_count']:,}; "
                f"published minus summary sum=${crosscheck['published_minus_summary_sum_usd']}; "
                f"excluded PUB_FLAG=1 sum=${crosscheck['excluded_pub_flag_1_expd_sum_usd']}; "
                f"exact after adding PUB_FLAG=1={crosscheck['exact_match_after_adding_pub_flag_1_household_week_count']:,}"
            )
    return f"""# CE Diary 2020 weekly experience preparation

Run ID: `{run_id}`
Retrieved date recorded: {retrieved_date}
Diary ZIP SHA-256: `{zip_sha}`
Dictionary XLSX SHA-256: `{dictionary_sha}`

## Source and version

- Diary archive: [{source_url}]({source_url}), the official BLS 2020 CSV Diary PUMD ZIP. This run reads only Q4 FMLD/EXPD members.
- Field and UCC codebook: [{dictionary_url}]({dictionary_url}), the current official Interview/Diary XLSX dictionary retrieved from BLS.
- The current 2020 public-use file includes BLS corrections published on 2022-03-10. See the [official errata]({ERRATA_URL}). It is a current corrected copy, not evidence of the version available at a 2021 forecast cutoff.
- BLS's [2021-09-09 annual release]({KNOWN_AVAILABLE_BY_URL}) states that 1980–2020 annual CE PUMD Interview and Diary files were available. This establishes `known_available_by={KNOWN_AVAILABLE_BY_DATE}` only; it is not a first-release date or evidence of this local 2022-corrected file vintage, and it does not certify availability by a 2021 May/June cutoff.
- Survey linkage, day-field and weighting rules follow the [BLS Getting Started Guide]({GETTING_STARTED_URL}).
- Data were processed locally with deterministic Python code. No JSONL or household record was sent to an LLM or remote service.

## Join, unit, and weights

The unit in `diary_weekly.jsonl` is one Diary consumer unit (CU) in one seven-day diary week. The script joins each quarterly FMLD demographic/weight record to EXPD detail records using the exact `NEWID` **within the same quarter**. Per BLS documentation, the final digit of Diary `NEWID` identifies week 1 or 2; the earlier digits identify the CU. FMLD and EXPD are joined on this week-specific ID. The output contains scoped SHA-256 keys instead of raw `NEWID` values; the CU-pair key only relates two weeks within this Diary sample.

BLS treats diary weeks as statistically independent and weights each week separately. Each output row therefore keeps its own `FINLWT21`, `diary_week_number`, and quarter. The output does not collapse weeks or multiply weekly amounts by 13 or by 52. The official unit is a CU, not an SCE person, and Diary and Interview use different samples; this code never reads the Interview ZIP or joins Interview IDs.

## Amount-only and day support

`amounts.category_amounts_usd` sums `EXPD.COST` (dictionary definition: total item cost including sales tax) for rows used in BLS published expenditure statistics (`PUB_FLAG=2`), by the explicit 2020 codebook map below. Amounts remain USD per reported seven-day Diary week; no annualized frequency or CPI/price exposure is calculated. `PUB_FLAG=1` records are present in the public-use microdata, but BLS does not use their values in published expenditure statistics; this preparation excludes them from category amounts and reports them separately. Rows with an unknown publication flag are also kept separate.

The field dictionary contains `EXPD.EXPNSQDY`, defined as the sequential day in the diary week (1–7), and its companion flag `EXPN_QDY`. Where these fields are in the CSV schema, `purchase_day_support` counts **distinct valid day codes across all expense categories with positive-cost, `PUB_FLAG=2` detail rows whose day flag is valid (D/E/T)**. It is one overall weekly day count, not a category-specific frequency measure. It does not count EXPD rows as transactions or recover the exact calendar date. If the day field is absent, the status is `unavailable_schema`; incomplete or invalid day values produce a partial or unmeasurable status. A zero detail-row count is labeled `zero_expd_rows`, while missing/invalid source support is labeled separately; zero recorded rows do not establish that a CU had no actual spending.

## Category mapping

The category map uses 2020-effective definitions in the official XLSX `Variables` and `Codes ` sheets. The categories are mutually exclusive. `FOODHOME`, `HOUSKEEP`, `PERSPROD`, and `PERSSERV` formula UCCs are resolved recursively. When the dictionary has overlapping open-ended formula rows for the same variable, the latest effective start is selected and recorded in the manifest. BLS's `FOODAWAY` formula cell is truncated at 255 characters in this workbook, so food away is mapped using all active 2020 `DIARY/EXPD` UCCs with the `190` prefix. The run independently compares this published EXPD 190-prefix sum to FMLD.FOODAWAY and records matches, differences, and aggregate sums below; this check is descriptive and does not assume the two source fields must agree. Other known UCCs go to `other_known_ucc`; UCCs not found in the active dictionary go to `unknown_ucc`.

{chr(10).join(map_lines)}

## Category summary-field cross-check

For each CU-week, published (`PUB_FLAG=2`) category sums are compared with the independent FMLD summary fields `FOODHOME`, `FOODAWAY`, and `HOUSKEEP`, plus `PERSPROD + PERSSERV` for personal care. The report separately shows excluded (`PUB_FLAG=1`) category amounts and whether the difference closes after adding those excluded rows. Category amount outputs remain published-only. These comparisons explain source-scope differences; they do not adjust the output amounts or turn Diary data into observed SCE purchases.

{chr(10).join(reconciliation_lines)}

## Input members

{chr(10).join(input_lines)}

## Week-specific weight audit

{chr(10).join(quarter_lines)}

## Output and audit

- `diary_weekly.jsonl`: one record per FMLD Diary week, joined to its EXPD detail costs and day-code support.
- `manifest.json`: source URLs, archive and dictionary hashes, member hashes, category map, field support, row counts, weights, and output hashes.
- `README.md`: this audit note.

Source files are append-only inputs. The output directory must be new; the script refuses to overwrite an existing run.
"""


def build(args: argparse.Namespace) -> dict:
    archive_path = Path(args.diary_zip).expanduser().resolve()
    dictionary_path = Path(args.dictionary).expanduser().resolve()
    if not archive_path.is_file():
        raise FileNotFoundError(f"Diary ZIP not found: {archive_path}")
    if not dictionary_path.is_file():
        raise FileNotFoundError(f"official BLS dictionary not found: {dictionary_path}")

    archive_sha = file_sha256(archive_path)
    dictionary_sha = file_sha256(dictionary_path)
    fmld_rows, expd_rows, source_members, zip_audit = read_official_diary_zip(archive_path)
    category_maps, known_ucc, mapping_audit = {}, {}, {}
    for quarter in (TARGET_QUARTER,):
        category_maps[quarter], known_ucc[quarter], mapping_audit[str(quarter)] = \
            category_map_from_dictionary(dictionary_path, year=TARGET_YEAR, quarter=quarter)
    weekly_rows, run_audit = prepare_diary_week_rows(
        fmld_rows, expd_rows, category_maps, known_ucc, source_members=source_members,
    )

    output_path = Path(args.output).expanduser() if args.output else None
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + f"_ce_diary2020q4_{archive_sha[:8]}"
    if output_path is None:
        output_path = ROOT / "data/interim/ce_experience" / run_id
    elif not output_path.is_absolute():
        output_path = ROOT / output_path
    output_path = output_path.resolve()
    created_at = datetime.now(timezone.utc).isoformat()
    retrieved_date = args.retrieved_date or date.today().isoformat()
    member_hashes = {k: v["sha256"] for k, v in sorted(source_members.items())}
    member_index = {k: v for k, v in source_members.items()}

    manifest = {
        "schema_version": "ce-diary-preparation-manifest-v1",
        "status": "prepared_offline_diary_proxy_not_personal_purchase_truth",
        "run_id": run_id,
        "created_at_utc": created_at,
        "retrieved_date": retrieved_date,
        "target_wave": "2020Q4 Diary PUMD only; every FMLD row is one CU-week",
        "source": {
            "survey": "BLS Consumer Expenditure Diary Survey",
            "url": args.source_url,
            "archive_path": str(archive_path),
            "archive_sha256": archive_sha,
            "archive_bytes": archive_path.stat().st_size,
            "version_note": "Current downloadable corrected 2020 public-use microdata; BLS 2022-03-10 Diary errata applied; not a historical 2021 vintage",
            "version_evidence_url": ERRATA_URL,
            "known_available_by": KNOWN_AVAILABLE_BY_DATE,
            "known_available_by_evidence_url": KNOWN_AVAILABLE_BY_URL,
            "known_available_by_evidence_scope": "BLS 2021-09-09 annual release states that 1980-2020 annual CE PUMD Interview and Diary files were available; establishes availability no later than that date, not the first release date or the exact local file vintage",
            "member_count": zip_audit["archive_member_count"],
            "members": member_index,
        },
        "dictionary": {
            "url": args.dictionary_url,
            "path": str(dictionary_path),
            "sha256": dictionary_sha,
            "release_note": "Current BLS dictionary; used only for 2020-effective variable and UCC definitions",
        },
        "method": {
            "household_week_join_key": "quarter + exact Diary NEWID between FMLD and EXPD",
            "diary_week": "NEWID final digit and FMLD.WEEKI, cross-checked as 1 or 2",
            "weight": "FMLD.FINLWT21 retained per NEWID/CU-week; do not collapse the two weeks or annualize weekly amounts",
            "amounts": "EXPD.COST USD including sales tax, by published PUB_FLAG=2 records; nonpublished and unknown flags separately reported",
            "day_count": "one overall distinct-day count across all expense categories: distinct EXPNSQDY values 1-7 with valid EXPN_QDY flags and positive-cost PUB_FLAG=2 rows when fields exist; not category-specific",
            "diary_interview_join": "prohibited; this script does not open Interview or SCE files",
            "no_llm_calls": True,
        },
        "category_mapping_by_quarter": mapping_audit,
        "processing_audit": run_audit,
        "field_support": {
            "amount_required_expd_fields": ["NEWID", "UCC", "COST", "PUB_FLAG"],
            "optional_day_fields": ["EXPNSQDY", "EXPN_QDY"],
            "demographic_fields_retained_when_present": list(PROFILE_FIELDS),
            "reported_fmld_summary_fields_retained_when_present": list(SUMMARY_FIELDS),
            "all_fmld_rows_joined_with_same_quarter_detail": True,
            "unmatched_expd_ids": 0,
        },
        "limitations": [
            "CU spending record, not SCE respondent spending or verified personal experience",
            "not a personal price index, CPI weight, shopping trip count, or annual purchase frequency",
            "Diary weekly observations come from an independent survey sample from Interview",
            "published zero records and unavailable source values remain distinct",
        ],
    }
    source_code = {
        "scripts/prepare_ce_diary.py": file_sha256(Path(__file__)),
        "studies/sce_inflation_expectations/diary_experience.py": file_sha256(
            ROOT / "studies/sce_inflation_expectations/diary_experience.py"
        ),
    }
    manifest["source_code_sha256"] = source_code

    # Construct all content before creating a fresh output directory so failures
    # during parsing or category validation leave no partial run behind.
    jsonl_bytes = b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
        for row in weekly_rows
    )
    readme_text = _readme(run_id, archive_sha, dictionary_sha, retrieved_date,
                          args.source_url, args.dictionary_url, mapping_audit,
                          source_members, run_audit)
    manifest["files"] = {
        "diary_weekly.jsonl": {"sha256": sha256_bytes(jsonl_bytes), "bytes": len(jsonl_bytes),
                               "records": len(weekly_rows)},
        "README.md": {"sha256": sha256_bytes(readme_text.encode("utf-8")),
                      "bytes": len(readme_text.encode("utf-8"))},
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    output_path.mkdir(parents=True, exist_ok=False)
    (output_path / "diary_weekly.jsonl").write_bytes(jsonl_bytes)
    (output_path / "README.md").write_text(readme_text, encoding="utf-8")
    (output_path / "manifest.json").write_bytes(manifest_bytes)
    return {"output": str(output_path), "run_id": run_id,
            "weekly_records": len(weekly_rows), "manifest_sha256": sha256_bytes(manifest_bytes),
            "quarter_audit": run_audit["quarter_audit"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diary-zip", default=str(DEFAULT_ZIP))
    parser.add_argument("--dictionary", default=str(DEFAULT_DICTIONARY))
    parser.add_argument("--output", help="new output directory; relative paths are resolved from the repo root")
    parser.add_argument("--run-id", help="optional run label; output directory must not already exist")
    parser.add_argument("--source-url", default=DIARY_ZIP_URL)
    parser.add_argument("--dictionary-url", default=DICTIONARY_URL)
    parser.add_argument("--retrieved-date", default="2026-10-06")
    args = parser.parse_args()
    result = build(args)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
