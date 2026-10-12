"""Prepare a small paired trial and template probes from the offline sidecars."""
import argparse
from collections import defaultdict
from copy import deepcopy
import html
import json
from pathlib import Path
import random

from .lifetime_experience import ARMS, MARKER, json_hash, matched_text
from .lifetime_sources import MONTHS, dump, sha


def prepare(root, bank, dest):
    root, bank, dest = Path(root).resolve(), Path(bank).resolve(), Path(dest).resolve()
    if dest.exists() or not dest.is_relative_to(root / "outputs"):
        raise ValueError("fresh ignored trial directory required")
    summary = json.loads((bank / "summary.json").read_text())
    for name, expected in summary["prepared_file_sha256"].items():
        if sha(bank/name) != expected:
            raise ValueError("sidecar bank changed")
    for name, expected in summary["sources_sha256"].items():
        if sha(root/name) != expected:
            raise ValueError("original source changed")
    protected = json.loads((root / "docs/sources/sol_handoff_protected_files_20261010.json").read_text())["files_sha256"]
    if any(sha(root/name) != expected for name, expected in protected.items()):
        raise ValueError("protected pending files changed")
    dest.mkdir(parents=True)
    seed = 20261012
    rng = random.Random(seed)
    source_hashes = {str((bank/"summary.json").relative_to(root)): sha(bank/"summary.json")}
    selection, cases, samples_by_month = [], [], {}
    base_root = root / "outputs/sce_confidence_trial_20261011_v1"
    base_plan = json.loads((base_root/"trial_manifest.json").read_text())
    for month in MONTHS:
        base = base_root / month / "population.json"
        if sha(base) != base_plan["prepared_file_sha256"][str(base.relative_to(base_root))]:
            raise ValueError("frozen original population changed")
        source_hashes[str(base.relative_to(root))] = sha(base)
        population = json.loads(base.read_text())
        profiles = {p["agent_id"]: p["attributes"] for p in population["personas"]}
        sidecars = json.loads((bank/month/"life_background_private.json").read_text())
        eligible = {s["agent_id"] for s in sidecars if s["eligible_for_first_pilot"]}
        groups = defaultdict(list)
        for aid in sorted(eligible):
            groups[profiles[aid]["age_group"]].append(aid)
        selected = []
        for group in ("Under 40", "40 to 60", "Over 60"):
            if len(groups[group]) < 4:
                raise ValueError("four eligible people per age category unavailable")
            selected.extend(rng.sample(groups[group], 4))
        samples_by_month[month] = selected
        for aid in selected:
            selection.append({"month": month, "local_agent_id": aid, "age_group": profiles[aid]["age_group"]})
        for arm in ARMS:
            path = bank/month/("preview_"+arm+"_private.json")
            previews = {p["agent_id"]: p for p in json.loads(path.read_text())}
            for aid in selected:
                row = previews[aid]
                if json_hash(row["messages"]) != row["canonical_messages_sha256"]:
                    raise ValueError("canonical message hash mismatch")
                cases.append({"case_id": f"{month}_{arm}_{aid}", "month": month, "arm": arm,
                    "local_agent_id": aid, "messages": row["messages"],
                    "messages_sha256": row["canonical_messages_sha256"],
                    "questionnaire_suffix_sha256": json_hash(row["messages"][0]["content"].split(MARKER, 1)[1])})
    # Read template introductions; keep the complete matched body unchanged.
    templates_path = root / "docs/literature/sce/heterogeneity_and_probability/prompt_template_candidates_20261012.json"
    source_hashes[str(templates_path.relative_to(root))] = sha(templates_path)
    templates = json.loads(templates_path.read_text())["wording_variants"]
    preambles = {t["id"]: t["template"].split("\n\n")[1] for t in templates}
    template_profiles = samples_by_month[MONTHS[0]][:2] + samples_by_month[MONTHS[0]][4:6] + samples_by_month[MONTHS[0]][8:10]
    reference = {r["local_agent_id"]: r for r in cases if r["month"] == MONTHS[0] and r["arm"] == "age_matched_history"}
    probes = []
    for aid in template_profiles:
        original = reference[aid]["messages"]
        for template_id, preamble in preambles.items():
            messages = deepcopy(original)
            messages[0]["content"] = preamble+"\n\n"+original[0]["content"]
            if messages[0]["content"].removeprefix(preamble+"\n\n") != original[0]["content"]:
                raise ValueError("template body changed")
            probes.append({"case_id": f"{MONTHS[0]}_{template_id}_{aid}", "month": MONTHS[0],
                "template_id": template_id, "local_agent_id": aid, "messages": messages,
                "messages_sha256": json_hash(messages), "canonical_fact_body_sha256": json_hash(original),
                "frozen_questionnaire_suffix_sha256": reference[aid]["questionnaire_suffix_sha256"]})
    with (dest/"cases_private.jsonl").open("w") as handle:
        for row in cases:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n")
    dump(dest/"selection_private.json", selection)
    dump(dest/"template_probes_private.json", probes)
    # Pricing is an illustrative reserve under the previous trial's rates, not a current quote.
    def reserve(messages):
        byte_allowance = len(json.dumps(messages, ensure_ascii=False).encode()) + 256
        return byte_allowance * .30 / 1e6 + 1024 * 1.20 / 1e6
    manifest = {"status": "prepared_message_draft_not_authorized_not_executable_simulation_config",
        "research_line": "A_historical_reconstruction", "months": list(MONTHS),
        "n_per_month": 12, "n_respondent_months": len(selection), "arms": list(ARMS), "repeats_candidate": 2,
        "main_unique_prompts": len(cases), "main_candidate_calls": len(cases)*2,
        "template_unique_prompts": len(probes), "template_candidate_calls": len(probes)*2,
        "sample_seed": seed, "sampling": "four eligible people per original age category; no outcomes used; not a nationally representative sample",
        "model_candidate": "deepseek-flash via DeepSeek official API", "temperature_candidate": .5,
        "max_output_tokens_candidate": 1024, "automatic_retries_candidate": 0,
        "generation_repeat_is_not_model_seed": True,
        "confidence_and_news": "retain prior national-confidence condition and frozen 50/50 news exactly",
        "primary_candidate_history_start_age": 6, "start_age_not_frozen": True,
        "old_baseline_reuse": "context only; proposed paired check reruns original to compare fresh generations under a common API configuration",
        "historical_rate_reserve_only": {"input_per_million_usd": .30, "output_per_million_usd": 1.20,
            "main_reserve_usd": sum(reserve(r["messages"]) for r in cases)*2,
            "template_reserve_usd": sum(reserve(r["messages"]) for r in probes)*2,
            "is_current_price_quote": False, "not_actual_tokens_or_invoice": True},
        "candidate_evaluation": {"primary": ["Q9 group median error", "Q9 cross-person IQR", "Q9 distribution distance"],
            "secondary": ["Q8 median error", "individual uncertainty", "raw deflation probability", "age group differences"],
            "comparisons": ["age_only vs original separates age precision", "common_history vs age_only separates shared historical information",
                "age_matched_history vs common_history combines age alignment and different compression; not a pure causal matching effect"],
            "template_check": "within-person comparison and repeated generations; template copies do not increase population size",
            "known_development_periods": True, "independent_holdout_registered": False,
            "no_target_based_answer_selection": True},
        "pre_run_gates": ["review complete prompts and the age-6 convention", "implement isolated runner and pass deterministic dry runs",
            "verify current model/price and register concrete expenditure cap", "confirm new age-detail sending scope and new-call budget",
            "register a separate mechanism holdout before any follow-up tuning"],
        "sources_sha256": source_hashes, "code_sha256": sha(__file__),
        "new_api_calls": 0, "files_sha256": {p.name: sha(p) for p in dest.iterdir() if p.is_file()}}
    dump(dest/"trial_manifest.json", manifest)
    print(json.dumps({k: manifest[k] for k in ("n_respondent_months", "main_candidate_calls", "template_candidate_calls", "historical_rate_reserve_only")}, ensure_ascii=False))
    return manifest


