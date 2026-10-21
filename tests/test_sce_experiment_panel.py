"""Synthetic smoke tests for the offline SCE experiment panel (zero-call).

Batch-1 conventions under test (experiment_panel_review_20261020):
- primary statistic = group-center MAE per month x repeat, equal-averaged;
  personal MAE and the personal absolute error median are separate;
- main support = person-months scorable in ALL arms x repeats; per-arm
  usable supports are sensitivity; Q8 takes its own support;
- ESS is Kish ESS on merged person-month weights (repeats never multiply
  people or ESS);
- repeat variance decomposition follows evaluation/temperature.py.

The standard fixture is a 2 month x 12 person x 2 repeat x 2 arm batch with
one unscored Q9 record and one missing prior, hand-checkable by construction:
truth = 2 + 0.1*uid (+0.3 in month 2), prior = truth - (0.2 + 0.05*uid),
model A = truth + 0.4, model B = truth - 0.1.
"""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

from studies.sce_inflation_expectations.evaluation.temperature import variance_components
from studies.sce_inflation_expectations.panel import adapters, registry
from studies.sce_inflation_expectations.panel.adapters import load_batch
from studies.sce_inflation_expectations.panel.regimes import build_regime_lookup
from studies.sce_inflation_expectations.panel.render import ROLE_STYLES, TABS, render_html
from studies.sce_inflation_expectations.panel.sections import (
    MIN_COVERAGE_N, build_panel, q9_support)

MONTHS = (202001, 202002)
UIDS = tuple(range(1, 13))
PROFILE = {
    1: {'education_group': 'college', 'employment_status': 'employed'},
    2: {'education_group': 'college', 'employment_status': 'retired'},
    3: {'education_group': 'high_school', 'employment_status': 'employed'},
    4: {'education_group': 'high_school', 'employment_status': 'homemaker'},
    5: {'education_group': 'some_college', 'employment_status': 'employed'},
    6: {'education_group': 'some_college', 'employment_status': 'student'},
    7: {'education_group': 'high_school', 'employment_status': 'employed'},
    8: {'education_group': 'high_school', 'employment_status': 'employed'},
    9: {'education_group': 'high_school', 'employment_status': 'employed'},
    10: {'education_group': 'high_school', 'employment_status': 'employed'},
    11: {'education_group': 'high_school', 'employment_status': 'employed'},
    12: {'education_group': 'high_school', 'employment_status': 'employed'},
}
MISSING_MODEL = (202001, 3, 1, 'A')   # month, uid, repeat, arm: scorer error
MISSING_PRIOR = (202002, 6)           # month, uid: no archived prior
BATCH = 'syn_batch_evaluation_20261020_v1'


def truth_mean(uid, month):
    return 2.0 + 0.1 * uid + (0.3 if month == 202002 else 0.0)


def prior_mean(uid, month):
    return truth_mean(uid, month) - (0.2 + 0.05 * uid)


def model_mean(arm, uid, month):
    return truth_mean(uid, month) + (0.4 if arm == 'A' else -0.1)


_SENTINEL = object()


def make_case(month, uid, repeat, arms, prior=_SENTINEL, weight=2.0, q8=_SENTINEL,
              truth=_SENTINEL):
    if prior is _SENTINEL:
        prior = prior_mean(uid, month)
    if q8 is _SENTINEL:
        q8 = float(uid)
    if truth is _SENTINEL:
        truth = truth_mean(uid, month)
    return {
        'month': month, 'userid': uid, 'agent_id': f'syn_{uid}_{repeat}',
        'profile': dict(PROFILE[uid]), 'stratum': 'syn',
        'survey_weight': weight / 2, 'inclusion_probability': 0.5,
        'design_survey_weight': weight, 'repeat': repeat,
        'real': {'q9_mean': truth, 'q9_iqr': 2.0,
                 'q9_zero_deflation': 0.0,
                 'q9_bins': [0., 0., 25., 25., 25., 25., 0., 0., 0., 0.],
                 'q8_point': q8,
                 'q8_outside_100': False,
                 'weight': weight / 2, 'previous_q9_mean': prior,
                 'previous_q9_bins': None},
        'arms': arms,
    }


def arm_entry(uid, month, arm, repeat):
    if (month, uid, repeat, arm) == MISSING_MODEL:
        return {'mean': None, 'iqr': None, 'q9_bins': None, 'point': None,
                'scorer_status': 'error', 'validation_status': 'invalid',
                'validation_error': 'synthetic', 'normalization_applied': False}
    return {'mean': model_mean(arm, uid, month), 'iqr': 1.0,
            'q9_bins': [10., 20., 30., 40., 0., 0., 0., 0., 0., 0.],
            'point': round(model_mean(arm, uid, month)),
            'scorer_status': 'ok', 'validation_status': 'valid',
            'validation_error': None, 'normalization_applied': arm == 'B'}


def make_cases():
    cases = []
    for month in MONTHS:
        for uid in UIDS:
            prior = None if (month, uid) == MISSING_PRIOR else prior_mean(uid, month)
            for repeat in (1, 2):
                arms = {arm: arm_entry(uid, month, arm, repeat) for arm in ('A', 'B')}
                cases.append(make_case(month, uid, repeat, arms, prior=prior))
    return cases


def write_batch(tmp_path, batch, cases):
    out = tmp_path / batch
    out.mkdir()
    (out / 'cases_private.json').write_text(json.dumps(cases))
    (out / 'summary.json').write_text(json.dumps({
        'status': 'synthetic', 'estimated_run_cost_usd_not_provider_bill': 0.01,
        'protocol': {'id': 'syn', 'months': sorted({c['month'] for c in cases}),
                     'n_per_month': len(UIDS), 'arms': ['A', 'B'],
                     'generation_repeats': [1, 2], 'model': 'test-model',
                     'temperature': 0.0}}))
    return out


