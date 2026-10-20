"""Render the aggregated panel JSON into a self-contained interactive HTML.

Single file: embedded CSS + aggregated JSON + vanilla JS drawing inline SVG.
No CDN, no server, file:// works. Only aggregate data is embedded; person
identifiers and raw ten-bin vectors never leave the aggregation layer. The
front end only reads aggregates, switches tabs and draws; every number is
computed in Python (sections.py).

Visual conventions (experiment_panel_v1_plan.md section 2):
- fixed role styles: truth #202733 solid square; reference/control #0072B2
  solid circle; candidate #D55E00 solid triangle; persistence baseline
  #6B7280 dashed diamond. Color, dash and marker are redundant encodings so
  the charts survive grayscale printing and color-blind readers.
- signed values use a zero-centred diverging scale; non-negative distances
  use a single-hue scale. Improvements always carry number + direction +
  metric name, never bare red/green.
- Chinese in Kaiti, latin/digits in Times New Roman; tables right-align
  numbers with tabular figures; axes, units, legends and titles all shown.
"""
from __future__ import annotations

import json

# Role styles shared by every chart; tested in tests/test_sce_experiment_panel.py
ROLE_STYLES = {
    'truth': {'label': '真人', 'color': '#202733', 'dash': '', 'marker': 'square'},
    'ref': {'label': '参考配置', 'color': '#0072B2', 'dash': '', 'marker': 'circle'},
    'cand': {'label': '候选配置', 'color': '#D55E00', 'dash': '', 'marker': 'triangle'},
    'base': {'label': '持续性基线', 'color': '#6B7280', 'dash': '6,3', 'marker': 'diamond'},
}

TABS = (
    ('overview', '结果概览'),
    ('monthly', '月份与人群'),
    ('priors', '先验与回答结构'),
    ('inputs', '输入与配置'),
    ('quality', '质量与复现'),
)

_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>SCE 实验分析面板 v1</title>
<style>
:root { --bg:#fbf9f3; --card:#ffffff; --ink:#22312a; --green:#1d4d3b;
        --navy:#23405f; --grey:#8a8f87; --line:#ddd6c6; --warn:#9aa39b; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
       font:15px/1.65 "Times New Roman","Kaiti SC","STKaiti",serif;
       font-variant-numeric: tabular-nums; }
