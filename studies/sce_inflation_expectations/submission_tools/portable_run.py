"""Portable own-key batch execution of the four original final experiments.

Research rendering, state transitions, normalization and fault-tolerant queues
are imported from the original source workspace. This module only connects
their inputs/outputs and supplies a reviewer-owned credential and budget.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
MODEL = "deepseek/deepseek-v3.2"
DESTINATION = "https://openrouter.ai/api/v1"
ROUTE = "siliconflow/fp8"
TASKS = ("A", "B", "monthly", "weekly")
MONTHS = [f"{y}{m:02}" for y in range(2019, 2026) for m in range(1, 13)
          if f"{y}{m:02}" <= "202510"]
BMONTHS = [f"{y}{m:02}" for y in (2025, 2026) for m in range(1, 13)
           if "202511" <= f"{y}{m:02}" <= "202609"]


def read(path):
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
    if path.suffix == ".gz":
        with path.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as f:
            f.write(text.encode())
    else:
        tmp = path.with_name(path.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            f.write(text); f.flush(); os.fsync(f.fileno())
        tmp.replace(path)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(2**20), b""):
            h.update(chunk)
    return h.hexdigest()


def jsonl(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def export(out, root=ROOT):
    """Export input-only dynamic templates; isolate scoring materials by role."""
    root, out = Path(root).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    micro = root / "outputs/sce_micro_reproduction_20261029_v3"
    codes = read(micro / "private_key_map_NOT_FOR_PACKAGE.json")
    reverse = {task: {original: alias for alias, original in codes.items()
                     if re.fullmatch(re.escape(task) + r"_\d+", alias)} for task in TASKS}
    weights = {(r["run"], r["period"], r["household"]): r["analysis_weight"]
               for r in jsonl(micro / "data/effective_answers.jsonl.gz") if r["run"] in TASKS}
    files, waves = {}, defaultdict(list)
    sources = {}

    def load(relative):
        p = root / relative
        sources[str(relative)] = sha(p)
        return read(p)

    def emit(task, period, rows, **extra):
        for aid, row in rows.items():
            alias = reverse[task][aid]
            row.update(agent_id=aid, household=alias,
                       weight=weights[task, period, alias])
        relative = f"inputs/{task}/{period}.json.gz"
        write(out / relative, dict(task=task, period=period, rows=rows, **extra))
        files[relative] = sha(out / relative)
        waves[task].append(dict(period=period, file=relative, people=len(rows)))

    a = "outputs/sce_full_a_personal_inputs_20261025_v1"
    a0 = "outputs/sce_monthly_fine_full_assembly_20261023_v3/prompts"
    for month in MONTHS:
        prompts = load(f"{a}/{month}/prompts.json")["rows"]
        context = load(f"{a}/{month}/contexts_private.json")
        initial = load(f"{a0}/{month}/initial_states_private.json")
        emit("A", month, {aid: dict(messages=r["messages"], initial=initial[aid],
              cutoff=context[aid]["as_of"]) for aid, r in prompts.items()})
    b = "outputs/sce_recent_b_sampled_dates_complete_20261026_v1/prompts"
    m = "outputs/sce_recent_b_recursion_terminal_20261026_v1/PE"
    for month in BMONTHS:
        templates = load(f"{b}/{month}/templates_private.json")
        initial = load(f"{b}/{month}/initial_states_private.json")
        context = load(f"{b}/{month}/timing_context_private.json")
        emit("B", month, {aid: dict(template=t, initial=initial[aid], context=context[aid],
              cutoff=context[aid]["as_of"]) for aid, t in templates.items()})
        # November is freshly generated from the identical B input, rather than
        # copying the author's archived simulated root into a fresh trajectory.
        mt = templates if month == BMONTHS[0] else load(f"{m}/{month}/templates_private.json")
        mc = context if month == BMONTHS[0] else load(f"{m}/{month}/timing_context_private.json")
        emit("monthly", month, {aid: dict(template=t, context=mc[aid], cutoff=mc[aid]["as_of"],
              **(dict(initial=initial[aid]) if month == BMONTHS[0] else {})) for aid, t in mt.items()})
    w = "outputs/sce_weekly_inputs_20261027_v2"
    plan = load(f"{w}/weekly_plan.json")
    cycles = load(f"{w}/priors/cycles_private.json")
    for point in plan:
        key, month = point["step_key"], point["month"]
        templates = load(f"{w}/weeks/{key}/{month}/templates_private.json")
        priors = cycles[point["cycle_key"]]["states"]
        emit("weekly", key, {aid: dict(template=t, prior=priors[aid], cutoff=point["cutoff"])
              for aid, t in templates.items()}, point=point)
    # At-rest evaluation targets and archived numerical caches are never opened
    # by generation. The separate evaluator reads only after checkpoints seal.
    import shutil
    evaluation = out / "evaluation"; evaluation.mkdir()
    for name in ("expected.json", "A_paired_cases.jsonl.gz", "A_full_wave_targets.jsonl.gz",
                 "density_cache.jsonl.gz", "normal_mechanism.jsonl.gz"):
        shutil.copyfile(micro / "data" / name, evaluation / name)
        files["evaluation/" + name] = sha(evaluation / name)
    write(evaluation / "code_map.json", codes)
    files["evaluation/code_map.json"] = sha(evaluation / "code_map.json")
    index = dict(schema="sce_portable_runtime/v1", waves=dict(waves),
        files_sha256=files, original_sources_sha256=sources,
        generation_reads="inputs/ only; no evaluation/ parsing in sender or state renderer",
        monthly_root="fresh November B request, or exact newly generated B November root in same run",
        model=MODEL, route=ROUTE, destination=DESTINATION, expected_provider="SiliconFlow",
        temperature=.5, max_tokens=1024, response_format="json_object", thinking="disabled",
        prior_strength=8, new_API_calls=0)
    write(out / "index.json", index)
    return index


def protocol(budget):
    return dict(model=MODEL, destination=DESTINATION, route=ROUTE, expected_provider="SiliconFlow",
        temperature=.5, max_tokens=1024, budget_cap_usd=budget,
        price_input_per_mtok=.259, price_output_per_mtok=.8, timeout_s=120,
        request_extra_body={"provider": {"order": [ROUTE], "allow_fallbacks": False,
            "require_parameters": True, "max_price": {"prompt": .259, "completion": .8}},
            "reasoning": {"enabled": False}})


def make_sender(p):
    """Identical Chat Completions body; reviewer environment Key only."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ValueError("Set your own OPENROUTER_API_KEY in this Terminal session")
    from openai import OpenAI
    import httpx
    local = threading.local()

    def send(messages):
        if not hasattr(local, "client"):
            local.client = OpenAI(base_url=DESTINATION, api_key=key, max_retries=0,
                http_client=httpx.Client(timeout=p["timeout_s"], follow_redirects=False))
        started = time.monotonic()
        r = local.client.chat.completions.create(model=MODEL, messages=messages,
            temperature=.5, max_tokens=1024, response_format={"type": "json_object"},
            extra_body=p["request_extra_body"])
        c = r.choices[0] if r.choices else None
        usage = getattr(r, "usage", None)
        return dict(raw_response_text=(c.message.content or "") if c else "",
            finish_reason=c.finish_reason if c else None,
            returned_model=r.model, returned_provider=getattr(r, "provider", None),
            request_id=r.id, system_fingerprint=getattr(r, "system_fingerprint", None),
            latency_ms=(time.monotonic() - started) * 1000,
            usage=usage.model_dump() if usage else None,
            api_reported_cost_usd=getattr(usage, "cost", None))
    return send


