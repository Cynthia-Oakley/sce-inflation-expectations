"""Export the exact existing Agent public E for baselines; no downloads or LLM."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studies/sce_inflation_expectations"))
from evaluation.shared_environment import extract_shared_rows


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--environment", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path)
    args = ap.parse_args()
    source = args.environment.resolve()
    rows = extract_shared_rows(json.loads(source.read_text()))
    out = args.output_dir or ROOT / "outputs" / ("sce_shared_environment_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    target = out / "shared_environment.jsonl"
    target.write_text("".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in rows))
    columns = sorted(set().union(*(r["numeric_features"] for r in rows)))
    report = {"run_id": out.name, "input_environment": str(source), "input_sha256": sha(source),
              "output_sha256": sha(target), "model_api_calls": 0, "network_calls": 0,
              "numeric_column_count": len(columns), "numeric_columns": columns,
              "months": [{"target_month": r["target_month"], "as_of": r["as_of"], "signals": len(r["signals"]),
                          "news": len(r["news"]), "missing_numeric_columns": sorted(set(columns) - set(r["numeric_features"])),
                          "evidence_uncertainties": r["evidence_uncertainties"]} for r in rows],
              "code_sha256": {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), ROOT / "studies/sce_inflation_expectations/evaluation/shared_environment.py"]},
              "status": "shared_input_export_only_not_trained_baseline", "research_line": "A_retrospective_current_CPI_release_day",
              "limitations": ["Metadata timestamp checks do not independently verify gasoline vintage or inferred release day",
                              "No historical SCE, population features or target outcomes have been added",
                              "News vocabulary, scaling, imputation and hyperparameters must be fitted only on admissible training periods"]}
    (out / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(out)


if __name__ == "__main__":
    main()
