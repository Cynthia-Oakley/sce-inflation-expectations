"""Opt-in finite joint-answer expansion for a weighted Core/Normal population.

Only Core answers are accepted. Same-entry, leave-local-cell-out neighbours
supply an empirical prior. Noninteger effective sample sizes make this a
weighted empirical-Bayes/pseudo-Dirichlet estimator, not an exact survey
likelihood or a claim of reproducing ConsumerSim's categorical CCI model.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import math

import numpy as np

FOUR_FIELDS = ('education', 'numeracy', 'age', 'income')
FRAME_KEYS = {'id', 'weight', 'entry', *FOUR_FIELDS, 'gender'}


@dataclass(frozen=True)
class JointAnswer:
    id: str
    q9_bins: tuple[float, ...]
    q9_mean: float
    q9_iqr: float
    q8: float | None = None

    def __post_init__(self):
        p = np.asarray(self.q9_bins, float)
        if p.shape != (10,) or not np.isfinite(p).all() or np.any(p < 0) or not np.isclose(p.sum(), 100., atol=1e-7, rtol=0):
            raise ValueError('Joint atom requires ten legal, already normalised Q9 probabilities')
        if not math.isfinite(self.q9_mean) or not math.isfinite(self.q9_iqr) or self.q9_iqr < 0:
            raise ValueError('Cached finite Q9 mean and nonnegative IQR required')
        if self.q8 is not None and (not math.isfinite(self.q8) or abs(self.q8) > 100):
            raise ValueError('Invalid Q8 must be marked missing, independently of Q9')

    def payload(self):
        return {'q9_bins': list(self.q9_bins), 'q9_mean': self.q9_mean,
                'q9_iqr': self.q9_iqr, 'q8': self.q8}


@dataclass(frozen=True)
class PointAnswer:
    """Separate Q8 marginal evidence, including Core with unusable Q9."""
    id: str
    q8: float

    def __post_init__(self):
        if not math.isfinite(self.q8) or abs(self.q8) > 100:
            raise ValueError('Finite legal Q8 point required')

    def payload(self):
        return {'q8': self.q8}


def effective_n(weights):
    w = np.asarray(weights, float)
    return float(w.sum()**2/(w@w)) if len(w) and w.sum() > 0 else 0.


def _frame(records, fields):
    out = {}
    for r in records:
        if set(r) - FRAME_KEYS:
            raise ValueError('Population frame must be outcome-free whitelisted fields only')
        uid = str(r['id'])
        if uid in out:
            raise ValueError('Duplicate population identity')
        weight = r['weight']
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight <= 0:
            raise ValueError('Positive original population weights required, never fill missing by one')
        if r.get('entry') not in {'newcomer', 'returner', 'unknown'}:
            raise ValueError('Explicit survey-entry pool required')
        values = tuple(r.get(k) for k in fields)
        if any(v is not None and not isinstance(v, str) for v in values):
            raise ValueError('Canonical category strings or None required')
        out[uid] = {'id': uid, 'weight': float(weight), 'entry': r['entry'],
                    'profile': values}
    if not out:
        raise ValueError('Empty population')
    return out


class JointExpansion:
    """Finite population: keep observed Core, predict only remaining mass."""

    def __init__(self, population, core_ids, answers, core_weights, *,
                 fields=FOUR_FIELDS, prior_strength=8.):
        if not fields or len(set(fields)) != len(fields) or set(fields) - (FRAME_KEYS-{'id','entry','weight'}):
            raise ValueError('Distinct supported profile fields required')
        if not math.isfinite(prior_strength) or prior_strength < 0:
            raise ValueError('Nonnegative finite prior strength required')
        self.fields = tuple(fields)
        self.population = _frame(population, fields)
        self.core_ids = tuple(sorted(str(u) for u in core_ids))
        if len(self.core_ids) != len(set(self.core_ids)) or not set(self.core_ids) <= self.population.keys():
            raise ValueError('Unique Core subset required')
        self.answers = tuple(sorted(answers, key=lambda a: str(a.id)))
        kinds = {type(a) for a in self.answers}
        if not kinds <= {JointAnswer, PointAnswer} or len(kinds) != 1:
            raise ValueError('One typed answer bank required; Q8 marginal and joint Q9 banks are separate')
        self.bank = 'q9_joint' if JointAnswer in kinds else 'q8_point'
        self.donor_ids = tuple(str(a.id) for a in self.answers)
        self._donor_index = {u:i for i,u in enumerate(self.donor_ids)}
        if not self.answers or len(set(self.donor_ids)) != len(self.donor_ids) or not set(self.donor_ids) <= set(self.core_ids):
            raise ValueError('Only unique Core answers may enter expansion; Normal answers forbidden')
        cw = {str(k): v for k, v in core_weights.items()}
        if set(cw) != set(self.core_ids) or any(not isinstance(v, (int,float)) or isinstance(v,bool) or not math.isfinite(v) or v <= 0 for v in cw.values()):
            raise ValueError('One positive design/calibrated weight per selected Core required')
        self.core_weights = cw
        self.weights = np.array([cw[u] for u in self.donor_ids], float)
        self.tau = float(prior_strength)
        self._cache = {}
        self._profiles = np.array([self.population[u]['profile'] for u in self.donor_ids], dtype=object)
        self._entries = np.array([self.population[u]['entry'] for u in self.donor_ids])
        missing = set(r['entry'] for r in self.population.values()) - set(self._entries)
        if missing:
            raise ValueError('No valid Core donor in entry pool(s): '+', '.join(sorted(missing)))

    def group_key(self, uid):
        r = self.population[str(uid)]
        return (r['entry'], *r['profile'])

    def conditional(self, key):
        """Posterior mean and audit, with parent/local evidence disjoint.

        Parent = most coordinates matched among other fine cells in the same
        survey-entry pool. Coordinates are treated symmetrically. Unknown
        coordinates provide no matching evidence; they are not invented values.
        """
        if key in self._cache:
            return self._cache[key]
        entry, *profile = key
        same_entry = self._entries == entry
        equal = np.column_stack([self._profiles[:, j] == value for j, value in enumerate(profile)])
        local = same_entry & equal.all(axis=1)
        outside = same_entry & ~local
        known = np.array([v is not None for v in profile])
        matches = (equal & known).sum(axis=1)
        maximum = int(matches[outside].max()) if outside.any() else None
        parent = outside & (matches == maximum) if outside.any() else np.zeros(len(local), bool)
        neff = effective_n(self.weights[local])
        local_p = np.zeros(len(local)); parent_p = np.zeros(len(local))
        if local.any():
            local_p[local] = self.weights[local]/self.weights[local].sum()
        if parent.any():
            parent_p[parent] = self.weights[parent]/self.weights[parent].sum()
        if local.any() and parent.any():
            alpha = neff*local_p + self.tau*parent_p
            p = alpha/alpha.sum()
            parent_fraction = self.tau/(self.tau+neff)
        elif local.any():
            alpha, p, parent_fraction = neff*local_p, local_p, 0.
        elif parent.any():
            # tau=0 means no regularisation where data exist, not dropping a
            # population cell with no valid local answer. Explicit prior fallback.
            alpha, p, parent_fraction = max(self.tau, 1.)*parent_p, parent_p, 1.
        else:
            raise ValueError('Unrepresented target entry pool')
        if not np.isclose(p.sum(), 1., atol=1e-12) or np.any(p < 0):
            raise ValueError('Conditional probability failed conservation')
        audit = {'local_core_n': int(local.sum()), 'local_core_ess': neff,
                 'outside_parent_core_n': int(parent.sum()), 'parent_matching_coordinates': maximum,
                 'parent_fraction': float(parent_fraction), 'local_unsupported': not bool(local.any()),
                 'entry_pool': entry, 'parent_local_overlap': int(np.sum(parent & local))}
        self._cache[key] = (p, alpha, audit)
        return self._cache[key]

    def atom_weights(self, target_ids=None, *, preserve_core=True):
        """Exact population integral using original person mass, never w/pi twice.

        Valid Core observations retain their own actual population weights.
        Remaining Normal and invalid-answer Core mass is predicted once. The
        earlier whole-cell predictor is available as an explicit sensitivity.
        """
        ids = list(self.population) if target_ids is None else [str(u) for u in target_ids]
        if not ids or len(set(ids)) != len(ids) or set(ids) - self.population.keys():
            raise ValueError('Nonempty unique population targets required')
        grouped = defaultdict(float)
        mass = np.zeros(len(self.answers))
        for uid in ids:
            w = self.population[uid]['weight']
            if preserve_core and uid in self._donor_index:
                mass[self._donor_index[uid]] += w
            else:
                grouped[self.group_key(uid)] += w
        for key, weight in grouped.items():
            mass += weight*self.conditional(key)[0]
        if not np.isclose(mass.sum(), sum(self.population[u]['weight'] for u in ids), rtol=1e-12):
            raise ValueError('Population mass was lost or Core was counted twice')
        return mass

    def draw_normal(self, *, month, seed):
        """Optional visualisation microdata, whole payloads, not extra evidence."""
        result = {}
        for uid in sorted(self.population.keys()-set(self.core_ids)):
            key_seed = int.from_bytes(hashlib.sha256(f'{seed}:{month}:{uid}'.encode()).digest()[:8], 'big')
            rng = np.random.default_rng(key_seed)
            probability = self.conditional(self.group_key(uid))[0]
            answer = self.answers[int(rng.choice(len(self.answers), p=probability))]
            result[uid] = {'donor_id': str(answer.id), 'source': 'statistical_Normal', **answer.payload()}
        return result

    def report(self, target_ids=None):
        ids = list(self.population) if target_ids is None else [str(u) for u in target_ids]
        total = sum(self.population[u]['weight'] for u in ids)
        unsupported = parent = retained = imputed_core = 0.
        for uid in ids:
            w = self.population[uid]['weight']
            if uid in self._donor_index:
                retained += w
                continue
            if uid in self.core_ids:
                imputed_core += w
            audit = self.conditional(self.group_key(uid))[2]
            unsupported += w*audit['local_unsupported']; parent += w*audit['parent_fraction']
        mass = self.atom_weights(ids)
        return {'method': 'weighted_empirical_bayes_joint_atoms_v1', 'profile_fields': list(self.fields),
                'prior_strength': self.tau, 'target_n': len(ids), 'population_weight_mass': total,
                'selected_core_n': len(self.core_ids), 'answer_bank': self.bank,
                ('valid_q9_core_atoms' if self.bank == 'q9_joint' else 'valid_q8_core_atoms'): len(self.answers),
                'invalid_core_answers_in_this_bank': len(self.core_ids)-len(self.answers),
                'normal_n': len(self.population.keys()-set(self.core_ids)),
                'retained_valid_core_population_fraction': retained/total,
                'imputed_invalid_core_population_fraction': imputed_core/total,
                'unsupported_local_population_fraction': unsupported/total,
                'parent_population_fraction': parent/total,
                'mass_conservation_error': float(abs(mass.sum()-total)),
                'effective_atom_mass_size_not_person_ess': effective_n(mass),
                'limits': ['Empirical parent comes only from other valid Core answers in the same entry pool.',
                           'Weighted effective-count posterior is not an exact survey-sampling likelihood.',
                           'Normal atom integration adds no independent LLM observations.',
                           'No recovery of personal prior dependence or true individual trajectories is implied.',
                           'Missing Q8 stays missing and never invalidates otherwise valid Q9.']}
