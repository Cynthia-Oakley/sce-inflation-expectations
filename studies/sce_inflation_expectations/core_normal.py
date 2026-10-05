"""Finite joint-response expansion for the SCE A-line development study.

The plan uses profiles, population weights and valid CORE donor IDs only.
No Normal responses are accepted. It is an empirical shrinkage estimator,
not a claim of exact ConsumerSim replication or a conjugate Bayesian posterior.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math

import numpy as np

from .monthly_analysis import weighted_summary


def profile_cell(attributes):
    employment = attributes.get("employment_status", "unknown")
    coarse = employment if employment in {"employed", "unemployed", "unknown"} else "not_working"
    return (attributes.get("education_group", "unknown"), coarse,
            attributes.get("age_group", "unknown"))


@dataclass
class ExpansionPlan:
    donor_ids: tuple[str, ...]
    core_ids: tuple[str, ...]
    normal_ids: tuple[str, ...]
    cells: dict[str, tuple[str, ...]]
    weights: dict[str, float]
    probabilities: dict[tuple[str, ...], np.ndarray]
    support: dict[tuple[str, ...], dict]
    prior_strength: float

    def atom_weights(self, target_ids=None):
        """Integrate joint donor atoms; no extra Monte Carlo noise in headlines.

        Optional target IDs restrict evaluation AFTER the plan is built. Invalid
        Core answers are excluded explicitly; they are never silently filled.
        """
        targets = set(self.weights) if target_ids is None else set(target_ids)
        if targets - set(self.weights):
            raise ValueError("unknown target IDs")
        mass = np.array([self.weights[u] if u in targets else 0. for u in self.donor_ids])
        group_mass = Counter()
        for uid in self.normal_ids:
            if uid in targets:
                group_mass[self.cells[uid]] += self.weights[uid]
        for cell, weight in group_mass.items():
            mass += weight * self.probabilities[cell]
        return mass

    def sample_normal_donors(self, *, seed=42, month):
        """One joint payload donor per Normal; order and seed are reproducible."""
        rng = np.random.default_rng(np.random.SeedSequence([seed, int(month)]))
        return {uid: self.donor_ids[int(rng.choice(len(self.donor_ids), p=self.probabilities[self.cells[uid]]))]
                for uid in self.normal_ids}

    def report(self):
        normal_weight = sum(self.weights[u] for u in self.normal_ids)
        unsupported = [u for u in self.normal_ids if self.support[self.cells[u]]["fine_donors"] == 0]
        return {"method": "joint_empirical_shrinkage_v1", "prior_strength": self.prior_strength,
                "group_fields": ["education", "coarse_employment", "age"],
                "frame_n": len(self.weights), "core_selected_n": len(self.core_ids),
                "core_joint_valid_donors_n": len(self.donor_ids),
                "core_without_joint_donor_n": len(self.core_ids) - len(self.donor_ids),
                "normal_n": len(self.normal_ids), "normal_without_fine_support_n": len(unsupported),
                "normal_without_fine_support_weight_fraction":
                    sum(self.weights[u] for u in unsupported) / normal_weight if normal_weight else 0.,
                "normal_prior_mass_fraction":
                    sum(self.weights[u] * (1 - self.support[self.cells[u]]["local_fraction"])
                        for u in self.normal_ids) / normal_weight if normal_weight else 0.,
                "group_support": {json.dumps(k): v for k, v in self.support.items()},
                "limitations": ["Shared donors do not add independent information",
                                "Normal assignments are statistical imputations, not recovered individual beliefs",
                                "No cross-month state, no posterior credible intervals, no target-outcome calibration"]}


def build_expansion(population, core_ids, donor_ids, weights, *, prior_strength=5.):
    """Build conditional distributions with leave-fine-cell-out parent pooling.

    Fine cell = education x coarse employment x age. Parent donors first match
    education/employment but have another age, then match education, then use
    all other cells. Parent excludes the local cell to avoid counting its answers
    twice. Local mass = effective donor n / (effective donor n + prior_strength).
    Unsupported cells explicitly fall back; if no outside donor exists, use the
    local distribution. The n/N factor for equal-probability SRS cancels inside
    each conditional distribution. Other sampling designs need their own contract.
    """
    if not math.isfinite(prior_strength) or prior_strength < 0:
        raise ValueError("prior strength must be finite and nonnegative")
    people = population["personas"]
    ids = [p["agent_id"] for p in people]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("population needs unique IDs")
    core, donors = tuple(sorted(core_ids)), tuple(sorted(donor_ids))
    if len(set(core)) != len(core) or len(set(donors)) != len(donors):
        raise ValueError("duplicate Core/donor IDs")
    if not core or set(core) - set(ids) or not donors or set(donors) - set(core):
        raise ValueError("valid donors must be a nonempty subset of selected Core in the population")
    if set(weights) != set(ids) or any(not math.isfinite(float(w)) or float(w) <= 0 for w in weights.values()):
        raise ValueError("need one positive finite population weight per ID")
    weights = {u: float(weights[u]) for u in ids}
    cells = {p["agent_id"]: profile_cell(p["attributes"]) for p in people}
    normal = tuple(sorted(set(ids) - set(core)))
    donor_cells = [cells[u] for u in donors]
    dw = np.array([weights[u] for u in donors])
    probabilities, support = {}, {}
    for cell in sorted({cells[u] for u in normal}):
        fine = np.array([c == cell for c in donor_cells])
        outside = ~fine
        parent, level = outside & np.array([c[:2] == cell[:2] for c in donor_cells]), "same_education_employment_other_age"
        if not parent.any():
            parent, level = outside & np.array([c[0] == cell[0] for c in donor_cells]), "same_education_other_cell"
        if not parent.any():
            parent, level = outside, "global_other_cell"
        local_w = dw[fine]
        ess = float(local_w.sum() ** 2 / (local_w @ local_w)) if fine.any() else 0.
        local_fraction = ess / (ess + prior_strength) if fine.any() else 0.
        if not parent.any():
            local_fraction, level = 1., "local_only_no_parent"
        probability = np.zeros(len(donors))
        if fine.any():
            probability[fine] = local_fraction * local_w / local_w.sum()
        if parent.any():
            probability[parent] = (1 - local_fraction) * dw[parent] / dw[parent].sum()
        if not np.isclose(probability.sum(), 1.):
            raise ValueError("invalid expansion distribution")
        probabilities[cell] = probability
        support[cell] = {"fine_donors": int(fine.sum()), "fine_effective_n": ess,
                         "parent_donors": int(parent.sum()), "parent_level": level,
                         "local_fraction": local_fraction,
                         "normal_target_n": sum(cells[u] == cell for u in normal)}
    return ExpansionPlan(donors, core, normal, cells, weights, probabilities, support, float(prior_strength))


def atom_summary(values, masses, *, point_prediction=False):
    result = weighted_summary(values, masses, interpolate_median=point_prediction)
    # Number of weighted response atoms is not a respondent ESS after expansion.
    result["effective_donor_mass_size"] = result.pop("effective_sample_size", None)
    result["valid_response_atoms"] = result.pop("n_valid")
    return result


def distribution_errors(values, masses, real_values, real_weights, *, point_prediction=False):
    """Distribution-level diagnostics; no pretend Normal-person matching."""
    from scipy.stats import wasserstein_distance
    simulated = atom_summary(values, masses, point_prediction=point_prediction)
    observed = atom_summary(real_values, real_weights, point_prediction=point_prediction)
    return {"median_absolute_error_pp": abs(simulated["weighted_median_pp"] - observed["weighted_median_pp"]),
            "mean_bias_pp": simulated["weighted_mean_pp"] - observed["weighted_mean_pp"],
            "std_bias_pp": simulated["weighted_std_pp"] - observed["weighted_std_pp"],
            "wasserstein_1_pp": float(wasserstein_distance(values, real_values, masses, real_weights)),
            "simulated": simulated, "observed": observed}
