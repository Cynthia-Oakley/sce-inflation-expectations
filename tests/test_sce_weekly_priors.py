import json

import pandas as pd
import pytest

from studies.sce_inflation_expectations.experiments import weekly_priors as mod
from studies.sce_inflation_expectations.experiments.weekly_priors import build_cycle_prior


OLD_BINS = [10.0] * 10
LATER_BINS = [20.0] * 5 + [0.0] * 5


def donor_pool(*, include_uncached_later=True):
    rows = []
    for period in (202411, 202412, 202501, 202502, 202510):
        bins = OLD_BINS if period <= 202501 or not include_uncached_later else LATER_BINS
        for i in range(8):
            rows.append({
                "userid": period * 100 + i,
                "date": period,
                "tenure": 2,
                "weight": 1.0 + i / 10,
                "_AGE_CAT": "Under 40",
                "_EDU_CAT": "College",
                "_HH_INC_CAT": "Under 50k",
                "Q8v2part2": 2.0 + i / 10,
                **{f"Q9_bin{j}": value for j, value in enumerate(bins, 1)},
            })
    return pd.DataFrame(rows)


def fixed_roster():
    return [
        {
            "persona": {
                "agent_id": f"weekly_{i}",
                "attributes": {
                    "age_group": "under_40",
                    "education_group": "college",
                    "household_income_band": "under_50k",
                },
            },
            "weekly_design": {
                "id": f"weekly_{i}",
                "poststratified_weight": weight,
            },
        }
        for i, weight in enumerate((2.0, 1.5, 0.75, 3.25))
    ]


def cache_rows():
    # The later vector is intentionally absent. It must be excluded by the
    # source-wave cutoff before any score-cache lookup is attempted.
    return [{"bins": OLD_BINS, "score": {"mean": 3.4}}]


def anchor(*, reference="2025-09", published="2025-10-07", value=3.4):
    return {
        "reference_period": reference,
        "published_date": published,
        "value_pp": value,
    }


def release_points(*, blocked_last=False, value=3.4):
    releases = [
        ("2025-11-07T23:59:59-05:00", "2025-09", "2025-10-07"),
        ("2025-11-14T23:59:59-05:00", "2025-10", "2025-11-07"),
        ("2025-12-12T23:59:59-05:00", "2025-11", "2025-12-08"),
        ("2026-01-09T23:59:59-05:00", "2025-12", "2026-01-08"),
        ("2026-02-13T23:59:59-05:00", "2026-01", "2026-02-09"),
        ("2026-03-13T23:59:59-04:00", "2026-02", "2026-03-09"),
        ("2026-04-10T23:59:59-04:00", "2026-03", "2026-04-07"),
        ("2026-05-08T23:59:59-04:00", "2026-04", "2026-05-07"),
        ("2026-06-12T23:59:59-04:00", "2026-05", "2026-06-08"),
        ("2026-07-10T23:59:59-04:00", "2026-06", "2026-07-07"),
        ("2026-08-14T23:59:59-04:00", "2026-07", "2026-08-07"),
        ("2026-09-11T23:59:59-04:00", "2026-08", "2026-09-08"),
    ]
    points = []
    for index, (cutoff, reference, published) in enumerate(releases):
        cycle_key = f"{reference}|{published}"
        points.append({
            "cutoff": cutoff,
            "anchor_reference_period": reference,
            "anchor_published_date": published,
            "anchor_pp": 5.0 if blocked_last and index == len(releases) - 1 else value,
            "reset_required": True,
            "cycle_key": cycle_key,
        })
    points.extend({"reset_required": False} for _ in range(35))
    return points


