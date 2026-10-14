import unittest

from studies.sce_inflation_expectations.behavior_prompt_blocks import ANCHOR_BLOCK, frequency_block, insert_block, LABELS
from studies.sce_inflation_expectations.prior_belief_preparation import MARKER, PRIOR_MARKER


class BehaviorBlockTest(unittest.TestCase):
    def test_added_instruction_keeps_prior_and_questionnaire_exactly(self):
        before='P/E facts\n'+PRIOR_MARKER+'\nraw prior bins\n'
        after='next 12 months, bins and output contract'
        original=[{'role':'user','content':before+MARKER+after}]
        changed=insert_block(original,ANCHOR_BLOCK,require_prior=True)
        self.assertEqual(changed[0]['content'].replace(ANCHOR_BLOCK,''),original[0]['content'])
        self.assertEqual(changed[0]['content'].split(MARKER)[1],after)
        with self.assertRaises(ValueError):insert_block([{'role':'user','content':MARKER+after}],ANCHOR_BLOCK,require_prior=True)
        with self.assertRaises(ValueError):insert_block([{'role':'user','content':MARKER+after}],ANCHOR_BLOCK)

    def test_partial_proxy_is_rejected_and_zero_is_not_dropped(self):
        data={key:{'status':'available','recorded_days_7d':int(i==0)*2} for i,key in enumerate(LABELS)}
        text=frequency_block(data)
        self.assertIn('0 of 7 days',text)
        self.assertIn('more attention and more influence',text)
        data['food_at_home']['status']='partial_support'
        with self.assertRaises(ValueError):frequency_block(data)


if __name__=='__main__':unittest.main()