@pytest.fixture()
def batch(tmp_path):
    out = write_batch(tmp_path, BATCH, make_cases())
    records, meta = load_batch(out / 'cases_private.json')
    regime_lookup = build_regime_lookup({202001: 2.0, 202002: 2.5})
    panel = build_panel(records, [meta], regime_lookup)
    return records, meta, panel


def test_adapter_record_shape_and_weight_split(batch):
    records, meta, _ = batch
    assert meta['status'] == 'ok'
    assert meta['registered'] is False          # 未登记批次也能显示
    assert len(records) == 2 * len(UIDS) * 2 * 2
    # each person's design weight (2.0) is split across two repeats
    assert all(r['weight'] == pytest.approx(1.0) for r in records)
    rec = next(r for r in records if r['arm'] == 'A' and r['model_shape'])
    assert rec['model_shape']['nz_bins'] == 4
    assert rec['model_shape']['mult10_share'] == pytest.approx(1.0)


def test_panel_serializable_without_nan(batch):
    _, _, panel = batch
    text = json.dumps(panel, ensure_ascii=False, allow_nan=False)
    assert 'NaN' not in text and 'Infinity' not in text
    exp = panel['experiments'][BATCH]
    assert set(exp['sections']) == {'overview', 'monthly', 'grid', 'priors', 'structure',
                                    'quality', 'drill', 'inputs'}
    assert exp['q8_available'] is True


def test_group_center_is_primary_and_personal_rows_differ(batch):
    _, _, panel = batch
    exp = panel['experiments'][BATCH]
    row = exp['sections']['overview']['q9']['A']
    # model A = truth + 0.4 constant: every month x repeat cell has center
    # error exactly 0.4, personal MAE 0.4, but the personal absolute error
    # median differs (0.4 is the median of |0.4| only if ... here constant)
    assert row['center_mae_pp'] == pytest.approx(0.4)
    assert row['center_rmse_pp'] == pytest.approx(0.4)
    assert row['center_bias_pp'] == pytest.approx(0.4)
    assert row['person_mae_pp'] == pytest.approx(0.4)
    # persistence (copy previous) on the identical support
    pers = row['persistence']
    err = {u: abs(prior_mean(u, 202001) - truth_mean(u, 202001)) for u in UIDS}
    m1 = sum(err[u] for u in UIDS if u != 3) / 11   # uid3 out of the support
    m2 = sum(err[u] for u in UIDS if u != 6) / 11   # uid6 prior missing
    assert pers['person_mae_pp'] == pytest.approx((m1 + m2) / 2)
    assert pers['n_identical_support'] == 22


def test_person_abs_error_median_differs_from_group_center():
    """Counterexample: median of personal absolute errors (0) is not the
    group-center MAE (5). truth: 6 persons at 0, 6 at 10; model moves the
    low half up by 5 and copies the high half exactly."""
    cases = []
    for uid in range(1, 13):
        truth = 0.0 if uid <= 6 else 10.0
        model = truth + 5.0 if uid <= 6 else truth
        arms = {'A': {'mean': model, 'iqr': 1.0,
                      'q9_bins': [0.] * 10, 'point': model,
                      'scorer_status': 'ok', 'validation_status': 'valid',
                      'validation_error': None, 'normalization_applied': False}}
        cases.append(make_case(202001, uid, 1, arms, prior=truth, weight=1.0,
                                 truth=truth))
    with tempfile.TemporaryDirectory() as td:
        out = write_batch(Path(td), 'counter_batch_evaluation_20261020_v1', cases)
        records, meta = load_batch(out / 'cases_private.json')
        panel = build_panel(records, [meta], build_regime_lookup({202001: 2.0}))
    row = panel['experiments']['counter_batch_evaluation_20261020_v1']['sections']['overview']['q9']['A']
    assert row['person_abs_error_median_pp'] == pytest.approx(0.0)
    assert row['center_mae_pp'] == pytest.approx(5.0)
    assert row['person_mae_pp'] == pytest.approx(2.5)
    assert row['person_abs_error_median_pp'] != row['center_mae_pp']


def test_common_support_and_sensitivity(batch):
    records, _, panel = batch
    exp = panel['experiments'][BATCH]
    row = exp['sections']['overview']['q9']['A']
    # uid3 month1 has an unscored arm-A repeat -> the whole person-month
    # leaves the all-arm x all-repeat common support (23 = 12 - 1 + 12);
    # unique persons de-duplicate the same 12 userids across both months
    assert row['n_person_months'] == 23
    assert row['unique_persons'] == 12
    sens = exp['sections']['overview']['support_sensitivity']
    assert sens['A']['n_person_months'] == 23      # arm A alone: same hole
    assert sens['B']['n_person_months'] == 24      # arm B unscored nowhere
    assert sens['A']['unique_persons'] == 12 and sens['B']['unique_persons'] == 12
    # Q8 takes its own support: the missing-model record also lacks a Q8
    # point, so Q8 support excludes uid3 month1 too; uid6 month2 stays in
    # (prior missing does not affect the Q8 support)
    q8 = exp['sections']['overview']['q8']
    assert q8['A']['n_person_months'] == 23


