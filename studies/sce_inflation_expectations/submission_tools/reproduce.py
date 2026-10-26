"""Portable offline study smoke run and real aggregate-result recomputation.

These two modes are deliberately different. Scripted Core trajectories are
engineering fixtures; replay re-scores the archived monthly real-LLM aggregates.
It does not claim to regenerate private micro trajectories or empirical W1.
"""
import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
from html import escape
import json
import math
from pathlib import Path
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies/sce_inflation_expectations"


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_child(root, name):
    root = Path(root).resolve(); path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Missing or unsafe declared package file: " + str(name))
    return path


def verify_package(root=ROOT):
    manifest = read(Path(root) / "PACKAGE_MANIFEST.json")
    for name, digest in manifest["files_sha256"].items():
        if sha(checked_child(root, name)) != digest:
            raise ValueError("Package hash mismatch: " + name)
    return {"files_verified": len(manifest["files_sha256"]), "package_status": manifest["status"]}


@contextmanager
def no_network():
    """Fail closed if an offline Python path unexpectedly tries a connection."""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create = socket.create_connection
    def blocked(*args, **kwargs):
        raise RuntimeError("Network is disabled in dry-run/replay modes")
    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    socket.create_connection = blocked
    try:
        yield
    finally:
        socket.socket.connect = original_connect
        socket.socket.connect_ex = original_connect_ex
        socket.create_connection = original_create


def dry_run(out, *, study=STUDY):
    from socioverse.engine import build_simulator
    from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig
    import duckdb
    import studies.sce_inflation_expectations.model  # registers the real four interfaces
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    pop = PopulationBundle.model_validate(read(study / "population/population_demo.json"))
    env = EnvironmentBundle.model_validate(read(study / "environment/environment_demo.json"))
    raw = read(study / "simulation/simulation_demo.json")
    if (raw["decision_args"].get("llm_kind") != "scripted"
            or raw["decision_ref"] != "sce_inflation_expectations.decision"
            or raw["collector_ref"] != "sce_inflation_expectations.collector"):
        raise ValueError("Offline mode accepts only the declared scripted SCE providers")
    sim = SimulationConfig.model_validate(raw)
    if sim.n_steps != len(env.provider_args["targets"]):
        raise ValueError("Demo target/step mismatch")
    env.provider_args["persona_by_id"] = {p.agent_id: p.attributes for p in pop.personas}
    env.provider_args["audit_dir"] = str(out)
    env.provider_args["run_id"] = "submission-offline-scripted"
    simulator = build_simulator(env_bundle=env, pop_bundle=pop, sim_config=sim,
                                store_path=out / "study.duckdb")
    history = simulator.run()
    history_data = history.model_dump(mode="json")
    with duckdb.connect(str(out / "study.duckdb"), read_only=True) as con:
        panel_n = con.execute("select count(*) from panel").fetchone()[0]
        actions_n = con.execute("select count(*) from panel where step > 0").fetchone()[0]
    if panel_n != len(pop.personas) * (sim.n_steps + 1) or actions_n != len(pop.personas) * sim.n_steps:
        raise ValueError("Official Core did not produce the full demo trajectory")
    result = {"status": "passed_official_Core_scripted_engineering_only", "seed": sim.seed,
              "agents": len(pop.personas), "steps": sim.n_steps, "panel_rows": panel_n,
              "scripted_decisions": actions_n, "actual_LLM_calls": 0, "empirical_accuracy_result": False}
    write(out / "metrics_history.json", history_data)
    write(out / "receipt.json", result)
    return result


def normalized_month(value):
    text = str(value).replace("-", "")
    if len(text) != 6 or not text.isdigit() or not 1 <= int(text[4:]) <= 12:
        raise ValueError("Invalid monthly aggregate key")
    return int(text)


def load_monthly(path):
    with Path(path).open(newline="") as f:
        rows = list(csv.DictReader(f))
    result = []
    for row in rows:
        parsed = {"month": normalized_month(row["month"]),
                  **{k: float(row[k]) for k in ("sim_pp", "anchor_pp", "truth_pp")}}
        if not all(math.isfinite(parsed[k]) for k in ("sim_pp", "anchor_pp", "truth_pp")):
            raise ValueError("Missing monthly predictions cannot be silently dropped")
        result.append(parsed)
    if not result or len({r["month"] for r in result}) != len(result):
        raise ValueError("Nonempty, unique monthly aggregates required")
    return sorted(result, key=lambda row: row["month"])


