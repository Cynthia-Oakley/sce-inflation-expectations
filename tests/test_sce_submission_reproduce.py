from contextlib import contextmanager
import csv
import json
import math
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from studies.sce_inflation_expectations.submission_tools.reproduce import (
    checked_child, dry_run, generate, load_monthly, no_network, replay, sha, verify_package, write,
)
from studies.sce_inflation_expectations.submission_tools.package_builder import _monthly_export


class SubmissionReproduceTests(unittest.TestCase):
    def test_network_guard_blocks_and_restores_connection_functions(self):
        original = socket.create_connection
        with no_network():
            with self.assertRaisesRegex(RuntimeError, "Network is disabled"):
                socket.create_connection(("example.invalid", 443))
        self.assertIs(socket.create_connection, original)

    def test_paid_mode_needs_all_explicit_arguments_before_any_subprocess(self):
        with patch("subprocess.run") as run:
            with self.assertRaises(ValueError):
                generate(None, None, confirm=False)
            run.assert_not_called()

    def test_manifest_rejects_path_escape_and_changed_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(ValueError):
                checked_child(root, "../outside")
            (root / "a.txt").write_text("original")
            write(root / "PACKAGE_MANIFEST.json", {"status": "test", "files_sha256": {"a.txt": sha(root / "a.txt")}})
            self.assertEqual(verify_package(root)["files_verified"], 1)
            (root / "a.txt").write_text("changed")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify_package(root)

    def test_monthly_export_physically_drops_personal_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp) / "private.csv"; dest = Path(temp) / "safe.csv"
            src.write_text("month,sim_pp,anchor_pp,truth_pp,userid,prompt,weight\n202501,2,3,4,private_id,private_text,7\n")
            _monthly_export(src, dest)
            self.assertNotIn("private_", dest.read_text())
            self.assertNotIn("userid", dest.read_text())
            self.assertNotIn("weight", dest.read_text())

    def test_duplicate_or_nonfinite_monthly_values_are_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "months.csv"
            for data in ("202501,2,3,4\n202501,2,3,4\n", "202501,nan,3,4\n"):
                path.write_text("month,sim_pp,anchor_pp,truth_pp\n" + data)
                with self.assertRaises(ValueError):
                    load_monthly(path)

    def test_real_aggregate_recompute_has_hand_calculated_expected_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            study = Path(temp) / "study"; evidence = study / "reproduction_data"; evidence.mkdir(parents=True)
            file = evidence / "two.csv"
            file.write_text("month,sim_pp,anchor_pp,truth_pp\n202501,0,0,1\n202502,6,4,4\n")
            expected = {"model": {"mae_pp": 1.5, "rmse_pp": math.sqrt(2.5), "bias_pp": .5},
                        "persistence": {"mae_pp": .5, "rmse_pp": math.sqrt(.5), "bias_pp": -.5}}
            write(evidence / "aggregate_cases.json", {"cases": [{"case_id": "known", "scope": "test",
                  "monthly_file": "two.csv", "monthly_sha256": sha(file), "n_months": 2,
                  "first_month": 202501, "last_month": 202502, "expected": expected,
                  "expected_yearly": {"2025": expected}}]})
            with no_network():
                result = replay(Path(temp) / "replay", study=study)
            self.assertEqual(result["cases"][0]["model"]["mae_pp"], 1.5)
            self.assertFalse(result["micro_trajectories_recomputed"])
            self.assertEqual(result["actual_LLM_calls"], 0)
            self.assertEqual(result["cases"][0]["yearly"]["2025"]["model"]["mae_pp"], 1.5)
            changed = json.loads((evidence / "aggregate_cases.json").read_text())
            changed["cases"][0]["expected"]["model"]["mae_pp"] = 1.4
            write(evidence / "aggregate_cases.json", changed)
            with self.assertRaisesRegex(ValueError, "result mismatch"):
                replay(Path(temp) / "bad_replay", study=study)
            changed["cases"][0]["expected"]["model"]["mae_pp"] = 1.5
            changed["cases"][0]["expected_yearly"]["2025"]["model"]["mae_pp"] = 1.4
            write(evidence / "aggregate_cases.json", changed)
            with self.assertRaisesRegex(ValueError, "yearly aggregate error changed"):
                replay(Path(temp) / "bad_yearly", study=study)

    def test_official_core_runs_20_synthetic_people_two_steps_without_a_key(self):
        from studies.sce_inflation_expectations.submission_tools.package_builder import _demo_artifacts
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "package"; package.mkdir()
            _demo_artifacts(package)
            study = package / "studies/sce_inflation_expectations"
            with no_network(), patch.dict("os.environ", {}, clear=True):
                receipt = dry_run(Path(temp) / "dry", study=study)
            self.assertEqual(receipt["panel_rows"], 60)
            self.assertEqual(receipt["scripted_decisions"], 40)
            self.assertEqual(receipt["actual_LLM_calls"], 0)
            self.assertFalse(receipt["empirical_accuracy_result"])


if __name__ == "__main__":
    unittest.main()
