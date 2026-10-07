#!/usr/bin/env python3
"""Render actual EnvironmentProvider observations offline; never invokes B/API."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from socioverse.schemas import EnvironmentBundle
from studies.sce_inflation_expectations.model import SCEEnvironmentProvider,build_sce_messages_v2
from studies.sce_inflation_expectations.dated_prompt import build_dated_messages,PROMPT_VERSION


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--environment',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    bundle=EnvironmentBundle.model_validate(json.loads(args.environment.read_text()))
    env=SCEEnvironmentProvider(bundle);env.reset(42);rows=[]
    for t in range(1,len(env.targets)+1):
        env.advance_to(t);ob=env.observe_batch(['offline_anonymous_preview'],t)[0]
        messages=build_dated_messages(ob,build_sce_messages_v2);text=json.dumps(messages,ensure_ascii=False,indent=2)+'\n'
        target=ob.macro_information['target_month'];path=args.out/f'prompt_{target}.json';path.write_text(text)
        refs=sorted({s['reference_period'] for s in ob.macro_information['signals']})
        rows.append({'target_month':target,'as_of':ob.macro_information['as_of'],'supplied_signal_count':len(ob.macro_information['signals']),
                     'reference_periods':refs,'prompt_chars':len(text),'prompt_sha256':hashlib.sha256(text.encode()).hexdigest()})
    result={'environment_file':str(args.environment),'environment_sha256':hashlib.sha256(args.environment.read_bytes()).hexdigest(),
            'prompt_version':PROMPT_VERSION,'months':rows,'status':'offline actual E-provider rendering; no historical P joined',
            'real_llm_calls':0,'simulation_config_modified':False}
    (args.out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'months':len(rows),'max_prompt_chars':max(r['prompt_chars'] for r in rows),'real_llm_calls':0}))

if __name__=='__main__':main()
