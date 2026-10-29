"""Create a local reading/Terminal companion for an independently verified ZIP.

This companion is outside the frozen package. It reads only the extracted
review data and verification receipts; it never imports a model client.
"""
import argparse
from datetime import datetime
import gzip
from html import escape
import json
from pathlib import Path
import shlex
import sys
from zoneinfo import ZoneInfo


STUDY = "studies/sce_inflation_expectations"


def _read(path):
    return json.loads(path.read_text())


def _tree(paths, docs, prefix=""):
    groups = {}
    for path in paths:
        head, _, rest = path.partition("/")
        groups.setdefault(head, []).append(rest)
    parts = ["<ul class='tree'>"]
    for head, tails in sorted(groups.items(), key=lambda x: (x[1] == [""], x[0])):
        full = prefix + head
        if tails != [""]:
            opened = " open" if full in ("studies", STUDY) else ""
            parts.append(f"<li><details{opened}><summary>{escape(head)}/ <small>{len(tails)} 文件</small></summary>"
                         + _tree(tails, docs, full + "/") + "</details></li>")
        elif full in docs:
            parts.append(f"<li><button data-doc='{escape(full, quote=True)}'>{escape(head)}</button></li>")
        else:
            parts.append(f"<li><a href='isolated_package/{escape(full, quote=True)}' target='_blank' rel='noopener'>{escape(head)}</a></li>")
    return "".join(parts) + "</ul>"