def update_reading_page(root, bank, trial):
    """Extend the existing artifact using clearly synthetic examples only."""
    root, bank, trial = Path(root).resolve(), Path(bank).resolve(), Path(trial).resolve()
    page = root / "docs/literature/sce/news_selection/news_review_20261011.html"
    before = page.read_text()
    anchor = "lifetime-background-preparation"
    if before.count("<footer>") != 1 or f'id="{anchor}"' in before:
        raise ValueError("reading page insertion point changed")
    (trial/"reading_page_before.html").write_text(before)
    annual = {r["year"]: r for r in json.loads((bank/"202203/annual_cpi_public.json").read_text())}
    sources = json.loads((root/"data/raw/lifetime_experience/20261012_v1/manifest.json").read_text())
    examples = []
    for label, births in (("约25岁的示意居民", [1996, 1997]), ("约75岁的示意居民", [1946, 1947])):
        record = {"birth_year_possible_range": births}
        text, details = matched_text(record, annual, sources["events"], 6, 2021)
        examples.append("<details><summary>"+html.escape(label)+"：展开实际格式的英文历史背景</summary>"
                        "<pre style=\"white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.65\">"+html.escape(text)+"</pre></details>")
    section = f'''<section id="{anchor}">
<h2>2026-10-12：年龄经历输入已准备，真实效果尚未验证</h2>
<p class="important">本轮完成资料归档、192条居民月记录的历史背景草案、四组共768份提示草案与小试抽样。新增模型调用0，正式配置未改。下面两位居民均为示意人物，不是SCE真实个人。</p>
<h3>准备了什么</h3>
<ul><li>ALFRED四个历史版本：2022-03-10、2022-09-13、2023-03-14、2024-03-12。对应最新CPI指数283.716、296.171、300.840、310.326，均与既有BLS发布稿核对。3月9日边界版本只到2022年1月。</li>
<li>长期序列统一用未季调CPI-U，以完整年度平均指数计算年度涨幅；不补入当年尚未发生的数据。美联储三篇历史文章只摘少量中性事实，当前下载文章不是经过认证的旧网页版本。</li>
<li>年龄仍是自报和推断范围。两个可能出生年份造成的“长期平均涨幅”差别中位数0.03、最大0.25个百分点；这是背景统计的敏感性，不是预测误差。</li></ul>
<h3>为什么分四组</h3>
<ol><li>原输入：沿用已跑过的央行信心版本。</li><li>只补年龄细节：辨别更细的年龄信息是否起作用。</li><li>共同历史背景：每个人拿到相同的年代摘要。</li><li>年龄对应背景：按可能经历的年龄阶段提供摘要。</li></ol>
<p>共同与年龄对应摘要保留的事实和压缩方式并不完全相同，因此差别不能全部解释成匹配有效。6岁起点尚未冻结；18岁起点也已另存。背景是全国年代环境的代理，不能声称记录了个人真实记忆。</p>
{''.join(examples)}
<h3>小试草案与下一步</h3>
<p>2022年3月/9月、2023年3月、2024年3月，各12人；每个年龄组4人。四组各生成两次，候选384次调用。另准备6人×3种中性措辞×两次生成，候选36次。措辞只改一句引导语，正文、问卷和数值完全相同。模板副本不是新增居民。</p>
<p>这些是已看过的开发时期。旧费率下的保守额度预留合计约$1.36，不是当前报价或真实账单。实际运行前还要完成独立运行入口、离线干跑、当前模型/价格核查及新预算确认；独立检验月份需另登记。当前不注入取整、零概率或概率表达行为。</p>
<p><a href="../heterogeneity_and_probability/lifetime_preparation_20261012.md">资料、方法与准确路径</a> · <a href="https://alfred.stlouisfed.org/series?seid=CPIAUCNS">ALFRED原始序列</a></p>
</section>'''
    after = before.replace("<footer>", section+"\n<footer>", 1)
    page.write_text(after)
    receipt = {"page": str(page.relative_to(root)), "before_sha256": sha(trial/"reading_page_before.html"),
        "after_sha256": sha(page), "anchor": anchor, "existing_content_preserved": after.replace(section+"\n", "", 1) == before,
        "examples_are_synthetic": True, "browser_visual_verification": False}
    dump(trial/"reading_receipt.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--update-reading-page", action="store_true")
    args = parser.parse_args()
    prepare(Path(__file__).resolve().parents[2], args.bank, args.out)
    if args.update_reading_page:
        update_reading_page(Path(__file__).resolve().parents[2], args.bank, args.out)
