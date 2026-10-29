"""Zero-network acceptance of the portable original research workflow."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

from . import portable_run as run


def fixture(point=3.2):
    return dict(raw_response_text=json.dumps(dict(point_pct=point,
        q9={f"bin{i}": (100 if i == 4 else 0) for i in range(1, 11)})),
        finish_reason="stop", returned_model=run.MODEL, returned_provider="SiliconFlow",
        api_reported_cost_usd=0)


def validate(data, out):
    from .reproduce import no_network
    data, out = Path(data).resolve(), Path(out).resolve()
    if out.exists():
        raise FileExistsError("Fresh acceptance output required")
    out.mkdir(parents=True)
    checks = []
    with no_network():
        result = run.execute(data, out / "fresh_fixture", budget_usd=1, workers=2,
            sender=lambda _: fixture(), cool=lambda _: None)
        assert result["answers"] == 16 and result["receipt"]["attempts"] == 14
        assert result["actual_model_results"] is False and not result["evaluation_opened"]
        checks.append("all_four_tasks_run_with_fresh_dynamic_state")
        def forbidden(_):
            raise AssertionError("Completed calls were resent")
        again = run.execute(data, out / "fresh_fixture", budget_usd=1, workers=2,
            sender=forbidden, resume=True)
        assert again["answers"] == 16 and again["receipt"]["attempts"] == 14
        checks.append("resume_sends_zero_completed_calls")
        index = run.load_index(data)
        for task in ("monthly", "weekly"):
            i = 1 if task == "weekly" else 0
            first = run.checked_wave(data, index["waves"][task][i])
            second = run.checked_wave(data, index["waves"][task][i + 1])
            selected = sorted(first["rows"])[:1]
            # A same-cycle weekly pair is used to demonstrate propagation.
            before, _ = run.render_wave(task, first, selected)
            key = f"{task}|{first['period']}|{selected[0]}"
            a = fixture(2); b = fixture(9)
            after_a, _ = run.advance(task, before, {key: a}, {}, first, selected)
            after_b, _ = run.advance(task, before, {key: b}, {}, first, selected)
            predecessor = first.get("point", {}).get("cutoff", first["period"])
            _, ma = run.render_wave(task, second, selected, after_a, predecessor)
            _, mb = run.render_wave(task, second, selected, after_b, predecessor)
            assert ma != mb
            assert '"point_pct": 9' in mb[selected[0]][0]["content"]
            checks.append(task + "_changed_previous_answer_changes_successor_prompt")
        stopped = run.execute(data, out / "budget_guard", budget_usd=1e-9, sender=forbidden)
        assert stopped["status"] == "stopped_data_preserved" and stopped["receipt"]["attempts"] == 0
        checks.append("budget_stops_before_network_dispatch")
        # Independently check all frozen per-wave payload hashes, without
        # opening evaluation targets or credentials.
        checked = 0
        for waves in index["waves"].values():
            for item in waves:
                run.checked_wave(data, item); checked += 1
        checks.append("every_input_wave_hash_verified")
        imports = {}
        for name, module in list(sys.modules.items()):
            if not (name.startswith("studies.sce_inflation_expectations")
                    or name in ("sce_q9", "beta_fit_kernel")):
                continue
            location = getattr(module, "__file__", None)
            if location:
                location = Path(location).resolve()
                if not location.is_relative_to(run.ROOT):
                    raise ValueError("SCE module was imported from outside the reviewer workspace")
                imports[name] = str(location.relative_to(run.ROOT))
        checks.append("all_imported_SCE_modules_from_this_source_workspace")
    receipt = dict(status="passed_portable_original_workflow_offline_acceptance",
        checks=checks, checked_input_waves=checked, engineering_fixture_answers=16,
        fixture_attempts=14, real_LLM_calls=0, network_allowed=False,
        credentials_read=False, empirical_accuracy_claim=False,
        source_modules=imports,
        note="Transport injection checks engineering; new paid model outputs require reviewer-owned Key")
    run.write(out / "acceptance.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    validate(args.data, args.out)
