"""Isolated prior-role wording contrast; existing facts and prior are unchanged."""
from socioverse.engine import register
from .model import SCEDecision
from .expanded_state_runtime import build_messages as original_messages
from .behavior_prompt_blocks import ANCHOR_BLOCK, insert_block
from .prior_belief_experiment import message_hash

REF='sce_inflation_expectations.anchor_role_decision'
PROMPT='sce-q8-q9-anchor-role-v1'
ARMS=('original','belief_start')


def build_messages(ob,bundle):
    if bundle['arm'] not in ARMS:raise ValueError('unknown prior-role arm')
    messages=original_messages(ob,bundle['base'])
    if bundle['arm']=='belief_start':messages=insert_block(messages,ANCHOR_BLOCK,require_prior=True)
    if message_hash(messages)!=bundle['messages_sha256'][ob.agent_id]:raise ValueError('frozen message changed')
    return messages


@register('decision',REF)
class AnchorRoleDecision(SCEDecision):
    def __init__(self,**args):
        if args.get('prompt_version')!=PROMPT:raise ValueError('provider/prompt mismatch')
        self.bundle=args['anchor_role_bundle']
        super().__init__(**args)

    def build_llm_messages(self,ob):return build_messages(ob,self.bundle)

    def _decide_scripted(self,obs):
        for ob in obs:self.build_llm_messages(ob)
        return super()._decide_scripted(obs)

    def _decide_openai_one(self,ob):
        action=super()._decide_openai_one(ob)
        action.payload.update(anchor_role_arm=self.bundle['arm'],research_line='A_conditional_returner_reconstruction',
                              actual_messages_sha256=self.bundle['messages_sha256'][ob.agent_id])
        return action
