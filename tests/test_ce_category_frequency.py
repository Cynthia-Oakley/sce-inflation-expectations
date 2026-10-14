import unittest

from studies.sce_inflation_expectations.category_frequency import category_days


def expense(ucc,day,cost='10',flag='2',dayflag='D'):
    return {'UCC':ucc,'EXPNSQDY':str(day),'EXPN_QDY':dayflag,'COST':cost,'PUB_FLAG':flag}


class CategoryFrequencyTest(unittest.TestCase):
    def test_same_day_is_one_contact_day_and_categories_can_overlap(self):
        mapping={'010110':'food_at_home','330110':'household_supplies_services'}
        rows=[expense('010110',1),expense('010110',1),expense('330110',1)]
        result=category_days(rows,mapping,set(mapping))
        self.assertEqual(result['food_at_home']['recorded_days_7d'],1)
        self.assertEqual(result['household_supplies_services']['recorded_days_7d'],1)
        self.assertEqual(result['food_at_home']['record_counts']['positive_published_rows'],2)

    def test_missing_days_and_missing_records_are_not_precise_zero(self):
        mapping={'010110':'food_at_home'}
        result=category_days([expense('010110',1),expense('010110','',dayflag='B')],mapping,set(mapping))
        self.assertIsNone(result['food_at_home']['recorded_days_7d'])
        self.assertEqual(result['food_at_home']['observed_valid_days_lower_bound'],1)
        self.assertIsNone(category_days([],mapping,set(mapping))['food_at_home']['recorded_days_7d'])

    def test_excluded_and_unknown_publication_flags_are_separate(self):
        mapping={'010110':'food_at_home'}
        excluded=category_days([expense('010110',1,flag='1')],mapping,set(mapping))
        self.assertEqual(excluded['food_at_home']['recorded_days_7d'],0)
        self.assertEqual(excluded['food_at_home']['status'],'no_positive_published_records')
        unknown=category_days([expense('010110',1,flag='9')],mapping,set(mapping))
        self.assertIsNone(unknown['food_at_home']['recorded_days_7d'])


if __name__=='__main__':unittest.main()
