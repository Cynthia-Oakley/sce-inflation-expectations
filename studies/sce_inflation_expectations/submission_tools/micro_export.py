"""Project immutable main-run records into an offline, pseudonymous review dataset.

No prompts, API clients, network calls, or target-dependent answer selection.
The public source files are read-only; the private key map stays outside ZIP.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil

from .package_builder import ROOT, read, sha, write

RUNS = {
    "A": "outputs/sce_full_a_t0_terminal_20261025_v1",
    "B": "outputs/sce_recent_b_sampled_terminal_20261026_v1",
    "monthly": "outputs/sce_recent_b_recursion_terminal_20261026_v2",
    "weekly": "outputs/sce_weekly_terminal_20261027_v1",
}
ANALYSIS = "outputs/sce_full_a_t0_analysis_20261026_v1"
A_NORMAL = "outputs/sce_full_a_core_normal_prediction_20261026_v2"
A_PREP = "outputs/sce_full_a_core_normal_prepared_20261026_v3"
B_NORMAL = "outputs/sce_recent_b_core_normal_20261026_v1"
TRUTH = "outputs/sce_monthly_fine_full_truth_20261023_v3"


def rows(path):
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def save_rows(path, records):
    """Stable gzip without a machine filename or timestamp in its header."""
    with Path(path).open("xb") as binary:
        with gzip.GzipFile(fileobj=binary, mode="wb", filename="", mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8") as stream:
                for record in records:
                    stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")


def clean_text(text):
    """Remove identifiers if echoed; never invent an unredacted-original claim."""
    text = text or ""
    original = text
    for pattern, replacement in (
        (r"\bsk-[A-Za-z0-9_-]{16,}", "[REDACTED_KEY]"),
        (r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]"),
        (r"/Users/[^\s\"']+", "[REDACTED_LOCAL_PATH]"),
        (r"\b(?:fine|sce_person|proxy_person)_[A-Za-z0-9_:-]{6,}\b", "[REDACTED_SOURCE_ID]"),
    ):
        text = re.sub(pattern, replacement, text)
    return text, text != original


class Sources:
    def __init__(self):
        self.hashes = {}

    def path(self, value):
        p = Path(value)
        p = p if p.is_absolute() else ROOT / p
        if not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to(ROOT):
            raise ValueError("Missing/unsafe original source: " + str(value))
        self.hashes[p.relative_to(ROOT).as_posix()] = sha(p)
        return p

    def json(self, value):
        p=self.path(value)
        parent=p.parent/"manifest.json"
        if p.name!="manifest.json" and parent.is_file():
            m=read(parent)
            expected=m.get("files_sha256",{}).get(p.name)
            if expected and sha(p)!=expected:
                raise ValueError("Frozen adjacent manifest differs: "+str(p))
            self.path(parent)
        return read(p)

    def frozen(self, folder):
        folder = ROOT / folder
        manifest = self.json(folder / "manifest.json")
        for name, digest in manifest.get("files_sha256", {}).items():
            p = (folder / name).resolve()
            if not p.is_relative_to(folder.resolve()) or sha(p) != digest:
                raise ValueError("Frozen source changed: " + str(p))
        return manifest


def export(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / "outputs"):
        raise ValueError("Use a fresh local outputs directory")
    out.mkdir(parents=True)
    public = out / "data"
    public.mkdir()
    src = Sources()
    ids, private_ids, id_counts = {}, {}, Counter()

    def uid(run, aid):
        key = (run, str(aid))
        if key not in ids:
            id_counts[run] += 1
            value = f"{run}_{id_counts[run]:06d}"
            ids[key] = value
            private_ids[value] = str(aid)
        return ids[key]

    # Main plus technical repair attempts; do not turn failed attempts into answers.
    output_rows, lookup = [], {}
    counts, redacted = Counter(), 0
    for run, relative in RUNS.items():
        folder = ROOT / relative
        roots = [folder / name for name in ("main", "repair")] if run in ("A", "B") else [folder / "waves"]
        paths = sorted(p for r in roots for p in r.rglob("calls_private.jsonl"))
        for path in paths:
            src.frozen(path.parent.relative_to(ROOT))
            src.path(path)
            parts = path.relative_to(folder).parts
            stage = "repair" if "repair" in parts else "main"
            wave = parts[1] if parts[0] == "waves" else None
            for row in rows(path):
                if row.get("actual_model_results") is not True:
                    raise ValueError("Non-model fixture in a production call ledger")
                period = wave or str(row["month"])
                aid = uid(run, row["agent_id"])
                key = (run, period, aid, stage)
                if key in lookup:
                    raise ValueError("Duplicate physical call for a stage/person/period")
                response_id = f"response_{len(output_rows) + 1:07d}"
                raw = row.get("raw_response_text") or ""
                digest = hashlib.sha256(raw.encode()).hexdigest()
                if row.get("raw_response_sha256") not in (None, digest):
                    raise ValueError("Original response hash differs")
                text, changed = clean_text(raw)
                redacted += changed
                usage = row.get("usage") or {}
                result = dict(response_id=response_id, run=run, period=period, household=aid,
                    stage=stage, prompt_sha256=row["prompt_sha256"], response_text=text,
                    original_response_sha256=digest,
                    delivered_response_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    response_text_redacted=changed, finish_reason=row.get("finish_reason"),
                    error=row.get("error"), model=row.get("returned_model"), provider=row.get("returned_provider"),
                    reported_cost_usd=row.get("api_reported_cost_usd"),
                    reservation_if_cost_unknown_usd=row.get("request_reservation_usd") if row.get("api_reported_cost_usd") is None else 0,
                    tokens={k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
                    field_usable=row.get("field_usable"), actual_model_results=True,
                    physical_new_api_attempt=True, historical_exact_prompt_reuse=False)
                lookup[key] = result
                output_rows.append(result)
                counts[run + "_attempts"] += 1
        print("Raw output projection:", run, counts[run + "_attempts"], flush=True)

    answers, cases, cache = [], [], {}
    expected = {}
    # Exact-vector scalar cache is a speed option; the package also exposes refit.
    for relative in (ANALYSIS + "/scoring_cache_private.json",
                     RUNS["B"] + "/evaluation/scoring_cache_private.json",
                     RUNS["monthly"] + "/evaluation/scoring_cache_private.json"):
        for row in src.json(relative):
            key = tuple(row["bins"])
            old = cache.get(key)
            if old and any(old.get(k) != row["score"].get(k) for k in ("mean", "iqr")):
                raise ValueError("Different frozen scores for the same probability vector")
            cache[key] = row["score"]

    def references(run, period, aid, fields):
        refs = {}
        for field in ("q8", "q9"):
            stage = fields[field]
            found = lookup.get((run, period, aid, stage))
            refs[field] = found["response_id"] if found else None
        return refs

    def answer(run, period, source_aid, point, bins, weight, fields, *, fallback=None, **other):
        aid = uid(run, source_aid)
        item = dict(run=run, period=period, household=aid, q8=point, q9_bins=bins,
                    analysis_weight=weight, field_source=fields,
                    selected_responses=references(run, period, aid, fields), **other)
        if fallback:
            item["fallback"] = fallback
        answers.append(item)
        counts[run + "_answers"] += 1
        return item

    src.frozen(ANALYSIS)
    a_summary = src.json(ANALYSIS + "/summary.json")
    actions = { (str(r["month"]), r["agent_id"]): r for r in rows(src.path(
        RUNS["A"] + "/generation_views/view_0001/logical_actions_private.jsonl")) }
    for case in src.json(ANALYSIS + "/cases_private.json"):
        month, original = str(case["month"]), case["agent_id"]
        action = actions[month, original]
        imported=action["main"]["execution_kind"]=="historical_import"
        if imported:
            record=lookup["A",month,uid("A",original),"main"]
            record.update(physical_new_api_attempt=False,historical_exact_prompt_reuse=True)
            counts["A_historical_imports"]+=1
        operational = case["arms"]["monthly_reconstruction"]
        item = answer("A", month, original, operational["point"], operational["q9_bins"],
            case["survey_weight"], action["field_source"],
            fallback={"mean": operational["mean"], "iqr": operational["iqr"]}
                if not action["field_updated"]["q9"] or operational.get("evaluation_only_input_scalar_fallback") else None,
            normalization=action["q9_normalization"],
            selected_model_q9_bins=action["effective_q9_bins"],
            density_failure_retained_input=bool(operational.get("evaluation_only_input_scalar_fallback")))
        # A historical exact-prompt reuse is not another new API attempt.
        for field, ref in item["selected_responses"].items():
            if ref is None and action["field_source"][field] in ("main", "repair"):
                rawref = action["main" if action["field_source"][field] == "main" else "repair"]["raw_reply_ref"]
                if not rawref:
                    raise ValueError("A selected output is missing its ledger reference")
        c = {k: deepcopy(case[k]) for k in ("month", "repeat", "survey_weight", "real", "arms",
             "stratum", "survey_entry_status", "initial_q9_provenance")}
        c.update(agent_id=item["household"], userid=len(cases),
            profile={k: case["profile"].get(k) for k in ("age_group", "education_group", "numeracy", "household_income_band", "region")})
        cases.append(c)
    expected["A"] = {k: a_summary[k] for k in ("full_wave_monthly", "official_national", "quality", "weight_definition")}
    # Retain complete shared-metric references, including genuine-adjacent support.
    expected["A"]["paired"] = {k:a_summary[k] for k in ("fixed_roster", "genuine_previous_only")}

    bp = src.json(RUNS["B"] + "/package/protocol.json")
    b_initial={}
    for row in rows(src.path(RUNS["B"] + "/combined/positions_private.jsonl")):
        fields = row["state_after"]["fields"]
        transition = row["state_after"]["transition"]["field_updated_from_model"]
        sources = {f: ("repair" if transition[f] and row.get("field_overlay_repair_key")
                      and not (lookup.get(("B", str(row["month"]), uid("B", row["agent_id"]), "main"), {}).get("field_usable") or {}).get(f)
                      else "main" if transition[f] else "retained_input") for f in ("q8", "q9")}
        # Get the original frozen analysis weight, not an arbitrary equal weight.
        fallback=None
        if cache[tuple(fields["q9"]["value"])]["mean"] is None:
            month=str(row["month"])
            if month not in b_initial:b_initial[month]=src.json(bp["input_templates"]+f"/{month}/initial_states_private.json")
            bins=b_initial[month][row["agent_id"]]["fields"]["q9"]["value"]
            fallback=dict(bins=bins,**cache[tuple(bins)])
        answer("B", str(row["month"]), row["agent_id"], fields["q8"]["value"], fields["q9"]["value"], None, sources,fallback=fallback)
    roster = src.json(bp["population_preflight"] + "/selected_proxy_population_private.json")
    weights_b = {(str(m), uid("B", p["persona"]["agent_id"])): p["analysis_weight"] for m, rs in roster.items() for p in rs}
    for a in answers:
        if a["run"] == "B":
            a["analysis_weight"] = weights_b[a["period"], a["household"]]
    expected["B"] = src.json(RUNS["B"] + "/evaluation/summary.json")["monthly"]

    mp = src.json(RUNS["monthly"] + "/package/protocol.json")
    mw = src.json(mp["PE"] + "/weights_private.json")
    roots = src.json(mp["PE"] + "/root_answers_private.json")
    for month in mp["months"]:
        states = roots if month == mp["months"][0] else src.json(RUNS["monthly"] + f"/checkpoints/{month}/states_private.json")
        for aid, record in sorted(states.items()):
            fields = record["state_after"]["fields"]
            prior = record["state_after"]["transition"]["field_updated_from_model"]
            stages = {}
            for f in ("q8", "q9"):
                main = lookup.get(("monthly", month, uid("monthly", aid), "main"))
                stages[f] = "main" if main and (main["field_usable"] or {}).get(f) else "repair" if prior[f] else "retained_previous"
            item = answer("monthly", month, aid, fields["q8"]["value"], fields["q9"]["value"], mw[aid]["analysis_weight"], stages,
                          previous_period=record.get("previous_month"), root_reused=month == mp["months"][0])
            if month == mp["months"][0]:
                ref = next(a for a in answers if a["run"] == "B" and a["period"] == month and a["household"] == uid("B", aid))
                item["selected_responses"] = ref["selected_responses"]
                item["shared_B_root"] = {"period":month,"household":ref["household"]}
    expected["monthly"] = src.json(RUNS["monthly"] + "/evaluation/summary.json")["monthly"]

    wp = src.json(RUNS["weekly"] + "/package/protocol.json")
    plan = src.json(wp["inputs"] + "/weekly_plan.json")
    ww = src.json(wp["inputs"] + "/weights_private.json")
    for p in plan:
        step = p["step_key"]
        for aid, state in sorted(src.json(RUNS["weekly"] + f"/checkpoints/{step}/states_private.json").items()):
            f = state["fields"]
            answer("weekly", step, aid, f["q8"]["value"], f["q9"]["value"], ww[aid], state["last_response_field_sources"],
                   cycle=state["cycle_key"], reset_required=p["reset_required"])
    with src.path(RUNS["weekly"] + "/evaluation/weekly_national.csv").open() as stream:
        expected["weekly"] = list(csv.DictReader(stream))

    # Full-wave reference consists of released public survey scalars and weights.
    # Do not claim its original ten-bin vectors are contained when they are not.
    full = src.json(TRUTH + "/full_wave_private.json")
    save_rows(public / "A_full_wave_targets.jsonl.gz", (
        dict(month=m, row=i, q9_mean=r["q9_mean"], q8=r["q8_point"], weight=r["weight"])
        for m, rs in full.items() for i, r in enumerate(rs)))
    save_rows(public / "A_paired_cases.jsonl.gz", cases)

    # Export the actual population draws separately from the integrated atom CDF.
    normals, populations = [], []
    for month_dir in sorted((ROOT / A_NORMAL).glob("[12][0-9]*")):
        month = month_dir.name
        data = src.json(A_PREP + f"/{month}/inputs_private.json")
        def anon(x):
            if isinstance(x, list): return [anon(v) for v in x]
            if isinstance(x, dict): return {k: uid("A_Normal", v) if k in ("id", "donor_id") else anon(v) for k,v in x.items()}
            return x
        normals.append(dict(run="A_Normal", period=month, inputs=anon(data),
            expected_atoms=anon(src.json(A_NORMAL + f"/{month}/atoms_private.json"))))
        populations.extend(dict(run="A_Normal", **anon(r)) for r in rows(src.path(A_NORMAL + f"/{month}/expanded_population_private.jsonl")))
    # Reuse the frozen frame maker solely to project its already declared source.
    from ..experiments.recent_b_core_normal import make_frame
    for month, rs in sorted(roster.items()):
        frame, profiles, cw, _ = make_frame(rs, month, 1300)
        def anon_b(x):
            if isinstance(x, list):return [anon_b(v) for v in x]
            if isinstance(x, dict):return {k:uid("B_Normal",v) if k in ("id","donor_id","proxy_id") else anon_b(v) for k,v in x.items()}
            return x
        normals.append(dict(run="B_Normal",period=month,frame=anon_b(frame),core_weights={uid("B_Normal",k):v for k,v in cw.items()},
            answers=anon_b(src.json(B_NORMAL+f"/{month}/core_model_answers_private.json")),
            expected_atoms=anon_b(src.json(B_NORMAL+f"/{month}/atoms_private.json"))))
        populations.extend(dict(run="B_Normal", **anon_b({k:v for k,v in r.items() if k!="profile"}))
            for r in rows(src.path(B_NORMAL+f"/{month}/expanded_population_private.jsonl")))
    expected["A_Normal"] = src.json("outputs/sce_full_a_core_normal_evaluation_20261026_v3/summary.json")["monthly"]
    expected["B_Normal"] = src.json("outputs/sce_recent_b_core_normal_evaluation_20261026_v1/summary.json")
    save_rows(public / "normal_mechanism.jsonl.gz", normals)
    save_rows(public / "normal_population_rows.jsonl.gz", populations)

    # Supplement missing exact-vector fits only; this is offline numerical work.
    from ..evaluation.cognition import _score_bins
    vectors = {tuple(a["q9_bins"]) for a in answers}
    missing = vectors - set(cache)
    if missing:
        from concurrent.futures import ProcessPoolExecutor
        print("Offline density fits required:", len(missing), flush=True)
        with ProcessPoolExecutor(max_workers=6) as pool:
            cache.update(zip(sorted(missing), pool.map(_score_bins, [list(v) for v in sorted(missing)], chunksize=16)))
    save_rows(public / "density_cache.jsonl.gz", (dict(bins=list(k),score=v) for k,v in sorted(cache.items())))
    save_rows(public / "model_outputs.jsonl.gz", output_rows)
    save_rows(public / "effective_answers.jsonl.gz", answers)
    write(public / "expected.json", expected)
    write(out / "private_key_map_NOT_FOR_PACKAGE.json", private_ids)
    write(out / "source_manifest_private.json", src.hashes)
    files = {p.name:sha(p) for p in public.iterdir() if p.is_file()}
    if any(counts[k+"_answers"]!=n for k,n in {"A":41970,"B":5632,"monthly":5632,"weekly":14100}.items()):
        raise ValueError("Canonical final answer scope differs")
    if counts["A_historical_imports"]!=182:
        raise ValueError("Historical exact-prompt reuse count changed")
    for name,digest in src.hashes.items():
        if sha(ROOT/name)!=digest:raise ValueError("Original source changed during projection")
    manifest = dict(schema="sce_micro_review_data/v1", scope=list(RUNS), files_sha256=files,
        counts=dict(counts), Normal_population_rows=len(populations), Normal_months=len(normals),
        physical_new_api_attempts=sum(r["physical_new_api_attempt"] for r in output_rows),
        physical_new_reported_cost_usd=sum(r["reported_cost_usd"] or 0 for r in output_rows if r["physical_new_api_attempt"]),
        export_code_sha256=sha(Path(__file__)),
        response_text_redactions=redacted, original_ids_included=False, prompts_included=False,
        source_file_hashes=list(src.hashes.values()), parameter_refit=False, new_API_calls=0,
        source_manifest_sha256=sha(out / "source_manifest_private.json"),
        full_wave_target_scope="Frozen public scalar means/Q8/weights; not every original human ten-bin response",
        development_pilots="Source/log index only; these four final runs are not all exploratory API calls")
    write(public / "manifest.json",manifest)
    print(json.dumps({k:v for k,v in manifest.items() if k not in ("files_sha256","source_file_hashes")},ensure_ascii=False,indent=2),flush=True)
    return manifest


def install(package, data):
    """Copy only the frozen release projection; never copy its private key map."""
    package, data = Path(package), Path(data).resolve()
    m=read(data/"manifest.json")
    required={"model_outputs.jsonl.gz","effective_answers.jsonl.gz","A_paired_cases.jsonl.gz",
              "A_full_wave_targets.jsonl.gz","density_cache.jsonl.gz","normal_mechanism.jsonl.gz",
              "normal_population_rows.jsonl.gz","expected.json"}
    if set(m["files_sha256"])!=required or m.get("new_API_calls")!=0:
        raise ValueError("Unexpected micro-data release allowlist")
    target=package/"studies/sce_inflation_expectations/reproduction_data/micro"
    target.mkdir()
    for name,digest in m["files_sha256"].items():
        p=(data/name).resolve()
        if not p.is_relative_to(data) or p.is_symlink() or sha(p)!=digest:
            raise ValueError("Micro export changed before packaging")
        shutil.copyfile(p,target/name)
    shutil.copyfile(data/"manifest.json",target/"manifest.json")
    for name in ("MICRO_DATA_GUIDE.md","SCE_DATA_NOTICE.md"):
        shutil.copyfile(TEMPLATES_V06/name, target/name)
    shutil.copyfile(ROOT/"submission/data_release_policy_v06.json",package/"DATA_RELEASE_POLICY.json")
    study=package/"studies/sce_inflation_expectations"
    spec=read(study/"study.yaml")
    spec.update(status="submission-candidate-answer-level-replay",
        run_note={"zh":"默认0API：工程例、聚合复算，以及四个最终任务逐答卷微观复算；付费再生成另列。"})
    write(study/"study.yaml",spec)
    idx=read(package/"SOURCE_INDEX.json")
    idx["exclusions"]=["credentials and provider request IDs","full prompts and original news text",
        "original respondent IDs, actual completion dates and private crosswalks","entire third-party repositories"]
    idx["answer_level_data_manifest"]="studies/sce_inflation_expectations/reproduction_data/micro/manifest.json"
    write(package/"SOURCE_INDEX.json",idx)
    # Prior guides are historical packaging text, not current scope declarations.
    for name in ("REVIEW_GUIDE.md","PUBLIC_RELEASE_CHECKLIST.md"):
        p=study/"reports"/name
        p.write_text("# v06复现范围更新\n\n当前逐答卷范围、原始输出与来源声明以 `../reproduction_data/micro/MICRO_DATA_GUIDE.md` 为准。"
                     "本包可重算四个最终任务的个人输出、A微观W1/IQR、Normal后验质量与全国误差；不声称重建了历史新闻或重新生成LLM。\n\n"
                     "全文提示、原始受访者编号、新闻全文与密钥不含在内。赛事后公开GitHub另作发布检查。\n")
    planning=package/"archive/planning_20261027"
    planning.mkdir()
    for name in ("PAPER_INTEGRATION_PLAN.md","LOCAL_DEMO_PLAN.md"):
        shutil.move(study/"reports"/name,planning/name)
    (planning/"README.md").write_text("# 2026-10-27写作/视频规划存档\n\n这些文件记录当时尚未完成的论文与录制计划，不是当前进展或执行入口。最终论文/视频另外提交，研究复现从包根README进入。\n")
    p=study/"reports/index.html"
    html=p.read_text().replace('href="LOCAL_DEMO_PLAN.md"','href="../../../archive/planning_20261027/LOCAL_DEMO_PLAN.md"').replace('href="PAPER_INTEGRATION_PLAN.md"','href="../../../archive/planning_20261027/PAPER_INTEGRATION_PLAN.md"')
    html=html.replace('完整微观重现仍需受控资料。','v06的逐答卷复算、原始模型回复与数据边界见 <a href="../reproduction_data/micro/MICRO_DATA_GUIDE.md">微观资料导读</a>。历史写作/视频规划已归档。')
    p.write_text(html)
    frozen=data.parent/"exporter_source_at_freeze.py"
    if sha(Path(__file__))!=m["export_code_sha256"]:
        if not frozen.is_file() or sha(frozen)!=m["export_code_sha256"]:
            raise ValueError("Original data-exporter source must accompany changed packaging helpers")
        shutil.copyfile(frozen,package/"archive/exporter_at_data_freeze.py")


TEMPLATES_V06=ROOT/"submission/package_templates/v06"
