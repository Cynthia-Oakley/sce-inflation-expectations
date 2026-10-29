import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import pytest

from studies.sce_inflation_expectations.submission_tools import reviewer_pipeline as p


def test_launcher_child_uses_only_the_installed_workspace_source(tmp_path, capfd):
    root = tmp_path / "review"
    module = root / "studies/sce_inflation_expectations/submission_tools/fixture_only.py"
    module.parent.mkdir(parents=True)
    for parent in (module.parent, module.parent.parent, root / "studies"):
        (parent / "__init__.py").write_text("")
    module.write_text("from pathlib import Path\nimport sys\nassert sys.argv[1:]==['check']\nprint(Path(__file__).resolve())\n")
    (root / "portable_installation.json").write_text("{}")
    assert p.child(root, "fixture_only", ["check"]) == 0
    assert str(module.resolve()) in capfd.readouterr().out


def test_archive_path_escape_is_rejected(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../outside.txt", "x")
    with pytest.raises(ValueError, match="Unsafe"):
        p.extract(archive, tmp_path / "root")
    assert not (tmp_path / "outside.txt").exists()


def test_single_workflow_chains_generation_and_independent_evaluation(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-test-key-not-for-network")
    workspace = tmp_path / "ws"; workspace.mkdir()
    calls = []
    def child(root, module, args):
        calls.append(module)
        args = list(args); out = Path(args[args.index("--out") + 1]); out.mkdir(parents=True)
        if module == "portable_run":
            (out / "answers.jsonl").write_text('{"fixture":true}\n')
        elif module == "portable_evaluate":
            answers = Path(args[args.index("--answers") + 1])
            (out / "manifest.json").write_text(json.dumps(dict(input_sha256={"answers.jsonl": p.sha(answers)})))
        return 0
    monkeypatch.setattr(p, "child", child)
    args = argparse.Namespace(confirm_paid=True, budget_usd=.2, out=tmp_path / "run",
        resume=False, use_prepared_inputs=True, scope="smoke", tasks=["A", "B", "monthly", "weekly"],
        workers=2, people=None, periods=None)
    assert p.workflow(args, workspace) == 0
    assert calls == ["portable_run", "portable_evaluate"]
    receipt = json.loads((args.out / "workflow.json").read_text())
    assert receipt["status"] == "fresh_workflow_complete" and not receipt["credentials_saved"]


def test_active_rebuilt_runtime_must_match_registered_hash(tmp_path):
    workspace = tmp_path / "ws"; index = workspace / "outputs/prepared/index.json"
    index.parent.mkdir(parents=True); index.write_text("{}")
    marker = workspace / "portable/active_runtime.json"; marker.parent.mkdir()
    marker.write_text(json.dumps(dict(runtime="outputs/prepared", index_sha256=p.sha(index))))
    assert p.active_runtime(workspace) == index.parent
    index.write_text('{"changed":true}')
    with pytest.raises(ValueError, match="changed"):
        p.active_runtime(workspace)