h1,h2,h3,.serif { font-family:"Times New Roman","Kaiti SC","STKaiti",serif; }
header { background:var(--green); color:#f4f1e6; padding:20px 34px 12px; }
header h1 { margin:0 0 2px; font-size:25px; letter-spacing:1px; }
header .sub { font-size:13px; opacity:.85; }
.notice { background:#efe7d2; border-bottom:1px solid var(--line);
          padding:8px 34px; font-size:13.5px; color:#5c4f2a; }
.toolbar { display:flex; gap:16px; flex-wrap:wrap; align-items:center;
           padding:12px 34px; background:var(--card);
           border-bottom:1px solid var(--line); position:sticky; top:0; z-index:6; }
.toolbar label { font-size:12.5px; color:var(--grey); display:block; }
.toolbar select,.toolbar button { font-size:14px; padding:4px 8px; font-family:inherit;
           border:1px solid var(--line); border-radius:4px; background:#fff; color:var(--ink); }
.toolbar .qbtns button { cursor:pointer; }
.toolbar .qbtns button.on { background:var(--green); color:#fff; border-color:var(--green); }
.toolbar .qbtns button:disabled { opacity:.45; cursor:not-allowed; }
.toolbar a { font-size:13px; color:var(--navy); }
.tabbar { display:flex; gap:4px; flex-wrap:wrap; padding:8px 34px 0;
          background:var(--card); border-bottom:2px solid var(--green); }
.tabbar button { border:1px solid var(--line); border-bottom:none; border-radius:6px 6px 0 0;
                 background:#f2efe6; color:#4a554e; padding:7px 16px; font-size:14.5px;
                 cursor:pointer; font-family:inherit; }
.tabbar button.on { background:var(--green); color:#fff; border-color:var(--green); }
.metabar { display:flex; gap:8px 20px; flex-wrap:wrap; padding:9px 34px; font-size:13px;
           background:var(--card); border-bottom:1px solid var(--line); color:#4a554e; }
.metabar b { color:var(--ink); }
.metabar details { width:100%; font-size:12.5px; color:#5c665f; }
main { padding:10px 34px 60px; max-width:1180px; }
section { margin:20px 0; }
section>h2 { font-size:20px; border-left:5px solid var(--green);
             padding-left:10px; margin-bottom:4px; }
.guide { font-size:13.5px; color:#5c665f; background:var(--card);
         border:1px solid var(--line); border-radius:6px; padding:8px 12px; margin:8px 0 14px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:8px;
        padding:14px 16px; margin:12px 0; overflow-x:auto; }
.card h3 { margin:2px 0 10px; font-size:16.5px; color:var(--navy); }
table { border-collapse:collapse; font-size:13.5px; width:100%; }
th,td { border:1px solid var(--line); padding:5px 9px; text-align:right; white-space:nowrap; }
th { background:#efeadb; font-weight:600; }
td.l,th.l { text-align:left; }
tr.drastic td { background:#f3ecd6; }
td.sup,tr.sup td { color:var(--warn); background:#f2f0ea; text-align:center; }
tr.explor td,td.explor { background:#eef0ea; color:#5c665f; }
tr.weakess td:first-child { border-left:4px solid #c9a227; }
.banners { font-size:13px; color:#7a5a20; background:#f6efdd; border:1px solid #e2d5ae;
           border-radius:6px; padding:8px 12px; margin:10px 0; }
.bigrow { display:flex; gap:14px; flex-wrap:wrap; margin:10px 0; }
.stat { background:var(--card); border:1px solid var(--line); border-radius:8px;
        padding:12px 18px; min-width:200px; flex:1; }
.stat .v { font-size:24px; font-weight:bold; }
.stat .k { font-size:12.5px; color:var(--grey); }
.stat .sub2 { font-size:13px; color:#4a554e; margin-top:2px; }
.stat .good { color:#1d4d3b; } .stat .bad { color:#8a4a12; }
.note { font-size:12.5px; color:#6b7268; margin:6px 0; }
.legend { font-size:12.5px; margin:4px 0; display:flex; gap:14px; flex-wrap:wrap; }
.legend .item { cursor:pointer; user-select:none; color:#4a554e; }
.legend .item.off { opacity:.35; text-decoration:line-through; }
.fact { background:var(--card); border:1px solid var(--line); border-left:5px solid var(--navy);
        border-radius:6px; padding:8px 14px; margin:8px 0; }
.fact summary { cursor:pointer; font-size:14.5px; }
.fact .evidence { margin-top:6px; font-size:13px; }
/* catalog */
.catalog { padding:14px 34px 4px; }
.catalog h2 { font-size:20px; margin:6px 0; }
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
@media (max-width: 720px) {
  header,.notice,.toolbar,.tabbar,.metabar,.catalog,main,footer { padding-left:14px; padding-right:14px; }
  .stat { min-width:150px; }
}
@media print {
  .toolbar,.tabbar,.catalog,.legend { display:none; }
  * { -webkit-print-color-adjust:exact; print-color-adjust:exact; }
}
</style>
</head>
<body>
<header>
  <h1>SCE 实验分析面板 <span style="font-size:14px">v1 · 离线 · 零 API</span></h1>
  <div class="sub">美国 SCE 一年期通胀预期（赛道 A）· 实验目录＋单实验页签视图 · 聚合数据自包含 HTML · 生成于 <span id="genat"></span></div>
</header>
<div class="notice" id="notice"></div>
<div class="catalog" id="catalog"></div>
<div class="toolbar" id="toolbar">
  <a href="#catalog" id="lnkCatalog">☰ 实验目录</a>
  <div><label>实验批次</label><select id="selExp"></select></div>
  <div><label>候选 arm（对照：<span id="ctlName"></span>）</label><select id="selArm"></select></div>
  <div><label>题目</label><div class="qbtns" style="display:flex;gap:6px">
    <button id="btnQ9" class="on">Q9 分布</button><button id="btnQ8">Q8 简表</button>
  </div></div>
  <div id="q8warn" style="font-size:12.5px;color:#a4453a;display:none">该批次 Q8 无可对照数据，已禁用。</div>
</div>
<div class="tabbar" id="tabbar"></div>
<div class="metabar" id="metabar"></div>
<main id="main"></main>
<footer><div>本页仅嵌聚合指标（n/ESS/分位数/W1/直方图桶/CDF），不含 userid、agent_id、逐人记录或原始十档向量；缺失与未提供一律显示“未提供”，不填零。图表以颜色＋线型＋标记三重区分，灰阶打印仍可辨认。</div>
<div style="margin-top:4px">更新流程（离线、零 API）：实验结束/停止且评价缓存产出后，运行 <code>scripts/build_sce_experiment_panel.py</code> 一条命令重建本面板与私有中间文件（留在 outputs/，不入库）；运行中只看技术进度与费用，不看真值调参。</div></footer>
<script id="panel-data" type="application/json">__PANEL_JSON__</script>
<script>
const ROLES = __ROLE_JSON__;
const TABS = __TABS_JSON__;
const PANEL = JSON.parse(document.getElementById('panel-data').textContent);
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const fmt = (v, d=2) => (v === null || v === undefined || Number.isNaN(v)) ? '<span style="color:#9aa39b">未提供</span>' : (typeof v === 'number' ? v.toFixed(d) : esc(v));
const _f = v => typeof v === 'number' && isFinite(v);
const yfmt = m => String(m).replace(/(\\d{4})(\\d{2})/, '$1-$2');

let cur = {exp:null, arm:null, tab:'overview', q:'q9'};
let hiddenSeries = {};
let catalogScroll = 0;

function expKeys(){ return Object.keys(PANEL.experiments); }
function exp(){ return PANEL.experiments[cur.exp]; }
function sec(name){ return exp().sections[name]; }
function controlArm(){ return exp().control_arm; }
function monthlyBlock(arm){ return sec('monthly')[arm] || {rows:[]}; }

/* ---------- table helper ---------- */
function table(headers, rows){
  let h = '<table><thead><tr>' + headers.map(x => Array.isArray(x)
    ? `<th class="${x[1]||''}">${x[0]}</th>` : `<th>${x}</th>`).join('') + '</tr></thead><tbody>';
  return h + rows.join('') + '</tbody></table>';
}
const td = (v,d) => `<td>${fmt(v,d)}</td>`;
const CLASS_CN = {coverage:'仅覆盖（n<10）', exploratory:'探索（10≤n<20）', weak_ess:'显示·ESS<10', normal:'正常'};

/* ---------- SVG marker paths ---------- */
function markerPath(kind, x, y, r){
  switch(kind){
    case 'square': return `M${x-r},${y-r} h${2*r} v${2*r} h${-2*r} Z`;
    case 'triangle': return `M${x},${y-r} L${x+r},${y+r} L${x-r},${y+r} Z`;
    case 'diamond': return `M${x},${y-r} L${x+r},${y} L${x},${y+r} L${x-r},${y} Z`;
    default: return `M${x},${y} m${-r},0 a${r},${r} 0 1,0 ${2*r},0 a${r},${r} 0 1,0 ${-2*r},0`;
  }
}

/* ---------- line chart with roles, clickable legend, end labels ---------- */
function lineChart(el, series, opts){
  const W=880,H=280,P={l:56,r:110,t:16,b:40};
  const visible = series.filter(s => !hiddenSeries[s.key]);
  const all = visible.flatMap(s=>s.values.filter(v=>_f(v.y)));
  if(!all.length){ el.innerHTML='<div class="note">无可绘制数据</div>'; return; }
  const labels = opts.labels;
  let yMin=Math.min(...all.map(v=>v.y)), yMax=Math.max(...all.map(v=>v.y));
  if(yMin===yMax){yMin-=1;yMax+=1;}
  const pad=(yMax-yMin)*0.12; yMin-=pad; yMax+=pad;
  const xw=(W-P.l-P.r)/Math.max(1,labels.length-1);
  const X=i=>P.l+i*xw;
  const Y=v=>P.t+(1-(v-yMin)/(yMax-yMin))*(H-P.t-P.b);
  let g='';
  for(let k=0;k<=4;k++){const gy=P.t+k/4*(H-P.t-P.b);
    g+=`<line x1="${P.l}" y1="${gy}" x2="${W-P.r}" y2="${gy}" stroke="#e7e1d2"/>`;
    g+=`<text x="${P.l-6}" y="${gy+4}" font-size="10.5" text-anchor="end" fill="#8a8f87">${(yMax-k/4*(yMax-yMin)).toFixed(1)}</text>`;}
  g+=`<text x="14" y="${P.t+10}" font-size="10.5" fill="#8a8f87">${esc(opts.unit||'pp')}</text>`;
  // non-contiguous month break markers
  const months = opts.months||[];
  for(let i=1;i<months.length;i++){
    const gap=(Math.floor(months[i]/100)-Math.floor(months[i-1]/100))*12+(months[i]%100)-(months[i-1]%100);
    if(gap>1){
      const bx=X(i)-xw/2;
      g+=`<line x1="${bx}" y1="${P.t}" x2="${bx}" y2="${H-P.b}" stroke="#c9bfa4" stroke-dasharray="2,4"/>`;
      g+=`<text x="${bx}" y="${P.t-4}" font-size="10" text-anchor="middle" fill="#a89f86">∥ 非连续</text>`;
    }
  }
  labels.forEach((lb,i)=>{ if(labels.length<=14||i%2===0)
    g+=`<text x="${X(i)}" y="${H-22}" font-size="10.5" text-anchor="middle" fill="#8a8f87">${lb}</text>`;});
  visible.forEach(s=>{
    const st=ROLES[s.role];
    const pts=s.values.map((v,i)=>_f(v.y)?`${X(i)},${Y(v.y)}`:null).filter(Boolean).join(' ');
    if(pts) g+=`<polyline points="${pts}" fill="none" stroke="${st.color}" stroke-width="2.2"${st.dash?` stroke-dasharray="${st.dash}"`:''}/>`;
    s.values.forEach((v,i)=>{ if(_f(v.y)) g+=`<path d="${markerPath(st.marker,X(i),Y(v.y),4)}" fill="${st.color}"><title>${esc(s.name)} ${v.x}: ${v.y.toFixed(2)} ${esc(opts.unit||'pp')}</title></path>`;});
    const last=[...s.values].reverse().find(v=>_f(v.y));
    if(last){ const li=s.values.indexOf(last);
      g+=`<text x="${X(li)+8}" y="${Y(last.y)+4}" font-size="11" fill="${st.color}">${esc(s.short||s.name)}</text>`;}
  });
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px;background:#fff;border:1px solid var(--line);border-radius:6px">${g}</svg>`;
  if(opts.legend!==false){
    const lg=document.createElement('div'); lg.className='legend';
    series.forEach(s=>{
      const st=ROLES[s.role];
      const item=document.createElement('span'); item.className='item'+(hiddenSeries[s.key]?' off':'');
      item.innerHTML=`<span style="color:${st.color}">${st.dash?'╌':'─'}${st.marker==='square'?'■':st.marker==='triangle'?'▲':st.marker==='diamond'?'◆':'●'}</span> ${esc(s.name)}`;
      item.onclick=()=>{ hiddenSeries[s.key]=!hiddenSeries[s.key]; renderTab(); };
      lg.appendChild(item);
    });
    el.appendChild(lg);
  }
}

/* ---------- diverging diff chart (candidate minus control) ---------- */
function diffChart(el, months, diffs, rawA, rawB, names){
  const W=880,H=260,P={l:56,r:20,t:16,b:40};
  const vals=diffs.filter(_f);
  if(!vals.length){ el.innerHTML='<div class="note">无可绘制数据</div>'; return; }
  const mx=Math.max(...vals.map(v=>Math.abs(v)))*1.15||1;
  const slot=(W-P.l-P.r)/months.length, bw=Math.min(34,(slot-10));
  const Y=v=>P.t+(1-(v+mx)/(2*mx))*(H-P.t-P.b);
  const zero=Y(0);
  let g=`<line x1="${P.l}" y1="${zero}" x2="${W-P.r}" y2="${zero}" stroke="#4a554e" stroke-width="1.2"/>`;
  for(let k=-2;k<=2;k++){const v=mx*k/2; if(!_f(v)) continue;
    g+=`<text x="${P.l-6}" y="${Y(v)+4}" font-size="10.5" text-anchor="end" fill="#8a8f87">${v>=0?'+':''}${v.toFixed(1)}</text>`;}
  g+=`<text x="14" y="${P.t+10}" font-size="10.5" fill="#8a8f87">pp</text>`;
  months.forEach((m,i)=>{
    const v=diffs[i];
    const cx=P.l+i*slot+slot/2;
    if(Math.floor(i)>0){}
    if(_f(v)){
      const mag=Math.min(1,Math.abs(v)/mx);
      const col=v>0 ? `rgba(213,94,0,${0.25+0.65*mag})` : `rgba(0,114,178,${0.25+0.65*mag})`;
      const y=Y(Math.max(0,v)), h=Math.abs(Y(v)-zero);
      g+=`<rect x="${cx-bw/2}" y="${y}" width="${bw}" height="${Math.max(h,1.5)}" fill="${col}"><title>${yfmt(m)}：${names[0]}−${names[1]} = ${v>0?'+':''}${v.toFixed(2)}pp（${names[0]} ${rawA[i].toFixed(2)} / ${names[1]} ${rawB[i].toFixed(2)}）</title></rect>`;
      g+=`<text x="${cx}" y="${v>0?Y(v)-4:Y(v)+13}" font-size="10" text-anchor="middle" fill="#4a554e">${v>0?'+':''}${v.toFixed(2)}</text>`;
    }
    if(months.length<=14||i%2===0)
      g+=`<text x="${cx}" y="${H-22}" font-size="10.5" text-anchor="middle" fill="#8a8f87">${yfmt(m).slice(2)}</text>`;
  });
  for(let i=1;i<months.length;i++){
    const gap=(Math.floor(months[i]/100)-Math.floor(months[i-1]/100))*12+(months[i]%100)-(months[i-1]%100);
    if(gap>1){ const bx=P.l+i*slot-slot/2;
      g+=`<line x1="${bx}" y1="${P.t}" x2="${bx}" y2="${H-P.b}" stroke="#c9bfa4" stroke-dasharray="2,4"/>`; }
  }
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px;background:#fff;border:1px solid var(--line);border-radius:6px">${g}</svg>`;
}

/* ---------- drill charts ---------- */
var drillSel = {month:null, dim:null, label:null};
function cdfChart(el, grid, series){
  const W=880,H=280,P={l:56,r:110,t:16,b:40};
  const all=series.flatMap(s=>s.values.filter(_f));
  if(!all.length){ el.innerHTML='<div class="note">无可绘制数据</div>'; return; }
  let yMin=0, yMax=1;
  const xw=(W-P.l-P.r)/Math.max(1,grid.length-1);
  const X=i=>P.l+i*xw, Y=v=>P.t+(1-(v-yMin)/(yMax-yMin))*(H-P.t-P.b);
  let g='';
  for(let k=0;k<=4;k++){const gy=P.t+k/4*(H-P.t-P.b); const val=yMax-k/4;
    g+=`<line x1="${P.l}" y1="${gy}" x2="${W-P.r}" y2="${gy}" stroke="#e7e1d2"/>`;
    g+=`<text x="${P.l-6}" y="${gy+4}" font-size="10.5" text-anchor="end" fill="#8a8f87">${val.toFixed(1)}</text>`;}
  g+=`<text x="14" y="${P.t+10}" font-size="10.5" fill="#8a8f87">累积概率</text>`;
  grid.forEach((gv,i)=>{ if(grid.length<=15||i%2===0) g+=`<text x="${X(i)}" y="${H-22}" font-size="10.5" text-anchor="middle" fill="#8a8f87">${gv}</text>`;});
  g+=`<text x="${(W+P.l-P.r)/2}" y="${H-4}" font-size="10.5" text-anchor="middle" fill="#8a8f87">一年期通胀预期（pp）</text>`;
  series.forEach(sr=>{
    const st=ROLES[sr.role];
    const pts=sr.values.map((v,i)=>_f(v)?`${X(i)},${Y(v)}`:null).filter(Boolean).join(' ');
    if(pts) g+=`<polyline points="${pts}" fill="none" stroke="${st.color}" stroke-width="2.2"${st.dash?` stroke-dasharray="${st.dash}"`:''}/>`;
    sr.values.forEach((v,i)=>{ if(_f(v)) g+=`<path d="${markerPath(st.marker,X(i),Y(v),4)}" fill="${st.color}"><title>${esc(sr.name)} @ ${grid[i]}pp: F=${v.toFixed(3)}</title></path>`;});
    const li=sr.values.length-1;
    if(_f(sr.values[li])) g+=`<text x="${X(li)+8}" y="${Y(sr.values[li])+4}" font-size="11" fill="${st.color}">${esc(sr.short||sr.name)}</text>`;
  });
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px;background:#fff;border:1px solid var(--line);border-radius:6px">${g}</svg>`;
}
function quantileChart(el, rows, unit){
  // rows: [{name, role, q:{p10,p25,p50,p75,p90}, n}]
  const W=880,H=60+rows.length*64,P={l:150,r:30,t:10,b:34};
  const all=rows.flatMap(r=>[r.q.p10,r.q.p90].filter(_f));
  if(!all.length){ el.innerHTML='<div class="note">无可绘制数据</div>'; return; }
  let xMin=Math.min(...all), xMax=Math.max(...all);
  if(xMin===xMax){xMin-=1;xMax+=1;}
  const pad=(xMax-xMin)*0.15; xMin=Math.max(0,xMin-pad); xMax+=pad;
  const X=v=>P.l+(v-xMin)/(xMax-xMin)*(W-P.l-P.r);
  let g='';
  for(let k=0;k<=6;k++){const gv=xMin+k/6*(xMax-xMin);
    g+=`<line x1="${X(gv)}" y1="${P.t}" x2="${X(gv)}" y2="${H-P.b}" stroke="#efe9da"/>`;
    g+=`<text x="${X(gv)}" y="${H-16}" font-size="10.5" text-anchor="middle" fill="#8a8f87">${gv.toFixed(1)}</text>`;}
  g+=`<text x="${(W+P.l-P.r)/2}" y="${H-2}" font-size="10.5" text-anchor="middle" fill="#8a8f87">${esc(unit||'pp')}</text>`;
  rows.forEach((r,i)=>{
    const yc=P.t+34+i*64;
    const st=ROLES[r.role];
    g+=`<text x="${P.l-12}" y="${yc+4}" font-size="12" text-anchor="end" fill="${st.color}">${esc(r.name)}</text>`;
    if(!_f(r.q.p10)) { g+=`<text x="${P.l+8}" y="${yc+4}" font-size="11" fill="#9aa39b">未提供</text>`; return; }
    g+=`<line x1="${X(r.q.p10)}" y1="${yc}" x2="${X(r.q.p90)}" y2="${yc}" stroke="${st.color}" stroke-width="3"${st.dash?` stroke-dasharray="${st.dash}"`:''}/>`;
    g+=`<line x1="${X(r.q.p25)}" y1="${yc-7}" x2="${X(r.q.p75)}" y2="${yc-7}" stroke="${st.color}" stroke-width="8"/>`;
    g+=`<path d="${markerPath('diamond',X(r.q.p50),yc,6)}" fill="${st.color}"/>`;
    g+=`<text x="${X(r.q.p50)}" y="${yc-14}" font-size="10" text-anchor="middle" fill="${st.color}">${r.q.p50.toFixed(2)}</text>`;
    g+=`<text x="${X(r.q.p10)}" y="${yc+16}" font-size="9.5" text-anchor="middle" fill="#8a8f87">P10 ${r.q.p10.toFixed(1)}</text>`;
    g+=`<text x="${X(r.q.p90)}" y="${yc+16}" font-size="9.5" text-anchor="middle" fill="#8a8f87">P90 ${r.q.p90.toFixed(1)}</text>`;
  });
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px;background:#fff;border:1px solid var(--line);border-radius:6px">${g}</svg>`;
}
function varianceChart(el, variance){
  const months=Object.keys(variance).map(Number).sort((a,b)=>a-b);
  const groups=months.map(m=>({label:yfmt(m).slice(2), values:[variance[m].between_cell_var_pp2, variance[m].within_cell_var_pp2]}));
  groupedBars(el, groups, ['格间','格内'], ['#0072B2','#6B7280']);
}

/* ---------- export helpers ---------- */
function downloadText(name, text, mime){
  const blob=new Blob([text], {type:mime||'text/plain;charset=utf-8'});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob); a.download=name;
  document.body.appendChild(a); a.click();
  setTimeout(()=>{URL.revokeObjectURL(a.href); a.remove();}, 0);
}
function exportContainerSVG(container, base){
  const svg=container.querySelector('svg');
  if(!svg) return;
  const text='<?xml version="1.0" encoding="UTF-8"?>\\n'+svg.outerHTML;
  downloadText(base+'.svg', text, 'image/svg+xml');
}
function exportContainerPNG(container, base){
  const svg=container.querySelector('svg');
  if(!svg) return;
  const text='<?xml version="1.0" encoding="UTF-8"?>\\n'+svg.outerHTML;
  const url=URL.createObjectURL(new Blob([text],{type:'image/svg+xml;charset=utf-8'}));
  const img=new Image();
  img.onload=()=>{
    const scale=2;
    const canvas=document.createElement('canvas');
    canvas.width=svg.viewBox.baseVal.width*scale; canvas.height=svg.viewBox.baseVal.height*scale;
    const ctx=canvas.getContext('2d');
    ctx.fillStyle='#ffffff'; ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.drawImage(img,0,0,canvas.width,canvas.height);
    URL.revokeObjectURL(url);
    const a=document.createElement('a');
    a.href=canvas.toDataURL('image/png'); a.download=base+'.png';
    document.body.appendChild(a); a.click(); a.remove();
  };
  img.src=url;
}
function exportButtonsHTML(id){
  return `<div style="margin:4px 0"><button class="xbt" data-x="${id}" data-k="svg">导出 SVG</button> <button class="xbt" data-x="${id}" data-k="png">导出 PNG</button></div>`;
}
function wireExportButtons(scope){
  (scope||document).querySelectorAll('button.xbt').forEach(b=>{
    b.onclick=()=>{
      const el=document.getElementById(b.getAttribute('data-x'));
      if(!el) return;
      const base=(exp().label||'panel').replace(/[\/:*?"<>|\s]+/g,'_')+'_'+b.getAttribute('data-x');
      if(b.getAttribute('data-k')==='svg') exportContainerSVG(el, base); else exportContainerPNG(el, base);
    };
  });
}
function exportLongCSV(){
  const e=exp();
  const head=['experiment','experiment_label','question','month','group','arm','metric','value_pp','n','ess','source'];
  const lines=[head.join(',')];
  const q=(s)=>'"'+String(s).replace(/"/g,'""')+'"';
  const push=(question,month,group,arm,metric,value,n,ess)=>{
    if(!_f(value)) return;
    lines.push([q(e.batch!==undefined?cur.exp:cur.exp),q(e.label),question,month,group,q(arm),metric,value.toFixed(6),
      n===undefined||n===null?'':n, ess===undefined||ess===null?'':(Math.round(ess*10)/10),'panel_aggregate'].join(','));
  };
  const ov=sec('overview');
  Object.entries(ov.q9).forEach(([arm,r])=>{
    push('q9','all','all',arm,'center_mae_pp',r.center_mae_pp,r.n_person_months,r.ess);
    push('q9','all','all',arm,'person_mae_pp',r.person_mae_pp,r.n_person_months,r.ess);
    push('q9','all','all',arm,'w1_pp',r.w1_pp,r.n_person_months,r.ess);
    push('q9','all','all',arm,'pred_iqr_pp',r.pred_iqr_pp,r.n_person_months,r.ess);
    push('q9','all','all',arm,'truth_iqr_pp',r.truth_iqr_pp,r.n_person_months,r.ess);
    if(r.persistence){
      push('q9','all','all',arm,'persist_center_mae_pp',r.persistence.center_mae_pp,r.persistence.n_identical_support,r.persistence.ess);
    }
  });
  const mb=sec('monthly');
  Object.entries(mb).forEach(([arm,block])=>{
    (block.rows||[]).forEach(r=>{
      const mm=yfmt(r.month)+'_r'+r.repeat;
      push('q9',mm,'all',arm,'model_center_mae_pp',r.model_center_mae_pp,r.n,r.ess);
      push('q9',mm,'all',arm,'persist_center_mae_pp',r.persist_center_mae_pp,r.n,r.ess);
      push('q9',mm,'all',arm,'model_median_pp',r.model_median_pp,r.n,r.ess);
      push('q9',mm,'all',arm,'truth_median_pp',r.truth_median_pp,r.n,r.ess);
    });
  });
  downloadText((e.label||'panel').replace(/\s+/g,'_')+'_aggregate_long.csv', '\\ufeff'+lines.join('\\n'), 'text/csv;charset=utf-8');
}

/* ---------- hash routing ---------- */
function parseHash(){
  const h=location.hash.replace(/^#/,'');
  const out={};
  h.split('&').forEach(kv=>{ const [k,v]=kv.split('='); if(k&&v) out[k]=decodeURIComponent(v); });
  return out;
}
function syncHash(){
  const h=`exp=${encodeURIComponent(cur.exp)}&tab=${cur.tab}&q=${cur.q}`;
  if(location.hash.slice(1)!==h) history.replaceState(null,'','#'+h);
}

/* ---------- catalog ---------- */
function renderCatalog(){
  const cat = PANEL.catalog;
  const info = b => PANEL.experiments[b] || null;
  const pin = (title, batch) => {
    if(!batch) return '';
    const e = info(batch);
    const src = PANEL.source_batches.find(x=>x.batch===batch)||{};
    const label = e ? e.label : (src.label || batch);
    const pr = e ? (e.protocol||{}) : {};
    const dims = e ? `${e.months.length} 月 × ${pr.n_per_month||'?'} 人 × ${e.repeats.length||'?'} 遍` :
                     (src.status==='skipped_old_contract' ? '旧契约未接入' : '未接入');
    return `<div class="pin"><div class="t">${title}</div><div class="name"><a href="#exp=${esc(batch)}" data-exp="${esc(batch)}">${esc(label)}</a></div>`+
      `<div style="font-size:12.5px;color:#5c665f">模型 ${esc(pr.model||'未提供')} · ${dims} · ${e?('共同支持 '+e.sections.quality.q9_common_person_months+' 人×月'):''}</div></div>`;
  };
  let html = `<div class="pinned">${pin('当前参考实验', cat.reference_batch) + pin('最近完成实验', cat.latest_batch)}</div>`;
  for(const g of cat.groups){
    const rows = g.entries.map(e=>{
      const live = info(e.batch);
      const dims = live ? `${e.months} 月 × ${e.n_per_month||'?'} 人 × ${e.repeats} 遍` : `${e.months||'?'} 月（未接入）`;
      const link = live ? `<a href="#exp=${esc(e.batch)}" data-exp="${esc(e.batch)}">${esc(e.label)}</a>` : esc(e.label);
      const parent = e.parent_label ? esc(e.parent_label) : (e.parent ? '父批次未在扫描中' : '—');
      const state = e.status==='ok' ? `${e.run_status} · ${e.evidence_stage}` : '未接入';
      return `<tr><td class="l">${link}${e.registered?'':'<span class="badge">未登记</span>'}${e.status!=='ok'?'<span class="badge">未接入</span>':''}</td>`+
        `<td class="l">${esc(e.mechanism_group)}</td><td class="l">${parent}</td><td class="l">${esc(e.model||'未提供')}</td>`+
        `<td class="l">${dims}</td><td class="l">${state}</td><td class="l" style="white-space:normal">${esc(e.note||'')}</td></tr>`;
    });
    html += `<div class="catgroup"><h3>${esc(g.section)}</h3>`+table(['实验','机制组','父批次','模型','规模','状态','说明'], rows)+'</div>';
  }
  html += `<div class="note">· ${esc(cat.note)}</div>`;
  $('catalog').innerHTML = `<h2>实验目录</h2>` + html;
  document.querySelectorAll('#catalog a[data-exp]').forEach(a=>{
    a.addEventListener('click', ev=>{ ev.preventDefault(); catalogScroll=window.scrollY;
      selectExperiment(a.getAttribute('data-exp')); });
  });
}

/* ---------- metabar (fixed top strip of the single-experiment view) ---------- */
function renderMetabar(){
  const e=exp(), pr=e.protocol||{}, ov=sec('overview');
  const armRow = ov.q9[controlArm()] || Object.values(ov.q9)[0];
  const research = pr.research_line || (e.registry||{}).note || '未提供';
  const cfg = [];
  if(pr.configuration) cfg.push(['配置说明', pr.configuration]);
  if(pr.month_selection) cfg.push(['月份选择', pr.month_selection]);
  if(pr.eligibility) cfg.push(['资格口径', pr.eligibility]);
  if(pr.weights) cfg.push(['权重口径', pr.weights]);
  $('metabar').innerHTML=
    `<span>研究任务：<b>${esc(research)}</b></span>`+
    `<span>月份：<b>${e.months.length} 个</b>（${yfmt(e.months[0])}–${yfmt(e.months[e.months.length-1])}，非连续）</span>`+
    `<span>规模：${esc(pr.n_per_month||'?')} 人/月 × ${e.repeats.length} 遍</span>`+
    `<span>模型：<b>${esc(pr.model||'未提供')}</b>${pr.temperature!==undefined?'（T='+esc(pr.temperature)+'）':''}</span>`+
    `<span>比较组：对照 <b>${esc(controlArm())}</b> vs 候选 <b>${esc(cur.arm)}</b></span>`+
    (armRow?`<span>支持口径：<b>${armRow.n_person_months} 人×月</b> 共同支持 · ESS ${fmt(armRow.ess,1)}</span>`:'')+
    (cfg.length?`<details><summary>截止规则与输入版本（展开）</summary><div style="margin-top:4px">${
      cfg.map(([k,v])=>`<div><b>${esc(k)}</b>：${esc(v)}</div>`).join('')}</div></details>`:'');
}

/* ---------- tab: overview ---------- */
function q8banner(msg){
  return `<div class="banners">该区暂不支持 Q8：${esc(msg)}；Q8 简表见「结果概览」页签。</div>`;
}

function renderOverviewTab(main){
  const e=exp(), ov=sec('overview');
  const ctrl=controlArm(), cand=cur.arm;
  if(cur.q==='q8'){
    const rows=Object.entries(ov.q8).map(([arm,c])=>{
      if(!c) return `<tr><td class="l"><b>${esc(arm)}</b></td><td colspan="9" class="sup">未提供</td></tr>`;
      return `<tr><td class="l"><b>${esc(arm)}</b></td><td>${c.n_person_months}</td><td>${c.unique_persons}</td>`+
        td(c.ess,1)+td(c.center_mae_pp)+td(c.center_bias_pp)+td(c.person_mae_pp)+td(c.person_abs_error_median_pp)+
        td(c.w1_pp)+td(c.pred_median_pp)+td(c.truth_median_pp)+'<td style="text-align:center;color:#9aa39b">未提供</td></tr>';
    });
    main.innerHTML = `<section><h2>结果概览 · Q8 点值</h2>
      <div class="guide">Q8 为点值简表：支持口径与 Q9 独立（Q9 失败不连带丢弃合法 Q8）；分布宽度与更新指标不适用于点值，显示“未提供”。</div>
      <div class="card"><h3>Q8：点值指标（独立支持，逐月×逐遍等权平均）</h3>`+
      table(['arm','n(人×月)','独立人数','ESS','群体中位数MAE','中心带符号偏差','个人MAE','个人绝对误差中位数','跨人W1','模型中位','真人中位','照抄上期'],rows)+
      '<div class="note">本适配器未接入上期 Q8 存档，持续性基线对 Q8 未提供。</div></section>';
    return;
  }
  const r=ov.q9[cand], p=(r&&r.persistence)||null;
  const ctrlRow=ov.q9[ctrl];
  // four main readouts
  const diffCenter = (p&&_f(p.center_mae_pp)&&_f(p.model_center_mae_same_support_pp)) ? p.center_mae_pp - p.model_center_mae_same_support_pp : null;
  const diffW1 = (p&&_f(p.w1_pp)&&_f(r.w1_pp)) ? p.w1_pp - r.w1_pp : null;
  const iqrNote = (_f(r.pred_iqr_pp)&&_f(r.truth_iqr_pp)) ? (r.pred_iqr_pp < r.truth_iqr_pp ? '模型分歧窄于真人' : '模型分歧宽于或接近真人') : '';
  const cards = [
    {k:'① 群体中位数MAE（主）', v:r.center_mae_pp, unit:'pp',
     sub:p?`同支持照抄上期 ${fmt(p.center_mae_pp)} pp；照抄−模型 = ${fmt(diffCenter)} pp（${(_f(diffCenter)&&diffCenter>0)?'模型优于照抄':'照抄不劣于模型'}，指标：群体中位数MAE，方向：照抄−模型）`:'同支持照抄上期：未提供'},
    {k:'② 跨人分布W1', v:r.w1_pp, unit:'pp',
     sub:p?`持续性基线 W1 = ${fmt(p.w1_pp)} pp；基线−模型 = ${fmt(diffW1)} pp`:'持续性基线 W1：未提供'},
    {k:'③ 跨人分歧宽度（IQR）', v:r.pred_iqr_pp, unit:'pp',
     sub:`真人 IQR = ${fmt(r.truth_iqr_pp)} pp；${iqrNote}。注意：接近真人 IQR 不单独算成功`},
    {k:'④ 更新分布W1（Δ）', v:r.delta_w1_pp, unit:'pp',
     sub:'模型Δ vs 真人Δ 的分布距离（同支持，逐月×遍等权平均）'},
  ];
  let html=`<section><h2>结果概览</h2>
    <div class="guide">主读数四项：中心误差、分布距离、分歧宽度、更新保真；中心RMSE、个人误差与秩类指标收在下方「更多指标」。所有金额级结论先看共同支持与 ESS。</div>
    <div class="bigrow">`+cards.map(c=>
      `<div class="stat"><div class="k">${esc(c.k)}</div><div class="v">${fmt(c.v)}<span style="font-size:13px">${esc(c.unit)}</span></div><div class="sub2">${c.sub}</div></div>`).join('')+`</div>`;
  // two main charts
  const mb=monthlyBlock(cand), cb=monthlyBlock(ctrl);
  const byMonth=(block,key)=>{ const acc={}; (block.rows||[]).forEach(row=>{ (acc[row.month]=acc[row.month]||[]).push(row[key]); });
    return acc; };
  const months=[...new Set([...(mb.rows||[]).map(r=>r.month), ...(cb.rows||[]).map(r=>r.month)])].sort((a,b)=>a-b);
  const avg=(obj,m)=>{ const v=(obj[m]||[]).filter(_f); return v.length? v.reduce((a,b)=>a+b,0)/v.length : null; };
  const tM=byMonth(mb,'truth_median_pp'), cM=byMonth(mb,'model_median_pp'), pM=byMonth(mb,'persist_median_pp');
  const c2M = cand!==ctrl ? byMonth(cb,'model_median_pp') : null;
  const series=[
    {key:'truth', role:'truth', name:'真人', short:'真人', values:months.map(m=>({x:yfmt(m),y:avg(tM,m)}))},
    {key:'ctrl', role:'ref', name:`对照 ${ctrl}`, short:'对照', values:months.map(m=>({x:yfmt(m),y:avg(c2M||cM,m)}))},
  ];
  if(cand!==ctrl) series.push({key:'cand', role:'cand', name:`候选 ${cand}`, short:'候选', values:months.map(m=>({x:yfmt(m),y:avg(cM,m)}))});
  series.push({key:'base', role:'base', name:'持续性基线（照抄上期）', short:'照抄', values:months.map(m=>({x:yfmt(m),y:avg(pM,m)}))});
  html+=`<div class="card"><h3>逐月中心（单位 pp；∥ 表示月份非连续，中间无模拟）</h3><div id="chart-center"></div></div>`;
  const maeM=byMonth(mb,'model_center_mae_pp'), pmaeM=byMonth(mb,'persist_center_mae_pp'), cmaeM=cand!==ctrl?byMonth(cb,'model_center_mae_pp'):null;
  const diffs=months.map(m=>{ const a=avg(cmaeM||maeM,m), b=avg(cmaeM?maeM:pmaeM,m); return (_f(a)&&_f(b))? a-b : null; });
  const rawA=months.map(m=>avg(cmaeM||maeM,m)), rawB=months.map(m=>avg(cmaeM?maeM:pmaeM,m));
  const dn = cand!==ctrl ? [`候选 ${cand}`,`对照 ${ctrl}`] : [`模型 ${cand}`,'持续性基线'];
  html+=`<div class="card"><h3>逐月误差差额（${esc(dn[0])} − ${esc(dn[1])}，单位 pp；正值=候选更差，悬停看原始误差）</h3><div id="chart-diff"></div></div>`;
  // auto facts
  html+=`<div class="card"><h3>自动事实（固定规则生成，最多三条，无因果解释）</h3>`;
  const facts=e.facts||[];
  if(!facts.length) html+='<div class="note">按现有固定规则没有触发的事实；这不表示实验无特点。</div>';
  facts.forEach(f=>{
    html+=`<details class="fact"><summary>▸ ${esc(f.text)}</summary><div class="evidence">`+
      table(['证据指标','数值(pp)'], (f.evidence||[]).map(ev=>`<tr><td class="l">${esc(ev.metric)}</td>${td(ev.value_pp)}</tr>`))+
      `</div></details>`;
  });
  html+='</div>';
  // more metrics (collapsed)
  const rows=Object.entries(ov.q9).map(([arm,row])=>{
    const pp=row.persistence;
    const dc=(pp&&_f(pp.center_mae_pp)&&_f(pp.model_center_mae_same_support_pp))?pp.center_mae_pp-pp.model_center_mae_same_support_pp:null;
    return `<tr${arm===cand?' style="background:#f6f3e8"':''}><td class="l"><b>${esc(arm)}</b>${arm===ctrl?'（对照）':''}</td><td>${row.n_person_months}</td><td>${row.unique_persons}</td><td>${row.n_cells}</td>`+
      td(row.ess,1)+td(row.max_weight_share,4)+
      td(row.center_mae_pp)+td(row.center_rmse_pp)+td(row.center_bias_pp)+
      td(row.person_mae_pp)+td(row.person_abs_error_median_pp)+
      td(row.w1_pp)+td(row.centered_w1_pp)+td(row.delta_w1_pp)+
      td(row.pred_median_pp)+td(row.truth_median_pp)+td(row.pred_iqr_pp)+td(row.truth_iqr_pp)+
      (pp?td(pp.center_mae_pp)+td(dc)+`<td>${pp.n_identical_support}</td>`
        :'<td colspan="3" style="text-align:center;color:#9aa39b">未提供</td>')+'</tr>';
  });
  const sens=Object.entries(ov.support_sensitivity||{}).map(([arm,s])=>
    `<tr><td class="l"><b>${esc(arm)}</b></td><td>${s.n_person_months}</td><td>${s.unique_persons}</td><td>${fmt(s.ess,1)}</td><td>${s.months_covered.length}</td><td>${fmt(s.max_weight_share,4)}</td></tr>`);
  html+=`<details class="card"><summary><b>更多指标（中心RMSE、个人误差、敏感性支持表）——点击展开</b></summary>
    <div style="margin-top:8px"><h3>Q9 全指标（逐月×逐遍等权平均；高亮行=当前候选）</h3>`+
    table(['arm','n(人×月)','独立人数','月×遍格','ESS','最大权重份额','群体中位数MAE','中心RMSE','中心带符号偏差','个人MAE','个人绝对误差中位数','跨人W1','去心W1','更新W1','模型中位','真人中位','模型IQR','真人IQR','照抄中心MAE','照抄−模型(中心)','同支持n'],rows)+
    `<h3>敏感性：各臂可用支持（该臂全部遍可评，不与其余臂取交）</h3>`+
    table(['arm','可用 n(人×月)','独立人数','ESS','覆盖月','最大权重份额'],sens)+
    `<div class="note">照抄上期只在模型与照抄完全相同的人×月支持上计算；「照抄−模型」为正表示模型优于照抄（指标：群体中位数MAE）。</div></div></details>`;
  html+='</section>';
  html=html.replace('<div id="chart-center"></div>','<div id="chart-center"></div>'+exportButtonsHTML('chart-center'));
  html=html.replace('<div id="chart-diff"></div>','<div id="chart-diff"></div>'+exportButtonsHTML('chart-diff'));
  html=html.replace('</section>','<div class="card"><h3>导出</h3><button id="btnCSV">导出聚合长表 CSV（实验×题目×月×组×臂×指标×n/ESS）</button>'+
    '<div class="note">· 只导出聚合指标，不含任何个人记录；换实验/臂后请重新导出。</div></div></section>');
  main.innerHTML=html;
  lineChart($('chart-center'), series, {labels:months.map(yfmt), months, unit:'pp'});
  diffChart($('chart-diff'), months, diffs, rawA, rawB, dn);
  const b=document.getElementById('btnCSV');
  if(b) b.onclick=exportLongCSV;
  wireExportButtons(main);
}

/* ---------- tab: monthly + grid ---------- */
function renderMonthlyTab(main){
  if(cur.q==='q8'){ main.innerHTML=`<section><h2>月份与人群</h2>${q8banner('逐月误差与人群网格只有 Q9 聚合')}</section>`; return; }
  const m = sec('monthly'), arm = cur.arm, block = m[arm];
  if(!block){ main.innerHTML='<section><h2>月份与人群</h2><div class="note">未提供</div></section>'; return; }
  const rows=block.rows.map(r=>{
    const cls = r.regime==='drastic' ? ' class="drastic"' : '';
    return `<tr${cls}><td class="l">${yfmt(r.month)}</td><td>${r.repeat}</td><td>${r.regime==='drastic'?'剧烈':(r.regime==='calm'?'平稳':'未知')}</td>`+
      `<td>${r.n}</td><td>${fmt(r.ess,1)}</td>`+
      td(r.truth_median_pp)+td(r.model_median_pp)+td(r.persist_median_pp)+
      td(r.model_center_mae_pp)+td(r.persist_center_mae_pp)+
      td(r.model_person_mae_pp)+td(r.persist_person_mae_pp)+td(r.w1_pp)+'</tr>';
  });
  const t=block.regime_table;
  const regimeRows=[['平稳',t.calm],['剧烈',t.drastic]].map(([lb,g])=>
    `<tr><td class="l">${lb}</td><td>${g.n_cells}</td>${td(g.model_center_mae_pp)}${td(g.persist_center_mae_pp)}${td(g.model_person_mae_pp)}${td(g.persist_person_mae_pp)}</tr>`);
  let html=`<section><h2>月份与人群</h2>
    <div class="guide">逐月逐遍先算再等权平均；剧烈月（|Δ真值中位|≥0.2pp，事后口径）方向正确即机械占优，必须与平稳月同报。</div>
    <div class="card"><h3>机制月 2×2（逐月×逐遍格等权平均）</h3>`+
    table(['机制月','格数','模型中心MAE(主)','照抄中心MAE','模型个人MAE','照抄个人MAE'],regimeRows)+
    `<div class="note">剧烈月技能值 S（中心口径，主）= 照抄−模型 = <b>${fmt(block.skill_s_center_pp)}</b> pp；S（个人MAE口径，并列参考）= <b>${fmt(block.skill_s_person_pp)}</b> pp。S>0 表示模型优于照抄。</div></div>
    <div class="card"><h3>逐月×逐遍明细表（黄色底纹=剧烈月）</h3>`+
    table(['月份','遍','机制','n','ESS','真人中位','模型中位','照抄中位','模型中心MAE','照抄中心MAE','模型个人MAE','照抄个人MAE','跨人W1'],rows)+'</div>';
  html+=(block.notes||[]).map(n=>`<div class="note">· ${esc(n)}</div>`).join('');
  // grid (人群)
  const g=sec('grid')[arm]||{};
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
  // drill: month selector + clickable grid rows
  const d=sec('drill');
  const monthOpts=[...new Set([...(block.rows||[]).map(r=>r.month)])].sort((a,b)=>a-b);
  html+=`<div class="card"><h3>下钻：月份 × 人群格（点击某行选择；再选月份看条件分布）</h3>
    <div style="display:flex;gap:18px;flex-wrap:wrap;align-items:center;margin-bottom:6px">
      <span>月份：<select id="drillMonth"><option value="">（先选择月份）</option>`+
      monthOpts.map(m=>`<option value="${m}" ${String(drillSel.month)===String(m)?'selected':''}>${yfmt(m)}</option>`).join('')+
      `</select></span>
      <span id="drillPick" style="font-size:13px;color:#5c665f">${
        drillSel.dim?('已选：'+esc(drillSel.dim)+' / '+esc(drillSel.label)+'（点击表格行可改选）'):'尚未选择人群格：点击下面任一表格行'}</span>
    </div><div id="drillPanel"></div></div>`;
  for(const [dim,title] of [['six_cell','六格网格（学历×在职）'],['age_group','年龄切片'],['household_income_band','家庭收入切片'],['numeracy','数理切片'],['region','地区切片'],['housing_tenure','住房切片']]){
    const cells=g[dim]||{};
    const entries=Object.entries(cells);
    if(!entries.length){ html+=`<div class="card"><h3>${title}</h3><div class="note">未提供</div></div>`; continue; }
    html+=`<div class="card"><h3>${title}（点击行下钻）</h3>`+
      table(['组','n(人×月)','独立人数','ESS','可报月/覆盖月','月内最小n','个人MAE','照抄个人MAE','群体中位数MAE','中心带符号偏差','跨人W1','展示等级'],
        entries.map(([k,c])=>{
          const row=cellRow(c.label_cn||k,c);
          return row.replace('<tr', `<tr class="drillrow" data-dim="${esc(dim)}" data-label="${esc(k)}" style="cursor:pointer"`);
        }))+'</div>';
  }
  html+='<div class="note">· 各格为跨月混合分布（非月内异质性）：按月×遍计算后等权平均；覆盖与月内最小 n 随格显示，不用全年人数掩盖月内缺口。</div>';
  // variance decomposition card
  if(d && Object.keys(d.variance||{}).length){
    html+=`<div class="card"><h3>六格组内/组间方差分解（真人，次级诊断）</h3><div id="chart-variance"></div>${exportButtonsHTML('chart-variance')}`+
      `<div class="note">· ${esc(d.note||'')}</div></div>`;
  }
  html+='</section>';
  main.innerHTML=html;
  const monthSel=document.getElementById('drillMonth');
  monthSel.onchange=()=>{ drillSel.month=monthSel.value?Number(monthSel.value):null; renderDrillPanel(); };
  main.querySelectorAll('tr.drillrow').forEach(row=>{
    row.onclick=()=>{ drillSel.dim=row.getAttribute('data-dim'); drillSel.label=row.getAttribute('data-label'); renderMonthlyTab(main); };
    row.title='点击下钻该人群格';
  });
  if(document.getElementById('chart-variance')){ varianceChart(document.getElementById('chart-variance'), d.variance); }
  renderDrillPanel();
  wireExportButtons(main);
}
function renderDrillPanel(){
  const panel=document.getElementById('drillPanel');
  if(!panel) return;
  const pick=document.getElementById('drillPick');
  if(!drillSel.month || !drillSel.dim || !drillSel.label){
    panel.innerHTML='<div class="note">选择月份并点击一个人群格后，这里显示真人/模型/持续性基线的加权 CDF 与分位区间。</div>';
    return;
  }
  if(pick) pick.textContent=`已选：${drillSel.dim} / ${drillSel.label} @ ${yfmt(drillSel.month)}`;
  const d=sec('drill');
  const cell=((d.dims[drillSel.dim]||{}).cells[drillSel.label]||{}).months[String(drillSel.month)];
  if(!cell){ panel.innerHTML='<div class="note">该月该格没有覆盖（未提供）。</div>'; return; }
  if(cell.display_class==='coverage'){
    panel.innerHTML=`<div class="note">该格该月 n=${cell.n}（<10），按稀疏纪律只显示覆盖，不渲染分布判断。</div>`;
    return;
  }
  const arm=cur.arm;
  const modelProf=(cell.arms||{})[arm];
  const series=[];
  if(cell.truth) series.push({role:'truth', name:'真人', short:'真人', values:cell.truth.cdf});
  if(modelProf) series.push({role:'cand', name:`模型 ${arm}`, short:'模型', values:modelProf.cdf});
  if(cell.prior) series.push({role:'base', name:'持续性基线（上期）', short:'上期', values:cell.prior.cdf});
  panel.innerHTML=`<div class="card" style="border:none;padding:4px 0"><h3>加权经验 CDF（${yfmt(drillSel.month)} · ${esc(drillSel.label)} · n=${cell.n} · ESS=${fmt(cell.ess,1)} · ${esc(d.quantile_note)}）</h3><div id="chart-cdf"></div>${exportButtonsHTML('chart-cdf')}</div>
    <div class="card" style="border:none;padding:4px 0"><h3>加权分位区间图（P10–P90 外段、P25–P75 内段、中位数标记；${esc(d.quantile_note)}，非 Tukey 箱线图）</h3><div id="chart-quant"></div>${exportButtonsHTML('chart-quant')}</div>`;
  cdfChart(document.getElementById('chart-cdf'), d.grid, series);
  quantileChart(document.getElementById('chart-quant'), [
    {name:'真人', role:'truth', q:(cell.truth||{}).q||{}},
    {name:`模型 ${arm}`, role:'cand', q:(modelProf||{}).q||{}},
    {name:'持续性基线（上期）', role:'base', q:(cell.prior||{}).q||{}},
  ].map(r=>({...r, n:cell.n})));
  wireExportButtons(panel);
}

/* ---------- tab: priors + structure ---------- */
function renderPriorsTab(main){
  if(cur.q==='q8'){ main.innerHTML=`<section><h2>先验与回答结构</h2>${q8banner('先验分组与十档形状只有 Q9 聚合')}</section>`; return; }
  const p=sec('priors'), arm=cur.arm, block=p[arm];
  const s=sec('structure'), sblock=s[arm];
  let html=`<section><h2>先验与回答结构</h2>
    <div class="guide">旧信念如何保留、谁改变了判断、十档概率与重复波动怎样失真。</div>`;
  if(block){
    const rowsOf=obj=>Object.values(obj).map(c=>{
      const head=`<td class="l">${esc(c.label_cn)}</td><td>${c.n}</td><td>${fmt(c.ess,1)}</td>`;
      if(c.display_class==='coverage' && !_f(c.person_mae_pp))
        return `<tr class="sup">${head}<td colspan="9" class="sup">n 不足（仅覆盖）</td></tr>`;
      return `<tr>${head}${td(c.prior_mean_pp)}${td(c.truth_mean_pp)}${td(c.model_mean_pp)}`+
        td(c.center_mae_pp)+td(c.person_mae_pp)+td(c.persist_person_mae_pp)+td(c.bias_pp)+td(c.w1_pp)+td(c.delta_w1_pp)+'</tr>';
    });
    html+='<div class="card"><h3>先验四档条件均值点线图（低端抬高/高端压缩一目了然）</h3><div id="chart-bands"></div>'+
      `<div class="note">· 点为各档合并条件均值（跨月混合）；真人 ${ROLES.truth.label} / 模型 ${ROLES.cand.label} / 先验 ${ROLES.base.label}。</div>${exportButtonsHTML('chart-bands')}</div>`;
    html+='<div class="card"><h3>按上期真人预期四档（前置特征分组）</h3>'+
      table(['上期预期档','n','ESS','先验均值','真人均值','模型均值','群体中位数MAE','个人MAE','照抄个人MAE','中心带符号偏差','跨人W1','Δ分布W1'],rowsOf(block.bands))+'</div>';
    html+='<div class="card"><h3>真人上调/稳定/下调：变化幅度对比（|Δ| 均值，跨月混合；事后真值分组）</h3><div id="chart-dirdelta"></div>'+
      `<div class="note">· 此分组使用本期真值，仅用于评价，不能用于输入分配。</div>${exportButtonsHTML('chart-dirdelta')}</div>`;
    html+='<div class="card"><h3>按真人本期变化方向（事后真值分组，仅用于评价，不能用于输入分配）</h3>'+
      table(['真人本期','n','ESS','先验均值','真人均值','模型均值','群体中位数MAE','个人MAE','照抄个人MAE','中心带符号偏差','跨人W1','Δ分布W1'],rowsOf(block.directions))+'</div>';
  }
  if(sblock){
    const cp=sblock.cross_person;
    html+='<div class="bigrow">'+
      `<div class="stat"><div class="v" style="color:${ROLES.truth.color}">${fmt(cp.truth_std_pp)}<span style="font-size:13px">pp</span></div><div class="k">真人跨人 std</div></div>`+
      `<div class="stat"><div class="v" style="color:${ROLES.cand.color}">${fmt(cp.model_std_pp)}<span style="font-size:13px">pp</span></div><div class="k">模型跨人 std</div></div>`+
      `<div class="stat"><div class="v" style="color:${ROLES.truth.color}">${fmt(cp.truth_iqr_pp)}</div><div class="k">真人跨人 IQR</div></div>`+
      `<div class="stat"><div class="v" style="color:${ROLES.cand.color}">${fmt(cp.model_iqr_pp)}</div><div class="k">模型跨人 IQR</div></div></div>`;
    if(cp.note) html+=`<div class="note">· ${esc(cp.note)}</div>`;
    const sh=(title,key)=>{
      const a=(sblock.model_shape||{})[key], b=(sblock.truth_shape||{})[key];
      if(!a && !b) return `<div class="card"><h3>${title}</h3><div class="note">未提供</div></div>`;
      return `<div class="card"><h3>${title}（跨月混合分布）</h3><div id="hist-${key}"></div>`+
        `<div class="note">n：模型 ${(sblock.model_shape||{}).n}，真人 ${(sblock.truth_shape||{}).n}；零通缩概率占比：模型 ${fmt((sblock.model_shape||{}).zero_deflation_share,3)}，真人 ${fmt((sblock.truth_shape||{}).zero_deflation_share,3)}；十档全零占比：模型 ${fmt((sblock.model_shape||{}).all_zero_share,3)}，真人 ${fmt((sblock.truth_shape||{}).all_zero_share,3)}</div></div>`;
    };
    html+=sh('十档形状特征：非零档数分布','nz_bins');
    html+=sh('十档形状特征：最大档概率分布（%）','max_prob');
    html+=sh('十档形状特征：概率为 5 的倍数占比分布','mult5_share');
    const r=sblock.repeats;
    if(r){
      const neg = r.noise_adjusted_negative ? '；噪声扣除后人际方差为负：人与人之间的差别小于重复采样波动，保留该负估计，不截为零。' : '';
      html+='<div class="card"><h3>重复生成方差分解（'+esc(r.repeat_label||('R='+r.repeats))+'，等权人）</h3><div class="bigrow">'+
        `<div class="stat"><div class="v">${fmt(r.within_person_repeat_variance_pp2,3)}</div><div class="k">人内重复方差(pp²)</div></div>`+
        `<div class="stat"><div class="v">${fmt(r.between_person_repeat_mean_variance_pp2,3)}</div><div class="k">重复均值的人际方差(pp²)</div></div>`+
        `<div class="stat"><div class="v">${fmt(r.noise_adjusted_between_variance_pp2,3)}</div><div class="k">扣除人内/R 后(pp²)</div></div></div>`+
        `<div class="note">n=${r.n_persons} 人×月，${r.n_months} 个月，R=${r.repeats}。${esc(r.note||'')}${neg}</div></div>`;
    }
  }
  html+='<div class="note">· 先验四档为开发期阈值的前置分组；变化方向分组使用本期真值，仅用于评价。</div></section>';
  main.innerHTML=html;
  // band point-line chart from pooled band means
  const bandDefs=[['below_2','<2%'],['2_to_below_4','2–4%'],['4_to_below_8','4–8%'],['8_or_above','≥8%']];
  const bandPts=bandDefs.map(([k,lb])=>{
    const b=(block.bands||{})[k]||{};
    return {label:lb, truth:b.truth_mean_pp, model:b.model_mean_pp, prior:b.prior_mean_pp};
  });
  if(document.getElementById('chart-bands')) bandLineChart(document.getElementById('chart-bands'), bandPts);
  const dirDefs=[['up','上调'],['stable','稳定'],['down','下调']];
  const dirGroups=dirDefs.map(([k,lb])=>{
    const rows=((block.direction_amplitude||{})[k])||[];
    const tv=rows.map(r=>r.truth_abs).filter(_f), mv=rows.map(r=>r.model_abs).filter(_f);
    return {label:lb, values:[tv.length?tv.reduce((a,b)=>a+b,0)/tv.length:null,
                               mv.length?mv.reduce((a,b)=>a+b,0)/mv.length:null]};
  });
  if(document.getElementById('chart-dirdelta')) groupedBars(document.getElementById('chart-dirdelta'), dirGroups, ['真人|Δ|','模型|Δ|'], [ROLES.truth.color, ROLES.cand.color]);
  ['nz_bins','max_prob','mult5_share'].forEach(key=>{
    const el=$('hist-'+key); if(!el) return;
    const a=(sblock.model_shape||{})[key], b=(sblock.truth_shape||{})[key];
    if(!a) return;
    barHist(el, a, b);
  });
  wireExportButtons(main);
}
function bandLineChart(el, pts){
  const W=560,H=300,P={l:56,r:20,t:16,b:40};
  const all=pts.flatMap(p=>[p.truth,p.model,p.prior].filter(_f));
  if(!all.length){ el.innerHTML='<div class="note">无可绘制数据</div>'; return; }
  let yMin=Math.min(...all), yMax=Math.max(...all);
  if(yMin===yMax){yMin-=1;yMax+=1;}
  const pad=(yMax-yMin)*0.15; yMin-=pad; yMax+=pad;
  const xw=(W-P.l-P.r)/Math.max(1,pts.length-1);
  const X=i=>P.l+i*xw, Y=v=>P.t+(1-(v-yMin)/(yMax-yMin))*(H-P.t-P.b);
  let g='';
  for(let k=0;k<=4;k++){const gy=P.t+k/4*(H-P.t-P.b);
    g+=`<line x1="${P.l}" y1="${gy}" x2="${W-P.r}" y2="${gy}" stroke="#e7e1d2"/>`;
    g+=`<text x="${P.l-6}" y="${gy+4}" font-size="10.5" text-anchor="end" fill="#8a8f87">${(yMax-k/4*(yMax-yMin)).toFixed(1)}</text>`;}
  g+=`<text x="14" y="${P.t+10}" font-size="10.5" fill="#8a8f87">pp</text>`;
  pts.forEach((p,i)=>{ g+=`<text x="${X(i)}" y="${H-20}" font-size="11.5" text-anchor="middle" fill="#4a554e">${esc(p.label)}</text>`;});
  [['truth','truth','真人'],['model','cand','模型'],['prior','base','先验']].forEach(([key,role,name])=>{
    const st=ROLES[role];
    const pts2=pts.map((p,i)=>({x:X(i), y:_f(p[key])?Y(p[key]):null, v:p[key]})).filter(pt=>pt.y!==null);
    if(pts2.length) g+=`<polyline points="${pts2.map(pt=>`${pt.x},${pt.y}`).join(' ')}" fill="none" stroke="${st.color}" stroke-width="2.2"${st.dash?` stroke-dasharray="${st.dash}"`:''}/>`;
    pts2.forEach(pt=>{ g+=`<path d="${markerPath(st.marker,pt.x,pt.y,4.5)}" fill="${st.color}"><title>${esc(name)} ${pt.v.toFixed(2)}pp</title></path>`;
      g+=`<text x="${pt.x}" y="${pt.y-10}" font-size="10" text-anchor="middle" fill="${st.color}">${pt.v.toFixed(1)}</text>`;});
  });
  const lg=document.createElement('div'); lg.className='legend';
  [['truth','真人'],['cand','模型'],['base','先验']].forEach(([role,name])=>{
    const st=ROLES[role];
    lg.innerHTML+=`<span class="item"><span style="color:${st.color}">${st.dash?'╌':'─'}${st.marker==='square'?'■':st.marker==='triangle'?'▲':st.marker==='diamond'?'◆':'●'}</span> ${name}</span> `;
  });
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px;background:#fff;border:1px solid var(--line);border-radius:6px">${g}</svg>`;
  el.appendChild(lg);
}
function barHist(el, histA, histB){
  const labels=histA.map(h=>h.label);
  const groups=labels.map((lb,i)=>({label:lb, values:[histA[i].n, histB?histB[i].n:null]}));
  groupedBars(el, groups, ['模型','真人'], [ROLES.cand.color, ROLES.truth.color]);
}
function groupedBars(el, groups, names, colors){
  const W=860,H=250,P={l:56,r:16,t:14,b:46};
  const vals=groups.flatMap(g=>g.values.filter(_f));
  if(!vals.length){ el.innerHTML='<div class="note">无可绘制数据</div>'; return; }
  const yMax=Math.max(...vals)*1.15||1;
  const slot=(W-P.l-P.r)/groups.length, bw=Math.min(26,(slot-8)/names.length);
  const y=v=>P.t+(1-v/yMax)*(H-P.t-P.b);
  let g='';
  for(let k=0;k<=4;k++){const gy=P.t+k/4*(H-P.t-P.b);
    g+=`<line x1="${P.l}" y1="${gy}" x2="${W-P.r}" y2="${gy}" stroke="#e7e1d2"/>`;
    g+=`<text x="${P.l-6}" y="${gy+4}" font-size="10.5" text-anchor="end" fill="#8a8f87">${(yMax*(1-k/4)).toFixed(0)}</text>`;}
  groups.forEach((gr,gi)=>{
    const cx0=P.l+gi*slot+slot/2;
    gr.values.forEach((v,ni)=>{
      if(!_f(v)) return;
      const bx=cx0-(names.length*bw)/2+ni*bw;
      g+=`<rect x="${bx}" y="${y(v)}" width="${bw-2}" height="${Math.max(0,H-P.b-y(v))}" fill="${colors[ni]}"/>`;
      g+=`<text x="${bx+bw/2-1}" y="${y(v)-3}" font-size="9.5" text-anchor="middle" fill="#4a554e">${v}</text>`;
    });
    g+=`<text x="${cx0}" y="${H-28}" font-size="10.5" text-anchor="middle" fill="#8a8f87">${gr.label}</text>`;
  });
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px;background:#fff;border:1px solid var(--line);border-radius:6px">${g}</svg>`;
}

/* ---------- tab: inputs ---------- */
function renderInputsTab(main){
  const e=exp(), pr=e.protocol||{};
  const inp=sec('inputs')||{};
  const meta=(k,v)=>`<tr><td class="l"><b>${esc(k)}</b></td><td class="l" style="white-space:normal">${(v===null||v===undefined)?'<span style="color:#9aa39b">未提供</span>':esc(Array.isArray(v)?v.join('、'):v)}</td></tr>`;
  let trialHtml='';
  if(!inp.trial_dir){
    trialHtml=`<div class="card"><h3>输入差异清单（trial 元数据）</h3><div class="note">· ${esc(inp.note||'未接入')}</div></div>`;
  } else {
    const layerRows=[];
    Object.entries(inp.months||{}).forEach(([m,mi])=>{
      if(mi.layers && mi.layers.length){
        mi.layers.forEach((L,i)=>{
          layerRows.push(`<tr><td class="l">${i===0?yfmt(m):''}</td><td class="l">${esc(L.name||'未提供')}</td><td class="l">${esc(L.scope||'')}</td><td class="l">${esc(L.dynamics||'')}</td><td class="l" style="white-space:normal">${esc(L.description||'未提供')}</td><td class="l" style="white-space:normal">${esc(L.source||'未提供')}</td></tr>`);
        });
      } else {
        layerRows.push(`<tr><td class="l">${yfmt(m)}</td><td class="l" colspan="5">${esc(mi.environment||'environment 未提供')}</td></tr>`);
      }
    });
    const monthRows=Object.entries(inp.months||{}).map(([m,mi])=>
      `<tr><td class="l">${yfmt(m)}</td><td>${mi.n_events===null||mi.n_events===undefined?'<span style="color:#9aa39b">未提供</span>':mi.n_events}</td>`+
      `<td class="l">${mi.prompt_arms&&mi.prompt_arms.length?esc(mi.prompt_arms.join('、')):'<span style="color:#9aa39b">未提供</span>'}</td>`+
      `<td class="l">${mi.layers?mi.layers.length:0} 层</td></tr>`);
    trialHtml=`<div class="card"><h3>各臂输入差异清单（来自 trial 元数据，非理由文本）</h3>`+
      table(['项','内容'],[
        meta('来源 trial 目录', inp.trial_dir),
        meta('臂间相同', (inp.arm_diff||{}).shared),
        meta('本机制改变', (inp.arm_diff||{}).changed),
        meta('未接入', ((inp.arm_diff||{}).not_integrated||[]).join('；')),
        meta('机制标识', inp.mechanism),
        meta('信息变化说明', inp.information_change),
        meta('预设对照', inp.prespecified_contrasts),
        meta('计划调用（trial protocol）', inp.planned_calls),
        meta('计划任务（manifest）', inp.planned_jobs),
        meta('预算上限合计（失败预留口径）', inp.budget_cap_usd!==undefined&&inp.budget_cap_usd!==null?inp.budget_cap_usd.toFixed(2)+' USD':'未提供'),
      ])+'</div>'+
      `<div class="card"><h3>按月提供的信息（environment layers / prompt 覆盖）</h3>`+
      table(['月份','计划事件数','该月有 prompt 的臂','环境层数'], monthRows)+
      `<details style="margin-top:6px"><summary>环境层明细（展开）</summary><div style="margin-top:6px">`+
      table(['月份','层名','范围','动态','说明','来源'], layerRows)+'</div></details>'+
      `<div class="note">· CPI/食品/能源逐月数值未结构化提供：本面板不从文本反推输入；如需要逐字段清单，请由输入准备层产出结构化快照后接入（插件式）。</div></div>`;
  }
  main.innerHTML=`<section><h2>输入与配置</h2>
    <div class="guide">这轮实验各组究竟收到了哪些人口、历史、新闻、价格与政策信息；跨批比较先核对本页与质量页的支持口径。</div>
    <div class="card"><h3>协议信息（来自 summary.json，未逐字段核对哈希）</h3>`+
    table(['字段','内容'],[
      meta('模型', pr.model), meta('官方标识', pr.official_advertised_version),
      meta('温度', pr.temperature), meta('协议', pr.id), meta('研究线', pr.research_line),
      meta('月份', pr.months ? pr.months.map(yfmt).join('、') : null),
      meta('每月人数', pr.n_per_month), meta('arms', pr.arms),
      meta('配置说明', pr.configuration), meta('月份选择', pr.month_selection),
      meta('资格口径', pr.eligibility), meta('权重口径', pr.weights),
      meta('说明（登记表）', e.description),
    ])+'</div>'+
    trialHtml+
    `<div class="card"><h3>比较资格</h3><div class="note">· ${esc(PANEL.comparability_notice)}</div>
     <div class="note">· 仅缺来源元数据时写“无法确认”，不自动归入同输入；同一温度不保证不同模型输出方差相同。</div></div>
  </section>`;
}

/* ---------- tab: quality ---------- */
function renderQualityTab(main){
  const q=sec('quality');
  const arms=q.arms||{};
  const rows=Object.entries(arms).map(([arm,a])=>`<tr><td class="l"><b>${esc(arm)}</b></td><td>${a.n_records}</td><td>${a.n_scorable}</td><td>${fmt(a.missing_share,4)}</td><td class="l">${esc(Object.entries(a.scorer_status).map(([k,v])=>k+':'+v).join('，')||'未提供')}</td><td>${fmt(a.normalization_applied_share,4)}</td><td>${a.weight_missing}</td><td>${fmt(a.q8_truth_coverage,3)}</td><td>${fmt(a.q8_model_coverage,3)}</td><td>${a.q9_usable_person_months!==undefined?a.q9_usable_person_months:'未提供'}</td></tr>`);
  const pr=q.protocol||{};
  const cost = pr.estimated_cost_usd!==undefined&&pr.estimated_cost_usd!==null
      ? (typeof pr.estimated_cost_usd==='number'?pr.estimated_cost_usd.toFixed(2)+' USD':esc(pr.estimated_cost_usd))
      : '未接入';
  // quality funnel per arm: stages read from cases fields; absent -> 未接入
  const STAGES=[['planned','计划（protocol/manifest）'],['attempted','回包（评分缓存记录）'],
    ['parsed','结构可解析'],['raw_valid','原始合法'],['normalized','归一化可用'],['scorable','可评分']];
  const funnelRows=Object.entries(q.arms||{}).map(([arm,a])=>{
    const f=a.funnel||{};
    return `<tr><td class="l"><b>${esc(arm)}</b></td>`+STAGES.map(([k,lb])=>
      `<td>${f[k]===undefined||f[k]===null?'<span style="color:#9aa39b">未接入</span>':f[k]}</td>`).join('')+`</tr>`;
  });
  const funnelNote='漏斗从 trial protocol/manifest 与评分缓存读取；读不到的环节标“未接入”，不填零。原始合法与归一化字段只在部分批次存档。';
  // month x arm missing matrix
  const ma=q.month_arm_missing||{};
  const allMonths=[...new Set(Object.values(ma).flatMap(armObj=>Object.keys(armObj)))].sort();
  const missRows=allMonths.map(m=>{
    const cells=Object.keys(ma).map(arm=>{
      const c=ma[arm][m];
      if(!c) return '<td style="text-align:center;color:#9aa39b">—</td>';
      const sh=c.missing_share;
      if(sh===null||sh===undefined) return '<td style="text-align:center;color:#9aa39b">未提供</td>';
      const alpha=Math.min(0.85, 0.08+sh*3);
      return `<td style="background:rgba(213,94,0,${alpha.toFixed(2)})" title="assigned ${c.assigned} / scorable ${c.scorable}">${(sh*100).toFixed(0)}%</td>`;
    }).join('');
    return `<tr><td class="l">${yfmt(Number(m))}</td>${cells}</tr>`;
  });
  const batches=PANEL.source_batches.map(b=>`<tr><td class="l">${esc(b.batch)}</td><td class="l">${esc(b.label)}${b.registered?'':'（未登记）'}</td><td>${esc(b.status==='ok'?'已接入':'未接入')}</td><td class="l">${esc(b.skip_reason||'—')}</td><td>${b.n_cases}</td></tr>`);
  main.innerHTML=`<section><h2>质量与复现</h2>
    <div class="guide">缺失、归一化、支持、费用、版本与复算入口。</div>
    <div class="card"><h3>支持口径</h3><div style="font-size:13.5px;display:flex;gap:8px 22px;flex-wrap:wrap">`+
    `<span><b>Q9 共同支持</b>：${q.q9_common_person_months} 人×月</span>`+
    `<span><b>Q8 共同支持</b>：${q.q8_common_person_months} 人×月（独立取支持）</span>`+
    (q.support_note?`<span style="color:#a4453a">${esc(q.support_note)}</span>`:'')+'</div></div>'+
    `<div class="card"><h3>质量漏斗（计划→回包→可解析→原始合法→归一化→可评分）</h3>`+
    table(['arm',...STAGES.map(([k,lb])=>lb)],funnelRows)+
    `<div class="note">· ${esc(funnelNote)}</div></div>`+
    `<div class="card"><h3>月 × 臂 缺失率热力表（悬停看 assigned/scorable）</h3>`+
    table(['月份',...Object.keys(ma).map(esc)],missRows)+
    `<div class="note">· 颜色越深得缺越多；共同支持=Q9 各臂×遍均可评的人×月，见支持口径卡。</div></div>`+
    `<details class="card"><summary><b>每臂质量明细（scorer 计数、归一化比例、Q8 覆盖）——展开</b></summary><div style="margin-top:8px">`+
    table(['arm','记录数','可评分','缺失率','scorer_status 计数','归一化比例','权重缺失','Q8真值覆盖','Q8模型覆盖','臂可用n(人×月)'],rows)+'</div></details>'+
    `<div class="card"><h3>运行与费用</h3><div style="font-size:13.5px;display:flex;flex-wrap:wrap;gap:8px 22px">`+
    `<span><b>状态</b>：${esc(pr.batch_status||'未提供')}</span><span><b>费用（${(q.cost||{}).basis==='actual_ledger'?'已报告':'估计'}）</b>：${esc((q.cost||{}).display||cost)}</span>`+
    `<span><b>预算上限（manifest cap 合计，失败预留口径）</b>：${(q.cost||{}).budget_cap_usd!==undefined&&(q.cost||{}).budget_cap_usd!==null?(q.cost||{}).budget_cap_usd.toFixed(2)+' USD':'未接入'}</span>`+
    `<span><b>计划任务</b>：${(q.cost||{}).planned_jobs!==undefined?(q.cost||{}).planned_jobs:'未接入'}</span>`+
    `<span><b>证据阶段</b>：${esc((exp().registry||{}).evidence_stage||'未登记')}</span>`+
    `<span><b>运行状态</b>：${esc((exp().registry||{}).run_status||'未登记')}</span>`+
    `<span><b>模型</b>：${esc(pr.model||'未提供')}${pr.temperature!==undefined?'（T='+esc(pr.temperature)+'）':''}</span></div></div>`+
    `<div class="card"><h3>复算入口</h3><div class="note">· 本页由 <code>scripts/build_sce_experiment_panel.py</code> 离线生成（零 API、零网络、不重新拟合密度）；重跑一条命令即可在评价缓存更新后刷新面板。私有逐人中间文件留在 outputs/（git 忽略），本 HTML 只嵌聚合。</div>`+
    `<div class="note">· 费用为已报告/估计值，未接入实际账本的批次显示“未接入”；失败预留与已花费不合并。</div></div>`+
    `<div class="card"><h3>批次清单（自动发现 outputs/*_evaluation_*）</h3>`+
    table(['批次','显示名','状态','原因','cases 数'],batches)+'</div>'+
  '</section>';
}

/* ---------- tab dispatch ---------- */
function renderTab(){
  document.querySelectorAll('#tabbar button').forEach(b=>{
    b.classList.toggle('on', b.getAttribute('data-tab')===cur.tab);
  });
  const main=$('main');
  hiddenSeries={};
  ({overview:renderOverviewTab, monthly:renderMonthlyTab, priors:renderPriorsTab,
    inputs:renderInputsTab, quality:renderQualityTab}[cur.tab]||renderOverviewTab)(main);
  renderMetabar();
  syncHash();
}

/* ---------- selection & init ---------- */
function fillArms(){
  const e=exp(), sel=$('selArm');
  const ctrl=controlArm();
  sel.innerHTML='';
  e.arms.forEach(a=>{const o=document.createElement('option');o.value=a;o.textContent=a+(a===ctrl?'（对照）':'');sel.appendChild(o);});
  if(!e.arms.includes(cur.arm) || cur.arm===ctrl){
    cur.arm = e.arms.find(a=>a!==ctrl) || ctrl;
  }
  sel.value=cur.arm;
  $('ctlName').textContent=ctrl;
  const hasQ8=e.q8_available;
  $('btnQ8').disabled=!hasQ8;
  $('q8warn').style.display=hasQ8?'none':'block';
  if(!hasQ8){cur.q='q9';$('btnQ9').classList.add('on');$('btnQ8').classList.remove('on');}
}
function selectExperiment(batch){
  if(!PANEL.experiments[batch]) return;
  cur.exp = batch;
  $('selExp').value = batch;
  fillArms();
  renderTab();
  $('toolbar').scrollIntoView({behavior:'smooth'});
}
function init(){
  $('notice').textContent=PANEL.comparability_notice;
  $('genat').textContent=PANEL.generated_at_utc.slice(0,19).replace('T',' ');
  renderCatalog();
  // tab bar
  TABS.forEach(([id,name])=>{
    const b=document.createElement('button');
    b.textContent=name; b.setAttribute('data-tab',id);
    b.onclick=()=>{ cur.tab=id; renderTab(); };
    $('tabbar').appendChild(b);
  });
  const sel=$('selExp');
  expKeys().forEach(k=>{const e=PANEL.experiments[k];const o=document.createElement('option');
    o.value=k;o.textContent=e.label;sel.appendChild(o);});
  cur.exp=expKeys()[0];
  const h=parseHash();
  if(h.exp && PANEL.experiments[h.exp]) cur.exp=h.exp;
  if(h.tab && TABS.some(([id])=>id===h.tab)) cur.tab=h.tab;
  if(h.q==='q8') cur.q='q8';
  sel.value=cur.exp;
  sel.onchange=()=>{cur.exp=sel.value; fillArms(); renderTab();};
  $('btnQ9').onclick=()=>{cur.q='q9';$('btnQ9').classList.add('on');$('btnQ8').classList.remove('on');renderTab();};
  $('btnQ8').onclick=()=>{ if(!exp().q8_available) return; cur.q='q8';$('btnQ8').classList.add('on');$('btnQ9').classList.remove('on');renderTab();};
  fillArms();
  $('selArm').onchange=()=>{cur.arm=$('selArm').value;renderTab();};
  $('lnkCatalog').onclick=(ev)=>{ ev.preventDefault(); $('catalog').scrollIntoView({behavior:'smooth'}); };
  window.addEventListener('hashchange',()=>{
    const h=parseHash();
    if(h.exp && h.exp!==cur.exp && PANEL.experiments[h.exp]){ cur.exp=h.exp; $('selExp').value=h.exp; fillArms(); }
    if(h.tab && h.tab!==cur.tab && TABS.some(([id])=>id===h.tab)) cur.tab=h.tab;
    if(h.q && h.q!==cur.q) cur.q=h.q;
    renderTab();
  });
  $('btnQ9').classList.toggle('on', cur.q==='q9');
  $('btnQ8').classList.toggle('on', cur.q==='q8');
  renderTab();
}
init();
</script>
</body>
</html>
"""


def render_html(panel):
    payload = json.dumps(panel, ensure_ascii=False, allow_nan=False)
    payload = payload.replace('</', '<\\/')
    page = _PAGE.replace('__PANEL_JSON__', payload)
    page = page.replace('__ROLE_JSON__', json.dumps(ROLE_STYLES, ensure_ascii=False))
    page = page.replace('__TABS_JSON__', json.dumps(TABS, ensure_ascii=False))
    return page
