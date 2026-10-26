#!/usr/bin/env python3
"""Run, evaluate and compare the frozen media-mechanism V3 package."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent / "socioverse2_repo"))
import studies

studies.__path__ = [str(ROOT / "studies"), *studies.__path__]
from studies.sce_inflation_expectations.experiments.frozen_batch import dispatch, worker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["attach-evaluation", "dry-run", "run", "resume", "worker"])
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--job-index", type=int)
    parser.add_argument("--scripted", action="store_true")
    args = parser.parse_args()
    if args.action == "attach-evaluation":
        from studies.sce_inflation_expectations.evaluation.media_mechanism_v3 import attach_evaluation
        protocol = json.loads((args.folder / "protocol.json").read_text())
        result = attach_evaluation(args.folder, ROOT / protocol["a82_reference"])
        print(json.dumps(result))
        return
    if args.action == "worker":
        if args.job_index is None:
            parser.error("worker requires --job-index")
        worker(args.folder, args.job_index, args.scripted)
        return
    if args.action == "resume":
        from studies.sce_inflation_expectations.experiments.media_mechanism_v3_execution import resume_missing
        print(json.dumps(resume_missing(args.folder, args.workers)))
        return
    dispatch(args.folder, args.action == "dry-run", args.workers)


if __name__ == "__main__":
    main()
