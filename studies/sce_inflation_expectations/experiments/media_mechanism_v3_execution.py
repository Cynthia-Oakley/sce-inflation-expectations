"""Resume only never-started V3 jobs; never retry partial or failed runs."""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys

from .frozen_batch import ROOT, authorize, dump, read_json, verify


def missing_job_indices(folder, root=ROOT):
    folder = Path(folder)
    root = Path(root)
    pending = []
    for index, job in enumerate(read_json(folder / "manifest.json")["jobs"]):
        audit = root / "outputs/local_runs" / job["run_id"]
        if not audit.exists():
            pending.append(index)
            continue
        receipt_path = audit / "run_manifest.json"
        receipt = read_json(receipt_path) if receipt_path.exists() else {}
        if receipt.get("status") != "completed":
            raise ValueError("partial or unknown existing run requires manual reconciliation: " + job["run_id"])
    return pending


def resume_missing(folder, workers=4):
    folder = Path(folder).resolve()
    manifest, protocol = verify(folder)
    authorize(folder, manifest, protocol)
    maximum = protocol.get("max_workers", 4)
    if type(workers) is not int or not 1 <= workers <= maximum:
        raise ValueError("workers exceed registered maximum")
    pending = missing_job_indices(folder)
    if not pending:
        return {"status": "all_jobs_already_complete", "new_api_calls": 0}
    subprocess.run([sys.executable, str(ROOT / "scripts/export_study_runtime.py")], cwd=ROOT,
                   capture_output=True, text=True, check=True)
    results = []
    failed = False

    def one(index):
        job = manifest["jobs"][index]
        command = [sys.executable, str(ROOT / "scripts/run_sce_media_mechanism_v3.py"), "worker",
                   "--folder", str(folder), "--job-index", str(index)]
        with (folder / (job["run_id"] + "-resume.log")).open("x") as log:
            rc = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                env=dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")).returncode
        return {"job_index": index, "run_id": job["run_id"], "exit_code": rc}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        active = {}
        next_index = 0
        while next_index < len(pending) and len(active) < workers:
            index = pending[next_index]
            active[pool.submit(one, index)] = index
            next_index += 1
        while active:
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                active.pop(future)
                result = future.result()
                results.append(result)
                failed |= bool(result["exit_code"])
            dump(folder / "resume_dispatch.json", results)
            while not failed and next_index < len(pending) and len(active) < workers:
                index = pending[next_index]
                active[pool.submit(one, index)] = index
                next_index += 1
    if failed:
        raise RuntimeError("resume stopped; completed runs retained, partial runs not retried")
    return {"status": "resume_completed", "jobs": len(results), "finished_at_utc": datetime.now(timezone.utc).isoformat()}
