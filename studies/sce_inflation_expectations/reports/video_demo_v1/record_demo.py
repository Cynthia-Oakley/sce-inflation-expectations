"""Offline recording demonstration in a fresh extracted copy, never in original package."""
from pathlib import Path
import argparse,datetime,hashlib,json,subprocess,sys,time,zipfile,html
ROOT=Path(__file__).resolve().parents[4]
ARCHIVE=ROOT/'deliverables/research_package/v05/SCE_research_package_draft_v05.zip'
EXPECTED='28f0866dea240c834f5d50a66b569536e2d5dfb4972bcd82fce597fd9d41804f'
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path);args=p.parse_args()
 stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
 dest=(args.out or ROOT/'tmp/video_demo_v1/recording_sessions'/stamp).resolve();dest.mkdir(parents=True,exist_ok=False)
 print('SCE 研究包离线演示',flush=True)
 print('范围：20户工程示例 + 已封存全国结果复算',flush=True)
 print('本次模型API调用：0，费用：$0',flush=True)
 assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()==EXPECTED,'研究包版本发生变化，请先更新演示核对'
 with zipfile.ZipFile(ARCHIVE) as z:
  for info in z.infolist():
   target=(dest/'package'/info.filename).resolve()
   if not target.is_relative_to(dest/'package'):raise ValueError('Unsafe archive member')
  z.extractall(dest/'package')
 roots=list((dest/'package').rglob('PACKAGE_MANIFEST.json'));assert len(roots)==1
 package=roots[0].parent; out=dest/'results';started=time.monotonic()
 command=[sys.executable,str(package/'studies/sce_inflation_expectations/run.py'),'--mode','all','--out',str(out)]
 print('正在核对研究包并运行官方Core工程示例……',flush=True)
 result=subprocess.run(command,cwd=package,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 (dest/'execution.log').write_text(result.stdout)
 if result.returncode:
  print(result.stdout[-4000:]);raise SystemExit(result.returncode)
 receipt=json.loads((out/'receipt.json').read_text());assert receipt['actual_LLM_calls']==0
 dr=receipt['dry_run'];assert dr['agents']==20 and dr['steps']==2
 print(f"工程示例：{dr['agents']}户、{dr['steps']}步，{dr['scripted_decisions']}次规则决策完成",flush=True)
 print('全国结果：历史、近期、统计扩展、月度、周度及下游复算通过',flush=True)
 print(f'完成，用时 {time.monotonic()-started:.1f} 秒',flush=True)
 print('结果页面：'+str(out/'index.html'),flush=True)
 print('执行收据：'+str(out/'receipt.json'),flush=True)
 print('本次为离线复算，不重新生成正式模型答卷',flush=True)
 (dest/'demo_receipt.json').write_text(json.dumps({'status':'passed','package_sha256':EXPECTED,'source_package_modified':False,'recording_output':str(out),'actual_LLM_calls':0,'command':command,'seconds':time.monotonic()-started},ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
