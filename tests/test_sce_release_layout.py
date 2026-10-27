from pathlib import Path
import ast
import unittest

from studies.sce_inflation_expectations.submission_tools.release_layout import destination, relocate


class ReleaseLayoutTests(unittest.TestCase):
    def setUp(self):
        self.prefix = "studies/sce_inflation_expectations"
        self.mapping = {self.prefix + "/belief_revision.py": self.prefix + "/components/behavior/belief_revision.py",
                        self.prefix + "/model.py": self.prefix + "/examples/core_demo/model.py",
                        self.prefix + "/evaluation/metrics.py": self.prefix + "/evaluation/metrics.py"}

    def test_unknown_flat_module_must_be_classified_not_dumped_in_root(self):
        with self.assertRaisesRegex(ValueError, "Unclassified"):
            destination(self.prefix + "/unknown.py")
        self.assertEqual(destination(self.prefix + "/core_normal_joint.py"),
                         self.prefix + "/components/behavior/core_normal_joint.py")

    def test_relative_sibling_import_and_root_resolution_follow_physical_move(self):
        code = "from . import model as base\nfrom .evaluation.metrics import headline_errors\nfrom pathlib import Path\nROOT=Path(__file__).resolve().parents[2]\nvalue=3*7\n"
        got = relocate(code, self.prefix + "/belief_revision.py", self.mapping[self.prefix + "/belief_revision.py"], self.mapping)
        self.assertIn("from studies.sce_inflation_expectations.examples.core_demo import model as base", got)
        self.assertIn("from studies.sce_inflation_expectations.evaluation.metrics import headline_errors", got)
        self.assertIn("parents[4]", got)
        self.assertIn("value=3*7", got)
        self.assertNotIn("core_demo.examples", got)

    def test_parent_relative_import_keeps_symbols_and_aliases(self):
        code = "from ..belief_revision import build_state as state, revise\n"
        got = relocate(code, self.prefix + "/experiments/a.py", self.prefix + "/experiments/a.py", self.mapping)
        self.assertIn("from studies.sce_inflation_expectations.components.behavior.belief_revision import build_state as state", got)
        self.assertIn("import revise", got)

    def test_literal_dynamic_module_and_source_path_are_relocated_once(self):
        code = 'path="studies/sce_inflation_expectations/belief_revision.py"\nm=__import__("studies.sce_inflation_expectations.belief_revision")\n'
        got = relocate(code, "tests/a.py", "tests/a.py", self.mapping)
        self.assertIn(self.mapping[self.prefix + "/belief_revision.py"], got)
        self.assertIn("components.behavior.belief_revision", got)
        ast.parse(got)

    def test_arithmetic_and_function_body_keep_identical_ast(self):
        code = 'from .model import Q9_KEYS\ndef weighted(v,w):\n    return sum(a*b for a,b in zip(v,w))/sum(w)\n'
        got = relocate(code,self.prefix+"/belief_revision.py",self.mapping[self.prefix+"/belief_revision.py"],self.mapping)
        old_fn=ast.parse(code).body[-1];new_fn=ast.parse(got).body[-1]
        self.assertEqual(ast.dump(old_fn),ast.dump(new_fn))


if __name__ == "__main__":
    unittest.main()
