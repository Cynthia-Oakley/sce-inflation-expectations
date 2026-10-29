"""Install explicitly scoped, deidentified inputs into a confidential study ZIP."""
from pathlib import Path
import hashlib
import json
import shutil

from .input_release_projection import validate_candidates


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def install(package, data, *, root):
    package, data, root = Path(package), Path(data).resolve(), Path(root)
    m = read(data / "candidate_manifest.json")
    required = {"complete_prompts.jsonl.gz", "prompt_templates.jsonl.gz", "population_belief_environment.jsonl.gz",
                "one_complete_prompt_example.json", "generation_settings.json", "SCE_DATA_NOTICE.md"}
    if (set(m["files"]) != required or not m.get("publisher_news_text_included")
            or m.get("real_person_linked_date_values_written") is not False
            or m.get("identity_map_included") is not False or m.get("new_API_calls") != 0):
        raise ValueError("Unexpected confidential-input allowlist or privacy status")
    study = package / "studies/sce_inflation_expectations"
    acceptance = validate_candidates(data, study / "reproduction_data/micro/model_outputs.jsonl.gz")
    target = study / "reproduction_data/inputs"
    target.mkdir()
    for name, info in m["files"].items():
        source = data / name
        if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != info["sha256"]:
            raise ValueError("Frozen input changed")
        if name != "SCE_DATA_NOTICE.md":
            shutil.copyfile(source, target / name)
    shutil.copyfile(data / "candidate_manifest.json", target / "source_projection_manifest.json")
    templates = root / "submission/package_templates/v10"
    shutil.copyfile(templates / "SCE_DATA_NOTICE.md", target / "SCE_DATA_NOTICE.md")
    installed = json.loads(json.dumps(m))
    notice = target / "SCE_DATA_NOTICE.md"
    installed["files"]["SCE_DATA_NOTICE.md"] = dict(bytes=notice.stat().st_size,
        sha256=hashlib.sha256(notice.read_bytes()).hexdigest())
    installed["source_projection_manifest_sha256"] = hashlib.sha256((data / "candidate_manifest.json").read_bytes()).hexdigest()
    installed["packaging_change"] = "SCE notice updated for v10 input scope; all prompt/data bytes retained"
    write(target / "manifest.json", installed)
    for name in ("INPUTS_README.md", "NEWS_REVIEW_NOTICE.md"):
        shutil.copyfile(templates / name, target / ("README.md" if name == "INPUTS_README.md" else name))
    shutil.copyfile(root / "docs/workstreams/20261029_input_release_review/SOURCE_AND_REUSE_NOTICE.md",
                    target / "SOURCE_TERMS_PREVIOUS_REVIEW.md")
    shutil.copyfile(root / "outputs/sce_input_release_candidates_20261029_v2/POLICY_SOURCES.json", target / "POLICY_SOURCES.json")
    # Earlier no-news review is provenance, explicitly superseded for this
    # restricted artifact by NEWS_REVIEW_NOTICE.md, never a copyright grant.
    shutil.copyfile(root / "studies/sce_inflation_expectations/submission_tools/reviewer_single_request.py",
                    study / "simulation/reviewer_request.py")
    write(target / "acceptance.json", acceptance)
    index = read(package / "SOURCE_INDEX.json")
    index["exclusions"] = ["credentials and provider request IDs", "original respondent IDs, actual completion dates and private crosswalks",
                           "entire third-party repositories", "unselected source articles and full publisher article bodies"]
    index["generation_input_manifest"] = "studies/sce_inflation_expectations/reproduction_data/inputs/manifest.json"
    entry = "studies/sce_inflation_expectations/simulation/reviewer_request.py"
    index["source_files_sha256"][entry] = hashlib.sha256((package / entry).read_bytes()).hexdigest()
    index["source_file_count"] = len(index["source_files_sha256"])
    index["packaging_adapters"].append(entry)
    index["distribution_scope"] = "confidential_competition_review_only_not_for_public_GitHub"
    write(package / "SOURCE_INDEX.json", index)
    policy = read(package / "DATA_RELEASE_POLICY.json")
    policy["input_release_v10"] = dict(scope=index["distribution_scope"], author_direction_date="2026-10-29",
        includes="Actual selected news excerpts, model-visible deidentified population/environment/prior inputs and complete B/monthly/weekly prompts",
        excludes="Keys, identity/donor crosswalks, original respondent IDs, real person-level completion/cutoff dates, unselected original datasets",
        no_publisher_license_asserted=True, public_release_permitted_by_this_package=False,
        notice="studies/sce_inflation_expectations/reproduction_data/inputs/NEWS_REVIEW_NOTICE.md")
    write(package / "DATA_RELEASE_POLICY.json", policy)
    required_inputs = read(package / "PRIVATE_INPUTS_REQUIRED.json")
    required_inputs["included_input_manifest"] = index["generation_input_manifest"]
    required_inputs["instructions"] = (
        "66,822 conditional input positions are supplied, including selected news excerpts for confidential review. "
        "24,852 B/monthly/weekly inputs are exact and complete. A's 41,970 inputs omit real person-linked dates. "
        "Use simulation/reviewer_request.py for offline preview or one explicit own-key conditional request. "
        "Full A regeneration and a fresh recursive chain still need separate private-date/restated-condition and state-rendering procedures. "
        "Default all remains offline. Never publish the news-bearing archive to GitHub.")
    write(package / "PRIVATE_INPUTS_REQUIRED.json", required_inputs)
    shutil.copyfile(templates / "MICRO_DATA_GUIDE.md", study / "reproduction_data/micro/MICRO_DATA_GUIDE.md")
    for name in ("REVIEW_GUIDE.md", "PUBLIC_RELEASE_CHECKLIST.md"):
        (study / "reports" / name).write_text(
            "# v10复现与分享范围\n\n默认逐答卷复算保持不变。实际P/E/先验、新闻摘录和完整Prompt候选已纳入"
            " `../reproduction_data/inputs/`；自备Key单次入口及范围见包根EXTERNAL_MODEL_AND_API.md。"
            "A真实个人日期和私人映射不提供，不能宣称所有历史运行可直接重跑。"
            "本ZIP仅供赛事保密评审，不得随将来公开GitHub自动再分发；第三方新闻未获公开再分发许可。\n")
    return acceptance