def replay(out, *, study=STUDY):
    from ..evaluation.metrics import headline_errors
    from ..evaluation.aggregate_blend import fit_weight, evaluate
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    evidence = study / "reproduction_data"
    registry = read(evidence / "aggregate_cases.json")
    cases = []
    for item in registry["cases"]:
        path = checked_child(evidence, item["monthly_file"])
        if sha(path) != item["monthly_sha256"]:
            raise ValueError("Frozen monthly input changed")
        rows = load_monthly(path)
        if (len(rows) != item["n_months"] or rows[0]["month"] != item["first_month"]
                or rows[-1]["month"] != item["last_month"]):
            raise ValueError("Archived monthly coverage differs")
        truth = [r["truth_pp"] for r in rows]
        values = {"case_id": item["case_id"], "scope": item["scope"],
                  "model": headline_errors([r["sim_pp"] for r in rows], truth),
                  "persistence": headline_errors([r["anchor_pp"] for r in rows], truth)}
        for arm in ("model", "persistence"):
            for metric in ("mae_pp", "rmse_pp", "bias_pp"):
                if abs(values[arm][metric] - item["expected"][arm][metric]) > 1e-10:
                    raise ValueError(f"Frozen macro result mismatch: {item['case_id']} / {arm} / {metric}")
        if item.get("chronological_combinations"):
            early = [r for r in rows if r["month"] <= 202212]
            later = [r for r in rows if r["month"] >= 202301]
            if len(early) != 48 or len(later) != 34:
                raise ValueError("The predeclared 48/34 split changed")
            values["chronological_combinations"] = {}
            for loss in ("mae", "mse"):
                alpha = fit_weight([r["truth_pp"] for r in early], [r["anchor_pp"] for r in early],
                                   [r["sim_pp"] for r in early], loss)
                block = {"simulation_weight": alpha, "history_weight": 1 - alpha,
                         "fit_n_months": 48, "evaluation_n_months": 34, "evaluation": evaluate(later, alpha)}
                reference = item["chronological_combinations"][loss]
                if abs(alpha - reference["simulation_weight"]) > 1e-10:
                    raise ValueError("Frozen early-period combination weight changed")
                for metric in ("mae_pp", "rmse_pp", "bias_pp"):
                    if abs(block["evaluation"][metric] - reference["evaluation"][metric]) > 1e-10:
                        raise ValueError("Frozen later-period combination error changed")
                values["chronological_combinations"][loss] = block
        if item.get("expected_yearly"):
            values["yearly"] = {}
            for year, expected in item["expected_yearly"].items():
                group = [r for r in rows if str(r["month"]).startswith(year)]
                if not group:
                    raise ValueError("Declared year missing from monthly cache")
                block = {arm: headline_errors([r[key] for r in group], [r["truth_pp"] for r in group])
                         for arm, key in (("model", "sim_pp"), ("persistence", "anchor_pp"))}
                for arm in ("model", "persistence"):
                    for metric in ("mae_pp", "rmse_pp", "bias_pp"):
                        if abs(block[arm][metric] - expected[arm][metric]) > 1e-10:
                            raise ValueError("Frozen yearly aggregate error changed")
                values["yearly"][year] = block
        cases.append(values)
    result = {"status": "matched_archived_national_aggregate_results", "cases": cases,
              "actual_LLM_calls": 0, "new_Q9_density_fits": 0,
              "micro_trajectories_recomputed": False,
              "limits": ["Each included completed A/B version is evaluated separately as listed in aggregate_cases.json.",
                         "Recomputes macro errors and early/late weights from archived real aggregate predictions.",
                         "Does not regenerate individuals, recompute empirical W1/IQR, or prove forecast generalization."]}
    write(out / "summary.json", result)
    return result


