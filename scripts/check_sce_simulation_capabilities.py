"""Fresh simulation MCP metadata only; no personas, questionnaires or paid tools."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from check_mcp_free_capabilities import McpHttpClient,gen_mcp_json,redact

ROOT=Path(__file__).resolve().parents[1]


def run(out):
    if out.exists():raise ValueError('Fresh metadata evidence directory required')
    env=gen_mcp_json.load_env();name='user_pool_survey_mcp';url_var,key_var=gen_mcp_json.SERVICES[name]
    if not env.get(url_var) or not env.get(key_var):raise ValueError('Configured service credentials required')
    client=McpHttpClient(env[url_var],env[key_var]);init=client.initialize();tools=client.list_tools()
    allowed='get_user_pool_simulation_capabilities'
    if allowed not in {t['name'] for t in tools}:raise ValueError('Free capabilities tool not advertised')
    capability=client.call_tool(allowed,{})
    out.mkdir(parents=True)
    record={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'initialize':redact(init),
       'tools':redact(tools),'capability':redact(capability),
       'operations':['initialize','tools/list',allowed],'paid_calls':0,'personal_data_sent':False}
    (out/'evidence.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    question=next((t for t in tools if t['name']=='run_user_pool_distribution_simulation'),{})
    fields=(question.get('inputSchema') or {}).get('properties') or {}
    print(json.dumps({'server_info':init.get('serverInfo'),'simulation_top_level_fields':sorted(fields),
                     'capability_top_level_keys':list(capability),'output':str(out),'paid_calls':0},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path)
    run(p.parse_args().out)
