import json
from pathlib import Path
import sys
import tempfile
import unittest

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_sce_experience_trial import ARMS, analyze_trial, main  # noqa: E402


class SCEExperienceTrialAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.trial_number = 0

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _bins_for(arm, uid):
        if arm == "basket_focus" and uid == 2:
            return [0, 0, 0, 10, 45, 45, 0, 0, 0, 0]
        return [0, 0, 0, 20, 50, 30, 0, 0, 0, 0]

    def _create_trial(
        self, *, invalid_cell=None, q9_invalid_cell=None, unfit_cell=None,
        altered_ids_cell=None, omit_truth_id=None,
    ):
        self.trial_number += 1
        trial_dir = self.base / f"trial-{self.trial_number}"
        trial_dir.mkdir()
        manifest_path = trial_dir / "trial_manifest.json"
        records = []
        truth_rows = []
        for month in (202105, 202106):
            for uid in (1, 2):
                truth_rows.append({
                    "date": month,
                    "userid": uid,
                    "Q8v2part2": float(uid),
                    **{f"Q9_bin{i + 1}": value for i, value in enumerate([0, 0, 0, 20, 50, 30, 0, 0, 0, 0])},
                })
        if omit_truth_id is not None:
            truth_rows = [r for r in truth_rows if (r["date"], r["userid"]) != omit_truth_id]
        truth_path = trial_dir / "truth.json"
        truth_path.write_text(json.dumps({"per_person": truth_rows}), encoding="utf-8")

        offsets = {
            "v2_baseline": 0.0,
            "expression_shared": 1.0,
            "basket_shared": 1.5,
            "focus_only": -0.5,
            "basket_focus": 2.0,
        }
        for month in (202105, 202106):
            for arm in ARMS:
                run_id = f"run-{month}-{arm}"
                run_dir = trial_dir / run_id
                run_dir.mkdir()
                (run_dir / "run_manifest.json").write_text(json.dumps({
                    "run_id": run_id,
                    "llm_kind": "openai",
                    "n_agents": 2,
                    "effective_artifact_sha256": {},
                    "source_snapshot_sha256": {},
                }), encoding="utf-8")
                answer_rows = []
                ids = [1, 2]
                if altered_ids_cell == (month, arm):
                    ids = [1, 3]
                for uid in ids:
                    is_invalid = invalid_cell == (month, arm, uid)
                    is_q9_invalid = q9_invalid_cell == (month, arm, uid)
                    is_unfit = unfit_cell == (month, arm, uid)
                    bins = ([0] * 10 if is_invalid or is_q9_invalid else
                            [20, 0, 0, 0, 0, 0, 0, 0, 0, 80] if is_unfit else
                            self._bins_for(arm, uid))
                    point = 0.0 if is_invalid else float(uid) + offsets[arm]
                    payload = {
                        "target_month": f"{month // 100}-{month % 100:02d}",
                        "point_pct": point,
                        "validation_status": ("error" if is_invalid else
                                              "invalid" if is_q9_invalid else "valid"),
                        **{f"q9_bin{i + 1}": value for i, value in enumerate(bins)},
                    }
                    if is_q9_invalid:
                        payload["llm"] = {"error": "q9_sum_0.0"}
                    answer_rows.append({
                        "agent_id": f"sce_u{uid}",
                        "step": 1,
                        "action_kind": "sce_answer",
                        "action_payload": payload,
                    })
                (run_dir / "panel_live.jsonl").write_text(
                    "".join(json.dumps(row) + "\n" for row in answer_rows), encoding="utf-8"
                )
                records.append({
                    "month": f"{month // 100}-{month % 100:02d}",
                    "arm": arm,
                    "run_id": run_id,
                    "output_dir": str(run_dir),
                    "status": "completed",
                    "cost": {"total_usd": 0.01},
                })
        manifest_path.write_text(json.dumps({"trial_id": "synthetic", "status": "completed", "records": records}), encoding="utf-8")
        return manifest_path, truth_path

    def test_analyzes_matched_cells_and_preserves_descriptive_provenance(self):
        manifest, truth = self._create_trial()
        result = analyze_trial(manifest, truth, project_root=ROOT, expected_n=2)

        self.assertEqual(result["schema_version"], "sce-experience-trial-analysis-v1")
        self.assertEqual(set(result["monthly_by_arm"]), {"202105", "202106"})
        self.assertEqual(set(result["monthly_by_arm"]["202105"]), set(ARMS))
        baseline = result["monthly_by_arm"]["202105"]["v2_baseline"]
        self.assertEqual(baseline["valid_answer_rate"], 1.0)
        self.assertEqual(baseline["q8"]["absolute_error_pp"]["mean"], 0.0)
        self.assertEqual(baseline["q8"]["rounding"]["distinct_numeric_values"], 2)
        self.assertEqual(baseline["q9"]["answer_shape"]["nonzero_bin_count"]["mean"], 3.0)
        self.assertEqual(baseline["q9"]["answer_shape"]["unique_templates"], 1)
        self.assertEqual(baseline["q9"]["answer_shape"]["reused_answer_share"], 1.0)
        self.assertEqual(len(baseline["per_person"]), 2)

        expression_contrast = next(
            c for c in result["paired_contrasts"]
            if c["month"] == 202105 and c["treatment_arm"] == "expression_shared"
            and c["reference_arm"] == "v2_baseline"
        )
        self.assertEqual(expression_contrast["q8"]["answer_delta_pp"]["mean"], 1.0)
        self.assertEqual(expression_contrast["q8"]["absolute_error_change_pp"]["mean"], 1.0)
        self.assertTrue(result["manifest"]["trial_manifest_sha256"])
        self.assertTrue(result["manifest"]["truth_sha256"])
        self.assertIn("frozen_dispatch", result["manifest"]["scorer"]["source_sha256"])
        self.assertIn("beta_fit_kernel", result["manifest"]["scorer"]["source_sha256"])
        self.assertTrue(any("limited power" in note for note in result["design_notes"]))
        self.assertTrue(any("does not select a winning arm" in note for note in result["design_notes"]))
        self.assertEqual(result["manifest"]["analysis_weighting"], "equal_person_unweighted")
        self.assertEqual(result["manifest"]["quantile_method"], "numpy.quantile(method='linear')")
        self.assertIn("ddof=1", result["manifest"]["standard_deviation_method"])

    def test_excludes_error_placeholders_and_keeps_question_masks_separate(self):
        manifest, truth = self._create_trial(invalid_cell=(202106, "focus_only", 1))
        result = analyze_trial(manifest, truth, project_root=ROOT, expected_n=2)
        cell = result["monthly_by_arm"]["202106"]["focus_only"]
        self.assertEqual(cell["valid_answer_count"], 1)
        self.assertEqual(cell["valid_answer_rate"], 0.5)
        self.assertEqual(cell["q8"]["legal_n"], 1)
        self.assertEqual(cell["q9"]["legal_n"], 1)
        self.assertIsNone(cell["per_person"][0]["q8_absolute_error_pp"])
        self.assertIsNone(cell["per_person"][0]["q9_absolute_error_pp"])

    def test_q8_mask_survives_a_q9_only_validation_failure(self):
        manifest, truth = self._create_trial(q9_invalid_cell=(202105, "focus_only", 1))
        result = analyze_trial(manifest, truth, project_root=ROOT, expected_n=2)
        cell = result["monthly_by_arm"]["202105"]["focus_only"]
        self.assertEqual(cell["q8"]["legal_n"], 2)
        self.assertEqual(cell["q9"]["legal_n"], 1)
        self.assertEqual(cell["valid_answer_count"], 1)
        person_one = next(r for r in cell["per_person"] if r["userid"] == 1)
        self.assertIsNotNone(person_one["q8_absolute_error_pp"])
        self.assertIsNone(person_one["q9_absolute_error_pp"])

    def test_legal_q9_with_unfittable_shape_is_counted_but_not_scored(self):
        manifest, truth = self._create_trial(unfit_cell=(202105, "basket_focus", 1))
        result = analyze_trial(manifest, truth, project_root=ROOT, expected_n=2)
        cell = result["monthly_by_arm"]["202105"]["basket_focus"]
        self.assertEqual(cell["q9"]["legal_n"], 2)
        self.assertEqual(cell["q9"]["scored_density_n"], 1)
        self.assertEqual(cell["q9"]["fit_status_counts"]["two_nonadjacent"], 1)

    def test_reads_finalized_duckdb_answer_payloads(self):
        manifest, truth = self._create_trial()
        trial = json.loads(manifest.read_text(encoding="utf-8"))
        record = next(
            r for r in trial["records"]
            if r["month"] == "2021-05" and r["arm"] == "v2_baseline"
        )
        run_dir = Path(record["output_dir"])
        source_rows = [
            json.loads(line)
            for line in (run_dir / "panel_live.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        (run_dir / "panel_live.jsonl").unlink()
        connection = duckdb.connect(str(run_dir / "study.duckdb"))
        connection.execute(
            "CREATE TABLE panel(agent_id VARCHAR, step INTEGER, action_kind VARCHAR, action_payload JSON)"
        )
        for row in source_rows:
            connection.execute(
                "INSERT INTO panel VALUES (?, ?, ?, ?::JSON)",
                [row["agent_id"], row["step"], row["action_kind"], json.dumps(row["action_payload"])],
            )
        connection.close()

        result = analyze_trial(manifest, truth, project_root=ROOT, expected_n=2)
        baseline = result["monthly_by_arm"]["202105"]["v2_baseline"]
        self.assertEqual(baseline["q8"]["legal_n"], 2)
        self.assertEqual(baseline["run"]["answer_source"]["kind"], "duckdb")

    def test_rejects_id_mismatch_and_does_not_use_truth_to_drop_people(self):
        manifest, truth = self._create_trial(altered_ids_cell=(202105, "basket_shared"))
        with self.assertRaisesRegex(ValueError, "share the same IDs"):
            analyze_trial(manifest, truth, project_root=ROOT, expected_n=2)

        manifest, truth = self._create_trial(omit_truth_id=(202105, 1))
        with self.assertRaisesRegex(ValueError, "will not substitute or select respondents"):
            analyze_trial(manifest, truth, project_root=ROOT, expected_n=2)

    def test_requires_trial_and_every_run_to_be_completed(self):
        manifest, truth = self._create_trial()
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["status"] = "running"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "requires completed"):
            analyze_trial(manifest, truth, project_root=ROOT, expected_n=2)

        manifest, truth = self._create_trial()
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["records"][0]["status"] = "pending"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "analysis requires completed records"):
            analyze_trial(manifest, truth, project_root=ROOT, expected_n=2)

    def test_rejects_scripted_or_wrong_size_run(self):
        manifest, truth = self._create_trial()
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        run_manifest = Path(payload["records"][0]["output_dir"]) / "run_manifest.json"
        run = json.loads(run_manifest.read_text(encoding="utf-8"))
        run["llm_kind"] = "scripted"
        run_manifest.write_text(json.dumps(run), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "expected a real openai run"):
            analyze_trial(manifest, truth, project_root=ROOT, expected_n=2)

        manifest, truth = self._create_trial()
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        run_manifest = Path(payload["records"][0]["output_dir"]) / "run_manifest.json"
        run = json.loads(run_manifest.read_text(encoding="utf-8"))
        run["n_agents"] = 3
        run_manifest.write_text(json.dumps(run), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "n_agents=3"):
            analyze_trial(manifest, truth, project_root=ROOT, expected_n=2)

    def test_cli_refuses_to_overwrite_existing_report(self):
        manifest, truth = self._create_trial()
        output = self.base / "summary.json"
        output.write_text("keep prior report\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as raised:
            main([
                "--trial-manifest", str(manifest),
                "--truth", str(truth),
                "--out", str(output),
                "--expected-n", "2",
            ])
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(output.read_text(encoding="utf-8"), "keep prior report\n")


if __name__ == "__main__":
    unittest.main()
