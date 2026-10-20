"""Render the aggregated panel JSON into a self-contained interactive HTML.

Single file: embedded CSS + aggregated JSON + vanilla JS drawing inline SVG.
No CDN, no server, file:// works. Only aggregate data is embedded; person
identifiers and raw ten-bin vectors never leave the aggregation layer. All
explanatory numbers are generated from the aggregated data, never hardcoded.
"""
from __future__ import annotations

import json

_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>SCE 实验分析面板 v1</title>
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
.toolbar a { font-size:13px; color:var(--navy); }
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
tr.explor td,td.explor { background:#eef0ea; color:#5c665f; }
tr.weakess td:first-child { border-left:4px solid #c9a227; }
.bigrow { display:flex; gap:16px; flex-wrap:wrap; margin:10px 0; }
.stat { background:var(--card); border:1px solid var(--line); border-radius:8px;
        padding:12px 20px; min-width:170px; }
.stat .v { font-size:26px; font-family:'Times New Roman',serif; font-weight:bold; }
.stat .k { font-size:12.5px; color:var(--grey); }
.stat .v.g { color:var(--green); } .stat .v.n { color:var(--navy); }
.note { font-size:12.5px; color:#6b7268; margin:6px 0; }
.legend { font-size:12.5px; color:var(--grey); margin:4px 0; }
/* catalog */
.catalog { padding:14px 34px 4px; }
.catalog h2 { font-size:20px; margin:6px 0; font-family:'Times New Roman','Kaiti SC',serif; }
.pinned { display:flex; gap:14px; flex-wrap:wrap; margin:8px 0; }
.pin { background:var(--card); border:1px solid var(--line); border-left:5px solid var(--green);
       border-radius:6px; padding:10px 16px; min-width:330px; flex:1; }
.pin .t { font-size:12.5px; color:var(--grey); }
.pin .name { font-size:17px; font-weight:600; color:var(--green); }
.pin .name a { color:inherit; }
.catgroup { margin:10px 0; }
.catgroup>h3 { font-size:16px; margin:8px 0 4px; color:var(--navy); }
.catgroup table { font-size:13px; }
.badge { display:inline-block; font-size:11.5px; border:1px solid var(--line);
         border-radius:8px; padding:0 7px; margin-left:6px; color:#5c665f; background:#f2f0ea; }
footer { padding:16px 34px; font-size:12px; color:var(--grey);
         border-top:1px solid var(--line); }
</style>
</head>
<body>
<header>
  <h1>SCE 实验分析面板 <span style="font-size:14px">v1 · 离线 · 零 API</span></h1>
  <div class="sub">美国 SCE 一年期通胀预期（赛道 A）· 实验目录＋单实验视图 · 聚合数据自包含 HTML · 生成于 <span id="genat"></span></div>
</header>
<div class="notice" id="notice"></div>
<div class="catalog" id="catalog"></div>
<div class="toolbar" id="toolbar">
  <a href="#catalog" id="lnkCatalog">☰ 实验目录</a>
  <div><label>实验批次</label><select id="selExp"></select></div>
  <div><label>实验组 arm</label><select id="selArm"></select></div>
  <div><label>题目</label><div class="qbtns" style="display:flex;gap:6px">
    <button id="btnQ9" class="on">Q9 分布</button><button id="btnQ8">Q8 简表</button>
  </div></div>
  <div id="q8warn" style="font-size:12.5px;color:#a4453a;display:none">该批次 Q8 无可对照数据，已禁用。</div>
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
<footer>本页仅嵌聚合指标（n/ESS/分位数/W1/直方图桶），不含 userid、agent_id、逐人记录或原始十档向量；缺失与未提供一律显示“未提供”，不填零。</footer>
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
const CLASS_CN = {coverage:'仅覆盖（n<10）', exploratory:'探索（10≤n<20）', weak_ess:'显示·ESS<10', normal:'正常'};

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

/* ---------- catalog ---------- */
function renderCatalog(){
  const cat = PANEL.catalog;
  const info = b => PANEL.experiments[b] ? PANEL.experiments[b] : null;
  const pin = (title, batch) => {
    if(!batch) return '';
    const e = info(batch);
    const src = e || (PANEL.source_batches.find(x=>x.batch===batch)||{});
    const label = e ? e.label : (src.label || batch);
    const pr = e ? (e.protocol||{}) : {};
    const dims = e ? `${e.months.length} 月 × ${pr.n_per_month||'?'} 人 × ${e.repeats.length||'?'} 遍` :
                     (src.status==='skipped_old_contract' ? '旧契约未接入' : '未接入');
    return `<div class="pin"><div class="t">${title}</div><div class="name"><a href="#exp=${esc(batch)}" data-exp="${esc(batch)}">${esc(label)}</a></div>`+
      `<div style="font-size:12.5px;color:#5c665f">模型 ${esc(pr.model||'未提供')} · ${dims} · ${e?('共同支持 '+e.sections.quality.q9_common_person_months+' 人×月'):''}</div></div>`;
  };
  let html = pin('当前参考实验', cat.reference_batch) + pin('最近完成实验', cat.latest_batch);
  html = `<div class="pinned">${html}</div>`;
  for(const g of cat.groups){
    const rows = g.entries.map(e=>{
      const live = info(e.batch);
      const dims = live ? `${e.months} 月 × ${e.n_per_month||'?'} 人 × ${e.repeats} 遍` : `${e.months||'?'} 月（未接入）`;
      const link = live ? `<a href="#exp=${esc(e.batch)}" data-exp="${esc(e.batch)}">${esc(e.label)}</a>`
                        : esc(e.label);
      const parent = e.parent_label ? esc(e.parent_label) : (e.parent ? '父批次未在扫描中' : '—');
      const state = e.status==='ok' ? `${e.run_status} · ${e.evidence_stage}` : '未接入';
      return `<tr><td class="l">${link}${e.registered?'':'<span class="badge">未登记</span>'}${e.status!=='ok'?'<span class="badge">未接入</span>':''}</td>`+
        `<td class="l">${esc(e.mechanism_group)}</td><td class="l">${parent}</td><td class="l">${esc(e.model||'未提供')}</td>`+
        `<td class="l">${dims}</td><td class="l">${state}</td><td class="l" style="white-space:normal">${esc(e.note||'')}</td></tr>`;
    });
    html += `<div class="catgroup"><h3>${esc(g.section)}</h3>`+
      table(['实验','机制组','父批次','模型','规模','状态','说明'], rows)+'</div>';
  }
  html += `<div class="note">· ${esc(cat.note)}</div>`;
  $('catalog').innerHTML = `<h2>实验目录</h2>` + html;
  document.querySelectorAll('#catalog a[data-exp]').forEach(a=>{
    a.addEventListener('click', ev=>{ ev.preventDefault(); selectExperiment(a.getAttribute('data-exp')); });
  });
}

/* ---------- sections ---------- */
function renderOverview(){
  const o = sec('overview');
  let html='';
  if(cur.q==='q9'){
    const rows=Object.entries(o.q9).map(([arm,r])=>{
      const p=r.persistence;
      const diff = (p && _f(p.center_mae_pp) && _f(r.center_mae_pp)) ? p.center_mae_pp - r.center_mae_pp : null;
      return `<tr><td class="l"><b>${esc(arm)}</b></td><td>${r.n_person_months}</td><td>${r.unique_persons}</td><td>${r.n_cells}</td>`+
        td(r.ess,1)+td(r.max_weight_share,4)+
        `<td><b>${fmt(r.center_mae_pp)}</b></td>`+td(r.center_rmse_pp)+td(r.center_bias_pp)+
        td(r.person_mae_pp)+td(r.person_abs_error_median_pp)+
        td(r.w1_pp)+td(r.centered_w1_pp)+
        td(r.pred_median_pp)+td(r.truth_median_pp)+td(r.pred_iqr_pp)+td(r.truth_iqr_pp)+
        (p?td(p.center_mae_pp)+td(diff)+`<td>${p.n_identical_support}</td>`
          :'<td colspan="3" style="text-align:center;color:#9aa39b">未提供</td>')+'</tr>';
    });
    html += '<div class="card"><h3>Q9：主统计量与分布指标（逐月×逐遍计算，等权平均）</h3>'+
      table(['arm','n(人×月)','独立人数','月×遍格','ESS','最大权重份额','群体中位数MAE(主)','中心RMSE','中心带符号偏差','个人MAE','个人绝对误差中位数','跨人W1','去心W1','模型中位','真人中位','模型IQR','真人IQR','照抄中心MAE','照抄−模型(中心)','同支持n'],rows)+
      '<div class="note">照抄上期（persistence）用本人上期预期当预测，只在模型与照抄完全相同的人×月支持上计算；“照抄−模型”为正表示模型优于照抄。权重口径：'+esc(exp().weight_field||'未提供')+'；支持口径：全部所选臂×遍共同支持。</div></div>';
    if(o.support_sensitivity && Object.keys(o.support_sensitivity).length){
      const srows=Object.entries(o.support_sensitivity).map(([arm,s])=>
        `<tr><td class="l"><b>${esc(arm)}</b></td><td>${s.n_person_months}</td><td>${s.unique_persons}</td><td>${fmt(s.ess,1)}</td><td>${s.months_covered.length}</td><td>${fmt(s.max_weight_share,4)}</td></tr>`);
      html += '<div class="card"><h3>敏感性：各臂可用支持（该臂全部遍可评，不与其余臂取交）</h3>'+
        table(['arm','可用 n(人×月)','独立人数','ESS','覆盖月','最大权重份额'],srows)+'</div>';
    }
  } else {
    const rows=Object.entries(o.q8).map(([arm,c])=>{
      if(!c || c.display_class==='coverage' && !c.person_mae_pp) return `<tr><td class="l"><b>${esc(arm)}</b></td><td>${c.n_person_months||0}</td><td colspan="7" class="sup">n 不足</td></tr>`;
      return `<tr><td class="l"><b>${esc(arm)}</b></td><td>${c.n_person_months}</td><td>${c.unique_persons}</td>`+
        td(c.ess,1)+td(c.center_mae_pp)+td(c.center_bias_pp)+td(c.person_mae_pp)+td(c.person_abs_error_median_pp)+
        td(c.pred_median_pp)+td(c.truth_median_pp)+
        '<td style="text-align:center;color:#9aa39b">未提供</td></tr>';
    });
    html += '<div class="card"><h3>Q8：点值简表（独立支持，不被 Q9 失败连带丢弃）</h3>'+
      table(['arm','n(人×月)','独立人数','ESS','群体中位数MAE','中心带符号偏差','个人MAE','个人绝对误差中位数','模型中位','真人中位','照抄上期'],rows)+
      '<div class="note">本适配器未接入上期 Q8 存档，照抄基线对 Q8 未提供。</div></div>';
  }
  $('body-1').innerHTML = html + (o.notes||[]).map(n=>`<div class="note">· ${esc(n)}</div>`).join('');
}
const _f = v => typeof v === 'number' && isFinite(v);

function renderMonthly(){
  const m = sec('monthly'), arm = cur.arm;
  const block = m[arm];
  if(!block){ $('body-2').innerHTML='<div class="note">未提供</div>'; return; }
  // per-month display values average the repeat cells
  const byMonth = {};
  block.rows.forEach(r=>{ (byMonth[r.month] = byMonth[r.month] || []).push(r); });
  const months = Object.keys(byMonth).map(Number).sort((a,b)=>a-b);
  const mval = (month, key) => {
    const vals = byMonth[month].map(r=>r[key]).filter(_f);
    return vals.length ? vals.reduce((a,b)=>a+b,0)/vals.length : null;
  };
  const rows=block.rows.map(r=>{
    const cls = r.regime==='drastic' ? ' class="drastic"' : '';
    return `<tr${cls}><td class="l">${r.month}</td><td>${r.repeat}</td><td>${r.regime==='drastic'?'剧烈':(r.regime==='calm'?'平稳':'未知')}</td>`+
      `<td>${r.n}</td><td>${fmt(r.ess,1)}</td>`+
      td(r.truth_median_pp)+td(r.model_median_pp)+td(r.persist_median_pp)+
      td(r.model_center_mae_pp)+td(r.persist_center_mae_pp)+
      td(r.model_person_mae_pp)+td(r.persist_person_mae_pp)+td(r.w1_pp)+'</tr>';
  });
  const labels=months.map(m=>String(m).replace(/(\d{4})(\d{2})/,'$1-$2'));
  const med=lineChart([
    {name:'真人中位', color:C.truth, values:months.map(mo=>mval(mo,'truth_median_pp'))},
    {name:'模型中位', color:C.model, values:months.map(mo=>mval(mo,'model_median_pp'))},
    {name:'照抄中位', color:C.persist, values:months.map(mo=>mval(mo,'persist_median_pp'))},
  ], labels);
  const mae=groupedBars(months.map(mo=>({label:String(mo).slice(2),
    values:[mval(mo,'model_center_mae_pp'), mval(mo,'persist_center_mae_pp')]})), ['模型','照抄'], [C.model, C.persist]);
  const t=block.regime_table;
  const regimeRows=[['平稳',t.calm],['剧烈',t.drastic]].map(([lb,g])=>
    `<tr><td class="l">${lb}</td><td>${g.n_cells}</td>${td(g.model_center_mae_pp)}${td(g.persist_center_mae_pp)}${td(g.model_person_mae_pp)}${td(g.persist_person_mae_pp)}</tr>`);
  let html='<div class="card"><h3>逐月中位（绿=真人，蓝=模型，灰=照抄上期；非连续月份不暗示中间月份有模拟）</h3>'+
    legend([[C.truth,'真人中位'],[C.model,'模型中位'],[C.persist,'照抄中位']])+med+'</div>';
  html+='<div class="card"><h3>逐月群体中位数MAE：模型 vs 照抄（黄色底纹=剧烈月）</h3>'+
    legend([[C.model,'模型'],[C.persist,'照抄']])+mae+'</div>';
  html+='<div class="card"><h3>机制月 2×2（逐月×逐遍格等权平均）</h3>'+
    table(['机制月','格数','模型中心MAE(主)','照抄中心MAE','模型个人MAE','照抄个人MAE'],regimeRows)+
    `<div class="note">剧烈月技能值 S（中心口径，主）= 照抄−模型 = <b>${fmt(block.skill_s_center_pp)}</b> pp；S（个人MAE口径，并列参考）= <b>${fmt(block.skill_s_person_pp)}</b> pp。S>0 表示模型优于照抄。</div></div>`;
  html+='<div class="card"><h3>逐月×逐遍明细表</h3>'+
    table(['月份','遍','机制','n','ESS','真人中位','模型中位','照抄中位','模型中心MAE','照抄中心MAE','模型个人MAE','照抄个人MAE','跨人W1'],rows)+'</div>';
  html+=(block.notes||[]).map(n=>`<div class="note">· ${esc(n)}</div>`).join('');
  $('body-2').innerHTML=html;
}

function renderGrid(){
  const g=sec('grid'), arm=cur.arm;
  const dims=g[arm]||{};
  let html='';
  const cellRow=(label,c)=>{
    const head=`<td class="l">${esc(label)}</td><td>${c.n}</td><td>${c.unique_persons}</td><td>${fmt(c.ess,1)}</td>`+
      `<td>${c.months_reportable}/${c.months_covered}</td><td>${c.min_month_n}</td>`;
    if(c.display_class==='coverage')
      return `<tr class="sup">${head}<td colspan="6" class="sup">n 不足（仅覆盖）</td></tr>`;
    const cls = c.display_class==='exploratory' ? ' class="explor"' : (c.display_class==='weak_ess' ? ' class="weakess"' : '');
    const flag = c.display_class==='weak_ess' ? ' ⚠' : '';
    return `<tr${cls}>${head}`+
      td(c.person_mae_pp)+td(c.persist_person_mae_pp)+td(c.center_mae_pp)+td(c.bias_pp)+td(c.w1_pp)+
      `<td>${CLASS_CN[c.display_class]||''}${flag}</td></tr>`;
  };
  for(const [dim,title] of [['six_cell','六格网格（学历×在职）'],['age_group','年龄切片'],['household_income_band','家庭收入切片'],['numeracy','数理切片'],['region','地区切片'],['housing_tenure','住房切片']]){
    const cells=dims[dim]||{};
    const entries=Object.entries(cells);
    if(!entries.length){ html+=`<div class="card"><h3>${title}</h3><div class="note">未提供</div></div>`; continue; }
    html+=`<div class="card"><h3>${title}</h3>`+
      table(['组','n(人×月)','独立人数','ESS','可报月/覆盖月','月内最小n','个人MAE','照抄个人MAE','群体中位数MAE','中心带符号偏差','跨人W1','展示等级'],
        entries.map(([k,c])=>cellRow(c.label_cn||k,c)))+'</div>';
  }
  html+='<div class="note">· 各格为跨月混合分布（非月内异质性）：按月×遍计算后等权平均；覆盖与月内最小 n 随格显示，不用全年人数掩盖月内缺口。</div>';
  $('body-3').innerHTML=html;
}

function renderPriors(){
  const p=sec('priors'), arm=cur.arm;
  const block=p[arm];
  if(!block){ $('body-4').innerHTML='<div class="note">未提供</div>'; return; }
  const rowsOf=obj=>Object.values(obj).map(c=>{
    const head=`<td class="l">${esc(c.label_cn)}</td><td>${c.n}</td><td>${fmt(c.ess,1)}</td>`;
    if(c.display_class==='coverage' && !_f(c.person_mae_pp))
      return `<tr class="sup">${head}<td colspan="9" class="sup">n 不足（仅覆盖）</td></tr>`;
    return `<tr>${head}${td(c.prior_mean_pp)}${td(c.truth_mean_pp)}${td(c.model_mean_pp)}`+
      td(c.center_mae_pp)+td(c.person_mae_pp)+td(c.persist_person_mae_pp)+td(c.bias_pp)+td(c.w1_pp)+td(c.delta_w1_pp)+'</tr>';
  });
  let html='<div class="card"><h3>按上期真人预期四档（前置特征分组）</h3>'+
    table(['上期预期档','n','ESS','先验均值','真人均值','模型均值','群体中位数MAE','个人MAE','照抄个人MAE','中心带符号偏差','跨人W1','Δ分布W1'],rowsOf(block.bands))+'</div>';
  html+='<div class="card"><h3>按真人本期变化方向（事后诊断，仅用于评价）</h3>'+
    table(['真人本期','n','ESS','先验均值','真人均值','模型均值','群体中位数MAE','个人MAE','照抄个人MAE','中心带符号偏差','跨人W1','Δ分布W1'],rowsOf(block.directions))+'</div>';
  html+=(block.notes||[]).map(n=>`<div class="note">· ${esc(n)}</div>`).join('');
  $('body-4').innerHTML=html;
}

function renderStructure(){
  const s=sec('structure'), arm=cur.arm;
  const block=s[arm];
  if(!block){ $('body-5').innerHTML='<div class="note">未提供</div>'; return; }
  const cp=block.cross_person;
  let html='<div class="bigrow">'+
    `<div class="stat"><div class="v g">${fmt(cp.truth_std_pp)}<span style="font-size:13px">pp</span></div><div class="k">真人跨人 std</div></div>`+
    `<div class="stat"><div class="v n">${fmt(cp.model_std_pp)}<span style="font-size:13px">pp</span></div><div class="k">模型跨人 std</div></div>`+
    `<div class="stat"><div class="v g">${fmt(cp.truth_iqr_pp)}</div><div class="k">真人跨人 IQR</div></div>`+
    `<div class="stat"><div class="v n">${fmt(cp.model_iqr_pp)}</div><div class="k">模型跨人 IQR</div></div></div>`;
  if(cp.note) html+=`<div class="note">· ${esc(cp.note)}</div>`;
  const sh=(title,key)=>{
    const a=(block.model_shape||{})[key], b=(block.truth_shape||{})[key];
    if(!a && !b) return `<div class="card"><h3>${title}</h3><div class="note">未提供</div></div>`;
    return `<div class="card"><h3>${title}（跨月混合分布）</h3>${legend([[C.model,'模型'],[C.truth,'真人']])}`+
      histBars(a,b||a,'模型','真人')+
      `<div class="note">n：模型 ${(block.model_shape||{}).n}，真人 ${(block.truth_shape||{}).n}；零通缩概率占比：模型 ${fmt((block.model_shape||{}).zero_deflation_share,3)}，真人 ${fmt((block.truth_shape||{}).zero_deflation_share,3)}；十档全零占比：模型 ${fmt((block.model_shape||{}).all_zero_share,3)}，真人 ${fmt((block.truth_shape||{}).all_zero_share,3)}</div></div>`;
  };
  html+=sh('十档形状特征：非零档数分布','nz_bins');
  html+=sh('十档形状特征：最大档概率分布（%）','max_prob');
  html+=sh('十档形状特征：概率为 5 的倍数占比分布','mult5_share');
  const r=block.repeats;
  if(r){
    const neg = r.noise_adjusted_negative ? '；噪声扣除后人际方差为负：人与人之间的差别小于重复采样波动，保留该负估计，不截为零。' : '';
    html+='<div class="card"><h3>重复生成方差分解（'+esc(r.repeat_label)+'，等权人）</h3><div class="bigrow">'+
      `<div class="stat"><div class="v n">${fmt(r.within_person_repeat_variance_pp2,3)}</div><div class="k">人内重复方差(pp²)</div></div>`+
      `<div class="stat"><div class="v">${fmt(r.between_person_repeat_mean_variance_pp2,3)}</div><div class="k">重复均值的人际方差(pp²)</div></div>`+
      `<div class="stat"><div class="v">${fmt(r.noise_adjusted_between_variance_pp2,3)}</div><div class="k">扣除人内/R 后(pp²)</div></div></div>`+
      `<div class="note">n=${r.n_persons} 人×月，${r.n_months} 个月，R=${r.repeats}。${esc(r.note)}${neg}</div></div>`;
  } else {
    html+='<div class="card"><h3>重复生成方差分解</h3><div class="note">未提供（无同一人完整多遍支持）</div></div>';
  }
  $('body-5').innerHTML=html;
}

function renderQuality(){
  const q=sec('quality');
  const arms=q.arms||{};
  const rows=Object.entries(arms).map(([arm,a])=>`<tr><td class="l"><b>${esc(arm)}</b></td><td>${a.n_records}</td><td>${a.n_scorable}</td><td>${fmt(a.missing_share,4)}</td><td class="l">${esc(Object.entries(a.scorer_status).map(([k,v])=>k+':'+v).join('，')||'未提供')}</td><td>${fmt(a.normalization_applied_share,4)}</td><td>${a.weight_missing}</td><td>${fmt(a.q8_truth_coverage,3)}</td><td>${fmt(a.q8_model_coverage,3)}</td><td>${a.q9_usable_person_months!==undefined?a.q9_usable_person_months:'未提供'}</td></tr>`);
  const pr=q.protocol||{};
  const meta=(k,v)=>`<span><b>${k}</b>：${v===null||v===undefined?'<span style="color:#9aa39b">未提供</span>':esc(Array.isArray(v)?v.join('、'):v)}</span>`;
  const cost = pr.estimated_cost_usd!==undefined&&pr.estimated_cost_usd!==null
      ? (typeof pr.estimated_cost_usd==='number'?pr.estimated_cost_usd.toFixed(2)+' USD':esc(pr.estimated_cost_usd))
      : '未接入';
  let html='<div class="card"><h3>支持口径</h3><div style="font-size:13.5px;display:flex;gap:8px 22px;flex-wrap:wrap">'+
    `<span><b>Q9 共同支持</b>：${q.q9_common_person_months} 人×月</span>`+
    `<span><b>Q8 共同支持</b>：${q.q8_common_person_months} 人×月（独立取支持）</span>`+
    (q.support_note?`<span style="color:#a4453a">${esc(q.support_note)}</span>`:'')+'</div></div>';
  html+='<div class="card"><h3>每实验组数据质量</h3>'+
    table(['arm','记录数','可评分','缺失率','scorer_status 计数','归一化比例','权重缺失','Q8真值覆盖','Q8模型覆盖','臂可用n(人×月)'],rows)+'</div>';
  html+='<div class="card"><h3>协议与运行元数据（来自 summary.json）</h3><div style="display:flex;flex-wrap:wrap;gap:8px 22px;font-size:13.5px">'+
    meta('模型',pr.model)+meta('官方标识',pr.official_advertised_version)+meta('温度',pr.temperature)+
    meta('协议',pr.id)+meta('研究线',pr.research_line)+meta('月数/人数',(pr.months?pr.months.length:'未提供')+' 月 × '+(pr.n_per_month||'未提供'))+
    meta('状态',pr.batch_status)+`<span><b>费用</b>：${cost}</span>`+
    `<span><b>证据阶段</b>：${esc((exp().registry||{}).evidence_stage||'未登记')}</span>`+
    `<span><b>运行状态</b>：${esc((exp().registry||{}).run_status||'未登记')}</span></div></div>`;
  const batches=PANEL.source_batches.map(b=>`<tr><td class="l">${esc(b.batch)}</td><td class="l">${esc(b.label)}${b.registered?'':'（未登记）'}</td><td>${esc(b.status==='ok'?'已接入':'未接入')}</td><td class="l">${esc(b.skip_reason||'—')}</td><td>${b.n_cases}</td></tr>`);
  html+='<div class="card"><h3>批次清单（自动发现 outputs/*_evaluation_*）</h3>'+
    table(['批次','显示名','状态','原因','cases 数'],batches)+'</div>';
  html+='<div class="note">· 跨组/跨批比较先看月份集合、人数、模型、权重与支持口径是否一致；不一致时只能描述整套配置差异，不按原始均值排榜。</div>';
  $('body-6').innerHTML=html;
}

/* ---------- top bar ---------- */
function renderMeta(){
  const e=exp(), pr=e.protocol||{}, ov=sec('overview');
  const armRow = ov.q9[cur.arm] || Object.values(ov.q9)[0];
  $('meta').innerHTML=
    `<span><b>${esc(e.label)}</b>${e.registered?'':'（未登记）'}</span>`+
    `<span>说明：${esc(e.description)}</span>`+
    `<span>模型：<b>${esc(pr.model||'未提供')}</b>${pr.temperature!==undefined?'（T='+esc(pr.temperature)+'）':''}</span>`+
    `<span>月份：${e.months.length} 个（${e.months[0]}–${e.months[e.months.length-1]}，非连续）</span>`+
    `<span>arms：${e.arms.length} · 遍数：${e.repeats.length}</span>`+
    (armRow?`<span>共同支持：<b>${armRow.n_person_months} 人×月</b> · ESS ${fmt(armRow.ess,1)} · 独立人数 ${armRow.unique_persons}</span>`:'')+
    `<span>权重：${esc(e.weight_field||'未提供')}</span>`;
}
function renderAll(){
  renderMeta();
  renderOverview(); renderMonthly(); renderGrid(); renderPriors(); renderStructure(); renderQuality();
}
function selectExperiment(batch){
  if(!PANEL.experiments[batch]) return;
  cur.exp = batch;
  $('selExp').value = batch;
  fillArms();
  renderAll();
  if(('#exp='+batch) !== location.hash) history.replaceState(null,'','#exp='+batch);
  $('toolbar').scrollIntoView({behavior:'smooth'});
}
function init(){
  $('notice').textContent=PANEL.comparability_notice;
  $('genat').textContent=PANEL.generated_at_utc.slice(0,19).replace('T',' ');
  ['overview','monthly','grid','priors','structure','quality'].forEach(n=>{
    $('guide-'+({overview:1,monthly:2,grid:3,priors:4,structure:5,quality:6}[n])).textContent=PANEL.section_guides[n];
  });
  renderCatalog();
  const sel=$('selExp');
  expKeys().forEach(k=>{const e=PANEL.experiments[k];const o=document.createElement('option');
    o.value=k;o.textContent=e.label+'（'+k+'）';sel.appendChild(o);});
  cur.exp=expKeys()[0];
  if(location.hash.startsWith('#exp=') && PANEL.experiments[location.hash.slice(5)])
    cur.exp = location.hash.slice(5);
  sel.value=cur.exp;
  sel.onchange=()=>{cur.exp=sel.value; if(('#exp='+cur.exp)!==location.hash) history.replaceState(null,'','#exp='+cur.exp); fillArms(); renderAll();};
  $('btnQ9').onclick=()=>{cur.q='q9';$('btnQ9').classList.add('on');$('btnQ8').classList.remove('on');renderOverview();};
  $('btnQ8').onclick=()=>{ if(!exp().q8_available) return; cur.q='q8';$('btnQ8').classList.add('on');$('btnQ9').classList.remove('on');renderOverview();};
  fillArms();
  $('selArm').onchange=()=>{cur.arm=$('selArm').value;renderAll();};
  window.addEventListener('hashchange',()=>{
    if(location.hash.startsWith('#exp=')) selectExperiment(location.hash.slice(5));
  });
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
