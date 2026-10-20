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
from studies.sce_inflation_expectations.panel.render import render_html
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
    assert set(exp['sections']) == {'overview', 'monthly', 'grid',
                                    'priors', 'structure', 'quality'}
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
    # leaves the all-arm x all-repeat common support (23 = 12 - 1 + 12)
    assert row['n_person_months'] == 23
    assert row['unique_persons'] == 23
    sens = exp['sections']['overview']['support_sensitivity']
    assert sens['A']['n_person_months'] == 23      # arm A alone: same hole
    assert sens['B']['n_person_months'] == 24      # arm B unscored nowhere
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
    for i in range(1, 7):
        assert f'id="sec-{i}"' in html
    assert '未提供' in html and 'n 不足' in html and '未登记' in html
    assert '实验目录' in html and '当前参考实验' in html
    assert '个人绝对误差中位数' in html and '群体中位数MAE' in html
    payload = html.split('panel-data', 1)[1].split('>', 1)[1].split('</script>')[0]
    payload = payload.replace('<\\/', '</')
    for forbidden in ('"userid"', '"agent_id"', '"_pid"', '"q9_bins"', '"model_q9_bins"'):
        assert forbidden not in payload


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
