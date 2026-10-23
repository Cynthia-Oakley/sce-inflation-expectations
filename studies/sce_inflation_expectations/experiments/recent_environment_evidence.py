"""2025-11 候选环境：显式信息截止 2025-11-13（America/New_York）。

零 API 离线工程。适配自
scripts/build_sce_fullperiod_sample_environments.py 的
build_environment_gap_tolerant：记录布局与硬性守卫（published_at < as_of）
保持一致，但信息截止日、CPI / 就业 / 汽油各系列的最新参考期分别显式传入，
不再依附 CPI 实际发布日期。

规则候选「取消发布时仍沿原计划日期取信息集」仅为候选：2025-10 CPI 原计划
2025-11-13 发布、后永久取消（FRASER 归档 BLS 官方修订表，
sources/bls_lapse_2025.pdf，sha256 见 manifest）。是否采纳由 Codex/用户冻结；
本目录输出不是生产默认，旧 202511（as_of=2025-10-24）不覆盖。

证据要点（同 PDF）：
- CPI October 2025：原计划 Thursday, November 13, 2025 → Canceled
- Employment Situation September 2025：原计划 10-03 → 改期 Thursday,
  November 20, 2025（晚于本候选截止，故就业最新仍为 2025-08）
"""
from __future__ import annotations

import hashlib
import importlib
import json
import sys
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path

from .frozen_batch import ROOT, dump, read_json, sha

OUT = ROOT / 'outputs/sce_recent_environment_evidence_20261023_v1'
OLD = ROOT / 'outputs/sce_fullperiod_data_20261021_v1'
PROD = ROOT / 'outputs/sce_fullperiod_materialized_20261022_v2'
FRASER_PDF = OUT / 'sources/bls_lapse_2025.pdf'
RELEASE_EVIDENCE = ROOT / 'data/raw/sce_baselines_latest_20261007/release_evidence.json'

TARGET = '2025-11'
CANDIDATE_AS_OF = '2025-11-13T23:59:59-05:00'
OLD_AS_OF = '2025-10-24T23:59:59-04:00'
CPI_REF = '2025-09'          # 10-24 发布（停摆延迟）；10月 CPI 永久取消
EMPLOYMENT_REF = '2025-08'   # 09-05 发布；9月就业报告改期 11-20，晚于候选截止
GASOLINE_REF = '2025-10'     # 周度观测 10/06..10/27，月末次周初可得


def helpers():
    sys.path.insert(0, str(ROOT / 'scripts'))
    return importlib.import_module('build_sce_fullperiod_sample_environments')


