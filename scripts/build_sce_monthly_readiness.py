#!/usr/bin/env python
"""P1: 近期 11 个月（2025-11..2026-09）逐月输入就绪清单（monthly_readiness）。

合并以下来源，对每月每项输入分类 verified / inferred_publication /
vintage_unverified / excluded / missing_permanent / unknown，
并给出 strict_B_eligible 与理由；同时输出回顾用（A 线）与严格 B 两套来源清单。

输入（全部本地，无新 API/LLM 调用）：
  outputs/sce_fullperiod_materialized_20261022_v2/<m>/  (receipt/environment/food/news_label_index)
  outputs/sce_recent_environment_evidence_20261023_v1/gasoline_summary.json      (P0-b)
  outputs/sce_recent_environment_evidence_20261023_v1/news_pool_summary.json     (P0-c)
  outputs/sce_recent_environment_evidence_20261023_v1/micro_publication_evidence.jsonl (附加项)
  data/raw/sce_baselines_latest_20261007/release_evidence.json                   (SCE 逐月发布日)
  studies/.../recent_environment_evidence.py 的 _policy_anchor/_confidence_anchor (政策/信心选择规则)

输出：outputs/sce_recent_environment_evidence_20261023_v1/monthly_readiness.json
      outputs/sce_recent_environment_evidence_20261023_v1/monthly_readiness.md
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAT = ROOT / 'outputs/sce_fullperiod_materialized_20261022_v2'
EV = ROOT / 'outputs/sce_recent_environment_evidence_20261023_v1'
OUT_JSON = EV / 'monthly_readiness.json'
OUT_MD = EV / 'monthly_readiness.md'

MONTHS = ['202511', '202512', '202601', '202602', '202603', '202604',
          '202605', '202606', '202607', '202608', '202609']

# 停摆永久缺失单元（FRASER bls_lapse_2025.pdf，P0-a 取证）
SHUTDOWN_PERMANENT = {
    'cpi_2025_10': 'CPI 2025-10 期发布永久取消（原计划 2025-11-13）',
    'cps_2025_10': 'CPS/就业 2025-10 参考期未采集，永久缺失',
}


def read_json(p):
    return json.load(open(p))


def main():
    gas = read_json(EV / 'gasoline_summary.json')
    news = read_json(EV / 'news_pool_summary.json')
    news_by_month = {m['target_month'].replace('-', ''): m for m in news['months']}
    micro_path = EV / 'micro_publication_evidence.jsonl'
    micro_rows = []
    if micro_path.exists():
        micro_rows = [json.loads(line) for line in open(micro_path) if line.strip()]

    import sys
    sys.path.insert(0, str(ROOT))
    from studies.sce_inflation_expectations.experiments.recent_environment_evidence import (
        _policy_anchor, _confidence_anchor, _sce_anchor)

    months_out = []
    for m in MONTHS:
        folder = MAT / m
        receipt = read_json(folder / 'environment_receipt.json')
        env = read_json(folder / 'environment.json')
        pa = env['provider_args']
        as_of = receipt['as_of']
        as_of_date = as_of[:10]

        sigs = pa['signals_by_step']['0']
        bls_sigs = [s for s in sigs if s['signal_id'].startswith('bls_')]
        eia_sigs = [s for s in sigs if s['signal_id'].startswith('eia_')]
        n_after = sum(1 for s in sigs if s['published_at'] > as_of)
        gaps = receipt.get('gaps', [])

        food = read_json(folder / 'food_categories.json')
        food_refs = sorted({v['reference_period'] for v in food.values()})
        food_strict = all(v.get('strict_B_eligible') for v in food.values())

        # --- 政策 / 信心 / SCE 锚（选择规则与 P0-a 相同，按日发布日比较） ---
        policy = _policy_anchor(as_of)
        conf = _confidence_anchor(as_of)
        sce = _sce_anchor(as_of_date)

        # --- 新闻（P0-c） ---
        nm = news_by_month[m]
        news_item = {
            'status': 'vintage_unverified',
            'strict_B_eligible': False,
            'reason': ('候选文本为 2026-10-07 抓取的 NYT Archive 缓存，无同期文本快照、'
                       '无发布方修订时间字段；严格 B 可用池为 0 篇'
                       f"（共同池下限 3 / 个人池下限 17）。A 池 {nm['index_pool_n']} 篇、"
                       f"共同 A1 {nm['index_common_a1_n']} 篇、个人 keep {nm['index_personal_keep_n']} 篇，"
                       '发布时间无越界（0 篇 after_cutoff）。'),
            'pool_n': nm['index_pool_n'],
            'common_a1_n': nm['index_common_a1_n'],
            'personal_keep_n': nm['index_personal_keep_n'],
            'strict_B_pool_n': 0,
            'after_cutoff_n': nm['after_cutoff_n'],
            'sce_leak_hits': nm['sce_mention_flag_n'],
        }

        # --- 微观人口 ---
        micro_item = {
            'status': 'unknown',
            'strict_B_eligible': False,
            'reason': ('人口为合成分布扩展（evidence_class=synthetic_distribution_extension, '
                       'micro_published_at=None）。微观文件公开时点证据见 '
                       'micro_publication_evidence.jsonl；无法证明某版本在各 as_of 前已公开。'),
            'evidence_rows': len(micro_rows),
        }

        inputs = {
            'bls_prices': {
                'status': 'verified',
                'strict_B_eligible': True,
                'n_signals': len(bls_sigs),
                'reason': ('归档首发 PDF（source_version=USDL 编号），发布时间逐条登记且均早于 as_of；'
                           f'source_status.bls={pa["source_status"]["bls"]}。'),
                'gaps': gaps,
            },
            'eia_gasoline': {
                'status': 'inferred_publication+vintage_verified',
                'strict_B_eligible': True,
                'n_signals': len(eia_sigs),
                'reason': ('P0-b：143/143 实例数值与缓存周度均值一致、全部组成观测推断发布时刻早于 as_of、'
                           'FRED realtime 首发 vintage 与当前快照一致（无修订）。发布时刻本身为日程推断'
                           '（inferred_publication）。占位 published_at 不可引用。'),
            },
            'food_categories': {
                'status': 'verified',
                'strict_B_eligible': food_strict,
                'n_categories': len(food),
                'reference_periods': food_refs,
                'reason': ('与 CPI 同一份归档首发 PDF 的表 2/表 7 抽取行，vintage=archived_initial_release；'
                           '生产侧保守置 strict_B_eligible=False（类别行未做独立首发核验），'
                           '是否升入严格 B 待 Codex/用户决定。'),
            },
            'policy_fomc': {
                'status': 'verified',
                'strict_B_eligible': False,
                'latest': {'published_at': policy['published_at'], 'source_url': policy['source_url']},
                'reason': ('联储声明为带日期的官方新闻稿（最新为截止前最后一次）；'
                           '但文本为 2026-10-22 抓取的当前快照、正文 vintage 未核验，'
                           '生产侧 strict_B_eligible=False。'),
            },
            'confidence_wave': {
                'status': 'verified',
                'strict_B_eligible': False,
                'latest': conf,
                'reason': ('Gallup 波次带发布日（日粒度保守取当日 ET 结束）；'
                           '原始 topline PDF 已归档，但生产侧 strict_B_eligible=False。'),
            },
            'news_pool': news_item,
            'sce_aggregate_anchor': {
                'status': 'excluded',
                'strict_B_eligible': False,
                'latest_available': {'reference_period': sce['reference_period'],
                                     'published_date': sce['published_date']},
                'reason': ('excluded_sources=[nyfed_sce]：同期真值不进 B 线环境，仅作 A 线锚/评价。'
                           '发布日有 NY Fed 新闻稿逐月取证（release_evidence.json）。'),
            },
            'micro_population': micro_item,
        }

        # 停摆永久缺失标注
        permanent = []
        for g in gaps:
            if g.get('family') in ('bls_cpi_yoy_history', 'bls_unemployment_history') \
                    and g.get('reference_period') == '2025-10':
                permanent.append(SHUTDOWN_PERMANENT[
                    'cpi_2025_10' if 'cpi' in g['family'] else 'cps_2025_10'])

        retrospective = [k for k in inputs]
        strict_b = [k for k, v in inputs.items() if v['strict_B_eligible']]

        months_out.append({
            'month': m,
            'as_of': as_of,
            'n_signals': len(sigs),
            'n_events': receipt['events'],
            'signals_published_after_as_of': n_after,
            'inputs': inputs,
            'shutdown_permanent_missing': permanent,
            'retrospective_sources': retrospective,
            'strict_B_sources': strict_b,
        })

    doc = {
        'report': 'SCE 近期 11 个月逐月输入就绪清单（monthly_readiness）',
        'built_at': '2026-10-23',
        'scope': 'outputs/sce_fullperiod_materialized_20261022_v2 的 202511..202609',
        'status_vocabulary': ['verified', 'inferred_publication', 'vintage_unverified',
                              'excluded', 'missing_permanent', 'unknown'],
        'new_api_calls': 0,
        'new_llm_calls': 0,
        'months': months_out,
    }
    OUT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=1))

    lines = ['# 近期 11 个月 monthly_readiness 汇总', '',
             '| 月份 | as_of | BLS价格 | 汽油EIA | 食品 | 政策FOMC | 信心波次 | 新闻池 | SCE锚 | 微观人口 |',
             '|---|---|---|---|---|---|---|---|---|---|']
    for mo in months_out:
        i = mo['inputs']
        def mark(k):
            v = i[k]
            return ('✅' if v['strict_B_eligible'] else '⚠️') + ' ' + v['status']
        lines.append(
            f"| {mo['month']} | {mo['as_of'][:10]} | {mark('bls_prices')} | {mark('eia_gasoline')} | "
            f"{mark('food_categories')} | {mark('policy_fomc')} | {mark('confidence_wave')} | "
            f"{mark('news_pool')} | {mark('sce_aggregate_anchor')} | {mark('micro_population')} |")
    lines += ['',
              '图例：✅=strict_B_eligible；⚠️=不满足严格 B（原因见 JSON 各 inputs.reason）。',
              'SCE 锚与同期真值按设计排除在 B 线环境之外（excluded），仅用于 A 线锚定/评价。',
              '新闻池全部 vintage_unverified：严格 B 可用池 11 个月均为 0 篇；A 池（回顾用）逐月充足。']
    OUT_MD.write_text('\n'.join(lines))

    print(f'written {OUT_JSON} ({len(months_out)} months)')
    print(f'written {OUT_MD}')


if __name__ == '__main__':
    main()
