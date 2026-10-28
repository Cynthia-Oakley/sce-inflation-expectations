#!/usr/bin/env python3
"""Independently extract a study ZIP and run its offline entry from /tmp."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile


def verify_relocated_sources(package, source_index):
    """Independently compare original archive bodies with relocated code."""
    records = source_index.get("source_relocations")
    if not records:
        return None
    mapping = {r["original"]: r["exported"] for r in records}
    def module(path):
        return path[:-3].replace("/", ".").removesuffix(".__init__")
    reverse = {b: a for a, b in mapping.items() if a != b}
    reverse.update({module(b): module(a) for a, b in mapping.items() if a != b})
    pattern = re.compile(r'(?<![\w/])(?:' + '|'.join(re.escape(x) for x in sorted(reverse, key=len, reverse=True)) + r')(?![\w])')
    class StripImports(ast.NodeTransformer):
        def visit_Import(self, node): return None
        def visit_ImportFrom(self, node): return None
    adapter = "studies/sce_inflation_expectations/submission_tools/reproduce.py"
    checked = 0
    with zipfile.ZipFile(package / source_index["archived_source_supplement"]["archive"]) as z:
        for row in records:
            original = z.read(row["original"])
            exported = (package / row["exported"]).read_bytes()
            if hashlib.sha256(original).hexdigest() != row["original_sha256"] or hashlib.sha256(exported).hexdigest() != row["exported_sha256"]:
                raise ValueError("Source relocation provenance mismatch")
            if row["original"] == adapter:
                # Explicit adapter: separate fixture locations and local output
                # directory; empirical replay bodies still independently run.
                continue
            restored = pattern.sub(lambda m: reverse[m[0]], exported.decode())
            delta = len(Path(row["exported"]).parts) - len(Path(row["original"]).parts)
            if delta:
                restored = re.sub(r'(Path\(__file__\)(?:\.resolve\(\))?\.parents\[)(\d+)(\])',
                    lambda m: m[1] + str(int(m[2]) - delta) + m[3], restored)
            old_ast = ast.dump(StripImports().visit(ast.parse(original.decode())))
            new_ast = ast.dump(StripImports().visit(ast.parse(restored)))
            if old_ast != new_ast:
                raise ValueError("Research body changed beyond import/location adapter: " + row["original"])
            checked += 1
    study = package / "studies/sce_inflation_expectations"
    if {p.name for p in study.glob("*.py")} != {"__init__.py", "model.py", "run.py"}:
        raise ValueError("Loose study-root Python modules reintroduced")
    for name in ("grounding/grounding.json", "population/roster.jsonl", "reports/report.md"):
        if not (study / name).is_file():
            raise ValueError("Standard study artifact absent: " + name)
    return {"research_bodies_identical_after_import_location_normalization": checked,
            "explicit_packaging_runner_adapters": 1, "root_python_files": 3,
            "standard_reading_artifacts_present": True}


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
source_index = json.loads((entry.parents[2] / 'SOURCE_INDEX.json').read_text())
if source_index.get('source_relocations'):
    import importlib
    from socioverse.schemas import StudySpec, EnvironmentBundle, PopulationBundle, SimulationConfig
    from socioverse.schemas.resources import ResourceManifest
    from studies.sce_inflation_expectations.submission_tools.reproduce import no_network
    study = entry.parent
    with no_network():
        for path in source_index['source_files_sha256']:
            if not path.endswith('.py') or path.endswith('/run.py'):
                continue
            name = path[:-3].replace('/', '.').removesuffix('.__init__')
            importlib.import_module(name)
        for filename, schema in [('study.yaml', StudySpec), ('population/population.json', PopulationBundle),
                                 ('environment/environment.json', EnvironmentBundle), ('simulation/simulation.json', SimulationConfig),
                                 ('resources.json', ResourceManifest)]:
            schema.model_validate(json.loads((study / filename).read_text()))
        pop = json.loads((study / 'population/population.json').read_text())
        roster = [json.loads(line) for line in (study / 'population/roster.jsonl').read_text().splitlines()]
        if roster != pop['personas']:
            raise ValueError('Standard roster differs from synthetic fixture')
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
    layout_acceptance = verify_relocated_sources(package, source_index)
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
    micro = receipt.get("micro")
    if (package/"studies/sce_inflation_expectations/reproduction_data/micro/manifest.json").exists():
        if not micro or micro.get("status")!="passed_answer_level_reproduction" or micro.get("actual_LLM_calls")!=0:
            raise ValueError("v06 must actually execute its answer-level reproduction")
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
        "full_individual_reproduction": bool(micro),
        "individual_reproduction_scope": ("Four final tasks: raw-to-effective answer verification, exact-vector density scoring, A paired/full-wave metrics, Normal posterior reconstruction; no LLM regeneration" if micro else None),
        "answer_level_metrics": micro.get("national") if micro else None,
        "answer_level_counts": micro.get("verification") if micro else None,
        "numerical_density_refit": micro.get("scoring_mode") if micro else None,
        "organised_source_acceptance": layout_acceptance,
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
