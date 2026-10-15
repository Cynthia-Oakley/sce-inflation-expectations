from studies.sce_inflation_expectations.evaluation.revision_format import describe_failed_coverage


def test_high_failure_support_has_only_descriptions_not_bootstrap_significance():
    rows = []
    for month in [202004, 202105]:
        for repeat in [1, 2]:
            for i in range(4):
                y = 1+i
                rows.append(dict(month=month, repeat=repeat, userid=month+i, common=True,
                    actual=y, previous=y-.1, original=y+.5, belief_start=y+.25,
                    copy_previous=y-.1, history_anchor_half=y-.2, actual_iqr=3,
                    actual_zero_deflation=1, actual_point=y, previous_point=y-.1, survey_weight=1))
    result = describe_failed_coverage(rows)
    assert result['common_generation_rows'] == 16
    assert result['person_months_with_both_repeats'] == 8
    for value in result['belief_start_minus_original'].values():
        assert value['paired_person_within_month_ci95_pp'] is None
    assert result['belief_start_minus_original']['sample_center_mae_pp']['change_pp'] == -.25