def test_q8_survives_q9_failure(tmp_path, monkeypatch):
    """A record with valid Q8 but failed Q9 stays in the Q8 support only."""
    monkeypatch.setattr(sys.modules[__name__], 'MISSING_MODEL', (190001, 0, 1, 'X'))
    cases = []
    for uid in UIDS:
        for repeat in (1, 2):
            arms = {arm: arm_entry(uid, 202001, arm, repeat) for arm in ('A', 'B')}
            if uid == 7 and repeat == 1:
                arms['A'] = {'mean': None, 'iqr': None, 'q9_bins': None,
                             'point': float(uid),              # Q8 still valid
                             'scorer_status': 'error', 'validation_status': 'invalid',
                             'validation_error': 'synthetic', 'normalization_applied': False}
            cases.append(make_case(202001, uid, repeat, arms,
                                   prior=prior_mean(uid, 202001)))
    out = write_batch(tmp_path, 'q8_batch_evaluation_20261020_v1', cases)
    records, meta = load_batch(out / 'cases_private.json')
    panel = build_panel(records, [meta], build_regime_lookup({202001: 2.0}))
    q = panel['experiments']['q8_batch_evaluation_20261020_v1']['sections']['quality']
    assert q['q9_common_person_months'] == 11       # uid7 out
    assert q['q8_common_person_months'] == 12       # Q8 unaffected


def test_ess_person_level_and_repeat_doubling(batch, monkeypatch):
    records, _, panel = batch
    row = panel['experiments'][BATCH]['sections']['overview']['q9']['A']
    weights = {}
    for r in records:
        if r['arm'] == 'A' and (r['month'], r['_pid']) and r['month'] == 202001 \
                and r['_pid'] != '202001|3':
            weights[r['_pid']] = weights.get(r['_pid'], 0.) + r['weight']
    expected_ess = sum(weights.values()) ** 2 / sum(w * w for w in weights.values())
    # Kish ESS over the whole support equals the month-1 value doubled in n
    # but not in per-person weight; verify directly via month1 ESS instead
    monthly = panel['experiments'][BATCH]['sections']['monthly']['A']['rows']
    m1 = next(r for r in monthly if r['month'] == 202001 and r['repeat'] == 1)
    assert m1['ess'] == pytest.approx(expected_ess)
    assert m1['n'] == 11
    # repeats doubled: a balanced 4-repeat generation of the same roster must
    # not increase the person count, the unique persons or the Kish ESS
    # (person weights merge back to the same design weights)
    monkeypatch.setattr(sys.modules[__name__], 'MISSING_MODEL', (190001, 0, 1, 'X'))

    def build(n_repeats):
        cases = []
        for month in MONTHS:
            for uid in UIDS:
                for repeat in range(1, n_repeats + 1):
                    arms = {arm: arm_entry(uid, month, arm, repeat) for arm in ('A', 'B')}
                    cases.append(make_case(month, uid, repeat, arms,
                                           prior=prior_mean(uid, month)))
        with tempfile.TemporaryDirectory() as td:
            out = write_batch(Path(td), 'rep_batch_evaluation_20261020_v1', cases)
            return load_batch(out / 'cases_private.json')[0]

    records2, records4 = build(2), build(4)
    support2, arms2, repeats2, _ = q9_support(records2)
    support4, _, repeats4, _ = q9_support(records4)
    assert repeats2 == [1, 2] and repeats4 == [1, 2, 3, 4]
    assert len(support2) == len(support4) == 24
    from studies.sce_inflation_expectations.panel.sections import _person_weights, _support_stats
    s2 = _support_stats(support2, _person_weights(records2, support2, arms2, repeats2))
    s4 = _support_stats(support4, _person_weights(records4, support4, arms2, repeats4))
    assert s2['n_person_months'] == s4['n_person_months']
    assert s2['ess'] == pytest.approx(s4['ess'])
    assert s2['unique_persons'] == s4['unique_persons']


def test_extreme_weight_is_reported_not_hidden(batch, monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], 'MISSING_MODEL', (190001, 0, 1, 'X'))
    cases = []
    for uid in UIDS:
        for repeat in (1, 2):
            arms = {arm: arm_entry(uid, 202001, arm, repeat) for arm in ('A', 'B')}
            weight = 100.0 if uid == 1 else 2.0
            cases.append(make_case(202001, uid, repeat, arms,
                                   prior=prior_mean(uid, 202001), weight=weight))
    with tempfile.TemporaryDirectory() as td:
        out = write_batch(Path(td), 'weight_batch_evaluation_20261020_v1', cases)
        records, meta = load_batch(out / 'cases_private.json')
        panel = build_panel(records, [meta], build_regime_lookup({202001: 2.0}))
    row = panel['experiments']['weight_batch_evaluation_20261020_v1']['sections']['overview']['q9']['A']
    assert row['n_person_months'] == 12
    assert row['max_weight_share'] == pytest.approx(100.0 / (100.0 + 11 * 2.0))
    expected_ess = (100.0 + 22.0) ** 2 / (100.0 ** 2 + 11 * 4.0)
    assert row['ess'] == pytest.approx(expected_ess)


def test_regime_lookup_threshold_boundary():
    lookup = build_regime_lookup({202001: 2.0, 202002: 2.2, 202003: 2.3999, 202004: 2.7})
    assert lookup[202001]['regime'] == 'series_start'
    assert lookup[202002]['regime'] == 'drastic'      # |delta| == 0.2 boundary
    assert lookup[202003]['regime'] == 'calm'         # 0.1999 < 0.2
    assert lookup[202004]['regime'] == 'drastic'
    assert lookup[202003]['abs_delta_pp'] == pytest.approx(0.1999)


def test_grid_display_classes_follow_draft_thresholds(batch):
    _, _, panel = batch
    grid = panel['experiments'][BATCH]['sections']['grid']['A']['six_cell']
    # uid1 alone in college|attached: pooled n=2 -> coverage only
    cell = grid['college|attached']
    assert cell['n'] == 2 and cell['display_class'] == 'coverage'
    assert cell.get('person_mae_pp') is None
    assert MIN_COVERAGE_N == 10
    # 7 persons x 2 months = 14 -> exploratory band, but no single month
    # reaches n>=10, so distribution metrics stay absent
    cell = grid['high_school|attached']
    assert cell['n'] == 13 and cell['display_class'] == 'exploratory'
    assert cell['months_covered'] == 2 and cell['months_reportable'] == 0
    assert cell['min_month_n'] == 6
    assert cell['person_mae_pp'] is None


