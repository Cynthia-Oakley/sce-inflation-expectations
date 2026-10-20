"""Render the aggregated panel JSON into a self-contained interactive HTML.

Single file: embedded CSS + aggregated JSON + vanilla JS drawing inline SVG.
No CDN, no server, file:// works. Only aggregate data is embedded; person
identifiers and raw ten-bin vectors never leave the aggregation layer.
"""
from __future__ import annotations

import json

_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>SCE 实验分析面板 v0</title>
<style>
:root { --bg:#f7f3ea; --card:#fffdf7; --ink:#22312a; --green:#1d4d3b;
        --navy:#23405f; --grey:#8a8f87; --line:#d8d2c2; --warn:#9aa39b; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
       font:15px/1.65 "PingFang SC","Hiragino Sans GB",sans-serif; }
h1,h2,h3,.serif { font-family:'Times New Roman','Kaiti SC',serif; }
header { background:var(--green); color:#f4f1e6; padding:22px 34px 14px; }
header h1 { margin:0 0 2px; font-size:26px; letter-spacing:1px; }
header .sub { font-size:13px; opacity:.85; }
.notice { background:#efe7d2; border-bottom:1px solid var(--line);
          padding:8px 34px; font-size:13.5px; color:#5c4f2a; }
.toolbar { display:flex; gap:18px; flex-wrap:wrap; align-items:center;
           padding:14px 34px; background:var(--card);
           border-bottom:1px solid var(--line); position:sticky; top:0; z-index:5; }
.toolbar label { font-size:13px; color:var(--grey); display:block; }
.toolbar select,.toolbar button { font-size:14px; padding:4px 8px;
           border:1px solid var(--line); border-radius:4px; background:#fff; color:var(--ink); }
.toolbar .qbtns button { cursor:pointer; }
.toolbar .qbtns button.on { background:var(--green); color:#fff; border-color:var(--green); }
.toolbar .qbtns button:disabled { opacity:.45; cursor:not-allowed; }
.meta { display:flex; gap:22px; flex-wrap:wrap; padding:10px 34px; font-size:13px;
        background:var(--card); border-bottom:1px solid var(--line); color:#4a554e; }
.meta b { color:var(--ink); }
main { padding:10px 34px 60px; max-width:1180px; }
section { margin:26px 0; }
section>h2 { font-size:21px; border-left:5px solid var(--green);
             padding-left:10px; margin-bottom:4px; }
.guide { font-size:13.5px; color:#5c665f; background:var(--card);
         border:1px solid var(--line); border-radius:6px; padding:8px 12px; margin:8px 0 14px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:8px;
        padding:14px 16px; margin:12px 0; overflow-x:auto; }
.card h3 { margin:2px 0 10px; font-size:17px; color:var(--navy); }
table { border-collapse:collapse; font-size:13.5px; width:100%; }
th,td { border:1px solid var(--line); padding:5px 9px; text-align:right; white-space:nowrap; }
th { background:#efeadb; font-weight:600; }
td.l,th.l { text-align:left; }
tr.drastic td { background:#f3ecd6; }
td.sup,tr.sup td { color:var(--warn); background:#f2f0ea; text-align:center; }
.bigrow { display:flex; gap:16px; flex-wrap:wrap; margin:10px 0; }
.stat { background:var(--card); border:1px solid var(--line); border-radius:8px;
        padding:12px 20px; min-width:170px; }
.stat .v { font-size:26px; font-family:'Times New Roman',serif; font-weight:bold; }
.stat .k { font-size:12.5px; color:var(--grey); }
.stat .v.g { color:var(--green); } .stat .v.n { color:var(--navy); }
.note { font-size:12.5px; color:#6b7268; margin:6px 0; }
.legend { font-size:12.5px; color:var(--grey); margin:4px 0; }
footer { padding:16px 34px; font-size:12px; color:var(--grey);
         border-top:1px solid var(--line); }
</style>
</head>
<body>
<header>
  <h1>SCE 实验分析面板 <span style="font-size:14px">v0 · 离线 · 零 API</span></h1>
  <div class="sub">美国 SCE 一年期通胀预期（赛道 A）· 聚合数据自包含 HTML · 生成于 <span id="genat"></span></div>
</header>
<div class="notice" id="notice"></div>
<div class="toolbar">
  <div><label>实验批次</label><select id="selExp"></select></div>
  <div><label>实验组 arm</label><select id="selArm"></select></div>
  <div><label>题目</label><div class="qbtns" style="display:flex;gap:6px">
    <button id="btnQ9" class="on">Q9 分布</button><button id="btnQ8">Q8 点值</button>
  </div></div>
  <div id="q8warn" style="font-size:12.5px;color:#a4453a;display:none">该批次 Q8 无对照数据，已禁用。</div>
</div>
<div class="meta" id="meta"></div>
<main>
  <section id="sec-1"><h2>一 · 总览</h2><div class="guide" id="guide-1"></div><div id="body-1"></div></section>
  <section id="sec-2"><h2>二 · 逐月与剧烈变化期</h2><div class="guide" id="guide-2"></div><div id="body-2"></div></section>
  <section id="sec-3"><h2>三 · 人群网格</h2><div class="guide" id="guide-3"></div><div id="body-3"></div></section>
  <section id="sec-4"><h2>四 · 先验与更新</h2><div class="guide" id="guide-4"></div><div id="body-4"></div></section>
  <section id="sec-5"><h2>五 · 回答结构与异质性</h2><div class="guide" id="guide-5"></div><div id="body-5"></div></section>
  <section id="sec-6"><h2>六 · 质量、输入与结论边界</h2><div class="guide" id="guide-6"></div><div id="body-6"></div></section>
</main>
<footer>本页仅嵌聚合指标（n/ESS/分位数/W1/直方图桶），不含 userid、agent_id 或逐人原始记录；缺失与未提供一律显示“未提供”，不填零。</footer>
<script id="panel-data" type="application/json">__PANEL_JSON__</script>
<script>
const PANEL = JSON.parse(document.getElementById('panel-data').textContent);
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const fmt = (v, d=2) => (v === null || v === undefined || Number.isNaN(v)) ? '<span style="color:#9aa39b">未提供</span>' : (typeof v === 'number' ? v.toFixed(d) : esc(v));
const C = {truth:'#1d4d3b', model:'#23405f', persist:'#8a8f87', warn:'#9aa39b'};

let cur = {exp:null, arm:null, q:'q9'};

function expKeys(){ return Object.keys(PANEL.experiments); }
function exp(){ return PANEL.experiments[cur.exp]; }
function sec(name){ return exp().sections[name]; }

/* ---------- table helper ---------- */
function table(headers, rows){
  let h = '<table><thead><tr>' + headers.map(x => Array.isArray(x)
    ? `<th class="${x[1]||''}">${x[0]}</th>` : `<th>${x}</th>`).join('') + '</tr></thead><tbody>';
  h += rows.join('') + '</tbody></table>';
  return h;
}
const td = (v,d) => `<td>${fmt(v,d)}</td>`;
const tdl = v => `<td class="l">${v===null||v===undefined?'未提供':esc(v)}</td>`;

/* ---------- inline SVG charts ---------- */
function lineChart(series, labels, opts={}){
  const W=860,H=260,P={l:52,r:16,t:14,b:34};
  const all = series.flatMap(s=>s.values.filter(v=>v!==null&&v!==undefined));
  if(!all.length) return '<div class="note">无可绘制数据</div>';
  let yMin=Math.min(...all), yMax=Math.max(...all);
  if(yMin===yMax){yMin-=1;yMax+=1;}
  const pad=(yMax-yMin)*0.12; yMin-=pad; yMax+=pad;
  const x=i=>P.l+(labels.length<2?0.5:(i/(labels.length-1)))*(W-P.l-P.r);
  const y=v=>P.t+(1-(v-yMin)/(yMax-yMin))*(H-P.t-P.b);
  let g='';
  for(let k=0;k<=4;k++){const gy=P.t+k/4*(H-P.t-P.b);
    g+=`<line x1="${P.l}" y1="${gy}" x2="${W-P.r}" y2="${gy}" stroke="#e4ddca" stroke-width="1"/>`;
    g+=`<text x="${P.l-6}" y="${gy+4}" font-size="10" text-anchor="end" fill="#8a8f87">${(yMax-k/4*(yMax-yMin)).toFixed(1)}</text>`;}
  labels.forEach((lb,i)=>{ if(labels.length<=16||i%2===0)
    g+=`<text x="${x(i)}" y="${H-16}" font-size="10" text-anchor="middle" fill="#8a8f87">${lb}</text>`;});
  series.forEach(s=>{
    const pts=s.values.map((v,i)=>(v===null||v===undefined)?null:`${x(i)},${y(v)}`).filter(Boolean).join(' ');
    if(pts) g+=`<polyline points="${pts}" fill="none" stroke="${s.color}" stroke-width="2"/>`;
    s.values.forEach((v,i)=>{ if(v!==null&&v!==undefined) g+=`<circle cx="${x(i)}" cy="${y(v)}" r="2.6" fill="${s.color}"/>`;});
  });
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px;background:#fffdf7;border:1px solid var(--line);border-radius:6px">${g}</svg>`;
}
function groupedBars(groups, names, colors){
  const W=860,H=250,P={l:52,r:16,t:14,b:46};
  const vals=groups.flatMap(g=>g.values.filter(v=>v!==null&&v!==undefined));
  if(!vals.length) return '<div class="note">无可绘制数据</div>';
  const yMax=Math.max(...vals)*1.15||1;
  const slot=(W-P.l-P.r)/groups.length, bw=Math.min(26,(slot-8)/names.length);
  const y=v=>P.t+(1-v/yMax)*(H-P.t-P.b);
  let g='';
  for(let k=0;k<=4;k++){const gy=P.t+k/4*(H-P.t-P.b);
    g+=`<line x1="${P.l}" y1="${gy}" x2="${W-P.r}" y2="${gy}" stroke="#e4ddca"/>`;
    g+=`<text x="${P.l-6}" y="${gy+4}" font-size="10" text-anchor="end" fill="#8a8f87">${(yMax*(1-k/4)).toFixed(1)}</text>`;}
  groups.forEach((gr,gi)=>{
    const cx0=P.l+gi*slot+slot/2;
    gr.values.forEach((v,ni)=>{
      if(v===null||v===undefined) return;
      const bx=cx0-(names.length*bw)/2+ni*bw;
      g+=`<rect x="${bx}" y="${y(v)}" width="${bw-2}" height="${Math.max(0,H-P.b-y(v))}" fill="${colors[ni]}"/>`;
      g+=`<text x="${bx+bw/2-1}" y="${y(v)-3}" font-size="9" text-anchor="middle" fill="#4a554e">${v.toFixed(2)}</text>`;
    });
    g+=`<text x="${cx0}" y="${H-28}" font-size="10" text-anchor="middle" fill="#8a8f87">${gr.label}</text>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px;background:#fffdf7;border:1px solid var(--line);border-radius:6px">${g}</svg>`;
}
function histBars(histA, histB, nameA, nameB){
  const labels=histA.map(h=>h.label);
  const groups=labels.map((lb,i)=>({label:lb, values:[histA[i].n, histB?histB[i].n:null]}));
  return groupedBars(groups, [nameA, nameB], [C.model, C.truth]);
}
const legend = items => `<div class="legend">${items.map(([c,t])=>`<span style="color:${c}">■</span> ${t}`).join('　')}</div>`;

/* ---------- sections ---------- */
function renderOverview(){
  const o = sec('overview');
  let html='';
  if(cur.q==='q9'){
    const rows=Object.entries(o.q9).map(([arm,r])=>{
      const p=r.persistence;
      return `<tr><td class="l"><b>${esc(arm)}</b></td><td>${r.n_person_months}</td><td>${r.n_months}</td><td>${fmt(r.ess,1)}</td>`+
        td(r.mae_pp)+td(r.median_abs_error_pp)+td(r.bias_pp)+td(r.w1_pp)+td(r.centered_w1_pp)+
        td(r.pred_median_pp)+td(r.truth_median_pp)+td(r.pred_iqr_pp)+td(r.truth_iqr_pp)+
        (p?td(p.mae_pp)+td(p.bias_pp)+`<td>${p.n_identical_support!==undefined?p.n_identical_support:'未提供'}</td>`
          :'<td colspan="3" style="text-align:center;color:#9aa39b">未提供</td>')+'</tr>';
    });
    html += '<div class="card"><h3>Q9：逐人误差与分布指标（按月计算后等月平均）</h3>'+
      table(['arm','n(人×月)','月数','ESS','逐人MAE','中位MAE','带符号偏差','跨人W1','去心W1','模型中位','真人中位','模型IQR','真人IQR','照抄MAE','照抄偏差','同支持n'],rows)+
      '<div class="note">照抄上期（persistence）用本人上期预期当真值预测，只在模型与照抄完全相同的人×月支持上计算；权重口径：'+esc(exp().weight_field||'未提供')+'，遍数平分。</div></div>';
  } else {
    const rows=Object.entries(o.q8).map(([arm,c])=>{
      if(c.suppressed) return `<tr><td class="l"><b>${esc(arm)}</b></td><td>${c.n}</td><td colspan="6" class="sup">n 不足</td></tr>`;
      return `<tr><td class="l"><b>${esc(arm)}</b></td><td>${c.n}</td><td>${fmt(c.ess,1)}</td>`+
        td(c.mae_pp)+td(c.median_abs_error_pp)+td(c.bias_pp)+td(c.pred_median_pp)+td(c.truth_median_pp)+
        '<td style="text-align:center;color:#9aa39b">未提供</td></tr>';
    });
    html += '<div class="card"><h3>Q8：点值误差（Q9 为主线的并列简表）</h3>'+
      table(['arm','n(人×月)','ESS','逐人MAE','中位MAE','带符号偏差','模型中位','真人中位','照抄上期'],rows)+
      '<div class="note">上期无 Q8 点值存档，照抄基线对 Q8 未提供。</div></div>';
  }
  $('body-1').innerHTML = html + o.notes.map(n=>`<div class="note">· ${esc(n)}</div>`).join('');
}

function renderMonthly(){
  const m = sec('monthly'), arm = cur.arm;
  const block = m[arm];
  if(!block){ $('body-2').innerHTML='<div class="note">未提供</div>'; return; }
  const rows=block.rows.map(r=>{
    const cls = r.regime==='drastic' ? ' class="drastic"' : '';
    if(r.suppressed) return `<tr${cls}><td class="l">${r.month}</td><td>${r.regime==='drastic'?'剧烈':'平稳'}</td><td>${r.n}</td><td colspan="7" class="sup">n 不足</td></tr>`;
    return `<tr${cls}><td class="l">${r.month}</td><td>${r.regime==='drastic'?'剧烈':(r.regime==='calm'?'平稳':'未知')}</td><td>${r.n}</td><td>${fmt(r.ess,1)}</td>`+
      td(r.truth_median_pp)+td(r.model_median_pp)+td(r.persist_median_pp)+td(r.model_mae_pp)+td(r.persist_mae_pp)+td(r.w1_pp)+'</tr>';
  });
  const labels=block.rows.map(r=>String(r.month).slice(2));
  const med=lineChart([
    {name:'真人中位', color:C.truth, values:block.rows.map(r=>r.suppressed?null:r.truth_median_pp)},
    {name:'模型中位', color:C.model, values:block.rows.map(r=>r.suppressed?null:r.model_median_pp)},
    {name:'照抄中位', color:C.persist, values:block.rows.map(r=>r.suppressed?null:r.persist_median_pp)},
  ], labels);
  const mae=groupedBars(block.rows.map(r=>({label:String(r.month).slice(2),
    values:r.suppressed?[null,null]:[r.model_mae_pp, r.persist_mae_pp]})), ['模型','照抄'], [C.model, C.persist]);
  const t=block.regime_table;
  const regimeRows=[['平稳',t.calm],['剧烈',t.drastic]].map(([lb,g])=>
    `<tr><td class="l">${lb}</td><td>${g.n_months}</td>${td(g.model_mae_pp)}${td(g.persist_mae_pp)}</tr>`);
  let html='<div class="card"><h3>逐月中位（绿=真人，蓝=模型，灰=照抄上期）</h3>'+
    legend([[C.truth,'真人中位'],[C.model,'模型中位'],[C.persist,'照抄中位']])+med+'</div>';
  html+='<div class="card"><h3>逐月 MAE：模型 vs 照抄（黄色底纹行为剧烈月）</h3>'+
    legend([[C.model,'模型MAE'],[C.persist,'照抄MAE']])+mae+'</div>';
  html+='<div class="card"><h3>机制月 2×2（等月平均 MAE）</h3>'+
    table(['机制月','月数','模型MAE','照抄MAE'],regimeRows)+
    `<div class="note">剧烈月技能值 S = 照抄MAE − 模型MAE = <b>${fmt(block.skill_s_drastic_pp)}</b> pp（S>0 表示模型优于照抄）。</div></div>`;
  html+='<div class="card"><h3>逐月明细表</h3>'+
    table(['月份','机制','n','ESS','真人中位','模型中位','照抄中位','模型MAE','照抄MAE','跨人W1'],rows)+'</div>';
  html+=block.notes.map(n=>`<div class="note">· ${esc(n)}</div>`).join('');
  $('body-2').innerHTML=html;
}

function renderGrid(){
  const g=sec('grid'), arm=cur.arm;
  const dims=g[arm]||{};
  let html='';
  const cellRow=(label,c)=> c.suppressed
    ? `<tr><td class="l">${esc(label)}</td><td>${c.n}</td><td>${fmt(c.ess,1)}</td><td colspan="5" class="sup">n 不足</td></tr>`
    : `<tr><td class="l">${esc(label)}</td><td>${c.n}</td><td>${fmt(c.ess,1)}</td>${td(c.mae_pp)}${td(c.persist_mae_pp)}${td(c.bias_pp)}${td(c.w1_pp)}${td(c.centered_w1_pp)}</tr>`;
  for(const [dim,title] of [['six_cell','六格网格（学历×在职）'],['age_group','年龄切片'],['household_income_band','家庭收入切片'],['numeracy','数理切片'],['region','地区切片'],['housing_tenure','住房切片']]){
    const cells=dims[dim]||{};
    const entries=Object.entries(cells);
    if(!entries.length){ html+=`<div class="card"><h3>${title}</h3><div class="note">未提供</div></div>`; continue; }
    html+=`<div class="card"><h3>${title}</h3>`+
      table(['组','n(人×月)','ESS','模型MAE','照抄MAE','带符号偏差','跨人W1','去心W1'],
        entries.map(([k,c])=>cellRow(c.label_cn||k,c)))+'</div>';
  }
  html+='<div class="note">· 各切片为独立单变量分组（非交叉）；缺失画像归入“未知”，不与任何组混合。</div>';
  $('body-3').innerHTML=html;
}

function renderPriors(){
  const p=sec('priors'), arm=cur.arm;
  const block=p[arm];
  if(!block){ $('body-4').innerHTML='<div class="note">未提供</div>'; return; }
  const rowsOf=obj=>Object.values(obj).map(c=> c.suppressed
    ? `<tr><td class="l">${esc(c.label_cn)}</td><td>${c.n}</td><td>${fmt(c.ess,1)}</td><td colspan="7" class="sup">n 不足</td></tr>`
    : `<tr><td class="l">${esc(c.label_cn)}</td><td>${c.n}</td><td>${fmt(c.ess,1)}</td>${td(c.prior_mean_pp)}${td(c.truth_mean_pp)}${td(c.model_mean_pp)}${td(c.model_mae_pp)}${td(c.persist_mae_pp)}${td(c.model_bias_pp)}${td(c.w1_pp)}${td(c.delta_w1_pp)}</tr>`);
  let html='<div class="card"><h3>按上期真人预期四档（前置特征分组）</h3>'+
    table(['上期预期档','n','ESS','先验均值','真人均值','模型均值','模型MAE','照抄MAE','带符号偏差','跨人W1','Δ分布W1'],rowsOf(block.bands))+'</div>';
  html+='<div class="card"><h3>按真人本期变化方向（事后诊断，仅用于评价）</h3>'+
    table(['真人本期','n','ESS','先验均值','真人均值','模型均值','模型MAE','照抄MAE','带符号偏差','跨人W1','Δ分布W1'],rowsOf(block.directions))+'</div>';
  html+=block.notes.map(n=>`<div class="note">· ${esc(n)}</div>`).join('');
  $('body-4').innerHTML=html;
}

function renderStructure(){
  const s=sec('structure'), arm=cur.arm;
  const block=s[arm];
  if(!block){ $('body-5').innerHTML='<div class="note">未提供</div>'; return; }
  const cp=block.cross_person;
  let html='<div class="bigrow">'+
    `<div class="stat"><div class="v g">${fmt(cp.truth_std_pp)}<span style="font-size:13px">pp</span></div><div class="k">真人跨人 std（核心参照）</div></div>`+
    `<div class="stat"><div class="v n">${fmt(cp.model_std_pp)}<span style="font-size:13px">pp</span></div><div class="k">模型跨人 std</div></div>`+
    `<div class="stat"><div class="v g">${fmt(cp.truth_iqr_pp)}</div><div class="k">真人跨人 IQR</div></div>`+
    `<div class="stat"><div class="v n">${fmt(cp.model_iqr_pp)}</div><div class="k">模型跨人 IQR</div></div></div>`;
  html+=`<div class="note">· ${esc(block.note)}</div>`;
  const sh=(title,key)=>{
    const a=(block.model_shape||{})[key], b=(block.truth_shape||{})[key];
    if(!a && !b) return `<div class="card"><h3>${title}</h3><div class="note">未提供</div></div>`;
    return `<div class="card"><h3>${title}</h3>${legend([[C.model,'模型'],[C.truth,'真人']])}`+
      histBars(a,b||a,'模型','真人')+
      `<div class="note">n：模型 ${(block.model_shape||{}).n}，真人 ${(block.truth_shape||{}).n}；零通缩概率占比：模型 ${fmt((block.model_shape||{}).zero_deflation_share,3)}，真人 ${fmt((block.truth_shape||{}).zero_deflation_share,3)}；十档全零占比：模型 ${fmt((block.model_shape||{}).all_zero_share,3)}，真人 ${fmt((block.truth_shape||{}).all_zero_share,3)}</div></div>`;
  };
  html+=sh('十档形状特征：非零档数分布','nz_bins');
  html+=sh('十档形状特征：最大档概率分布（%）','max_prob');
  html+=sh('十档形状特征：概率为 5 的倍数占比分布','mult5_share');
  const r=block.repeats;
  if(r){
    html+='<div class="card"><h3>两遍重复：人内波动 vs 人际差异</h3><div class="bigrow">'+
      `<div class="stat"><div class="v n">${fmt(r.within_person_std_pp)}</div><div class="k">人内 std（同输入两遍）</div></div>`+
      `<div class="stat"><div class="v g">${fmt(r.between_person_std_pp)}</div><div class="k">人际 std（两遍均值）</div></div>`+
      `<div class="stat"><div class="v">${fmt(r.deducted_between_var_pp2,3)}</div><div class="k">扣除噪声后方差(pp²)</div></div></div>`+
      `<div class="note">n=${r.n_persons} 人×月，${r.n_months} 个月。${esc(r.note)}</div></div>`;
  } else {
    html+='<div class="card"><h3>两遍重复诊断</h3><div class="note">未提供（无同一人多遍记录）</div></div>';
  }
  $('body-5').innerHTML=html;
}

function renderQuality(){
  const q=sec('quality');
  const arms=q.arms||{};
  const rows=Object.entries(arms).map(([arm,a])=>`<tr><td class="l"><b>${esc(arm)}</b></td><td>${a.n_records}</td><td>${a.n_scorable}</td><td>${fmt(a.missing_share,4)}</td><td class="l">${esc(Object.entries(a.scorer_status).map(([k,v])=>k+':'+v).join('，')||'未提供')}</td><td>${fmt(a.normalization_applied_share,4)}</td><td>${a.weight_missing}</td><td>${fmt(a.q8_truth_coverage,3)}</td><td>${fmt(a.q8_model_coverage,3)}</td></tr>`);
  const pr=q.protocol||{};
  const meta=(k,v)=>`<span><b>${k}</b>：${v===null||v===undefined?'<span style="color:#9aa39b">未提供</span>':esc(Array.isArray(v)?v.join('、'):v)}</span>`;
  let html='<div class="card"><h3>每实验组数据质量</h3>'+
    table(['arm','记录数','可评分','缺失率','scorer_status 计数','归一化比例','权重缺失','Q8真值覆盖','Q8模型覆盖'],rows)+'</div>';
  html+='<div class="card"><h3>协议与运行元数据（来自 summary.json）</h3><div style="display:flex;flex-wrap:wrap;gap:8px 22px;font-size:13.5px">'+
    meta('模型',pr.model)+meta('官方标识',pr.official_advertised_version)+meta('温度',pr.temperature)+
    meta('协议',pr.id)+meta('研究线',pr.research_line)+meta('月数/人数',(pr.months?pr.months.length:'未提供')+' 月 × '+(pr.n_per_month||'未提供'))+
    meta('状态',pr.batch_status)+meta('费用估计(USD)',pr.estimated_cost_usd)+'</div></div>';
  const batches=PANEL.source_batches.map(b=>`<tr><td class="l">${esc(b.batch)}</td><td class="l">${esc(b.label)}${b.registered?'':'（未登记）'}</td><td>${esc(b.status==='ok'?'已接入':'未接入')}</td><td class="l">${esc(b.skip_reason||'—')}</td><td>${b.n_cases}</td></tr>`);
  html+='<div class="card"><h3>批次清单（自动发现 outputs/*_evaluation_*）</h3>'+
    table(['批次','显示名','状态','原因','cases 数'],batches)+'</div>';
  html+='<div class="note">· 跨组/跨批比较先看月份集合、人数、模型与权重口径是否一致；不一致时只能描述整套配置差异，不按原始均值排榜。</div>';
  $('body-6').innerHTML=html;
}

/* ---------- top bar ---------- */
function renderMeta(){
  const e=exp(), pr=e.protocol||{};
  $('meta').innerHTML=
    `<span><b>${esc(e.label)}</b>${e.registered?'':'（未登记）'}</span>`+
    `<span>说明：${esc(e.description)}</span>`+
    `<span>模型：<b>${esc(pr.model||'未提供')}</b>${pr.temperature!==undefined?'（T='+esc(pr.temperature)+'）':''}</span>`+
    `<span>月份：${e.months.length} 个（${e.months[0]}–${e.months[e.months.length-1]}）</span>`+
    `<span>arms：${e.arms.length}</span>`+
    `<span>权重：${esc(e.weight_field||'未提供')}</span>`+
    `<span>费用估计：${pr.estimated_cost_usd!==undefined?(typeof pr.estimated_cost_usd==='number'?pr.estimated_cost_usd.toFixed(2):esc(pr.estimated_cost_usd))+' USD':'未提供'}</span>`;
}
function renderAll(){
  renderMeta();
  renderOverview(); renderMonthly(); renderGrid(); renderPriors(); renderStructure(); renderQuality();
}
function init(){
  $('notice').textContent=PANEL.comparability_notice;
  $('genat').textContent=PANEL.generated_at_utc.slice(0,19).replace('T',' ');
  ['overview','monthly','grid','priors','structure','quality'].forEach(n=>{
    $('guide-'+({overview:1,monthly:2,grid:3,priors:4,structure:5,quality:6}[n])).textContent=PANEL.section_guides[n];
  });
  const sel=$('selExp');
  expKeys().forEach(k=>{const e=PANEL.experiments[k];const o=document.createElement('option');
    o.value=k;o.textContent=e.label+'（'+k+'）';sel.appendChild(o);});
  cur.exp=expKeys()[0];
  sel.value=cur.exp;
  sel.onchange=()=>{cur.exp=sel.value;fillArms();renderAll();};
  $('btnQ9').onclick=()=>{cur.q='q9';$('btnQ9').classList.add('on');$('btnQ8').classList.remove('on');renderOverview();};
  $('btnQ8').onclick=()=>{ if(!exp().q8_available) return; cur.q='q8';$('btnQ8').classList.add('on');$('btnQ9').classList.remove('on');renderOverview();};
  fillArms();
  $('selArm').onchange=()=>{cur.arm=$('selArm').value;renderAll();};
  renderAll();
}
function fillArms(){
  const e=exp(), sel=$('selArm');
  sel.innerHTML='';
  e.arms.forEach(a=>{const o=document.createElement('option');o.value=a;o.textContent=a;sel.appendChild(o);});
  cur.arm=e.arms[0]; sel.value=cur.arm;
  const hasQ8=e.q8_available;
  $('btnQ8').disabled=!hasQ8;
  $('q8warn').style.display=hasQ8?'none':'block';
  if(!hasQ8){cur.q='q9';$('btnQ9').classList.add('on');$('btnQ8').classList.remove('on');}
}
init();
</script>
</body>
</html>
"""


def render_html(panel):
    payload = json.dumps(panel, ensure_ascii=False, allow_nan=False)
    payload = payload.replace('</', '<\\/')
    return _PAGE.replace('__PANEL_JSON__', payload)
