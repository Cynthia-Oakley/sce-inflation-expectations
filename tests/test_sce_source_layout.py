from pathlib import Path
import tempfile
import unittest
import zipfile

from studies.sce_inflation_expectations.submission_tools.source_layout import (
    dependency_closure, export_supplement, sha,
)


class SourceLayoutTests(unittest.TestCase):
    def test_dependency_closure_keeps_relative_imports_and_eager_compatibility(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "studies/sce_inflation_expectations"
            folder.mkdir(parents=True)
            data = {"__init__.py": "from . import legacy\n", "entry.py": "from .helper import value\n",
                    "helper.py": "value=3\n", "legacy.py": "value=2\n", "other.py": "raise RuntimeError('not a dependency')\n"}
            for name, code in data.items():
                (folder / name).write_text(code)
            files = sorted(folder.glob("*.py"))
            selected, _ = dependency_closure(root, ["studies/sce_inflation_expectations/entry.py"], files=files)
            self.assertEqual({p.name for p in selected}, {"__init__.py", "entry.py", "helper.py", "legacy.py"})

    def test_archive_preserves_source_bytes_and_original_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); src = root / "scripts/old.py"; src.parent.mkdir()
            original = b"# preserved historical experiment\nvalue=7\n"; src.write_bytes(original)
            package = root / "package"; package.mkdir()
            info = export_supplement(package, root, {"supplement": [src]}, source_bytes=lambda p: p.read_bytes())
            with zipfile.ZipFile(package / info["archive"]) as z:
                self.assertEqual(z.namelist(), ["scripts/old.py"])
                self.assertEqual(z.read("scripts/old.py"), original)
            self.assertEqual(src.read_bytes(), original)
            self.assertEqual(info["archive_sha256"], sha(package / info["archive"]))

    def test_missing_primary_entry_is_not_silently_pruned(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "missing"):
                dependency_closure(Path(temp), ["missing.py"], files=[])


if __name__ == "__main__":
    unittest.main()