def test_monthly_center_and_skill(batch):
    _, _, panel = batch
    block = panel['experiments'][BATCH]['sections']['monthly']['A']
    assert len(block['rows']) == 4                    # 2 months x 2 repeats
    assert [r['regime'] for r in block['rows']] == ['series_start', 'series_start',
                                                    'drastic', 'drastic']
    for r in block['rows']:
        assert r['model_center_mae_pp'] == pytest.approx(0.4)
    assert block['skill_s_center_pp'] == pytest.approx(
        block['regime_table']['drastic']['persist_center_mae_pp'] - 0.4)
    assert _f(block['skill_s_person_pp'])


def _f(v):
    return isinstance(v, (int, float)) and np.isfinite(v)


def test_repeat_variance_components_match_temperature_method(batch):
    _, _, panel = batch
    rep = panel['experiments'][BATCH]['sections']['structure']['A']['repeats']
    assert rep['repeats'] == 2
    assert rep['repeat_label'] == '2 遍重复'
    # arm A is constant within person across repeats: within variance 0,
    # noise-adjusted between equals raw between
    assert rep['within_person_repeat_variance_pp2'] == pytest.approx(0.0)
    assert rep['noise_adjusted_between_variance_pp2'] == pytest.approx(
        rep['between_person_repeat_mean_variance_pp2'])
    assert rep['n_persons'] == 23                     # 11 + 12 complete persons
    # cross-check against the reused reference implementation
    matrix = np.asarray([[1.0, 1.0], [3.0, 5.0], [2.0, 4.0]])
    ref = variance_components(matrix)
    within = (0.0 + 2.0 + 2.0) / 3
    assert ref['within_person_repeat_variance_pp2'] == pytest.approx(within)
    assert ref['noise_adjusted_between_variance_pp2'] == pytest.approx(
        np.var([1.0, 4.0, 3.0], ddof=1) - within / 2)


def test_html_contains_anchors_and_display_discipline(batch):
    _, _, panel = batch
    html = render_html(panel)
    assert '未提供' in html and 'n 不足' in html and '未登记' in html
    assert '实验目录' in html and '当前参考实验' in html
    assert '个人绝对误差中位数' in html and '群体中位数MAE' in html
    # tab framework (batch 2): five tabs and the hash router
    for tab, name in TABS:
        assert f"['{tab}'" in html or f'"{tab}"' in html
        assert name in html
    assert 'parseHash' in html and 'syncHash' in html and 'hashchange' in html
    assert '该区暂不支持 Q8' in html
    payload = html.split('panel-data', 1)[1].split('>', 1)[1].split('</script>')[0]
    payload = payload.replace('<\\/', '</')
    for forbidden in ('"userid"', '"agent_id"', '"_pid"', '"q9_bins"', '"model_q9_bins"'):
        assert forbidden not in payload


def test_role_styles_follow_v1_plan():
    """§2 fixed roles: color + dash + marker are redundant encodings."""
    assert ROLE_STYLES['truth'] == {'label': '真人', 'color': '#202733',
                                    'dash': '', 'marker': 'square'}
    assert ROLE_STYLES['ref']['color'] == '#0072B2'
    assert ROLE_STYLES['ref']['marker'] == 'circle' and ROLE_STYLES['ref']['dash'] == ''
    assert ROLE_STYLES['cand']['color'] == '#D55E00'
    assert ROLE_STYLES['cand']['marker'] == 'triangle'
    assert ROLE_STYLES['base']['color'] == '#6B7280'
    assert ROLE_STYLES['base']['dash'] == '6,3'      # dashed baseline
    assert ROLE_STYLES['base']['marker'] == 'diamond'
    colors = {v['color'] for v in ROLE_STYLES.values()}
    assert len(colors) == 4
    # every role carries all three encodings (survives grayscale printing)
    for v in ROLE_STYLES.values():
        assert v['dash'] in ('', '6,3') and v['marker'] in ('square', 'circle', 'triangle', 'diamond')


def test_auto_facts_rules_synthetic():
    """Fixed-rule facts: regression month, low-prior gap, small arm gap."""
    from studies.sce_inflation_expectations.panel.sections import auto_facts, pick_control_arm
    arms = ['A', 'B']
    control = pick_control_arm(arms)
    assert control == 'A'                                  # first arm fallback
    assert pick_control_arm(['baseline', 'x']) == 'baseline'
    # rule 1: a clear 2021-09 style regression vs persistence (primary arm = B)
    rows = []
    for month in (202009, 202109, 202206):
        for rep in (1, 2):
            persist = 0.2
            model = 1.6 if month == 202109 else 0.3
            rows.append({'month': month, 'repeat': rep, 'regime': 'calm',
                         'model_center_mae_pp': model, 'persist_center_mae_pp': persist})
    sections = {
        'monthly': {'B': {'rows': rows}},
        'priors': {'B': {'bands': {'below_2': {'person_mae_pp': 2.0},
                                   '8_or_above': {'person_mae_pp': 6.5}}}},
        'overview': {'q9': {'A': {'center_mae_pp': 0.5}, 'B': {'center_mae_pp': 0.55}}},
    }
    facts = auto_facts(sections, arms, control)
    ids = [f['id'] for f in facts]
    assert 'regression_month' in ids and 'low_prior_closer' in ids
    reg = next(f for f in facts if f['id'] == 'regression_month')
    assert '2021-09' in reg['text'] and '+1.40pp' in reg['text']
    assert reg['evidence'][0]['value_pp'] == pytest.approx(1.6)
    # rule 2 evidence numbers
    low = next(f for f in facts if f['id'] == 'low_prior_closer')
    assert '2.00' in low['text'] and '6.50' in low['text']
    # rule 3 fires when arms barely differ
    sections2 = {
        'monthly': {'B': {'rows': [{'month': 202009, 'repeat': 1, 'regime': 'calm',
                                    'model_center_mae_pp': 0.3, 'persist_center_mae_pp': 0.2}]}},
        'priors': {'B': {'bands': {'below_2': {'person_mae_pp': 3.0},
                                   '8_or_above': {'person_mae_pp': 3.5}}}},
        'overview': {'q9': {'A': {'center_mae_pp': 0.50}, 'B': {'center_mae_pp': 0.55}}},
    }
    facts2 = auto_facts(sections2, arms, control)
    assert 'small_arm_gap' in [f['id'] for f in facts2]
    gap = next(f for f in facts2 if f['id'] == 'small_arm_gap')
    assert '0.05' in gap['text']
    # thresholds: small regression (0.2pp) and small band gap (0.5pp) stay silent
    facts3 = auto_facts(sections2, ['A'], 'A')
    assert all(f['id'] != 'regression_month' for f in facts3)
    assert all(f['id'] != 'low_prior_closer' for f in facts3)
    # facts never exceed three and carry evidence
    assert len(facts) <= 3 and all(f['evidence'] for f in facts)


