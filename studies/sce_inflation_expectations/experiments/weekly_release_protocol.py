"""Weekly reset/score clocks, isolated from the running monthly experiment.

No model client or population calibration is executed here. Scheduling uses
release metadata; the optional scorer opens target values only after forecasts
exist. Calendar target month, publication time and state-reset cycle are distinct.
"""
from datetime import datetime, date, time, timedelta
import math
from zoneinfo import ZoneInfo

from ..evaluation.metrics import headline_errors

NY=ZoneInfo('America/New_York')


def aware(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('Timezone-aware cutoff required')
    return result


def known_from(release):
    """Date-only releases enter the next day; no guessed intraday timestamp."""
    if release.get('verified_published_at'):
        instant=aware(release['verified_published_at'])
        if instant.astimezone(NY).date()!=date.fromisoformat(release['published_date']):
            raise ValueError('Verified release timestamp conflicts with its New York date')
        return instant
    day=date.fromisoformat(release['published_date'])+timedelta(days=1)
    return datetime.combine(day,time(0),NY)


def schedule(cutoffs,releases):
    """A new PUBLIC anchor changes the cycle; a calendar boundary alone does not."""
    points=sorted(map(aware,cutoffs));refs=[r['reference_period'] for r in releases]
    if len(set(points))!=len(points) or len(refs)!=len(set(refs)):
        raise ValueError('Unique weekly points and release reference periods required')
    previous=None;rows=[]
    for point in points:
        target=point.astimezone(NY).strftime('%Y-%m')
        eligible=[r for r in releases if r['reference_period']<target and known_from(r)<=point]
        if not eligible:raise ValueError('No strictly past public anchor before weekly cutoff')
        anchor=max(eligible,key=lambda r:(known_from(r),r['reference_period']))
        key=(anchor['reference_period'],anchor['published_date'])
        rows.append(dict(cutoff=point.isoformat(),target_reference_period=target,
            anchor_reference_period=anchor['reference_period'],anchor_published_date=anchor['published_date'],
            anchor_known_from=known_from(anchor).isoformat(),anchor_pp=anchor['value_pp'],
            reset_required=previous!=key,cycle_key='|'.join(key),
            state_source='public_anchor_calibrated_joint_donor' if previous!=key else 'same_household_previous_week'))
        previous=key
    return rows


def score_cutoffs(points,releases,horizons=(7,14,21)):
    """One predeclared point per MONTH per panel, never a best-error selection.

    Primary: last weekly point in survey month. Horizon panels: latest such
    point at least H calendar days before the target publication date. Actual
    lead times vary and are reported explicitly. No post-release calibrated
    state can be used to score its own calibration target.
    """
    refs={r['reference_period']:r for r in releases};out=[]
    targets=sorted({p['target_reference_period'] for p in points})
    if any(type(h) is not int or h<1 for h in horizons):raise ValueError('Positive integer leads required')
    for target in targets:
        if target not in refs:raise ValueError('Missing target release metadata')
        release=refs[target];release_day=date.fromisoformat(release['published_date'])
        safe=[p for p in points if p['target_reference_period']==target
              and p['anchor_reference_period']<target
              and aware(p['cutoff']).astimezone(NY).date()<release_day]
        for label,h in [('last_week_in_month',0),*[(f'at_least_{h}_days_before_release',h) for h in horizons]]:
            eligible=[p for p in safe if (release_day-aware(p['cutoff']).astimezone(NY).date()).days>=h]
            selected=max(eligible,key=lambda p:aware(p['cutoff'])) if eligible else None
            out.append(dict(target_reference_period=target,panel=label,minimum_lead_days=h,
                cutoff=selected['cutoff'] if selected else None,
                actual_lead_days=(release_day-aware(selected['cutoff']).astimezone(NY).date()).days if selected else None,
                target_published_date=release['published_date'],
                anchor_reference_period=selected['anchor_reference_period'] if selected else None))
    return out


def direction(value,epsilon=.1):
    if not math.isfinite(value) or epsilon<0:raise ValueError('Finite change and nonnegative tolerance required')
    return 'up' if value>epsilon+1e-10 else 'down' if value< -epsilon-1e-10 else 'flat'


def evaluate_frozen_points(forecasts,releases,*,epsilon=.1,anomaly=.3,horizons=(7,14,21)):
    """National level/innovation errors; never treat 47 points as 47 truths.

    Targets are opened here only. `forecast_pp` must be the raw pre-reset
    prediction, not a calibrated state or an A-fitted blended index. This helper
    cannot certify when an old forecast was actually sealed; caller must bind
    immutable generation and forecast-kind provenance separately.
    """
    if not forecasts:raise ValueError('Nonempty sealed forecasts required')
    keys=[(r['target_reference_period'],aware(r['cutoff']).isoformat()) for r in forecasts]
    if len(keys)!=len(set(keys)):raise ValueError('Duplicate weekly forecast')
    for row in forecasts:
        if row.get('forecast_kind')!='raw_model_pre_reset':
            raise ValueError('Post-reset or blended states are not raw predictive evidence')
        if type(row['forecast_pp']) not in (int,float) or not math.isfinite(row['forecast_pp']):
            raise ValueError('Finite forecast required')
    points=schedule([r['cutoff'] for r in forecasts],releases)
    bycut={r['cutoff']:r for r in points};bykey=dict(zip(keys,forecasts));ref={r['reference_period']:r for r in releases}
    for forecast in forecasts:
        point=bycut[aware(forecast['cutoff']).isoformat()]
        for field in ('target_reference_period','anchor_reference_period','anchor_pp'):
            if forecast[field]!=point[field]:raise ValueError('Forecast/public-anchor metadata mismatch: '+field)
    panels={}
    for selection in score_cutoffs(points,releases,horizons):
        if selection['cutoff'] is None:continue
        key=(selection['target_reference_period'],selection['cutoff']);r=bykey[key]
        target=ref[key[0]]['value_pp'];baseline=r['anchor_pp'];prediction=r['forecast_pp']
        year,month=map(int,key[0].split('-'));previous=f'{year-(month==1):04}-{12 if month==1 else month-1:02}'
        mom=None if previous not in ref else target-ref[previous]['value_pp']
        row=dict(**selection,truth_pp=target,forecast_pp=prediction,baseline_pp=baseline,
            forecast_innovation_pp=prediction-baseline,realized_innovation_pp=target-baseline,
            predicted_direction=direction(prediction-baseline,epsilon),actual_direction=direction(target-baseline,epsilon),
            target_month_change_pp=mom,evaluation_only_anomaly=mom is not None and abs(mom)+1e-10>=anomaly)
        panels.setdefault(selection['panel'],[]).append(row)
    result={}
    for label,rows in panels.items():
        raw=headline_errors([r['forecast_pp'] for r in rows],[r['truth_pp'] for r in rows])
        baseline=headline_errors([r['baseline_pp'] for r in rows],[r['truth_pp'] for r in rows])
        up=[r for r in rows if r['actual_direction']=='up'];no_up=[r for r in rows if r['actual_direction']!='up']
        result[label]=dict(n_target_months=len(rows),raw=raw,persistence=baseline,
            relative_MAE_reduction=None if baseline['mae_pp']==0 else 1-raw['mae_pp']/baseline['mae_pp'],
            direction_accuracy=sum(r['predicted_direction']==r['actual_direction'] for r in rows)/len(rows),
            upward_recall=None if not up else sum(r['predicted_direction']=='up' for r in up)/len(up),
            false_upward_alarm_rate=None if not no_up else sum(r['predicted_direction']=='up' for r in no_up)/len(no_up),
            rows=rows)
    return dict(panels=result,epsilon_pp=epsilon,anomaly_threshold_pp=anomaly,
        n_distinct_target_months=len({r['target_reference_period'] for r in forecasts}),
        no_parameter_fitting=True,new_API_calls=0,
        limits=['Monthly targets are survey-period aggregates, not weekly ground truth.',
                'Lead-time panels reuse the same target months and are not independent samples.',
                'Anomaly status uses released target data for evaluation grouping only; never an input trigger.',
                'Retrospective cutoff eligibility alone does not establish ex-ante forecast sealing.'])
