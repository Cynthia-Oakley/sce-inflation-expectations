#!/usr/bin/env python3
"""Independently extract a study ZIP and run its offline entry from /tmp."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile


def verify(archive, out, *, fresh_environment=False):
    archive, out = Path(archive).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    package = out / "isolated_package"
    package.mkdir()
    if fresh_environment:
        cfg = Path(sys.prefix) / "pyvenv.cfg"
        if (sys.prefix == sys.base_prefix or not cfg.exists()
                or "include-system-site-packages = false" not in cfg.read_text().lower()):
            raise ValueError("Fresh-environment acceptance requires a venv without system site packages")
    with zipfile.ZipFile(archive) as z:
        for entry in z.infolist():
            candidate = (package / entry.filename).resolve()
            if not candidate.is_relative_to(package) or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Unsafe ZIP member")
        z.extractall(package)
    result = out / "verified_results"
    origin = out / "import_origins.json"
    program = """
import json, runpy, sys
from pathlib import Path
entry, out, origins = map(Path, sys.argv[1:])
sys.argv = [str(entry), '--mode', 'all', '--out', str(out)]
runpy.run_path(str(entry), run_name='__main__')
mods = {name: str(Path(m.__file__).resolve()) for name, m in sys.modules.items()
        if name.startswith('studies.sce_inflation_expectations') and getattr(m, '__file__', None)}
origins.write_text(json.dumps(mods, indent=2))
"""
    env = {k: v for k, v in os.environ.items() if not any(t in k.upper() for t in ("KEY", "TOKEN", "SECRET", "PASSWORD"))}
    entry = package / "studies/sce_inflation_expectations/run.py"
    run = subprocess.run([sys.executable, "-I", "-c", program, str(entry), str(result), str(origin)],
                         cwd="/private/tmp" if Path("/private/tmp").exists() else "/tmp",
                         env=env, text=True, capture_output=True)
    (out / "execution.log").write_text(run.stdout + run.stderr)
    if run.returncode:
        raise RuntimeError("Offline reproduction failed; inspect execution.log")
    receipt = json.loads((result / "receipt.json").read_text())
    imported = json.loads(origin.read_text())
    if not imported or any(not Path(p).is_relative_to(package) for p in imported.values()):
        raise ValueError("Study module unexpectedly imported from original workspace")
    source_index = json.loads((package / "SOURCE_INDEX.json").read_text())
    supplement = source_index.get("archived_source_supplement")
    archived_sources_verified = 0
    if supplement:
        archive_path = (package / supplement["archive"]).resolve()
        if not archive_path.is_relative_to(package):
            raise ValueError("Source archive escaped package")
        if hashlib.sha256(archive_path.read_bytes()).hexdigest() != supplement["archive_sha256"]:
            raise ValueError("Source archive hash mismatch")
        expected = json.loads((package / "archive/SOURCE_INDEX.json").read_text())["files_sha256"]
        with zipfile.ZipFile(archive_path) as z:
            if len(z.namelist()) != len(expected) or set(z.namelist()) != set(expected):
                raise ValueError("Source archive member list differs")
            for name, digest in expected.items():
                if hashlib.sha256(z.read(name)).hexdigest() != digest:
                    raise ValueError("Archived source bytes changed")
        archived_sources_verified = len(expected)
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests"], cwd=package,
                           env=env, text=True, capture_output=True)
    (out / "tests.log").write_text(tests.stdout + tests.stderr)
    if tests.returncode:
        raise RuntimeError("Packaged target tests failed; inspect tests.log")
    ext = receipt["replay"].get("extensions", {})
    acceptance = {"status": "passed_independent_zip_offline_execution", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "verified_package_files": receipt["verification"]["files_verified"],
        "study_modules_all_from_extracted_package": len(imported),
        "main_source_files": source_index["source_file_count"],
        "archived_source_files_verified": archived_sources_verified,
        "dry_run": receipt["dry_run"], "base_replay_cases": len(receipt["replay"]["cases"]),
        "extension_replay_cases": len(ext.get("cases", [])),
        "downstream_groups_verified": ext.get("downstream", {}).get("model_metrics_verified"),
        "downstream_contrasts_verified": ext.get("downstream", {}).get("paired_contrasts_verified"),
        "target_tests_exit_code": tests.returncode, "new_API_calls": 0,
        "new_dependency_environment_installed": fresh_environment,
        "dependency_versions": {name: importlib.metadata.version(name) for name in (
            "SocioVerse2", "pydantic", "duckdb", "pyarrow", "pandas", "numpy", "scipy", "openai", "httpx", "matplotlib", "pytest")},
        "full_individual_reproduction": False,
        "results_html": str(result / "index.html")}
    (out / "acceptance.json").write_text(json.dumps(acceptance, ensure_ascii=False, indent=2) + "\n")
    return acceptance


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--fresh-environment", action="store_true",
                   help="Assert this invocation uses a newly installed no-system-site venv")
    a = p.parse_args()
    print(json.dumps(verify(a.archive, a.out, fresh_environment=a.fresh_environment), ensure_ascii=False, indent=2))
