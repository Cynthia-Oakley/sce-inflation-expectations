"""One real, archived questionnaire call for a Terminal recording. Preview is offline."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
import os
import sys
import time
from contextlib import contextmanager

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.q9_normalization import response_view

DEFAULT=ROOT/'deliverables/video/terminal_live_v01'
MODEL='deepseek/deepseek-v3.2'
URL='https://openrouter.ai/api/v1'
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
message_hash=lambda m:hashlib.sha256(json.dumps(m,ensure_ascii=False).encode()).hexdigest()


def dump(p,x):
    Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def safe(s):
    return ''.join(c for c in str(s) if c in '\n\t' or (ord(c)>=32 and ord(c)!=127))


def say(s=''):
    print(safe(s),flush=True)


def prepare(out):
    """Freeze one existing input, with no previous simulated reply or target truth."""
    samples=ROOT/'tmp/video_samples_v02/data.json'
    lineage=ROOT/'tmp/video_samples_v02/private_lineage.json'
    source_protocol=ROOT/'outputs/sce_full_a_t0_terminal_20261025_v1/protocol.json'
    sample=next(s for s in read(samples)['samples'] if s['id']=='A01')
    link=next(s for s in read(lineage) if s['demo_id']=='A01')
    prompt_file=ROOT/link['prompt_file']
    original=read(prompt_file)['rows'][link['agent_id']]
    if original['messages']!=sample['messages'] or message_hash(original['messages'])!=sample['prompt_hash']:
        raise ValueError('Original prompt differs from recorded example')
    p=read(source_protocol)
    if p['model']!=MODEL or p['destination']!=URL or p['route']!='siliconflow/fp8':
        raise ValueError('Only the established route is accepted')
    extras=p['request_extra_body']
    prices=extras['provider']['max_price']
    if extras['provider']['order']!=['siliconflow/fp8'] or extras['provider']['allow_fallbacks'] is not False:
        raise ValueError('Provider must be locked without fallback')
    reserve=((len(json.dumps(original['messages'],ensure_ascii=False).encode())+1024)*prices['prompt']+1024*prices['completion'])/1e6
    if reserve>.01:raise ValueError('Single-call reservation exceeds one cent')
    public_keys=['id','month','profile','cutoff','prior_q8','grocery_role','news_count',
                 'common_count','personal_count','news','food_lines','food_reference',
                 'food_published','spending_block','prompt_hash']
    data={k:sample[k] for k in public_keys}
    data['messages']=original['messages']
    protocol=dict(schema='sce_terminal_live_demo/v1',model=MODEL,destination=URL,
        expected_provider='SiliconFlow',temperature=.5,max_tokens=1024,
        request_extra_body=extras,planned_calls=1,budget_cap_usd=.01,
        reserved_usd=reserve,automatic_retries=0,provider_fallback=False,
        streaming=True,new_research_experiment=False,
        input_sha256=hashlib.sha256(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False).encode()+b'\n').hexdigest())
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    (out/'.gitignore').write_text('*\n')
    dump(out/'input_private.json',data);dump(out/'protocol.json',protocol)
    dump(out/'source_hashes.json',{str(x.relative_to(ROOT)):sha(x) for x in [samples,lineage,prompt_file,source_protocol]})
    source=Path(__file__).resolve()
    python=sys.executable
    for name,mode in [('preview.command','preview'),('record_live.command','run')]:
        content='#!/bin/zsh\nset -euo pipefail\nexec '+ ' '.join("'"+x.replace("'","'\\''")+"'" for x in [python,str(source),mode,'--bundle',str(out)])+'\n'
        (out/name).write_text(content);(out/name).chmod(0o755)
    (out/'README.md').write_text('''# 一户真实模型终端演示

先运行preview.command，完全离线，只展示已准备的人口、新闻和问卷；不会显示旧答卷冒充新生成。

record_live.command可重复运行。已有调用时，回车或选1会整段回放最近一次完整真实答卷（0API）；选2则在展示准备过程后，再要求输入RUN确认本次1个新请求、$0.01上限。只有确认后才读取本机OpenRouter密钥并流式请求DeepSeek V3.2（固定SiliconFlow FP8、温度0.5、关闭思考）。不自动重试、不换供应商、不修改原研究。

准备阶段读取已封存的资料，现场不重新抓取新闻或重新抽样。模型阶段是真实API分块返回，不是打字动画。完整Prompt、流式事件、回答、格式检查及费用分别保留：最初调用在execution/，后续手动新调用在executions/take_时间/。每次只尝试一次，失败和未知在途不自动重发；重录无需删除旧记录。

replay子命令也能整段重放最近一次完整调用，画面标明“存档回放、0API”，播放节奏不代表接口原始耗时。不得将单户演示并入论文正式统计。用户录制的mp4仍放recordings/clips/page_07.mp4。
''')
    dump(out/'manifest.json',{'protocol_sha256':sha(out/'protocol.json'),
        'input_sha256':sha(out/'input_private.json'),'runner_sha256':sha(source)})
    say(f'已准备：{out}');say(f'离线预览：{out/"preview.command"}')
    say(f'真实录制：{out/"record_live.command"}（需Terminal确认，不会在准备时调用）')
    say(f'1次请求；保守预留 ${reserve:.6f}；本批上限 $0.01；新增调用0。')
    return protocol


def validate_visibility(d):
    cutoff=datetime.fromisoformat(d['cutoff'].replace('Z','+00:00'))
    if len(d['news'])!=d['news_count'] or d['common_count']+d['personal_count']!=d['news_count']:
        raise ValueError('News count differs from the frozen exposure')
    for item in d['news']:
        if datetime.fromisoformat(item['published_at'].replace('Z','+00:00'))>cutoff:
            raise ValueError('News after cutoff')
        if item['headline'] not in d['messages'][0]['content']:raise ValueError('Displayed news is not in actual prompt')
    if datetime.fromisoformat(d['food_published'].replace('Z','+00:00'))>cutoff:
        raise ValueError('Food release after cutoff')


def load(bundle):
    manifest=read(bundle/'manifest.json')
    if (sha(bundle/'protocol.json')!=manifest['protocol_sha256']
        or sha(bundle/'input_private.json')!=manifest['input_sha256']):raise ValueError('Prepared input changed')
    if sha(Path(__file__))!=manifest['runner_sha256']:
        # A reviewed display/execution addendum, preserving the original manifest.
        upgrade=read(bundle/'repeat_recording_policy.json')
        if (upgrade['parent_manifest_sha256']!=sha(bundle/'manifest.json')
            or upgrade['parent_protocol_sha256']!=sha(bundle/'protocol.json')
            or upgrade['runner_sha256']!=sha(Path(__file__))
            or upgrade['live_calls_per_manual_take']!=1
            or upgrade['budget_per_manual_take_usd']!=.01
            or upgrade['automatic_retries']!=0):raise ValueError('Unreviewed recording addendum')
    p=read(bundle/'protocol.json')
    if p['model']!=MODEL or p['destination']!=URL or p['planned_calls']!=1 or p['budget_cap_usd']!=.01:
        raise ValueError('Frozen scope changed')
    if sha(bundle/'input_private.json')!=p['input_sha256']:
        raise ValueError('Frozen input changed')
    d=read(bundle/'input_private.json')
    if message_hash(d['messages'])!=d['prompt_hash']:raise ValueError('Prompt hash mismatch')
    validate_visibility(d)
    if (p['request_extra_body']['provider']['order']!=['siliconflow/fp8']
        or p['request_extra_body']['provider']['allow_fallbacks'] is not False
        or p['request_extra_body']['reasoning']!={'enabled':False}
        or p['request_extra_body']['provider']['max_price']!={'prompt':.259,'completion':.8}
        or p['max_tokens']!=1024 or p['temperature']!=.5):raise ValueError('Locked generation settings changed')
    bound=((len(json.dumps(d['messages'],ensure_ascii=False).encode())+1024)*.259+1024*.8)/1e6
    if not math.isclose(bound,p['reserved_usd']) or bound>p['budget_cap_usd']:
        raise ValueError('Invalid reservation')
    return p,d


def stage(title,pause):
    if pause and sys.stdin.isatty():input('\n按回车继续展示…')
    say('\n'+'━'*38);say(title);say('━'*38)


def show_input(p,d,pause):
    say('SCE 家庭通胀预期｜一户真实模拟演示')
    say('输入准备：读取正式研究已封存资料；现场不重新采集新闻。')
    stage('1 / 4　读取家庭画像与既有信念',False)
    q=d['profile'];say(f'调查月：{d["month"][:4]}-{d["month"][4:]}　展示编号：{d["id"]}')
    say(f'年龄：{q["age"]}　学历：{q["education"]}　数理：{q["numeracy"]}')
    say(f'收入：{q["income"]}　就业：{q["employment"]}　住房：{q["housing"]}　地区：{q["region"]}')
    say(f'合成采购角色：{d["grocery_role"]}；本人前期Q8：{d["prior_q8"]:g}%')
    say('其他输入：合成消费支出与政策信心、本人更早Q8/Q9摘要。')
    say('来源：SCE家庭记录；CE支出、ATUS采购角色与Gallup信心的条件匹配。')
    stage('2 / 4　核对信息截止与匹配环境',pause)
    say(f'个人信息截止：{d["cutoff"]}')
    say(f'新闻：共同背景{d["common_count"]}篇＋个人匹配{d["personal_count"]}篇＝{d["news_count"]}篇')
    for n in d['news']:
        say(f'  [{n["date"]}] {n["headline"]}')
    say(f'食品价格：参考{d["food_reference"]}，公布于{d["food_published"]}')
    for line in d['food_lines']:say('  '+line)
    say('联储政策：使用截止前公开内容，完整原文一并进入模型。')
    stage('3 / 4　组装正式问卷输入',pause)
    say('提问摘要：')
    say('Q8：你认为未来12个月价格会上涨或下降多少百分比？')
    say('Q9：把概率分配给十个通胀／通缩区间，合计100%。')
    say('输入结构：家庭画像＋既有信念＋匹配环境＋问卷＋JSON结构要求')
    say(f'模型：DeepSeek V3.2；温度0.5；关闭思考；最多1024输出token')
    say(f'Prompt与正式运行相同：{d["prompt_hash"][:16]}…')


def consume(chunks,p,folder,emit=say):
    """Retain raw chunks even on mid-stream error; never infer missing metadata."""
    text=[];models=set();providers=set();usage=None;finish=None;request_id=None
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/'stream_private.jsonl').open('x') as f, (folder/'response_partial.txt').open('x') as partial:
        for item in chunks:
            obj=item.model_dump(mode='json') if hasattr(item,'model_dump') else item
            f.write(json.dumps(obj,ensure_ascii=False)+'\n');f.flush()
            if obj.get('error'):raise ValueError('UpstreamStreamError')
            if obj.get('model'):
                models.add(obj['model'])
                if obj['model']!=p['model']:raise ValueError('ReturnedModelMismatch')
            if obj.get('provider'):
                providers.add(obj['provider'])
                if obj['provider']!=p['expected_provider']:raise ValueError('ReturnedProviderMismatch')
            request_id=obj.get('id') or request_id
            if obj.get('usage'):usage=obj['usage']
            for choice in obj.get('choices',[]):
                delta=(choice.get('delta') or {}).get('content') or ''
                if delta:
                    text.append(delta);partial.write(delta);partial.flush();emit(safe(delta))
                finish=choice.get('finish_reason') or finish
    raw=''.join(text);(folder/'response_raw.txt').write_text(raw)
    view=response_view(raw)
    if finish!='stop':raise ValueError('IncompleteOrTruncatedResponse')
    cost=(usage or {}).get('cost')
    if cost is not None and (type(cost) not in (float,int) or not math.isfinite(cost) or cost<0 or cost>p['budget_cap_usd']):
        raise ValueError('ReportedCostOutsideBudget')
    result=dict(status='completed' if models and providers else 'completed_metadata_incomplete',
        actual_LLM_calls=1,returned_models=sorted(models),returned_providers=sorted(providers),
        finish_reason=finish,request_id=request_id,usage=usage,reported_cost_usd=cost,
        spent_or_reserved_usd=cost if cost is not None else p['reserved_usd'],
        q8=view['point'],q9=view,new_research_result=False,automatic_retries=0)
    dump(folder/'checked_answer.json',view)
    return result


def run_once(bundle,p,d,pause,folder=None):
    folder=folder or bundle/'execution'
    if folder.exists():
        raise FileExistsError('This recording already has an execution directory. Preserve it; do not resend automatically.')
    show_input(p,d,pause)
    stage('4 / 4　现场请求模型，接收真实流式回答',pause)
    say('本次仅1个请求，上限$0.01，无自动重试或供应商回退。')
    say('目的地：OpenRouter → SiliconFlow FP8；发送上述画像、历史信念、公开环境与派生截止日期。')
    if input('确认上述外发范围与预算，输入RUN开始；其他输入退出：').strip()!='RUN':
        say('未启动，API调用0。');return
    # One-attempt ownership, before reading credentials or performing any network request.
    from studies.sce_inflation_expectations.news_label_trial import dotenv_values
    key=os.environ.get('OPENROUTER_API_KEY') or dotenv_values(ROOT.parent/'socioverse2_repo/.env').get('OPENROUTER_API_KEY')
    if not key:raise ValueError('OpenRouter key unavailable; nothing sent')
    folder.mkdir(parents=True,exist_ok=False)
    from studies.sce_inflation_expectations.model import SCEOpenAILLM
    os.environ['SV_LLM_BASE_URL']=p['destination'];os.environ['SV_LLM_API_KEY']=key
    llm=SCEOpenAILLM(model=p['model'],temperature=p['temperature'],max_tokens=p['max_tokens'],
        extra_body=p['request_extra_body'],response_format='json_object',timeout_s=120)
    dump(folder/'request_private.json',{'messages':d['messages'],'protocol':p})
    # Exclusive intent is durable before dispatch, including unknown-outcome failures.
    with (folder/'intent.json').open('x') as f:
        json.dump(dict(at_utc=datetime.now(timezone.utc).isoformat(),protocol_sha256=sha(bundle/'protocol.json'),
            prompt_sha256=d['prompt_hash'],reserved_usd=p['reserved_usd'],user_confirmation='RUN',
            recording_policy_sha256=sha(bundle/'repeat_recording_policy.json') if (bundle/'repeat_recording_policy.json').exists() else None,
            runner_sha256=sha(Path(__file__))),f)
        f.flush();os.fsync(f.fileno())
    started=time.monotonic();say('请求已开始，等待模型返回。下方内容均为本次API实际输出：')
    try:
        with llm._get_client().chat.completions.create(model=p['model'],messages=d['messages'],
            temperature=p['temperature'],max_tokens=p['max_tokens'],response_format={'type':'json_object'},
            extra_body=p['request_extra_body'],stream=True) as stream:
            result=consume(stream,p,folder,emit=lambda s:print(s,end='',flush=True))
        say('\n\n格式检查完成：Q8点预期 '+str(result['q8'])+'%；Q9十档齐备。')
        say('Q9原始概率合计：'+str(result['q9']['raw_sum'])+'%；比例归一化：'+str(result['q9']['applied']))
        if result['status']=='completed_metadata_incomplete':say('提示：服务端身份元数据未完整返回，收据已标记，需另核对。')
    except BaseException as exc:
        result=dict(status='stopped_data_preserved',actual_LLM_calls='one attempted; see intent',
            error_type=type(exc).__name__,http_status=getattr(exc,'status_code',None),
            spent_or_reserved_usd=p['reserved_usd'],automatic_retries=0)
        say('\n本次已停止，已接收内容保留，不自动再次请求。')
    result['seconds']=time.monotonic()-started;dump(folder/'receipt.json',result)
    say(f'回答与收据已存档：{folder}')
    if result.get('reported_cost_usd') is not None:say(f'本次报告费用：${result["reported_cost_usd"]:.6f}')
    if result['status']=='stopped_data_preserved':
        say('本次为停止记录，不记作成功答卷。');return result
    say('单户现场演示完成；不计算全国MAE，不改论文正式结果。')
    return result


def completed_takes(bundle):
    """Read-only discovery. Old execution/ and all new takes retain their bytes."""
    folders=[bundle/'execution']+sorted((bundle/'executions').glob('take_*'))
    found=[]
    for folder in folders:
        if not (folder/'receipt.json').exists():continue
        r=read(folder/'receipt.json')
        if r.get('status') not in ('completed','completed_metadata_incomplete'):continue
        if r.get('actual_LLM_calls')!=1 or not (folder/'response_raw.txt').exists():continue
        raw=(folder/'response_raw.txt').read_text()
        response_view(raw)
        # A replay cannot silently differ from the content archived in the stream.
        if (folder/'stream_private.jsonl').exists():
            chunks=[json.loads(line) for line in (folder/'stream_private.jsonl').read_text().splitlines() if line]
            content=''.join((c.get('delta') or {}).get('content') or '' for row in chunks for c in row.get('choices',[]))
            if content!=raw:raise ValueError('Archived stream/text mismatch')
        found.append(folder)
    return found


def playback(bundle,p,d,pause,folder=None,*,delay=.035):
    candidates=completed_takes(bundle)
    folder=folder or (candidates[-1] if candidates else None)
    if folder not in candidates:raise ValueError('No complete archived model answer available')
    say('【真实调用存档回放｜本次API调用0｜不产生费用】')
    say('本段重放已保存的输入与回复，不是再次现场调用。')
    show_input(p,d,pause)
    stage('4 / 4　真实答卷存档回放（0 API）',pause)
    say('按归档分块播放；阅读节奏不代表原始接口耗时。')
    stream=folder/'stream_private.jsonl'
    if stream.exists():
        for line in stream.open():
            row=json.loads(line)
            for choice in row.get('choices',[]):
                content=(choice.get('delta') or {}).get('content') or ''
                if content:
                    print(safe(content),end='',flush=True)
                    if delay:time.sleep(delay)
    else:say((folder/'response_raw.txt').read_text())
    r=read(folder/'receipt.json');q=response_view((folder/'response_raw.txt').read_text())
    say('\n\n原答卷格式检查：Q8 '+str(q['point'])+'%；Q9十档齐备。')
    say(f'原调用耗时：{r.get("seconds",0):.1f}秒；原调用费用：'+
        (f'${r["reported_cost_usd"]:.6f}' if r.get('reported_cost_usd') is not None else '未完整返回'))
    say('回答存档：'+str(folder))
    say('【回放结束｜本次新增API调用0】')
    return dict(status='archived_playback_complete',new_api_calls=0,source=str(folder))


@contextmanager
def live_lock(bundle):
    """Prevent simultaneous paid dispatches while keeping all old attempts."""
    import fcntl
    with (bundle/'.live_recording.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another live recording request is running')
        try:yield
        finally:fcntl.flock(lock,fcntl.LOCK_UN)


def run(bundle,p,d,pause):
    existing=(bundle/'execution').exists() or any((bundle/'executions').glob('take_*'))
    if existing:
        takes=completed_takes(bundle)
        say('SCE 录制入口｜可以重复运行，旧记录全部保留')
        say('1／直接回车：回放最近一次完整真实调用（0 API、0费用）')
        say('2：重新调用一次模型（新答卷，单次预算$0.01）')
        say('Q：退出')
        choice=input('请选择：').strip().lower() or '1'
        if choice=='1':
            if not takes:
                say('现有调用尚无完整答卷可回放；可重新打开菜单选择2，另行确认一次新调用。');return
            return playback(bundle,p,d,pause,takes[-1])
        if choice!='2':say('已退出；本次API调用0。');return
    # Every new take still requires RUN and its own one-request budget confirmation.
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    folder=bundle/'executions'/('take_'+stamp)
    with live_lock(bundle):return run_once(bundle,p,d,pause,folder)


def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('mode',choices=['prepare','preview','run','replay'])
    a.add_argument('--bundle',type=Path,default=DEFAULT);a.add_argument('--no-pause',action='store_true');args=a.parse_args()
    if args.mode=='prepare':prepare(args.bundle);return
    p,d=load(args.bundle)
    if args.mode=='preview':
        show_input(p,d,not args.no_pause);say('\n【离线预览结束】本次没有调用模型，也没有播放旧答案。')
    elif args.mode=='replay':
        playback(args.bundle,p,d,not args.no_pause)
    else:
        result=run(args.bundle,p,d,not args.no_pause)
        if result and result['status']=='stopped_data_preserved':raise SystemExit(1)


if __name__=='__main__':main()
