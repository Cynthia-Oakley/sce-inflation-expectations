"""Synthetic smoke tests for the offline SCE experiment panel (zero-call).

A tiny same-contract batch (2 months x 12 persons x 2 repeats x 2 arms, with
one unscored record and one missing prior) is pushed through
adapter -> six sections -> HTML render. Numbers are hand-checkable by
construction: truth = 2 + 0.1*uid (+0.3 in month 2), prior = truth - (0.2 +
0.05*uid), model A = truth + 0.4, model B = truth - 0.1.
"""
import json

import pytest

from studies.sce_inflation_expectations.panel import adapters
from studies.sce_inflation_expectations.panel.adapters import load_batch
from studies.sce_inflation_expectations.panel.regimes import build_regime_lookup
from studies.sce_inflation_expectations.panel.render import render_html
from studies.sce_inflation_expectations.panel.sections import MIN_CELL_N, build_panel

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


def make_cases():
    cases = []
    for month in MONTHS:
        for uid in UIDS:
            prior = None if (month, uid) == MISSING_PRIOR else prior_mean(uid, month)
            for repeat in (1, 2):
                arms = {}
                for arm in ('A', 'B'):
                    if (month, uid, repeat, arm) == MISSING_MODEL:
                        arms[arm] = {'mean': None, 'iqr': None, 'q9_bins': None,
                                     'point': None, 'scorer_status': 'error',
                                     'validation_status': 'invalid',
                                     'validation_error': 'synthetic',
                                     'normalization_applied': False}
                    else:
                        arms[arm] = {'mean': model_mean(arm, uid, month), 'iqr': 1.0,
                                     'q9_bins': [10., 20., 30., 40., 0., 0., 0., 0., 0., 0.],
                                     'point': round(model_mean(arm, uid, month)),
                                     'scorer_status': 'ok', 'validation_status': 'valid',
                                     'validation_error': None,
                                     'normalization_applied': arm == 'B'}
                cases.append({
                    'month': month, 'userid': uid, 'agent_id': f'syn_{uid}_{repeat}',
                    'profile': dict(PROFILE[uid]), 'stratum': 'syn',
                    'survey_weight': 1.0, 'inclusion_probability': 0.5,
                    'design_survey_weight': 2.0, 'repeat': repeat,
                    'real': {'q9_mean': truth_mean(uid, month), 'q9_iqr': 2.0,
                             'q9_zero_deflation': 0.0,
                             'q9_bins': [0., 0., 25., 25., 25., 25., 0., 0., 0., 0.],
                             'q8_point': float(uid), 'q8_outside_100': False,
                             'weight': 1.0, 'previous_q9_mean': prior,
                             'previous_q9_bins': None},
                    'arms': arms,
                })
    return cases


@pytest.fixture()
def batch(tmp_path):
    out = tmp_path / BATCH
    out.mkdir()
    (out / 'cases_private.json').write_text(json.dumps(make_cases()))
    (out / 'summary.json').write_text(json.dumps({
        'status': 'synthetic', 'estimated_run_cost_usd_not_provider_bill': 0.01,
        'protocol': {'id': 'syn', 'months': list(MONTHS), 'n_per_month': 12,
                     'arms': ['A', 'B'], 'generation_repeats': [1, 2],
                     'model': 'test-model', 'temperature': 0.0}}))
    records, meta = load_batch(out / 'cases_private.json')
    regime_lookup = build_regime_lookup({202001: 2.0, 202002: 2.5})
    panel = build_panel(records, [meta], regime_lookup)
    return records, meta, panel


def test_adapter_record_shape_and_weight_split(batch):
    records, meta, _ = batch
    assert meta['status'] == 'ok'
    assert meta['registered'] is False          # 未登记批次也要能显示
    assert len(records) == 2 * len(UIDS) * 2 * 2
    # each person's design weight (2.0) is split across two repeats
    assert all(r['weight'] == pytest.approx(1.0) for r in records)
    for r in records:
        assert {'month', 'arm', 'repeat', 'cell', 'prior_q9_mean',
                'truth_q9_mean', 'model_q9_mean', 'scorer_status',
                'normalization_applied', 'model_shape', 'truth_shape'} <= set(r)
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


