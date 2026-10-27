"""Reviewer-facing source selection without moving frozen research modules.

Primary roots are deliberately curated. Static transitive imports, package
initializers and the scorer's two local-path imports stay executable. Remaining
Python files are a read-only source supplement, not declared obsolete or deleted.
"""
import ast
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[3]
STUDY_REL = "studies/sce_inflation_expectations"

ENTRY_GROUPS = {
    "offline_review_and_packaging": [
        "submission_tools/reproduce.py", "submission_tools/package_builder.py",
        "submission_tools/release_evidence.py", "submission_tools/source_layout.py",
        "submission_tools/experiment_logs.py"],
    "A_personal_reconstruction": ["experiments/full_a_personal_inputs.py",
        "experiments/full_a_personal_terminal.py", "evaluation/full_a_personal.py"],
    "B_latest_independent_months": ["experiments/recent_b_sampled_dates.py",
        "experiments/recent_b_sampled_terminal.py"],
    "Core_Normal": ["core_normal_joint.py", "experiments/full_a_core_normal.py",
        "evaluation/full_a_core_normal.py", "experiments/recent_b_core_normal.py"],
    "monthly_recursion": ["experiments/recent_b_recursion.py",
        "reports/monthly_b_recursion.py"],
    "weekly_recursion": ["experiments/weekly_inputs.py", "experiments/weekly_terminal.py",
        "experiments/weekly_evaluation.py", "experiments/weekly_final_readout.py"],
    "macro_and_downstream": ["evaluation/aggregate_blend.py",
        "evaluation/full_a_macro_calibration.py", "evaluation/downstream_regression.py"],
}
SCRIPT_ENTRIES = [
    "build_sce_research_package.py", "verify_sce_research_package.py", "catalog_sce_study.py",
    "build_sce_submission_experiment_logs.py", "prepare_sce_full_a_personal_inputs.py",
    "run_sce_full_a_personal.py", "analyze_sce_full_a_personal.py", "run_sce_recent_b_sampled.py",
    "prepare_sce_recent_b_sampled_dates.py", "run_sce_full_a_core_normal.py",
    "evaluate_sce_full_a_core_normal.py", "expand_sce_recent_b_core_normal.py",
    "evaluate_sce_recent_b_core_normal.py", "run_sce_recent_b_recursion.py",
    "analyze_sce_recent_b_recursion.py", "prepare_sce_weekly_release_plan.py",
    "prepare_sce_weekly_inputs.py", "run_sce_weekly.py", "evaluate_sce_weekly_compat.py",
    "analyze_sce_weekly_final.py", "analyze_sce_full_a_macro_calibration.py",
    "analyze_sce_downstream_regression.py", "prepare_sce_downstream_data.py",
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def all_sources(root):
    root = Path(root).resolve()
    files = list((root / STUDY_REL).rglob("*.py")) + list((root / "scripts").glob("*.py"))
    return sorted(p for p in files if p.is_file() and "__pycache__" not in p.parts)


def dependency_closure(root, entry_paths, *, files=None):
    root = Path(root).resolve()
    originals = files if files is not None else all_sources(root)
    if any(Path(p).is_symlink() for p in originals):
        raise ValueError("Source-file symlinks are not permitted")
    files = [Path(p).resolve() for p in originals]
    if any(not p.is_relative_to(root) for p in files):
        raise ValueError("Source file outside declared root")
    modules = {}
    for path in files:
        parts = list(path.relative_to(root).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        modules[".".join(parts)] = path
    initial = [root / p for p in entry_paths]
    if any(p not in files for p in initial):
        missing = [str(p.relative_to(root)) for p in initial if p not in files]
        raise ValueError("Curated source entry missing: " + ", ".join(missing))
    queue = deque(initial); selected = set(); edges = {}
    while queue:
        path = queue.popleft()
        if path in selected:
            continue
        selected.add(path)
        name = ".".join(path.relative_to(root).with_suffix("").parts)
        package = name.rsplit(".", 1)[0] if path.name != "__init__.py" else name.removesuffix(".__init__")
        targets = set()
        def resolve(module):
            if module in modules:
                targets.add(modules[module])
            # Some frozen scoring modules use an explicitly inserted local path.
            elif "." not in module:
                local = path.parent / (module + ".py")
                score = root / STUDY_REL / "scoring" / (module + ".py")
                if local in files:
                    targets.add(local)
                elif module in {"sce_q9", "beta_fit_kernel"} and score in files:
                    targets.add(score)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    resolve(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parts = package.split(".")
                    base = ".".join(parts[:len(parts) - node.level + 1])
                    module = ".".join(filter(None, (base, node.module)))
                else:
                    module = node.module or ""
                resolve(module)
                for alias in node.names:
                    resolve(module + "." + alias.name)
        for parent in path.parents:
            if parent == root:
                break
            init = parent / "__init__.py"
            if init in files:
                targets.add(init)
        targets.discard(path)
        edges[str(path.relative_to(root))] = sorted(str(p.relative_to(root)) for p in targets)
        queue.extend(sorted(targets - selected))
    return sorted(selected), edges


def layout(root=ROOT):
    root = Path(root).resolve(); files = all_sources(root)
    groups = {group: [STUDY_REL + "/" + p for p in paths] for group, paths in ENTRY_GROUPS.items()}
    groups["CLI_wrappers"] = ["scripts/" + p for p in SCRIPT_ENTRIES]
    entries = [p for paths in groups.values() for p in paths]
    selected, edges = dependency_closure(root, entries, files=files)
    chosen = set(selected)
    return {"groups": groups, "entries": entries, "selected": selected,
            "supplement": [p for p in files if p not in chosen], "edges": edges}


def write_inventory(out, root=ROOT):
    root = Path(root).resolve(); out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    plan = layout(root)
    chosen = set(plan["selected"]); entries = {root / p for p in plan["entries"]}
    rows = []
    for path in sorted((root / STUDY_REL).rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        if path.name == ".DS_Store":
            status = "local_ephemeral_not_packaged"
        elif path in entries:
            status = "current_research_entry"
        elif path in chosen:
            status = "transitive_runtime_or_compatibility_dependency"
        elif path.suffix == ".py":
            status = "supporting_or_historical_source_supplement"
        elif "/population/" in rel and path.name != "README.md":
            status = "local_population_or_fixture_not_auto_distributed"
        elif "/reports/" in rel and ("progress_20261015" in rel or "manuscript" in path.name):
            status = "historical_report_preserved_in_place"
        elif path.suffix in {".json", ".jsonl", ".yaml", ".txt"}:
            status = "versioned_configuration_or_evidence_review_required"
        else:
            status = "documentation_or_aggregate_figure"
        rows.append({"path": rel, "status": status, "bytes": path.stat().st_size, "sha256": sha(path)})
    result = {"schema": "sce_source_layout_inventory/v1", "study_files": len(rows),
        "status_counts": dict(Counter(r["status"] for r in rows)),
        "all_python_sources": len(chosen) + len(plan["supplement"]),
        "main_python_sources": len(chosen), "reference_archive_python_sources": len(plan["supplement"]),
        "classification_basis": "Curated research roots plus static imports; not proof that every historical file was individually rerun or obsolete.",
        "original_source_files_moved_or_deleted": 0, "new_API_calls": 0,
        "entry_groups": plan["groups"], "files": rows}
    (out / "file_catalog.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    (out / "dependency_edges.json").write_text(json.dumps(plan["edges"], indent=2) + "\n")
    return result


def export_supplement(package, root, plan, *, source_bytes):
    """Archive references as code only, with a file-level independent hash map."""
    package, root = Path(package), Path(root)
    archive_dir = package / "archive"; archive_dir.mkdir()
    mapping = {}
    with zipfile.ZipFile(archive_dir / "research_source_supplement.zip", "x", zipfile.ZIP_DEFLATED) as z:
        for path in plan["supplement"]:
            content = source_bytes(path)
            rel = path.relative_to(root).as_posix()
            z.writestr(rel, content)
            mapping[rel] = hashlib.sha256(content).hexdigest()
    (archive_dir / "SOURCE_INDEX.json").write_text(json.dumps({"files_sha256": mapping,
        "scope": "Supporting research, historical experiments and development helpers. Not required by default replay; not all obsolete.",
        "raw_data_included": False}, ensure_ascii=False, indent=2) + "\n")
    (archive_dir / "README.md").write_text("# 补充源码归档\n\n默认运行不需要解压。这里是主线依赖之外的专题、历史实验和开发辅助源码，保留原路径与逐文件哈希；不表示全部失效，也不是新建的第二份维护源码。\n\n如需复查早期实验，先按研究问题定位源码，再在独立副本中解压；完整运行仍需合法的原输入与版本依赖。不要覆盖主包或直接执行历史付费入口。原始数据、个人轨迹和新闻文本不在此档。\n")
    return {"archive": "archive/research_source_supplement.zip", "archive_sha256": sha(archive_dir / "research_source_supplement.zip"),
            "source_file_count": len(mapping), "original_source_files_moved_or_deleted": 0}
