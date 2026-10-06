"""Independent checks for Diary week joins, categories, weights, and support states."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "studies/sce_inflation_expectations/diary_experience.py"
MODULE_SPEC = importlib.util.spec_from_file_location("_ce_diary_experience_test", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise ImportError(f"cannot load Diary processing module: {MODULE_PATH}")
diary_module = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = diary_module
MODULE_SPEC.loader.exec_module(diary_module)
_formula_uccs = diary_module._formula_uccs
prepare_diary_week_rows = diary_module.prepare_diary_week_rows
read_official_diary_zip = diary_module.read_official_diary_zip


def fmld(newid, week, weight, **extra):
    return {
        "NEWID": newid,
        "WEEKI": str(week),
        "WEEKN": "2",
        "FINLWT21": str(weight),
        "AGE_REF": "42",
        "EDUC_REF": "15",
        "CUTENURE": "4",
        "REGION": "2",
        "FOODHOME": "30.00",
        **extra,
    }


def expd(newid, ucc, cost, day, *, flag="2", alloc="0"):
    return {
        "NEWID": newid,
        "UCC": ucc,
        "COST": str(cost),
        "PUB_FLAG": flag,
        "ALLOC": alloc,
        "EXPNSQDY": day,
        "EXPN_QDY": "D" if day else "B",
    }


class DiaryExperienceTest(unittest.TestCase):
    def setUp(self):
        self.week1_id = "04632011"
        self.week2_id = "04632012"
        self.category_map = {
            "010110": "food_at_home",
            "190111": "food_away_from_home",
            "330110": "household_supplies_services",
            "640110": "personal_care_products_services",
        }
        self.known_ucc = set(self.category_map) | {"999990"}
        self.headers = {
            "fmld_q1": {"member": "diary20/fmld201.csv", "headers": [
                "NEWID", "WEEKI", "WEEKN", "FINLWT21", "AGE_REF", "EDUC_REF", "CUTENURE", "REGION", "FOODHOME", "FOODAWAY",
            ]},
            "expd_q1": {"member": "diary20/expd201.csv", "headers": [
            "NEWID", "UCC", "COST", "PUB_FLAG", "ALLOC", "EXPNSQDY",
            "EXPN_QDY",
            ]},
        }

    def test_formula_resolver_uses_nested_summary_definitions(self):
        formulas = {"FOODHOME": "SUM (CEREAL, 010110)", "CEREAL": "SUM (020110, 020210)"}
        self.assertEqual(_formula_uccs("FOODHOME", formulas), {"010110", "020110", "020210"})
        self.assertEqual(_formula_uccs("BROKEN_CLOSE", {"BROKEN_CLOSE": "SUM (140110,140210"}),
                         {"140110", "140210"})
        with self.assertRaisesRegex(ValueError, "incomplete or unsupported"):
            _formula_uccs("BROKEN_LIST", {"BROKEN_LIST": "SUM (140110,"})

    def test_weekly_join_uses_unique_days_and_week_specific_weights(self):
        fmld_rows = {1: [fmld(self.week1_id, 1, 10), fmld(self.week2_id, 2, 25)]}
        expd_rows = {1: [
            expd(self.week1_id, "190111", "2.00", "1"),
            expd(self.week1_id, "190111", "3.00", "1"),
            expd(self.week1_id, "010110", "4.50", "2"),
            expd(self.week2_id, "999999", "7.25", ""),
        ]}
        rows, audit = prepare_diary_week_rows(fmld_rows, expd_rows, self.category_map,
                                               self.known_ucc, source_members=self.headers)
        by_week = {row["diary_week_number"]: row for row in rows}
        w1, w2 = by_week[1], by_week[2]

        self.assertEqual(w1["amounts"]["category_amounts_usd"]["food_away_from_home"], "5")
        self.assertEqual(w1["amounts"]["category_amounts_usd"]["food_at_home"], "4.5")
        self.assertEqual(w1["purchase_day_support"]["distinct_days_with_positive_published_cost_records"], 2)
        self.assertEqual(w1["purchase_day_support"]["status"], "available")
        self.assertIn("across all expense categories", w1["purchase_day_support"]["interpretation"])
        self.assertEqual(w1["amounts"]["detail_record_counts"]["all_expd_rows"], 3)
        self.assertEqual(w1["sampling_weight_FINLWT21"], "10")
        self.assertEqual(w2["sampling_weight_FINLWT21"], "25")
        self.assertEqual(w1["diary_cu_pair_key_sha256"], w2["diary_cu_pair_key_sha256"])
        self.assertNotEqual(w1["diary_week_key_sha256"], w2["diary_week_key_sha256"])
        self.assertEqual(w2["amounts"]["category_amounts_usd"]["unknown_ucc"], "7.25")
        self.assertEqual(w2["purchase_day_support"]["distinct_days_with_positive_published_cost_records"], None)
        self.assertEqual(w2["purchase_day_support"]["status"], "partial_day_support")
        self.assertNotIn(self.week1_id, json.dumps(rows, ensure_ascii=False))
        self.assertEqual(audit["quarter_audit"]["1"]["weight_by_diary_week"]["1"]["sum_FINLWT21"], "10")
        self.assertEqual(audit["quarter_audit"]["1"]["weight_by_diary_week"]["2"]["sum_FINLWT21"], "25")

    def test_zero_records_and_missing_day_schema_are_distinct(self):
        fmld_rows = {1: [fmld(self.week1_id, 1, 10)]}
        zero_rows, _ = prepare_diary_week_rows(fmld_rows, {1: []}, self.category_map,
                                                self.known_ucc, source_members=self.headers)
        self.assertEqual(zero_rows[0]["amounts"]["support_status"], "zero_expd_rows")
        self.assertEqual(zero_rows[0]["purchase_day_support"]["status"], "zero_expd_rows")
        self.assertEqual(zero_rows[0]["purchase_day_support"]["distinct_days_with_positive_published_cost_records"], 0)

        without_day = {**self.headers, "expd_q1": {"member": "diary20/expd201.csv", "headers": [
            "NEWID", "UCC", "COST", "PUB_FLAG", "ALLOC",
        ]}}
        unmeasurable_rows, _ = prepare_diary_week_rows(fmld_rows, {1: []}, self.category_map,
                                                        self.known_ucc, source_members=without_day)
        self.assertEqual(unmeasurable_rows[0]["purchase_day_support"]["status"], "unavailable_schema")
        self.assertIsNone(unmeasurable_rows[0]["purchase_day_support"]["distinct_days_with_positive_published_cost_records"])

    def test_nonpublished_records_are_separate_and_not_purchase_days(self):
        rows, _ = prepare_diary_week_rows(
            {1: [fmld(self.week1_id, 1, 10, FOODAWAY="8.00")]},
            {1: [expd(self.week1_id, "190111", "8.00", "1", flag="1")]},
            self.category_map, self.known_ucc, source_members=self.headers,
        )
        self.assertEqual(rows[0]["amounts"]["published_cost_sum_usd"], "0")
        self.assertEqual(rows[0]["amounts"]["not_published_cost_sum_usd"], "8")
        food_away_check = rows[0]["category_summary_crosschecks"]["food_away_from_home"]
        self.assertEqual(food_away_check["published_minus_fmld_summary_usd"], "-8")
        self.assertEqual(food_away_check["published_plus_pub_flag_1_minus_fmld_summary_usd"], "0")
        self.assertEqual(rows[0]["purchase_day_support"]["status"], "zero_positive_pub_flag_2_cost_records")
        self.assertEqual(rows[0]["purchase_day_support"]["distinct_days_with_positive_published_cost_records"], 0)

    def test_personal_care_published_only_gap_is_explicitly_excluded_flag1(self):
        rows, audit = prepare_diary_week_rows(
            {1: [fmld(self.week1_id, 1, 10, PERSPROD="12.00", PERSSERV="0.00")]},
            {1: [expd(self.week1_id, "640110", "12.00", "1", flag="1")]},
            self.category_map, self.known_ucc, source_members=self.headers,
        )
        check = rows[0]["category_summary_crosschecks"]["personal_care_products_services"]
        self.assertEqual(check["published_expd_pub_flag_2_sum_usd"], "0")
        self.assertEqual(check["fmld_summary_sum_usd"], "12")
        self.assertEqual(check["excluded_expd_pub_flag_1_sum_usd"], "12")
        self.assertEqual(check["published_minus_fmld_summary_usd"], "-12")
        self.assertEqual(check["published_plus_pub_flag_1_minus_fmld_summary_usd"], "0")
        self.assertEqual(
            audit["quarter_audit"]["1"]["category_summary_reconciliation"]
            ["personal_care_products_services"]["exact_match_after_adding_pub_flag_1_household_week_count"],
            1,
        )

    def test_unmatched_detail_or_duplicate_week_key_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "lack same-quarter FMLD"):
            prepare_diary_week_rows(
                {1: [fmld(self.week1_id, 1, 10)]},
                {1: [expd("04632021", "190111", "2", "1")]},
                self.category_map, self.known_ucc, source_members=self.headers,
            )
        with self.assertRaisesRegex(ValueError, "duplicate FMLD NEWID"):
            prepare_diary_week_rows(
                {1: [fmld(self.week1_id, 1, 10), fmld(self.week1_id, 1, 10)]},
                {1: []}, self.category_map, self.known_ucc, source_members=self.headers,
            )

    def test_official_archive_reader_selects_only_2020_q4(self):
        with tempfile.TemporaryDirectory() as temp:
            archive_path = Path(temp) / "diary20.zip"
            fmld_csv = "NEWID,WEEKI,WEEKN,FINLWT21\n04632011,1,2,10\n"
            expd_csv = "NEWID,UCC,COST,PUB_FLAG,ALLOC,EXPNSQDY\n04632011,190111,2,2,0,1\n"
            with zipfile.ZipFile(archive_path, "w") as archive:
                for quarter in range(1, 5):
                    archive.writestr(f"diary20/fmld20{quarter}.csv", fmld_csv)
                    archive.writestr(f"diary20/expd20{quarter}.csv", expd_csv)
            fmld_rows, expd_rows, members, archive_audit = read_official_diary_zip(archive_path)
            self.assertEqual(set(fmld_rows), {4})
            self.assertEqual(set(expd_rows), {4})
            self.assertEqual(members["fmld_q4"]["row_count"], 1)
            self.assertEqual(len(members["expd_q4"]["sha256"]), 64)
            self.assertEqual(archive_audit["processed_quarter"], 4)
            self.assertEqual(archive_audit["archive_member_count"], 8)


if __name__ == "__main__":
    unittest.main()