def build_environment_explicit_cutoff(E, target, *, as_of_dt, cpi_ref,
                                      employment_ref, gasoline_ref):
    """build_environment_gap_tolerant 的显式截止变体；守卫与记录布局相同。"""
    v1, env2 = E.v1, E.env2
    raw_root = E.RAW_BLS
    bundle = deepcopy(read_json(OLD / '201906/environment.json'))
    external_events = deepcopy(read_json(OLD / '201906/external_events.json'))
    components = env2.load_components()
    gasoline = env2.load_gasoline_weekly()
    events_by_month = env2.load_nyt_events()

    as_of = as_of_dt
    ref = cpi_ref
    history_refs = [env2.shift_month(ref, -k) for k in range(1, 12)]
    gas_history_refs = [env2.shift_month(gasoline_ref, -k) for k in range(1, 12)]
    data_gaps: list[dict] = []

    # ---- history sequences: skip refs with no archived release ----
    history: dict[str, dict] = {}
    emp_history: dict[str, dict] = {}
    for h_ref in history_refs:
        try:
            info = v1.ensure_release('cpi', h_ref, raw_root / h_ref, False,
                                     v1.DEFAULT_PROXY)
        except FileNotFoundError:
            data_gaps.append({'reference_period': h_ref,
                              'family': 'bls_cpi_yoy_history',
                              'reason': E._gap_reason(h_ref)})
        else:
            try:
                cpi_h = E._transcribe_cpi_history(
                    v1._first_pages_text(info['path']), h_ref, info['path'])
            except ValueError as exc:
                data_gaps.append({'reference_period': h_ref,
                                  'family': 'bls_cpi_yoy_history',
                                  'reason': f'transcription failed: {exc}'})
            else:
                history[h_ref] = {
                    'value': v1._clean_value(cpi_h['cpi_yoy_nsa_pct']['value']),
                    'published_at': env2._pub_et(info['release_date']),
                    'source_version': f"USDL-{cpi_h['usdl']}",
                    'source_url': v1.ARCHIVE_URL['cpi'].format(
                        mmddyyyy=info['release_date'].strftime('%m%d%Y')),
                    'source_sha256': hashlib.sha256(
                        info['path'].read_bytes()).hexdigest(),
                    **({'note': cpi_h['note']} if 'note' in cpi_h else {}),
                }
        try:
            einfo = v1.ensure_release('empsit', h_ref, raw_root / h_ref, False,
                                      v1.DEFAULT_PROXY)
        except FileNotFoundError:
            data_gaps.append({'reference_period': h_ref,
                              'family': 'bls_unemployment_history',
                              'reason': E._gap_reason(h_ref)})
        else:
            try:
                emp_h = env2._unemployment_rate_only(
                    v1._first_pages_text(einfo['path']), h_ref)
            except ValueError as exc:
                data_gaps.append({'reference_period': h_ref,
                                  'family': 'bls_unemployment_history',
                                  'reason': f'transcription failed: {exc}'})
            else:
                emp_history[h_ref] = {
                    'value': v1._clean_value(emp_h['value']),
                    'published_at': env2._pub_et(einfo['release_date']),
                    'source_version': f"USDL-{emp_h['usdl']}",
                    'source_url': v1.ARCHIVE_URL['empsit'].format(
                        mmddyyyy=einfo['release_date'].strftime('%m%d%Y')),
                    'source_sha256': hashlib.sha256(
                        einfo['path'].read_bytes()).hexdigest(),
                }

    # ---- latest-release headline signals ----
    cpi_info = v1.ensure_release('cpi', ref, raw_root / ref, False,
                                 v1.DEFAULT_PROXY)
    emp_ref = employment_ref
    emp_info = v1.ensure_release('empsit', emp_ref, raw_root / emp_ref, False,
                                 v1.DEFAULT_PROXY)
    cpi = v1.transcribe_cpi(v1._first_pages_text(cpi_info['path']), ref)
    emp = v1.transcribe_empsit(v1._first_pages_text(emp_info['path']), emp_ref)
    pub_cpi = v1.published_at_for(cpi_info['release_date'])
    pub_emp = v1.published_at_for(emp_info['release_date'])
    if not datetime.fromisoformat(pub_cpi) < as_of:
        raise ValueError(f'CPI release for {ref} not before as_of {as_of}')
    if not datetime.fromisoformat(pub_emp) < as_of:
        raise ValueError(f'employment release for {emp_ref} not before as_of {as_of}')
    url_cpi = v1.ARCHIVE_URL['cpi'].format(
        mmddyyyy=cpi_info['release_date'].strftime('%m%d%Y'))
    url_emp = v1.ARCHIVE_URL['empsit'].format(
        mmddyyyy=emp_info['release_date'].strftime('%m%d%Y'))
    records = [dict(r, role='latest_release')
               for r in v1._signals_for_ref(ref, cpi, emp, url_cpi, url_emp,
                                            pub_cpi, pub_emp)]
    broadcasts = [v1._broadcast(0, target, ref, cpi, emp)]
    if emp_ref != ref:
        # 明确登记的旧就业报告：不把旧报告改名成 CPI 的月份。
        for record in records:
            if record['signal_id'].startswith(('bls_unemployment_', 'bls_nonfarm_')):
                record['signal_id'] = record['signal_id'].replace(
                    ref.replace('-', '_'), emp_ref.replace('-', '_'))
                record['reference_period'] = emp_ref
        label = lambda value: f"{v1.MONTH_ABBR[int(value[5:7]) - 1]} {value[:4]}"
        for prefix in ('unemployment', 'nonfarm payrolls'):
            broadcasts[0]['content'] = broadcasts[0]['content'].replace(
                f'{prefix} {label(ref)}:', f'{prefix} {label(emp_ref)}:')
        data_gaps.append({
            'reference_period': ref, 'family': 'latest_employment_release_delayed',
            'substitute_reference_period': emp_ref,
            'reason': ('September 2025 Employment Situation rescheduled to '
                       '2025-11-20 (FRASER bls_lapse_2025.pdf), after candidate '
                       'as_of 2025-11-13; latest legal jobs report is 2025-08 '
                       'released 2025-09-05. Original period and publication retained')})

    # ---- components (latest ref; per-signal gaps recorded) ----
    ref_components = components.get(ref, {})
    usdl, cpi_url = next(
        (r['source_version'], r['source_url']) for r in records
        if r['signal_id'].startswith('bls_cpi_u_all_items_yoy'))
    for sig, measure in env2.COMPONENT_MEASURES.items():
        c = ref_components.get(sig)
        if c is None:
            data_gaps.append({'reference_period': ref,
                              'family': 'bls_cpi_components_latest',
                              'signal_id': sig,
                              'reason': 'component not extractable from archived release'})
            continue
        records.append({
            'signal_id': f"bls_{sig}_nsa_{ref.replace('-', '_')}_initial",
            'measure': measure, 'value': c['value'], 'unit': 'percent',
            'reference_period': ref,
            'published_at': env2._pub_et(date.fromisoformat(c['published_at'])),
            'source_version': usdl, 'source_url': cpi_url,
            'eligibility': 'eligible', 'role': 'latest_release',
        })

    # ---- history records (BLS 锚定 CPI 参考期；汽油锚定自己的最新月) ----
    for h_ref in history_refs:
        h = history.get(h_ref)
        if h:
            records.append({
                'signal_id': f"bls_cpi_u_all_items_yoy_nsa_{h_ref.replace('-', '_')}_initial",
                'measure': 'CPI-U all items 12-month percent change, not seasonally adjusted',
                'value': h['value'], 'unit': 'percent', 'reference_period': h_ref,
                'published_at': h['published_at'], 'source_version': h['source_version'],
                'source_url': h['source_url'], 'eligibility': 'eligible',
                'role': 'history',
            })
        ue = emp_history.get(h_ref)
        if ue:
            records.append({
                'signal_id': f"bls_unemployment_rate_sa_{h_ref.replace('-', '_')}_initial",
                'measure': 'Civilian unemployment rate, seasonally adjusted',
                'value': ue['value'], 'unit': 'percent', 'reference_period': h_ref,
                'published_at': ue['published_at'],
                'source_version': ue['source_version'],
                'source_url': ue['source_url'], 'eligibility': 'eligible',
                'role': 'history',
            })
        for sig, measure in env2.HISTORY_COMPONENTS.items():
            c = components.get(h_ref, {}).get(sig)
            if c is None:
                if h_ref in history:
                    data_gaps.append({'reference_period': h_ref,
                                      'family': 'bls_cpi_component_history',
                                      'signal_id': sig,
                                      'reason': 'component not extractable from archived release'})
                continue
            records.append({
                'signal_id': f"bls_{sig}_nsa_{h_ref.replace('-', '_')}_initial",
                'measure': measure, 'value': c['value'], 'unit': 'percent',
                'reference_period': h_ref,
                'published_at': history[h_ref]['published_at'],
                'source_version': history[h_ref]['source_version'],
                'source_url': history[h_ref]['source_url'],
                'eligibility': 'eligible', 'role': 'history',
            })

    def gas_record(g_ref, role):
        g_h = gasoline.get(g_ref)
        if g_h is None:
            data_gaps.append({'reference_period': g_ref,
                              'family': 'eia_gasoline_level_history',
                              'reason': 'no weekly gasoline observations for ref month'})
            return None
        gas_pub_h = (date.fromisoformat(g_h['last_obs_date'])
                     + timedelta(days=3)).isoformat() + 'T17:00:00'
        rec = {
            'signal_id': f"eia_gasoline_retail_regular_mean_{g_ref.replace('-', '_')}",
            'measure': ('U.S. regular all formulations retail gasoline price, '
                        'monthly mean of weekly observations'),
            'value': g_h['price_mean'], 'unit': 'dollars_per_gallon',
            'reference_period': g_ref,
            'published_at': datetime.fromisoformat(gas_pub_h).replace(
                tzinfo=v1.RELEASE_TZ).isoformat(),
            'source_version': 'FRED GASREGW (EIA weekly retail, Monday obs)',
            'source_url': 'https://fred.stlouisfed.org/series/GASREGW',
            'eligibility': 'vintage_unverified', 'role': role,
            'published_at_basis': 'last_weekly_observation_plus_3_days_assumption',
            'note': ('monthly mean of weekly Monday observations; published_at = '
                     'last weekly obs + 3 days (conservative)'),
        }
        if g_h.get('yoy_pct') is not None:
            yoy = dict(rec)
            yoy.update({
                'signal_id': f"eia_gasoline_retail_regular_yoy_{g_ref.replace('-', '_')}",
                'measure': 'Retail gasoline price 12-month percent change (monthly means)',
                'value': g_h['yoy_pct'], 'unit': 'percent'})
            return [rec, yoy]
        return [rec]

    for g_ref in gas_history_refs:
        for rec in gas_record(g_ref, 'history') or []:
            if rec['signal_id'].startswith('eia_gasoline_retail_regular_yoy'):
                continue  # 与生产一致：历史序列只保留价位水平
            records.append(rec)
    latest_gas = gas_record(gasoline_ref, 'latest_release')
    if not latest_gas:
        raise ValueError(f'missing gasoline data for ref {gasoline_ref}')
    records.extend(latest_gas)

    # hard eligibility guard: everything strictly before as_of
    for r in records:
        if not datetime.fromisoformat(r['published_at']) < as_of:
            raise ValueError(f"record {r['signal_id']} published {r['published_at']} "
                             f'not before as_of {as_of.isoformat()}')

    # ---- NYT events: M-1 (shadow ledger, full month) + early M (PIT cutoff) ----
    as_of_date = as_of.date()
    pool = list(events_by_month.get(env2.shift_month(target, -1), []))
    pool.extend(env2.load_nyt_events_until(target, as_of_date))
    for e in pool:
        if date.fromisoformat(e['pub_date']) > as_of_date:
            raise ValueError(f"event {e['event_id']} after as_of")
    evs = [{k: e[k] for k in
            ('event_id', 'pub_date', 'tier', 'headline', 'abstract',
             'section_name', 'web_url', 'matched_keywords')}
           for e in env2._merge_event_pool(pool, env2.EVENT_BUDGET)]
    for event in evs:
        event['text_vintage_status'] = 'unverified_archive_snapshot'
        event['selection_cutoff'] = as_of_date.isoformat()

    bundle['provider_args']['signals_by_step'] = {'0': records}
    bundle['provider_args']['events_by_step'] = {'0': evs}
    bundle['provider_args']['targets'] = [
        {'target_month': target, 'as_of': as_of.isoformat()}]
    bundle['provider_args']['e_version'] = 'v2'
    bundle['provider_args']['evidence_class'] = 'mixed_source_vintage_status'
    bundle['provider_args']['source_status'] = {
        'bls': 'archived_initial_release_verified',
        'eia_gasoline': 'current_fred_snapshot_vintage_unverified',
        'nyt': 'archive_metadata_text_vintage_unverified',
    }
    bundle['provider_args']['excluded_sources'] = ['nyfed_sce']
    bundle['provider_args']['e_v2_layers'] = [
        'bls_headline_4_signals', 'bls_cpi_components_5',
        'eia_gasoline_retail_level_yoy',
        'bls_cpi_yoy_history_11m', 'bls_unemployment_history_11m',
        'bls_cpi_component_history_3x11m', 'eia_gasoline_level_history_11m',
        'nyt_salient_events_m_minus_1_through_as_of',
    ]
    bundle['provider_args']['data_gaps'] = {
        'note': ('Candidate information cutoff 2025-11-13 (original October CPI '
                 'schedule date, later cancelled — FRASER bls_lapse_2025.pdf). '
                 'Rule candidate "cancelled release follows original schedule '
                 'date" is NOT frozen. Gasoline/news text vintage unverified.'),
        'gaps': data_gaps,
    }
    bundle['information_program']['broadcasts'] = broadcasts

    external_events['dataset_id'] = 'sce_bls_initial_release_e_2025_11_v2_candidate_asof20251113'
    external_events['requested_months'] = [target]
    external_events['records_by_step'] = {'0': records}
    external_events['events_by_step'] = {'0': evs}
    external_events['as_of'] = {'0': as_of.isoformat()}
    external_events['e_version'] = 'v2'
    external_events['status'] = 'mixed_source_vintage_status'
    external_events['data_gaps'] = bundle['provider_args']['data_gaps']

    sim = v1.simulation_config([target])
    v1.validate_with_official_schemas(bundle, sim)
    return {'bundle': bundle, 'external_events': external_events,
            'data_gaps': data_gaps, 'n_records': len(records),
            'n_events': len(evs), 'as_of': as_of.isoformat()}