def generate(workspace, prepared_run, *, confirm=False, executor="full-a"):
    """Delegate only a real frozen, data-complete workspace after explicit consent."""
    if not confirm or workspace is None or prepared_run is None:
        raise ValueError("Real generation requires --source-workspace, --prepared-run and --confirm-paid")
    workspace = Path(workspace).resolve()
    run = (workspace / prepared_run).resolve()
    if not run.is_relative_to(workspace / "outputs") or not run.is_dir():
        raise ValueError("An existing frozen run under the declared workspace outputs/ is required")
    entries = {"full-a": "scripts/run_sce_full_a_personal.py", "recent-b": "scripts/run_sce_recent_b.py"}
    if executor not in entries:
        raise ValueError("Only declared frozen A/B executors are accepted")
    entry = checked_child(workspace, entries[executor])
    # Existing executor owns input hashes, per-batch authorization, budget,
    # archival, retries and duplicate-launch protection. Never bypass its guard.
    subprocess.run([sys.executable, str(entry), "review", "--run-dir", str(run)], cwd=workspace, check=True)
    subprocess.run([sys.executable, str(entry), "run", "--run-dir", str(run),
                    "--confirm-scope-and-budget"], cwd=workspace, check=True)
    return {"status": "delegated_to_frozen_external_workspace", "new_calls_from_this_wrapper": "see executor ledger"}


def make_report(out, result):
    sections = ["<h1>SCE研究包：离线复现记录</h1>",
                "<p>确定性干跑检验工程链路；缓存重算检验已归档宏观数字。两者均不重新询问LLM。</p>"]
    if "dry_run" in result:
        r = result["dry_run"]
        sections.append(f"<h2>官方Core干跑</h2><p>{r['agents']}个合成代理，{r['steps']}步，"
                        f"{r['scripted_decisions']}次规则决策，{r['panel_rows']}条面板记录。不是实证拟合成绩。</p>")
    if "replay" in result:
        sections.append("<h2>真实月度聚合的重算核对</h2><p>A与B分别评价，不合并计算93个月总误差。单位：百分点。</p>")
        for case in result["replay"]["cases"]:
            sections.append(f"<h3>{escape(case['case_id'])}</h3><p>{escape(case['scope'])}</p>"
                "<table><tr><th>预测方式</th><th>MAE</th><th>RMSE</th><th>平均偏差</th></tr>" +
                "".join(f"<tr><td>{name}</td><td>{case[key]['mae_pp']:.6f}</td>"
                        f"<td>{case[key]['rmse_pp']:.6f}</td><td>{case[key]['bias_pp']:.6f}</td></tr>"
                        for key, name in (("model", "原始模拟"), ("persistence", "已公开历史基线"))) + "</table>")
        sections.append("<p>完整微观Q9评分、W1和人群分布复算需要受控数据与逐人缓存，本包此模式不声称已复算这些结果。</p>")
    (out / "index.html").write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<title>SCE研究包离线复现</title><style>body{max-width:1000px;margin:30px auto;padding:20px;'
        'font:17px/1.8 "Times New Roman","Kaiti SC",serif;color:#242424}table{border-collapse:collapse;'
        'width:100%;margin-bottom:24px}td,th{padding:8px 14px;border-bottom:1px solid #ccc;text-align:left}'
        'th{background:#eee}</style>' + "".join(sections) + '</html>')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("all", "dry-run", "replay", "verify", "generate"), default="all")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--source-workspace", type=Path)
    parser.add_argument("--prepared-run")
    parser.add_argument("--executor", choices=("full-a", "recent-b"), default="full-a")
    parser.add_argument("--confirm-paid", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "generate":
        result = generate(args.source_workspace, args.prepared_run, confirm=args.confirm_paid, executor=args.executor)
    else:
        verification = verify_package()
        if args.mode == "verify":
            print(json.dumps(verification, ensure_ascii=False)); return verification
        out = (args.out or ROOT / "outputs" / ("reproduction_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ"))).resolve()
        out.mkdir(parents=True, exist_ok=False)
        with no_network():
            result = {"mode": args.mode, "verification": verification, "actual_LLM_calls": 0}
            if args.mode in ("all", "dry-run"):
                result["dry_run"] = dry_run(out / "dry_run")
            if args.mode in ("all", "replay"):
                result["replay"] = replay(out / "replay")
        result["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        write(out / "receipt.json", result)
        make_report(out, result)
        print("Results: " + str(out))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result