def test_control_arm_and_facts_in_panel(batch):
    _, _, panel = batch
    exp = panel['experiments'][BATCH]
    assert exp['control_arm'] == 'A'
    facts = exp['facts']
    # synthetic data has no >=0.3pp regression month and no >=1pp band gap
    assert isinstance(facts, list)


def test_old_contract_batch_is_skipped_not_guessed(tmp_path):
    out = tmp_path / 'old_contract_evaluation_20261014_v1'
    out.mkdir()
    (out / 'cases_private.json').write_text(json.dumps([{
        'month': 202003, 'userid': 1, 'repeat': 1, 'profile': {},
        'actual': 2.0, 'previous': 1.8, 'common': {'mean': 2.0}}]))
    records, meta = load_batch(out / 'cases_private.json')
    assert records == []
    assert meta['status'] == 'skipped_old_contract'
    assert 'real' in meta['skip_reason']


def test_registry_sections_and_catalog(batch):
    assert registry.CATALOG['sce_reference_validation_evaluation_20261017_v1']['section'] == '扩大验证'
    assert registry.CATALOG['sce_temperature_evaluation_20261019_v1']['mechanism_group'] == '采样温度'
    assert '新闻条数×统计详略6期' == registry.CATALOG[
        'sce_information_exposure_evaluation_20261019_v1']['label']
    assert '新闻匹配/随机6期' == registry.CATALOG[
        'sce_news_breadth_evaluation_20261019_v1']['label']
    _, _, panel = batch
    cat = panel['catalog']
    assert cat['reference_batch'] == 'sce_reference_validation_evaluation_20261017_v1'
    sections = [g['section'] for g in cat['groups']]
    assert '待登记' in sections                      # synthetic batch lands there
    pending = next(g for g in cat['groups'] if g['section'] == '待登记')
    assert all(not e['registered'] for e in pending['entries'])


def test_drill_cdf_and_quantiles_hand_computed(batch):
    """Weighted CDF at the grid and the five quantiles are hand-checkable."""
    from studies.sce_inflation_expectations.panel.sections import (
        CDF_GRID_PP, _cdf_curve, _quantile_set)
    # two people, weights 1 and 3, values 2 and 6
    values = np.asarray([2.0, 6.0])
    weights = np.asarray([1.0, 3.0])
    cdf = _cdf_curve(values, weights, CDF_GRID_PP)
    total = 4.0
    for g, f in zip(CDF_GRID_PP, cdf):
        expected = (1.0 if 2 <= g else 0.0) + (3.0 if 6 <= g else 0.0)
        assert f == pytest.approx(expected / total)
    q = _quantile_set(values, weights)
    # left-CDF convention (metrics.quantile): first cumsum >= p*total
    assert q['p25'] == pytest.approx(2.0)     # 1.0 >= 1.0 -> value 2
    assert q['p50'] == pytest.approx(6.0)     # 4.0 >= 2.0 -> value 6
    assert q['p90'] == pytest.approx(6.0)
    # drill section: a well-populated synthetic cell exposes truth/model/prior
    _, _, panel = batch
    drill = panel['experiments'][BATCH]['sections']['drill']
    cell = drill['dims']['high_school|attached'.replace('|attached', '|not_attached')] \
        if False else None
    cell = (drill['dims']['six_cell']['cells']['high_school|not_attached']
            ['months']['202001'])
    # month1: only uid4 (uid3 fell out of the support) -> coverage only
    assert cell['n'] == 1 and cell['display_class'] == 'coverage'
    assert 'truth' not in cell
    cell2 = (drill['dims']['six_cell']['cells']['some_college|not_attached']
             ['months']['202002'])
    # month2: only uid6 (prior missing does not remove it from the support)
    assert cell2['n'] == 1 and cell2['display_class'] == 'coverage'