def _sce_anchor(cutoff_date: str) -> dict:
    """截止前最后公开的全国 SCE 汇总（发布按日粒度比较）。"""
    releases = sorted(json.load(open(RELEASE_EVIDENCE)),
                      key=lambda r: r['published_date'])
    avail = [r for r in releases if r['published_date'] <= cutoff_date]
    last = avail[-1]
    return {'reference_period': last['reference_period'],
            'published_date': last['published_date'],
            'source_url': last['source_url'],
            'local_file': last['file'], 'local_file_sha256': last['sha256']}


def _policy_anchor(cutoff_iso: str) -> dict:
    policies = read_json(
        ROOT / 'docs/workstreams/20261021_fullperiod/new2025_policy_sources.json')
    policies.update(read_json(
        ROOT / 'data/raw/sce_fullperiod_supplement_20261022/policy_sources_full_v2.json'))
    cutoff = datetime.fromisoformat(cutoff_iso)
    eligible = [v for v in policies.values()
                if datetime.fromisoformat(v['published_at']) <= cutoff]
    sp = max(eligible, key=lambda v: v['published_at'])
    return {'published_at': sp['published_at'], 'source_url': sp['source_url'],
            'facts': sp['facts']}


def _confidence_anchor(cutoff_iso: str) -> dict:
    from ..coverage_preparation import latest_wave
    waves = read_json(
        ROOT / 'docs/workstreams/20261017_reference_scaleup/confidence_sources.json')['waves']
    waves = waves + read_json(
        ROOT / 'data/raw/sce_fullperiod_supplement_20261022/confidence_supplement.json')['waves']
    w = latest_wave(waves, cutoff_iso)
    return {'wave_id': w['wave_id'], 'published_date': w['published_date']}


