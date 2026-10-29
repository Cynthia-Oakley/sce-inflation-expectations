"""Standalone reviewer entry: install, rebuild inputs, run own-key batches, score.

Installed under study/simulation/. Standard-library bootstrap deliberately runs
the original source in a fresh child process, apart from the organised replay
package's module namespace. No author workspace or author Key is consulted.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile


BOOTSTRAP = """import sys,runpy
from pathlib import Path
root=Path(sys.argv.pop(1)).resolve()
sys.path.insert(0,str(root))
import studies
studies.__path__=[str(root/'studies'),*studies.__path__]
module=sys.argv.pop(1)
sys.argv[0]=module
runpy.run_module(module,run_name='__main__')
"""
PREFIX = "studies.sce_inflation_expectations.submission_tools."


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(2**20), b""):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def package_paths():
    study = Path(__file__).resolve().parents[1]
    package = study.parents[1]
    if not (package / "PACKAGE_MANIFEST.json").is_file():
        raise ValueError("Use the entry from the extracted research package's study/simulation directory")
    return package, study / "reproduction_data/portable"


def extract(archive, out):
    with zipfile.ZipFile(archive) as z:
        seen = set()
        for info in z.infolist():
            relative = Path(info.filename)
            if relative.is_absolute() or ".." in relative.parts or "\\" in info.filename:
                raise ValueError("Unsafe archive path")
            if info.filename in seen or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Duplicate archive entry or symlink")
            seen.add(info.filename)
            target = out / relative
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                if target.exists():
                    if sha(target) == hashlib.sha256(z.read(info)).hexdigest():
                        continue
                    raise ValueError("Conflicting portable source path: " + info.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as source, target.open("xb") as dest:
                    shutil.copyfileobj(source, dest)


def install(package, data, workspace):
    workspace = Path(workspace).resolve()
    if workspace.exists():
        raise FileExistsError("Use a new --workspace for an independent installation")
    manifest = read(data / "manifest.json")
    for rel, digest in manifest["files_sha256"].items():
        p = (data / rel).resolve()
        if not p.is_relative_to(data.resolve()) or p.is_symlink() or sha(p) != digest:
            raise ValueError("Portable source collection changed: " + rel)
    workspace.mkdir(parents=True)
    source = package / "archive/research_source_supplement.zip"
    expected = read(package / "PACKAGE_MANIFEST.json")["files_sha256"][str(source.relative_to(package))]
    if sha(source) != expected:
        raise ValueError("Original source archive changed")
    extract(source, workspace)
    extract(data / "public_sources.zip", workspace)
    for name in ("runtime", "evidence", "downstream", "calibration"):
        shutil.copytree(data / name, workspace / "portable" / name)
    (workspace / "portable_installation.json").write_text(json.dumps(dict(
        schema="sce_portable_install/v1", package_manifest_sha256=sha(package / "PACKAGE_MANIFEST.json"),
        portable_manifest_sha256=sha(data / "manifest.json"), original_source_sha256=sha(source),
        original_source_workspace=str(workspace), credentials_read=False, new_API_calls=0), indent=2) + "\n")
    return dict(status="portable_workspace_installed", workspace=str(workspace), new_API_calls=0)


def child(workspace, module, args):
    if not (workspace / "portable_installation.json").is_file():
        raise ValueError("Run install once before using this workspace")
    command = [sys.executable, "-I", "-c", BOOTSTRAP, str(workspace), PREFIX + module, *map(str, args)]
    env = os.environ.copy()
    if module != "portable_run":
        # Offline preparation/evaluation/refits do not need account secrets.
        # In particular a workflow's own Key is not inherited by Core checks.
        for name in list(env):
            if name.upper().endswith(("_API_KEY", "_ACCESS_TOKEN", "_AUTH_TOKEN")):
                env.pop(name)
    return subprocess.run(command, cwd=workspace, env=env, check=False).returncode


def active_runtime(workspace):
    marker = workspace / "portable/active_runtime.json"
    if not marker.exists():
        return workspace / "portable/runtime"
    m = read(marker)
    runtime = (workspace / m["runtime"]).resolve()
    if not runtime.is_relative_to(workspace) or sha(runtime / "index.json") != m["index_sha256"]:
        raise ValueError("Active rebuilt runtime changed or escaped workspace")
    return runtime


def workflow(args, workspace):
    """One foreground program; no coding agent is needed between phases."""
    if not args.confirm_paid or args.budget_usd is None or args.out is None:
        raise ValueError("workflow requires --confirm-paid, --budget-usd and a new --out")
    if not math.isfinite(args.budget_usd) or args.budget_usd <= 0 or not 1 <= args.workers <= 64:
        raise ValueError("Positive finite budget and 1–64 workers required")
    if len(set(args.tasks)) != len(args.tasks):
        raise ValueError("Select each task only once")
    args.tasks = [task for task in ("A", "B", "monthly", "weekly") if task in args.tasks]
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise ValueError("Set your own OPENROUTER_API_KEY before starting this paid workflow")
    out = args.out.resolve()
    if out.exists() and not args.resume:
        raise FileExistsError("Use a new workflow --out or explicitly --resume")
    out.mkdir(parents=True, exist_ok=True)
    completed = []
    def receipt(status, **extra):
        value = dict(status=status, phases=completed, credentials_saved=False, **extra)
        (out / "workflow.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    def phase(module, options, name):
        status = child(workspace, module, options)
        if status:
            receipt("stopped_data_preserved", stopped_phase=name, exit_code=status)
            return False
        completed.append(name); receipt("running")
        return True
    marker = workspace / "portable/active_runtime.json"
    if not marker.exists() and not args.use_prepared_inputs:
        prepared = workspace / "outputs/reviewer_preparation"
        if not (prepared / "preparation_index.json").exists():
            if prepared.exists():
                prepared = prepared.with_name(prepared.name + "_" + str(time.time_ns()))
            if not phase("portable_prepare", ["--workspace", workspace, "--out", prepared], "public_sources_to_prepared_inputs"):
                return 1
        if not phase("portable_adopt", ["--workspace", workspace, "--preparation", prepared], "adopt_verified_rebuilt_inputs"):
            return 1
    runtime = active_runtime(workspace)
    options = ["run", "--data", runtime, "--out", out / "generation", "--scope", args.scope,
               "--tasks", *args.tasks, "--budget-usd", args.budget_usd, "--workers", args.workers, "--confirm-paid"]
    for name in ("people", "periods"):
        if getattr(args, name) is not None: options += ["--" + name, getattr(args, name)]
    if args.resume and (out / "generation").exists(): options.append("--resume")
    if not phase("portable_run", options, "fresh_model_generation_and_state_recursion"):
        return 1
    evaluation = out / "evaluation"
    if evaluation.exists() and not (evaluation / "manifest.json").exists():
        interrupted = out / "_interrupted"; interrupted.mkdir(exist_ok=True)
        evaluation.rename(interrupted / ("evaluation_" + str(time.time_ns())))
    if not evaluation.exists():
        if not phase("portable_evaluate", ["--answers", out / "generation/answers.jsonl",
            "--data", runtime / "evaluation", "--out", evaluation], "independent_evaluation_and_Normal"):
            return 1
    else:
        evidence = read(evaluation / "manifest.json")
        if evidence["input_sha256"]["answers.jsonl"] != sha(out / "generation/answers.jsonl"):
            raise ValueError("Existing evaluation belongs to different generated answers")
        completed.append("existing_evaluation_verified")
    if args.scope == "full" and "A" in args.tasks:
        for name, receipt_name in (("calibration", "portable_calibration_receipt.json"),
                                   ("downstream", "portable_verification.json")):
            path = out / name
            if path.exists() and not (path / receipt_name).exists():
                interrupted = out / "_interrupted"; interrupted.mkdir(exist_ok=True)
                path.rename(interrupted / (name + "_" + str(time.time_ns())))
        if not (out / "calibration").exists():
            if not phase("portable_calibration", ["replay", "--data", workspace / "portable/calibration",
                "--out", out / "calibration", "--fresh-evaluation", evaluation], "original_training_and_macro_refit"):
                return 1
        if "B" in args.tasks and not (out / "downstream").exists():
            if not phase("portable_downstream", ["replay", "--data", workspace / "portable/downstream",
                "--out", out / "downstream", "--a", out / "calibration/monthly_predictions_public.csv",
                "--b", evaluation / "monthly_national.csv", "--no-verify"], "original_downstream_refit_on_fresh_indicators"):
                return 1
    receipt("fresh_workflow_complete", scope=args.scope,
        note="Smoke has insufficient history for new calibration/downstream fits; those phases require complete A/B series")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("install", "prepare", "audit-inputs", "plan", "run", "workflow", "evaluate", "calibrate", "downstream", "check"))
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--out", type=Path)
    p.add_argument("--answers", type=Path)
    p.add_argument("--tasks", nargs="+", choices=("A", "B", "monthly", "weekly"), default=["A", "B", "monthly", "weekly"])
    p.add_argument("--scope", choices=("smoke", "full"), default="smoke")
    p.add_argument("--people", type=int)
    p.add_argument("--periods", type=int)
    p.add_argument("--budget-usd", type=float)
    p.add_argument("--workers", type=int, default=32)
    p.add_argument("--confirm-paid", action="store_true")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--a", type=Path)
    p.add_argument("--b", type=Path)
    p.add_argument("--fresh-evaluation", type=Path)
    p.add_argument("--use-prepared-inputs", action="store_true",
                   help="Use supplied exact prepared P/E cache; otherwise workflow rebuilds public source stages first")
    args = p.parse_args(argv)
    package, data = package_paths(); workspace = args.workspace.resolve()
    runtime = active_runtime(workspace)
    if args.action == "install":
        print(json.dumps(install(package, data, workspace), ensure_ascii=False, indent=2)); return
    if args.action == "workflow":
        raise SystemExit(workflow(args, workspace))
    if args.action in ("plan", "run"):
        options = [args.action, "--data", runtime, "--tasks", *args.tasks, "--scope", args.scope]
        for name in ("people", "periods"):
            if getattr(args, name) is not None:
                options += ["--" + name, getattr(args, name)]
        if args.action == "run":
            if args.out is None or args.budget_usd is None:
                p.error("run requires a fresh --out plus --budget-usd")
            options += ["--out", args.out.resolve(), "--budget-usd", args.budget_usd, "--workers", args.workers]
            if args.confirm_paid: options.append("--confirm-paid")
            if args.resume: options.append("--resume")
        status = child(workspace, "portable_run", options)
    elif args.action == "prepare":
        # This command rebuilds original source stages in a disposable output
        # tree; it is not the frozen-message replay command.
        prepared = args.out.resolve() if args.out else workspace / "outputs/reviewer_preparation"
        status = child(workspace, "portable_prepare", ["--workspace", workspace, "--out", prepared])
        if status == 0:
            status = child(workspace, "portable_adopt", ["--workspace", workspace, "--preparation", prepared])
    elif args.action == "evaluate":
        if args.answers is None or args.out is None:
            p.error("evaluate requires --answers <fresh run>/answers.jsonl and fresh --out")
        status = child(workspace, "portable_evaluate", ["--answers", args.answers.resolve(),
            "--data", runtime / "evaluation", "--out", args.out.resolve()])
    elif args.action == "downstream":
        if args.out is None: p.error("downstream requires --out")
        options = ["replay", "--data", workspace / "portable/downstream", "--out", args.out.resolve()]
        if args.a or args.b:
            if not args.a or not args.b: p.error("Provide both --a and --b for newly generated aggregate refits")
            options += ["--a", args.a.resolve(), "--b", args.b.resolve(), "--no-verify"]
        status = child(workspace, "portable_downstream", options)
    elif args.action == "calibrate":
        if args.out is None: p.error("calibrate requires --out")
        options = ["replay", "--data", workspace / "portable/calibration", "--out", args.out.resolve()]
        if args.fresh_evaluation:
            options += ["--fresh-evaluation", args.fresh_evaluation.resolve()]
        status = child(workspace, "portable_calibration", options)
    elif args.action == "audit-inputs":
        if args.out is None: p.error("audit-inputs requires a fresh --out")
        status = child(workspace, "portable_message_replay", ["--runtime-data", runtime,
            "--evidence-dir", workspace / "portable/evidence", "--out", args.out.resolve()])
    else:
        options = ["--data", runtime, "--out", args.out.resolve() if args.out else workspace / "portable_check"]
        status = child(workspace, "portable_validate", options)
    raise SystemExit(status)


if __name__ == "__main__":
    main()
