import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { Presentation, PresentationFile, FileBlob } from '@oai/artifact-tool';

const ROOT=process.env.SCE_PROJECT_ROOT||process.cwd();
const OUT=path.join(ROOT,'deliverables/video/samples_v02'),BUILD=path.join(ROOT,'tmp/video_samples_v02');
const SKILL='/Users/wushuyue/.codex/plugins/cache/openai-primary-runtime/presentations/26.1022.11436/skills/presentations';
const PY='/Users/wushuyue/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
process.env.RUNTIME_NODE_MODULES??='/Users/wushuyue/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const {finalizePresentation,applyPresentationChartFont}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
const D=JSON.parse(await fs.readFile(path.join(BUILD,'data.json'),'utf8')),A=D.samples[0],B=D.samples[1],M=D.months[A.month];
const CN='Kaiti SC',EN='Times New Roman',C={ink:'#203447',blue:'#2B5E87',purple:'#79578D',orange:'#B55823',gray:'#637481',rule:'#D9E2E8',soft:'#F3F6F9'};
const p=Presentation.create({slideSize:{width:1920,height:1080}});p.theme.defaultFont=CN;
const iteration=new Date().toISOString().replace(/[^0-9]/g,'');
const parts=(s,size,color,bold=false)=>(s.match(/[\x00-\x7F]+|[^\x00-\x7F]+/g)||[]).map(run=>({run,style:{typeface:/^[\x00-\x7F]+$/.test(run)?EN:CN,fontSize:`${size}px`,color,bold}}));
function tx(sl,name,s,x,y,w,h,size=34,color=C.ink,bold=false){
 const sh=sl.shapes.add({geometry:'textbox',name,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 sh.text.style={typeface:CN,fontSize:size,color,bold,verticalAlignment:'top',wrap:'square',autoFit:'none',insets:{left:0,right:0,top:0,bottom:0}};
 sh.text=s.split('\n').map(line=>({spaceAfter:Math.round(size*.16),runs:parts(line,size,color,bold)}));return sh;
}
function rule(sl,name,x,y,w,color=C.rule,width=1.5){return sl.shapes.add({geometry:'connector',kind:'straight',name,position:{left:x,top:y,width:w,height:0},line:{fill:color,width}});}
function vline(sl,name,x,y,h,color=C.rule,width=1.5){return sl.shapes.add({geometry:'connector',kind:'straight',name,position:{left:x,top:y,width:0,height:h},line:{fill:color,width}});}
function block(sl,name,heading,body,x,y,w,h,color=C.blue,size=28){
 const sh=sl.shapes.add({geometry:'textbox',name,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 sh.text.style={typeface:CN,fontSize:size,color:C.ink,verticalAlignment:'top',wrap:'square',autoFit:'none',insets:{left:0,right:0,top:0,bottom:0}};
 sh.text=[{spaceAfter:12,runs:parts(heading,32,color,true)},...body.map(s=>({spaceAfter:9,runs:parts(s,size,C.ink)}))];return sh;
}
function slide(page,title,subtitle,notes){
 const s=p.slides.add();s.background.fill='#FFFFFF';
 tx(s,'title',title,75,55,1770,82,55,C.ink,true);tx(s,'subtitle',subtitle,78,150,1740,58,29,C.gray);rule(s,'header-rule',78,230,1764);
 tx(s,'footer','家庭与已有信念  →  个人可见信息  →  问卷回答  →  指标与评价',80,1007,1570,40,23,C.gray);
 tx(s,'page-number',page,1760,1006,90,42,27,C.blue);
 s.speakerNotes.text=notes+'\n\n来源：最新A T0冻结messages及同Prompt哈希实际模型回复；调查月2021-06。展示编号A01/A02替代原受访者标识。A01 prompt_sha256='+A.prompt_hash+'。\n本页使用实际输入节选与回答，不重新调用模型。互动功能请打开同目录index.html。';return s;
}
const common={chartFill:'none',plotAreaFill:'none',chartLine:{fill:'none',width:0},plotAreaLine:{fill:'none',width:0},hasLegend:false,lineOptions:{smooth:false},xAxis:{line:{fill:C.rule,width:1},textStyle:{fontSize:22,fill:C.gray}},yAxis:{line:{fill:'none',width:0},majorGridlines:{fill:'#E7EDF1',width:1},textStyle:{fontSize:24,fill:C.gray}}};
function chart(s,kind,cfg){const c=s.charts.add(kind,{...common,...cfg,series:cfg.series.map(z=>({...z,values:z.values.map(v=>+v.toFixed(8)),...(z.xValues?{xValues:z.xValues.map(v=>+v.toFixed(8))}:{})}))});applyPresentationChartFont(c,{fontFamily:EN});return c;}
function bins(s,pos,small=false){const values=[...A.bins].reverse();const labels=small?D.bin_labels.map(l=>l.replace('~','\n~')):D.bin_labels;return chart(s,'bar',{position:pos,categories:labels,series:[{name:'Q9概率（%）',values,fill:C.purple,line:{fill:'none',width:0},dataLabelOverrides:values.map((v,idx)=>({idx,showValue:v!==0,position:'outEnd'}))}],barOptions:{direction:'column',gapWidth:55},xAxis:{...common.xAxis,textStyle:{fontSize:small?16:18,fill:C.gray}},yAxis:{...common.yAxis,min:0,max:80,majorUnit:20,numberFormatCode:'0"%"'},dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0',textStyle:{fontSize:small?24:28,fill:C.purple}}});}
// Sample for planned page 02: real prompt excerpts and paired real output.
{
 const s=slide('02','一份真实的模型输入与回答','家庭 A01 · 2021年6月 · 真实输入节选与同一次请求的回答',
 '这是一次真实请求。左边是实际发送的内容：家庭背景、过去判断、当时可见的信息，以及原问卷的题目。右边是模型实际交回的答卷。互动页面还能展开完整Prompt与原始JSON，并随机切换其他真实样本。');
 tx(s,'input-label','模型实际收到的Prompt',80,276,1000,52,35,C.blue,true);vline(s,'input-output-divider',1090,278,680);
 block(s,'profile-block','01  家庭画像',[
  A.sections.profile[0],
 ],82,350,960,148,C.blue,25);
 block(s,'prior-block','02  原有信念',[
  'Earlier belief state (expectations, not measured inflation):',
  `上期Q8 ${A.prior_q8}%；同时提供本人上期十档Q9和较早历史摘要。`,
 ],82,518,960,125,C.blue,27);
 const news=A.news.find(n=>n.date==='2021-06-10')||A.news[0];
 block(s,'environment-block','03  个人可见信息',[
  `${A.news_count}篇新闻 · 全部采购角色 · 信息截止 ${A.cutoff.slice(0,10)}`,
  news.headline,
 ],82,662,960,138,C.orange,27);
 block(s,'question-block','04  问卷与回答格式',[
  'Over the next 12 months, what do you expect the rate of inflation to be, in percent?',
  'Q9填写十档概率；返回 point_pct、q9 和 reason。完整题目在交互页展开。',
 ],82,820,960,135,C.blue,26);
 tx(s,'output-label','同一次请求的真实回答',1140,276,660,52,35,C.purple,true);
 tx(s,'model','DeepSeek V3.2 · Temperature 0.5 · 关闭思考',1142,338,660,53,26,C.gray);
 tx(s,'point-label','Q8  点预期',1144,416,310,50,31,C.gray);tx(s,'point-value',A.q8.toFixed(1)+'%',1470,390,350,100,77,C.purple,true);
 tx(s,'Q9label','Q9  概率分配',1144,500,620,50,31,C.ink);
 bins(s,{left:1112,top:563,width:740,height:280});
 tx(s,'x-unit','未来12个月通胀区间（%）',1235,846,540,42,25,C.gray);
 tx(s,'reason',A.response.reason,1144,898,665,90,23,C.ink);
}
// Sample for planned page 04: matched information; exact price release and cutoffs.
{
 const s=slide('04','同月两户，收到怎样的信息？','真实信息包对照：新闻数量、采购角色与信息截止共同决定可见内容',
 '同一个月，两户家庭收到的信息不同。A01负责全部采购，看到食品总项和六类细项；A02不负责采购，只看到总项。新闻数量随机分档，主题结合个人信息匹配。日期也不同：六月十日公布的新价格，A01可见，A02的这次回答尚不可见。');
 const xs=[80,720],families=[A,B];
 families.forEach((f,i)=>{
  const x=xs[i];
  tx(s,'family-'+i,`家庭 ${f.id}`,x,286,570,60,42,C.blue,true);
  tx(s,'counts-'+i,`${f.news_count} 篇新闻  ·  ${f.grocery_role}`,x,365,570,63,39,C.orange,true);
  tx(s,'counts-detail-'+i,`共同关注${f.common_count}篇＋个人匹配${f.personal_count}篇`,x,438,570,47,27,C.gray);
  rule(s,'news-rule-'+i,x,500,560);
  const chosen=i?[f.news[0],f.news[f.common_count]]:[f.news.find(n=>n.date==='2021-06-10'),f.news[f.common_count]];
  chosen.forEach((n,j)=>block(s,'news-'+i+'-'+j,n.date,[n.headline],x,526+j*133,560,120,C.gray,27));
  rule(s,'price-rule-'+i,x,803,560);
  block(s,'food-'+i,`食品价格：${f.food_reference}参考期`,[
   i?'总项同比 +1.2%；不提供采购细项。':'总项同比 +0.7%；另有6类采购细项。',
   i?'5月12日发布；仅提供总项。':'6月10日发布；提供总项与采购细项。',
  ],x,834,570,142,C.orange,27);
 });
 vline(s,'compare-divider',675,286,680);vline(s,'time-divider',1330,286,680);
 tx(s,'time-title','同一条时间边界',1390,286,430,60,35,C.blue,true);
 vline(s,'timeline',1400,420,420,C.rule,3);
 const timeline=[['6月1日','A02信息截止',C.blue],['6月10日','BLS公布5月食品价格',C.orange],['6月12日','A01信息截止',C.blue]];
 timeline.forEach(([date,label,color],i)=>{const y=403+i*160;rule(s,'tick-'+i,1388,y+22,24,color,4);block(s,'time-'+i,date,[label],1440,y,370,125,color,30);});
 tx(s,'time-bottom','较晚的信息先排除，\n再做主题匹配与抽取。',1385,906,440,78,29,C.gray);
}
// Sample for planned page 05: three editable scientific charts from the same record.
{
 const s=slide('05','十档概率，怎样成为全国指标？','沿用家庭A01答卷；个人密度均值与全国加权中位数分别计算',
 '这十个概率先拟合成一个人的连续分布，取均值，再把所有人的均值按人口权重汇总，得到全国中位数。Q8单独计算。我们还按同类答卷分布补齐人口规模，称为统计扩展；它增加人口表示，不增加独立的模型判断。');
 const xx=[80,710,1340],ww=[545,545,500];
 ['01  十档概率答卷','02  个人连续密度','03  全月加权分布'].forEach((t,i)=>tx(s,'step-'+i,t,xx[i],292,ww[i],65,36,C.blue,true));
 tx(s,'bar-desc','模型原始回答 · 概率总和100%',82,370,550,60,28,C.gray);
 tx(s,'density-desc','冻结广义Beta算法 · 个人Q9均值',710,370,550,60,28,C.gray);
 tx(s,'national-desc',`2021年6月 · ${M.n}份直接模拟的权重`,1340,370,500,60,28,C.gray);
 tx(s,'density-y-label','概率密度',713,430,460,36,24,C.gray);
 tx(s,'cdf-y-label','累计人口质量（%）',1340,430,500,36,24,C.gray);
 vline(s,'step-divider1',660,290,560);vline(s,'step-divider2',1290,290,560);
 bins(s,{left:60,top:464,width:580,height:330},true);
 const den=A.density,max=Math.max(...den.y)*1.12;
 chart(s,'scatter',{position:{left:685,top:464,width:585,height:330},scatterOptions:{style:'line'},series:[{name:'个人概率密度',xValues:den.x,values:den.y,line:{fill:C.purple,width:3},marker:{symbol:'none'}},{name:'密度均值',xValues:[den.mean,den.mean],values:[0,max],line:{fill:C.orange,width:2,style:'dash'},marker:{symbol:'none'}}],xAxis:{...common.xAxis,min:0,max:12,majorUnit:4},yAxis:{...common.yAxis,min:0,max,numberFormatCode:'0.00'}});
 const arr=M.atoms;let cum=0,xs=[Math.min(-5,arr[0].x)],ys=[0];
 arr.forEach(a=>{xs.push(a.x,a.x);ys.push(cum*100,(cum+a.mass)*100);cum+=a.mass;});
 const hi=Math.max(22,arr.at(-1).x);xs.push(hi);ys.push(100);
 chart(s,'scatter',{position:{left:1304,top:464,width:550,height:330},scatterOptions:{style:'line'},series:[{name:'加权累计人口质量',xValues:xs,values:ys,line:{fill:C.blue,width:3},marker:{symbol:'none'}},{name:'50%人口质量',xValues:[-5,hi],values:[50,50],line:{fill:C.gray,width:1.5,style:'dash'},marker:{symbol:'none'}},{name:'全国加权中位数',xValues:[M.median,M.median],values:[0,100],line:{fill:C.orange,width:2,style:'dash'},marker:{symbol:'none'}}],xAxis:{...common.xAxis,min:-5,max:hi,majorUnit:5},yAxis:{...common.yAxis,min:0,max:100,majorUnit:50,numberFormatCode:'0"%"'}});
 tx(s,'prob-axis','通胀区间（%）',230,803,390,45,25,C.gray);tx(s,'density-axis','通胀（%）',865,803,350,45,25,C.gray);tx(s,'cdf-axis','各家庭的Q9密度均值（%）',1380,803,450,45,24,C.gray);
 tx(s,'Q8value',`Q8  ${A.q8.toFixed(1)}%`,84,865,520,75,53,C.purple,true);
 tx(s,'mean-value',`${den.mean.toFixed(2)}%  个人均值`,712,865,550,75,51,C.purple,true);
 tx(s,'national-value',`${M.median.toFixed(2)}%  全国中位数`,1340,865,500,75,49,C.purple,true);
 tx(s,'normal',`统计扩展支路：${M.n}份直接模拟 → ${M.frame_n}人口规模（τ = 8）；上图全国指标保留直接模拟口径。`,84,955,1735,42,25,C.gray);
}

await fs.mkdir(OUT,{recursive:true});await fs.mkdir(path.join(OUT,'slides'),{recursive:true});await fs.mkdir(path.join(BUILD,'validated'),{recursive:true});
const candidate=path.join(BUILD,`candidate_${iteration}.pptx`);await(await PresentationFile.exportPptx(p)).save(candidate);
const finalPath=path.join(BUILD,'validated',`samples_${iteration}.pptx`),receipt=path.join(BUILD,`validation_${iteration}.json`);
await finalizePresentation({workspaceDir:BUILD,candidatePath:candidate,finalPath,pythonExecutable:PY,
 integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','18288000,10287000','--validate-bullet-geometry','--validate-heading-fit'],explicitTotalSlideCount:3,requiredNativeChartOwnerSlides:[1,3],
 materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'user_request',families:[CN,EN]},verifyArtifactToolImport:true,receiptPath:receipt});
await fs.copyFile(finalPath,path.join(OUT,'SCE_samples_02_04_05_v02.pptx'));
const final=await PresentationFile.importPptx(await FileBlob.load(finalPath));
for(let i=0;i<3;i++){
 const blob=await final.export({slide:final.slides.items[i],format:'png',scale:1});
 await fs.writeFile(path.join(OUT,'slides',`page_${['02','04','05'][i]}.png`),new Uint8Array(await blob.arrayBuffer()));
}
await fs.writeFile(path.join(BUILD,'latest_build.json'),JSON.stringify({finalPath,receipt,iteration,slides:3},null,2));
console.log(JSON.stringify({slides:3,pptx:path.join(OUT,'SCE_samples_02_04_05_v02.pptx'),receipt}));
