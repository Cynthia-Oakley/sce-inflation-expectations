"""Independent boundary tests: vintage timing, profile-only donors, dated E."""
import copy,json,unittest
from types import SimpleNamespace
import numpy as np,pandas as pd
from socioverse.schemas import EnvironmentBundle,PopulationBundle
from pathlib import Path
from studies.sce_inflation_expectations.environment_authoring.vintages import select_vintages
from studies.sce_inflation_expectations.monthly_population import PROFILE_COLUMNS
from studies.sce_inflation_expectations.population_forecast import profile_view,synthesize,donor_probabilities
from studies.sce_inflation_expectations.dated_prompt import build_dated_messages
from studies.sce_inflation_expectations.model import build_sce_messages_v2,SCEEnvironmentProvider


def version(value,pub,kind='revision'):
    return dict(measure='jobs',unit='thousands',reference_period='2021-03',value=value,
                published_at=pub,source_version='test-'+pub,source_url='https://example.org/report',vintage_kind=kind)


class VintageTests(unittest.TestCase):
    def test_revision_is_usable_only_after_its_publication(self):
        rows=[version(916,'2021-04-02T08:30:00-04:00','initial_release'),
              version(770,'2021-05-07T08:30:00-04:00'),version(785,'2021-06-04T08:30:00-04:00')]
        for cutoff,expected in [('2021-04-30T23:59:59-04:00',916),('2021-05-31T23:59:59-04:00',770),('2021-06-30T23:59:59-04:00',785)]:
            self.assertEqual(select_vintages(rows,cutoff)[0]['value'],expected)
        self.assertEqual(select_vintages(rows,'2021-06-30T23:59:59-04:00',policy='first_release')[0]['value'],916)
        self.assertEqual(rows[0]['value'],916)

    def test_earliest_stored_revision_is_not_initial_release(self):
        row=version(770,'2021-05-07T08:30:00-04:00')
        self.assertEqual(select_vintages([row],'2021-06-30T23:59:59-04:00',policy='first_release'),[])
        del row['vintage_kind']
        with self.assertRaises(ValueError):select_vintages([row],'2021-06-30T23:59:59-04:00',policy='first_release')

    def test_ambiguous_conflict_and_naive_timestamp_rejected(self):
        a=version(1,'2021-04-02T08:30:00-04:00');b=copy.deepcopy(a);b['value']=2
        with self.assertRaises(ValueError):select_vintages([a,b],'2021-06-30T23:59:59-04:00')
        with self.assertRaises(ValueError):select_vintages([a],'2021-06-30')
        with self.assertRaises(ValueError):select_vintages([a],'2021-06-30T23:59:59-04:00',policy='retrospective_latest')


def profiles():
    rows=[]
    for month in [202501,202502]:
        for uid,weight in [(1,1.),(2,3.),(3,np.nan)]:
            row={col:np.nan for col in PROFILE_COLUMNS}
            row.update(date=month,userid=uid,weight=weight,_AGE_CAT='Under 40' if uid==1 else 'Over 60',
                       _EDU_CAT='College' if uid==1 else 'High School',_HH_INC_CAT='Under 50k',
                       _REGION_CAT='South',_NUM_CAT='Low',Q43=(1 if uid==1 else 2) if month==202501 else np.nan,D3=0,
                       Q10_1=1,secret_true_answer=99)
            rows.append(row)
    return pd.DataFrame(rows)


class PopulationTests(unittest.TestCase):
    def build(self,**kwargs):
        args=dict(target_month='2026-10',donor_end=202502,available_at='2026-09-28T00:00:00+00:00',
                  cutoff='2026-09-30T23:59:59-04:00',n=2000,core_n=300,seed=42)
        args.update(kwargs);return synthesize(profile_view(profiles()),**args)

    def test_joint_donor_weights_used_once_and_answers_absent(self):
        bundle,meta,private=self.build();PopulationBundle.model_validate(bundle)
        self.assertEqual(meta['excluded_missing_weight_rows'],1)
        self.assertEqual(len(meta['core_ids']),300)
        old=sum(p['attributes']['age_group']=='Over 60' for p in bundle['personas'])/2000
        self.assertAlmostEqual(old,.75,delta=.035)
        for p in bundle['personas']:
            a=p['attributes'];self.assertEqual(p['weight'],1)
            self.assertEqual(a['education_group'],'college' if a['age_group']=='Under 40' else 'high_school')
            self.assertNotIn('secret_true_answer',a);self.assertNotIn('userid',a)
        self.assertEqual(self.build(),(bundle,meta,private))

    def test_unavailable_same_month_and_invalid_month_rejected(self):
        for change in [dict(available_at='2026-10-01T00:00:00-04:00'),dict(target_month='2025-02'),dict(target_month='2026-13')]:
            with self.subTest(change=change),self.assertRaises(ValueError):self.build(**change)

    def test_housing_uses_only_own_past_and_invalidates_after_move(self):
        d=profiles();d.loc[(d.userid==1)&(d.date==202502),'D3']=1
        view=profile_view(d)
        self.assertEqual(view[(view.userid==1)&(view.date==202501)].iloc[0].housing_tenure,'owner')
        self.assertEqual(view[(view.userid==1)&(view.date==202502)].iloc[0].housing_tenure,'unknown')
        self.assertEqual(view[(view.userid==2)&(view.date==202502)].iloc[0].housing_tenure,'renter')

    def test_conditional_weight_distribution_and_bad_weights(self):
        view=profile_view(profiles());view.loc[view.userid==1,'weight']=0
        with self.assertRaises(ValueError):donor_probabilities(view,202502)
        view=profile_view(profiles());view.loc[view.date==202501,'weight']=view.loc[view.date==202501,'weight']*10
        donors,p,_=donor_probabilities(view,202502)
        self.assertAlmostEqual(p.sum(),1);self.assertAlmostEqual(p[donors.userid.eq(2)].sum(),.75)

    def test_twelve_wave_mixture_does_not_overweight_larger_waves(self):
        source=profile_view(profiles());parts=[]
        for i in range(1,13):
            wave=source[source.date==202501].copy();wave['date']=202400+i
            if i%2==0:wave=wave[wave.userid==2].copy()
            wave['weight']=wave['weight']*i
            parts.append(wave)
        donors,p,months=donor_probabilities(pd.concat(parts,ignore_index=True),202412,12)
        for month in months:self.assertAlmostEqual(p[donors.date.eq(month)].sum(),1/12)


