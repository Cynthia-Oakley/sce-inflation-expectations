import copy
import unittest

from scripts.split_sce_basket_population import split_roles
from studies.sce_inflation_expectations.price_experience import profile_hash


class BasketRoleSplitTest(unittest.TestCase):
    def setUp(self):
        self.full = {'study_id':'sce_inflation_expectations',
                     'provider_ref':'sce_inflation_expectations.population',
                     'provider_args':{'target_month':202105,'sampling_design':'census'},
                     'materialized_count':3,
                     'personas':[{'agent_id':f'p{i}','attributes':{'age_group':'Under 40'},'weight':1.0} for i in range(3)]}
        self.core=copy.deepcopy(self.full)
        self.core['personas']=self.core['personas'][:1]
        self.core['materialized_count']=1
        self.exp={'research_line':'A_historical_reconstruction','target_month':'2021-05',
                  'experience_by_id':{p['agent_id']:{'agent_id':p['agent_id'],
                      'profile_sha256':profile_hash(p['attributes']),
                      'spending_shares':{'food':.2,'gasoline':.05,'shelter':.3,'other':.45}}
                                      for p in self.full['personas']}}

    def test_roles_partition_without_redrawing_or_mutating(self):
        before=copy.deepcopy((self.full,self.core,self.exp))
        split=split_roles(self.full,self.core,self.exp)
        self.assertEqual(set(split['core'][1]['experience_by_id']),{'p0'})
        self.assertEqual(set(split['normal'][1]['experience_by_id']),{'p1','p2'})
        self.assertEqual(split['normal'][1]['experience_by_id']['p2'],self.exp['experience_by_id']['p2'])
        self.assertEqual((self.full,self.core,self.exp),before)

    def test_wrong_person_or_month_rejected(self):
        self.core['personas'][0]['attributes']['age_group']='Over 60'
        with self.assertRaisesRegex(ValueError,'Core persona'):
            split_roles(self.full,self.core,self.exp)
        self.core=copy.deepcopy(self.full)
        self.core['personas']=self.core['personas'][:1]
        self.core['materialized_count']=1
        self.core['provider_args']['target_month']=202106
        with self.assertRaisesRegex(ValueError,'months'):
            split_roles(self.full,self.core,self.exp)

    def test_missing_or_wrong_basket_rejected(self):
        self.exp['experience_by_id']['p0']['profile_sha256']='invalid'
        with self.assertRaisesRegex(ValueError,'profile'):
            split_roles(self.full,self.core,self.exp)


if __name__=='__main__':
    unittest.main()
