"""Wave-specific state replacement; same recipient roster and psychological text."""
from collections import Counter
from pathlib import Path
import pandas as pd
from .block_preparation import prepare_blocks
from .frozen_batch import ROOT, read_json, sha
from .psychological_state import profiles_from_links, render_psychology, permute_joint
from ..psychological_profiles import build_sidecars


def sample_wave(profiles, donors, wave, source_hash, *, seed, draw, min_ess):
    rows = build_sidecars(profiles, donors, seed=seed, draw=draw, min_ess=min_ess,
                          source_hash=source_hash, include_household_state=False)
    for row in rows:
        row['source_wave'] = wave
        row['temporal_assumption'] = 'Annual/nearest-preceding-wave psychological background; not measured target-month psychology'
    return rows


def prepare(out, config):
    if config['mechanism'] != 'wave_psychological_state' or config['arms'] != ['matched_psychology', 'permuted_psychology']:
        raise ValueError('Wave-specific matched/permuted configuration required')
    if config['donor_draw'] != 0 or config['donor_sensitivity_draws'] != 5 or config['min_donor_ess'] != 10:
        raise ValueError('Do not retune matching/draw thresholds in a source-wave comparison')
    audit_path = ROOT/config['wave_audit']
    audit = read_json(audit_path)
    source = [audit_path, ROOT/'docs/workstreams/20261018_psychological_waves/plan.md']
    pools = {}
    for month in config['months']:
        wave = config['wave_by_month'][str(month)]
        expected = max(int(y) for y in audit['waves'] if int(y) <= month//100)
        if wave != expected: raise ValueError('Use predeclared latest survey-year rule, not outcome-selected waves')
        item = audit['waves'][str(wave)]
        p = ROOT/item['donor_path']
        raw = ROOT/item['source_path']
        if sha(p) != item['donor_sha256'] or sha(raw) != item['source_sha256']:
            raise ValueError('Wave provenance changed')
        pools[wave] = pd.read_json(p, lines=True)
        if not pools[wave].source_wave.eq(wave).all(): raise ValueError('Mixed donor waves')
        source.extend([p, raw])
    def make_blocks(month, population, links):
        wave = config['wave_by_month'][str(month)]
        item = audit['waves'][str(wave)]
        profiles = profiles_from_links(links)
        ids = {r['userid']: r['agent_id'] for r in links}
        draws = []
        for draw in range(config['donor_sensitivity_draws']):
            sampled = sample_wave(profiles, pools[wave], wave, item['source_sha256'], seed=config['donor_seed'],
                                   draw=draw, min_ess=config['min_donor_ess'])
            draws.append({ids[int(r['agent_id'].split('sce_u')[1])]: r for r in sampled})
        matched = draws[0]
        shuffled = permute_joint(matched, month, config['permutation_seed'])
        block = {arm: {aid: render_psychology(row['psychological_attributes']) for aid, row in records.items()}
                 for arm, records in [('matched_psychology', matched), ('permuted_psychology', shuffled)]}
        def joint(records):
            return dict(Counter(f"{r['psychological_attributes']['HAPPY']}|{r['psychological_attributes']['SATFIN']}" for r in records.values()))
        if joint(matched) != joint(shuffled): raise ValueError('Permutation changed joint counts')
        weights = {r['agent_id']: r['design_survey_weight'] for r in links}
        def weighted_joint(records):
            result = Counter()
            for aid, r in records.items():
                q = r['psychological_attributes']; result[f"{q['HAPPY']}|{q['SATFIN']}"] += weights[aid]
            return {k: v/sum(weights.values()) for k, v in result.items()}
        known = [r for r in matched.values() if r['support_status'] == 'synthetic_assigned']
        covariance_diagnostic = []
        for name, records in [('matched', matched), ('permuted', shuffled)]:
            covariance_diagnostic.append({'arm': name, 'weighted_joint': weighted_joint(records)})
        coverage = {'source_wave': wave, 'n': len(links), 'assigned_n': len(known), 'unknown_n': len(links)-len(known),
            'pooled_region_n': sum(r['fallback_tier'] == 1 for r in known),
            'min_assigned_ess': min((r['donor_ess'] for r in known), default=None),
            'joint_counts': joint(matched), 'weighted_joint_diagnostic': covariance_diagnostic,
            'offline_donor_draw_joint_counts': [joint(d) for d in draws],
            'labels_changed_by_permutation_n': sum(block['matched_psychology'][a] != block['permuted_psychology'][a] for a in matched),
            'source_year_distance': month//100-wave,
            'same_year_note': '2022 full-wave fieldwork extends beyond June; annual A proxy, not June measurement or B input' if month == 202206 else 'Adjacent-wave background, not monthly interpolation',
            'matching_fields': ['age 18-39/40-59/60+', 'education', 'nominal prior-year family-income proxy', 'Census four-region; pooled only when ESS<10'],
            'permutation_note': 'Unweighted joint counts preserved; unequal survey weights may change weighted proportions; not a pure causal randomization.'}
        return block, {'matched': matched, 'permuted': shuffled}, coverage
    return prepare_blocks(out, config, ROOT/config['reuse_baseline_trial'], make_blocks, source)
