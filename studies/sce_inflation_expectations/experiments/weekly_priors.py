"""Release-cycle synthetic priors for the fixed weekly SCE roster.

This is a pure adapter over the existing B donor matcher/calibrator. It reads
only a past public anchor, the supplied old joint-donor pool, and an exact-bin
Q9 density-score cache. Donor waves are screened under the same declared
nine-month availability assumption as ``recent_b_rolling_preflight`` before
any score lookup. It neither opens target answers nor fits missing Q9 scores.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .recent_b_priors import (
    balance_joint_draw,
    expected_summary,
    month_age,
    next_month,
    options_from_old_pool,
    prior_bands,
)
from .recent_b_rolling_preflight import inferred_available_date, select_source_wave
from .frozen_batch import ROOT, dump, read_json, sha
from ..experiments.state_continuity_inputs import BINS, density_center, finite_point
from ..population.entry_initialization import calibrate, draw
from ..prior_belief_preparation import valid_bins
from .weekly_release_protocol import NY, aware, known_from


SEED = 20261026
Q9_BAND_HALF_WIDTH_PP = 0.05
AVAILABILITY_BASIS = "survey_month_end_plus_nine_calendar_months_before_cutoff_assumed"
CODE_ROOT = Path(__file__).resolve().parents[3]
DONOR_POOL_PATH = ROOT / "outputs/sce_recent_b_rolling_preflight_20261025_v1/old_joint_donor_pool_private.parquet"
SCORE_CACHE_PATH = ROOT / "outputs/sce_monthly_fine_full_truth_20261023_v3/scoring_cache_private.json"


def _score_cache_map(score_cache):
    """Keep valid cache keys, including explicit None for known-unscorable bins."""
    result = {}

    def add(raw_bins, raw_score):
        try:
            bins = tuple(float(value) for value in raw_bins)
            if not valid_bins(bins):
                return
            if isinstance(raw_score, Mapping):
                raw_score = raw_score.get("mean")
            if (raw_score is None or isinstance(raw_score, bool)
                    or not isinstance(raw_score, (int, float, np.number))):
                score = None
            else:
                score = float(raw_score)
                if not math.isfinite(score):
                    score = None
        except (TypeError, ValueError, OverflowError):
            return
        if bins in result:
            old = result[bins]
            if old is not None and score is not None and old != score:
                raise ValueError("Conflicting deterministic Q9 score cache")
            if old is not None:
                return
        result[bins] = score

    if isinstance(score_cache, Mapping):
        for raw_bins, raw_score in score_cache.items():
            add(raw_bins, raw_score)
        return result

    for row in score_cache:
        if not isinstance(row, Mapping):
            continue
        add(row.get("bins", ()), row.get("score"))
    return result


def _jsonable(value):
    """Convert NumPy scalars/arrays in metrics to ordinary JSON values."""
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _canonical_hash(value):
    payload = json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _source_label(path):
    path = Path(path).resolve()
    try:
        return str(path.relative_to(CODE_ROOT))
    except ValueError:
        return str(path)


def _recipient_rows(roster):
    """Adapt preflight rows while taking weights only from weekly_design."""
    selected = []
    seen = set()
    for row in roster:
        persona = row["persona"]
        aid = str(persona["agent_id"])
        design = row["weekly_design"]
        if str(design.get("id")) != aid:
            raise ValueError("Weekly design identity differs from fixed persona")
        weight = design.get("poststratified_weight")
        if (isinstance(weight, bool) or not isinstance(weight, (int, float))
                or not math.isfinite(weight) or weight <= 0):
            raise ValueError("Positive weekly_design.poststratified_weight required")
        if aid in seen:
            raise ValueError("Duplicate fixed-roster identity")
        seen.add(aid)
        selected.append({"persona": persona, "analysis_weight": float(weight)})
    if not selected:
        raise ValueError("Nonempty fixed weekly roster required")
    return selected


def _score_past_only(past, score_cache, scoring_month):
    """Attach frozen Q8/Q9 fields using cache hits only; never fit a density."""
    if past.empty:
        raise ValueError("No past joint donors remain after source-wave filtering")
    if past.duplicated(["date", "userid"]).any():
        raise ValueError("Donor pool must be unique by reference period and anonymous ID")
    if not past.date.lt(int(scoring_month)).all():
        raise ValueError("Current/future outcomes cannot enter weekly initialization")

    scored = past.copy()
    scored["_point"] = scored.Q8v2part2.map(finite_point)
    scored["_bins_valid"] = scored.apply(
        lambda row: valid_bins([row[key] for key in BINS]), axis=1)

    centers = []
    cache_hits = 0
    unscorable_rows = 0
    unscorable_vectors = set()
    missing = set()
    for row in scored.to_dict("records"):
        if not row["_bins_valid"] or row["_point"] is None or pd.isna(row["_point"]):
            centers.append(None)
            continue
        bins = tuple(float(row[key]) for key in BINS)
        if bins not in score_cache:
            missing.add(bins)
            centers.append(None)
            continue
        center = score_cache[bins]
        centers.append(center)
        if center is None:
            unscorable_rows += 1
            unscorable_vectors.add(bins)
        else:
            cache_hits += 1
    if missing:
        raise ValueError(
            f"{len(missing)} eligible Q9 vectors are absent from the frozen score cache; "
            "weekly preparation must not fit them")
    scored["_center"] = centers
    scored["_age_months"] = [month_age(scoring_month, value) for value in scored.date]
    return scored, cache_hits, unscorable_rows, len(unscorable_vectors)


def _prefill_missing_scores(donors, reset_points, score_rows):
    """Add only truly absent eligible vectors to an in-memory frozen-score map."""
    scores = _score_cache_map(score_rows)
    sidecar = []
    fits_by_wave = {}
    donor_months = donors.date.dropna().unique()

    for point in reset_points:
        cutoff = aware(point["cutoff"])
        target_month = int(cutoff.astimezone(NY).strftime("%Y%m"))
        wave = select_source_wave(donor_months, cutoff.isoformat(), target_month)
        if wave in fits_by_wave:
            continue

        eligible = donors.loc[(donors.date <= wave) & (donors.date < target_month)]
        missing = set()
        for row in eligible.to_dict("records"):
            if finite_point(row.get("Q8v2part2")) is None:
                continue
            try:
                bins = tuple(float(row[key]) for key in BINS)
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if valid_bins(bins) and bins not in scores:
                missing.add(bins)

        fit_count = 0
        for bins in sorted(missing):
            # density_center delegates to the same frozen scorer used by the
            # existing monthly cache. An unscorable vector is cached as None so
            # later cycles exclude it rather than repeatedly attempting it.
            try:
                center = density_center(bins)
            except (TypeError, ValueError, OverflowError):
                center = None
            if center is not None:
                center = float(center)
                if not math.isfinite(center):
                    center = None
            scores[bins] = center
            sidecar.append({
                "bins": list(bins),
                "score_mean": center,
                "status": "scored" if center is not None else "unscorable_by_frozen_scorer",
                "first_eligible_source_wave": str(wave),
                "inferred_available_date": inferred_available_date(wave).isoformat(),
            })
            fit_count += 1
        fits_by_wave[wave] = fit_count

    return scores, sidecar, fits_by_wave


def build_cycle_prior(donors, roster, *, cutoff, public_anchor, score_cache,
                      seed=SEED, prepared_cache=None, prefilled_new_q9_fits=0):
    """Build one same-ID synthetic joint prior for a newly public SCE anchor.

    Args:
        donors: Old joint-donor DataFrame from the rolling preflight parquet.
        roster: Rows from ``weekly_preflight``'s ``roster_private.json``.
        cutoff: Timezone-aware weekly cutoff string.
        public_anchor: Earlier public release with reference_period,
            published_date, and value_pp. Date-only publication enters the next
            New York day, matching the weekly release protocol.
        score_cache: Exact-bin cache rows or mapping to frozen density means.
        seed: Stable seed for the donor draw and finite-assignment constraint.
        prepared_cache: Optional mutable dict shared across cycle calls. It
            caches past-only scores and donor options by source wave and the
            fixed recipient IDs/weights; anchor-specific calibration still runs
            once for each newly public release.
        prefilled_new_q9_fits: Count of vectors locally scored by the
            prepare_cycles sidecar for this source wave. The pure default is
            strict and never fits a missing vector.

    Returns a JSON-compatible result. On an infeasible finite assignment,
    ``states`` is None and ``status`` is blocked; it never clips or fabricates
    Q9 values.
    """
    point = aware(cutoff)
    cutoff_text = point.isoformat()
    target_month = int(point.astimezone(NY).strftime("%Y%m"))
    anchor_ref = int(str(public_anchor["reference_period"]).replace("-", ""))
    if anchor_ref >= target_month:
        raise ValueError("Only a strictly past public SCE anchor may initialize this cycle")
    if known_from(public_anchor) > point:
        raise ValueError("Public SCE anchor was not yet known at the weekly cutoff")
    anchor_value = public_anchor.get("value_pp")
    if (isinstance(anchor_value, bool) or not isinstance(anchor_value, (int, float))
            or not math.isfinite(anchor_value)):
        raise ValueError("Finite published Q9 headline required")
    if type(prefilled_new_q9_fits) is not int or prefilled_new_q9_fits < 0:
        raise ValueError("Nonnegative integer prefilled Q9 fit count required")

    if "date" not in donors or "userid" not in donors:
        raise ValueError("Joint donor pool requires date and anonymous userid")
    wave = select_source_wave(donors.date.dropna().unique(), cutoff_text, target_month)
    # This filter deliberately precedes cache lookup, so later rows never enter
    # initialization merely because the downloaded pool contains them.
    past = donors.loc[(donors.date <= wave) & (donors.date < target_month)].copy()
    if past.empty or int(past.date.max()) > wave:
        raise ValueError("Past-only donor-wave filter failed")

    selected = _recipient_rows(roster)
    roster_signature = tuple((row["persona"]["agent_id"], row["analysis_weight"],
                              _canonical_hash(row["persona"]["attributes"]))
                             for row in selected)
    prepared_key = (int(wave), roster_signature)
    cached = prepared_cache.get(prepared_key) if prepared_cache is not None else None
    if cached is None:
        normalized_scores = _score_cache_map(score_cache)
        scoring_month = next_month(wave)
        scored, cache_hits, unscorable_rows, unscorable_vectors = _score_past_only(
            past, normalized_scores, scoring_month)
        options = options_from_old_pool(scored, selected, source_max_month=wave)
        eligible_donor_rows = len(scored)
        if prepared_cache is not None:
            prepared_cache[prepared_key] = {
                "options": deepcopy(options),
                "scoring_cache_hits": cache_hits,
                "unscorable_cache_rows": unscorable_rows,
                "unscorable_cache_vectors": unscorable_vectors,
                "eligible_donor_rows": eligible_donor_rows,
            }
        prepared_options_cache_hit = False
    else:
        options = deepcopy(cached["options"])
        cache_hits = cached["scoring_cache_hits"]
        unscorable_rows = cached["unscorable_cache_rows"]
        unscorable_vectors = cached["unscorable_cache_vectors"]
        eligible_donor_rows = cached["eligible_donor_rows"]
        prepared_options_cache_hit = True

    bands = prior_bands(options, float(anchor_value))
    # Preserve the project's registered ±0.05pp band around the public
    # one-decimal Q9 headline; Q8 remains unconstrained by that headline.
    if not math.isclose(bands["q9"][0], float(anchor_value) - Q9_BAND_HALF_WIDTH_PP,
                        abs_tol=1e-12) or not math.isclose(
            bands["q9"][1], float(anchor_value) + Q9_BAND_HALF_WIDTH_PP, abs_tol=1e-12):
        raise ValueError("Unexpected public Q9 calibration band")
    fit = calibrate(options, bands, max_ratio=4.)
    before = expected_summary(options, calibrated=False)
    after = expected_summary(options, calibrated=True)

    cycle_key = f"{public_anchor['reference_period']}|{public_anchor['published_date']}"
    sampled = draw(options, cycle_key, seed)
    balanced, assignment = balance_joint_draw(
        options, sampled, bands["q9"], month=cycle_key, seed=seed)

    sampled_by_id = {row["agent_id"]: row for row in sampled}
    provenance = {}
    for row in balanced:
        original = sampled_by_id[row["agent_id"]]
        provenance[row["agent_id"]] = {
            "donor_userid_private": row["donor_userid_private"],
            "donor_reference_period": int(row["donor_period"]),
            "donor_age_months_at_target": month_age(target_month, row["donor_period"]),
            "recipient_weight": float(row["weight"]),
            "matching": row["matching"],
            "finite_assignment_changed": (
                original["donor_userid_private"] != row["donor_userid_private"]
                or original["donor_period"] != row["donor_period"]
                or original["q9_bins"] != row["q9_bins"]
                or original["q8"] != row["q8"]
                or original["q9"] != row["q9"]
            ),
        }

    states = None
    status = "blocked_finite_assignment_infeasible"
    if assignment["status"] == "finite_assignment_band_met":
        states = {}
        for row in balanced:
            source_period = int(row["donor_period"])
            row_provenance = provenance[row["agent_id"]]
            states[row["agent_id"]] = {
                "fields": {
                    "q8": {"value": float(row["q8"]), "source_period": source_period,
                           "source_kind": "synthetic_donor"},
                    "q9": {"value": [float(value) for value in row["q9_bins"]],
                           "source_period": source_period, "source_kind": "synthetic_donor"},
                },
                "history_centers": [],
                "center": float(row["q9"]),
                "q9_density_mean_pct": float(row["q9"]),
                "provenance": row_provenance,
                "public_anchor_reference_period": public_anchor["reference_period"],
                "public_anchor_published_date": public_anchor["published_date"],
                "source_wave": str(wave),
                "availability_basis": AVAILABILITY_BASIS,
                "historical_byte_vintage_verified": False,
            }
        status = "ready_synthetic_joint_prior"
    else:
        provenance = {}

    diagnostics = {
        "status": status,
        "cycle_key": cycle_key,
        "cutoff": cutoff_text,
        "target_month": str(target_month),
        "public_anchor": {
            "reference_period": public_anchor["reference_period"],
            "published_date": public_anchor["published_date"],
            "known_from": known_from(public_anchor).isoformat(),
            "value_pp": float(anchor_value),
        },
        "q9_median_band_pp": list(bands["q9"]),
        "q8_national_constraint": None,
        "source_wave": str(wave),
        "source_wave_inferred_available_date": inferred_available_date(wave).isoformat(),
        "availability_basis": AVAILABILITY_BASIS,
        "historical_byte_vintage_verified": False,
        "eligible_donor_rows_before_matching": eligible_donor_rows,
        "scoring_cache_hits": cache_hits,
        "known_unscorable_q9_rows_excluded": unscorable_rows,
        "known_unscorable_q9_vectors_excluded": unscorable_vectors,
        "new_q9_density_fits": prefilled_new_q9_fits,
        "prepared_options_cache_hit": prepared_options_cache_hit,
        "calibration": fit,
        "expected_before": before,
        "expected_after": after,
        "finite_assignment": assignment,
        "states": states,
        "donor_provenance": provenance,
        "limitations": [
            "Source-wave availability uses the declared nine-month lag and does not certify historical byte vintages.",
            "Only the published Q9 national headline constrains the synthetic prior median; Q8 remains joint donor data.",
            "The finite assignment can couple donor choices; the probability-tilt ratio bound does not apply after that constraint.",
        ],
    }
    return {
        "status": status,
        "cycle_key": cycle_key,
        "states": states,
        "donor_provenance": provenance,
        "diagnostics": diagnostics,
        **diagnostics,
    }


def prepare_cycles(roster, points, out):
    """Prepare all 12 release-cycle priors from the frozen weekly inputs.

    ``points`` is the 47-row schedule/inventory output from ``weekly_preflight``;
    only rows marked ``reset_required`` are initialized. All cycle calculations
    finish before the fresh output directory is created, so an infeasible finite
    assignment raises without leaving a partly accepted prior package.
    """
    out = Path(out).resolve()
    output_root = (ROOT / "outputs").resolve()
    if out.exists() or not out.is_relative_to(output_root):
        raise ValueError("Fresh project outputs directory required")
    if len(points) != 47:
        raise ValueError("The registered weekly schedule contains exactly 47 points")
    reset_points = [row for row in points if row.get("reset_required")]
    if len(reset_points) != 12:
        raise ValueError("The registered weekly schedule contains 12 initialization/release cycles")
    if not DONOR_POOL_PATH.is_file() or not SCORE_CACHE_PATH.is_file():
        raise FileNotFoundError("Frozen old joint-donor pool or Q9 score cache is unavailable")

    donor_frame = pd.read_parquet(DONOR_POOL_PATH)
    score_rows = read_json(SCORE_CACHE_PATH)
    prepared_scores, score_sidecar, fits_by_wave = _prefill_missing_scores(
        donor_frame, reset_points, score_rows)
    prepared_cache = {}
    cycles = {}
    charged_waves = set()
    for index, row in enumerate(reset_points, start=1):
        cutoff_dt = aware(row["cutoff"])
        target_month = int(cutoff_dt.astimezone(NY).strftime("%Y%m"))
        source_wave = select_source_wave(
            donor_frame.date.dropna().unique(), cutoff_dt.isoformat(), target_month)
        newly_fitted = fits_by_wave.get(source_wave, 0) if source_wave not in charged_waves else 0
        charged_waves.add(source_wave)
        public_anchor = {
            "reference_period": row["anchor_reference_period"],
            "published_date": row["anchor_published_date"],
            "value_pp": row["anchor_pp"],
        }
        result = build_cycle_prior(
            donor_frame,
            roster,
            cutoff=row["cutoff"],
            public_anchor=public_anchor,
            score_cache=prepared_scores,
            prepared_cache=prepared_cache,
            prefilled_new_q9_fits=newly_fitted,
        )
        if result["status"] != "ready_synthetic_joint_prior" or result["states"] is None:
            raise ValueError(
                f"{result['cycle_key']}: finite joint-donor assignment is infeasible; "
                "weekly package is blocked without numeric repair")
        if row.get("cycle_key") and row["cycle_key"] != result["cycle_key"]:
            raise ValueError("Release schedule cycle key differs from public anchor")
        if result["cycle_key"] in cycles:
            raise ValueError("Duplicate public release-cycle key")

        states = {
            aid: {
                "fields": state["fields"],
                "center": state["center"],
                "provenance": state["provenance"],
            }
            for aid, state in result["states"].items()
        }
        diagnostics = dict(result["diagnostics"])
        diagnostics.pop("states", None)
        diagnostics.pop("donor_provenance", None)
        diagnostics = _jsonable(diagnostics)
        cycles[result["cycle_key"]] = {"states": _jsonable(states), "diagnostics": diagnostics}

    source_paths = (
        DONOR_POOL_PATH,
        SCORE_CACHE_PATH,
        Path(__file__),
        Path(__file__).with_name("recent_b_priors.py"),
        Path(__file__).with_name("recent_b_rolling_preflight.py"),
        Path(__file__).with_name("weekly_release_protocol.py"),
        Path(__file__).with_name("full_a_personal_inputs.py"),
        CODE_ROOT / "studies/sce_inflation_expectations/population/entry_initialization.py",
        CODE_ROOT / "studies/sce_inflation_expectations/experiments/state_continuity_inputs.py",
    )
    source_sha256 = {_source_label(path): sha(path) for path in source_paths}
    for directory in (out, out / "cycles"):
        directory.mkdir()

    cycle_files = {}
    for index, (cycle_key, payload) in enumerate(cycles.items(), start=1):
        safe_key = cycle_key.replace("|", "_").replace("-", "")
        name = f"cycle_{index:02d}_{safe_key}_prior_private.json"
        path = out / "cycles" / name
        dump(path, {"cycle_key": cycle_key, **payload})
        cycle_files[name] = sha(path)

    sidecar_name = "q9_score_cache_sidecar_private.json"
    dump(out / sidecar_name, {
        "schema": "sce_weekly_q9_frozen_score_sidecar/v1",
        "scorer": "state_continuity_inputs.density_center -> score_q9_frozen",
        "new_q9_density_fits": len(score_sidecar),
        "rows": score_sidecar,
    })
    cycle_files[sidecar_name] = sha(out / sidecar_name)
    total_new_fits = sum(fits_by_wave.values())
    dump(out / "manifest.json", {
        "schema": "sce_weekly_release_cycle_priors/v1",
        "status": "prepared_offline_not_dispatchable",
        "cycle_count": len(cycles),
        "roster_count": len(roster),
        "schedule_point_count": len(points),
        "roster_sha256": _canonical_hash(roster),
        "schedule_points_sha256": _canonical_hash(points),
        "source_sha256": source_sha256,
        "files_sha256": cycle_files,
        "new_api_calls": 0,
        "target_truth_opened": False,
        "new_q9_density_fits": total_new_fits,
        "new_Q9_fits": total_new_fits,
        "score_cache_sidecar": sidecar_name,
    })
    return cycles
