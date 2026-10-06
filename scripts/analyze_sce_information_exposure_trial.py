#!/usr/bin/env python3
"""Evaluate completed E/P routing LLM trial; no network, no new simulation."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid
import duckdb
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.household_state_analysis import density
from studies.sce_inflation_expectations.information_exposure import ARMS
from studies.sce_inflation_expectations.information_exposure_analysis import paired_metrics


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trial", type=Path, required=True)
    ap.add_argument("--truth", type=Path, default=ROOT / "data/evaluation/dev_full_20261005T045330Z_947a818f/truth.json")
    a = ap.parse_args()
    folder = a.trial.resolve()
    plan_path = folder / "trial_manifest.json"
    plan = json.loads(plan_path.read_text())
    if plan["status"] != "completed" or any(r["status"] != "completed" for r in plan["records"]):
        ap.error("requires completed genuine LLM trial")
    truth = {(str(r["date"]), f"sce_u{int(r['userid'])}"): r for r in json.loads(a.truth.read_text())["per_person"]}
    result = {"trial_id": plan["trial_id"], "months": {},
              "sources": {str(plan_path): sha(plan_path), str(a.truth): sha(a.truth), str(Path(__file__)): sha(__file__)}}
    rows = []
    for month in plan["metadata"]:
        bundle = json.loads((folder / month / "exposure_matched.json").read_text())
        ids = set(bundle["rows"])
        by_arm = {}
        for arm in ARMS:
            cells = [r for r in plan["records"] if r["month"] == month and r["arm"] == arm]
            if len(cells) != 1:
                raise ValueError("missing or duplicate trial cell")
            run_dir = Path(cells[0]["output_dir"])
            manifest = run_dir / "run_manifest.json"
            run = json.loads(manifest.read_text())
            if run["run_id"] != cells[0]["run_id"] or run["llm_kind"] != "openai" or run["n_agents"] != len(ids):
                raise ValueError("run identity/size mismatch")
            for name, h in run["effective_artifact_sha256"].items():
                if sha(run_dir / name) != h:
                    raise ValueError("changed run inputs")
            with duckdb.connect(run["store_path"], read_only=True) as db:
                answers = db.execute("SELECT agent_id, action_payload FROM panel WHERE step=1 ORDER BY agent_id").fetchall()
            if len(answers) != len(ids) or {aid for aid, _ in answers} != ids:
                raise ValueError("answer coverage mismatch")
            by_arm[arm] = {aid: json.loads(p) if isinstance(p, str) else p for aid, p in answers}
            result["sources"].update({str(manifest): sha(manifest), run["store_path"]: sha(run["store_path"])})
        q9rows, q8rows, statuses = [], [], Counter()
        for aid in sorted(ids):
            real = truth[(month, aid)]
            fits = {"real": density([real.get(f"Q9_bin{i}") for i in range(1, 11)]),
                    **{arm: density([by_arm[arm][aid].get(f"q9_bin{i}") for i in range(1, 11)]) for arm in ARMS}}
            statuses.update(f"{arm}:{f['status']}" for arm, f in fits.items())
            base = {"month": month, "agent_id": aid, "channel": bundle["rows"][aid]["intended_channel"]}
            q9rows.append({**base, **{arm: f["mean"] for arm, f in fits.items()}})
            rawpoint = real.get("Q8v2part2")
            q8rows.append({**base, "real": rawpoint if type(rawpoint) in (int, float) else None,
                          **{arm: by_arm[arm][aid]["point_pct"] for arm in ARMS}})
        result["months"][month] = {"Q9": paired_metrics(q9rows), "Q8_secondary": paired_metrics(q8rows),
                                    "fitting_status_counts": dict(statuses)}
        rows.extend({**r, "Q8": q8} for r, q8 in zip(q9rows, q8rows))
    result["both_months_screen_passed"] = all(m["Q9"]["development_screen_passed"] for m in result["months"].values())
    result["limitations"] = ["Development months only; not a blind test", "16 per channel, no power guarantee",
        "CE proxy not observed household spending or attention", "Single generation and permutation; LLM noise not separately estimated",
        "No news in any arm; shared-vs-limited is a joint information intervention", "Same approximate Q9 scorer on both sides",
        "Empirical distribution and individual uncertainty are different objects", "Bootstrap conditions on this selected sample; no national significance claim"]
    out = ROOT / "outputs" / ("sce_exposure_analysis_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    out.mkdir(exist_ok=False)
    (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    (out / "paired_evaluation.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in rows))
    print("ANALYSIS_DIR=" + str(out))


if __name__ == "__main__":
    main()