def load_index(data):
    index = read(Path(data) / "index.json")
    if index["schema"] != "sce_portable_runtime/v1" or index["model"] != MODEL:
        raise ValueError("Frozen portable runtime required")
    return index


def checked_wave(data, item):
    base = Path(data).resolve(); index = load_index(base)
    path = (base / item["file"]).resolve()
    if not path.is_relative_to(base) or path.is_symlink() or sha(path) != index["files_sha256"][item["file"]]:
        raise ValueError("Prepared wave changed")
    return read(path)


def select_waves(index, task, scope, people=None, periods=None):
    if scope not in ("smoke", "full"):
        raise ValueError("Choose smoke or full scope explicitly")
    if people is not None and people < 1 or periods is not None and periods < 1:
        raise ValueError("Positive smoke people/periods required")
    waves = index["waves"][task]
    if scope == "smoke":
        waves = waves[:(periods or 2)]
    elif people is not None or periods is not None:
        raise ValueError("--people/--periods only select a clearly labelled smoke demonstration")
    return waves, (people or 2) if scope == "smoke" else None


def ordered_tasks(tasks):
    tasks = tuple(tasks)
    if not tasks or len(set(tasks)) != len(tasks) or set(tasks) - set(TASKS):
        raise ValueError("Select each supported task at most once")
    # A canonical DAG order allows a new B root to initialize monthly even
    # when the caller lists the requested tasks in another order.
    return tuple(task for task in TASKS if task in tasks)


