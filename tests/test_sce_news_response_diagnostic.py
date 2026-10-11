import math
import unittest
from studies.sce_inflation_expectations.news_response_diagnostic import valid_bins, bin_stats
from studies.sce_inflation_expectations.persistence_probe_preparation import common_correction, with_prior, PRIORS


class ResponseDiagnosticTests(unittest.TestCase):
    def test_sparse_real_probability_allowed(self):
        bins=[0,0,0,100,0,0,0,0,0,0]
        self.assertTrue(valid_bins(bins))
        s=bin_stats([bins,[10]*10])
        self.assertEqual(s['zero_deflation_mass_count'],1)
        self.assertEqual(s['deflation_probability_percent']['median'],25)
        self.assertEqual(s['positive_bin_count']['median'],5.5)

    def test_invalid_probability_not_zero_filled(self):
        for bins in ([None]+[0]*9,[math.nan]+[0]*9,[0]*10,[100]*10,[True]+[11]*9):
            self.assertFalse(valid_bins(bins))
        self.assertEqual(bin_stats([[None]*10])['n_valid'],0)

    def test_negative_mass_follows_ordered_bins(self):
        self.assertEqual(bin_stats([[0,0,0,0,20,80,0,0,0,0]])['deflation_probability_percent']['median'],80)

    def test_prior_only_adds_one_inspectable_block(self):
        old=[{'role':'user','content':'Household\nRecent official statistics:\nrent and shelter +2.1%\nGeneral news you encountered:\nOriginal news\nQuestion 1 (point estimate): original questions'}]
        base=common_correction(old)
        for arm,prior in PRIORS.items():
            made=with_prior(base,arm)
            self.assertEqual(made[0]['content'].replace(prior+'\n\n','',1),base[0]['content'])
            self.assertEqual(made[0]['content'].split('General news')[1],old[0]['content'].split('General news')[1])
        self.assertIn('rent and shelter',old[0]['content'])
        self.assertEqual(with_prior(base,'unassigned'),base)

    def test_no_numeric_forecast_or_population_prevalence_in_prior(self):
        for text in PRIORS.values():
            self.assertFalse(any(c.isdigit() for c in text))
            self.assertIn('not a known future outcome',text)
        with self.assertRaises(ValueError):
            with_prior([{'role':'user','content':'missing marker'}],'easing_prior')


if __name__=='__main__':
    unittest.main()
