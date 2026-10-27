"""Aggregate-only v03 exports and offline checks; no private trajectories or API.

These caches reproduce errors from archived predictions, not the process that
generated individuals, fitted their densities, or trained downstream regressions.
"""
from collections import defaultdict
import csv
import hashlib
from html import escape
import json
import math
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[3]
METRICS = ("mae_pp", "rmse_pp", "bias_pp")


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def csv_rows(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def csv_write(path, rows, columns):
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="raise")
        w.writeheader(); w.writerows({k: r[k] for k in columns} for r in rows)


def metrics(predictions, truth):
    from ..evaluation.metrics import headline_errors
    p, y = list(map(float, predictions)), list(map(float, truth))
    if not p or len(p) != len(y) or not all(math.isfinite(x) for x in p + y):
        raise ValueError("Nonempty finite paired predictions are required")
    return headline_errors(p, y)


def assert_metrics(actual, expected):
    for k in METRICS:
        if not math.isclose(actual[k], float(expected[k]), rel_tol=1e-10, abs_tol=1e-10):
            raise ValueError("Archived aggregate metric mismatch: " + k)


def _source_binding(paths):
    return {str(p.relative_to(ROOT)): digest(p) for p in paths}


def export_v03(package):
    """Strict column projections from five completed, independently read sources."""
    target = Path(package) / "studies/sce_inflation_expectations/reproduction_data"
    cases = []

    def case(case_id, rows, methods, panels, scope, sources, blend=None):
        filename = case_id + ".csv"
        columns = ["month", "truth_pp", *methods]
        projected = [{k: r[k] for k in columns} for r in rows]
        csv_write(target / filename, projected, columns)
        cases.append(dict(case_id=case_id, file=filename, sha256=digest(target / filename),
                          methods=list(methods), panels=panels, scope=scope,
                          source_files_sha256=_source_binding(sources), fixed_blend=blend))

    a = ROOT / "outputs/sce_full_a_macro_calibration_20261026_v1"
    a_summary = read(a / "summary.json")
    a_rows = csv_rows(a / "monthly_predictions_public.csv")
    a_methods = ["CoreNormal_tau8_pure", "CoreNormal_tau8_blend_mse", "persistence"]
    case("A82_Core_Normal_tau8", a_rows, a_methods,
         [{"name": name, "from": first, "to": last, "n": n,
           "expected": {m: a_summary["results"][m][key] for m in a_methods}}
          for name, first, last, n, key in (
              ("all82_descriptive", "201901", "202510", 82, "all82_descriptive"),
              ("late34_after_early48_fit", "202301", "202510", 34, "later34"))],
         "A reconstruction; Normal is a weighted statistical expansion, not new LLM evidence.",
         [a / "summary.json", a / "monthly_predictions_public.csv"],
         {"raw": "CoreNormal_tau8_pure", "anchor": "persistence", "combined": "CoreNormal_tau8_blend_mse",
          "weight": a_summary["fits"]["CoreNormal_tau8_blend_mse"]["simulation_weight"]})

    b = ROOT / "outputs/sce_recent_b_core_normal_evaluation_20261026_v1"
    b_summary = read(b / "summary.json")
    b_methods = ["Core_pp", "expanded_pp", "Core_blend_pp", "expanded_blend_pp",
                 "baseline_pp", "macro_without_sim_pp", "Core_macro_pp", "expanded_macro_pp"]
    case("B11_latest_Core_and_Normal", csv_rows(b / "monthly_national.csv"), b_methods,
         [{"name": "all11_retrospective", "from": "202511", "to": "202609", "n": 11,
           "expected": {m: b_summary["metrics"][m] for m in b_methods}}],
         "Latest B, prior-year response-date sampling; 512 Core, optional 1300-row Normal projection. No recent micro truth.",
         [b / "summary.json", b / "monthly_national.csv"],
         {"raw": "expanded_pp", "anchor": "baseline_pp", "combined": "expanded_blend_pp",
          "weight": b_summary["simulation_blend_weight"]})

    rec = ROOT / "outputs/sce_recent_b_recursion_analysis_20261026_v2/summary.json"
    r = read(rec)
    r_methods = ["recursive_pp", "anchor_pp", "fixed_blend_pp", "independently_initialized_B_pp",
                 "independent_fixed_blend_pp", "root_retention_pp"]
    case("monthly_autonomous_recursion", r["monthly"], r_methods,
         [{"name": "post_root10_primary", "from": "202512", "to": "202609", "n": 10,
           "expected": r["post_root_10_months_primary"]},
          {"name": "including_shared_root11_secondary", "from": "202511", "to": "202609", "n": 11,
           "expected": r["all_11_months_secondary"]}],
         "Fixed 512, no entry/exit, no reset after root. Shared root excluded from primary score; no Normal.",
         [rec], {"raw": "recursive_pp", "anchor": "anchor_pp", "combined": "fixed_blend_pp",
                 "weight": r["combination_weight"]})

    w = ROOT / "outputs/sce_weekly_final_readout_20261027_v2"
    w_summary = read(w / "summary.json")
    w_methods = {"raw_pp": "raw_model", "anchor_pp": "public_SCE_persistence",
                 "held_prior_pp": "same_cycle_fixed_joint_prior", "blend_pp": "fixed_A_early48_MSE_blend",
                 "macro_pp": "macro_without_sim", "macro_sim_pp": "macro_plus_sim"}
    w_rows = csv_rows(w / "monthly_primary.csv")
    case("weekly47_monthly11_primary", w_rows, w_methods,
         [{"name": "last_Friday11_primary", "from": "202511", "to": "202609", "n": 11,
           "expected": {k: w_summary["primary"][v] for k, v in w_methods.items()}}],
         "47 Fridays, fixed 300; released past SCE resets prior, own states update within cycle. Raw is before output blend. Retrospective; no Normal.",
         [w / "summary.json", w / "monthly_primary.csv"],
         {"raw": "raw_pp", "anchor": "anchor_pp", "combined": "blend_pp", "weight": r["combination_weight"]})
    # Only national weekly data, never the small conditional groups/individuals.
    csv_write(target / "weekly47_path.csv", csv_rows(w / "weekly_descriptive.csv"),
              ["step_key", "cutoff", "month", "q8_median_pp", "q9_median_pp", "q9_iqr_pp", "q9_std_pp", "reset_required"])

    micro = ROOT / "outputs/sce_full_a_core_normal_evaluation_20261026_v3"
    ms = read(micro / "summary.json")["full_wave_distribution"]["q9_mean"]
    micro_cols = ["month", "before_q9_w1_pp", "expanded_q9_w1_pp", "truth_q9_iqr_pp",
                  "before_q9_iqr_pp", "expanded_q9_iqr_pp"]
    csv_write(target / "A82_micro_monthly_summaries.csv", csv_rows(micro / "monthly_public.csv"), micro_cols)
    micro_expected = {"before_q9_w1_pp": ms["before_t0"]["mean_w1_pp"],
                      "expanded_q9_w1_pp": ms["expanded_by_tau"]["8"]["mean_w1_pp"],
                      "truth_q9_iqr_pp": ms["observed_distribution"]["mean_iqr_pp"],
                      "before_q9_iqr_pp": ms["before_t0"]["mean_predicted_iqr_pp"],
                      "expanded_q9_iqr_pp": ms["expanded_by_tau"]["8"]["mean_predicted_iqr_pp"]}

    d = ROOT / "outputs/sce_downstream_regression_20261027_v1"
    downstream_columns = {
        "predictions.csv": ["outcome", "horizon", "scope", "evaluation", "date", "target_date", "model", "n_train", "prediction", "actual", "error"],
        "model_metrics.csv": ["outcome", "horizon", "scope", "evaluation", "model", "n", "mae", "rmse", "bias", "n_train_min", "n_train_max"],
        "contrasts.csv": ["outcome", "horizon", "scope", "evaluation", "reference", "candidate", "n", "reference_rmse", "candidate_rmse", "rmse_improvement", "reference_mae", "candidate_mae", "mae_improvement", "reference_r2", "candidate_r2", "delta_r2"],
    }
    for filename, cols in downstream_columns.items():
        csv_write(target / ("downstream_" + filename), csv_rows(d / filename), cols)
    # Macro values only; no respondent or copyrighted article data.
    copied = [target / "weekly47_path.csv", target / "A82_micro_monthly_summaries.csv",
              *(target / ("downstream_" + n) for n in downstream_columns)]
    write(target / "extension_cases.json", {
        "schema": "sce_review_extension/v1", "cases": cases,
        "auxiliary_files_sha256": {p.name: digest(p) for p in copied},
        "micro_summary_expected": micro_expected,
        "downstream": {"prediction_rows": 4896, "metric_rows": 192, "contrast_rows": 408,
            "lineage": "Monthly A/B Core+Normal, not weekly. Current-vintage controls; upstream calibration was not nested at every origin. Retrospective use analysis, not a certified real-time forecast.",
            "replay_scope": "Recompute errors and paired contrasts from saved macro predictions, not refit regressions or recompute in-sample R2."},
        "source_files_sha256": _source_binding([micro / "summary.json", micro / "monthly_public.csv",
            w / "weekly_descriptive.csv", *(d / n for n in downstream_columns)]),
        "new_API_calls": 0, "private_record_data_included": False,
    })
    docs = Path(package) / "studies/sce_inflation_expectations/reports"
    for name in ("REVIEW_GUIDE.md", "LOCAL_DEMO_PLAN.md", "PAPER_INTEGRATION_PLAN.md", "PUBLIC_RELEASE_CHECKLIST.md"):
        shutil.copyfile(ROOT / "submission/package_templates" / name, docs / name)
    shutil.copyfile(ROOT / "docs/workstreams/20261026_downstream/regression_protocol.json", docs / "downstream_regression_protocol.json")
    protocols = []
    allowed = {"model", "route", "expected_provider", "temperature", "thinking", "response_format",
               "max_tokens", "generation_repeats", "planned_calls", "logical_positions",
               "eligible_person_months", "n_per_month", "n_per_week", "weekly_points", "retry_max",
               "provider_fallback", "entry_exit", "Normal", "strict_B_eligible"}
    for label, filename in (
        ("A_T0", "outputs/sce_full_a_t0_terminal_20261025_v1/protocol.json"),
        ("B_latest", "outputs/sce_recent_b_sampled_terminal_20261026_v1/package/protocol.json"),
        ("monthly_recursion", "outputs/sce_recent_b_recursion_terminal_20261026_v2/package/protocol.json"),
        ("weekly", "outputs/sce_weekly_terminal_20261027_v1/package/protocol.json")):
        path = ROOT / filename
        protocol = read(path)
        protocols.append({"configuration_id": label, "protocol_sha256": digest(path),
                          "configuration": {k: v for k, v in protocol.items() if k in allowed},
                          "seed_note": "No single inference seed. Sampling, donor and exposure randomness is frozen by input manifests/source; it does not make vendor generation byte-deterministic."})
    write(Path(package) / "studies/sce_inflation_expectations/simulation/latest_research_configurations.json", protocols)
    # Actual constants, not a made-up universal seed for stochastic API outputs.
    from ..experiments.full_a_personal_inputs import NEWS_SEED as a_news
    from ..experiments.recent_b_sampled_dates import DATE_SEED
    from ..experiments.recent_b_news_refresh import SEED as b_news
    from ..experiments.weekly_priors import SEED as weekly_prior
    write(Path(package) / "studies/sce_inflation_expectations/simulation/seed_policy.json", {
        "demo": 42, "A_personal_news": a_news, "B_response_dates": DATE_SEED,
        "B_news": b_news, "weekly_joint_prior": weekly_prior,
        "weekly_exposure_assignment": 20261026,
        "sampling_and_donor_rule_sources": ["experiments/full_a_personal_inputs.py", "experiments/recent_b_priors.py",
                                            "experiments/weekly_priors.py", "experiments/weekly_inputs.py"],
        "model_inference_seed": None,
        "limits": "These are declared deterministic assignment constants. Original sampled rosters and per-person seeds remain private inputs; cache replay does not resample them. Service-side inference is not byte-reproducible."})
    figures = docs / "figures"
    figures.mkdir()
    gallery = []
    for filename, source, caption in (
        ("A82_levels.png", ROOT / "docs/workstreams/20261026_full_a_refresh/results_v1/figures/a82_levels.png", "A82新旧原始模拟与公开全国参照，2021仍是主要难点"),
        ("A2021.png", ROOT / "docs/workstreams/20261026_full_a_refresh/results_v1/figures/a2021_levels_errors.png", "2021专项：改善与持续性差距同时披露"),
        ("weekly_path.png", w / "weekly_path.png", "周度原始与公开SCE：发布后校准先验，原始值未做输出层组合"),
        ("weekly_errors.png", w / "monthly_errors.png", "周度11月主评误差：保留9月漏报")):
        shutil.copyfile(source, figures / filename)
        gallery.append(f'<figure><img src="figures/{filename}" alt="{escape(caption)}"><figcaption>{escape(caption)}</figcaption></figure>')
    (docs / "index.html").write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>SCE研究包图表导览</title><style>body{max-width:1100px;margin:40px auto;font:18px/1.8 serif;padding:16px;color:#182333}img{max-width:100%}figure{margin:32px 0}figcaption{color:#4b5563}</style><h1>SCE研究包：图表与复现导览</h1><p>先从包根README执行 --mode all，生成本次核对结果。下图为已封存结果的可读快照，不代表现场重新生成模型答卷。</p><p><a href="REVIEW_GUIDE.md">研究导读</a> · <a href="LOCAL_DEMO_PLAN.md">本地视频计划</a> · <a href="PAPER_INTEGRATION_PLAN.md">论文规划</a></p>' + ''.join(gallery) + '<p>下游全部预测与408对照在 ../reproduction_data/；零API replay将重新核对误差，但不重新拟合回归。完整微观重现仍需受控资料。</p></html>')


def load_case(rows, methods):
    keys = [str(r["month"]).replace("-", "") for r in rows]
    if not keys or len(keys) != len(set(keys)) or keys != sorted(keys):
        raise ValueError("Unique chronological monthly rows required")
    for r in rows:
        for name in ["truth_pp", *methods]:
            if not math.isfinite(float(r[name])):
                raise ValueError("Nonfinite archived aggregate")
    return rows


def check_downstream(predictions, expected_metrics, contrasts):
    groups = defaultdict(list)
    for r in predictions:
        key = tuple(r[k] for k in ("outcome", "horizon", "scope", "evaluation", "model"))
        groups[key].append(r)
    results = {}
    for key, rows in groups.items():
        dates = [r["date"] for r in rows]
        if len(dates) != len(set(dates)):
            raise ValueError("Duplicate downstream prediction origin")
        for r in rows:
            if not math.isclose(float(r["error"]), float(r["prediction"]) - float(r["actual"]), abs_tol=1e-10):
                raise ValueError("Downstream stored error changed")
        results[key] = metrics([r["prediction"] for r in rows], [r["actual"] for r in rows])
    if len(results) != len(expected_metrics):
        raise ValueError("Missing downstream model groups")
    for e in expected_metrics:
        key = tuple(e[k] for k in ("outcome", "horizon", "scope", "evaluation", "model"))
        rows = groups[key]
        if len(rows) != int(e["n"]):
            raise ValueError("Downstream sample changed")
        assert_metrics(results[key], {k: e[k.removesuffix("_pp")] for k in METRICS})
    for c in contrasts:
        key = tuple(c[k] for k in ("outcome", "horizon", "scope", "evaluation"))
        ref, cand = key + (c["reference"],), key + (c["candidate"],)
        ref_rows = {r["date"]: float(r["actual"]) for r in groups[ref]}
        cand_rows = {r["date"]: float(r["actual"]) for r in groups[cand]}
        if ref_rows != cand_rows or len(ref_rows) != int(c["n"]):
            raise ValueError("Contrasts must use identical origin/target support")
        for metric in ("mae", "rmse"):
            a, b = results[ref][metric + "_pp"], results[cand][metric + "_pp"]
            if a == 0:
                raise ValueError("Relative improvement undefined at zero error")
            for value, column in ((a, "reference_" + metric), (b, "candidate_" + metric),
                                  ((a - b) / a, metric + "_improvement")):
                if not math.isclose(value, float(c[column]), rel_tol=1e-9, abs_tol=1e-10):
                    raise ValueError("Paired downstream contrast changed")
    credit = [c for c in contrasts if c["outcome"] == "REVOLSL" and c["scope"] == "A"
              and c["reference"] == "official_sce" and c["candidate"] in ("simulated_sce", "blended_sce")]
    return {"prediction_rows": len(predictions), "model_metrics_verified": len(results),
            "paired_contrasts_verified": len(contrasts), "credit_application": credit,
            "regressions_refitted": False, "in_sample_R2_recomputed": False}


def replay_extensions(evidence):
    """Called inside the existing offline network guard by study replay."""
    from .reproduce import checked_child
    evidence = Path(evidence)
    registry = read(evidence / "extension_cases.json")
    for name, expected in registry["auxiliary_files_sha256"].items():
        if digest(checked_child(evidence, name)) != expected:
            raise ValueError("Extension aggregate hash changed")
    cases = []
    for item in registry["cases"]:
        path = checked_child(evidence, item["file"])
        if digest(path) != item["sha256"]:
            raise ValueError("Extension case hash changed")
        rows = load_case(csv_rows(path), item["methods"])
        blend = item.get("fixed_blend")
        if blend:
            for r in rows:
                value = (1 - blend["weight"]) * float(r[blend["anchor"]]) + blend["weight"] * float(r[blend["raw"]])
                if not math.isclose(value, float(r[blend["combined"]]), abs_tol=1e-10):
                    raise ValueError("Fixed combination lineage mismatch")
        panels = []
        for panel in item["panels"]:
            selected = [r for r in rows if panel["from"] <= str(r["month"]).replace("-", "") <= panel["to"]]
            if len(selected) != panel["n"]:
                raise ValueError("Panel coverage changed")
            result = {m: metrics([r[m] for r in selected], [r["truth_pp"] for r in selected]) for m in item["methods"]}
            for m, actual in result.items():
                assert_metrics(actual, panel["expected"][m])
            panels.append({"name": panel["name"], "n": len(selected), "metrics": result})
        cases.append({"case_id": item["case_id"], "scope": item["scope"], "panels": panels})
    micro_rows = csv_rows(evidence / "A82_micro_monthly_summaries.csv")
    if len(micro_rows) != 82 or len({r["month"] for r in micro_rows}) != 82:
        raise ValueError("82 unique micro-summary months required")
    micro = {}
    for key, expected in registry["micro_summary_expected"].items():
        actual = sum(float(r[key]) for r in micro_rows) / len(micro_rows)
        if not math.isclose(actual, expected, abs_tol=1e-10):
            raise ValueError("Micro-summary mean changed")
        micro[key] = actual
    downstream = check_downstream(csv_rows(evidence / "downstream_predictions.csv"),
        csv_rows(evidence / "downstream_model_metrics.csv"), csv_rows(evidence / "downstream_contrasts.csv"))
    for key, value in (("prediction_rows", downstream["prediction_rows"]),
                       ("metric_rows", downstream["model_metrics_verified"]),
                       ("contrast_rows", downstream["paired_contrasts_verified"])):
        if value != registry["downstream"][key]:
            raise ValueError("Downstream declared coverage changed")
    return {"cases": cases, "cached_monthly_micro_summary_means": micro,
            "individual_W1_IQR_recomputed": False, "downstream": downstream,
            "downstream_lineage": registry["downstream"]["lineage"], "new_API_calls": 0,
            "new_density_fits": 0, "new_Normal_generation": 0, "parameters_refitted": False}


def extension_report(result):
    sections = ["<h2>最新主线与扩展：全国缓存复算</h2><p>下列任务分别评价。周度47点仅对应11份月度真值；原始模拟未做输出层组合。Normal不增加独立模型信息。</p>"]
    for case in result["cases"]:
        sections.append("<h3>" + escape(case["case_id"]) + "</h3><p>" + escape(case["scope"]) + "</p>")
        for panel in case["panels"]:
            sections.append(f"<p>{escape(panel['name'])} · {panel['n']}月</p><table><tr><th>方法</th><th>MAE</th><th>RMSE</th><th>偏差</th></tr>")
            for name, values in panel["metrics"].items():
                sections.append(f"<tr><td>{escape(name)}</td><td>{values['mae_pp']:.6f}</td><td>{values['rmse_pp']:.6f}</td><td>{values['bias_pp']:.6f}</td></tr>")
            sections.append("</table>")
    sections.append("<h2>下游用途：循环信贷线索</h2><p>" + escape(result["downstream_lineage"]) + "</p>")
    for candidate, label in (("simulated_sce", "原始月度模拟"), ("blended_sce", "月度组合")):
        rows = sorted([r for r in result["downstream"]["credit_application"] if r["candidate"] == candidate], key=lambda r: int(r["horizon"]))
        sections.append("<p>" + label + "相对官方SCE，未来1/2/3个月RMSE改善：" + " / ".join(f"{float(r['rmse_improvement']):+.2%}" for r in rows) + "。其他结局不稳定，简单基线仍强。</p>")
    sections.append("<p>已核对4,896个预测、192组误差和408组配对对照。没有重新拟合回归；样本内R²未复算。W1/IQR仅重算已保存月摘要的平均数，没有重新读取真人答卷或拟合个人密度。</p>")
    return "".join(sections)
