import fs from 'node:fs/promises';import path from 'node:path';import {pathToFileURL} from 'node:url';import {createRequire} from 'node:module';import {execFileSync} from 'node:child_process';
import {Presentation,PresentationFile,FileBlob} from '@oai/artifact-tool';
const ROOT=process.env.SCE_PROJECT_ROOT||process.cwd(),BUILD=path.join(ROOT,'tmp/video_complete_v05'),OUT=path.join(ROOT,'deliverables/video/v05');
const SKILL='/Users/wushuyue/.codex/plugins/cache/openai-primary-runtime/presentations/26.1022.11436/skills/presentations',PY='/Users/wushuyue/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
process.env.RUNTIME_NODE_MODULES??='/Users/wushuyue/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const {finalizePresentation,applyPresentationChartFont}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')));
const req=createRequire(createRequire(import.meta.url).resolve('@oai/artifact-tool'));const {FontLibrary}=await import(pathToFileURL(req.resolve('skia-canvas')));
FontLibrary.use('Kaiti SC',[path.join(ROOT,'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf')]);
const D=JSON.parse(await fs.readFile(path.join(BUILD,'data.json'),'utf8')),story=JSON.parse(await fs.readFile(path.join(OUT,'storyboard.json'),'utf8'));
const CN='Kaiti SC',EN='Times New Roman',C={ink:'#203447',blue:'#2B5E87',purple:'#79578D',orange:'#B55823',gray:'#637481',rule:'#D9E2E8',soft:'#F3F6F9'};
const p=Presentation.create({slideSize:{width:1920,height:1080}});p.theme.defaultFont=CN;const stamp=new Date().toISOString().replace(/\D/g,'');
const runs=(text,size,color,bold)=>(text.match(/[\x00-\x7F]+|[^\x00-\x7F]+/g)||[]).map(run=>({run,style:{fontSize:`${size}px`,typeface:/^[\x00-\x7F]+$/.test(run)?EN:CN,color,bold}}));
function tx(s,name,text,x,y,w,h,size=28,color=C.ink,bold=false){const z=s.shapes.add({geometry:'textbox',name,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});z.text.style={fontSize:size,typeface:CN,color,bold,verticalAlignment:'top',wrap:'square',autoFit:'none',insets:{left:0,right:0,top:0,bottom:0}};z.text=text.split('\n').map(t=>({spaceAfter:Math.round(size*.3),runs:runs(t,size,color,bold)}));return z;}
function rule(s,name,x,y,w,h=0){return s.shapes.add({geometry:'connector',kind:'straight',name,position:{left:x,top:y,width:w,height:h},line:{fill:C.rule,width:1.5}});}
function slide(page,subtitle,sources){const s=p.slides.add();s.background.fill='#FFFFFF';tx(s,'title',story.slides[page-1].title,75,55,1770,82,55,C.ink,true);tx(s,'subtitle',subtitle,78,150,1740,58,29,C.gray);rule(s,'header',78,230,1764);tx(s,'footer','家庭画像与既有信念  →  可见环境  →  模拟答卷  →  全国指标与分布评价',80,1007,1570,40,23,C.gray);tx(s,'page',String(page).padStart(2,'0'),1760,1006,90,42,27,C.blue);s.speakerNotes.text=story.slides[page-1].narration+'\n\n来源与边界：'+sources+'\n本次仅制作演示，不重拟研究参数、不调用模型。';return s;}
const axis={line:{fill:C.rule,width:1},textStyle:{fontSize:24,fill:C.gray}};
function chart(s,type,cfg){cfg={...cfg,series:cfg.series.map(v=>({...v,values:v.values.map(x=>+x.toFixed(8)),...(v.xValues?{xValues:v.xValues.map(x=>+x.toFixed(8))}:{})}))};const ch=s.charts.add(type,{chartFill:'none',plotAreaFill:'none',chartLine:{fill:'none',width:0},plotAreaLine:{fill:'none',width:0},hasLegend:false,xAxis:axis,yAxis:{...axis,majorGridlines:{fill:'#E7EDF1',width:1}},...cfg});applyPresentationChartFont(ch,{fontFamily:CN});return ch;}
function table(s,name,values,x,y,w,h,widths){const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,columnWidths:widths,values});t.borders.assign({style:'solid',fill:C.rule,width:1});for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){let cell=t.getCell(r,c);cell.fill=r===0?C.soft:'#FFFFFF';cell.text.style={typeface:r>0&&c>0&&/^[0-9.]+$/.test(String(values[r][c]))?EN:CN,fontSize:r===0?27:29,bold:r===0,color:C.ink,verticalAlignment:'middle',wrap:'square',autoFit:'none',insets:{left:13,right:10,top:10,bottom:10}};}return t;}

