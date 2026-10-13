"""Render a frozen public comparison summary as a local, offline reading page."""
import argparse
import json
from pathlib import Path


TEMPLATE = '''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SCE：同样本评价与基线</title>
<style>
body{font:16px/1.75 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;color:#25312f;background:#fafbf9;margin:0}
main{max-width:1100px;margin:auto;padding:28px 24px 55px}h1{font-size:27px;margin-bottom:8px}h2{font-size:21px;margin-top:32px}p{max-width:900px}a{color:#176859}small,.muted{color:#5e6864}section{border-top:1px solid #d9dfda;padding-top:16px}
.intro{border-left:4px solid #176859;padding:4px 18px;background:#f0f5f1}.controls{display:flex;gap:18px;flex-wrap:wrap;margin:24px 0}select{padding:7px 12px;font-size:16px;border:1px solid #bfc9c1;border-radius:4px;background:white}.plots{display:grid;grid-template-columns:1fr 1fr;gap:18px}.plot{background:white;padding:16px;border:1px solid #e0e5df}.plot h3{font-size:17px;margin:0 0 12px}.scroll{overflow-x:auto}svg{width:100%;min-width:390px;height:auto}table{border-collapse:collapse;width:100%;min-width:900px;font-size:15px}th,td{text-align:left;padding:11px 14px;border-bottom:1px solid #dce2dc;white-space:nowrap}th{background:#f0f4ef}code{overflow-wrap:anywhere;font-size:.9em}li{margin:8px 0}.note{background:#f2f4f0;padding:14px 20px}.metricdefs{columns:2;column-gap:30px}.metricdefs p{break-inside:avoid}@media(max-width:850px){.plots{grid-template-columns:1fr}.metricdefs{columns:1}main{padding:20px 15px}}
</style><main>
<h1>我们既要保留人的差异，也要合理更新</h1>
<p class="muted">SCE一年期通胀预期 · 同样本离线评价 · 新API调用0</p>
<div class="intro"><p><strong>当前结论：</strong>本人先验帮助LLM改善，但其人群分布仍明显过窄。上期照抄更能保留差异，LLM的跨月变化分布较近；后续机制需要兼顾两者。</p></div>
<p>四期每期12人，48个人月；两次生成不等于增加真人人数。Q9共同评价47人月/94条，Q8为48人月/96条。所有方法使用同一批人、同一计分与经验分位数；这是小样机制诊断，不是全国预测成绩。</p>
<div class="controls"><label>回答类型 <select id="measure"><option value="Q9">Q9 概率回答的个人均值</option><option value="Q8">Q8 点回答</option></select></label><label>时期 <select id="month"><option value="all">四期等权汇总</option><option value="202203">2022-03</option><option value="202209">2022-09</option><option value="202303">2023-03</option><option value="202403">2024-03</option></select></label><label>生成 <select id="repeat"><option value="all">两次平均</option><option value="1">第一次</option><option value="2">第二次</option></select></label></div>
<div class="plots" id="plots"></div>
<p class="muted" id="caption"></p>
<div class="scroll"><table><thead><tr><th>方法</th><th>总体MAE</th><th>人群W1</th><th>变化W1</th><th>人际IQR</th><th>真人IQR</th><th>有符号中心偏差</th></tr></thead><tbody id="numbers"></tbody></table></div>
<p>上表均为百分点。主分位数采用左逆经验CDF，插值只另存作敏感性。人群IQR不等于单个人的概率不确定性。</p>
<section><h2>三个指标分别在问什么？</h2><div class="metricdefs"><p><strong>总体中位数MAE：</strong>这批人的总体预期水平有没有对上？Q9是个人密度均值的跨人中位数，不是Q8或个人分布中位数。</p><p><strong>人群W1：</strong>不同人的预期整体分布是否接近真人？同时受水平、形状与尾部影响，不只是方差。</p><p><strong>变化W1：</strong>从本人上期到本期的变化分布是否像真人？它不能证明每个人都获得了正确更新。</p><p><strong>人际IQR：</strong>中间50%的人彼此差多少？扩大跨度本身不等于模拟成功。</p></div></section>
<section><h2>怎样理解目前的证据？</h2><ul>
<li>本人先验LLM相对无先验，截面/变化W1均下降；本批按人配对区间支持这两项改善。总体MAE虽下降，区间仍跨0。</li>
<li>LLM相对照抄的人群W1多约1.399pp，条件区间约[0.117,1.799]；相对个人锚多1.668pp，约[0.513,1.933]。差异被压缩仍是需要解决的问题。</li>
<li>LLM总体误差点结果不及两种简单基线，但相应区间很宽，不能从12人小样推论它在全国必然更差。</li>
<li>本人/置换先验差异仍不明确；“更新像真人”与“按正确身份更新”应分开检验。</li></ul>
<div class="note">这些区间固定四个被选月份，用受访者为单位重抽样，保留两次生成；不覆盖未来月份、模型全部生成随机性或全国人口。不含0只是本批条件下的方向证据，不是机制因果证明。</div></section>
<section><h2>两个基线用的是什么？</h2><p><strong>上期照抄：</strong>保留本人上期Q9；预测变化是0。<strong>过去个人锚：</strong>上期值向本人严格过去均值移动一半；历史不足两次则照抄。没有读取本期答案或全国真值。固定0.5借自旧训练候选，未用这批结果优化。</p><p>个人锚只预测中心，不虚构十档概率；Q8没有对应锚规则。它去掉了Kimi原C1的当月真值共同变化项、改为同冻结计分，不能引用原C1成绩。</p><p>个人锚没有新闻/宏观E，但拿到了更早期个人历史；旧LLM有E，却只拿到上期回答。两边信息并非一方完全包含另一方。新状态组增加历史摘要后，这一维更接近；差距仍不能全部归于方法，未来也需要更完整的信息公平性对照。</p></section>
<section><h2>下一步如何判断？</h2><p>新U1与旧本人先验比较：两次生成都降低总体MAE和人群W1，变化W1不恶化，回答有效覆盖不减少，才记作项目“小试信号”。还要并列对比两个简单基线。这是筛选规则，不能直接正式采用。</p><p>若只有格式变得像、单项误差下降或方差增大，记录局部结果。若联合改善，再另留月份、扩大代表性样本并检查路线B自身状态递推。原生回答为主；报告映射另作敏感性，偏差不能略去。</p></section>
<section><h2>复算与交接</h2><p>30项测试；独立W1/分位数核对最大差5.33e-15；48份历史的当期/未来及权重扰动不改变基线；96份旧回答经新接入口复放结果零差。无新模拟。</p><p>主分析：<code>outputs/sce_behavior_comparison_20261013_v2/</code>；私有行只在本地outputs。源码和输入哈希见聚合记录。</p><p>当前工作区复算需要本地缓存及冻结内核，15待审文件仍未提交；本轮没有宣称仅克隆仓库即可运行。</p><p><a href="codex_comparison_results.md">完整结果与统计解释</a> · <a href="codex_comparison_input_spec.md">给Kimi的接入规范</a> · <a href="codex_comparison_summary.json">聚合结果</a> · <a href="../../current_todo.html">任务清单</a></p></section>
</main><script>
const DATA=__DATA__;
const LABELS={no_prior:'无先验LLM',own_previous:'本人先验LLM',permuted_previous:'置换先验LLM',copy_previous:'本人上期照抄',history_anchor_half:'过去个人锚调整'};
const defs=[['sample_center_mae_pp','总体中位数MAE'],['cross_section_w1_pp','人群截面W1'],['delta_w1_pp','跨月变化W1']];
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function render(){const q=document.getElementById('measure').value,m=document.getElementById('month').value,r=document.getElementById('repeat').value;const arms=DATA.measures[q].conditions;
const entries=Object.entries(arms).map(([name,x])=>{const cells=x.cells.filter(c=>(m==='all'||String(c.month)===m)&&(r==='all'||String(c.repeat)===r));const av={};for(const k of Object.keys(cells[0])) if(typeof cells[0][k]==='number') av[k]=cells.reduce((s,c)=>s+c[k],0)/cells.length;return[name,av];});
document.getElementById('plots').innerHTML=defs.map(([k,title])=>{const max=Math.max(...entries.map(([,v])=>v[k]),.1)*1.12;const ticks=[0,max/2,max];let s='<svg viewBox="0 0 570 265" role="img" aria-label="'+esc(title)+'"><text x="0" y="15" font-size="12" fill="#637169">纵轴：方法；横轴：距离/误差（百分点）</text>';
entries.forEach(([a,v],i)=>{const y=48+i*34;const fill=a==='own_previous'?'#176859':'#a3afa7';s+='<text x="0" y="'+(y+13)+'" font-size="13">'+esc(LABELS[a]||a)+'</text><rect x="160" y="'+y+'" width="'+(325*v[k]/max)+'" height="20" fill="'+fill+'"/><text x="'+(168+325*v[k]/max)+'" y="'+(y+14)+'" font-size="13">'+v[k].toFixed(3)+'</text>';});s+='<line x1="160" x2="485" y1="224" y2="224" stroke="#a3afa7"/>';ticks.forEach(t=>s+='<text x="'+(160+325*t/max)+'" y="244" text-anchor="middle" font-size="12">'+t.toFixed(1)+'</text>');return '<div class="plot"><h3>'+esc(q+' · '+title)+'（越低越好）</h3><div class="scroll">'+s+'</svg></div></div>';}).join('');
const keys=['sample_center_mae_pp','cross_section_w1_pp','delta_w1_pp','cross_person_iqr_pp','real_cross_person_iqr_pp','center_bias_pp'];document.getElementById('numbers').innerHTML=entries.map(([a,v])=>'<tr><td>'+esc(LABELS[a]||a)+'</td>'+keys.map(k=>'<td>'+v[k].toFixed(3)+'</td>').join('')+'</tr>').join('');document.getElementById('caption').textContent='来源：已封存的本人先验三组回答与SCE问卷；'+(m==='all'?'2022-03 / 2022-09 / 2023-03 / 2024-03，四期等权':'月份 '+m)+'；'+(r==='all'?'两次生成等权':'第'+r+'次生成')+'。绿色为本人先验LLM，灰色为其他参照。';}
['measure','month','repeat'].forEach(id=>document.getElementById(id).addEventListener('change',render));render();
</script></html>'''


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    data = json.loads(args.summary.read_text())
    if "results" in data:
        data = data["results"]
    embedded = json.dumps(data, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    args.out.write_text(TEMPLATE.replace("__DATA__", embedded), encoding="utf-8")
    print(f"Reading page saved: {args.out}")
