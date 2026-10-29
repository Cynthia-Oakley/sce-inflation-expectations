"""Bind actually rebuilt P/E/prompt stages to the fresh API execution cache.

The original exported input cache is preserved. Rebuilt messages must match its
registered exact-message hashes before they can replace that cache. This avoids
a prepare command that computes inputs and then silently ignores its outputs.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import time

from .portable_run import read, write, sha, checked_wave, load_index


def message_hash(messages):
    return hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()


def adopt(workspace, preparation):
    workspace, preparation = Path(workspace).resolve(), Path(preparation).resolve()
    report = read(preparation / "preparation_index.json")
    frozen = workspace / "portable/runtime"
    target = preparation / "runtime_from_rebuilt_inputs"
    if target.exists():
        saved = target / "adoption.json"
        if saved.exists():
            previous = read(saved)
            if (previous.get("preparation_index_sha256") == sha(preparation / "preparation_index.json")
                    and previous["index_sha256"] == sha(target / "index.json")):
                write(workspace / "portable/active_runtime.json", previous)
                return previous
        # A failed adoption never becomes active. Retain it and use a fresh
        # cache if the preparation/index has been corrected after inspection.
        target = target.with_name(target.name + "_" + str(time.time_ns()))
    index = load_index(frozen)
    fresh = report["fresh_inputs"]
    def path(name):
        value = fresh.get(name)
        if not value:
            return None
        # Preparation metadata can provide both relative/absolute forms.
        if isinstance(value, dict):
            value = value.get("relative") or value.get("path") or value.get("absolute")
        p = Path(value)
        p = p.resolve() if p.is_absolute() else (workspace / p).resolve()
        if not p.is_relative_to(workspace):
            raise ValueError("Rebuilt source path escaped reviewer workspace")
        return p
    a, assembly, b, weekly = (path(k) for k in ("a_personal_cutoff", "a_assembly", "b_prompts", "weekly_inputs"))
    shutil.copytree(frozen, target)
    adopted = {}
    for task, items in index["waves"].items():
        count = 0
        for item in items:
            old = checked_wave(frozen, item)
            new = deepcopy(old); period = item["period"]
            if task == "A" and a:
                if not assembly:
                    raise ValueError("Fresh A assembly is required with A final inputs")
                prompts = read(a / period / "prompts.json")["rows"]
                contexts = read(a / period / "contexts_private.json")
                weights = read(a / period / "weights_private.json")
                states = read(assembly / "prompts" / period / "initial_states_private.json")
                if set(prompts) != set(old["rows"]):
                    raise ValueError("Rebuilt A roster differs from original")
                for aid, row in new["rows"].items():
                    row.update(messages=prompts[aid]["messages"], initial=states[aid],
                        cutoff=contexts[aid]["as_of"], weight=weights[aid]["analysis_weight"])
                    if message_hash(row["messages"]) != message_hash(old["rows"][aid]["messages"]):
                        raise ValueError(f"Rebuilt A prompt differs: {period}/{aid}")
                count += len(prompts)
            elif task == "B" and b:
                from ..experiments.recent_b_sampled_dates import render_B_messages
                templates = read(b / period / "templates_private.json")
                contexts = read(b / period / "timing_context_private.json")
                states = read(b / period / "initial_states_private.json")
                if set(templates) != set(old["rows"]):
                    raise ValueError("Rebuilt B roster differs from original")
                for aid, row in new["rows"].items():
                    row.update(template=templates[aid], initial=states[aid], context=contexts[aid], cutoff=contexts[aid]["as_of"])
                    before = render_B_messages(old["rows"][aid]["template"], old["rows"][aid]["initial"], period, old["rows"][aid]["context"])
                    after = render_B_messages(row["template"], row["initial"], period, row["context"])
                    if message_hash(before) != message_hash(after):
                        raise ValueError(f"Rebuilt B prompt differs: {period}/{aid}")
                count += len(templates)
            elif task == "monthly" and b and period == "202511":
                # The fixed monthly root is precisely the new B November input.
                templates = read(b / period / "templates_private.json")
                contexts = read(b / period / "timing_context_private.json")
                states = read(b / period / "initial_states_private.json")
                for aid, row in new["rows"].items():
                    row.update(template=templates[aid], initial=states[aid], context=contexts[aid], cutoff=contexts[aid]["as_of"])
                count += len(new["rows"])
            elif task == "weekly" and weekly:
                plans = {p["step_key"]: p for p in read(weekly / "weekly_plan.json")}
                point = plans[period]
                templates = read(weekly / "weeks" / period / point["month"] / "templates_private.json")
                priors = read(weekly / "priors/cycles_private.json")[point["cycle_key"]]["states"]
                if set(templates) != set(old["rows"]):
                    raise ValueError("Rebuilt weekly cohort differs from original")
                new["point"] = point
                for aid, row in new["rows"].items():
                    row.update(template=templates[aid], prior=priors[aid], cutoff=point["cutoff"])
                    if row["template"] != old["rows"][aid]["template"] or row["prior"] != old["rows"][aid]["prior"]:
                        raise ValueError(f"Rebuilt weekly structural input differs: {period}/{aid}")
                count += len(templates)
            if new != old:
                write(target / item["file"], new)
            index["files_sha256"][item["file"]] = sha(target / item["file"])
        adopted[task] = count
    index["preparation_provenance"] = dict(index_sha256=sha(preparation / "preparation_index.json"),
        fresh_input_positions_adopted=adopted,
        monthly_later_context="Original fixed-cohort P/E templates supplied as exact prepared source snapshots; every simulated belief state is newly rendered")
    write(target / "index.json", index)
    marker = dict(runtime=str(target.relative_to(workspace)), index_sha256=sha(target / "index.json"),
        preparation=str(preparation.relative_to(workspace)), positions=adopted,
        preparation_index_sha256=sha(preparation / "preparation_index.json"), new_API_calls=0)
    write(target / "adoption.json", marker)
    write(workspace / "portable/active_runtime.json", marker)
    return marker


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--preparation", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(adopt(a.workspace, a.preparation), ensure_ascii=False, indent=2))
