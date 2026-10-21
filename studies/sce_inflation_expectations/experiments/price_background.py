"""A two-arm price-information menu contrast, with no target-answer reads."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re

from pypdf import PdfReader

from .frozen_batch import ROOT, read_json, dump, sha
from .model_migration import validate_transport
from ..model_counterfactual import preflight
from ..prior_belief_experiment import message_hash
from ..procurement_price_views import BASKET, table_text, row_values, validate_cutoff
from ..q9_normalization import POLICY

MONTHS = [202009, 202109, 202206, 202312, 202410, 202503]
ARMS = ['food_background', 'broader_background']
MARKER = 'Additional general price background:\n'


def extract_broader_prices(pages, food):
    """Read YoY NSA in three tables of the SAME archived initial release."""
    tables = {n: table_text(pages, n) for n in (1, 2, 7)}
    facts = {}
    for key, label in [('all_items', 'All items'), ('energy', 'Energy')]:
        one, raw1 = row_values(tables[1], label, 9)
        two, raw2 = row_values(tables[2], label, 6)
        seven, raw7 = row_values(tables[7], label, 2)
        if one[4] != two[1] or one[4] != seven[1]:
            raise ValueError('Three-table YoY disagreement: '+label)
        facts[key] = {k: food[k] for k in (
            'reference_period', 'published_at', 'vintage', 'source_file',
            'source_sha256', 'source_url', 'historical_release_archive')}
        facts[key].update(category=key, label=label, yoy_nsa_percent=one[4],
            unit='percent', adjustment='not seasonally adjusted',
            scope='US city average CPI-U; aggregate public information, not personal receipts',
            source_table=1, exact_extracted_row=raw1,
            crosscheck_table2_row=raw2, crosscheck_table7_row=raw7,
            strict_B_eligible=False)
    return facts


def add_background(messages, facts):
    """Insert exactly one neutral block; preserve every other input byte."""
    if len(messages) != 1 or messages[0]['role'] != 'user':
        raise ValueError('One frozen user message required')
    text = messages[0]['content']
    if text.count(BASKET) != 1 or MARKER in text:
        raise ValueError('Unique insertion boundary and no existing treatment required')
    if set(facts) != {'all_items', 'energy'}:
        raise ValueError('Only the registered two series may enter the treatment')
    a, e = facts['all_items'], facts['energy']
    if (a['reference_period'], a['published_at']) != (e['reference_period'], e['published_at']):
        raise ValueError('Both facts must be from the same release')
    publication = a['published_at']
    pattern = r'^BLS release '+re.escape(publication)+r'; availability relative to your previous survey: (earlier|later|same-day uncertain)\.$'
    statuses = re.findall(pattern, text, re.M)
    if len(statuses) != 1:
        raise ValueError('Same-release recipient-specific timing tag required')
    block = (MARKER
        + f"US CPI-U, all items, reference {a['reference_period']}: 12-month change {a['yoy_nsa_percent']:+.1f}% (not seasonally adjusted).\n"
        + f"US CPI-U, energy, reference {e['reference_period']}: 12-month change {e['yoy_nsa_percent']:+.1f}% (not seasonally adjusted).\n"
        + f"BLS release {publication}; availability relative to your previous survey: {statuses[0]}.\n\n")
    result = deepcopy(messages)
    result[0]['content'] = text.replace(BASKET, block+BASKET, 1)
    if result[0]['content'].replace(block, '', 1) != text:
        raise ValueError('A non-treatment input byte changed')
    return result, block


def prepare(out, config):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('A fresh ignored output directory is required')
    validate_transport(config)
    if (config['mechanism'] != 'price_background_qwen' or config['months'] != MONTHS
            or config['arms'] != ARMS or config['n_per_month'] != 96
            or config['generation_repeats'] != [1, 2] or config['temperature'] != .5
            or config['retry_max'] != 0 or config['max_tokens'] != 1024
            or config['q9_postprocessing'] != POLICY):
        raise ValueError('Registered six-period 96-person two-arm contrast required')
    parent = (ROOT/config['source_trial']).resolve()
    catalog_path = (ROOT/config['source_price_catalog']).resolve()
    metadata = (ROOT/config['provider_metadata']).resolve()
    if not all(p.is_relative_to(ROOT) for p in (parent, catalog_path, metadata)):
        raise ValueError('Local evidence paths required')
    old_manifest = read_json(parent/'manifest.json')
    sources = {}

    def pinned(path, digest=None):
        actual = sha(path)
        if digest is not None and actual != digest:
            raise ValueError('Frozen input drift: '+str(path.relative_to(ROOT)))
        sources[str(path.relative_to(ROOT))] = actual
        return read_json(path)

    pinned(parent/'manifest.json')
    old = pinned(parent/'protocol.json', old_manifest['protocol_sha256'])
    validate_transport(old)
    for k in ('months', 'n_per_month', 'generation_repeats', 'model', 'route',
              'temperature', 'thinking', 'max_tokens', 'request_extra_body', 'allocation_seed'):
        if config[k] != old[k]:
            raise ValueError('Only the price menu may change: '+k)
    catalog = pinned(catalog_path)
    origin = ROOT/old['source_preparation']
    origin_manifest = pinned(origin/'manifest.json')
    origin_summary = pinned(origin/'summary.json', origin_manifest['output_sha256']['summary.json'])
    cutoffs = {r['month']: r['as_of'] for r in origin_summary['inventory']}
    # Catalog must be the one already frozen into the parent preparation chain.
    if old_manifest['source_sha256'].get(str(catalog_path.relative_to(ROOT))) != sha(catalog_path):
        # Original preparation pins its complete outputs rather than each catalog in the paid adapter.
        if catalog_path != origin/'category_prices.json' or origin_manifest['output_sha256'].get('category_prices.json') != sha(catalog_path):
            raise ValueError('Original frozen category catalog required')
    directory = pinned(metadata)
    preflight({'route_candidate':config['route'], 'input_price_per_million':config['price_input_per_mtok'],
               'output_price_per_million':config['price_output_per_mtok']}, directory)
    links = pinned(parent/'evaluation_links_private.json', old_manifest['prepared_file_sha256']['evaluation_links_private.json'])
    truth = ROOT/old['evaluation_truth']
    if sha(truth) != old_manifest['source_sha256'][old['evaluation_truth']]:
        raise ValueError('Frozen evaluation cache drift')
    sources[old['evaluation_truth']] = sha(truth)  # Hash only; do not open target answers.
    out.mkdir(parents=True)
    jobs = []; inventory = []; all_facts = {}; reserve = estimate = 0.; maximum = 0
    for month in MONTHS:
        dest = out/str(month); dest.mkdir()
        for name in ('population.json', 'environment.json', 'simulation.json'):
            value = pinned(parent/str(month)/name, old_manifest['prepared_file_sha256'][f'{month}/{name}'])
            dump(dest/name, value)
        people = read_json(dest/'population.json')['personas']
        ids = {p['agent_id'] for p in people}
        if len(ids) != 96 or len(people) != 96:
            raise ValueError('Original unique 96-person roster required')
        source = pinned(parent/str(month)/'prompts_matched_role.json',
                        old_manifest['prepared_file_sha256'][f'{month}/prompts_matched_role.json'])
        if set(source['rows']) != ids:
            raise ValueError('Original matched-role prompts must cover the same roster')
        food = catalog[str(month)]['food_at_home']; pdf = ROOT/food['source_file']
        if sha(pdf) != food['source_sha256']:
            raise ValueError('Archived initial CPI release changed')
        sources[food['source_file']] = sha(pdf)
        facts = extract_broader_prices([p.extract_text() for p in PdfReader(pdf).pages], food)
        as_of = cutoffs[month]
        validate_cutoff([food, *facts.values()], as_of)
        all_facts[str(month)] = facts
        differences = []
        for arm in ARMS:
            bundle = deepcopy(source); bundle['arm'] = arm
            for row in bundle['rows'].values():
                if arm == 'broader_background':
                    row['messages'], block = add_background(row['messages'], facts)
                    row['prompt_sha256'] = message_hash(row['messages'])
                    differences.append(block)
                elif message_hash(row['messages']) != row['prompt_sha256']:
                    raise ValueError('Original control message hash mismatch')
            dump(dest/f'prompts_{arm}.json', bundle)
            sizes = [len(json.dumps(r['messages'], ensure_ascii=False).encode()) for r in bundle['rows'].values()]
            maximum = max(maximum, *[len(json.dumps(r['messages'], ensure_ascii=False)) for r in bundle['rows'].values()])
            bound = sum(((n+1024)*config['price_input_per_mtok']+1024*config['price_output_per_mtok'])/1e6 for n in sizes)
            guess = sum((n/4*config['price_input_per_mtok']+300*config['price_output_per_mtok'])/1e6 for n in sizes)
            for repeat in (1, 2):
                cap = math.ceil(bound*1e6)/1e6; reserve += cap; estimate += guess
                jobs.append(dict(month=month, arm=arm, repeat=repeat, seed=41+repeat,
                    run_id=f'{out.name}-{month}-{arm}-r{repeat}', cap_usd=cap))
        inventory.append(dict(month=month, reference_period=food['reference_period'], as_of=as_of,
            published_at=food['published_at'], vintage=food['vintage'], source_url=food['source_url'],
            food_yoy_nsa=food['yoy_nsa_percent'], headline_yoy_nsa=facts['all_items']['yoy_nsa_percent'],
            energy_yoy_nsa=facts['energy']['yoy_nsa_percent'], n=96,
            treatment_blocks=len(differences), example_added_block=differences[0]))
    if reserve > config['budget_cap_usd']:
        raise ValueError('Conservative full-batch reservation exceeds cap')
    jobs.sort(key=lambda j: (j['month'], j['repeat'], ARMS.index(j['arm'])))
    protocol = {**config, 'registered_at_utc':datetime.now(timezone.utc).isoformat(),
        'planned_calls':2304, 'max_prompt_chars':maximum+100,
        'provider_metadata_mode':'frozen_batch_catalog', 'evaluation_truth':old['evaluation_truth'],
        'live_scheduler':'Existing per-slot call ledger after all Core dry-runs; no live Core-loop claim.',
        'error_policy':'No retries. Keep isolated connection/timeout failures missing; halt on fatal error or three consecutive transient errors. Any continuation may send only never-attempted frozen slots within the same cap.',
        'primary_metric':'cross_section_w1_pp', 'primary_comparison':ARMS, 'additional_comparisons':[],
        'research_line':'A_conditional_returner_mechanism_development',
        'scientific_rule':'Development signal: all arms >=99% usable/scorable; paired-person W1 difference interval upper bound <0; delta W1 not worse. Report center MAE/RMSE separately; no automatic default upgrade.',
        'macro_center_role':'Report paired raw MAE/RMSE and persistence; do not fit a macro blend on these outcome months.',
        'normalization_rule':'Ten finite nonnegative probabilities with a positive sum are proportionally rescaled to 100 in evaluation only; raw answers and zero masses preserved.',
        'limits':['All six months have been examined; this is a targeted development contrast, not independent validation.',
            'Two public series are one joint information-menu treatment; their separate effects are not identified.',
            'Same nominal model/route, but hosted weight revision and knowledge cutoff are not verified.',
            'Real prior answers, synthetic grocery role and national proxies remain declared A-line conditions.',
            'Old Qwen controls are contextual evidence only; both current arms are generated concurrently.',
            'Two generations are not extra real households; person bootstrap fixes the six calendar months.']}
    dump(out/'protocol.json', protocol); dump(out/'evaluation_links_private.json', links)
    dump(out/'price_facts.json', all_facts); dump(out/'information_diff.json', inventory)
    # Kimi is editing panel/* concurrently; that independent reporting code is not a runtime dependency.
    for path in (ROOT/'studies/sce_inflation_expectations').rglob('*.py'):
        if 'panel' not in path.relative_to(ROOT/'studies/sce_inflation_expectations').parts:
            sources[str(path.relative_to(ROOT))] = sha(path)
    sources['scripts/run_sce_frozen_trial.py'] = sha(ROOT/'scripts/run_sce_frozen_trial.py')
    manifest = dict(jobs=jobs, planned_calls=2304, new_api_calls=0, source_sha256=sources,
        protocol_sha256=sha(out/'protocol.json'),
        prepared_file_sha256={str(p.relative_to(out)):sha(p) for p in out.rglob('*.json')},
        estimated_cost_usd=estimate, conservative_reservation_usd=reserve,
        control_prompt_comparisons_passed=576, treatment_single_block_checks_passed=576,
        current_target_answers_read=False, panel_code_excluded_from_runtime_pins=True)
    dump(out/'manifest.json', manifest)
    dump(out/'authorization.json', dict(approved=False, protocol_sha256=manifest['protocol_sha256'],
        cap_usd=config['budget_cap_usd'], planned_calls=2304, destination=config['destination'], user_confirmation=None))
    print(json.dumps({k:manifest[k] for k in ('planned_calls','estimated_cost_usd','conservative_reservation_usd','new_api_calls')}, indent=2))
    return manifest