def test_persistence_baseline_hand_computed(batch):
    _, _, panel = batch
    exp = panel['experiments'][BATCH]
    overview = exp['sections']['overview']['q9']['A']['persistence']
    # month 202001: uid3 repeat1 model is missing -> that person-month drops
    # from the identical support; month 202002: uid6 prior missing.
    err = {uid: abs(prior_mean(uid, 202001) - truth_mean(uid, 202001)) for uid in UIDS}
    m1 = (2 * sum(err.values()) - err[3]) / 23
    m2 = 2 * sum(err[u] for u in UIDS if u != 6) / 22
    assert overview['mae_pp'] == pytest.approx((m1 + m2) / 2)
    # identical-support person-months: 12 (month1; uid3 still has repeat2)
    # + 11 (month2 without uid6) = 23
    assert overview['n_identical_support'] == 23
    # model MAE is exactly 0.4 for arm A on every scored record
    model = exp['sections']['overview']['q9']['A']
    assert model['mae_pp'] == pytest.approx(0.4)


def test_regime_lookup_threshold_boundary():
    lookup = build_regime_lookup({202001: 2.0, 202002: 2.2, 202003: 2.3999, 202004: 2.7})
    assert lookup[202001]['regime'] == 'series_start'
    assert lookup[202002]['regime'] == 'drastic'      # |delta| == 0.2 boundary
    assert lookup[202003]['regime'] == 'calm'         # 0.1999 < 0.2
    assert lookup[202004]['regime'] == 'drastic'
    assert lookup[202003]['abs_delta_pp'] == pytest.approx(0.1999)


def test_n_under_10_cells_are_suppressed(batch):
    _, _, panel = batch
    exp = panel['experiments'][BATCH]
    grid = exp['sections']['grid']['A']['six_cell']
    # only uid1 is college|attached: 1 person x 2 months = 2 < 10
    cell = grid['college|attached']
    assert cell['n'] == len(MONTHS)
    assert cell['suppressed'] is True
    assert cell.get('mae_pp') is None
    assert MIN_CELL_N == 10
    # a well-populated cell is not suppressed
    assert grid['high_school|attached']['suppressed'] is False


def test_monthly_regime_skill(batch):
    _, _, panel = batch
    exp = panel['experiments'][BATCH]
    block = exp['sections']['monthly']['A']
    assert [r['regime'] for r in block['rows']] == ['series_start', 'drastic']
    # arm A model error is a constant 0.4 on every scored record
    assert block['regime_table']['drastic']['model_mae_pp'] == pytest.approx(0.4)
    assert block['skill_s_drastic_pp'] == pytest.approx(
        block['regime_table']['drastic']['persist_mae_pp'] - 0.4)


def test_html_contains_anchors_and_display_discipline(batch):
    _, _, panel = batch
    html = render_html(panel)
    for i in range(1, 7):
        assert f'id="sec-{i}"' in html
    assert '未提供' in html          # missing / not-provided discipline
    assert 'n 不足' in html          # suppression wording
    assert '未登记' in html
    # the embedded payload must not carry person identifiers or raw bin vectors
    payload = html.split('panel-data', 1)[1].split('>', 1)[1].split('</script>')[0]
    payload = payload.replace('<\\/', '</')
    for forbidden in ('"userid"', '"agent_id"', '"_pid"', '"q9_bins"', '"model_q9_bins"'):
        assert forbidden not in payload


def test_shape_and_repeat_sections(batch):
    _, _, panel = batch
    exp = panel['experiments'][BATCH]
    structure = exp['sections']['structure']['A']
    # arm A model = truth + 0.4 constant: same cross-person dispersion as truth
    assert structure['cross_person']['model_std_pp'] == pytest.approx(
        structure['cross_person']['truth_std_pp'])
    # within-person std across the two repeats is exactly 0 for arm A;
    # uid3 month1 has only one valid repeat and is excluded: 11 + 12 = 23
    assert structure['repeats']['within_person_std_pp'] == pytest.approx(0.0)
    assert structure['repeats']['n_persons'] == 23


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


def test_registry_lists_known_batches():
    assert 'sce_reference_validation_evaluation_20261017_v1' in adapters.REGISTRY
    label, _ = adapters.REGISTRY['sce_procurement_qwen_evaluation_20261020_v2']
    assert '采购' in label
