"""Outcome-free weekly roster and full-window inventory, never a live runner.

Keep the completed monthly sources immutable. The 300-person roster is a
second-stage sample of the fixed 512-person root, with explicit poststratified
weights. No previous model answer or recent target outcome selects a person.
"""
from collections import Counter, defaultdict
import calendar
from pathlib import Path

from .frozen_batch import ROOT, read_json, dump, sha
from .full_a_personal_inputs import _food_snapshot, _policy_snapshot
from .fullperiod_materialization import news_pool_for_prompts
from .media_mechanism_trial import is_sce_report, text_of
from .recent_b_news_refresh import _load_labels, _news_pools, B_SCE_PATTERN
from .recent_b_sampled_dates import BASE, load_repair, merge_labels, archive_view, archive_screen
from .weekly_design import weekly_cutoffs
from .weekly_release_protocol import aware, schedule, score_cutoffs
from ..coverage_preparation import latest_wave, previous_month
from ..population.grid_sampling import plan_core, draw_core
from ..news_selection_trial import RecallRules, RULE_FILE
from ..submission_tools.reproduce import no_network

RUN = ROOT / 'outputs/sce_recent_b_recursion_terminal_20261026_v2'
PE = ROOT / 'outputs/sce_recent_b_recursion_terminal_20261026_v1/PE'
REPAIR = ROOT / 'outputs/sce_recent_b_news_repair_20261026_v1/repair_manifest.json'
RELEASES = ROOT / 'data/evaluation/sce_recent_b_evaluation_20261025_v1/aggregate_inputs.json'
MONTHS = ['202511', '202512', *[f'2026{m:02}' for m in range(1, 10)]]
SEED = 20261026


def roster(weights, n=300, *, seed=SEED, minimum=2):
    """Preserve every occupied root grid's mass, not its individual responses."""
    frame = [dict(id=aid, cell=row['stratum'], weight=row['analysis_weight'])
             for aid, row in sorted(weights.items())]
    plan = plan_core(frame, n, minimum=minimum)
    selected = draw_core(frame, plan, seed=seed, month='weekly_fixed_root')
    mass = defaultdict(float)
    for row in selected:
        mass[row['cell']] += row['poststratified_weight']
    total = plan['population_weight_total']
    error = max(abs(mass[k] - c['population_mass']) / total for k, c in plan['cells'].items())
    w = [r['poststratified_weight'] for r in selected]
    return selected, dict(plan=plan, seed=seed, maximum_cell_fraction_error=error,
                         total_analysis_mass=sum(w), effective_sample_size=sum(w)**2/sum(v*v for v in w),
                         source='second-stage SRS within the fixed 512 root; not a new draw from all SCE records',
                         limitation='Exact grid mass does not guarantee unchanged within-cell distribution or median.')


def news_inventory(raw, labels, cutoff):
    """Future and SCE-answer stories never become missing-label requests."""
    eligible = [r for r in raw if aware(r['pub_date']) <= aware(cutoff)]
    missing = {}
    for row in eligible:
        if is_sce_report(row) or B_SCE_PATTERN.search(text_of(row)):
            continue
        if row['new_hits'] and row['article_id'] not in labels:
            missing[row['article_id']] = row
    return eligible, missing


