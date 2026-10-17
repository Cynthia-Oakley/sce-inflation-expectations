"""GSS HAPPY/SATFIN synthetic joint categories; no SCE current financial facts."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import numpy as np
import pandas as pd
from .block_preparation import prepare_blocks
from .frozen_batch import ROOT, read_json, sha
from ..psychological_profiles import build_sidecars

AUDIT = ROOT/'outputs/household_psychology_20261006T133213Z_6de9a161'
HAPPY = {1: 'very happy', 2: 'pretty happy', 3: 'not too happy'}
SATFIN = {1: 'pretty well satisfied', 2: 'more or less satisfied', 3: 'not satisfied at all'}
EDU = {'college': 'College', 'some_college': 'Some College', 'high_school': 'High School'}
INCOME = {'under_50k': 'Under 50k', '50k_to_100k': '50k to 100k', 'over_100k': 'Over 100k'}


def profiles_from_links(links):
    return pd.DataFrame([{'date': r['month'], 'userid': r['userid'], '_AGE_CAT': r['profile'].get('age_group'),
        '_EDU_CAT': EDU.get(r['profile'].get('education_group')), '_HH_INC_CAT': INCOME.get(r['profile'].get('household_income_band')),
        '_REGION_CAT': r['profile'].get('region')} for r in links])


def render_psychology(record):
    if set(record) != {'HAPPY', 'SATFIN'}: raise ValueError('Only two synthetic psychological categories permitted')
    h, s = record['HAPPY'], record['SATFIN']
    if h is None and s is None: return ''
    if type(h) is not int or h not in HAPPY or type(s) is not int or s not in SATFIN:
        raise ValueError('Valid joint psychological categories required')
    return ('Your personal outlook on life and finances:\n'
            f'Taking life as a whole these days, you feel {HAPPY[h]}.\n'
            f'With your present financial situation, you feel {SATFIN[s]}.\n\n')


def permute_joint(records, month, seed):
    """Retain unsupported people and supported unweighted joint counts exactly."""
    out = deepcopy(records); aids = sorted(a for a, r in records.items() if r['psychological_attributes']['HAPPY'] is not None)
    token = f'{seed}:psychology-permutation:{month}'.encode()
    rng = np.random.default_rng(int.from_bytes(hashlib.sha256(token).digest()[:8], 'big'))
    donors = rng.permutation(aids)
    for aid, donor in zip(aids, donors):
        out[aid] = deepcopy(records[donor])
        out[aid]['permutation_source_agent_id_private'] = donor
    return out


def prepare(out, config):
    if config['mechanism'] != 'synthetic_psychological_state' or config['arms'] != ['matched_psychology', 'permuted_psychology']:
        raise ValueError('Psychological adapter requires matched and permuted arms')
    if config['donor_draw'] != 0 or config['donor_sensitivity_draws'] != 5 or config['min_donor_ess'] != 10:
        raise ValueError('Freeze original matching support and first draw, do not select on target outcomes')
    audit = read_json(AUDIT/'summary.json'); donor_file = AUDIT/'gss2018_candidate_donors.jsonl'
    if sha(donor_file) != audit['candidate_file_hashes'][donor_file.name]: raise ValueError('Audited donor file changed')
    donors = pd.read_json(donor_file, lines=True)
    # Do not pass TRUST, source IDs or donor weights to runtime messages.
    source = [AUDIT/'summary.json', donor_file, ROOT/'docs/PSYCHOLOGICAL_PROFILES_ACCEPTANCE_20261006.md']
    def make_blocks(month, population, links):
        profiles = profiles_from_links(links)
        id_by_user = {r['userid']: r['agent_id'] for r in links}
        draws = []
        for draw in range(config['donor_sensitivity_draws']):
            sampled = build_sidecars(profiles, donors, seed=config['donor_seed'], draw=draw,
                min_ess=config['min_donor_ess'], source_hash=audit['sources']['gss']['sha256'], include_household_state=False)
            draws.append({id_by_user[int(r['agent_id'].split('sce_u')[1])]: r for r in sampled})
        matched = draws[0]; shuffled = permute_joint(matched, month, config['permutation_seed'])
        blocks = {arm: {aid: render_psychology(rec['psychological_attributes']) for aid, rec in records.items()}
                  for arm, records in [('matched_psychology', matched), ('permuted_psychology', shuffled)]}
        def joint(records):
            return dict(Counter(str(r['psychological_attributes']['HAPPY'])+'|'+str(r['psychological_attributes']['SATFIN']) for r in records.values()))
        if joint(matched) != joint(shuffled): raise ValueError('Joint marginal altered by permutation')
        weights = {r['agent_id']: r['design_survey_weight'] for r in links}
        def weighted_joint(records):
            result = Counter()
            for aid, r in records.items():
                q = r['psychological_attributes']; result[f"{q['HAPPY']}|{q['SATFIN']}"] += weights[aid]
            return {k: v/sum(weights.values()) for k, v in result.items()}
        known = [r for r in matched.values() if r['support_status'] == 'synthetic_assigned']
        coverage = {'n': len(links), 'assigned_n': len(known), 'unknown_n': len(links)-len(known),
            'pooled_region_n': sum(r['fallback_tier'] == 1 for r in known), 'min_assigned_ess': min((r['donor_ess'] for r in known), default=None),
            'labels_changed_by_permutation_n': sum(blocks['matched_psychology'][a] != blocks['permuted_psychology'][a] for a in matched),
            'joint_counts': joint(matched), 'weighted_joint_matched': weighted_joint(matched),
            'weighted_joint_permuted': weighted_joint(shuffled),
            'offline_donor_draw_joint_counts': [joint(d) for d in draws],
            'permutation_note': 'Joint unweighted counts and unknown status preserved. Unequal-weight category proportions may differ and are reported; this is a matching placebo, not a pure causal test.'}
        return blocks, {'matched': matched, 'permuted': shuffled}, coverage
    return prepare_blocks(out, config, ROOT/config['reuse_baseline_trial'], make_blocks, source)