def test_drill_normal_cell_profiles_and_variance():
    """A bigger synthetic batch: normal drill cell + variance decomposition."""
    def case(uid, repeat, education, truth):
        arms = {'A': {'mean': truth + 1.0, 'iqr': 1.0, 'q9_bins': [0.] * 10,
                      'point': 1.0, 'scorer_status': 'ok', 'validation_status': 'valid',
                      'validation_error': None, 'normalization_applied': False}}
        return {
            'month': 202001, 'userid': uid, 'agent_id': f'd_{uid}_{repeat}',
            'profile': {'education_group': education, 'employment_status': 'employed'},
            'stratum': 'syn', 'survey_weight': 1.0, 'inclusion_probability': 0.5,
            'design_survey_weight': 2.0, 'repeat': repeat,
            'real': {'q9_mean': truth, 'q9_iqr': 1.0, 'q9_zero_deflation': 0.0,
                     'q9_bins': [0.] * 10, 'q8_point': 1.0, 'q8_outside_100': False,
                     'weight': 1.0, 'previous_q9_mean': truth - 1.0,
                     'previous_q9_bins': None},
            'arms': arms}
    cases = []
    for uid in range(1, 41):
        for repeat in (1, 2):
            truth = 1.0 if uid <= 20 else 9.0
            cases.append(case(uid, repeat, 'high_school' if uid <= 20 else 'college', truth))
    with tempfile.TemporaryDirectory() as td:
        out = write_batch(Path(td), 'drill_batch_evaluation_20261021_v1', cases)
        records, meta = load_batch(out / 'cases_private.json')
        panel = build_panel(records, [meta], build_regime_lookup({202001: 2.0}))
    exp = panel['experiments']['drill_batch_evaluation_20261021_v1']
    drill = exp['sections']['drill']
    # per-label drill cells: high_school cluster at 1, college cluster at 9
    cell_hs = drill['dims']['six_cell']['cells']['high_school|attached']['months']['202001']
    assert cell_hs['n'] == 20 and cell_hs['display_class'] == 'normal'
    assert cell_hs['truth']['q']['p50'] == pytest.approx(1.0)
    assert cell_hs['truth']['q']['p10'] == pytest.approx(1.0)
    cell_col = drill['dims']['six_cell']['cells']['college|attached']['months']['202001']
    assert cell_col['truth']['q']['p50'] == pytest.approx(9.0)
    # model = truth + 1, prior = truth - 1
    assert cell_hs['arms']['A']['q']['p50'] == pytest.approx(2.0)
    assert cell_hs['prior']['q']['p50'] == pytest.approx(0.0)
    # weighted CDF at grid points: F(0)=0, F(1)=1.0 for the low cluster
    grid = drill['grid']
    cdf = cell_hs['truth']['cdf']
    assert cdf[grid.index(0)] == pytest.approx(0.0)
    assert cdf[grid.index(1)] == pytest.approx(1.0)
    # weighted decomposition: between = (20*(1-5)^2+20*(9-5)^2)/40 = 16,
    # within = 0, and the identity total = between + within holds exactly
    var = drill['variance']['202001']
    assert var['between_cell_var_pp2'] == pytest.approx(16.0)
    assert var['within_cell_var_pp2'] == pytest.approx(0.0, abs=1e-9)
    assert var['total_var_pp2'] == pytest.approx(16.0)
    assert abs(var['between_cell_var_pp2'] + var['within_cell_var_pp2']
               - var['total_var_pp2']) < 1e-9


def test_quality_funnel_and_month_matrix(batch):
    _, _, panel = batch
    q = panel['experiments'][BATCH]['sections']['quality']
    fa = q['arms']['A']['funnel']
    assert fa['attempted'] == 48          # 12 uids x 2 repeats x 1 month pair = 48 arm-A records
    assert fa['scorable'] == 47           # one unscored arm-A record
    # parsed/raw_valid/normalized are absent in the synthetic arm entries -> 未接入
    assert fa['parsed'] is None and fa['raw_valid'] is None
    assert fa['normalized'] is not None   # normalization_applied present (True/False)
    matrix = q['month_arm_missing']
    assert matrix['A']['202001']['assigned'] == 24
    assert matrix['A']['202001']['scorable'] == 23
    assert matrix['A']['202001']['missing_share'] == pytest.approx(1 / 24)
    # the synthetic summary carries an estimate -> shown as 估计, not 未接入
    assert q['cost']['display'] == '估计 0.01 USD'
    assert q['cost']['basis'] == 'estimate'


def test_inputs_plugin_with_fake_trial(tmp_path):
    """Trial matched by protocol id: manifest jobs, environment layers."""
    batch_dir = write_batch(tmp_path, 'inputs_batch_evaluation_20261021_v1', make_cases())
    trial = tmp_path / 'inputs_batch_trial_20261021_v1'
    (trial / '202001').mkdir(parents=True)
    (trial / '202002').mkdir(parents=True)
    (trial / 'protocol.json').write_text(json.dumps({
        'id': 'syn', 'mechanism': 'synthetic_mechanism',
        'information_change': 'none', 'planned_calls': 96,
        'interactions': [], 'prespecified_contrasts': []}))
    (trial / 'manifest.json').write_text(json.dumps({'jobs': [
        {'month': 202001, 'arm': 'A', 'repeat': 1, 'cap_usd': 0.5},
        {'month': 202001, 'arm': 'B', 'repeat': 1, 'cap_usd': 0.25}]}))
    (trial / '202001' / 'environment.json').write_text(json.dumps({
        'layers': [{'name': 'macro', 'scope': 'macro', 'dynamics': 'scheduled',
                    'source': 'outputs/x.json', 'description': 'CPI 层'}],
        'scheduled_events': [1, 2]}))
    (trial / '202001' / 'prompts_A.json').write_text('{}')
    records, meta = load_batch(batch_dir / 'cases_private.json')
    # point the summary protocol id at the fake trial protocol id
    meta['protocol']['id'] = 'syn'
    meta['summary_path'] = str(batch_dir / 'summary.json')
    from studies.sce_inflation_expectations.panel.sections import (
        resolve_trials, section_inputs)
    resolve_trials([meta])
    assert meta['trial']['dir'] == trial.name
    out = section_inputs({'inputs_batch_evaluation_20261021_v1': records},
                         {}, {'inputs_batch_evaluation_20261021_v1': meta})
    inp = out['inputs_batch_evaluation_20261021_v1']
    assert inp['mechanism'] == 'synthetic_mechanism'
    assert inp['planned_jobs'] == 2
    assert inp['budget_cap_usd'] == pytest.approx(0.75)
    m1 = inp['months']['202001']
    assert m1['n_events'] == 2 and m1['prompt_arms'] == ['A']
    assert m1['layers'][0]['name'] == 'macro'
    # unmatched month dir: 202002 has no environment.json -> 未提供
    assert inp['months']['202002']['environment'] == '未提供'


