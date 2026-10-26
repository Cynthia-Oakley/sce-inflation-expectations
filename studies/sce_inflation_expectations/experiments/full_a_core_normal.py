"""Offline A82 Core/Normal adapter: frozen model answers in, no human answers.

Population attributes and original weights are projected independently. The
answer bank uses the completed generation overlay and its already frozen score
lookup, never the evaluator's person-linked human answers or prior fallbacks.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from ..core_normal_joint import JointAnswer, PointAnswer, JointExpansion
from ..population.monthly_fine_grid import profile, cell, PROFILE_KEYS
from ..evaluation.metrics import compare_distributions
from ..scoring.sce_q9_frozen import provenance
from ..submission_tools.reproduce import no_network
from .frozen_batch import ROOT
from .state_continuity_inputs import FRAME, anonymous_id

MATERIALIZED = ROOT / 'outputs/sce_fullperiod_materialized_20261022_v2'
T0_INPUTS = ROOT / 'outputs/sce_full_a_personal_inputs_20261025_v1'
GENERATION = ROOT / 'outputs/sce_full_a_t0_terminal_20261025_v1/generation_views/view_0001'
EVALUATION = ROOT / 'outputs/sce_full_a_t0_analysis_20261026_v1'
MODEL_SCORES = ROOT / 'outputs/sce_full_a_model_score_projection_20261026_v1'
PROTOCOL = ROOT / 'docs/workstreams/20261026_core_normal_full_a/protocol.json'
FRAME_KEYS = {'id', 'weight', 'entry', *PROFILE_KEYS}
ANSWER_KEYS = {'id', 'q9_bins', 'q9_mean', 'q9_iqr', 'q8'}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def fresh(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh project outputs/ directory required')
    out.mkdir(parents=True)
    return out


def checked(folder, mapping):
    folder = Path(folder).resolve()
    for name, digest in mapping.items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder) or sha(path) != digest:
            raise ValueError('Frozen artifact changed or escaped scope: ' + name)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def entry_pool(status):
    return 'newcomer' if status == 'entrant' else 'returner' if status in {'returning', 'gap_return'} else 'unknown'


def model_record(action, score_cache):
    """Missing/prior-retained/unfittable Q9 never becomes a model donor."""
    record = {'id': action['agent_id'], 'q9_bins': [], 'q9_mean': None, 'q9_iqr': None, 'q8': None}
    quality = Counter()
    if action['field_updated']['q8']:
        point = action['effective_q8']
        if not finite(point) or abs(point) > 100:
            raise ValueError('Q8 differs from the frozen legal support')
        record['q8'] = point
    else:
        quality['q8_not_model_output'] += 1
    if action['field_updated']['q9']:
        bins = action['effective_q9_bins']; score = score_cache.get(tuple(bins))
        if score is None:
            raise ValueError('Missing frozen Q9 score; refitting is forbidden here')
        if finite(score.get('mean')) and finite(score.get('iqr')) and score['iqr'] >= 0:
            record.update(q9_bins=bins, q9_mean=score['mean'], q9_iqr=score['iqr'])
        else:
            quality['q9_unfittable_model_output'] += 1
    else:
        quality['q9_not_model_output'] += 1
    return record, quality


def build_banks(people, selected, records, tau):
    if any(set(p) - FRAME_KEYS for p in people) or any(set(a) - ANSWER_KEYS for a in records):
        raise ValueError('Outcome-free population and model-answer field whitelists required')
    core_ids = [r['id'] for r in selected]
    if len(core_ids) != len(set(core_ids)) or {a['id'] for a in records} != set(core_ids):
        raise ValueError('Exactly one record per selected Core required')
    weights = {r['id']: r['poststratified_weight'] for r in selected}
    q9, q8 = [], []
    for record in records:
        if record['q8'] is not None:
            q8.append(PointAnswer(record['id'], record['q8']))
        if record['q9_mean'] is not None:
            q9.append(JointAnswer(record['id'], tuple(record['q9_bins']), record['q9_mean'],
                                  record['q9_iqr'], record['q8']))
    return {name: JointExpansion(people, core_ids, answers, weights, prior_strength=tau)
            for name, answers in [('q9', q9), ('q8', q8)]}


def prepare(out):
    protocol = read(PROTOCOL)
    if protocol['new_API_calls'] != 0 or protocol['tau_candidates'] != [0, 8, 24]:
        raise ValueError('Unexpected offline protocol')
    from ..evaluation.full_a_personal import validate_completed_view
    receipt, _ = validate_completed_view(GENERATION)
    if receipt['planned_calls'] != 41970 or not receipt['actual_model_results']:
        raise ValueError('Only the completed frozen T0 A82 overlay is accepted')
    sm = read(MODEL_SCORES / 'manifest.json'); checked(MODEL_SCORES, sm['files_sha256'])
    # Hash verification of the projection's evaluation-side sources is separate
    # from parsing questionnaire values. Mixed cache contents are never parsed
    # or supplied to either the posterior or parameter selection here.
    checked(ROOT, sm['source_sha256'])
    from .full_a_personal_terminal import _validate_input
    _validate_input(T0_INPUTS)
    projection = read(MODEL_SCORES / 'summary.json')
    if (projection['status'] != 'exported_frozen_scores_for_verified_model_vectors_only'
            or projection['origin_validation_performed'] is not True
            or projection['generation_manifest_sha256'] != sha(GENERATION / 'manifest.json')
            or projection['input_manifest_sha256'] != sha(T0_INPUTS / 'manifest.json')
            or projection['scorer'] != provenance()):
        raise ValueError('A raw-bound model-only score projection is required')
    cache = {tuple(x['bins']): x['score'] for x in read(MODEL_SCORES / 'model_scores_private.json')}
    actions = defaultdict(dict)
    quality = Counter()
    for line in (GENERATION / 'logical_actions_private.jsonl').open():
        action = json.loads(line)
        if action['arm'] != 'T0' or action['repeat'] != 1:
            raise ValueError('Only one-generation T0 actions are supported')
        month, uid = str(action['month']), action['agent_id']
        if uid in actions[month]:
            raise ValueError('Duplicate Core action')
        record, q = model_record(action, cache)
        actions[month][uid] = record; quality.update(q)
    # Strict projection: no Q8/Q9, historical answers or current answer validity.
    frame = pd.read_parquet(FRAME, columns=['date', 'userid', 'weight'])
    if frame.duplicated(['date', 'userid']).any():
        raise ValueError('Duplicate source population identity')
    out = fresh(out); write(out / 'protocol.json', protocol)
    sources = {str(p.relative_to(ROOT)): sha(p) for p in [PROTOCOL, FRAME,
        GENERATION / 'manifest.json', GENERATION / 'receipt.json',
        GENERATION / 'logical_actions_private.jsonl', MODEL_SCORES / 'manifest.json',
        MODEL_SCORES / 'summary.json', MODEL_SCORES / 'model_scores_private.json', Path(__file__),
        ROOT / 'studies/sce_inflation_expectations/core_normal_joint.py',
        ROOT / 'studies/sce_inflation_expectations/population/monthly_fine_grid.py']}
    monthly = []
    for month in sorted(actions):
        month_sources = [MATERIALIZED / month / n for n in ('population.json', 'population_state_private.json')]
        month_sources += [T0_INPUTS / month / n for n in ('weights_private.json', 'roster_private.json')]
        pop, entry, weights, roster = map(read, month_sources)
        part = frame.loc[frame.date.eq(int(month))]
        raw = {anonymous_id(r.userid, entry['anon_salt']): float(r.weight)
               for r in part.itertuples(index=False)}
        people_ids = {p['agent_id'] for p in pop['personas']}
        if len(people_ids) != len(pop['personas']) or people_ids != set(raw):
            raise ValueError('Full-wave population and original weights differ: ' + month)
        entries = {r['agent_id']: r for r in entry['persons']}
        if people_ids != set(entries) or set(weights) != set(actions[month]):
            raise ValueError('Population/Core/entry identity coverage differs')
        people, missing = [], []
        for person in pop['personas']:
            uid = person['agent_id']; w = raw[uid]
            row = dict(id=uid, weight=w if finite(w) and w > 0 else None,
                       entry=entry_pool(entries[uid]['survey_entry_status']), **profile(person['attributes']))
            (people if row['weight'] is not None else missing).append(row)
        by_id = {r['id']: r for r in people}
        if not set(weights) <= set(by_id):
            raise ValueError('A selected Core lacks a valid source population weight')
        selected = []
        for uid, w in weights.items():
            if not math.isclose(w['raw_survey_weight'], by_id[uid]['weight'], rel_tol=1e-12):
                raise ValueError('Core original weight differs from full population')
            key = '|'.join(by_id[uid][k] for k in PROFILE_KEYS) if all(by_id[uid][k] is not None for k in PROFILE_KEYS) else 'unknown'
            if key != w['profile_cell']:
                raise ValueError('Core grid profile changed')
            selected.append({'id': uid, 'poststratified_weight': w['analysis_weight']})
        whole_mass, sample_mass = defaultdict(float), defaultdict(float)
        for person in people:
            key = tuple(person[k] for k in PROFILE_KEYS)
            key = key if all(x is not None for x in key) else 'unknown'
            whole_mass[key] += person['weight']
        for row in selected:
            person = by_id[row['id']]; key = tuple(person[k] for k in PROFILE_KEYS)
            key = key if all(x is not None for x in key) else 'unknown'
            sample_mass[key] += row['poststratified_weight']
        if set(whole_mass) != set(sample_mass) or any(not math.isclose(whole_mass[k], sample_mass[k], rel_tol=1e-10, abs_tol=1e-12) for k in whole_mass):
            raise ValueError('Core calibrated weights do not recover full positive grid masses')
        payload = dict(month=month, people=people, missing_weight_people=missing, selected=selected,
                       answers=[actions[month][uid] for uid in sorted(actions[month])])
        # Fail closed on unsupported entry pools before any parameter selection.
        banks = build_banks(people, selected, payload['answers'], 0)
        sub = out / month; sub.mkdir(); write(sub / 'inputs_private.json', payload)
        roster_rows = list(roster['rows'].values()) if isinstance(roster['rows'], dict) else roster['rows']
        if {r['agent_id'] for r in roster_rows if r['eligible']} != set(actions[month]):
            raise ValueError('Eligible dated roster differs from the frozen model Core')
        excluded = [r for r in roster_rows if not r['eligible']]
        monthly.append(dict(month=month, target_frame_n=len(people) + len(missing),
            weighted_frame_n=len(people), missing_weight_n=len(missing), core_n=len(selected),
            normal_n=len(people) + len(missing) - len(selected), weighted_normal_n=len(people) - len(selected),
            population_mass=sum(r['weight'] for r in people),
            valid_q9_model_donors=len(banks['q9'].answers), valid_q8_model_donors=len(banks['q8'].answers),
            excluded_personal_date_Core_now_statistical_Normal=len(excluded),
            entry_counts=dict(Counter(r['entry'] for r in people)),
            core_entry_counts=dict(Counter(by_id[r['id']]['entry'] for r in selected))))
        sources.update({str(p.relative_to(ROOT)): sha(p) for p in month_sources})
    if len(monthly) != 82 or sum(r['core_n'] for r in monthly) != 41970:
        raise ValueError('Expected all 82 completed Core months')
    summary = dict(status='prepared_A82_core_normal_without_target_answers', new_api_calls=0,
        new_q9_fits=0, target_answers_read=False, population_columns_projected=['date', 'userid', 'weight'],
        scorer=provenance(), months=monthly, quality=dict(quality), model_only_score_projection=True,
        total_frame_n=sum(r['target_frame_n'] for r in monthly),
        total_weighted_frame_n=sum(r['weighted_frame_n'] for r in monthly),
        total_core_n=sum(r['core_n'] for r in monthly),
        total_normal_n=sum(r['normal_n'] for r in monthly))
    write(out / 'summary.json', summary)
    write(out / 'manifest.json', dict(source_sha256=sources,
        files_sha256={str(p.relative_to(out)): sha(p) for p in out.rglob('*.json')}, new_api_calls=0))
    return summary


def holdout_split(people, selected, records, *, seed, month, fraction):
    """Within entry/profile cells, retain at least one valid training donor."""
    pp = {r['id']: r for r in people}; rr = {r['id']: r for r in records}
    weights = {r['id']: r['poststratified_weight'] for r in selected}
    groups = defaultdict(list)
    for uid in weights:
        if rr[uid]['q9_mean'] is not None:
            groups[(pp[uid]['entry'], *(pp[uid][k] for k in PROFILE_KEYS))].append(uid)
    held = []
    for key, ids in groups.items():
        ordered = sorted(ids, key=lambda uid: hashlib.sha256(f'{seed}:{month}:{uid}'.encode()).digest())
        n = min(len(ids) - 1, max(1, int(len(ids) * fraction))) if len(ids) > 1 else 0
        held.extend(ordered[:n])
    held = set(held); training = [r for r in selected if r['id'] not in held]
    # Correct training weights to the original observed-Core design mass in each
    # entry/profile group. Human population targets/outcomes play no role here.
    def group(uid):
        return (pp[uid]['entry'], *(pp[uid][k] for k in PROFILE_KEYS))
    full_mass, train_mass = defaultdict(float), defaultdict(float)
    for uid, w in weights.items(): full_mass[group(uid)] += w
    for row in training: train_mass[group(row['id'])] += row['poststratified_weight']
    training = [dict(r, poststratified_weight=r['poststratified_weight'] *
                    full_mass[group(r['id'])] / train_mass[group(r['id'])]) for r in training]
    return training, sorted(held)


def holdout_weights(people, selected, records, held):
    """Correct unequal held-out fractions; singleton groups stay unvalidated."""
    pp = {r['id']: r for r in people}; rr = {r['id']: r for r in records}
    ww = {r['id']: r['poststratified_weight'] for r in selected}
    def key(uid):
        return (pp[uid]['entry'], *(pp[uid][k] for k in PROFILE_KEYS))
    full, sampled = defaultdict(float), defaultdict(float)
    for uid, w in ww.items():
        if rr[uid]['q9_mean'] is not None: full[key(uid)] += w
    for uid in held:
        if rr[uid]['q9_mean'] is None: raise ValueError('Holdout needs a valid model answer')
        sampled[key(uid)] += ww[uid]
    weights = {uid: ww[uid] * full[key(uid)] / sampled[key(uid)] for uid in held}
    return weights, dict(represented_valid_Core_mass_fraction=sum(full[k] for k in sampled) / sum(full.values()),
                         evaluated_profile_entry_groups=len(sampled), valid_profile_entry_groups=len(full))


def select_tau(inputs, protocol):
    validations = []
    for info in read(inputs / 'summary.json')['months']:
        month = info['month']
        if not protocol['development'][0] <= month <= protocol['development'][1]: continue
        payload = read(inputs / month / 'inputs_private.json')
        pp = {r['id']: r for r in payload['people']}
        rr = {r['id']: r for r in payload['answers']}
        valid_selected = [r for r in payload['selected'] if rr[r['id']]['q9_mean'] is not None]
        valid_records = [rr[r['id']] for r in valid_selected]
        ww = {r['id']: r['poststratified_weight'] for r in valid_selected}
        # The holdout population consists solely of already-observed LLM Core,
        # with its calibrated design mass, not contemporaneous human answers.
        pop = [dict(pp[uid], weight=w) for uid, w in ww.items()]
        for seed in protocol['holdout_seeds']:
            train, held = holdout_split(pop, valid_selected, valid_records,
                seed=seed, month=month, fraction=protocol['holdout_fraction'])
            if not held: raise ValueError('No valid model-only holdout')
            hw, coverage = holdout_weights(pop, valid_selected, valid_records, held)
            evaluation_pop = [dict(p, weight=hw.get(p['id'], p['weight'])) for p in pop]
            records = [rr[r['id']] for r in train]
            for tau in protocol['tau_candidates']:
                bank = build_banks(evaluation_pop, train, records, tau)['q9']
                mass = bank.atom_weights(held)
                comparison = compare_distributions([a.q9_mean for a in bank.answers], mass,
                    [rr[uid]['q9_mean'] for uid in held], [hw[uid] for uid in held])
                validations.append(dict(month=month, seed=seed, tau=tau, heldout_n=len(held),
                    training_n=len(train), center_absolute_error_pp=comparison['median_error_pp'],
                    w1_pp=comparison['w1_pp'], iqr_absolute_error_pp=comparison['iqr_error_pp'], **coverage))
    scores = []
    for tau in protocol['tau_candidates']:
        rows = [r for r in validations if r['tau'] == tau]
        if len(rows) != 48 * len(protocol['holdout_seeds']):
            raise ValueError('Early 48-month validation support changed')
        scores.append(dict(tau=tau, validation_cells=len(rows),
            center_mae_pp=float(np.mean([r['center_absolute_error_pp'] for r in rows])),
            w1_pp=float(np.mean([r['w1_pp'] for r in rows])),
            iqr_mae_pp=float(np.mean([r['iqr_absolute_error_pp'] for r in rows]))))
    best = min(scores, key=lambda r: (round(r['center_mae_pp'], 12), round(r['w1_pp'], 12), r['tau']))
    return dict(status='frozen_by_early_model_only_holdout', selected_tau=best['tau'], candidates=scores,
        cells=validations, target='withheld existing LLM answers only, no human outcomes',
        development=protocol['development'], late_period_used_for_selection=False,
        loss='mean monthly/seed median absolute error, W1 tie-break, then smaller tau')


def draw_payload(bank, key, seed, month, uid):
    k = int.from_bytes(hashlib.sha256(f'{seed}:{month}:{uid}'.encode()).digest()[:8], 'big')
    probabilities = bank.conditional(key)[0]
    answer = bank.answers[int(np.random.default_rng(k).choice(len(bank.answers), p=probabilities))]
    return str(answer.id), answer.payload()


def predict(inputs, out):
    inputs = Path(inputs).resolve(); m = read(inputs / 'manifest.json')
    checked(inputs, m['files_sha256']); checked(ROOT, m['source_sha256'])
    prepared = read(inputs / 'summary.json'); protocol = read(inputs / 'protocol.json')
    if prepared['target_answers_read'] or prepared['new_api_calls']:
        raise ValueError('Prediction preparation must exclude target answers and API calls')
    out = fresh(out); write(out / 'protocol.json', protocol)
    selection = select_tau(inputs, protocol)
    # Freeze selection on disk before full-population predictions or evaluation.
    write(out / 'parameter_selection.json', selection)
    selected_tau = selection['selected_tau']; monthly = []
    for info in prepared['months']:
        month = info['month']; data = read(inputs / month / 'inputs_private.json')
        pp = {r['id']: r for r in data['people']}; ss = {r['id']: r for r in data['selected']}
        banks_by_tau = {tau: build_banks(data['people'], data['selected'], data['answers'], tau)
                        for tau in protocol['tau_candidates']}
        banks = banks_by_tau[selected_tau]
        artifact = dict(month=month,
            q9_atoms=[{'id':str(a.id), **a.payload()} for a in banks['q9'].answers],
            q8_atoms=[{'id':str(a.id), **a.payload()} for a in banks['q8'].answers], by_tau={})
        audit = {}
        for tau, pair in banks_by_tau.items():
            artifact['by_tau'][str(tau)] = {name + '_mass': bank.atom_weights().tolist()
                                          for name, bank in pair.items()}
            audit[str(tau)] = {name: bank.report() for name, bank in pair.items()}
            for bank in pair.values():
                if not math.isclose(bank.atom_weights().sum(), info['population_mass'], rel_tol=1e-10, abs_tol=1e-12):
                    raise ValueError('Population mass not integrated exactly once')
        artifact['core_actual_only'] = {name + '_mass': [ss[str(a.id)]['poststratified_weight'] for a in bank.answers]
                                        for name, bank in banks.items()}
        sub = out / month; sub.mkdir(); write(sub / 'atoms_private.json', artifact)
        # Every actual survey row is materialized, including missing-weight rows.
        # A fixed-seed draw is for inspection only; main metrics integrate atoms.
        counts = Counter()
        with (sub / 'expanded_population_private.jsonl').open('w') as stream:
            for person in [*data['people'], *data['missing_weight_people']]:
                uid = person['id']; core = uid in ss
                row = dict(id=uid, month=month, simulation_role='core' if core else 'statistical_Normal',
                    original_weight=person['weight'], included_in_weighted_metrics=person['weight'] is not None,
                    synthetic_draw_for_inspection_only=not core, fields={})
                for name, bank in banks.items():
                    if uid in bank._donor_index:
                        answer = bank.answers[bank._donor_index[uid]]
                        row['fields'][name] = dict(source='actual_LLM_output', donor_id=uid, **answer.payload())
                    else:
                        key = (person['entry'], *(person[k] for k in PROFILE_KEYS))
                        donor, payload = draw_payload(bank, key, protocol['normal_draw_seed'], month, uid)
                        row['fields'][name] = dict(source='statistical_posterior_draw', donor_id=donor, **payload)
                # For Normal both marginal draws are separately labeled. A Q9
                # atom preserves its original paired Q8, distinct from the Q8 bank.
                counts[row['simulation_role']] += 1
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
        if sum(counts.values()) != info['target_frame_n'] or counts['core'] != info['core_n']:
            raise ValueError('Materialized rows do not equal the actual survey frame')
        monthly.append(dict(info, tau_support=audit, actual_materialized_rows=sum(counts.values())))
        if len(monthly) % 12 == 0: print(f'{month}: offline expansion {len(monthly)}/82', flush=True)
    summary = dict(status='completed_full_a_core_normal_prediction', selected_tau=selected_tau,
        tau_candidates=protocol['tau_candidates'], months=monthly, new_api_calls=0, new_q9_fits=0,
        target_answers_read=False, model_only_score_projection=True, parameter_selection_source='early48_withheld_LLM_only',
        total_frame_n=prepared['total_frame_n'], total_weighted_frame_n=prepared['total_weighted_frame_n'],
        total_core_n=prepared['total_core_n'], total_normal_n=prepared['total_normal_n'],
        quality=prepared['quality'], primary_statistics='Exact posterior-mean CDF atom integration; not a random roster realization',
        limitations=['Normal adds no independent LLM evidence or recovered individual historical beliefs.',
            'Four-dimensional demographic matching is not conditioning on personal prior beliefs or exact news cutoffs.',
            'All original full-wave profiles are represented; 14 excluded date-Core records now receive statistical predictions, not personally dated LLM simulations.',
            'Missing source weights remain null and do not enter weighted metrics.',
            'Core invalid Q9 fields are predicted, never promoted as LLM donors or retained-prior evidence.',
            'Fixed-seed row draws are inspection outputs; Q8 marginal and Q9 joint banks are labeled separately and not claimed to define one fully modeled joint population.',
            'The historical late period was previously inspected; not a new blind validation.'])
    write(out / 'summary.json', summary)
    write(out / 'manifest.json', dict(new_api_calls=0, input_manifest_sha256=sha(inputs / 'manifest.json'),
        source_sha256={str(p.relative_to(ROOT)): sha(p) for p in [inputs / 'manifest.json', Path(__file__),
            ROOT / 'studies/sce_inflation_expectations/core_normal_joint.py']},
        files_sha256={str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()}))
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare'); prep.add_argument('--out', type=Path, required=True)
    pred = sub.add_parser('predict'); pred.add_argument('--inputs', type=Path, required=True); pred.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    with no_network():
        result = prepare(args.out) if args.command == 'prepare' else predict(args.inputs, args.out)
    print(json.dumps({k: v for k, v in result.items() if k not in {'months', 'scorer'}}, ensure_ascii=False))


if __name__ == '__main__': main()