// 5: named data sources and actual conditional-information evidence.
{
 const s=slide(5,'人口差异来自调查记录，补充属性按相似家庭的分布合成匹配','SCE公开微观；CE消费者支出调查；ATUS 2022饮食健康模块采购责任；Gallup联储主席信心。ATUS用于历史A是外部结构假设，不称本人实测。网格结果：sce_grid_dimensions_20261023_v1/summary.json，2019—2022按受访者四折；126套候选、整块移除重拟，四领域标准化月内损失。图展示Q9概率宽度领域；数理3.2381、学历1.5233、收入0.7160个标准化损失百分点。年龄另对填法有0.7040信息，综合生命阶段/资源含义与抽样支持选54格，不宣称PCA或唯一最优。调整GVIF范围1.0074—1.1860。');
 tx(s,'sources-head','资料来源与字段',80,287,780,60,36,C.blue,true);rule(s,'source-divider',900,285,0,673);
 tx(s,'SCE','纽约联储 SCE 消费者预期调查',80,365,790,45,31,C.blue,true);tx(s,'SCE-fields','年龄、学历、收入、就业、住房、数理与地区\n本人既往通胀答卷作为历史信念',82,422,780,88,28);
 rule(s,'source-rule',80,532,775);
 tx(s,'CE','美国BLS：CE消费者支出调查',80,563,790,45,30,C.orange,true);tx(s,'CE-fields','匹配食品、燃油、住房等支出份额',82,616,775,42,27);
 tx(s,'ATUS','美国BLS／USDA：ATUS时间使用调查',80,694,790,45,30,C.orange,true);tx(s,'ATUS-fields','按家庭构成、年龄等分配合成采购角色',82,747,775,42,27);
 tx(s,'Gallup','盖洛普 Gallup 调查',80,827,790,45,30,C.orange,true);tx(s,'Gallup-fields','匹配对美联储主席的信心分布',82,880,775,42,27);
 tx(s,'grid-head','分组依据：独立信息与代表性',953,287,885,60,36,C.blue,true);
 tx(s,'grid-validation','比较126套候选，按受访者留出验证，另查变量冗余。',955,361,875,64,28);
 tx(s,'loss-title','移除变量后，概率宽度预测损失增加',957,439,870,40,27,C.gray);
 chart(s,'bar',{position:{left:944,top:497,width:900,height:243},categories:['数理','学历','收入'],series:[{name:'标准化损失增加',values:['numeracy','education','income'].map(k=>D.grid_conditionals[k].uncertainty),fill:C.blue}],barOptions:{direction:'column',grouping:'clustered',gapWidth:110},yAxis:{...axis,min:0,max:4,majorUnit:1,numberFormatCode:'0.0'},dataLabels:{showValue:true,showCategoryName:false,showSeriesName:false,position:'outEnd',numberFormatCode:'0.00',textStyle:{fontSize:28,fill:C.blue}}});
 tx(s,'loss-note','单位：标准化损失百分点，越大表示独立信息越多。',958,760,880,40,24,C.gray);
 tx(s,'age','年龄另补充生命周期与概率填法的信息。',956,817,880,43,28);
 tx(s,'grid-formula','学历3 × 数理2 × 年龄3 × 收入3 ＝ 54类',955,873,890,51,32,C.blue,true);
 tx(s,'sampling','每月约512份模型答卷：稀有类别多抽，汇总按人口权重恢复原比例。',82,954,1750,39,26,C.gray);
}
// 6: common response behavior, with reconstruction and simulated prediction prior contracts.
{
 const s=slide(6,'既有判断提供起点，可见环境提供更新信息，两条路线使用同一作答程序','本人历史优先；A缺失起点用最近1—3个月联合供体；B按公开滞后规则选择微观样本，联合Q8/Q9起点按最新公开全国Q9中位数±0.05pp约束。B人口/数值先验按月全局D准备，合成个人日期只进一步限制E；不称严格逐人事前认证。模型为OpenRouter→固定SiliconFlow FP8 DeepSeek V3.2，温度0.5，关闭思考，结构占位示例无数值。');
 tx(s,'history-head','历史重建',80,291,800,56,39,C.blue,true);tx(s,'history-period','2019-01—2025-10',82,365,790,42,29,C.gray);
 tx(s,'history-prior','历史起点：本人前期Q8、Q9与更早摘要\n历史缺失：从最近1—3个月相似家庭抽取\n环境截止：实际作答日前一天',82,441,800,169,31);
 rule(s,'contracts-divider',945,290,0,324);
 tx(s,'forecast-head','模拟预测',995,291,830,56,39,C.purple,true);tx(s,'forecast-period','2025-11—2026-09',997,365,825,42,29,C.gray);
 tx(s,'forecast-prior','家庭与先验：按发布滞后规则选取调查样本\n中心校准：对齐最新已公开的全国Q9水平\n环境截止：按历史作答日分布合成并封顶',997,441,830,169,30);
 rule(s,'behavior-rule',80,656,1755);
 tx(s,'behavior-head','统一模拟作答',80,705,1735,56,36,C.blue,true);
 tx(s,'model-settings','DeepSeek V3.2，温度0.5，关闭思考',82,783,1735,52,32);
 tx(s,'update','更新规则：允许保持、上调或下调，不预设方向与幅度。',82,851,1735,47,30);
 tx(s,'answer','回答内容：Q8点预测＋Q9十档概率，保留JSON与简短理由。',82,914,1735,47,30);
 tx(s,'truth-boundary','目标月真人答案只进入评价。模拟预测采用回顾性时点回测，时间资格和模型知识限制详报告。',82,970,1735,31,23,C.gray);
}
// 7: fewer scattered production counters, one visible execution path.
{
 const s=slide(7,'正式模型生成与评价分开，现场复算已有封存结果','A82正式生成41,970个合格个人月，41,788新主＋241技术补、182相同Prompt复用。演示run.py --mode all是20户×2步规则例＋封存全国聚合复算，非重新生成真人模型回答或全微观密度重拟。record_demo.command仍沿用v01入口，0API。');
 const cols=[80,685,1290];const heads=['① 独立生成','② 逐条存档','③ 独立评价'];
 const bodies=['冻结人口、环境、提示与预算\n按队列调用模型，记录技术失败','保存完整Prompt与原始回答\n保留模型、token、费用及补跑收据','读取封存答卷和评价真值\n按同一计分口径计算误差与分布'];
 for(let i=0;i<3;i++){tx(s,'step-head-'+i,heads[i],cols[i],298,545,61,37,C.blue,true);tx(s,'step-body-'+i,bodies[i],cols[i]+2,388,545,146,29);if(i<2)rule(s,'step-separator-'+i,cols[i]+570,292,0,291);}
 rule(s,'run-command-rule',80,622,1750);
 tx(s,'entry-head','研究包统一复算入口',80,673,1735,54,35,C.blue,true);
 tx(s,'command','python studies/sce_inflation_expectations/run.py --mode all --out <新目录>',82,749,1735,65,30);
 tx(s,'demo-definition','现场小例：20户、2步；同时复算封存全国指标，输出结果页和执行收据。',82,838,1735,50,29);
 tx(s,'production-summary','正式生成覆盖82个月、41,970个个人月；本次现场复算的模型API调用为0。',82,926,1735,54,31,C.orange,true);
}
// 8: full-period frozen combination and persistence, with clear national/micro scales.
{
 const s=slide(8,'全国指标看MAE，人群结构另看W1与IQR，持续性基线始终并列','主图仍为每月约512份直接LLM答卷的校准加权指标，非Normal口径。A82_personal_T0.csv、B11_latest_Core_and_Normal.csv。λ=.1339762571517809由2019—2022前48月MSE拟定，整段曲线应用同一固定λ，未重拟。A全期固定组合MAE.2224644567含拟权样本，不称全期独立样本外。后34月raw.214613、blend.184125、anchor.194118；Braw.348509、blend.144277、anchor.172727。微观W1/IQR只在41,042个共同合法A答卷，同权重同近似算法，W1为2.219218、IQR2.247712、人类5.260960。全国线性组合没有对应个人分布，不给组合编造W1/IQR。B为回顾性模拟预测，缺真实近期微观，不给W1/IQR。');
 const year=m=>{m=m.replace('-','');return +m.slice(0,4)+(+m.slice(4)-1)/12;};const ax=D.A.map(r=>year(r.month)),bx=D.B.map(r=>year(r.month));
 const xx=[...ax,...bx],truth=[...D.A.map(r=>+r.truth_pp),...D.B.map(r=>+r.truth_pp)];
 const raw=[...D.A.map(r=>+r.sim_pp),...D.B.map(r=>+r.Core_pp)],combo=[...D.A.map(r=>+r.fixed_blend_pp),...D.B.map(r=>+r.Core_blend_pp)],baseline=[...D.A.map(r=>+r.anchor_pp),...D.B.map(r=>+r.baseline_pp)];
 const seq=(name,values,color,dash=false)=>({name,xValues:xx,values,line:{fill:color,width:3.2,style:dash?'dash':'solid'},marker:{symbol:'none'},smooth:false});
 tx(s,'plot-unit','通胀预期（%）',82,282,970,41,25,C.gray);
 chart(s,'scatter',{position:{left:62,top:339,width:1020,height:500},hasLegend:true,scatterOptions:{style:'line'},series:[seq('真实SCE',truth,C.ink),seq('原始模拟',raw,C.blue),seq('固定组合',combo,C.orange),seq('持续性基线',baseline,C.purple,true),{name:'阶段分界',xValues:[2025+10/12,2025+10/12],values:[2,8.2],line:{fill:C.gray,width:1.3,style:'dash'},marker:{symbol:'none'}}],xAxis:{...axis,min:2019,max:2026.75,majorUnit:1,numberFormatCode:'0'},yAxis:{...axis,min:2,max:8.2,majorUnit:1,numberFormatCode:'0.0',majorGridlines:{fill:'#E7EDF1',width:1}},legend:{position:'bottom',overlay:false,textStyle:{fontSize:23,fill:C.ink}}});
 tx(s,'phase-A','历史重建',84,866,510,43,28,C.blue,true);tx(s,'phase-B','模拟预测',884,866,220,43,28,C.purple,true);
 tx(s,'frozen-rule','固定组合＝13.4%模拟＋86.6%最新已公开SCE。',83,925,1000,40,26,C.gray);
 tx(s,'direct-scope','主图采用每月约512份直接模型答卷的加权结果。',83,965,1000,30,23,C.gray);
 rule(s,'metric-divider',1117,280,0,687);
 tx(s,'mae-head','全国MAE（百分点，越低越好）',1170,284,670,54,31,C.blue,true);
 const f=n=>n.toFixed(3),m=D.metrics;
 table(s,'national-mae',[
  ['时间范围','原始模拟','固定组合','持续性'],
  ['重建：82个月',f(m.A_raw),f(m.A_blend),f(m.A_baseline)],
  ['后34个月检查',f(m.late_raw),f(m.late_blend),f(m.late_baseline)],
  ['预测：11个月',f(m.B_raw),f(m.B_blend),f(m.B_baseline)]
 ],1165,366,680,253,[245,145,145,145]);
 tx(s,'fit-period','前48月定权，后34月固定检查。\n全期组合含拟权期，不作全期样本外声明。',1170,646,665,80,25,C.gray);
 tx(s,'micro-head','历史重建：跨家庭分布',1170,750,665,45,30,C.blue,true);
 table(s,'micro',[
  ['指标（百分点）','原始模拟','真人参照'],
  ['W1分布距离',f(m.w1),'参照分布'],
  ['IQR中间50%宽度',f(m.iqr),f(m.real_iqr)]
 ],1165,813,680,150,[300,190,190]);
 tx(s,'scope','微观仅历史段同批答卷；预测段无真人微观。',1170,973,665,27,22,C.gray);
}

