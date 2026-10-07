import unittest
import numpy as np
from studies.sce_inflation_expectations.macro_population import forecast,reconstruct,logratios,employment_shares,month_shift
from scripts.check_sce_macro_population import build_rows,UE,PAY


class MacroPopulationTests(unittest.TestCase):
    def test_composition_and_months(self):
        self.assertEqual(month_shift(202001,-10),201903)
        p=employment_shares({'employed':.6,'unemployed':.05,'retired':.2})
        np.testing.assert_allclose(p,[.6,.05,.35])
        np.testing.assert_allclose(reconstruct(p,[0.,0.]),p)
        self.assertTrue((reconstruct(p,[1000.,-1000.])>=0).all())
        self.assertAlmostEqual(reconstruct(p,[1000.,-1000.]).sum(),1.)
        with self.assertRaises(ValueError):employment_shares({'employed':.8,'unemployed':.3})

    def test_future_labels_and_target_truth_do_not_change_prediction(self):
        base=[.6,.05,.35];rows=[]
        for month,x in [(202001,-2.),(202002,0.),(202003,2.)]:
            rows.append({'month':month,'features':[x,0.,0.],'base':base,'truth':reconstruct(base,[-.2*x,.1*x]).tolist()})
        test={'month':202101,'features':[1.,0.,0.],'base':base,'truth':[.1,.2,.7]}
        future={'month':202012,'features':[900.,900.,900.],'base':base,'truth':[.999,.0005,.0005]}
        p,a=forecast(rows+[future,test],test,label_cutoff=202003,method='unrate_ols',min_train=3)
        np.testing.assert_allclose(p,reconstruct(base,[-.2,.1]),rtol=1e-10)
        self.assertEqual(a['max_train_month'],202003)
        test['truth']=[.9,.05,.05];future['truth']=[.2,.5,.3]
        p2,_=forecast(rows+[future,test],test,label_cutoff=202003,method='unrate_ols',min_train=3)
        np.testing.assert_allclose(p,p2)
        with self.assertRaises(ValueError):forecast(rows,test,label_cutoff=202101,min_train=3)

    def test_ridge_and_missing_training(self):
        rows=[{'month':202001+i,'features':[i,i%2,2*i],'base':[.6,.05,.35],'truth':[.58,.06,.36]} for i in range(3)]
        test={'month':202101,'features':[1.,0.,2.],'base':[.6,.05,.35]}
        p,a=forecast(rows,test,label_cutoff=202003,min_train=3)
        self.assertAlmostEqual(p.sum(),1.);self.assertEqual(a['ridge_alpha'],1.)
        with self.assertRaises(ValueError):forecast(rows,test,label_cutoff=202003)

    def test_future_macro_release_excluded_from_features(self):
        months=[month_shift(201903,-i) for i in range(12)]+[202001]
        population=[{'month':m,'margins':{'employment_status':{'weighted':{'employed':.6,'unemployed':.05}}}} for m in months]
        macro=[]
        for measure,refs in [(UE,[201903,201908,201911]),(PAY,[201901,201902,201903,201909,201910,201911])]:
            for m in refs:
                macro.append({'measure':measure,'month':m,'value':5. if measure==UE else 200.,'published_at':'2019-12-02T08:30:00-05:00'})
        future={'measure':UE,'month':201912,'value':999.,'published_at':'2020-01-03T08:30:00-05:00'}
        rows=build_rows(population,macro+[future])
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['latest_unrate_month'],201911)
        np.testing.assert_allclose(rows[0]['features'],[0.,0.,0.])

if __name__=='__main__':unittest.main()