def plan(data, *, tasks=TASKS, scope="smoke", people=None, periods=None):
    index = load_index(data); result = []
    for task in ordered_tasks(tasks):
        waves, n = select_waves(index, task, scope, people, periods)
        result.append(dict(task=task, periods=[w["period"] for w in waves],
            main_requests=sum(min(n, w["people"]) if n else w["people"] for w in waves),
            people_per_period=n or "original frozen roster"))
    # The same freshly generated B November answer can seed the fixed monthly
    # cohort. Main count is an upper bound until the selected identities join.
    return dict(status="offline_execution_plan", model=MODEL, provider="SiliconFlow",
        route=ROUTE, scope=scope, tasks=result,
        maximum_main_requests=sum(r["main_requests"] for r in result),
        maximum_attempts=sum(r["main_requests"] for r in result) * 2,
        retries="Each known technical failure at most one repair; unknown in-flight never resent",
        credentials_read=False, new_API_calls=0,
        notice="Smoke is an engineering demonstration, not the full paper's accuracy estimate")


def render_wave(task, wave, selected, previous=None, predecessor=None):
    """Call the original same-household state renderers, never archived future answers."""
    from ..experiments.recent_b_sampled_dates import render_B_messages
    from ..experiments.weekly_terminal import state_before
    from ..experiments.weekly_inputs import render
    rows = {a: wave["rows"][a] for a in selected}; before = {}; messages = {}
    if task == "weekly":
        before = state_before(previous, {a: r["prior"] for a, r in rows.items()}, wave["point"], predecessor)
    for aid, r in rows.items():
        if task == "A":
            before[aid] = deepcopy(r["initial"]); messages[aid] = r["messages"]
        elif task in ("B", "monthly"):
            before[aid] = deepcopy(previous[aid] if previous else r["initial"])
            messages[aid] = render_B_messages(r["template"], before[aid], wave["period"], r["context"])
        else:
            messages[aid] = render(r["template"], before[aid], wave["point"]["cutoff"])
    return before, messages