def _diff_summary(candidate: dict) -> dict:
    prod = read_json(PROD / '202511/environment.json')
    # 生产文件里同一 signal_id 可同时出现在 latest_release 与 history
    # （就业替代参考期=历史末月），比较键必须含 role。
    prod_sigs = {(r['signal_id'], r['role']): r for r in
                 prod['provider_args']['signals_by_step']['0']}
    cand_sigs = {(r['signal_id'], r['role']): r for r in
                 candidate['bundle']['provider_args']['signals_by_step']['0']}
    added = sorted(k[0] for k in set(cand_sigs) - set(prod_sigs))
    removed = sorted(k[0] for k in set(prod_sigs) - set(cand_sigs))
    changed_values = sorted(
        k for k in set(prod_sigs) & set(cand_sigs)
        if prod_sigs[k].get('value') != cand_sigs[k].get('value'))
    prod_events = {e['event_id'] for e in
                   prod['provider_args']['events_by_step']['0']}
    cand_events = {e['event_id'] for e in
                   candidate['bundle']['provider_args']['events_by_step']['0']}
    return {
        'as_of': {'production': prod['provider_args']['targets'][0]['as_of'],
                  'candidate': candidate['as_of']},
        'signals': {'production_n': len(prod_sigs), 'candidate_n': len(cand_sigs),
                    'added': added, 'removed': removed,
                    'changed_values': changed_values},
        'events': {'production_n': len(prod_events),
                   'candidate_n': len(cand_events),
                   'added_n': len(cand_events - prod_events),
                   'removed_n': len(prod_events - cand_events),
                   'shared_n': len(prod_events & cand_events)},
        'broadcast_content_unchanged':
            prod['information_program']['broadcasts'][0]['content']
            == candidate['bundle']['information_program']['broadcasts'][0]['content'],
    }