class DatedPromptTests(unittest.TestCase):
    def obs(self):
        s=[dict(signal_id='x',measure='CPI annual',value=2.7,unit='percent',reference_period='2025-11',
                published_at='2025-12-18T08:30:00-05:00',source_version='R1',eligibility='eligible'),
           dict(signal_id='y',measure='CPI monthly',value=.3,unit='percent',reference_period='2025-09',
                published_at='2025-10-24T08:30:00-04:00',source_version='R2',eligibility='eligible'),
           dict(signal_id='z',measure='Unemployment',value=4.3,unit='percent',reference_period='2025-08',
                published_at='2025-09-05T08:30:00-04:00',source_version='R3',role='history',eligibility='eligible')]
        return SimpleNamespace(local_physical={'profile':{'age_group':'Over 60'},'prior_answer':{'point_pct':999}},
                               macro_information={'target_month':'2026-01','as_of':'2025-12-31T23:59:59-05:00','signals':s,'events':[]})

    def test_separate_dates_and_same_questionnaire(self):
        ob=self.obs();before=build_sce_messages_v2(ob)
        new=build_dated_messages(ob,build_sce_messages_v2)[0]['content']
        self.assertIn('CPI annual [percent]; 2025-11: 2.7',new)
        self.assertIn('CPI monthly [percent]; 2025-09: 0.3',new)
        self.assertIn('Unemployment [percent]: 2025-08: 4.3',new)
        self.assertNotIn('999',new);self.assertNotIn('past 12 monthly releases',new)
        self.assertEqual(new.split('Question 1 (point estimate):')[1],before[0]['content'].split('Question 1 (point estimate):')[1])

    def test_future_report_and_news_rejected(self):
        ob=self.obs();ob.macro_information['signals'][0]['published_at']='2026-01-02T08:30:00-05:00'
        with self.assertRaises(ValueError):build_dated_messages(ob,build_sce_messages_v2)
        ob=self.obs();ob.macro_information['events']=[{'pub_date':'2026-01-02T08:30:00-05:00','headline':'later news'}]
        with self.assertRaises(ValueError):build_dated_messages(ob,build_sce_messages_v2)

    def test_day_only_news_keeps_unverified_status(self):
        ob=self.obs();event={'pub_date':'2025-12-30','headline':'day only','text_vintage_status':'unverified_archive_snapshot'}
        ob.macro_information['events']=[event]
        self.assertIn('publication day only; archived text vintage unverified',build_dated_messages(ob,build_sce_messages_v2)[0]['content'])
        del event['text_vintage_status']
        with self.assertRaises(ValueError):build_dated_messages(ob,build_sce_messages_v2)

    def test_real_draft_all_13_months_render_offline(self):
        root=Path(__file__).resolve().parents[1]
        path=root/'outputs/sce_e_B_through_2026_10_draft_v2_20261007/environment_B_bls_only_draft.json'
        if not path.exists():self.skipTest('local draft not distributed in Git')
        bundle=EnvironmentBundle.model_validate(json.loads(path.read_text()))
        env=SCEEnvironmentProvider(bundle);env.reset(42)
        for t in range(1,14):
            env.advance_to(t);ob=env.observe_batch(['offline_preview'],t)[0]
            text=build_dated_messages(ob,build_sce_messages_v2)[0]['content']
            for s in ob.macro_information['signals']:self.assertIn(s['reference_period'],text)

if __name__=='__main__':unittest.main()
