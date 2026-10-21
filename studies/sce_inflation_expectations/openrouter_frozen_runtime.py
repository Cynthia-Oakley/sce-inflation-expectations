"""Provider lock and audit for the existing SocioVerse2 frozen-prompt runner."""
import math
import os
import httpx
import json
from pathlib import Path
from socioverse.engine import register
from .frozen_prompt_runtime import FrozenPromptDecision
from .model import SCEOpenAILLM
from .model_counterfactual import preflight
from .experiments.model_migration import validate_transport, MODEL, ROUTE

REF='sce_inflation_expectations.openrouter_frozen_decision'


def configure_live(protocol,dotenv):
    validate_transport(protocol)
    from .news_label_trial import dotenv_values
    values=dotenv_values(dotenv)
    key=os.environ.get('OPENROUTER_API_KEY') or values.get('OPENROUTER_API_KEY')
    if not key:raise ValueError('OpenRouter credential missing')
    url='https://openrouter.ai/api/v1/models/'+protocol['model']+'/endpoints'
    if protocol.get('provider_metadata_mode') == 'frozen_batch_catalog':
        root = Path(__file__).resolve().parents[2]
        path = (root/protocol['provider_metadata']).resolve()
        if not path.is_relative_to(root/'data/raw/mcp_checks'):
            raise ValueError('Pinned local provider catalog required')
        directory = json.loads(path.read_text())
    else:
        with httpx.Client(timeout=20,follow_redirects=False) as client:
            reply=client.get(url);reply.raise_for_status();directory=reply.json()
    preflight({'route_candidate':protocol['route'],'input_price_per_million':protocol['price_input_per_mtok'],
               'output_price_per_million':protocol['price_output_per_mtok']},directory)
    # Only the isolated worker changes its runtime environment; no .env edits.
    os.environ['SV_LLM_BASE_URL']=protocol['destination'];os.environ['SV_LLM_API_KEY']=key
    return directory


class ProviderAuditLLM(SCEOpenAILLM):
    def chat(self,messages):
        self.last_provider_evidence={}
        response,latency=super().chat(messages)
        usage=getattr(response,'usage',None)
        self.last_provider_evidence={'returned_provider':getattr(response,'provider',None),
            'api_reported_cost_usd':getattr(usage,'cost',None)}
        return response,latency


@register('decision',REF)
class OpenRouterFrozenDecision(FrozenPromptDecision):
    def __init__(self,**args):
        super().__init__(**args)
        self.expected_provider=args.get('expected_provider',
            'AtlasCloud' if self.model=='deepseek/deepseek-v3.2' else 'DeepInfra')
        self.api_reported_cost_total=0.;self.api_reported_cost_calls=0
        if self.llm_kind=='openai':
            self.llm=ProviderAuditLLM(model=self.model,temperature=self.temperature,max_tokens=self.max_tokens,
                extra_body=self.extra_body,response_format=self.response_format,timeout_s=self.timeout_s)

    def _audit_llm_call(self,row):
        if not row['error']:
            evidence=getattr(self.llm,'last_provider_evidence',{})
            row.update(evidence)
            fee=evidence.get('api_reported_cost_usd')
            expected_model = self.model if self.model == 'deepseek/deepseek-v3.2' else MODEL
            expected_provider = self.expected_provider
            if row.get('returned_provider')!=expected_provider or row.get('returned_model')!=expected_model:
                row['error']='Locked OpenRouter model/provider identity mismatch'
            if fee is not None:
                if type(fee) not in (int,float) or not math.isfinite(fee) or fee<0:
                    row['error']='Invalid OpenRouter reported cost'
                else:
                    self.api_reported_cost_total+=fee;self.api_reported_cost_calls+=1
                    if fee>self._request_cost_bound(row['prompt_text'])+1e-9:
                        row['error']='Reported cost exceeds frozen request reservation'
        super()._audit_llm_call(row)

    def cost_summary(self):
        return {**super().cost_summary(),'api_reported_cost_usd':self.api_reported_cost_total,
                'api_reported_cost_calls':self.api_reported_cost_calls}