def advance(task, before, main, repair, wave, selected):
    from ..experiments import frozen_message_queue as queue
    from ..experiments.recent_b_recursion import transition
    from ..experiments.weekly_terminal import overlay
    after, answers = {}, []
    for aid in selected:
        row = wave["rows"][aid]; key = f"{task}|{wave['period']}|{aid}"
        r = main.get(key, {}); rr = repair.get("repair1|" + key, {})
        allowed = [field for field, valid in queue.fields(r).items() if not valid]
        if task == "weekly":
            state = overlay(before[aid], r, rr, allowed, row["cutoff"])
            sources = state["last_response_field_sources"]
        else:
            state = transition(before[aid], r, rr, allowed, wave["period"], row["cutoff"])
            sources = {f: ("main" if queue.fields(r)[f] else "repair" if queue.fields(rr)[f]
                           else "retained_prior") for f in ("q8", "q9")}
        after[aid] = state
        answers.append(dict(task=task, period=wave["period"], agent_id=aid,
            household=row["household"], weight=row["weight"], q8=state["fields"]["q8"]["value"],
            q9_bins=state["fields"]["q9"]["value"], field_sources=sources,
            before_q8=before[aid]["fields"]["q8"]["value"],
            before_q9_bins=before[aid]["fields"]["q9"]["value"],
            actual_model_results=bool(r.get("actual_model_results")), cutoff=row["cutoff"]))
    return after, answers


def _ledger(folder):
    from ..experiments import frozen_message_queue as queue
    intents, replies = [], []
    for segment in sorted(Path(folder).glob("segments/segment_*")):
        if (segment / "manifest.json").exists():
            for name, digest in read(segment / "manifest.json")["files_sha256"].items():
                if sha(segment / name) != digest:
                    raise ValueError("Immutable API ledger changed")
        intents.extend(queue.lines(segment / "dispatch_private.jsonl"))
        replies.extend(queue.lines(segment / "calls_private.jsonl"))
    queue.account(intents, replies)
    return intents, replies


def _run_slots(out, slots, send, p, workers, engineering, cool, *, gate=False):
    from ..experiments import frozen_message_queue as queue
    from ..experiments import full_a_personal_terminal as transport
    policy = transport._policy()
    cycles = 0
    while True:
        intents, replies = _ledger(out)
        sent = {r["key"] for r in intents}; pending = [s for s in slots if s["key"] not in sent]
        gate_slots = slots[:32] if gate else []
        gate_keys = {s["key"] for s in gate_slots}
        if gate_keys and gate_keys <= sent:
            observed = [r for r in replies if r["key"] in gate_keys]
            if len(observed) != len(gate_keys):
                return queue.account(intents, replies), "unknown_inflight_in_technical_gate"
            repaired = {r["key"].removeprefix("repair1|"): r for r in replies
                        if r["key"].startswith("repair1|")}
            normal = sum(any(not r.get("error") and r.get("finish_reason") == "stop"
                             for r in (main, repaired.get(main["key"], {}))) for main in observed)
            usable = sum(all(queue.fields(main)[f] or queue.fields(repaired.get(main["key"], {}))[f]
                             for f in ("q8", "q9")) for main in observed)
            if normal < min(16, len(gate_keys)) or usable / len(gate_keys) < .95:
                repairable = any(not all(queue.fields(r).values()) and "repair1|" + r["key"] not in sent
                                 for r in observed)
                return queue.account(intents, replies), ("technical_gate_repair_required" if repairable
                                                         else "technical_format_gate_failed")
        elif gate_keys:
            pending = [s for s in pending if s["key"] in gate_keys]
        if not pending:
            return queue.account(intents, replies), None
        segments = out / "segments"; segments.mkdir(exist_ok=True)
        dest = segments / f"segment_{len(list(segments.glob('segment_*'))):06}"
        def progress(value):
            write(out / "progress.json", value)
            if value["completed"] % 25 == 0 or not value["in_flight"]:
                print(f"{datetime.now():%H:%M:%S} | completed {value['completed']} | "
                      f"in-flight {value['in_flight']} | $ {value['spent_or_reserved_usd']:.4f}", flush=True)
        receipt, _ii, rr = transport._execute_tolerant_segment(p, pending, dest, send,
            workers=min(workers, 8) if gate_keys - sent else min(workers, 32),
            max_workers=min(workers, 8) if gate_keys - sent else workers, scale_after=32, policy=policy,
            prior_intents=intents, prior_replies=replies, engineering_only=engineering, publish=progress)
        if receipt["status"] == "completed":
            continue
        halt = receipt["halt_reason"]
        hard = halt in {"hard_provider_or_account_error", "Budget cap reached before dispatch",
                         "Budget guard", "Frozen prompt mismatch"}
        if hard or cycles >= 5:
            return receipt, halt or "bounded_recovery_limit"
        seconds = min(30 * (cycles + 1), 180)
        print(f"Temporary transport interruption; cooldown {seconds}s; only untouched slots resume", flush=True)
        cool(seconds); cycles += 1


