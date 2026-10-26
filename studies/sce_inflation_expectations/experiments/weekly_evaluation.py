"""Post-generation, national-only evaluation for the 47-point weekly run.

This module is loaded only by the separate evaluation command. It refuses
offline fixtures, verifies the sealed checkpoints, and opens the public target
catalog only after the generation receipt confirms actual model results.
No model client, endpoint, or target data is used during generation.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from html import escape
import csv
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from .frozen_batch import ROOT as PROJECT_ROOT, dump, read_json, sha
from .weekly_terminal import CATALOG, checked, sealed
from .weekly_release_protocol import aware, evaluate_frozen_points, schedule, score_cutoffs
from .state_continuity_inputs import density_center
from ..evaluation.metrics import distribution_summary, headline_errors
from .recent_b_review_materials import macro_prediction


ROOT = PROJECT_ROOT
MACRO_PARAMETERS = ROOT / "outputs/sce_recent_b_review_materials_20261026_v2/macro_parameters.json"
FOOD_CATALOG = ROOT / "outputs/sce_fullperiod_materialized_20261022_v2/food_catalog.json"
NY = ZoneInfo("America/New_York")
EXPECTED_POINTS = 47
EXPECTED_HOUSEHOLDS = 300
EXPECTED_CYCLES = 12
REGISTERED_MSE_WEIGHT = 0.133976257


def _as_float(value, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"Finite numeric {label} required")
    return float(value)


def _key(target: str, cutoff: str) -> tuple[str, str]:
    return target, aware(cutoff).astimezone(timezone.utc).isoformat()


def _publication_known_from(row: dict, food_overrides: dict | None = None) -> datetime:
    """Parse a verified instant, otherwise conservatively use next NY midnight."""
    published_at = row.get("verified_published_at") or row.get("published_at")
    published_date = row.get("published_date")
    if published_at and "T" in published_at:
        instant = aware(published_at)
        if published_date and instant.astimezone(NY).date() != date.fromisoformat(published_date):
            raise ValueError("Publication timestamp conflicts with its New York release date")
        return instant
    day_text = published_date or (published_at[:10] if published_at else None)
    if not day_text:
        raise ValueError("Publication date or verified timestamp required")
    key = (row.get("reference_period"), day_text)
    if food_overrides and key in food_overrides:
        instant = aware(food_overrides[key])
        if instant.astimezone(NY).date() != date.fromisoformat(day_text):
            raise ValueError("Food-catalog timestamp conflicts with CPI release date")
        return instant
    day = date.fromisoformat(day_text) + timedelta(days=1)
    return datetime.combine(day, time(0), NY)


def _publication_timing_method(row: dict, food_overrides: dict | None = None) -> str:
    if (row.get("verified_published_at") or row.get("published_at")):
        published = row.get("verified_published_at") or row.get("published_at")
        if "T" in published:
            return "catalog_verified_publication_timestamp"
    day_text = row.get("published_date")
    if day_text and food_overrides and (row.get("reference_period"), day_text) in food_overrides:
        return "food_catalog_archived_0830_override"
    return "date_only_next_NY_midnight"


def _food_catalog_publication_overrides(path: Path, sources: dict) -> tuple[dict, dict]:
    """Use only archived matching 08:30 ET CPI timestamps; never synthesize one."""
    path = Path(path).resolve()
    if not path.is_file() or not path.is_relative_to(ROOT.resolve()):
        return {}, {"status": "catalog_unavailable_date_only_fallback", "override_count": 0}
    sources[str(path.relative_to(ROOT))] = sha(path)
    food = read_json(path)
    overrides = {}
    for row in food.values():
        if not isinstance(row, dict) or not isinstance(row.get("food_at_home"), dict):
            continue
        item = row["food_at_home"]
        reference = item.get("reference_period")
        published_at = item.get("published_at")
        source_file = item.get("source_file")
        source_digest = item.get("source_sha256")
        if not all(isinstance(value, str) and value for value in (reference, published_at, source_file, source_digest)):
            continue
        if "T" not in published_at:
            continue
        instant = aware(published_at)
        local = instant.astimezone(NY)
        # The override is specifically the archived 08:30 ET BLS release time.
        if (local.hour, local.minute, local.second) != (8, 30, 0):
            continue
        source = _verify_catalog_source(source_file, source_digest)
        sources[str(source.relative_to(ROOT))] = source_digest
        key = (reference, local.date().isoformat())
        prior = overrides.get(key)
        if prior is not None and prior != published_at:
            raise ValueError("Conflicting archived CPI publication timestamps in food catalog")
        overrides[key] = published_at
    return overrides, {"status": "archived_food_catalog_checked", "override_count": len(overrides),
                       "rule": "Exact archived 08:30 ET timestamp only for matching reference period and published date; otherwise next NY midnight"}


def _verify_catalog_source(relative: str, expected: str) -> Path:
    path = (ROOT / relative).resolve()
    base = ROOT.resolve()
    if not path.is_relative_to(base) or not path.is_file() or sha(path) != expected:
        raise ValueError("Public evaluation source hash mismatch: " + relative)
    return path


def _validate_bins(value) -> tuple[float, ...]:
    if (not isinstance(value, list) or len(value) != 10
            or any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 or x > 100
                   for x in value)
            or abs(math.fsum(value) - 100) > 1e-6):
        raise ValueError("Sealed Q9 state must contain ten legal probabilities summing to 100")
    return tuple(float(x) for x in value)


def _same_instant(left: str, right: str) -> bool:
    return aware(left).astimezone(timezone.utc) == aware(right).astimezone(timezone.utc)


def _state_center(state: dict, exact_cache: dict[tuple[float, ...], float]) -> float:
    """Use the exact center attached to the current Q9 source, then frozen scorer.

    Failed Q9 fields retain their previous source instant and the weekly state
    history retains that source's center. Matching on the field timestamp keeps
    a failed attempted answer from being mistaken for the household's state.
    """
    field = state.get("fields", {}).get("q9", {})
    bins = _validate_bins(field.get("value"))
    source_at = field.get("source_at")
    for row in reversed(state.get("history_centers", [])):
        if source_at and row.get("source_at") and _same_instant(row["source_at"], source_at):
            value = _as_float(row.get("center"), "Q9 history center")
            return value
    if bins not in exact_cache:
        center = density_center(bins)
        if center is None or not math.isfinite(center):
            raise ValueError("Frozen Q9 density scorer could not score a sealed household state")
        exact_cache[bins] = float(center)
    return exact_cache[bins]


def _public_cycle_summaries(cycles: dict, cycle_keys: set[str], ids: set[str], weights: dict) -> dict:
    if set(cycles) != cycle_keys:
        raise ValueError("Calibrated cycle roster does not match the 47-point plan")
    out = {}
    for cycle_key, cycle in cycles.items():
        states = cycle.get("states")
        if not isinstance(states, dict) or set(states) != ids:
            raise ValueError("Each calibrated cycle must contain the complete fixed household roster")
        centers = [_as_float(states[aid].get("center"), "cycle prior center") for aid in ids]
        out[cycle_key] = distribution_summary(centers, [weights[aid] for aid in ids])
    return out


def _available_cpi(point: dict, cpi_releases: list[dict], sources: dict,
                   food_overrides: dict | None = None) -> tuple[dict | None, str | None]:
    cutoff = aware(point["cutoff"])
    eligible = [row for row in cpi_releases if _publication_known_from(row, food_overrides) <= cutoff]
    by_period = {}
    for row in eligible:
        period = row["reference_period"]
        old = by_period.get(period)
        if old is None or _publication_known_from(row, food_overrides) > _publication_known_from(old, food_overrides):
            by_period[period] = row
    ordered = sorted(by_period.values(), key=lambda row: row["reference_period"], reverse=True)
    if len(ordered) < 2:
        return None, "fewer_than_two_cutoff_eligible_CPI_first_releases"
    latest, previous = ordered[:2]
    for row in (latest, previous):
        source_path = row.get("source_file") or row.get("file")
        source_hash = row.get("source_sha256") or row.get("sha256")
        if source_path and source_hash:
            source = _verify_catalog_source(source_path, source_hash)
            sources[str(source.relative_to(ROOT))] = source_hash
    try:
        latest_value = _as_float(latest.get("value"), "CPI first-release value")
        previous_value = _as_float(previous.get("value"), "prior CPI first-release value")
    except ValueError:
        return None, "nonfinite_CPI_first-release_value"
    return {
        "cpi_yoy_pp": latest_value,
        "cpi_change_pp": latest_value - previous_value,
        "latest_reference_period": latest["reference_period"],
        "latest_known_from": _publication_known_from(latest, food_overrides).isoformat(),
        "latest_timing_method": _publication_timing_method(latest, food_overrides),
        "previous_reference_period": previous["reference_period"],
        "previous_known_from": _publication_known_from(previous, food_overrides).isoformat(),
        "previous_timing_method": _publication_timing_method(previous, food_overrides),
    }, None


def _fixed_macro_predictions(point: dict, sim_median: float, cpi_releases: list[dict],
                             parameters: dict, sources: dict,
                             food_overrides: dict | None = None) -> tuple[dict, dict]:
    max_label_date = parameters.get("max_training_label_publication")
    if not max_label_date:
        raise ValueError("Fixed macro fit must declare its latest training-label publication")
    training_known = _publication_known_from({"published_date": max_label_date})
    if training_known > aware(point["cutoff"]):
        why = "training_labels_not_public_by_cutoff"
        return ({"prediction_pp": None, "status": why},
                {"prediction_pp": None, "status": why})
    cpi, missing = _available_cpi(point, cpi_releases, sources, food_overrides)
    if cpi is None:
        why = missing or "cutoff_eligible_CPI_inputs_missing"
        return ({"prediction_pp": None, "status": why},
                {"prediction_pp": None, "status": why})
    predictors = {"baseline_pp": _as_float(point["anchor_pp"], "public anchor"),
                  "cpi_yoy_pp": cpi["cpi_yoy_pp"], "cpi_change_pp": cpi["cpi_change_pp"],
                  "sim_pp": sim_median}
    fits = parameters["fits"]
    without = macro_prediction(predictors, fits["macro_without_sim"])
    with_sim = macro_prediction(predictors, fits["macro_plus_sim"])
    return ({"prediction_pp": without, "status": "fixed_A82_SCE_CPI_model",
             "cpi_latest_reference_period": cpi["latest_reference_period"],
             "cpi_previous_reference_period": cpi["previous_reference_period"],
             "cpi_latest_known_from": cpi["latest_known_from"],
             "cpi_latest_timing_method": cpi["latest_timing_method"],
             "cpi_previous_known_from": cpi["previous_known_from"],
             "cpi_previous_timing_method": cpi["previous_timing_method"]},
            {"prediction_pp": with_sim, "status": "fixed_A82_SCE_CPI_plus_sim_model",
             "cpi_latest_reference_period": cpi["latest_reference_period"],
             "cpi_previous_reference_period": cpi["previous_reference_period"],
             "cpi_latest_known_from": cpi["latest_known_from"],
             "cpi_latest_timing_method": cpi["latest_timing_method"],
             "cpi_previous_known_from": cpi["previous_known_from"],
             "cpi_previous_timing_method": cpi["previous_timing_method"]})


def _panel_comparison(panel: dict, predictions: dict, held_predictions: dict, alpha: float) -> dict:
    rows = panel["rows"]
    truth = [row["truth_pp"] for row in rows]
    out = {
        "n_target_months": len(rows),
        "raw_model": panel["raw"],
        "public_SCE_persistence": panel["persistence"],
        "same_cycle_fixed_joint_prior": None,
        "fixed_A_early48_MSE_blend": None,
        "macro_without_sim": None,
        "macro_plus_sim": None,
    }
    blend = [(1 - alpha) * row["baseline_pp"] + alpha * row["forecast_pp"] for row in rows]
    held = [held_predictions[_key(row["target_reference_period"], row["cutoff"])] for row in rows]
    out["same_cycle_fixed_joint_prior"] = headline_errors(held, truth)
    out["fixed_A_early48_MSE_blend"] = headline_errors(blend, truth)
    for name, key in (("macro_without_sim", "without_sim"), ("macro_plus_sim", "with_sim")):
        values = [predictions.get(_key(row["target_reference_period"], row["cutoff"]), {}).get(key)
                  for row in rows]
        if all(value is not None for value in values):
            out[name] = headline_errors(values, truth)
        else:
            out[name] = {"status": "incomplete_cutoff_eligible_inputs",
                         "available_points": sum(value is not None for value in values),
                         "required_points": len(values)}
    return out


def _figure(rows: list[dict], scored: list[dict], out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib import font_manager

    font = PROJECT_ROOT / "outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf"
    if font.exists():
        font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({"font.family": ["Times New Roman", "KaiTi SC"],
                         "axes.unicode_minus": False})
    x = [aware(row["cutoff"]).astimezone(NY) for row in rows]
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, layout="constrained",
                             gridspec_kw={"height_ratios": [2.2, 1]})
    axes[0].plot(x, [row["sim_median_pp"] for row in rows], color="#c76800", marker="o",
                 markersize=2.8, linewidth=1.8, label="周度模拟中位数")
    axes[0].plot(x, [row["anchor_pp"] for row in rows], color="#0072B2", linestyle="--",
                 linewidth=1.4, label="当时最后公开SCE")
    axes[0].plot(x, [row["cycle_prior_median_pp"] for row in rows], color="#8B3A8B",
                 linestyle=":", linewidth=1.8, label="本公开周期固定合成起点")
    scored_by_cutoff = {aware(row["cutoff"]).astimezone(timezone.utc): row for row in scored}
    sx, sy = [], []
    for row in rows:
        matched = scored_by_cutoff.get(aware(row["cutoff"]).astimezone(timezone.utc))
        if matched is not None:
            sx.append(aware(row["cutoff"]).astimezone(NY)); sy.append(matched["truth_pp"])
    if sx:
        axes[0].scatter(sx, sy, color="#242424", marker="D", s=30, zorder=5,
                        label="月度主评分点对应全国SCE")
    axes[0].set_ylabel("未来12个月通胀预期（%）")
    axes[0].legend(frameon=False, ncols=2)
    axes[0].grid(axis="y", alpha=.18)

    if scored:
        sx = [aware(row["cutoff"]).astimezone(NY) for row in scored]
        raw_err = [abs(row["forecast_pp"] - row["truth_pp"]) for row in scored]
        base_err = [abs(row["baseline_pp"] - row["truth_pp"]) for row in scored]
        alpha = rows[0]["mse_simulation_weight"]
        blend_err = [abs(((1-alpha)*row["baseline_pp"] + alpha*row["forecast_pp"])
                         - row["truth_pp"]) for row in scored]
        cycle_prior_by_cutoff = {
            aware(row["cutoff"]).astimezone(timezone.utc): row["cycle_prior_median_pp"]
            for row in rows
        }
        held_err = [abs(cycle_prior_by_cutoff[aware(row["cutoff"]).astimezone(timezone.utc)]
                        - row["truth_pp"]) for row in scored]
        axes[1].plot(sx, raw_err, color="#c76800", marker="o", linewidth=1.5, label="模拟绝对误差")
        axes[1].plot(sx, base_err, color="#0072B2", marker="s", linewidth=1.3, label="持续性绝对误差")
        axes[1].plot(sx, blend_err, color="#8B3A8B", marker="^", linewidth=1.3, label="固定A早48月组合绝对误差")
        axes[1].plot(sx, held_err, color="#4D4D4D", marker="x", linestyle="--", linewidth=1.1,
                     label="同周期固定合成先验绝对误差")
    axes[1].set_ylabel("主评分绝对误差（pp）")
    axes[1].legend(frameon=False, ncols=2)
    axes[1].grid(axis="y", alpha=.18)
    axes[1].xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m", tz=NY))
    fig.savefig(out, dpi=180)
    plt.close(fig)


def evaluate(folder) -> dict:
    """Evaluate one completed actual-model weekly generation into a fresh folder."""
    folder = Path(folder).resolve()
    protocol, package_manifest = checked(folder)
    generation_path = folder / "generation_receipt.json"
    generation = read_json(generation_path)
    if (generation.get("status") != "weekly_generation_complete"
            or generation.get("actual_model_results") is not True
            or generation.get("weekly_points") != EXPECTED_POINTS):
        raise ValueError("Actual complete 47-week model generation required; offline fixtures are refused")
    generation_weeks = generation.get("weekly")
    if (not isinstance(generation_weeks, list) or len(generation_weeks) != EXPECTED_POINTS
            or any(row.get("actual_model_results") is not True for row in generation_weeks)):
        raise ValueError("Every weekly generation receipt must contain actual model results")
    out = folder / "evaluation"
    if out.exists():
        raise ValueError("Fresh folder/evaluation output required")

    inputs = (ROOT / protocol["inputs"]).resolve()
    if not inputs.is_relative_to(ROOT.resolve()):
        raise ValueError("Weekly evaluation inputs must remain inside the project")
    expected_catalog = str(Path(CATALOG).resolve().relative_to(ROOT.resolve()))
    if protocol.get("evaluation_catalog_only") != expected_catalog:
        raise ValueError("Evaluation catalog differs from the frozen evaluation-only path")
    plan = read_json(inputs / "weekly_plan.json")
    weights = read_json(inputs / "weights_private.json")
    cycles = read_json(inputs / "priors/cycles_private.json")
    if len(plan) != EXPECTED_POINTS or len({row["step_key"] for row in plan}) != EXPECTED_POINTS:
        raise ValueError("Exactly 47 unique frozen weekly points required")
    if len({row["cycle_key"] for row in plan}) != EXPECTED_CYCLES:
        raise ValueError("The frozen weekly plan must contain the registered 12 public cycles")
    if len(weights) != EXPECTED_HOUSEHOLDS:
        raise ValueError("The fixed 300-household weight roster is required")
    for aid, value in weights.items():
        weights[aid] = _as_float(value, "household analysis weight")
        if weights[aid] <= 0:
            raise ValueError("Household analysis weights must be positive")
    ids = set(weights)
    cycle_keys = {row["cycle_key"] for row in plan}
    fixed_cycle = _public_cycle_summaries(cycles, cycle_keys, ids, weights)

    # Recheck release clocks against the execution plan without opening targets.
    # The public catalog is intentionally deferred until every actual checkpoint
    # has been sealed and identity/cutoff checked below.
    forecast_meta = []
    weekly_rows = []
    score_cache: dict[tuple[float, ...], float] = {}
    retention = Counter()
    checkpoint_sources = {}
    generation_receipts_by_key = {row.get("step_key"): row for row in generation_weeks}
    for point in plan:
        step_receipt = generation_receipts_by_key.get(point["step_key"])
        if step_receipt is None or step_receipt.get("cycle_key") != point["cycle_key"]:
            raise ValueError("Generation receipt does not match the frozen weekly plan")
        states, receipt = sealed(folder, point)
        if (receipt.get("actual_model_results") is not True
                or receipt.get("step_key") != point["step_key"]
                or receipt.get("cycle_key") != point["cycle_key"]
                or not _same_instant(receipt.get("cutoff", ""), point["cutoff"])):
            raise ValueError("Sealed weekly receipt is not an actual result for the planned cutoff")
        checkpoint_dir = folder / "checkpoints" / point["step_key"]
        for path in sorted(checkpoint_dir.rglob("*")):
            if path.is_file():
                checkpoint_sources[str(path.relative_to(ROOT))] = sha(path)
        wave_dir = folder / "waves" / point["step_key"]
        if (wave_dir / "wave_plan.json").is_file():
            checkpoint_sources[str((wave_dir / "wave_plan.json").relative_to(ROOT))] = sha(wave_dir / "wave_plan.json")
        for path in sorted(wave_dir.rglob("manifest.json")):
            checkpoint_sources[str(path.relative_to(ROOT))] = sha(path)
        if not isinstance(states, dict) or set(states) != ids:
            raise ValueError("Every sealed week must contain exactly the fixed 300 households")
        centers, household_weights = [], []
        updated_flags = {"q8": 0, "q9": 0}
        for aid in sorted(ids):
            state = states[aid]
            if (state.get("agent_id") != aid or state.get("cycle_key") != point["cycle_key"]
                    or not _same_instant(state.get("last_cutoff", ""), point["cutoff"])):
                raise ValueError("Cross-person, cross-cycle, or wrong-week state detected")
            steps = state.get("steps")
            if not isinstance(steps, list) or not steps:
                raise ValueError("Sealed household state requires its final weekly transition")
            last = steps[-1]
            if not _same_instant(last.get("cutoff", ""), point["cutoff"]):
                raise ValueError("Latest household transition does not match its checkpoint week")
            updated = last.get("field_updated_from_model")
            if not isinstance(updated, dict) or set(updated) != {"q8", "q9"}:
                raise ValueError("Per-field update provenance required for both Q8 and Q9")
            updated_flags["q8"] += bool(updated["q8"])
            updated_flags["q9"] += bool(updated["q9"])
            centers.append(_state_center(state, score_cache))
            household_weights.append(weights[aid])
        model_summary = distribution_summary(centers, household_weights)
        prior_summary = fixed_cycle[point["cycle_key"]]
        raw_forecast = model_summary["median_pp"]
        blend_weight = None
        weekly_rows.append({
            "step_key": point["step_key"], "cutoff": point["cutoff"],
            "target_reference_period": point["target_reference_period"],
            "cycle_key": point["cycle_key"], "reset_required": point["reset_required"],
            "anchor_reference_period": point["anchor_reference_period"],
            "anchor_published_date": point["anchor_published_date"],
            "anchor_known_from": point["anchor_known_from"], "anchor_pp": _as_float(point["anchor_pp"], "public SCE anchor"),
            "sim_median_pp": model_summary["median_pp"], "sim_iqr_pp": model_summary["iqr_pp"],
            "sim_q25_pp": model_summary["q25_pp"], "sim_q75_pp": model_summary["q75_pp"],
            "sim_mean_pp_descriptive_only": model_summary["mean_pp"],
            "sim_ess": model_summary["ess"], "sim_n_valid": model_summary["n_valid"],
            "cycle_prior_median_pp": prior_summary["median_pp"],
            "cycle_prior_iqr_pp": prior_summary["iqr_pp"],
            "cycle_prior_mean_pp_descriptive_only": prior_summary["mean_pp"],
            "q8_updated_n": updated_flags["q8"], "q8_retained_n": EXPECTED_HOUSEHOLDS-updated_flags["q8"],
            "q9_updated_n": updated_flags["q9"], "q9_retained_n": EXPECTED_HOUSEHOLDS-updated_flags["q9"],
            "mse_simulation_weight": 0.0,
            "fixed_A_early48_MSE_blend_pp": None,
            "main_score_point": False, "target_release_value_pp": None,
            "raw_main_abs_error_pp": None, "persistence_main_abs_error_pp": None,
            "same_cycle_prior_main_abs_error_pp": None,
            "fixed_A_early48_blend_main_abs_error_pp": None,
        })
        retention["q8_retained_household_weeks"] += EXPECTED_HOUSEHOLDS-updated_flags["q8"]
        retention["q9_retained_household_weeks"] += EXPECTED_HOUSEHOLDS-updated_flags["q9"]
        forecast_meta.append({
            "cutoff": point["cutoff"], "target_reference_period": point["target_reference_period"],
            "anchor_reference_period": point["anchor_reference_period"],
            "anchor_pp": _as_float(point["anchor_pp"], "public SCE anchor"),
            "forecast_pp": raw_forecast, "forecast_kind": "raw_model_pre_reset",
        })

    # Only after all actual checkpoints and the generation receipt pass do we
    # read any target values from the evaluation-only public catalog.
    catalog_path = Path(CATALOG).resolve()
    if not catalog_path.is_file() or not catalog_path.is_relative_to(ROOT.resolve()):
        raise ValueError("Evaluation-only national SCE catalog is unavailable")
    catalog = read_json(catalog_path)
    releases = catalog.get("headline_releases")
    cpi_releases = catalog.get("cpi_first_releases")
    if not isinstance(releases, list) or not isinstance(cpi_releases, list):
        raise ValueError("Headline and first-release CPI series required in evaluation catalog")
    release_by_period = {row["reference_period"]: row for row in releases}
    if len(release_by_period) != len(releases):
        raise ValueError("Duplicate public SCE reference period in evaluation catalog")
    clock_rows = schedule([row["cutoff"] for row in plan], releases)
    for point, clock in zip(plan, clock_rows):
        for field in ("target_reference_period", "anchor_reference_period", "anchor_published_date", "cycle_key"):
            if point[field] != clock[field]:
                raise ValueError("Frozen plan/public release clock mismatch: " + field)
        if not math.isclose(float(point["anchor_pp"]), float(clock["anchor_pp"]), rel_tol=0, abs_tol=1e-12):
            raise ValueError("Frozen plan/public SCE anchor value mismatch")

    source_hashes = {
        str(catalog_path.relative_to(ROOT)): sha(catalog_path),
        str(generation_path.relative_to(ROOT)): sha(generation_path),
        str((folder / "package/protocol.json").relative_to(ROOT)): sha(folder / "package/protocol.json"),
        str((folder / "package/manifest.json").relative_to(ROOT)): sha(folder / "package/manifest.json"),
        str((inputs / "manifest.json").relative_to(ROOT)): sha(inputs / "manifest.json"),
        str((inputs / "weekly_plan.json").relative_to(ROOT)): sha(inputs / "weekly_plan.json"),
        str((inputs / "weights_private.json").relative_to(ROOT)): sha(inputs / "weights_private.json"),
        str((inputs / "priors/cycles_private.json").relative_to(ROOT)): sha(inputs / "priors/cycles_private.json"),
    }
    source_hashes.update(package_manifest.get("source_sha256", {}))
    source_hashes.update(checkpoint_sources)
    food_overrides, food_timing_info = _food_catalog_publication_overrides(FOOD_CATALOG, source_hashes)
    used_references = ({row["target_reference_period"] for row in plan}
                       | {row["anchor_reference_period"] for row in plan})
    for reference in sorted(used_references):
        release = release_by_period.get(reference)
        if release is None:
            raise ValueError("Missing target/anchor SCE release: " + reference)
        source_path = release.get("source_file")
        source_digest = release.get("source_sha256")
        if not source_path or not source_digest:
            raise ValueError("National release must bind its archived source hash: " + reference)
        archive = _verify_catalog_source(source_path, source_digest)
        source_hashes[str(archive.relative_to(ROOT))] = source_digest

    parameters_path = Path(MACRO_PARAMETERS).resolve()
    if not parameters_path.is_file() or not parameters_path.is_relative_to(ROOT.resolve()):
        raise ValueError("Frozen A82 macro parameter file is unavailable")
    parameters = read_json(parameters_path)
    if (parameters.get("B_targets_used_for_fitting") is not False
            or parameters.get("coefficient_update_within_B") is not False):
        raise ValueError("Weekly evaluation requires fixed A-only coefficients and no refitting")
    if parameters["blends"]["mse"].get("training_n") != 48:
        raise ValueError("Fixed MSE blend must use its registered 48 early-A training months")
    alpha = _as_float(parameters["blends"]["mse"]["simulation_weight"], "frozen MSE blend weight")
    if not math.isclose(alpha, REGISTERED_MSE_WEIGHT, rel_tol=0, abs_tol=1e-9):
        raise ValueError("Frozen early-A MSE blend weight differs from its registered value")
    source_hashes[str(parameters_path.relative_to(ROOT))] = sha(parameters_path)
    for row in weekly_rows:
        row["mse_simulation_weight"] = alpha
        row["fixed_A_early48_MSE_blend_pp"] = ((1 - alpha) * row["anchor_pp"]
                                         + alpha * row["sim_median_pp"])

    macro_predictions = {}
    for point, row in zip(plan, weekly_rows):
        without, with_sim = _fixed_macro_predictions(point, row["sim_median_pp"], cpi_releases,
                                                      parameters, source_hashes, food_overrides)
        row["macro_without_sim_pp"] = without["prediction_pp"]
        row["macro_without_sim_status"] = without["status"]
        row["macro_plus_sim_pp"] = with_sim["prediction_pp"]
        row["macro_plus_sim_status"] = with_sim["status"]
        row["macro_cpi_latest_known_from"] = without.get("cpi_latest_known_from")
        row["macro_cpi_latest_timing_method"] = without.get("cpi_latest_timing_method")
        row["macro_cpi_previous_known_from"] = without.get("cpi_previous_known_from")
        row["macro_cpi_previous_timing_method"] = without.get("cpi_previous_timing_method")
        key = _key(point["target_reference_period"], point["cutoff"])
        macro_predictions[key] = {
            "without_sim": without["prediction_pp"], "with_sim": with_sim["prediction_pp"],
        }

    protocol_result = evaluate_frozen_points(forecast_meta, releases)
    selections = score_cutoffs(plan, releases)
    primary_selections = [row for row in selections if row["panel"] == "last_week_in_month"]
    if len(primary_selections) != len({row["target_reference_period"] for row in plan}):
        raise ValueError("One primary last-week score point per target month required")
    protocol_by_panel = protocol_result["panels"]
    held_predictions = {_key(row["target_reference_period"], row["cutoff"]): row["cycle_prior_median_pp"]
                        for row in weekly_rows}
    panels = {label: _panel_comparison(value, macro_predictions, held_predictions, alpha)
              for label, value in protocol_by_panel.items()}
    row_by_key = {_key(row["target_reference_period"], row["cutoff"]): row for row in weekly_rows}
    primary_rows = protocol_by_panel.get("last_week_in_month", {}).get("rows", [])
    for score_row in primary_rows:
        key = _key(score_row["target_reference_period"], score_row["cutoff"])
        weekly = row_by_key[key]
        weekly["main_score_point"] = True
        weekly["target_release_value_pp"] = score_row["truth_pp"]
        weekly["raw_main_abs_error_pp"] = abs(score_row["forecast_pp"] - score_row["truth_pp"])
        weekly["persistence_main_abs_error_pp"] = abs(score_row["baseline_pp"] - score_row["truth_pp"])
        weekly["same_cycle_prior_main_abs_error_pp"] = abs(
            weekly["cycle_prior_median_pp"] - score_row["truth_pp"])
        weekly["fixed_A_early48_blend_main_abs_error_pp"] = abs(
            weekly["fixed_A_early48_MSE_blend_pp"] - score_row["truth_pp"])
    primary_rows = sorted(primary_rows, key=lambda row: row["target_reference_period"])

    out.mkdir()
    dump(out / "summary.json", {
        "status": "completed_weekly_national_evaluation",
        "generation_status": generation["status"], "actual_model_results": True,
        "weekly_points": EXPECTED_POINTS, "fixed_households": EXPECTED_HOUSEHOLDS,
        "public_calibration_cycles": EXPECTED_CYCLES,
        "target_months": protocol_result["n_distinct_target_months"],
        "weekly_ground_truth_available": False, "recent_micro_truth_available": False,
        "micro_W1": None, "new_api_calls": 0,
        "primary_panel": "last_week_in_month",
        "evaluation": panels,
        "macro_fixed_model": {
            "status": "fixed_A82_parameters_evaluated_when_cutoff_inputs_are_available",
            "parameter_source": str(parameters_path.relative_to(ROOT)),
            "training_label_max_publication": parameters["max_training_label_publication"],
            "date_only_training_label_known_from": _publication_known_from(
                {"published_date": parameters["max_training_label_publication"]}).isoformat(),
            "first_week_unavailable_before_training_release_known_from": True,
            "cpi_publication_timing": food_timing_info,
            "cpi_date_only_fallback": "next New York midnight; an archived matching 08:30 ET timestamp in food_catalog overrides this only for that exact CPI reference period and published date",
            "coefficient_refit": False,
            "input_methods": "CPI first releases selected by published time; date-only releases enter next NY day",
        },
        "fixed_A_early48_MSE_blend": {
            "simulation_weight": alpha,
            "training_months": parameters["blends"]["mse"]["training_n"],
            "formula": "(1 - lambda) * last_public_SCE + lambda * current_week_simulated_median",
            "parameter_source": str(parameters_path.relative_to(ROOT)),
            "refit": False,
        },
        "retained_fields": dict(retention),
        "primary_monthly_points": primary_rows,
        "source_sha256": source_hashes,
        "limits": [
            "47 weekly states are one trajectory, not 47 independent national targets.",
            "Primary scoring uses one last-week state per target SCE month; 7/14/21-day panels reuse those target months.",
            "The national SCE is monthly; no weekly truth series exists.",
            "No recent respondent-level truth was read or used; no real-micro W1 or personal accuracy is reported.",
            "The fixed A82 SCE+CPI models are retrospective sensitivities; the first weekly cutoff predates their latest training-label publication.",
        ],
    })
    fields = [
        "step_key", "cutoff", "target_reference_period", "cycle_key", "reset_required",
        "anchor_reference_period", "anchor_published_date", "anchor_known_from", "anchor_pp",
        "sim_median_pp", "sim_iqr_pp", "sim_q25_pp", "sim_q75_pp", "sim_mean_pp_descriptive_only",
        "sim_ess", "sim_n_valid", "cycle_prior_median_pp", "cycle_prior_iqr_pp",
        "cycle_prior_mean_pp_descriptive_only", "q8_updated_n", "q8_retained_n", "q9_updated_n",
        "q9_retained_n", "mse_simulation_weight", "fixed_A_early48_MSE_blend_pp",
        "macro_without_sim_pp", "macro_without_sim_status", "macro_plus_sim_pp", "macro_plus_sim_status",
        "macro_cpi_latest_known_from", "macro_cpi_latest_timing_method",
        "macro_cpi_previous_known_from", "macro_cpi_previous_timing_method",
        "main_score_point", "target_release_value_pp", "raw_main_abs_error_pp",
        "persistence_main_abs_error_pp", "fixed_A_early48_blend_main_abs_error_pp",
        "same_cycle_prior_main_abs_error_pp",
    ]
    with (out / "weekly_national.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(weekly_rows)
    _figure(weekly_rows, primary_rows, out / "weekly_national.png")

    primary = panels["last_week_in_month"]
    raw_mae = primary["raw_model"]["mae_pp"]
    persistence_mae = primary["public_SCE_persistence"]["mae_pp"]
    held_mae = primary["same_cycle_fixed_joint_prior"]["mae_pp"]
    blend_metrics = primary["fixed_A_early48_MSE_blend"]
    horizon_rows = "".join(
        f"<tr><td>{escape(label)}</td><td>{item['n_target_months']}</td>"
        f"<td>{item['raw_model']['mae_pp']:.3f}</td>"
        f"<td>{item['public_SCE_persistence']['mae_pp']:.3f}</td>"
        f"<td>{item['same_cycle_fixed_joint_prior']['mae_pp']:.3f}</td>"
        f"<td>{item['fixed_A_early48_MSE_blend']['mae_pp']:.3f}</td></tr>"
        for label, item in panels.items()
    )
    body = (
        f"<h1>SCE周度状态链：独立全国评价</h1>"
        f"<p>真实模型结果 {EXPECTED_POINTS} 周、固定家庭 {EXPECTED_HOUSEHOLDS} 户、"
        f"{protocol_result['n_distinct_target_months']} 个目标月。主口径为每月最后一周："
        f"原始模拟MAE {raw_mae:.3f}pp，公开SCE持续性基线 {persistence_mae:.3f}pp，"
        f"同周期固定合成先验MAE {held_mae:.3f}pp，"
        f"固定A早48月MSE组合（λ={alpha:.6f}）MAE {blend_metrics['mae_pp']:.3f}pp。</p>"
        f"<p>只有月度SCE评分点对应观测值；周度曲线不代表周度真值。未读取近期个人真值，"
        f"不报告真人微观W1或个人准确度。宏观SCE+CPI敏感性沿用A82固定系数，不重新拟合；"
        f"首周截止早于该模型最后训练标签的保守可得时刻。</p>"
        f"<img src=\"weekly_national.png\" alt=\"47周状态链与月度主评分\">"
        f"<table><thead><tr><th>评分面板</th><th>目标月数</th><th>模拟MAE（pp）</th>"
        f"<th>持续性MAE（pp）</th><th>同周期合成先验MAE（pp）</th>"
        f"<th>固定A早48月组合MAE（pp）</th></tr></thead>"
        f"<tbody>{horizon_rows}</tbody></table>"
        f"<p><a href=\"summary.json\">完整汇总</a> · "
        f"<a href=\"weekly_national.csv\">47周汇总数据</a></p>"
    )
    html = (
        "<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\">"
        "<title>SCE周度状态链评价</title><style>"
        "body{max-width:1120px;margin:30px auto;padding:20px;font-family:'Times New Roman','KaiTi SC',serif;color:#242424;line-height:1.8}"
        "img{width:100%;border:1px solid #bbb}table{border-collapse:collapse;width:100%;margin:1.2em 0}"
        "th,td{border:1px solid #777;padding:.4em .65em;text-align:left}th{background:#eee}"
        "a{color:#005a8d}</style>" + body + "</html>"
    )
    (out / "index.html").write_text(html, encoding="utf-8")
    output_files = [path for path in out.iterdir() if path.is_file()]
    manifest_sources = dict(source_hashes)
    for path in (Path(__file__), Path(__file__).with_name("weekly_terminal.py"),
                 Path(__file__).with_name("weekly_release_protocol.py"),
                 Path(__file__).with_name("weekly_state.py"),
                 PROJECT_ROOT / "studies/sce_inflation_expectations/evaluation/metrics.py",
                 PROJECT_ROOT / "studies/sce_inflation_expectations/experiments/state_continuity_inputs.py",
                 PROJECT_ROOT / "studies/sce_inflation_expectations/scoring/sce_q9_frozen.py"):
        manifest_sources[str(path.resolve().relative_to(PROJECT_ROOT.resolve()))] = sha(path)
    dump(out / "manifest.json", {
        "status": "weekly_national_evaluation_complete", "new_api_calls": 0,
        "actual_model_results": True,
        "target_catalog_sha256": sha(catalog_path),
        "source_sha256": manifest_sources,
        "files_sha256": {path.name: sha(path) for path in output_files},
    })
    return read_json(out / "summary.json")