def main() -> int:
    E = helpers()
    cpi_ref, gas_ref = CPI_REF, GASOLINE_REF
    history_refs = {E.env2.shift_month(cpi_ref, -k) for k in range(1, 12)}
    gas_history_refs = {E.env2.shift_month(gas_ref, -k) for k in range(1, 12)}

    # 影子输入：组件合订本、汽油合并周值、按候选截止过滤的 NYT 事件台账。
    from .fullperiod_materialization import complete_components
    support = OUT / '_build_support/202511_candidate'
    support.mkdir(parents=True, exist_ok=True)
    refs = sorted({cpi_ref} | history_refs)
    E.env2.COMPONENTS_JSONL = complete_components(E, refs)
    E.env2.GAS_WEEKLY_CSV = E.GAS_CONSOLIDATED
    ledger = support / 'events_ledger_cutoff_filtered.jsonl'
    cutoff_date = date(2025, 11, 13)
    with ledger.open('w') as handle:
        window = E.env2.shift_month(TARGET, -1)
        raw = ROOT / 'data/raw/nyt_archive' / f'{window}.json'
        docs = [d for d in read_json(raw)['response']['docs']
                if d.get('pub_date', '')[:10] <= cutoff_date.isoformat()]
        for event in E.nyt.select_events(docs, window, sha(raw),
                                         E.env2.EVENT_BUDGET):
            handle.write(json.dumps(event) + '\n')
    E.env2.NYT_LEDGER = ledger

    as_of_dt = datetime.fromisoformat(CANDIDATE_AS_OF)
    result = build_environment_explicit_cutoff(
        E, TARGET, as_of_dt=as_of_dt, cpi_ref=cpi_ref,
        employment_ref=EMPLOYMENT_REF, gasoline_ref=gas_ref)

    folder = OUT / '202511_candidate_asof20251113'
    folder.mkdir(parents=True, exist_ok=True)
    dump(folder / 'environment.json', result['bundle'])
    dump(folder / 'external_events.json', result['external_events'])

    # 食品分项：同一 9 月 CPI 首发 PDF（10-24 发布），与生产一致。
    from ..procurement_price_views import extract_categories
    cpi_info = E.v1.ensure_release('cpi', cpi_ref, E.RAW_BLS / cpi_ref, False,
                                   E.v1.DEFAULT_PROXY)
    facts = extract_categories(E._best_page_texts(cpi_info['path']))
    for fact in facts.values():
        fact.update(reference_period=cpi_ref,
                    published_at=E.v1.published_at_for(cpi_info['release_date']),
                    source_file=str(cpi_info['path'].relative_to(ROOT)),
                    source_sha256=sha(cpi_info['path']),
                    vintage='archived_initial_release', strict_B_eligible=False)
    dump(folder / 'food_categories.json', facts)

    receipt = dict(month='202511', candidate_of='2025-11',
                   cutoff_rule_candidate='cancelled_release_follows_original_schedule_date',
                   rule_status='candidate_not_frozen',
                   environment_available=True, food_available=True,
                   as_of=result['as_of'], signals=result['n_records'],
                   events=result['n_events'], gaps=result['data_gaps'],
                   component_sha256=sha(E.env2.COMPONENTS_JSONL),
                   new_api_calls=0)
    dump(folder / 'environment_receipt.json', receipt)

    as_of_candidates = {
        'target_month': TARGET,
        'rule_candidate': ('取消发布时仍沿原计划日期取信息集；候选未冻结，'
                           '截止选择不基于拟合表现'),
        'evidence': {
            'fraser_pdf': {
                'path': 'outputs/sce_recent_environment_evidence_20261023_v1/sources/bls_lapse_2025.pdf',
                'sha256': sha(FRASER_PDF),
                'quotes': [
                    'Consumer Price Index October 2025 — Previously scheduled '
                    'Thursday, November 13, 2025 — Canceled (See CPI note)',
                    'Employment Situation September 2025 — Previously scheduled '
                    'Friday, October 3, 2025 — Revised Thursday, November 20, '
                    '2025 8:30 AM ET',
                ],
            },
        },
        'candidates': {
            'production_old': {
                'as_of': OLD_AS_OF,
                'basis': '实际 CPI 发布日耦合（9月 CPI 因停摆延迟至 10-24）',
                'cpi_latest': {'reference_period': '2025-09',
                               'published_at': '2025-10-24T08:30:00-04:00'},
                'employment_latest': {'reference_period': '2025-08',
                                      'published_at': '2025-09-05T08:30:00-04:00'},
                'gasoline_latest': {'reference_period': '2025-09',
                                    'published_at_basis': 'last_obs+3d'},
                'sce_aggregate_anchor': _sce_anchor('2025-10-24'),
                'policy_latest': _policy_anchor(OLD_AS_OF),
                'confidence_wave': _confidence_anchor(OLD_AS_OF),
            },
            'candidate_20251113': {
                'as_of': CANDIDATE_AS_OF,
                'basis': '10月 CPI 原计划发布日（后取消）；规则候选未冻结',
                'cpi_latest': {'reference_period': '2025-09',
                               'published_at': '2025-10-24T08:30:00-04:00',
                               'note': '截止移动不捏造新 CPI 值'},
                'employment_latest': {'reference_period': '2025-08',
                                      'published_at': '2025-09-05T08:30:00-04:00',
                                      'note': '9月就业报告改期 11-20，晚于截止'},
                'gasoline_latest': {'reference_period': '2025-10',
                                    'published_at_basis': 'last_obs+3d'},
                'sce_aggregate_anchor': _sce_anchor('2025-11-13'),
                'policy_latest': _policy_anchor(CANDIDATE_AS_OF),
                'confidence_wave': _confidence_anchor(CANDIDATE_AS_OF),
            },
        },
    }
    dump(OUT / 'as_of_candidates.json', as_of_candidates)

    diff = _diff_summary(result)
    summary = {
        'generated_at': datetime.now().isoformat(),
        'new_api_calls': 0,
        'candidate_dir': str(folder.relative_to(ROOT)),
        'diff_vs_production_202511': diff,
        'files': {
            'environment.json': sha(folder / 'environment.json'),
            'external_events.json': sha(folder / 'external_events.json'),
            'food_categories.json': sha(folder / 'food_categories.json'),
            'environment_receipt.json': sha(folder / 'environment_receipt.json'),
            'as_of_candidates.json': sha(OUT / 'as_of_candidates.json'),
        },
    }
    dump(OUT / 'candidate_202511_summary.json', summary)
    print(json.dumps({'signals': result['n_records'], 'events': result['n_events'],
                      'diff': diff}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