def test_priors_band_series_present(batch):
    _, _, panel = batch
    priors = panel['experiments'][BATCH]['sections']['priors']['A']
    series = priors['band_series']['below_2']
    assert series and {'month', 'prior', 'truth', 'model', 'n'} <= set(series[0])
    amp = priors['direction_amplitude']
    assert set(amp) == {'up', 'stable', 'down'}


def test_diff_series_computed_in_python_with_signs():
    """diffs_vs_control: diff = arm - control per month (positive = worse)."""
    cases = []
    for month in (202001, 202002):
        for uid in UIDS:
            for repeat in (1, 2):
                # month1: B closer to truth than A (improvement, diff<0);
                # month2: B farther (regression, diff>0)
                base = truth_mean(uid, month)
                a_model = base + 0.4
                b_model = base + (0.1 if month == 202001 else 0.9)
                arms = {
                    'A': {'mean': a_model, 'iqr': 1.0, 'q9_bins': [0.] * 10,
                          'point': 1.0, 'scorer_status': 'ok', 'validation_status': 'valid',
                          'validation_error': None, 'normalization_applied': False},
                    'B': {'mean': b_model, 'iqr': 1.0, 'q9_bins': [0.] * 10,
                          'point': 1.0, 'scorer_status': 'ok', 'validation_status': 'valid',
                          'validation_error': None, 'normalization_applied': False},
                }
                cases.append(make_case(month, uid, repeat, arms,
                                       prior=prior_mean(uid, month)))
    with tempfile.TemporaryDirectory() as td:
        out = write_batch(Path(td), 'diff_batch_evaluation_20261021_v1', cases)
        records, meta = load_batch(out / 'cases_private.json')
        panel = build_panel(records, [meta], build_regime_lookup(
            {202001: 2.0, 202002: 2.5}))
    q9 = panel['experiments']['diff_batch_evaluation_20261021_v1']['sections']['overview']['q9']
    row = q9['B']
    d1 = next(d for d in row['diffs_vs_control'] if d['month'] == 202001)
    d2 = next(d for d in row['diffs_vs_control'] if d['month'] == 202002)
    # constant shifts -> center MAE equals the shift per month
    assert d1['arm_mae'] == pytest.approx(0.1) and d1['other_mae'] == pytest.approx(0.4)
    assert d1['diff'] == pytest.approx(-0.3)          # improvement is negative
    assert d2['arm_mae'] == pytest.approx(0.9) and d2['other_mae'] == pytest.approx(0.4)
    assert d2['diff'] == pytest.approx(+0.5)          # regression is positive
    # the control arm's own vs_control series is empty by construction
    for d in q9['A']['diffs_vs_control']:
        assert d['diff'] is None and d['other_mae'] is None
    # vs_persist: prior = truth - e(u); persistence error is positive, so the
    # model (truth + 0.4 for arm A) beats persistence in both months -> diff<0
    for d in q9['A']['diffs_vs_persist']:
        assert d['arm_mae'] == pytest.approx(0.4)
        assert _f(d['other_mae']) and d['diff'] == pytest.approx(
            d['arm_mae'] - d['other_mae'])
        assert d['diff'] < 0


def test_no_common_support_no_fallback(tmp_path, monkeypatch):
    """Disjoint arm supports: empty main table, note present, sensitivity kept."""
    monkeypatch.setattr(sys.modules[__name__], 'MISSING_MODEL', (190001, 0, 1, 'X'))
    bad = {'mean': None, 'iqr': None, 'q9_bins': None, 'point': None,
           'scorer_status': 'error', 'validation_status': 'invalid',
           'validation_error': 'x', 'normalization_applied': False}
    cases = []
    for uid in UIDS:
        for repeat in (1, 2):
            # arms A and B cover completely disjoint person sets -> no common support
            if uid <= 6:
                arms = {'A': arm_entry(uid, 202001, 'A', repeat), 'B': dict(bad)}
            else:
                arms = {'A': dict(bad), 'B': arm_entry(uid, 202001, 'B', repeat)}
            cases.append(make_case(202001, uid, repeat, arms,
                                   prior=prior_mean(uid, 202001)))
    out = write_batch(tmp_path, 'disjoint_batch_evaluation_20261021_v1', cases)
    records, meta = load_batch(out / 'cases_private.json')
    panel = build_panel(records, [meta], build_regime_lookup({202001: 2.0}))
    exp = panel['experiments']['disjoint_batch_evaluation_20261021_v1']
    ov = exp['sections']['overview']
    assert ov['support_note'] and '无法作主比较表' in ov['support_note']
    for arm in ('A', 'B'):
        row = ov['q9'][arm]
        assert row['n_person_months'] == 0
        assert row['center_mae_pp'] is None and row['person_mae_pp'] is None
        assert row['w1_pp'] is None
        assert all(d['diff'] is None for d in row['diffs_vs_control'])
        # sensitivity keeps per-arm usable supports even without a common one
        assert ov['support_sensitivity'][arm]['n_person_months'] == 6
    # sections downstream must not blow up on the empty support
    assert exp['sections']['monthly']['A']['rows'] == []
    assert exp['sections']['quality']['q9_common_person_months'] == 0