await fs.mkdir(path.join(BUILD,'validated'),{recursive:true});await fs.mkdir(path.join(OUT,'slides'),{recursive:true});
const cand=path.join(BUILD,'edited_'+stamp+'.pptx');await(await PresentationFile.exportPptx(p)).save(cand);
const v={workspaceDir:BUILD,pythonExecutable:PY,integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','18288000,10287000','--validate-bullet-geometry','--validate-heading-fit'],fontPolicy:{basis:'user_request',families:[CN,EN]},verifyArtifactToolImport:true};
const stage=path.join(BUILD,'validated','edited_'+stamp+'.pptx');await finalizePresentation({...v,layoutArgs:[...v.layoutArgs,'--require-native-table-slide','4'],candidatePath:cand,finalPath:stage,explicitTotalSlideCount:4,requiredNativeChartOwnerSlides:[1,4],requiredNativeTableOwnerSlides:[4],materializeLiteralChartWorkbooks:true,receiptPath:path.join(BUILD,'edited_validation_'+stamp+'.json')});
const merged=path.join(BUILD,'merged_'+stamp+'.pptx'),preservation=path.join(BUILD,'preservation_'+stamp+'.json');execFileSync(PY,[path.join(ROOT,'studies/sce_inflation_expectations/reports/video_complete_v05/replace_slides.py'),path.join(BUILD,'author_deck.pptx'),stage,merged,preservation],{stdio:'pipe'});
const finalPath=path.join(BUILD,'validated','complete_'+stamp+'.pptx'),receipt=path.join(BUILD,'validation_'+stamp+'.json');await finalizePresentation({...v,layoutArgs:[...v.layoutArgs,'--require-native-table-slide','8'],candidatePath:merged,finalPath,explicitTotalSlideCount:9,requiredNativeChartOwnerSlides:[2,3,5,8,9],requiredNativeTableOwnerSlides:[8],materializeLiteralChartWorkbooks:false,receiptPath:receipt});
await fs.copyFile(finalPath,path.join(OUT,'SCE_video_complete_v05.pptx'));
const preview=path.join(BUILD,'preview_'+stamp+'.pptx');execFileSync(PY,[path.join(ROOT,'studies/sce_inflation_expectations/reports/video_complete_v04/render_copy.py'),finalPath,preview,path.join(BUILD,'preview_compatibility_'+stamp+'.json')],{stdio:'pipe'});
const final=await PresentationFile.importPptx(await FileBlob.load(preview));for(let i=0;i<9;i++){const b=await final.export({slide:final.slides.items[i],format:'png',scale:1});await fs.writeFile(path.join(OUT,'slides','page_'+String(i+1).padStart(2,'0')+'.png'),new Uint8Array(await b.arrayBuffer()));}
for(const i of [4,5,6,7]){const l=await final.slides.items[i].export({format:'layout'});await fs.writeFile(path.join(BUILD,'page'+(i+1)+'.layout.json'),await l.text());}
await fs.writeFile(path.join(BUILD,'latest_build.json'),JSON.stringify({finalPath,receipt,preservation,stamp},null,2));console.log(JSON.stringify({finalPath,edited_pages:[5,6,7,8],protected_pages:[1,2,3,4,9]}));