def install_cycle_inputs(monkeypatch, tmp_path, *, blocked_last=False, score_rows=None, value=3.4):
    root = tmp_path / "project"
    (root / "outputs").mkdir(parents=True)
    donor_path = tmp_path / "old_joint_donors.parquet"
    donor_pool(include_uncached_later=False).to_parquet(donor_path, index=False)
    cache_path = tmp_path / "scores.json"
    cache_path.write_text(json.dumps(cache_rows() if score_rows is None else score_rows))
    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "DONOR_POOL_PATH", donor_path)
    monkeypatch.setattr(mod, "SCORE_CACHE_PATH", cache_path)
    return root, donor_path, cache_path, release_points(blocked_last=blocked_last, value=value)


def test_cycle_uses_latest_assumed_available_wave_and_cache_only():
    result = build_cycle_prior(
        donor_pool(), fixed_roster(), cutoff="2025-11-07T23:59:59-05:00",
        public_anchor=anchor(), score_cache=cache_rows(),
    )

    assert result["status"] == "ready_synthetic_joint_prior"
    # January 2025 is month-end + nine months before this cutoff; February is
    # not yet available. The cache-missing future vector was never scored.
    assert result["source_wave"] == "202501"
    assert result["source_wave_inferred_available_date"] == "2025-10-31"
    assert result["new_q9_density_fits"] == 0
    assert result["scoring_cache_hits"] == 24
    assert result["q9_median_band_pp"] == pytest.approx([3.35, 3.45])
    assert set(result["states"]) == {f"weekly_{i}" for i in range(4)}
    json.dumps(result, allow_nan=False)

    for i, expected_weight in enumerate((2.0, 1.5, 0.75, 3.25)):
        aid = f"weekly_{i}"
        state = result["states"][aid]
        assert state["fields"]["q8"]["source_kind"] == "synthetic_donor"
        assert state["fields"]["q9"]["source_kind"] == "synthetic_donor"
        assert state["fields"]["q8"]["source_period"] == 202501
        assert state["fields"]["q9"]["source_period"] == 202501
        assert state["fields"]["q9"]["value"] == OLD_BINS
        assert result["donor_provenance"][aid]["recipient_weight"] == expected_weight
        assert result["donor_provenance"][aid]["donor_reference_period"] == 202501


def test_score_cache_skips_none_and_invalid_rows_but_blocks_missing_required_vector():
    mixed_cache = [
        {"bins": OLD_BINS, "score": {"mean": 3.4}},
        {"bins": LATER_BINS, "score": {"mean": None}},
        {"bins": [0.0] * 10, "score": {"mean": 3.4}},
        {"bins": OLD_BINS, "score": {"mean": float("nan")}},
    ]
    assert mod._score_cache_map(mixed_cache) == {
        tuple(OLD_BINS): 3.4,
        tuple(LATER_BINS): None,
    }
    pool = donor_pool()
    unscorable = pool.iloc[0].to_dict()
    unscorable["date"] = 202501
    unscorable["userid"] = 999999
    unscorable.update({f"Q9_bin{j}": value for j, value in enumerate(LATER_BINS, 1)})
    pool = pd.concat([pool, pd.DataFrame([unscorable])], ignore_index=True)
    ready = build_cycle_prior(
        pool, fixed_roster(), cutoff="2025-11-07T23:59:59-05:00",
        public_anchor=anchor(), score_cache=mixed_cache,
    )
    assert ready["status"] == "ready_synthetic_joint_prior"
    assert ready["new_q9_density_fits"] == 0
    assert ready["known_unscorable_q9_rows_excluded"] == 1
    assert ready["known_unscorable_q9_vectors_excluded"] == 1

    no_cached_vector = []
    with pytest.raises(ValueError, match="absent from the frozen score cache"):
        build_cycle_prior(
            donor_pool(), fixed_roster(), cutoff="2025-11-07T23:59:59-05:00",
            public_anchor=anchor(), score_cache=no_cached_vector,
        )


def test_public_anchor_must_be_available_by_cutoff():
    with pytest.raises(ValueError, match="not yet known"):
        build_cycle_prior(
            donor_pool(), fixed_roster(), cutoff="2025-11-07T23:59:59-05:00",
            public_anchor=anchor(reference="2025-10", published="2025-11-07", value=3.2),
            score_cache=cache_rows(),
        )


