"""Export a physically organised study without editing frozen research sources.

Only imports, source-location expressions, and registration scaffolding adapt to
the new locations. Full original source is archived with independent hashes.
"""
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil

from .source_layout import ENTRY_GROUPS, STUDY_REL, all_sources, layout, export_supplement, dependency_closure

ROOT = Path(__file__).resolve().parents[3]
PREFIX = "studies.sce_inflation_expectations"

POPULATION = {
    "age_reporting_audit", "belief_state_preparation", "belief_trial_preparation",
    "coverage_preparation", "expanded_state_inputs", "household_state_audit",
    "monthly_population", "personal_information_preparation", "population_stratification",
    "prior_belief_preparation", "reference_population_preparation", "spending_audit",
}
ENVIRONMENT = {
    "dated_prompt", "news_exposure", "news_exposure_demo", "news_exposure_trial",
    "news_extension_label_preparation", "news_label_compat", "news_label_trial",
    "news_mechanism_label_preparation", "news_mechanism_labels", "news_pool_preparation",
    "news_quantity", "news_selection_trial", "price_contact", "price_experience",
    "procurement_price_views", "information_exposure", "lifetime_sources",
    "lifetime_episodes", "lifetime_experience",
}
BEHAVIOR = {
    "behavior_prompt_blocks", "belief_revision", "cognition_input", "cognition_runtime",
    "confidence_experiment", "core_normal_joint", "experience_mechanism",
    "household_state_mechanism", "model_counterfactual", "output_format_example",
    "prior_belief_experiment", "q8_delta_contract", "q9_normalization",
    "native_spending", "lifetime_experiment", "lifetime_text_experiment", "u1_state_experiment",
}
RUNTIME = {
    "anchor_role_runtime", "expanded_state_runtime", "frozen_prompt_runtime",
    "information_update_runtime", "openrouter_frozen_runtime", "q8_delta_runtime",
    "reference_validation_runtime", "revision_format_runtime", "state_continuity_runtime",
}


def destination(relative):
    relative = Path(relative)
    for old, new in (("environment_authoring", "components/environment/authoring"),
                     ("reporting_behavior", "components/behavior/reporting")):
        prefix = STUDY_REL + "/" + old + "/"
        if relative.as_posix().startswith(prefix):
            return STUDY_REL + "/" + new + "/" + relative.as_posix().removeprefix(prefix)
    if relative.parent.as_posix() != STUDY_REL:
        return relative.as_posix()
    name = relative.stem
    if name == "model":
        folder = "examples/core_demo"
    elif name == "__init__":
        return relative.as_posix()
    elif name in POPULATION:
        folder = "components/population"
    elif name in ENVIRONMENT:
        folder = "components/environment"
    elif name in BEHAVIOR:
        folder = "components/behavior"
    elif name in RUNTIME or name == "reference_validation_preparation":
        folder = "runtime"
    elif name == "monthly_analysis":
        folder = "evaluation"
    else:
        raise ValueError("Unclassified root source: " + relative.as_posix())
    return f"{STUDY_REL}/{folder}/{relative.name}"