def execute(data, out, *, tasks=TASKS, scope="smoke", people=None, periods=None,
            budget_usd, confirm_paid=False, workers=32, resume=False, sender=None, cool=time.sleep):
    """Durable fresh-run command. Injected senders are strictly engineering-only."""
    if not math.isfinite(budget_usd) or budget_usd <= 0 or not 1 <= workers <= 64:
        raise ValueError("Positive budget and 1–64 workers required")
    if sender is None and not confirm_paid:
        raise ValueError("Live generation requires --confirm-paid and your own budget/API Key")
    tasks = ordered_tasks(tasks)
    data, out = Path(data).resolve(), Path(out).resolve()
    if out.exists() and not resume:
        raise FileExistsError("Fresh --out required, or explicitly --resume the same immutable plan")
    if resume and not out.exists():
        raise FileNotFoundError("No run to resume")
    out.mkdir(parents=True, exist_ok=True)
    lock = (out / ".execution.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close(); raise ValueError("This run is already active")
    try:
        code_paths = [Path(__file__), ROOT / "studies/sce_inflation_expectations/experiments/full_a_personal_terminal.py",
            ROOT / "studies/sce_inflation_expectations/experiments/frozen_message_queue.py",
            ROOT / "studies/sce_inflation_expectations/experiments/recent_b_sampled_dates.py",
            ROOT / "studies/sce_inflation_expectations/experiments/recent_b_recursion.py",
            ROOT / "studies/sce_inflation_expectations/experiments/weekly_terminal.py",
            ROOT / "studies/sce_inflation_expectations/experiments/weekly_inputs.py",
            ROOT / "studies/sce_inflation_expectations/state_continuity_runtime.py",
            ROOT / "studies/sce_inflation_expectations/experiments/weekly_state.py",
            ROOT / "studies/sce_inflation_expectations/q9_normalization.py"]
        config = dict(schema="sce_reviewer_fresh_run/v1", tasks=list(tasks), scope=scope,
            people=people, periods=periods, budget_usd=budget_usd,
            runtime_index_sha256=sha(data / "index.json"), model=MODEL, route=ROUTE,
            actual_model_results=sender is None,
            code_sha256={str(p.relative_to(ROOT)): sha(p) for p in code_paths},
            fixed_model_protocol=protocol(budget_usd))
        if (out / "run_config.json").exists():
            if read(out / "run_config.json") != config:
                raise ValueError("Resume may not change research scope, budget or input hashes")
        else:
            write(out / "run_config.json", config)
            write(out / "execution_plan.json", plan(data, tasks=tasks, scope=scope, people=people, periods=periods))
        send = sender or make_sender(protocol(budget_usd))
        return _execute(data, out, config, workers, send, sender is not None, cool)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN); lock.close()