def test_same_source_wave_reuses_scored_options_but_recalibrates_new_anchor():
    cache = {}
    first = build_cycle_prior(
        donor_pool(), fixed_roster(), cutoff="2025-11-07T23:59:59-05:00",
        public_anchor=anchor(), score_cache=cache_rows(), prepared_cache=cache,
    )
    second = build_cycle_prior(
        donor_pool(), fixed_roster(), cutoff="2025-11-14T23:59:59-05:00",
        public_anchor=anchor(reference="2025-10", published="2025-11-07", value=3.4),
        score_cache=cache_rows(), prepared_cache=cache,
    )

    assert first["source_wave"] == second["source_wave"] == "202501"
    assert not first["diagnostics"]["prepared_options_cache_hit"]
    assert second["diagnostics"]["prepared_options_cache_hit"]
    assert second["diagnostics"]["new_q9_density_fits"] == 0
    assert second["cycle_key"] == "2025-10|2025-11-07"


def test_infeasible_finite_assignment_is_blocked_without_states():
    result = build_cycle_prior(
        donor_pool(), fixed_roster(), cutoff="2025-11-07T23:59:59-05:00",
        public_anchor=anchor(value=5.0), score_cache=cache_rows(),
    )

    assert result["status"] == "blocked_finite_assignment_infeasible"
    assert result["finite_assignment"]["status"] == "finite_assignment_infeasible"
    assert result["states"] is None
    assert result["donor_provenance"] == {}


def test_prepare_cycles_writes_separate_cycle_files_and_hashes_sources(monkeypatch, tmp_path):
    root, donor_path, cache_path, points = install_cycle_inputs(monkeypatch, tmp_path)
    out = root / "outputs" / "weekly_prior_fixture"
    cycles = mod.prepare_cycles(fixed_roster(), points, out)

    manifest = json.loads((out / "manifest.json").read_text())
    assert len(cycles) == manifest["cycle_count"] == 12
    assert len(manifest["files_sha256"]) == 13
    assert manifest["target_truth_opened"] is False
    assert manifest["new_q9_density_fits"] == 0
    assert manifest["source_sha256"][str(donor_path)]
    assert manifest["source_sha256"][str(cache_path)]
    assert len(list((out / "cycles").glob("*_prior_private.json"))) == 12
    assert all(set(cycle["states"]) == {f"weekly_{i}" for i in range(4)}
               for cycle in cycles.values())


def test_prepare_cycles_scores_truly_missing_vectors_into_new_sidecar(monkeypatch, tmp_path):
    frozen_score = mod.density_center(tuple(OLD_BINS))
    assert frozen_score is not None
    root, _, _, points = install_cycle_inputs(
        monkeypatch, tmp_path, score_rows=[], value=frozen_score)
    out = root / "outputs" / "weekly_prior_cache_extension"

    cycles = mod.prepare_cycles(fixed_roster(), points, out)
    manifest = json.loads((out / "manifest.json").read_text())
    sidecar = json.loads((out / "q9_score_cache_sidecar_private.json").read_text())

    assert len(cycles) == 12
    assert manifest["new_q9_density_fits"] == manifest["new_Q9_fits"] == 1
    assert sidecar["new_q9_density_fits"] == 1
    assert sidecar["rows"][0]["bins"] == OLD_BINS
    assert sidecar["rows"][0]["score_mean"] == pytest.approx(frozen_score)
    assert sum(c["diagnostics"]["new_q9_density_fits"] for c in cycles.values()) == 1


def test_prepare_cycles_fails_before_creating_output_when_any_cycle_is_infeasible(monkeypatch, tmp_path):
    root, _, _, points = install_cycle_inputs(monkeypatch, tmp_path, blocked_last=True)
    out = root / "outputs" / "blocked_fixture"

    with pytest.raises(ValueError, match="blocked without numeric repair"):
        mod.prepare_cycles(fixed_roster(), points, out)
    assert not out.exists()