def module_name(path):
    parts = list(Path(path).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def plan(root=ROOT):
    root = Path(root).resolve()
    old = layout(root)
    # Current entry modules and their imports, but no historical registrations
    # imported solely by the former eager study __init__. No flat CLI copies.
    entries = [p for group, paths in old["groups"].items() if group != "CLI_wrappers" for p in paths]
    # The hand-calculated joint/missing-field regression tests exercise this
    # production compatibility adapter as well as the current full-A wrapper.
    entries.append(STUDY_REL + "/experiments/core_normal_expansion.py")
    _, edges = dependency_closure(root, entries)
    seen, todo = set(), list(entries)
    init = STUDY_REL + "/__init__.py"
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        if name != init:
            todo.extend(edges.get(name, []))
    mapping = {p: destination(p) for p in sorted(seen)}
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("Source relocation collision")
    return {"entries": entries, "mapping": mapping, "all_sources": all_sources(root)}


def relocate(text, original, target, mapping):
    """Rewrite only import statements and literal source-location references."""
    if original == target:
        delta = 0
    else:
        delta = len(Path(target).parts) - len(Path(original).parts)
    modules = {module_name(a): module_name(b) for a, b in mapping.items()}
    module = module_name(original)
    package = module if original.endswith("/__init__.py") else module.rsplit(".", 1)[0]
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    edits = []
    for node in ast.walk(ast.parse(text)):
        replacement = None
        if isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[:len(parts) - node.level + 1])
                resolved = ".".join(filter(None, (base, node.module)))
            else:
                resolved = node.module or ""
            if resolved.startswith(PREFIX):
                statements = []
                for alias in node.names:
                    child = resolved + "." + alias.name
                    mapped_child = modules.get(child)
                    if mapped_child and mapped_child != child:
                        parent, leaf = mapped_child.rsplit(".", 1)
                        suffix = f" as {alias.asname or alias.name}" if leaf != alias.name or alias.asname else ""
                        statements.append(f"from {parent} import {leaf}{suffix}")
                    else:
                        suffix = f" as {alias.asname}" if alias.asname else ""
                        statements.append(f"from {modules.get(resolved, resolved)} import {alias.name}{suffix}")
                replacement = ("\n" + " " * node.col_offset).join(statements)
        elif isinstance(node, ast.Import):
            # Imported module binding is preserved. Attribute references for
            # unaliased imports are relocated in the following token pass.
            if any(a.name in modules and modules[a.name] != a.name for a in node.names):
                replacement = "import " + ", ".join(modules.get(a.name, a.name) +
                    (f" as {a.asname}" if a.asname else "") for a in node.names)
        if replacement is not None:
            start = offsets[node.lineno - 1] + node.col_offset
            end = offsets[node.end_lineno - 1] + node.end_col_offset
            edits.append((start, end, replacement))
    for start, end, value in sorted(edits, reverse=True):
        text = text[:start] + value + text[end:]
    # The research ROOT stays the same package root after physical relocation.
    if delta:
        text = re.sub(r'(Path\(__file__\)(?:\.resolve\(\))?\.parents\[)(\d+)(\])',
                      lambda m: m[1] + str(int(m[2]) + delta) + m[3], text)
    # Source-bound import strings and source hashes/links must refer to the
    # relocated file. Single pass prevents applying a mapping twice.
    changes = {a: b for a, b in modules.items() if a != b}
    changes.update({a: b for a, b in mapping.items() if a != b})
    if changes:
        pattern = re.compile(r'(?<![\w/])(?:' + '|'.join(re.escape(x) for x in sorted(changes, key=len, reverse=True)) + r')(?![\w])')
        text = pattern.sub(lambda m: changes[m[0]], text)
    ast.parse(text)
    return text


def export(package, *, root=ROOT, source_bytes):
    root, package = Path(root).resolve(), Path(package)
    p = plan(root)
    records = []
    for original, target in p["mapping"].items():
        if original == STUDY_REL + "/__init__.py":
            continue
        content = source_bytes(root / original)
        transformed = relocate(content.decode("utf-8"), original, target, p["mapping"]).encode("utf-8")
        dest = package / target
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(transformed)
        records.append({"original": original, "exported": target,
            "original_sha256": hashlib.sha256(content).hexdigest(),
            "exported_sha256": hashlib.sha256(transformed).hexdigest(),
            "adapter": "import_and_source_location_only"})
    study = package / STUDY_REL
    (study / "__init__.py").write_text('"""SCE study: register only the explicit Core fixture, not old experiments."""\nfrom . import model\n')
    (study / "model.py").write_text('"""Official Core engineering fixture registration.\n\n'
        'Production uses runtime/ and experiments/; see simulation/research_runs.json.\n'
        'This module does not describe the empirical 512-household production run.\n"""\n'
        'from .examples.core_demo import model as engineering_fixture\n')
    for dest in list(study.rglob("*.py")):
        for parent in dest.parents:
            if parent == study:
                break
            init = parent / "__init__.py"
            if not init.exists():
                init.write_text('"""SCE organised study component."""\n')
    archive = export_supplement(package, root, {"supplement": p["all_sources"]}, source_bytes=source_bytes)
    (package / "archive/README.md").write_text('# 原始研究源码归档\n\n'
        '完整保存开发源码原路径和原字节，含当前实现及历史实验。默认不解压。\n\n'
        '主study按用途重排；SOURCE_INDEX.json记录导出前后路径及哈希。源码正文只调整导入和位置引用；'
        '旧算法、数据、付费运行和结果均未重写。历史受控输入不随包分发。\n')
    return p, records, archive


