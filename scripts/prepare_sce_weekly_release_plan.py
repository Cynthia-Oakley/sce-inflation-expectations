#!/usr/bin/env python3
"""Offline weekly publication-reset and pre-release score schedule; no LLM."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.frozen_batch import read_json,dump,sha
from studies.sce_inflation_expectations.experiments.weekly_design import weekly_cutoffs
from studies.sce_inflation_expectations.experiments.weekly_release_protocol import schedule,score_cutoffs
from studies.sce_inflation_expectations.submission_tools.reproduce import no_network


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh local outputs directory required')
    catalog=ROOT/'data/evaluation/sce_recent_b_evaluation_20261025_v1/aggregate_inputs.json'
    months=['202511','202512',*[f'2026{m:02}' for m in range(1,10)]]
    with no_network():
        releases=read_json(catalog)['headline_releases'];points=schedule([c for m in months for c in weekly_cutoffs(m)],releases)
        evaluation=score_cutoffs(points,releases)
        result=dict(status='offline_release_reset_and_metric_draft_not_execution_package',months=months,
            candidate_weekly_points=len(points),candidate_core_n=300,arithmetic_main_calls=len(points)*300,
            resets_visible_at_weekly_grid=sum(p['reset_required'] for p in points),
            reset_clock='actual publication availability, not month boundaries; date-only availability conservatively next NY day',
            primary_metric='One last-week-in-survey-month Q9 median forecast per month; MAE/RMSE versus that monthly official SCE',
            supplementary='At least 7/14/21 days before publication, one forecast per month and panel; direction, false alarms, anomaly strata',
            metric_defaults_proposed_not_frozen=dict(direction_epsilon_pp=.1,evaluation_only_anomaly_month_change_pp=.3),
            target_alignment_limit='A last-week population snapshot is not the exact month-long survey aggregate; weighted-CDF month aggregation is a separate sensitivity.',
            input_plan_role='Each point exposes only an anchor with an earlier reference month and proven publication before its cutoff.',
            real_forecasts=0,new_API_calls=0,live_ready=False,
            pending=['300-person roster/design weights','intact joint donor calibration at reset','timestamp-based live state updates',
                     'bounded news exposure/seen-article memory','full weekly E overlays','final messages/Core/replay','exact paid scope and budget'])
        out.mkdir();dump(out/'summary.json',result);dump(out/'state_clock_plan.json',points)
        # Publication dates and selection rules only; no target values here.
        dump(out/'evaluation_clock_plan.json',evaluation)
        paths=[catalog,Path(__file__),ROOT/'studies/sce_inflation_expectations/experiments/weekly_design.py',
               ROOT/'studies/sce_inflation_expectations/experiments/weekly_release_protocol.py']
        dump(out/'manifest.json',dict(source_sha256={str(p.relative_to(ROOT)):sha(p) for p in paths},
            files_sha256={p.name:sha(p) for p in out.iterdir()},new_API_calls=0))
    import json
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
