"""Reuse completed A and freeze only the new wording/time-index B/C cells."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import math

import numpy as np
import pandas as pd
from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig

from .model import SCEEnvironmentProvider
from .anchor_role_runtime import build_messages as parent_messages
from .information_update_runtime import REF, PROMPT, ARMS, TIME_ROLE_BLOCK, time_index, transform, build_messages
from .behavior_prompt_blocks import ANCHOR_BLOCK
from .prior_belief_experiment import message_hash
from .evaluation.expanded_state import sha, dump

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / 'outputs/sce_anchor_role_trial_20261014_v3'
DATES = ROOT / 'outputs/sce_prior_preparation_20261013_v4/labeled_reference_private.parquet'
OLD_CASES = ROOT / 'outputs/sce_anchor_role_evaluation_20261014_v1/cases_private.json'


def prepare(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('fresh ignored output required')
    parent = json.loads((PARENT / 'manifest.json').read_text())
    for path, digest in parent['source_sha256'].items():
        if sha(ROOT / path) != digest: raise ValueError('parent source changed: ' + path)
    def frozen(name):
        path = PARENT / name
        if sha(path) != parent['prepared_file_sha256'][name]: raise ValueError('parent input changed: ' + name)
        return json.loads(path.read_text())
    oldprotocol = frozen('protocol.json')
    links = frozen('evaluation_links_private.json')
    dates = pd.read_parquet(DATES, columns=['userid', 'date', 'survey_date'])
    if dates.duplicated(['userid', 'date']).any(): raise ValueError('duplicate reference dates')
    lookup = dates.set_index(['userid', 'date'])
    sources = {str((PARENT / 'manifest.json').relative_to(ROOT)): sha(PARENT / 'manifest.json'),
               str(DATES.relative_to(ROOT)): sha(DATES),
               str(OLD_CASES.relative_to(ROOT)): sha(OLD_CASES),
               'scripts/run_sce_information_update_trial.py': sha(ROOT / 'scripts/run_sce_information_update_trial.py'),
               'scripts/run_sce_anchor_role_trial.py': sha(ROOT / 'scripts/run_sce_anchor_role_trial.py')}
    for p in (ROOT / 'studies/sce_inflation_expectations').rglob('*.py'):
        if '__pycache__' not in p.parts and 'evaluation' not in p.relative_to(ROOT / 'studies/sce_inflation_expectations').parts:
            sources[str(p.relative_to(ROOT))] = sha(p)
    reused = [j for j in parent['jobs'] if j['arm'] == 'belief_start']
    for j in reused:
        directory = ROOT / 'outputs/local_runs' / j['run_id']
        run = json.loads((directory / 'run_manifest.json').read_text())
        if run['llm_kind'] != 'openai' or run['cost']['call_count'] != 48:
            raise ValueError('completed real parent A required')
        for name in ['run_manifest.json', 'study.duckdb', 'llm_calls.jsonl']:
            sources[str((directory / name).relative_to(ROOT))] = sha(directory / name)
    out.mkdir(parents=True)
    jobs, audit, dates_private = [], [], []
    estimate = reservation = 0.0
    for month in oldprotocol['months']:
        dest = out / str(month); dest.mkdir()
        env = EnvironmentBundle.model_validate(frozen(f'{month}/environment.json'))
        pop = PopulationBundle.model_validate(frozen(f'{month}/population.json'))
        cfg = SimulationConfig.model_validate(frozen(f'{month}/simulation_belief_start.json'))
        anchor = cfg.decision_args['anchor_role_bundle']
        original = {r['agent_id']: r for r in frozen(f'{month}/preview_belief_start.json')}
        baseline = anchor['base']['baseline']; news = baseline['news']
        current = env.provider_args['targets'][0]['as_of']
        signals = env.provider_args['signals_by_step']['0']
        timing = {}
        chosen = [r for r in links if r['month'] == month]
        y, m = divmod(month, 100); previous_month = (y - 1) * 100 + 12 if m == 1 else y * 100 + m - 1
        for row in chosen:
            prior_date = pd.Timestamp(lookup.loc[(row['userid'], previous_month), 'survey_date'])
            if pd.isna(prior_date) or prior_date.year * 100 + prior_date.month != previous_month:
                raise ValueError('prior survey date/month mismatch')
            day = prior_date.date().isoformat()
            aid = row['agent_id']
            timing[aid], detail = time_index(signals, news['common_news'], news['rows'][aid]['personal_news'],
                                            baseline['policy'], day, current)
            dates_private.append({'month': month, 'agent_id': aid, 'previous_survey_day': day})
            audit.append({'month': month, 'agent_id': aid, **detail})
        if set(timing) != {p.agent_id for p in pop.personas} or len(timing) != 48:
            raise ValueError('same 48-person roster required')
        provider = SCEEnvironmentProvider(env.model_copy(deep=True)); provider.audit_dir = None
        provider.reset(42); provider.advance_to(1)
        observations = provider.observe_batch([p.agent_id for p in pop.personas], 1)
        for arm in ARMS:
            bundle = {'arm': arm, 'parent': deepcopy(anchor), 'time_index_by_id': timing,
                      'messages_sha256': {}}
            previews = []; reserve = 0.0
            for ob in observations:
                old = parent_messages(ob, anchor)
                if message_hash(old) != original[ob.agent_id]['prompt_sha256']:
                    raise ValueError('reused A input mismatch')
                messages = transform(old, arm, timing[ob.agent_id])
                recovered = messages[0]['content'].replace(TIME_ROLE_BLOCK, ANCHOR_BLOCK, 1)
                if arm == 'dated_information': recovered = recovered.replace(timing[ob.agent_id], '', 1)
                if recovered != old[0]['content']: raise ValueError('substantive facts or questionnaire changed')
                text = messages[0]['content']
                if any(term in text for term in ['"userid"', '"weight"', 'Q9_mean', 'QSP5', 'MIDUS', 'sce_u']):
                    raise ValueError('forbidden prompt field')
                bundle['messages_sha256'][ob.agent_id] = message_hash(messages)
                previews.append({'agent_id': ob.agent_id, 'messages': messages, 'prompt_sha256': message_hash(messages)})
                reserve += (len(json.dumps(messages, ensure_ascii=False).encode()) + 256) * .3 / 1e6 + 1024 * 1.2 / 1e6
            for ob in observations: build_messages(ob, bundle)
            newcfg = cfg.model_copy(deep=True); newcfg.decision_ref = REF
            newcfg.decision_args = {'information_update_bundle': bundle, 'prompt_version': PROMPT,
                                   'llm_kind': 'scripted', 'seed': 42, 'max_prompt_chars': 30000}
            dump(dest / f'simulation_{arm}.json', newcfg.model_dump(mode='json'))
            dump(dest / f'preview_{arm}.json', previews)
            for repeat in oldprotocol['generation_repeats']:
                cap = math.ceil((reserve + .000001) * 1e4) / 1e4
                jobs.append({'month': month, 'arm': arm, 'repeat': repeat, 'cap_usd': cap,
                             'run_id': f'{out.name}-{month}-{arm}-r{repeat}'})
                reservation += reserve
                oldjob = next(j for j in reused if j['month'] == month and j['repeat'] == repeat)
                oldcalls = [json.loads(line) for line in (ROOT / 'outputs/local_runs' / oldjob['run_id'] / 'llm_calls.jsonl').read_text().splitlines()]
                newbyid = {r['agent_id']: r for r in previews}
                for call in oldcalls:
                    newbytes = len(json.dumps(newbyid[call['agent_id']]['messages'], ensure_ascii=False).encode())
                    ratio = newbytes / len(call['prompt_text'].encode())
                    estimate += (call['usage']['prompt_tokens'] * ratio * .3 + call['usage']['completion_tokens'] * 1.2) / 1e6
        dump(dest / 'population.json', pop.model_dump(mode='json'))
        dump(dest / 'environment.json', env.model_dump(mode='json'))
        for name in ['population.json', 'environment.json', 'simulation_belief_start.json', 'preview_belief_start.json']:
            sources[str((PARENT / str(month) / name).relative_to(ROOT))] = sha(PARENT / str(month) / name)
    jobs = [jobs[i] for i in np.random.default_rng(20261016).permutation(len(jobs))]
    cap = math.ceil(sum(j['cap_usd'] for j in jobs) * 2) / 2
    protocol = {**oldprotocol, 'id': 'sce-information-update-reuse-v1',
                'registered_at_utc': datetime.now(timezone.utc).isoformat(), 'arms': list(ARMS),
                'wording_block': TIME_ROLE_BLOCK, 'role_block': TIME_ROLE_BLOCK,
                'planned_calls': len(jobs) * 48, 'budget_cap_usd': cap,
                'reused_A_calls': 384, 'reused_A_folder': str(PARENT.relative_to(ROOT)), 'reused_A_arm': 'belief_start',
                'comparison': 'Only B/C newly generated together; old A reused at user request. C differs from B only by a publication-time index.',
                'primary_contrast': 'dated_information minus new_wording on cross-section W1',
                'exploratory_contrast': 'new_wording minus reused_A; contains batch/time drift and is not a clean contemporaneous wording effect',
                'candidate_gate': 'Primary W1 paired-person upper 95% bound < 0; center MAE and delta W1 points no worse; new scorable fraction >=99%. Not overall project success.',
                'date_boundary': 'Prior survey calendar day, New York release dates; same-day unknown response time is ambiguous. No actual prior response date sent.',
                'support': 'Same truth-scorable person-generations with all three A/B/C answers, plus explicit failure coverage.',
                'limits': oldprotocol['limits'] + ['Reused A is an earlier batch; apparent wording gain cannot exclude batch drift.', 'Publication-time tags do not establish real attention or information acquisition.'],
                'truth_isolation': 'No new sampling. Read only userid/date/survey_date for past-date lookup; current answers/weights confined to evaluation sidecar.',
                'no_tuning_after_run': True}
    dump(out / 'protocol.json', protocol); dump(out / 'evaluation_links_private.json', links)
    dump(out / 'previous_dates_private.json', dates_private); dump(out / 'timing_audit_private.json', audit)
    manifest = {'status': 'prepared_awaiting_specific_budget', 'source_sha256': sources,
                'prepared_file_sha256': {str(p.relative_to(out)): sha(p) for p in out.rglob('*.json')},
                'jobs': jobs, 'reused_jobs': reused, 'planned_calls': protocol['planned_calls'], 'reused_calls': 384,
                'sum_job_caps_usd': sum(j['cap_usd'] for j in jobs), 'conservative_reservation_usd': reservation,
                'estimated_peak_cost_usd': estimate, 'proposed_cap_usd': cap, 'new_api_calls': 0,
                'protocol_sha256': sha(out / 'protocol.json')}
    dump(out / 'manifest.json', manifest)
    return manifest