def _execute(data, out, config, workers, send, engineering, cool):
    from ..prior_belief_experiment import message_hash
    from ..experiments import frozen_message_queue as queue
    from ..experiments.full_a_personal_terminal import reserve
    index = load_index(data); p = protocol(config["budget_usd"])
    all_answers = []; fresh_B_root = None
    for task in config["tasks"]:
        waves, n = select_waves(index, task, config["scope"], config["people"], config["periods"])
        previous, predecessor = None, None
        fixed_ids = None
        for item in waves:
            wave = checked_wave(data, item)
            selected = sorted(wave["rows"])[:n] if n else sorted(wave["rows"])
            if task in ("monthly", "weekly"):
                if fixed_ids is None:
                    fixed_ids = selected
                if selected != fixed_ids:
                    raise ValueError("Fixed-cohort identities changed")
            checkpoint = out / "checkpoints" / task / item["period"]
            before, messages = render_wave(task, wave, selected, previous, predecessor)
            state_hash = hashlib.sha256(json.dumps(before, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if checkpoint.exists():
                if read(checkpoint / "manifest.json")["before_sha256"] != state_hash:
                    raise ValueError("Predecessor state differs from the sealed checkpoint")
                for name, digest in read(checkpoint / "manifest.json")["files"].items():
                    if sha(checkpoint / name) != digest:
                        raise ValueError("Checkpoint changed")
                previous = read(checkpoint / "after.json")
                answers = read(checkpoint / "answers.json")
                all_answers.extend(answers)
                predecessor = wave["point"]["cutoff"] if task == "weekly" else item["period"]
                if task == "B" and item["period"] == "202511":
                    fresh_B_root = (deepcopy(previous), deepcopy(answers))
                if task in ("A", "B"):
                    previous = None
                continue
            if task == "monthly" and item["period"] == "202511" and fresh_B_root:
                previous, answers = deepcopy(fresh_B_root)
                if set(previous) != set(selected):
                    raise ValueError("Newly generated B roots must match monthly identities")
                for a in answers:
                    a.update(task="monthly", household=wave["rows"][a["agent_id"]]["household"],
                             weight=wave["rows"][a["agent_id"]]["weight"], root_reused_from_fresh_B=True)
            else:
                slots = [dict(key=f"{task}|{item['period']}|{aid}", month=wave.get("point", {}).get("month", item["period"]),
                    arm=task, repeat=1, agent_id=aid, messages=messages[aid],
                    prompt_sha256=message_hash(messages[aid]),
                    reserved_usd=reserve(p, len(json.dumps(messages[aid], ensure_ascii=False).encode()))) for aid in selected]
                # Save exactly what will be sent before any network activity.
                wave_dir = out / "waves" / task / item["period"]
                if (wave_dir / "inputs.json.gz").exists():
                    if read(wave_dir / "inputs.json.gz") != slots:
                        raise ValueError("Frozen fresh prompt changed on resume")
                else:
                    write(wave_dir / "inputs.json.gz", slots)
                    write(wave_dir / "before.json.gz", before)
                # The production 32-request gate is preserved for full waves.
                # Tiny demonstrations use their one allowed technical repair;
                # a single transient failure among two calls must not make the
                # same run permanently impossible to resume before repair.
                receipt, halt = _run_slots(out, slots, send, p, workers, engineering, cool, gate=len(slots) >= 32)
                if halt == "technical_gate_repair_required":
                    _ii, gate_replies = _ledger(out)
                    gate_map = {r["key"]: r for r in gate_replies}
                    gate_repairs = []
                    for s in slots[:32]:
                        if not all(queue.fields(gate_map[s["key"]]).values()):
                            copy = deepcopy(s); copy["key"] = "repair1|" + s["key"]; gate_repairs.append(copy)
                    repaired_receipt, repair_halt = _run_slots(out, gate_repairs, send, p,
                        min(workers, 32), engineering, cool)
                    write(wave_dir / "technical_gate_repair.json", dict(
                        main_gate_required_repair=True, repair_targets=len(gate_repairs),
                        repair_halt=repair_halt, receipt=repaired_receipt,
                        rule="One known technical repair before gate reassessment; no accuracy selection"))
                    if repair_halt:
                        receipt, halt = repaired_receipt, repair_halt
                    else:
                        receipt, halt = _run_slots(out, slots, send, p, workers, engineering, cool, gate=True)
                if halt:
                    result = dict(status="stopped_data_preserved", task=task, period=item["period"],
                        halt_reason=halt, receipt=receipt, actual_model_results=not engineering)
                    write(out / "receipt.json", result); return result
                intents, replies = _ledger(out)
                main = {r["key"]: r for r in replies if not r["key"].startswith("repair1|")}
                missing = set(s["key"] for s in slots) - set(main)
                if missing:
                    result = dict(status="stopped_unknown_dispatch_preserved", unresolved=len(missing),
                        notice="Do not resend unknown in-flight requests; preserve reservation and inspect provider receipts")
                    write(out / "receipt.json", result); return result
                repairs = []
                for s in slots:
                    r = main[s["key"]]
                    if not all(queue.fields(r).values()):
                        copy = deepcopy(s); copy["key"] = "repair1|" + copy["key"]; repairs.append(copy)
                receipt, halt = _run_slots(out, repairs, send, p, min(workers, 32), engineering, cool)
                if halt:
                    result = dict(status="stopped_data_preserved", halt_reason=halt, receipt=receipt)
                    write(out / "receipt.json", result); return result
                _ii, replies = _ledger(out)
                repair = {r["key"]: r for r in replies if r["key"].startswith("repair1|")}
                if {s["key"] for s in repairs} - set(repair):
                    result = dict(status="stopped_unknown_dispatch_preserved",
                        notice="Unknown repair in-flight retained without resend; inspect provider receipts")
                    write(out / "receipt.json", result); return result
                previous, answers = advance(task, before, main, repair, wave, selected)
            staged = checkpoint.with_name("." + checkpoint.name + "_" + str(time.time_ns()))
            staged.mkdir(parents=True)
            write(staged / "after.json", previous); write(staged / "answers.json", answers)
            write(staged / "manifest.json", dict(before_sha256=state_hash,
                files={name: sha(staged / name) for name in ("after.json", "answers.json")},
                status="sealed_before_next_period", actual_model_results=not engineering))
            staged.rename(checkpoint)
            all_answers.extend(answers)
            predecessor = wave["point"]["cutoff"] if task == "weekly" else item["period"]
            if task == "B" and item["period"] == "202511":
                fresh_B_root = (deepcopy(previous), deepcopy(answers))
            # Independent A/B target months do not propagate their simulated answer.
            if task in ("A", "B"):
                previous = None
    with (out / "answers.jsonl").open("w", encoding="utf-8") as f:
        for a in all_answers:
            f.write(json.dumps(a, ensure_ascii=False, allow_nan=False) + "\n")
    intents, replies = _ledger(out)
    result = dict(status="fresh_generation_complete", actual_model_results=not engineering,
        evaluation_opened=False, answers=len(all_answers), receipt=queue.account(intents, replies),
        scientific_configuration="original final A/B/monthly/weekly methods; smoke explicitly labelled")
    write(out / "receipt.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("export", "plan", "run"))
    parser.add_argument("--data", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--tasks", nargs="+", choices=TASKS, default=list(TASKS))
    parser.add_argument("--scope", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--people", type=int)
    parser.add_argument("--periods", type=int)
    parser.add_argument("--budget-usd", type=float)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--confirm-paid", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.action == "export":
        result = export(args.out)
    elif args.action == "plan":
        result = plan(args.data, tasks=args.tasks, scope=args.scope, people=args.people, periods=args.periods)
    else:
        if args.budget_usd is None or args.out is None:
            parser.error("run requires --out and --budget-usd")
        result = execute(args.data, args.out, tasks=args.tasks, scope=args.scope, people=args.people,
            periods=args.periods, budget_usd=args.budget_usd, workers=args.workers,
            confirm_paid=args.confirm_paid, resume=args.resume)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status", "") not in ("fresh_generation_complete", "offline_execution_plan", ""):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
