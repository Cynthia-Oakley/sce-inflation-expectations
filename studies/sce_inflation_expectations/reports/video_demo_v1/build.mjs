import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { Presentation, PresentationFile } from '@oai/artifact-tool';
const ROOT=process.env.SCE_PROJECT_ROOT||process.cwd();
const OUT=path.join(ROOT,'deliverables/video/v01'),BUILD=path.join(ROOT,'tmp/video_demo_v1');
const SKILL='/Users/wushuyue/.codex/plugins/cache/openai-primary-runtime/presentations/26.1022.11436/skills/presentations';
const PY='/Users/wushuyue/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
const {finalizePresentation,applyPresentationChartFont}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
const d=JSON.parse(await fs.readFile(path.join(BUILD,'data.json'),'utf8'));
const story=JSON.parse(await fs.readFile(path.join(OUT,'storyboard.json'),'utf8'));
const C={ink:'#203447',blue:'#245D7D',orange:'#B45316',purple:'#7C588F',gray:'#697782',rule:'#D5DFE5',paper:'#FFFFFF',paleBlue:'#EFF5F9',paleOrange:'#FCF3EA',palePurple:'#F4F0F7',true:'#202A32'};
const CN='Kaiti SC',EN='Times New Roman';
const iteration=new Date().toISOString().replace(/[^0-9]/g,'');
const p=Presentation.create({slideSize:{width:1920,height:1080}});p.theme.defaultFont=CN;
const sourceNotes=['v10 §§1–2 and archived real anonymous June-2025 illustration','v10 §§3–5, current 54-grid and final T0 configuration','v05 study run.py --mode all; 20 scripted agents, 2 steps; archived national aggregate replay','v10 §6; A82_personal_T0.csv; 48/34 chronological combination','v10 §§6–7; B11_latest_Core_and_Normal.csv; historical common-support micro metrics','v10 §8; weekly47_path.csv and weekly47_monthly11_primary.csv','v10 §9; downstream_contrasts.csv; historical A expanding-window regressions','v10 §10; conclusions and limits'];
function runParts(s,size,color,bold=false){return (s.match(/[\x00-\x7F]+|[^\x00-\x7F]+/g)||[]).map(run=>({run,style:{typeface:/^[\x00-\x7F]+$/.test(run)?EN:CN,fontSize:`${size}px`,color,bold}}));}
function text(sl,name,s,x,y,w,h,size=36,color=C.ink,bold=false,align='left'){
 const sh=sl.shapes.add({geometry:'textbox',name,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 sh.text.style={typeface:CN,fontSize:size,color,bold,alignment:align,verticalAlignment:'top',wrap:'square',autoFit:'none',insets:{left:0,right:0,top:0,bottom:0}};
 sh.text=s.split('\n').map(line=>({spaceBefore:0,spaceAfter:Math.round(size*.18),runs:runParts(line,size,color,bold)}));return sh;
}
function rect(sl,name,x,y,w,h,fill,stroke=C.rule){return sl.shapes.add({geometry:'rect',name,position:{left:x,top:y,width:w,height:h},fill,line:{fill:stroke,width:stroke==='none'?0:1.6}});}
function line(sl,name,x,y,w,color=C.rule,ww=1.5){return sl.shapes.add({geometry:'connector',kind:'straight',name,position:{left:x,top:y,width:w,height:0},line:{fill:color,width:ww}});}
function arrow(sl,name,x,y,w,color=C.blue){return sl.shapes.add({geometry:'connector',kind:'straight',name,position:{left:x,top:y,width:w,height:0},line:{fill:color,width:3},tail:{type:'triangle',width:'med',length:'med'}});}
function addSlide(i,title,subtitle=''){
 const sl=p.slides.add();sl.background.fill=C.paper;
 text(sl,'title',title,72,58,1760,90,58,C.ink,true);
 if(subtitle)text(sl,'subtitle',subtitle,76,158,1740,65,30,C.gray);
 line(sl,'header-rule',76,237,1768);
 text(sl,'page',String(i).padStart(2,'0'),1768,1008,78,40,24,C.gray,false,'right');
 text(sl,'source-foot','水上挽月  SocioVerse Challenge 2026',76,1008,1400,42,23,C.gray);
 sl.speakerNotes.text=story.slides[i-1].narration+'\n\n录制：'+story.slides[i-1].seconds+'秒。'+story.slides[i-1].visual+'\n来源：'+sourceNotes[i-1]+'。数据单位与时期见画面，不把不同路径视为单一机制因果对照。';return sl;
}
const chartCommon={lineOptions:{smooth:false},chartFill:'none',plotAreaFill:'none',chartLine:{fill:'none',width:0},plotAreaLine:{fill:'none',width:0},hasLegend:true,legend:{position:'bottom',overlay:false,textStyle:{fontSize:27,fill:C.ink}},xAxis:{line:{fill:C.rule,width:1},textStyle:{fontSize:23,fill:C.gray}},yAxis:{numberFormatCode:'0.0',line:{fill:'none',width:0},majorGridlines:{fill:'#E8EDF0',width:1,style:'solid'},textStyle:{fontSize:25,fill:C.gray}}};
function chart(sl,kind,cfg){cfg={...cfg,series:cfg.series.map(s=>({...s,values:s.values.map(v=>v===null?v:Number(v.toFixed(8))),...(s.xValues?{xValues:s.xValues.map(v=>Number(v.toFixed(8)))}:{})}))};const ch=sl.charts.add(kind,{...chartCommon,...cfg});applyPresentationChartFont(ch,{fontFamily:CN});return ch;}
function series(name,values,color,dash=false,marker='none'){color=color===C.blue?'#3178A7':color;return {name,values,smooth:false,line:{fill:color,width:3.6,style:dash?'dash':'solid'},marker:{symbol:marker,size:9,fill:color},fill:color};}
function metric(sl,label,value,x,y,color=C.blue,w=450){text(sl,'metric-label-'+label,label,x,y,w,50,30,C.gray);text(sl,'metric-value-'+label,value,x,y+57,w,110,70,color,true);}
// 01 Real survey example. Editable bars preserve the supplied ten probabilities.
{
 const s=addSlide(1,'居民通胀预期的生成式社会模拟','家庭怎样判断未来一年的物价？');
 text(s,'question','让模型填写真实问卷\n同时观察全国水平与家庭差异',76,310,690,165,46,C.ink,true);
 text(s,'q8','Q8  给出一个预测数值',80,550,700,60,34,C.blue,true);
 text(s,'q8-value','这份答卷：3.2%',80,618,680,70,43,C.ink);
 text(s,'q9','Q9  把100%概率分到十个区间',80,746,710,65,34,C.orange,true);
 text(s,'individual','单份答卷示例，2025年6月',900,295,870,50,31,C.gray);
 chart(s,'bar',{position:{left:850,top:365,width:1000,height:480},categories:['≤−12','−12~-8','−8~-4','−4~-2','−2~0','0~2','2~4','4~8','8~12','≥12'],series:[{name:'概率',values:d.q9_example.q9_probabilities_ascending_pct,fill:C.orange,line:{fill:'none',width:0}}],hasLegend:false,barOptions:{direction:'column',gapWidth:55},yAxis:{...chartCommon.yAxis,min:0,max:45,majorUnit:10,numberFormatCode:'0"%"'},xAxis:{...chartCommon.xAxis,textStyle:{fontSize:22,fill:C.gray}},dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0"%"',textStyle:{fontSize:25,fill:C.ink}}});
 text(s,'chart-x-unit','未来12个月价格变化区间（%）',1000,869,800,50,27,C.gray,false,'center');
 text(s,'point-density','同一份答卷的密度均值约3.03%，与点预期可以不同',80,935,1700,52,28,C.gray);
}
// 02 Native editable P/E/B diagram. Shape text lives inside its own box.
{
 const s=addSlide(2,'家庭背景与可见信息共同进入答卷','设计依据：信念持续性、有限注意与生活价格体验');
 function box(name,title,body,x,y,w,h,fill,color){const sh=rect(s,name,x,y,w,h,fill);sh.text.style={typeface:CN,fontSize:33,color:C.ink,verticalAlignment:'top',wrap:'square',autoFit:'none',insets:{left:24,right:20,top:20,bottom:15}};sh.text=[{spaceAfter:18,runs:runParts(title,39,color,true)},...body.map(t=>({spaceAfter:12,runs:runParts(t,31,C.ink)}))];return sh;}
 box('population','家庭背景与既有信念',['学历 × 数理 × 年龄 × 收入，共54类','每月约512户，小群体多抽','汇总恢复人口比例','本人历史，或近期相似家庭答卷'],76,292,580,280,C.paleBlue,C.blue);
 box('environment','个人可见的信息',['新闻量随机4/8/16/32篇，主题按人匹配','通胀高相关新闻抽样权重 ×1.5','食品细项价格结合采购角色','新闻与政策只取作答前已公开信息'],76,590,580,305,C.paleOrange,C.orange);
 box('behavior','模型填写问卷',['DeepSeek V3.2','温度0.5，关闭思考','固定SiliconFlow FP8','Q8点预期与Q9十档概率'],784,434,420,330,C.palePurple,C.purple);
 box('aggregate','计分与人口汇总',['Q9连续密度的个人均值','按人口权重取全国中位数','Q8独立汇总','统计扩展τ=8，补齐人口规模'],1332,434,510,330,C.paleBlue,C.blue);
 arrow(s,'P-to-B',656,475,128,C.blue);arrow(s,'E-to-B',656,715,128,C.orange);arrow(s,'B-to-summary',1204,600,128,C.purple);
 text(s,'basis','开发依据：126套人口网格候选，新闻量、主题与信息截止的多轮对照',80,934,1740,48,29,C.gray);
}
// 03 Actual runnable workflow. This slide can bridge into the user's recording.
{
 const s=addSlide(3,'可执行的研究流程与结果追溯','现场演示不消耗模型API费用');
 const xs=[90,730,1370],titles=['读取研究配置','执行工程示例与复算','查看新输出与收据'];
 const bodies=['人口、环境与问卷设置\n标准study与README','20户、2步的规则工程示例\n已封存全国指标离线复算','运行成功与本次输出路径\n逐月指标、模型与基线'];
 xs.forEach((x,i)=>{text(s,'step-'+i,String(i+1).padStart(2,'0'),x,330,220,100,80,[C.blue,C.purple,C.orange][i],true);text(s,'step-title-'+i,titles[i],x,465,500,75,40,C.ink,true);text(s,'step-body-'+i,bodies[i],x,574,500,150,33,C.gray);if(i<2)arrow(s,'step-arrow-'+i,x+500,510,105,C.blue);});
 line(s,'workflow-bottom',90,815,1740);
 text(s,'archived','正式模型答卷已在此前生成，配置、运行数量、费用与技术补跑均有归档',90,857,1730,95,34,C.ink);
}
// 04 Historical nationwide path, 2021 inset, and chronological blend result.
{
 const s=addSlide(4,'历史重建缓解了部分高通胀期低估','2019年1月至2025年10月，82个月，41,970个合格个人月');
 const ax=d.A.map(r=>Number(r.month.slice(0,4))+(Number(r.month.slice(5))-1)/12);
 text(s,'A-unit','通胀预期（%）',80,269,600,42,25,C.gray);
 chart(s,'scatter',{position:{left:62,top:315,width:1260,height:553},scatterOptions:{style:'line'},series:[{...series('真实SCE',d.A.map(r=>r.truth_pp),C.true),xValues:ax},{...series('原始模拟',d.A.map(r=>r.sim_pp),C.blue),xValues:ax},{...series('已公布历史值',d.A.map(r=>r.anchor_pp),C.gray,true),xValues:ax}],yAxis:{...chartCommon.yAxis,min:2,max:8,majorUnit:1},xAxis:{...chartCommon.xAxis,min:2019,max:2025.75,majorUnit:1,numberFormatCode:'0'}});
 const a21=d.A.filter(r=>r.month.startsWith('2021'));
 text(s,'inset-title','2021年：上行仍跟随不足',1370,293,485,56,34,C.orange,true);
 chart(s,'line',{position:{left:1340,top:370,width:530,height:320},categories:a21.map(r=>r.month.slice(5)),series:[series('真实',a21.map(r=>r.truth_pp),C.true),series('模拟',a21.map(r=>r.sim_pp),C.blue)],hasLegend:false,yAxis:{...chartCommon.yAxis,min:2,max:7,majorUnit:1,textStyle:{fontSize:22,fill:C.gray}}});
 text(s,'A-numbers','全期MAE（百分点）\n原始模拟 0.298\n历史参照 0.223',1390,735,450,164,32,C.ink);
 text(s,'A-holdout','早48个月拟权，后34个月检查：组合MAE 0.184，历史参照0.194',80,929,1730,52,30,C.blue,true);
}
// 05 Recent monthly path and fixed combination, historical micro as a clearly labelled diagnostic.
{
 const s=addSlide(5,'近期组合降低全国中心误差','2025年11月至2026年9月，11个月，沿用历史拟合的组合比例');
 text(s,'B-unit','通胀预期（%）',80,269,600,42,25,C.gray);
 chart(s,'line',{position:{left:62,top:325,width:1110,height:510},categories:d.B.map(r=>r.month.slice(4,6)),series:[series('真实SCE',d.B.map(r=>r.truth_pp),C.true),series('原始模拟',d.B.map(r=>r.Core_pp),C.blue),series('固定组合',d.B.map(r=>r.Core_blend_pp),C.orange)],yAxis:{...chartCommon.yAxis,min:2.8,max:4.8,majorUnit:.5}});
 text(s,'b-mae-title','全国MAE（百分点）',1280,300,535,60,34,C.ink,true);
 chart(s,'bar',{position:{left:1200,top:390,width:670,height:420},categories:['原始模拟','固定组合','历史参照','SCE+CPI'],series:[{name:'MAE',values:[d.metrics.B_raw,d.metrics.B_blend,d.metrics.B_baseline,d.metrics.B_macro],fill:C.blue,points:[{idx:1,fill:C.orange},{idx:2,fill:C.gray},{idx:3,fill:'#AAA8A1'}]}],hasLegend:false,barOptions:{direction:'bar',gapWidth:90},xAxis:{...chartCommon.xAxis,textStyle:{fontSize:28,fill:C.ink}},yAxis:{...chartCommon.yAxis,min:0,max:.4,majorUnit:.1},dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0.000',textStyle:{fontSize:28,fill:C.ink}}});
 text(s,'blend-weight','组合：约13.4%模拟 + 86.6%历史值',85,853,1740,60,37,C.orange,true);
 text(s,'micro-diagnostic','历史微观诊断：跨人IQR为模型2.248、真人5.261，W1为2.219pp。统计扩展不增加独立判断。',85,935,1735,60,27,C.gray);
}
// 06 Weekly trajectory evaluated against monthly targets, no invented weekly truth.
{
 const s=addSlide(6,'周度更新提供了月内变化线索','固定300户，47个周五，新的历史SCE公布后校准起点');
 const truthMap=new Map(d.weekly_monthly.map(r=>[r.month,r.truth_pp]));
 text(s,'weekly-unit','通胀预期（%）',80,269,600,42,25,C.gray);
 const excel=r=>Math.round((Date.parse(r.cutoff.slice(0,10)+'T00:00:00Z')-Date.UTC(1899,11,30))/86400000);
 const last=d.weekly.filter((r,i)=>i===d.weekly.length-1||d.weekly[i+1].month!==r.month);
 const reset=d.weekly.filter(r=>r.reset_required==='True');
 chart(s,'scatter',{position:{left:64,top:310,width:1270,height:560},scatterOptions:{style:'lineWithMarkers'},series:[{...series('每周原始模拟',d.weekly.map(r=>r.q9_median_pp),C.blue),xValues:d.weekly.map(excel)},{name:'月度调查真值',values:last.map(r=>truthMap.get(r.month)),xValues:last.map(excel),line:{fill:'none',width:0},marker:{symbol:'diamond',size:13,fill:C.true}},{name:'公开值发布后校准',values:reset.map(r=>r.q9_median_pp),xValues:reset.map(excel),line:{fill:'none',width:0},marker:{symbol:'circle',size:9,fill:C.orange}}],yAxis:{...chartCommon.yAxis,min:2.8,max:4.2,majorUnit:.2},xAxis:{...chartCommon.xAxis,min:excel(d.weekly[0]),max:excel(d.weekly.at(-1)),majorUnit:56,numberFormatCode:'yy-mm-dd',textStyle:{fontSize:22,fill:C.gray}}});
 metric(s,'月末原始MAE（百分点）','0.152',1390,320,C.blue);metric(s,'历史参照MAE','0.173',1390,520,C.gray);
 text(s,'weekly-n','5 / 11 个月改善\n9月仍漏判上行',1390,760,440,140,35,C.orange,true);
 text(s,'monthly-motivation','月度自主链后五期MAE升至0.500。周度结果来自另一配置，不能单独归因于更新频率。',85,935,1735,60,27,C.gray);
}
// 07 Credit horizon evidence. Percent improvements are ratios, not pp.
{
 const s=addSlide(7,'循环信贷预测出现局部增量','历史A段，未来1—3个月累计增长，相对同结构官方SCE回归');
 chart(s,'line',{position:{left:90,top:310,width:1240,height:570},categories:['未来1个月','未来2个月','未来3个月'],series:[{...series('原始月度模拟',[3.55,8.17,1.69],C.blue,false,'circle'),dataLabels:{showValue:true,position:'top',numberFormatCode:'0.00"%"',textStyle:{fontSize:31,fill:C.blue}}},{...series('组合指标',[-3.18,5.03,4.80],C.orange,false,'square'),dataLabels:{showValue:true,position:'bottom',numberFormatCode:'0.00"%"',textStyle:{fontSize:28,fill:C.orange}}},series('官方SCE参照',[0,0,0],C.gray,true)],yAxis:{...chartCommon.yAxis,min:-5,max:10,majorUnit:5,numberFormatCode:'0"%"'}});
 metric(s,'未来2个月RMSE降低','8.17%',1380,370,C.blue);
 text(s,'credit-comparison','同结构回归中的\n局部用途线索',1380,610,460,150,39,C.ink,true);
 text(s,'credit-boundary','其他结局没有一致改善，信贷的历史均值基线仍然更强。',90,936,1725,60,31,C.gray);
}
// 08 Close on specific contributions and future directions.
{
 const s=addSlide(8,'可追溯的框架与明确的改进方向','居民通胀预期的生成式社会模拟');
 const items=[['机制','家庭背景、既有信念与可见信息共同约束答卷',C.blue],['发现','近期组合、周度更新与循环信贷提供局部价值',C.orange],['方向','异常时期跟随不足，家庭之间的分歧仍偏窄',C.purple]];
 items.forEach(([tag,body,color],i)=>{const y=320+i*155;text(s,'close-tag-'+i,tag,90,y,220,90,48,color,true);text(s,'close-body-'+i,body,340,y+4,1470,95,42,C.ink);line(s,'close-rule-'+i,90,y+116,1720,C.rule);});
 text(s,'limits','回顾性研究。旧人口匹配、历史文本版本与模型知识仍有边界。',90,848,1730,60,30,C.gray);
 text(s,'deliver','代码、配置、运行记录与复算入口随研究包提供',90,933,1730,58,34,C.blue,true);
}
await fs.mkdir(path.join(OUT,'slides'),{recursive:true});
const candidate=path.join(BUILD,`candidate_${iteration}.pptx`);await (await PresentationFile.exportPptx(p)).save(candidate);
await fs.mkdir(path.join(BUILD,'validated'),{recursive:true});
const finalPath=path.join(BUILD,'validated',`SCE_video_${iteration}.pptx`);
const result=await finalizePresentation({workspaceDir:ROOT,candidatePath:candidate,finalPath,pythonExecutable:PY,integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','18288000,10287000','--validate-bullet-geometry','--validate-heading-fit'],explicitTotalSlideCount:8,requiredNativeChartOwnerSlides:[1,4,5,6,7],materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'user_request',families:[CN,EN]},verifyArtifactToolImport:true,receiptPath:path.join(BUILD,`validation_${iteration}.json`)});
await fs.copyFile(finalPath,path.join(OUT,'SCE_video_presentation_v01.pptx'));
for(const [i,sl] of p.slides.items.entries()){
 const buf=await p.export({slide:sl,format:'png',scale:1});await fs.writeFile(path.join(OUT,'slides',`slide_${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await buf.arrayBuffer()));
 const lay=await sl.export({format:'layout'});await fs.writeFile(path.join(BUILD,`slide_${i+1}.layout.json`),await lay.text());
}
const montage=await p.export({format:'webp',montage:true});await fs.writeFile(path.join(BUILD,'montage.webp'),new Uint8Array(await montage.arrayBuffer()));
await fs.writeFile(path.join(BUILD,'latest_build.json'),JSON.stringify({finalPath,receipt:result.receiptPath,slides:p.slides.items.length},null,2));
console.log(JSON.stringify({finalPath,slides:p.slides.items.length,validationPassed:true}));