def test_q8_months_independent_of_q9_support(tmp_path, monkeypatch):
    """A month with all-Q9-failed records still appears in the Q8 summary."""
    monkeypatch.setattr(sys.modules[__name__], 'MISSING_MODEL', (190001, 0, 1, 'X'))
    cases = []
    for uid in UIDS:
        for month in (202001, 202002):
            for repeat in (1, 2):
                arms = {arm: arm_entry(uid, month, arm, repeat) for arm in ('A', 'B')}
                if month == 202002:      # Q9 fails for everyone in month2
                    for arm in ('A', 'B'):
                        arms[arm] = {'mean': None, 'iqr': None, 'q9_bins': None,
                                     'point': round(model_mean(arm, uid, month)),
                                     'scorer_status': 'error', 'validation_status': 'invalid',
                                     'validation_error': 'x', 'normalization_applied': False}
                cases.append(make_case(month, uid, repeat, arms,
                                       prior=prior_mean(uid, month)))
    out = write_batch(tmp_path, 'q8month_batch_evaluation_20261021_v1', cases)
    records, meta = load_batch(out / 'cases_private.json')
    panel = build_panel(records, [meta], build_regime_lookup(
        {202001: 2.0, 202002: 2.5}))
    exp = panel['experiments']['q8month_batch_evaluation_20261021_v1']
    q8 = exp['sections']['overview']['q8']['A']
    assert q8['n_person_months'] == 24          # 12 uids x 2 months on Q8 support
    assert _f(q8['center_mae_pp'])              # month2 contributes to Q8
    assert q8['months_covered'] == [202001, 202002]


def test_drill_ess_merges_repeats_and_names_pooling():
    """12 equal-weight persons x 2 repeats: n=12, ESS=12, repeat-pooled label."""
    cases = []
    for uid in range(1, 13):
        for repeat in (1, 2):
            truth = float(uid)
            arms = {'A': {'mean': truth, 'iqr': 1.0, 'q9_bins': [0.] * 10,
                          'point': truth, 'scorer_status': 'ok', 'validation_status': 'valid',
                          'validation_error': None, 'normalization_applied': False}}
            cases.append({
                'month': 202001, 'userid': uid, 'agent_id': f'e_{uid}_{repeat}',
                'profile': {'education_group': 'high_school', 'employment_status': 'employed'},
                'stratum': 'syn', 'survey_weight': 1.0, 'inclusion_probability': 0.5,
                'design_survey_weight': 2.0, 'repeat': repeat,
                'real': {'q9_mean': truth, 'q9_iqr': 1.0, 'q9_zero_deflation': 0.0,
                         'q9_bins': [0.] * 10, 'q8_point': truth, 'q8_outside_100': False,
                         'weight': 1.0, 'previous_q9_mean': truth - 0.1,
                         'previous_q9_bins': None},
                'arms': arms})
    with tempfile.TemporaryDirectory() as td:
        out = write_batch(Path(td), 'ess_batch_evaluation_20261021_v1', cases)
        records, meta = load_batch(out / 'cases_private.json')
        panel = build_panel(records, [meta], build_regime_lookup({202001: 2.0}))
    drill = panel['experiments']['ess_batch_evaluation_20261021_v1']['sections']['drill']
    cell = drill['dims']['six_cell']['cells']['high_school|attached']['months']['202001']
    assert cell['n'] == 12
    assert cell['ess'] == pytest.approx(12.0, abs=1e-9)
    assert cell['distribution_kind'] == 'repeat_pooled'


def test_auto_facts_neutral_wording_and_arm_field(batch):
    _, _, panel = batch
    exp = panel['experiments'][BATCH]
    for fact in exp['facts']:
        assert fact.get('arm') in ('A', 'B')
        assert '仍被压缩' not in fact['text']
    low = next((f for f in exp['facts'] if f['id'] == 'low_prior_closer'), None)
    if low is not None:
        assert '不推断压缩方向' in low['text']
        bias_rows = [e for e in low['evidence'] if '偏差' in e['metric']]
        assert len(bias_rows) == 2


def test_arm_labels_cover_known_arms_and_render(batch):
    from studies.sce_inflation_expectations.panel.registry import ARM_LABELS, arm_label
    expected = {'reference', 'baseline', 'shared_price', 'matched_role', 'shuffled_role',
                'news_matched', 'news_randomized', 'temperature_10', 'direct'}
    assert expected <= set(ARM_LABELS)
    assert arm_label('matched_role') == '匹配角色'
    assert arm_label('unknown_arm_xyz') == 'unknown_arm_xyz'
    _, _, panel = batch
    html = render_html(panel)
    assert 'arm_labels' in html
    assert '匹配角色' in html and '共享价格' in html


def test_build_receipt_fields(tmp_path):
    from scripts.build_sce_experiment_panel import (
        STATS_VERSION, build_receipt, write_atomic)
    target = tmp_path / 'out' / 'x.json'
    write_atomic(target, '{"a":1}\n')
    assert target.read_text() == '{"a":1}\n'
    assert not (tmp_path / 'out' / 'x.json.tmp').exists()
    fake_dir = tmp_path / 'fake_evaluation_20261021_v1'
    fake_dir.mkdir()
    (fake_dir / 'cases_private.json').write_text('[]')
    metas = [{'batch': 'b1', 'summary_path': str(fake_dir / 'summary.json'),
              'n_records': 3, 'status': 'ok'}]
    panel = {'generated_at_utc': '2026-10-21T00:00:00+00:00'}
    receipt = build_receipt(metas, panel)
    assert receipt['stats_version'] == STATS_VERSION == 'panel-stats-v1.1'
    assert receipt['python_version']
    assert len(receipt['panel_modules_sha256']) == 6
    assert receipt['source_batches'][0]['batch'] == 'b1'
    assert len(receipt['source_batches'][0]['cases_sha256']) == 64