def complete_artifacts(package, *, root=ROOT):
    """Replace stale demo and old-B ambiguity, add official reading artifacts."""
    root, package = Path(root), Path(package)
    study = package / STUDY_REL
    def read(path): return json.loads(path.read_text())
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    example = study / "examples/core_demo"
    for folder in ("population", "environment", "simulation"):
        src = study / folder / f"{folder}_demo.json"
        shutil.move(src, example / f"{folder}.json")
    pop = read(example / "population.json")
    roster = study / "population/roster.jsonl"
    roster.write_text(''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in pop['personas']))
    spec = read(study / "study.yaml")
    spec.update(title="SCE：历史重建、近期模拟与周度更新（本地研究）",
        title_i18n={"zh":"SCE：历史重建、近期模拟与周度更新（本地研究）","en":"SCE: household expectation reconstruction and calibrated weekly simulation"},
        research_question="人口异质性、既有信念与时点化信息接触，能否重建家庭通胀预期并提供增量信号？",
        hypothesis="信息接触与先验更新影响模拟中心和分布，须分别与持续性及同结构宏观基线比较。",
        status="submission-candidate-offline-verified-controlled-micro-pending",
        step_meaning="默认Core工程例每步为一个合成测试月，共2步；真实A82/B11/周度47步分别见simulation/research_runs.json，不是这个2步示例。",
        run_note={"zh":"run.py默认执行0API工程示例及封存聚合复算。20人两步仅验证引擎接口；正式研究为A82月、B11月、Normal、月度递推、47周及下游分析。"},
        research_runs_ref="simulation/research_runs.json")
    spec['metric_descriptions']['q8_point_median_demo']='20人两步合成工程示例的未来12个月通胀点预期中位数；不是正式实证指标。'
    write(study / "study.yaml", spec)
    write(study / "resources.json", {
        "study_id":"sce_inflation_expectations", "mcp_servers":[],
        "datasets":[
            {"name":"engineering_personas", "path":"examples/core_demo/population.json", "kind":"json", "description":"20 hand-authored synthetic fixtures; not empirical SCE respondents."},
            {"name":"archived_national_cases", "path":"reproduction_data/aggregate_cases.json", "kind":"json", "description":"Current A plus explicitly labelled historical comparisons; aggregates only."},
            {"name":"completed_extensions", "path":"reproduction_data/extension_cases.json", "kind":"json", "description":"Latest B, Normal, monthly and weekly recursion and downstream prediction-error replay."}],
        "tools":[]})
    records = read(study / "simulation/latest_research_configurations.json")
    for r in records:
        r['role']='current_completed_research'
    write(study / "simulation/research_runs.json", {
        "default_core_example": "../examples/core_demo/", "default_example_is_empirical_run": False,
        "research_runs": records, "offline_evidence": "../reproduction_data/",
        "production_backend": "local_frozen_message_adapter_after_official_Core_offline_acceptance",
        "research_scope": {
            "A82":{"months":"2019-01 through 2025-10","sampling":"54 cells: education3 x numeracy2 x age3 x income3; unknown profiles separately; oversampling with calibrated population mass", "core_roster_size_per_month":512,"eligible_person_months":41970,"time_rule":"personal completion date minus one New York calendar day", "news":"4/8/16/32; CPI relevance1.5; alarm1", "prior":"own strictly earlier response, otherwise 1-3 month anonymous joint donor"},
            "B11":{"months":"2025-11 through 2026-09","core_size_per_month":512,"date_rule":"prior-year same-month empirical response-date distribution", "prior":"joint anonymous donor plus already public national Q9 calibration", "entry_exit":False},
            "Normal":{"algorithm":"weighted joint empirical shrinkage","tau":8,"A_size":"actual survey-wave count976-1372", "B_size":1300,"new_LLM_information":False},
            "monthly_recursion":{"root":"2025-11 reused", "new_months":"2025-12 through 2026-09", "fixed_households":512,"entry_exit":False,"national_reset_after_root":False},
            "weekly":{"months":"2025-11 through 2026-09", "fridays":47,"fixed_households":300,"national_reset":"only after a past SCE release becomes publicly usable", "within_cycle_state":"own previous simulated week", "Normal":False}},
        "controlled_inputs_and_new_paid_authorization_required_for_generation": True})
    (study / "simulation/latest_research_configurations.json").unlink()
    old = read(study / "simulation/production_references.json")
    (study / "simulation/production_references.json").unlink()
    write(package / "archive/historical_configuration_references.json", old)
    requirements=[]
    for label,relative in (
        ('A82_T0','outputs/sce_full_a_personal_inputs_20261025_v1/manifest.json'),
        ('B11_latest','outputs/sce_recent_b_sampled_dates_complete_20261026_v1/manifest.json'),
        ('monthly_recursion','outputs/sce_recent_b_recursion_terminal_20261026_v2/package/manifest.json'),
        ('weekly47','outputs/sce_weekly_terminal_20261027_v1/package/manifest.json')):
        source=root/relative
        if not source.is_file():raise ValueError('Current controlled input manifest absent: '+label)
        requirements.append({'id':label,'workspace_relative_path':relative,
            'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'included_in_zip':False,
            'access':'authorized_data_complete_workspace_required'})
    write(package/'PRIVATE_INPUTS_REQUIRED.json', {'requirements':requirements,
        'not_a_public_download_bundle':True,
        'instructions':'These are the current research inputs, not the superseded B bundle. Obtain legal sources, rebuild in an independent complete workspace and freeze a new version. The portable default only replays safe aggregates.'})
    grounding = {
        "study_id":"sce_inflation_expectations", "query":spec['research_question'],
        "updated_at":"2026-10-27", "method_notes":"Current research provenance summary; not the old two-month development grounding. Full historical bytes and per-person linkage remain controlled. Input admissibility does not certify absence of model training knowledge.",
        "implementation_refs":[{"title":"SocioVerse study anatomy","url":"https://socioverse.fudan-disc.com/docs/concepts/study-anatomy/","takeaway":"Standard artifacts and four-interface engineering test.","accessed":"2026-10-27"}],
        "facts":[
            {"id":"sce-questionnaire","claim":"SCE provides household inflation point expectations and ten-bin subjective probabilities.","basis":"sourced","source":{"title":"NYFed Survey of Consumer Expectations","url":"https://www.newyorkfed.org/microeconomics/sce","via":"provider","accessed":"2026-10-27"},"applies_to":["Q8","Q9"]},
            {"id":"research-records","claim":"Completed research configuration and data hashes are bound by exported protocol records.","basis":"sourced","source":{"title":"Frozen completed run metadata","url":"../simulation/research_runs.json","via":"provider","accessed":"2026-10-27"},"applies_to":["A82","B11","monthly_recursion","weekly47"]},
            {"id":"synthetic-engineering-roster","claim":"The default roster contains 20 hand-authored synthetic fixtures, not real SCE respondents.","value":20,"unit":"fixtures","basis":"assumed","source":{"title":"Packaged synthetic fixture","url":"../population/roster.jsonl","via":"user","accessed":"2026-10-27"},"applies_to":["default_core_example"]}],
        "assumptions":[
            {"id":"attention-proxy","claim":"News 4/8/16/32 and CPI relevance 1.5 are experimental modelling choices, not measured individual attention.","rationale":"Frozen mechanism comparisons; see reports/REVIEW_GUIDE.md and simulation/research_runs.json."},
            {"id":"recent-prior","claim":"Recent household priors are synthetic joint assignments calibrated to already public historical SCE; not true personal priors.","rationale":"Recent micro responses are unavailable."},
            {"id":"normal-expansion","claim":"Normal is weighted empirical shrinkage with tau=8, not new independent model information.","rationale":"Early48 masked-LLM selection; later periods are not used to select tau."}]}
    write(study / "grounding/grounding.json", grounding)
    # Replay still verifies every historical comparison, but readers encounter
    # the current A run first and old references live in an explicit subfolder.
    registry = read(study / "reproduction_data/aggregate_cases.json")
    cases = registry['cases']
    for item in cases:
        if item['case_id'].endswith('_original_reference'):
            old_path = study / "reproduction_data" / item['monthly_file']
            new_path = study / "reproduction_data/history" / old_path.name
            new_path.parent.mkdir(exist_ok=True)
            shutil.move(old_path,new_path)
            item['monthly_file']='history/'+old_path.name
            item['status']='historical_comparison_only'
        else:
            item['status']='current_completed_research'
    registry['cases']=sorted(cases,key=lambda c:c['status']=='historical_comparison_only')
    write(study / "reproduction_data/aggregate_cases.json",registry)
    # The relocated offline runner reads the explicitly separated examples.
    runner=study/'submission_tools/reproduce.py'
    text=runner.read_text()
    for folder in ('population','environment','simulation'):
        text=text.replace(f'study / "{folder}/{folder}_demo.json"',f'(study / "examples/core_demo/{folder}.json" if (study / "examples/core_demo/{folder}.json").exists() else study / "{folder}/{folder}_demo.json")')
    runner.write_text(text)
    text=text.replace('ROOT / "outputs" / ("reproduction_','ROOT / "_runs" / ("reproduction_')
    text=text.replace('"recent-b": "scripts/run_sce_recent_b.py"','"recent-b": "scripts/run_sce_recent_b_sampled.py"')
    runner.write_text(text)
    (study/'population/README.md').write_text('# 人口配置\n\npopulation.json与roster.jsonl是同一份20人合成工程示例，不能当作正式512人名单。正式抽样/权重/先验见simulation/research_runs.json、components/population与reports/REVIEW_GUIDE.md；真实个人资料不随包分发。\n')
    (study/'environment/README.md').write_text('# 环境配置\n\nenvironment.json仅用于两步工程示例，原日期是固定回归测试标签。正式研究的信息时点、来源、新闻与价格规则见simulation/research_runs.json及grounding/grounding.json；不以示例日期代表全期研究。\n')
    (study/'simulation/README.md').write_text('# 两类运行配置\n\nsimulation.json是官方Core的scripted工程验收设置，不收费、不生成实证成绩。research_runs.json登记实际已完成研究，seed_policy.json列各分配规则种子。旧B等历史配置仅保留在包根archive中。\n')
    (study/'reports/README.md').write_text('# 研究结果\n\n先读report.md，再读REVIEW_GUIDE.md和index.html。论文与视频计划不等于最终PDF/MP4；默认运行新生成的index.html是当次复算结果。\n')
    # Update algorithm paths in reviewer-facing prose to the physical locations.
    for doc in (study/'reports').glob('*.md'):
        content=doc.read_text()
        content=content.replace('旧示例model.py','examples/core_demo/model.py中的兼容示例')
        content=content.replace('3. 使用 `scripts/prepare_sce_full_a_personal_inputs.py --help`、`prepare_sce_recent_b_sampled_dates.py --help`、`prepare_sce_weekly_inputs.py --help` 及对应实验模块，按选定版本重新物化，不伪造原冻结哈希。具体P/E路径和当前机器缓存仍需重新配置，此步骤尚非无人干预的一键恢复。',
            '3. 按SOURCE_INDEX定位当前experiments模块。完整历史CLI在包根archive原源码中，须在单独的获准开发工作区恢复；不得直接覆盖本包。按选定版本重新物化并生成新哈希，具体P/E路径和缓存仍需配置，此步骤尚非无人干预的一键恢复。')
        doc.write_text(content)
    return {"standard_artifacts_added":["grounding/grounding.json","population/roster.jsonl","reports/report.md"],
        "historical_source_bytes_changed":False,"paid_generation_calls":0,
        "note":"Default scripted Core fixture is separated from real completed research configuration; no claim of full controlled-micro reproduction."}
