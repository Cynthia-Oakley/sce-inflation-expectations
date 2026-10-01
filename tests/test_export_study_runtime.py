"""Round-trip tests for scripts/export_study_runtime.py."""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_study_runtime.py"
spec = importlib.util.spec_from_file_location("export_study_runtime", SCRIPT)
export_study_runtime = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = export_study_runtime
spec.loader.exec_module(export_study_runtime)


class ExportStudyRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target_root = Path(self.tmp.name) / "studies"

    def export(self):
        return export_study_runtime.export(self.target_root)

    def test_export_then_verify_ok(self):
        target = self.export()
        self.assertTrue((target / "study.yaml").is_file())
        self.assertTrue((target / "scoring" / "sce_q9.py").is_file())
        manifest = json.loads((target / "RUNTIME_EXPORT.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["exporter"], export_study_runtime.EXPORTER_TAG)
        self.assertEqual(manifest["study_id"], "sce_inflation_expectations")
        self.assertEqual(manifest["file_count"], len(manifest["files"]))
        self.assertEqual(export_study_runtime.verify(self.target_root), 0)

    def test_export_excludes_derived_content(self):
        target = self.export()
        names = {str(p.relative_to(target)) for p in target.rglob("*") if p.is_file()}
        self.assertFalse(any("__pycache__" in n or n.endswith(".pyc") for n in names))
        self.assertFalse(any(n.endswith(".DS_Store") for n in names))
        # placeholder READMEs survive; derived payload files would not
        self.assertIn("trajectory/README.md", names)

    def test_generated_init_present(self):
        target = self.export()
        self.assertTrue((target / "__init__.py").is_file())

    def test_verify_detects_tampering(self):
        target = self.export()
        scored = target / "scoring" / "sce_q9.py"
        scored.write_text(scored.read_text(encoding="utf-8") + "\n# tampered\n",
                          encoding="utf-8")
        self.assertEqual(export_study_runtime.verify(self.target_root), 1)

    def test_verify_detects_extra_file(self):
        target = self.export()
        (target / "local_edit.py").write_text("# edited in runtime copy\n",
                                              encoding="utf-8")
        self.assertEqual(export_study_runtime.verify(self.target_root), 1)

    def test_refuses_to_overwrite_foreign_directory(self):
        foreign = self.target_root / "sce_inflation_expectations"
        foreign.mkdir(parents=True)
        (foreign / "study.yaml").write_text("study_id: sce_inflation_expectations\n",
                                            encoding="utf-8")
        with self.assertRaises(SystemExit) as ctx:
            export_study_runtime.export(self.target_root)
        self.assertNotEqual(ctx.exception.code, 0)
        self.assertTrue((foreign / "study.yaml").is_file())

    def test_reexport_over_own_copy_ok(self):
        self.export()
        self.export()
        self.assertEqual(export_study_runtime.verify(self.target_root), 0)


if __name__ == "__main__":
    unittest.main()