def build(preview, python=None):
    preview = Path(preview).resolve()
    proof = _read(preview / "acceptance.json")
    if proof.get("status") != "passed_independent_zip_offline_execution" or proof.get("new_API_calls") != 0:
        raise ValueError("A successful independent 0-API verification receipt is required")
    package = preview / "isolated_package"
    manifest = _read(package / "PACKAGE_MANIFEST.json")
    paths = sorted([*manifest["files_sha256"], "PACKAGE_MANIFEST.json"])
    test_log = (preview / "tests.log").read_text()
    import re
    test_match = re.search(r"(\d+) passed", test_log)
    if not test_match or int(test_match[1]) < 72:
        raise ValueError("Expected packaged verification tests are missing")
    important = ["README.md", "DIRECTORY_GUIDE.md", "REPRODUCIBILITY.md", "EXTERNAL_MODEL_AND_API.md",
                 "requirements.lock.txt", f"{STUDY}/README.md", f"{STUDY}/FILE_GUIDE.md",
                 f"{STUDY}/simulation/research_runs.json", f"{STUDY}/reports/PAPER_METRIC_GUIDE.md",
                 f"{STUDY}/reproduction_data/micro/MICRO_DATA_GUIDE.md"]
    portable = package / STUDY / "reproduction_data/portable/manifest.json"
    if portable.exists():
        important.append("PORTABLE_REPRODUCTION.md")
    inputs_manifest = package / STUDY / "reproduction_data/inputs/manifest.json"
    input_metadata = _read(inputs_manifest) if inputs_manifest.exists() else {}
    if inputs_manifest.exists():
        important.extend([f"{STUDY}/reproduction_data/inputs/README.md", f"{STUDY}/reproduction_data/inputs/NEWS_REVIEW_NOTICE.md"])
    docs = {name: (package / name).read_text() for name in important}
    data = package / STUDY / "reproduction_data/micro"
    with gzip.open(data / "effective_answers.jsonl.gz", "rt") as f:
        effective = json.loads(next(f))
    response_id = effective["selected_responses"]["q9"]
    raw = None
    with gzip.open(data / "model_outputs.jsonl.gz", "rt") as f:
        for line in f:
            row = json.loads(line)
            if row["response_id"] == response_id:
                raw = row
                break
    if raw is None:
        raise ValueError("Effective sample does not resolve to an archived response")
    text = raw["response_text"]  # Preserve the delivered, deidentified text.
    selected = {key: effective[key] for key in ("run", "period", "household", "q8", "q9_bins", "analysis_weight", "field_source")}
    sample = json.dumps(selected, ensure_ascii=False, indent=2)
    checked = datetime.fromisoformat(proof["checked_at_utc"]).astimezone(ZoneInfo("Asia/Shanghai"))
    version = preview.name
    # Resolving a venv's python symlink would silently select the base env.
    interpreter = Path(python or sys.executable).absolute()
    command = '''#!/bin/zsh
set -euo pipefail
SCE_PREVIEW_ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
SCE_REVIEW_PYTHON="${SCE_REVIEW_PYTHON:-DEFAULT_PYTHON}"
if [[ ! -x "$SCE_REVIEW_PYTHON" ]]; then
  print '本机预装Python环境不存在。请按研究包README安装依赖后运行默认命令。'
  exit 1
fi
SCE_REVIEW_TAG="$(date -u +%Y%m%dT%H%M%SZ)_$$"
SCE_REVIEW_OUT="$SCE_PREVIEW_ROOT/manual_results/run_$SCE_REVIEW_TAG"
mkdir -p "$SCE_PREVIEW_ROOT/manual_results"
cd "$SCE_PREVIEW_ROOT/isolated_package"
print '开始：工程示例 → 全国聚合复算 → 正式逐答卷复算'
print '本次不调用LLM、不使用API Key。请等待；完整复算可能需要几分钟。'
print "结果将写入：$SCE_REVIEW_OUT"
"$SCE_REVIEW_PYTHON" -I studies/sce_inflation_expectations/run.py --mode all --out "$SCE_REVIEW_OUT" 2>&1 | tee "$SCE_REVIEW_OUT.log"
print "复算成功。结果页面：$SCE_REVIEW_OUT/index.html"
open "$SCE_REVIEW_OUT/index.html"
if [[ -t 0 ]]; then read -r '?按回车关闭本终端窗口。'; fi
'''.replace("DEFAULT_PYTHON", str(interpreter))
    (preview / "运行复现.command").write_text(command)
    (preview / "运行复现.command").chmod(0o755)
    generic = "python3 -m venv .venv\nsource .venv/bin/activate\npython -m pip install -r requirements.lock.txt\npython studies/sce_inflation_expectations/run.py --mode all"
    run_command = shlex.quote(str(preview / "运行复现.command"))
    doc_options = "".join(f"<option value='{escape(k, quote=True)}'>{escape(k)}</option>" for k in docs)
    document_json = json.dumps(docs, ensure_ascii=False).replace("<", "\\u003c")
    page = """<!doctype html><html lang='zh-CN'><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>SCE研究包｜本机拆包与复现导览</title>
<style>
:root{--ink:#192a42;--accent:#185ba0;--sub:#536478;--line:#d8e0e8;--paper:#f5f7fa;--warm:#fff3d9}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.75 -apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}header{background:#192a42;color:white;padding:32px max(28px,calc((100vw - 1160px)/2));border-bottom:5px solid #dc9b29}
header small{color:#c7d6e5}h1{font-size:28px;line-height:1.4;margin:10px 0}h2{font-size:23px;margin:0 0 16px}h3{font-size:18px;margin:18px 0 8px}p{margin:10px 0}
.layout{display:grid;grid-template-columns:210px minmax(0,1fr);max-width:1220px;margin:auto;padding:24px;gap:28px}nav{position:sticky;top:18px;align-self:start}nav a{display:block;padding:9px 12px;color:var(--ink)}nav a:hover{background:white}
section{background:white;border:1px solid var(--line);padding:26px;margin:0 0 22px;border-radius:10px;scroll-margin-top:16px}.lead{font-size:18px}.note{padding:14px 18px;background:var(--warm);border-left:4px solid #b87c12}.muted,small{color:var(--sub)}
.row{display:grid;grid-template-columns:1fr 1fr;gap:18px}.box{background:#f5f7fa;padding:18px;border-radius:7px}.path{font-family:ui-monospace,monospace;word-break:break-all}
.route{display:flex;align-items:center;flex-wrap:wrap;gap:12px;font-size:19px;margin:22px 0}.route strong{padding:14px 20px;background:#eef3f8;border:1px solid var(--line);border-radius:7px}
.button{display:inline-block;padding:10px 18px;background:var(--accent);color:white;border-radius:6px;margin:8px 10px 8px 0}.button:hover{color:white;text-decoration:none;background:#144a82}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.65 ui-monospace,SFMono-Regular,monospace;background:#f2f5f8;border:1px solid var(--line);padding:16px;border-radius:6px;margin:12px 0}code{font-family:ui-monospace,monospace;background:#eef3f8;padding:1px 4px}
select{max-width:100%;padding:10px;font:14px sans-serif;border:1px solid var(--line);border-radius:5px}.file-view{max-height:520px;overflow:auto}details{margin:7px 0}summary{cursor:pointer}ul{padding-left:24px}.tree{list-style:none;padding-left:18px;font:13px/1.7 ui-monospace,monospace}.tree li{margin:3px 0}.tree button{padding:0;border:0;background:none;color:var(--accent);font:inherit;cursor:pointer;text-align:left}.tree small{font:12px sans-serif}.tree-panel{max-height:560px;overflow:auto;background:#f8fafc;border:1px solid var(--line);padding:12px}.proof{padding-left:22px}.proof li{margin:9px 0}.badge{display:inline-block;background:#e8f0f8;color:#184878;border:1px solid #c9d9e9;padding:3px 10px;border-radius:20px;font-size:13px}.long-hash{font:12px ui-monospace,monospace;overflow-wrap:anywhere}
@media(max-width:820px){.layout{display:block;padding:16px}nav{position:static;display:flex;flex-wrap:wrap;margin-bottom:15px}nav a{padding:6px 9px}section{padding:20px}.row{grid-template-columns:1fr}h1{font-size:24px}.route{font-size:16px}}
</style>
<header><small>水上挽月 · SocioVerse Challenge · 仅供本机查看与练习</small>
<h1>把提交ZIP拆开，看看它究竟如何运行</h1>
<div>当前内容：VERSION · ZIP_MEMBERS个ZIP文件 · 1个study · 本次新增模型调用0</div></header>
<div class='layout'><nav><a href='#relation'>1. 研究包与study</a><a href='#structure'>2. 包里有哪些东西</a><a href='#answers'>3. 真正的模型答卷</a><a href='#commands'>4. 评委怎样复现</a><a href='#proof'>5. 本机实际验收</a><a href='#limits'>6. 范围与边界</a></nav><main>
<section id='relation'><h2>一个容器，一项研究</h2><p class='lead'><b>study是研究本身的标准目录；研究包是交给评委的完整交付容器。</b></p>
<div class='route'><strong>研究包ZIP</strong><span>解压 →</span><strong>安装说明＋依赖＋证据</strong><span>＋</span><strong>studies/下的一个SCE study</strong></div>
<p>官方要求研究问题、人口P、环境E、运行配置、轨迹和报告按study组织。包根再提供安装与复现入口，让评委不用先理解整个开发仓库。</p>
<p class='muted'>官方依据：<a href='https://socioverse.fudan-disc.com/docs/zh/concepts/study-anatomy/' target='_blank' rel='noopener'>一个Study的解剖</a>。这里的预览副本不是第二份正式源码，也不是新的提交版本。</p></section>
<section id='structure'><h2>先看这四组，不必逐个读代码</h2>
<div class='row'><div><h3>包根：从这里开始</h3><p><code>README.md</code>安装与默认命令；<code>requirements.lock.txt</code>锁定依赖；<code>DIRECTORY_GUIDE.md</code>目录导航。</p><h3>标准study：研究和实现</h3><p><code>study.yaml</code>说明装配；<code>population/</code>、<code>environment/</code>、<code>simulation/</code>是标准P/E/运行产物。实现按组件、实验、计分、评价和运行分目录。</p></div>
<div><h3>复现数据：正式答卷在这里</h3><p><code>reproduction_data/</code>包含全国序列、逐答卷、评价参考和Normal材料。<code>simulation/research_runs.json</code>登记四个正式任务。</p><h3>审查与历史：按需阅读</h3><p><code>tests/</code>是包内测试；<code>experiment_logs/</code>是公开实验索引。<code>archive/</code>单独保存ARCHIVED_SOURCES份原始开发源码，不进入默认导入链。</p></div></div>
<p class='note'><b>20户工程示例 ≠ 论文样本。</b>标准population/environment/simulation中的小示例用于检查官方接口；正式四批模型输出保存在micro数据层。<code>reports/report.md</code>是包内结果导读，8页论文和视频另交。</p>
<details><summary><b>展开：ZIP真实完整目录（可点击说明文件）</b></summary><div class='tree-panel'>TREE</div></details>
<h3>在页面内读原文件</h3><select id='docSelect'>OPTIONS</select><pre class='file-view' id='docText'></pre></section>
<section id='answers'><h2>它包含真实模型回答，不只是汇总表</h2><p><code>reproduction_data/micro/</code>中最关键的几类资料：</p>
<ul><li><code>model_outputs.jsonl.gz</code>：四个正式任务共67,147条脱敏模型原文和失败/补跑记录。</li><li><code>effective_answers.jsonl.gz</code>：67,334个有效状态，包含复用起点；不是67,334次新调用。</li><li><code>A_paired_cases</code>及<code>A_full_wave_targets</code>：只供评价的配对与全波次参考。</li><li><code>density_cache</code>：按精确概率向量绑定的冻结密度计分缓存。</li><li><code>normal_mechanism</code>及<code>normal_population_rows</code>：Normal后验质量重算与人口展示行。</li></ul>
<details><summary><b>打开一份来自这个ZIP的脱敏真实答卷</b></summary><p>任务A，月份SAMPLE_PERIOD，匿名家庭SAMPLE_ID；下方原文与有效字段由response_id关联，现场没有调用模型。这是一例文件内容展示，不代表总体表现。</p>
<div class='row'><div><h3>模型回答原文</h3><pre>RAW</pre></div><div><h3>进入计分的有效字段</h3><pre>EFFECTIVE</pre></div></div></details></section>
<section id='commands'><h2>评委运行的命令</h2><p>先进入解压后同时含<code>README.md</code>和<code>requirements.lock.txt</code>的包根目录，再执行：</p><pre>GENERIC</pre>
<p>首次安装依赖需要网络；之后的默认复算不使用密钥、不调用LLM。每次输出到全新目录，终端最后打印<code>Results:</code>路径，打开其中的<code>index.html</code>。</p>
<div class='row'><div class='box'><h3>你的Mac：已经准备好</h3><p>双击本预览目录中的<b>运行复现.command</b>，或复制下面这一行到Terminal。它使用本机已有Python，每次另存一份结果。</p><pre>LOCAL_COMMAND</pre></div><div class='box'><h3>它会依次做什么</h3><ol><li>校验包内文件哈希。</li><li>20户、两步官方Core工程示例。</li><li>全国、组合及下游误差复算。</li><li>逐答卷计分、A微观指标和Normal重建。</li></ol></div></div>
<p>只做答卷复算：<code>--mode micro</code>；CPU重拟密度：<code>--mode micro --refit-density</code>。付费生成是另一条明确授权的入口，本预览command不会调用它。</p></section>
<section id='proof'><h2>刚刚从上传ZIP独立运行的结果</h2><span class='badge'>验收通过 · CHECKED（北京时间）</span>
<ul class='proof'><li>上传ZIP指纹与当前正式版本一致；VERIFIED_FILES个清单文件校验通过，另有manifest本身，共ZIP_MEMBERS个ZIP成员。</li><li>IMPORTED_MODULES个study模块全部来自新解压目录，没有从开发study偷取实现。</li><li>TEST_COUNT项包内测试通过；工程示例、聚合和正式逐答卷复算全部通过。</li><li>重算67,334个有效状态；本次新增API调用0，模型费用0。</li></ul>
<a class='button' href='verified_results/index.html' target='_blank' rel='noopener'>打开真实复算结果</a><a class='button' href='acceptance.json' target='_blank' rel='noopener'>查看验收记录</a><a href='tests.log' target='_blank' rel='noopener'>TEST_COUNT项测试原始日志</a>
<p class='long-hash'>源ZIP SHA256：HASH</p><p class='muted'>本次复用了已有无system-site-packages的隔离Python环境，没有重新联网安装依赖；研究包和上传原件未修改。</p></section>
<section id='limits'><h2>哪些事情没有被混在一起</h2>
<ul><li>复算历史回答与向DeepSeek重新提问分开。前者无需Key，后者需评审者自己的Key、合法完整输入及预算。</li><li>默认计分查用冻结密度缓存；加参数可重跑数值拟合。它不会把旧MAE直接当作新的微观计算。</li><li>近期B、月度和周度没有真人微观真值，不评价它们的微观准确性。DOWNSTREAM_LIMITS</li><li>INPUT_LIMITS</li></ul>
<p class='note'><b>提交仍使用原“提交材料”目录中的三件套。</b>本目录是查看与练习副本，打开或重复复算都不会改变正式ZIP、论文和视频。</p></section>
</main></div><script>const docs=DOCUMENTS;const select=document.getElementById('docSelect');function showDoc(path){select.value=path;document.getElementById('docText').textContent=docs[path];}select.addEventListener('change',()=>showDoc(select.value));document.querySelectorAll('[data-doc]').forEach(b=>b.addEventListener('click',()=>{showDoc(b.dataset.doc);document.getElementById('docSelect').scrollIntoView({behavior:'smooth',block:'center'});}));showDoc('README.md');</script></html>"""
    replacements = {"VERSION": version, "TREE": _tree(paths, docs), "OPTIONS": doc_options,
                    "SAMPLE_PERIOD": escape(effective["period"]), "SAMPLE_ID": escape(effective["household"]),
                    "RAW": escape(text), "EFFECTIVE": escape(sample), "GENERIC": escape(generic),
                    "LOCAL_COMMAND": escape(run_command), "CHECKED": checked.strftime("%Y-%m-%d %H:%M:%S"),
                    "HASH": proof["archive_sha256"], "DOCUMENTS": document_json,
                    "ZIP_MEMBERS": str(len(paths)), "VERIFIED_FILES": str(proof["verified_package_files"]),
                    "IMPORTED_MODULES": str(proof["study_modules_all_from_extracted_package"]),
                    "ARCHIVED_SOURCES": str(proof["archived_source_files_verified"]), "TEST_COUNT": test_match[1],
                    "DOWNSTREAM_LIMITS": ("默认all只重算封存下游预测的误差；另用review.py downstream可从公共序列真实重建面板并重拟原回归，calibrate可重估原训练期组合/宏观模型。" if portable.exists() else "默认下游部分重算封存预测的误差，没有重新拟合回归。"),
                    "INPUT_LIMITS": ("本版补齐公开原始源快照、SCE匿名编号/内部编码、调查日期、新闻候选与标签及原始调用凭证。PORTABLE_REPRODUCTION.md给出自备Key批量A/B、新月度/周度递推、重新评价与回归拟合命令；不依赖作者旧目录。Key等真实账号秘密不提供。含新闻ZIP仅供赛事保密评审，不公开上传GitHub。" if portable.exists() else
                        ((f"本版另附66,822份实际输入与选中新闻摘录，{input_metadata['full_prompt_rows']:,}份完整输入可用自己的Key单次再生成；" + ("A公开调查派生日期也完整保留，无需回填；" if input_metadata.get("public_survey_derived_dates_retained") else "A真实日期仍遮蔽；") + "原始身份键和Key不提供。含新闻的ZIP只供赛事保密评审，不进入公开GitHub。") if inputs_manifest.exists() else "不包含原始身份键、真实完成日期、密钥、完整历史提示与新闻全文；完整付费再生成仍有输入恢复条件。")) }
    # Single-pass replacement prevents a token in source text being reinterpreted.
    import re
    page = re.sub("|".join(re.escape(k) for k in sorted(replacements, key=len, reverse=True)),
                  lambda m: replacements[m[0]], page)
    (preview / "index.html").write_text(page)
    (preview / "本机阅读说明.md").write_text(
        "# 本机复现练习副本\n\n打开index.html看关系、目录、真实答卷和实际结果；isolated_package/是上传ZIP新解压的完整副本，verified_results/是本次复算输出。\n\n"
        "双击运行复现.command可重复运行，每次写入manual_results/新目录，不修改正式上传文件。该command使用本机已有Python；评委在其他电脑按包根README安装依赖。\n\n"
        "本预览目录不是另一份待提交研究包，不上传整个预览。\n")
    return {"preview": str(preview / "index.html"), "freshly_extracted_package": str(package),
            "terminal_command": str(preview / "运行复现.command"), "new_API_calls": 0}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--preview-dir", type=Path, required=True)
    p.add_argument("--python", type=Path)
    args = p.parse_args()
    print(json.dumps(build(args.preview_dir, args.python), ensure_ascii=False, indent=2))