def prepare(out, n=300):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh project outputs directory required')
    sources = {}
    frozen = read_json(RUN / 'package/manifest.json')['source_sha256']

    def load(path):
        path = Path(path).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('Project-local input required')
        name = str(path.relative_to(ROOT)); digest = sha(path)
        if name in frozen and frozen[name] != digest:
            raise ValueError('Completed monthly source changed: ' + name)
        sources[name] = digest
        return read_json(path)

    with no_network():
        population = load(PE / 'population_private.json')
        weights = load(PE / 'weights_private.json')
        tiers = load(PE / 'tiers_private.json')
        selected, sample = roster(weights, n)
        people = {r['agent_id']: r for r in population['personas']}
        if set(people) != set(weights) or set(tiers) != set(weights):
            raise ValueError('Root identity/weight/tier mismatch')
        releases = load(RELEASES)['headline_releases']
        points = schedule([c for m in MONTHS for c in weekly_cutoffs(m)], releases)
        monthly_protocol = load(ROOT / 'outputs/sce_recent_b_sampled_terminal_20261026_v1/package/protocol.json')
        root_plan = load(ROOT / monthly_protocol['population_preflight'] / 'monthly_input_plan.json')[0]
        if root_plan['month'] != MONTHS[0] or root_plan['inferred_available_date'] >= points[0]['cutoff'][:10]:
            raise ValueError('Root frame is not eligible before the earliest weekly cutoff')
        foods = load(ROOT / 'outputs/sce_fullperiod_materialized_20261022_v2/food_catalog.json')
        policies = load(ROOT / 'data/raw/sce_fullperiod_supplement_20261022/policy_sources_full_v2.json')
        waves = load(ROOT / 'docs/workstreams/20261017_reference_scaleup/confidence_sources.json')['waves']
        waves += load(ROOT / 'data/raw/sce_fullperiod_supplement_20261022/confidence_supplement.json')['waves']
        rules = RecallRules(load(RULE_FILE))
        overrides, extra = load_repair(REPAIR, sources)
        labels = merge_labels(_load_labels(load(BASE / 'summary.json'), sources), extra)
        # Required dates include all preceding calendar months, not just old D.
        required = {}
        for m in MONTHS:
            target = m[:4] + '-' + m[4:]
            prev = previous_month(target)
            required[prev] = calendar.monthrange(int(prev[:4]), int(prev[5:]))[1]
            required[target] = max(required.get(target, 0), int(weekly_cutoffs(m)[-1][8:10]))
        screens = [archive_screen(m, d, overrides, sources) for m, d in sorted(required.items())]
        out.mkdir()
        view, aliases = archive_view(out, required, overrides)
        weekly = []; all_missing = {}; raw_cache = {}
        for month in MONTHS:
            target = month[:4] + '-' + month[4:]
            raw, _, hashes = news_pool_for_prompts(view, target, weekly_cutoffs(month)[-1], rules)
            for name, digest in hashes.items():
                actual = aliases[Path(name).stem]
                if sha(ROOT / actual) != digest:
                    raise ValueError('Archive view identity mismatch')
                sources[actual] = digest
            raw_cache[month] = raw
        for point in points:
            cutoff = point['cutoff']; month = point['target_reference_period'].replace('-', '')
            eligible, missing = news_inventory(raw_cache[month], labels, cutoff)
            all_missing.update(missing)
            foodkey, food = _food_snapshot(foods, cutoff)
            policy = _policy_snapshot(policies, cutoff); confidence = latest_wave(waves, cutoff)
            pool_error = None; pool_audit = None
            if not missing:
                try:
                    _, _, pool_audit = _news_pools(eligible, labels, cutoff, food['food_at_home']['published_at'][:10])
                except ValueError as exc:
                    pool_error = str(exc)
            weekly.append(dict(**point, eligible_archive_articles=len(eligible), missing_base_labels=len(missing),
                news_pool_assembly_checked=not missing and pool_error is None, pool_error=pool_error,
                pool_audit=pool_audit, food_snapshot=foodkey,
                food_published_at=food['food_at_home']['published_at'],
                policy_published_at=policy['published_at'], confidence_wave=confidence['wave_id']))
        ids = {r['id'] for r in selected}
        rows = [dict(persona=people[r['id']], root_weight=weights[r['id']],
                     weekly_design=r, attention_tier=tiers[r['id']]) for r in selected]
        sample['attention_tier_counts'] = dict(Counter(tiers[a] for a in ids))
        latest_policy = max(r['published_at'] for r in policies.values())
        result = dict(status='offline_weekly_roster_and_environment_inventory_not_execution_package',
            n_fixed_households=n, occupied_root_cells=len(sample['plan']['cells']),
            weekly_points=len(points), arithmetic_main_requests=n*len(points),
            calibration_points_including_initial=sum(r['reset_required'] for r in points),
            root_population_source=dict(reference_period=root_plan['old_population_reference_period'],
                inferred_available_date=root_plan['inferred_available_date'],
                availability_basis=root_plan['availability_basis'], historical_byte_vintage_verified=False,
                eligible_before_first_week_under_declared_assumption=True, attributes_fixed_after_root=True),
            roster=sample, archive_months=len(screens),
            archive_day_screen_failures=[r['month'] for r in screens if not r['screen_passed']],
            unique_missing_base_labels=len(all_missing),
            weekly_points_with_missing_labels=sum(bool(r['missing_base_labels']) for r in weekly),
            latest_policy_in_current_catalog=latest_policy,
            known_policy_overlay_pending=dict(publication_date='2026-09-16',
                affected_cutoffs=[r['cutoff'] for r in points if r['cutoff'][:10] > '2026-09-16'],
                source_url='https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm',
                status='previously identified official release; archived facts overlay still required'),
            first_week=points[0],
            live_ready=False, new_API_calls=0, credentials_read=False, recent_personal_truth_read=False,
            monthly_outputs_modified=False, selected_model_responses_read=False,
            pending=['full-week policy overlay (base labels have no gaps)' if not all_missing
                     else 'base-label gaps and full-week policy overlay',
                     '300-person joint donor calibration for each public release cycle',
                     'timestamp-based state and cycle-local history',
                     'seen-news identity memory and finite monthly contact budget',
                     'weekly messages and official Core/replay acceptance',
                     'independent Terminal worker/watch/resume, technical repair and budget',
                     'frozen scoring thresholds and exact paid scope approval'],
            limits=['Archive day presence is a coverage screen, not proof of complete news or historical text vintage.',
                    'Root P inherits declared nine-month publication-lag assumption; exact old byte vintage is unverified.',
                    'Only earlier published anchor values enter the per-week state plan; current targets are not inputs.',
                    'This prepares identities and inventory, not calibrated beliefs, prompts, forecasts or final fees.'])
        dump(out / 'roster_private.json', rows)
        dump(out / 'weekly_environment_inventory.json', weekly)
        dump(out / 'required_news_archives.json', screens)
        dump(out / 'evaluation_clock_plan.json', score_cutoffs(points, releases))
        dump(out / 'missing_public_news_labels.json', list(all_missing.values()))
        dump(out / 'summary.json', result)
        for path in (Path(__file__), ROOT / 'scripts/prepare_sce_weekly_preflight.py',
                     Path(__file__).with_name('weekly_design.py'), Path(__file__).with_name('weekly_release_protocol.py'),
                     ROOT / 'studies/sce_inflation_expectations/population/grid_sampling.py'):
            sources[str(path.relative_to(ROOT))] = sha(path)
        dump(out / 'manifest.json', dict(source_sha256=sources,
            files_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file()},
            new_API_calls=0, live_ready=False))
    return result
