#!/usr/bin/env python3
"""Offline matched contact/price materials; previews only, no live provider/API."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from studies.sce_inflation_expectations.purchase_frequency_matching import (
    prepare_donors, FrequencyAssigner, CATEGORIES, render_frequency)
from studies.sce_inflation_expectations.frequency_price_inputs import extract_prices, render_prices
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
from studies.sce_inflation_expectations.diary_experience import canonical_hash, file_sha256

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'outputs/sce_information_update_trial_20261014_v2'


def dump(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def prepare(out):
    out = out.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'): raise ValueError('fresh ignored directory required')
    donors, raw, audit = prepare_donors(); assigner = FrequencyAssigner(donors)
    manifest = json.loads((BASE / 'manifest.json').read_text())
    links = json.loads((BASE / 'evaluation_links_private.json').read_text())
    if file_sha256(BASE / 'evaluation_links_private.json') != manifest['prepared_file_sha256']['evaluation_links_private.json']:
        raise ValueError('frozen identity sidecar changed')
    stable_keys = {(r['month'], r['agent_id']): canonical_hash(['frequency-person', r['userid']]) for r in links}
    out.mkdir(parents=True); assignments = []; prices = []; previews = []; source_hashes = {}
    for file in ['scripts/prepare_sce_purchase_frequency.py',
                 'studies/sce_inflation_expectations/purchase_frequency_matching.py',
                 'studies/sce_inflation_expectations/frequency_price_inputs.py']:
        source_hashes[file] = file_sha256(ROOT / file)
    for month in [202004, 202105, 202111, 202203]:
        directory = BASE / str(month)
        for name in ['population.json', 'environment.json', 'preview_dated_information.json']:
            path = directory / name
            if file_sha256(path) != manifest['prepared_file_sha256'][f'{month}/{name}']:
                raise ValueError('parent input changed')
            source_hashes[str(path.relative_to(ROOT))] = file_sha256(path)
        pop = json.loads((directory / 'population.json').read_text())['personas']
        environment = json.loads((directory / 'environment.json').read_text()); price = extract_prices(environment); prices.append(price)
        bases = {r['agent_id']: r for r in json.loads((directory / 'preview_dated_information.json').read_text())}
        for person in pop:
            aid = person['agent_id']; assigned = assigner.assign(stable_keys[month, aid], person['attributes'])
            assigned.update(month=month, agent_id=aid, profile=dict(person['attributes']))
            assignments.append(assigned); text = bases[aid]['messages'][0]['content']; marker = 'Question 1 (point estimate):'
            if text.count(marker) != 1 or message_hash(bases[aid]['messages']) != bases[aid]['prompt_sha256']:
                raise ValueError('parent message mismatch')
            neutral = render_prices(price) + render_frequency(assigned, active_rule=False)
            active = render_prices(price) + render_frequency(assigned, active_rule=True)
            if not active.startswith(neutral[:-2]): raise ValueError('data-only treatment differs')
            for arm, addition in [('frequency_data', neutral), ('frequency_rule', active)]:
                before, after = text.split(marker, 1); messages = [{'role': 'user', 'content': before + addition + marker + after}]
                if messages[0]['content'].replace(addition, '', 1) != text: raise ValueError('other mechanism changed')
                if any(k in messages[0]['content'] for k in ['"userid"', '"weight"', 'QSP5', 'MIDUS', '"sex"']): raise ValueError('unapproved preview field')
                previews.append({'month': month, 'agent_id': aid, 'arm': arm,
                                 'messages': messages, 'messages_sha256': message_hash(messages)})
    private = {'assignments_private.json': assignments, 'donors_private.json': donors,
               'prices.json': prices, 'preview_messages_private.json': previews}
    for name, value in private.items(): dump(out / name, value)
    aggregate = {}
    for category in CATEGORIES:
        values = [r['recorded_days_7d'][category] for r in assignments]
        aggregate[category] = {'assigned_day_counts': dict(Counter(values)), 'assigned_mean_days': float(np.mean(values))}
    support = {'matched_field_patterns': dict(Counter(','.join(r['matched_fields']) for r in assignments)),
               'smallest_unique_CU_pool': min(r['pool_unique_units'] for r in assignments),
               'smallest_effective_CU_pool': min(r['pool_effective_units'] for r in assignments),
               'distinct_assigned_CUs': len({r['cu_key'] for r in assignments}),
               'all_vectors_copied_from_single_eligible_CU_week': True}
    result = {'status': 'offline_matched_frequency_and_price_previews_no_live_provider',
              'new_api_calls': 0, 'n_person_months': len(assignments), 'n_preview_messages': len(previews),
              'months': [202004, 202105, 202111, 202203], 'donor_audit': audit,
              'assignment_support': support, 'assigned_categories': aggregate,
              'price_sources': prices, 'source_sha256': source_hashes,
              'files_sha256': {name: file_sha256(out / name) for name in private},
              'baseline_decision': 'Keep the promising time-index C as the common exploratory base for both frequency arms; not a formal main-mechanism upgrade.',
              'limits': ['2020Q4 retrospective donor, not a timely B input; corrected current file.',
                         'Complete supported positive contact subset, not representative of all CE CUs.',
                         'CU-first mean eligible-week weight followed by conditional week draw is a synthetic donor design, not an official CE estimator.',
                         'SCE household vs CE consumer unit and reference person are approximate matches.',
                         'Same-category days, not trips, quantities, annual habits or respondent shopping responsibility.',
                         'Diary contact and existing Interview spending shares come from separate households; no cross-survey person linkage.',
                         'Four narrow sector contacts/prices cover a subset of all spending; no personal inflation index claimed.',
                         'Grooming-service rows have PUB_FLAG=1 in this file; omitted, never interpreted as zero-frequency observations.',
                         'Gender available as CE reference-person sex, not used in matching, prompt or role assignment.',
                         'No live provider, configuration, dry-run gate, new budget or real API calls yet.']}
    dump(out / 'summary.json', result)
    # Keep a complete actual preview available locally; do not commit individual data.
    example = next(r for r in previews if r['month'] == 202111 and r['arm'] == 'frequency_rule')
    (out / 'preview_sample_private.txt').write_text(example['messages'][0]['content']+'\n')
    print(json.dumps({'status': result['status'], 'units': audit['eligible_consumer_units'],
                      'person_months': len(assignments), 'preview_messages': len(previews), 'support': support}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--out', type=Path, required=True)
    prepare(p.parse_args().out)
