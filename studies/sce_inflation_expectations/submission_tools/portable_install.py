"""Install the complete confidential, portable reproduction layer into v12."""
import hashlib
import json
from pathlib import Path
import shutil


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(2**20), b""):
            h.update(chunk)
    return h.hexdigest()


def freeze(out, *, public_sources, runtime, evidence, downstream, calibration):
    """Freeze existing zero-API exports; refuse mixed or unmanifested files."""
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(public_sources, out / "public_sources.zip")
    for name, source in (("runtime", runtime), ("evidence", evidence), ("downstream", downstream),
                         ("calibration", calibration)):
        shutil.copytree(source, out / name)
    files = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()}
    manifest = dict(schema="sce_portable_reproduction_layer/v1", files_sha256=files,
        scope="confidential competition review; not for public GitHub redistribution",
        new_API_calls=0, runtime="four original final tasks; fresh recursive state; own Key and budget",
        code="original exact research source in package archive; independently materialised workspace",
        exclusions=["API Keys", "account passwords", "authentication headers", "payment credentials"])
    write(out / "manifest.json", manifest)
    return manifest


def install(package, data, *, root):
    package, data, root = Path(package), Path(data).resolve(), Path(root)
    m = read(data / "manifest.json")
    if m["schema"] != "sce_portable_reproduction_layer/v1" or m["new_API_calls"] != 0:
        raise ValueError("Frozen zero-API portable layer required")
    for rel, digest in m["files_sha256"].items():
        p = (data / rel).resolve()
        if not p.is_relative_to(data) or p.is_symlink() or sha(p) != digest:
            raise ValueError("Portable artifact changed: " + rel)
    study = package / "studies/sce_inflation_expectations"
    target = study / "reproduction_data/portable"
    shutil.copytree(data, target)
    launcher = study / "simulation/reviewer_pipeline.py"
    shutil.copyfile(root / "studies/sce_inflation_expectations/submission_tools/reviewer_pipeline.py", launcher)
    short_entry = package / "review.py"
    short_entry.write_text('"""Short entry for the packaged original-source workflow."""\n'
        'from pathlib import Path\nimport runpy\n'
        'if __name__ == "__main__":\n'
        '    runpy.run_path(str(Path(__file__).resolve().parent / '
        '"studies/sce_inflation_expectations/simulation/reviewer_pipeline.py"), run_name="__main__")\n')
    index = read(package / "SOURCE_INDEX.json")
    index["exclusions"] = ["API Keys and genuine account/authentication/payment secrets", "entire third-party code repositories"]
    index["portable_execution_layer"] = "studies/sce_inflation_expectations/reproduction_data/portable/manifest.json"
    index["source_files_sha256"][str(launcher.relative_to(package))] = sha(launcher)
    index["source_files_sha256"]["review.py"] = sha(short_entry)
    index["source_file_count"] = len(index["source_files_sha256"])
    index["packaging_adapters"].append(str(launcher.relative_to(package)))
    index["packaging_adapters"].append("review.py")
    index["historical_source_scripts"] = "Exact original source archive also supplies the portable fresh execution workspace; organised main study remains the cached-result review entry"
    write(package / "SOURCE_INDEX.json", index)
    spec = read(study / "study.yaml")
    spec["status"] = "submission-candidate-portable-source-and-generation"
    spec["run_note"] = {"zh": "默认0API：正式逐答卷/指标复算；自备Key完整流程从包根review.py进入，含P/E重建、批量、递推、Normal与回归。"}
    write(study / "study.yaml", spec)
    resources = read(study / "resources.json")
    resources["datasets"].extend([
        dict(name="formal_questionnaires", path="reproduction_data/micro/manifest.json", kind="json",
             description="Exact archived model replies, field overlays and separate human evaluation targets."),
        dict(name="complete_original_messages", path="reproduction_data/inputs/manifest.json", kind="json",
             description="All 66,822 exact conditional messages; no missing public date/news fields."),
        dict(name="portable_original_source_workflow", path="reproduction_data/portable/manifest.json", kind="json",
             description="Public source snapshots, code maps, call receipts, dynamic templates and original refit inputs.")])
    write(study / "resources.json", resources)
    runs = read(study / "simulation/research_runs.json")
    runs["portable_reexecution"] = dict(entry="../../../review.py", detailed_entry="reviewer_pipeline.py",
        tasks=["A", "B", "monthly", "weekly"], requires="Reviewer-owned OpenRouter Key and explicit budget only for new model generation",
        scientific_configuration="Unchanged final method; fresh recursive states come from this new run, never archived successor answers",
        execution_policy="Durable dispatch; bounded cooldown; one known technical repair; unknown in-flight not resent",
        scope_note="Historical protocol hashes above describe original runs; this reexecution writes a new run configuration and receipts")
    write(study / "simulation/research_runs.json", runs)
    write(package / "PRIVATE_INPUTS_REQUIRED.json", dict(
        schema="sce_portable_inputs_supplied/v1", status="original public source snapshots and generation inputs supplied",
        note="Legacy filename retained. No missing author-only private input or author Key is required for the four final experiments.",
        entry="studies/sce_inflation_expectations/simulation/reviewer_pipeline.py",
        requires_from_reviewer=["Python dependencies", "funded own OpenRouter Key only for fresh LLM generation", "explicit local budget"],
        includes=["public original anonymous SCE IDs/dates", "internal code crosswalks", "population/prior/matching sources", "news archives and frozen labels", "original response IDs/timestamps/usage", "complete exact messages and raw outputs"],
        scientific_limits=["LLM randomness and mutable provider service prevent identical new natural-language answers", "historical text vintages and model training knowledge limitations remain as disclosed", "No paid external-service availability test was performed while packaging"],
        new_API_calls=0))
    policy = read(package / "DATA_RELEASE_POLICY.json")
    policy.update(policy_version="2026-10-29_v12", scope=m["scope"],
        excluded=m["exclusions"], release_projection="Original public SCE IDs, source dates and data-code maps retained; no additional anonymisation of public reproduction inputs",
        user_authorization="2026-10-29: author requested complete source-to-result reproducibility on reviewer equipment with reviewer-owned API Key",
        public_GitHub_data_release=False)
    policy["input_release_v12"] = dict(scope=m["scope"],
        includes="Exact complete prompts; public raw snapshots/candidate news/labels; original anonymous survey IDs/dates and data-code maps; original reply/request receipts; portable batch and fresh-state execution",
        excludes=m["exclusions"], no_publisher_license_asserted=True,
        public_release_permitted_by_this_package=False,
        notice="studies/sce_inflation_expectations/reproduction_data/inputs/NEWS_REVIEW_NOTICE.md")
    write(package / "DATA_RELEASE_POLICY.json", policy)
    guide = root / "submission/package_templates/v12/PORTABLE_REPRODUCTION.md"
    shutil.copyfile(guide, package / "PORTABLE_REPRODUCTION.md")
    for filename in ("MICRO_DATA_GUIDE.md",):
        shutil.copyfile(root / "submission/package_templates/v12" / filename,
                        study / "reproduction_data/micro" / filename)
    for filename in ("REVIEW_GUIDE.md", "PUBLIC_RELEASE_CHECKLIST.md"):
        (study / "reports" / filename).write_text(
            "# v12 当前入口\n\n从包根 README.md 和 PORTABLE_REPRODUCTION.md 进入。完整公开原始输入、日期、匿名SCE编号、内部编码映射、原始模型回复与调用凭证均保留；只排除真正的账号秘密。\n\n"
            "先运行默认零API复算；需要新回答时使用自备Key批量入口，支持A、B、月度和周度递推。带新闻与公开微观数据的ZIP仅供赛事保密评审，不随GitHub公开。\n")
    return dict(status="portable_original_source_to_results_layer_installed",
        file_count=len(m["files_sha256"]), manifest_sha256=sha(target / "manifest.json"),
        launcher_sha256=sha(launcher), new_API_calls=0)
