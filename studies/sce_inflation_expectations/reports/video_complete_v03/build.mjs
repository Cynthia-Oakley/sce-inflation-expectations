import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createRequire} from 'node:module';
import {PresentationFile,FileBlob} from '@oai/artifact-tool';

const ROOT=process.env.SCE_PROJECT_ROOT||process.cwd(),OUT=path.join(ROOT,'deliverables/video/v03'),BUILD=path.join(ROOT,'tmp/video_complete_v03');
const SKILL='/Users/wushuyue/.codex/plugins/cache/openai-primary-runtime/presentations/26.1022.11436/skills/presentations',PY='/Users/wushuyue/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
process.env.RUNTIME_NODE_MODULES??='/Users/wushuyue/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const {finalizePresentation,applyPresentationChartFont}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
// Register the exact locally available Kaiti SC, for previews only. Do not
// substitute a different family or embed a licensed font into the deliverable.
const artifactRequire=createRequire(createRequire(import.meta.url).resolve('@oai/artifact-tool'));
const {FontLibrary}=await import(pathToFileURL(artifactRequire.resolve('skia-canvas')).href);
FontLibrary.use('Kaiti SC',[process.env.SCE_KAITI_FONT||path.join(ROOT,'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf')]);
const D=JSON.parse(await fs.readFile(path.join(BUILD,'data.json'),'utf8')),story=JSON.parse(await fs.readFile(path.join(OUT,'storyboard.json'),'utf8'));
// Import the approved native sample deck rather than rewriting those three pages.
const p=await PresentationFile.importPptx(await FileBlob.load(path.join(BUILD,'source_for_import.pptx')));
const original=[...p.slides.items],order={2:original[0],4:original[1],5:original[2]};
const CN='Kaiti SC',EN='Times New Roman',C={ink:'#203447',blue:'#2B5E87',purple:'#79578D',orange:'#B55823',gray:'#637481',rule:'#D9E2E8',soft:'#F3F6F9'};
p.theme.defaultFont=CN;
const iteration=new Date().toISOString().replace(/[^0-9]/g,'');
const runs=(s,size,color,bold=false)=>(s.match(/[\x00-\x7F]+|[^\x00-\x7F]+/g)||[]).map(run=>({run,style:{typeface:/^[\x00-\x7F]+$/.test(run)?EN:CN,fontSize:`${size}px`,color,bold}}));
function tx(sl,name,s,x,y,w,h,size=32,color=C.ink,bold=false){
 const sh=sl.shapes.add({geometry:'textbox',name,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 sh.text.style={typeface:CN,fontSize:size,color,bold,verticalAlignment:'top',wrap:'square',autoFit:'none',insets:{left:0,right:0,top:0,bottom:0}};
 sh.text=s.split('\n').map(line=>({spaceAfter:Math.round(size*.16),runs:runs(line,size,color,bold)}));return sh;
}
function line(sl,name,x,y,w,color=C.rule,width=1.5){return sl.shapes.add({geometry:'connector',kind:'straight',name,position:{left:x,top:y,width:w,height:0},line:{fill:color,width}});}
function vl(sl,name,x,y,h,color=C.rule,width=1.5){return sl.shapes.add({geometry:'connector',kind:'straight',name,position:{left:x,top:y,width:0,height:h},line:{fill:color,width}});}
function arrow(sl,name,x,y,w,color=C.blue){return sl.shapes.add({geometry:'connector',kind:'straight',name,position:{left:x,top:y,width:w,height:0},line:{fill:color,width:2.5},tail:{type:'triangle',width:'med',length:'med'}});}
function block(sl,name,head,body,x,y,w,h,color=C.blue,size=30){
 const sh=sl.shapes.add({geometry:'textbox',name,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 sh.text.style={typeface:CN,fontSize:size,color:C.ink,verticalAlignment:'top',wrap:'square',autoFit:'none',insets:{left:0,right:0,top:0,bottom:0}};
 sh.text=[{spaceAfter:15,runs:runs(head,35,color,true)},...body.map(t=>({spaceAfter:11,runs:runs(t,size,C.ink)}))];return sh;
}
function note(s,page,source){const st=story.slides[page-1];s.speakerNotes.text=st.narration+'\n\n录制操作：'+st.operation+'\n计划停留：'+st.seconds+'秒。\n来源：'+source+'\n所有结果沿用已冻结版本，当前制作不新增模型调用、密度拟合或参数估计。';}
function slide(page,title,sub,source){const s=p.slides.add();s.background.fill='#FFFFFF';order[page]=s;
 tx(s,'title',title,75,55,1770,82,55,C.ink,true);tx(s,'subtitle',sub,78,150,1740,58,29,C.gray);line(s,'header-rule',78,230,1764);
 tx(s,'footer','家庭与已有信念  →  个人可见信息  →  问卷回答  →  指标与评价',80,1007,1570,40,23,C.gray);tx(s,'page-number',String(page).padStart(2,'0'),1760,1006,90,42,27,C.blue);note(s,page,source);return s;}
const common={chartFill:'none',plotAreaFill:'none',chartLine:{fill:'none',width:0},plotAreaLine:{fill:'none',width:0},hasLegend:true,
 lineOptions:{smooth:false},legend:{position:'bottom',overlay:false,textStyle:{fontSize:25,fill:C.ink}},
 xAxis:{line:{fill:C.rule,width:1},textStyle:{fontSize:23,fill:C.gray}},yAxis:{line:{fill:'none',width:0},majorGridlines:{fill:'#E7EDF1',width:1},textStyle:{fontSize:24,fill:C.gray}}};
function chart(s,kind,cfg,font=EN){const c=s.charts.add(kind,{...common,...cfg,series:cfg.series.map(z=>({...z,values:z.values.map(v=>v===null?null:+v.toFixed(8)),...(z.xValues?{xValues:z.xValues.map(v=>+v.toFixed(8))}:{})}))});applyPresentationChartFont(c,{fontFamily:font});return c;}
const series=(name,values,color,dash=false)=>({name,values,smooth:false,line:{fill:color,width:3.4,style:dash?'dash':'solid'},marker:{symbol:'none'},fill:color});
const year=m=>{const t=m.replace('-','');return +t.slice(0,4)+(Number(t.slice(4))-1)/12;};

// 01: the author's confirmed overview, unchanged and at full original aspect ratio.
{
 const s=p.slides.add();order[1]=s;s.background.fill='#FFFFFF';
 const image=await fs.readFile(path.join(ROOT,'docs/workstreams/20261027_final_delivery/overview_figure_v3/sce_framework_author_v3.png'));
 s.images.add({blob:image.buffer.slice(image.byteOffset,image.byteOffset+image.byteLength),contentType:'image/png',alt:'作者确认的SCE方法框架图',fit:'contain',position:{left:0,top:0,width:1920,height:1080}});
 note(s,1,'作者手调方法框架图v3的已确认高清PNG。原生可编辑图件另存于原目录，当前仅引用，不重建或覆盖。');
}

// 03: actual sampling cells and calibration, not a made-up weighting example.
{
 const s=slide(3,'家庭画像、抽样与代表权重','2021年6月真实抽样：1,297人框架，512份模型答卷',
 '202106 weights_private.json的实际格级人口质量、入样率和校准权重；A01字段来自与Prompt配对的记录。126套候选分析见grid_dimension_selection_20261023.md，四维选择包含覆盖约束与过采样取舍，不宣称PCA证明唯一最优。');
 block(s,'observed','A01  调查记录',['60岁以上，大学及以上','数理较低，年家庭收入10万美元以上','中西部，自有住房，在职'],80,290,565,252,C.blue,31);
 line(s,'persona-rule',80,580,565);
 block(s,'synthetic','匹配补充',['支出：食品18.4%，现金住房20.1%','采购角色：全部采购','对联储主席信心：几乎没有'],80,616,565,233,C.orange,30);
 tx(s,'synthetic-note','补充属性来自外部资料匹配，\n与本人的调查实测字段分开。',83,885,550,80,28,C.gray);
 vl(s,'persona-divider',680,285,680);
 tx(s,'grid-formula','学历3 × 数理2 × 年龄3 × 收入3',740,289,1095,66,43,C.blue,true);
 tx(s,'grid-note','54个已知画像格，未知另池。小格保留，大格分层抽样。',742,373,1080,58,29,C.gray);
 const q=D.sampling;
 block(s,'small-cell',`较小格：${q.small.frame_n}人全部入样`,['高中及以下／数理高／40岁以下／收入5万—10万美元'],742,459,520,119,C.blue,25);
 block(s,'large-cell',`较大格：${q.large.frame_n}人抽取${q.large.n}人`,['大学及以上／数理高／40岁以下／收入10万美元以上'],1320,459,520,119,C.blue,25);
 chart(s,'bar',{position:{left:720,top:602,width:1130,height:312},categories:['较小格','较大格'],
 series:[{name:'目标人口质量',values:[q.small.target,q.large.target],fill:C.gray},{name:'仅原调查权重',values:[q.small.original_sample_weight_share,q.large.original_sample_weight_share],fill:C.orange},{name:'抽样校准后',values:[q.small.corrected,q.large.corrected],fill:C.blue}],barOptions:{direction:'column',grouping:'clustered',gapWidth:100},
 yAxis:{...common.yAxis,min:0,max:7,majorUnit:2,numberFormatCode:'0"%"'},dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0.00',textStyle:{fontSize:24,fill:C.ink}}},CN);
 tx(s,'sample-caption','按调查人口质量计权：校准后恢复原比例，不按当期预测误差调权。',741,937,1090,46,27,C.gray);
}

// 06: two information contracts, with an actual November-2025 public anchor.
{
 const s=slide(6,'两段模拟的先验与时间','历史重建沿用个人历史，近期回测以旧样本和已公布全国值构造起点',
 'A T0配置；B rolling_preflight monthly_input_plan.json 202511：源波次202501，月全局截止2025-11-13；2025-10全国Q9 3.2%，2025-11-07公开。旧波次按九个月滞后规则推定可得，历史字节版本未认证。B源画像与先验按月准备，个人日期只进一步限制E。');
 tx(s,'A-label','A  历史重建',80,290,510,65,40,C.blue,true);tx(s,'A-period','2019-01—2025-10',80,370,490,55,31,C.gray);
 block(s,'A-prior','本人过去的Q8与Q9',['A01：2021年5月的答卷','Q8起点为5%','缺失者参考最近1—3个月同类'],590,302,555,197,C.blue,31);
 arrow(s,'A-to-E',1115,401,90,C.blue);
 block(s,'A-E','个人日期之前的信息',['A01截止：2021-06-12','价格、新闻、政策同步筛选','再填写本次Q8和Q9'],1260,302,565,197,C.orange,31);
 line(s,'AB-divider',80,548,1750);
 tx(s,'B-label','B  近期回测',80,594,510,65,40,C.purple,true);tx(s,'B-period','2025-11—2026-09',80,674,490,55,31,C.gray);
 block(s,'B-source','旧样本构造联合起点',['2025年11月示例','按滞后规则选2025年1月资料','Q8、Q9完整成对抽取'],590,608,555,200,C.purple,31);
 arrow(s,'B-to-calibration',1115,708,90,C.purple);
 block(s,'B-anchor','对齐已公布的历史全国值',['10月Q9：3.2%，11月7日公布','合成Q9中心约束：3.2% ± 0.05pp','保留个体差异，Q8不强设为3.2%'],1260,608,565,200,C.blue,30);
 tx(s,'B-dates','环境：按前一年同月分布抽作答日，个人前一日与月全局截止取较早。',590,858,1235,60,29,C.orange);
 tx(s,'boundary','目标月真值只进评价。B的P与先验按月准备，旧资料可得性采用发布滞后规则推定。',81,944,1740,42,26,C.gray);
}

// 07: archived real production summary and a real, small no-API reproduction.
{
 const s=slide(7,'执行、存档与离线复算','正式模型生成已有封存记录，现场演示使用零API复算入口',
 'v01 archived_run_evidence.json与research_package/v05；record_demo.command已验证执行20户2步规则工程例和封存全国聚合复算。不将它冒称重生成完整个人答卷或重新拟合全部微观密度。');
 const a=D.archived_runs.records[0];
 block(s,'real-production','此前真实生成：A82',['82个月，41,970个合格个人月',`${a.main_physical_requests.toLocaleString('en-US')}次新主请求＋${a.repair_physical_requests}次技术补跑`,`${a.historical_reuse_slots}份相同提示旧答复用`],80,289,780,226,C.blue,34);
 line(s,'production-rule',80,556,780);
 block(s,'trace','每条记录可以回溯',['发送意图、冻结Prompt与原始回答','模型、供应商、token与费用','成功字段保留，失败按技术规则补跑'],80,595,780,240,C.purple,32);
 tx(s,'production-quality','最终Q9更新41,969份，1份按原规则保留输入先验。',83,890,780,77,27,C.gray);
 vl(s,'execution-divider',922,286,674);
 tx(s,'replay-label','现场演示：研究包统一入口',995,289,840,65,37,C.blue,true);
 tx(s,'command','python studies/sce_inflation_expectations/\nrun.py --mode all --out <新目录>',998,396,820,113,30,C.ink);
 line(s,'replay-rule',997,555,810);
 block(s,'replay-output','工程示例与封存结果复算',['20户 × 2步，40次规则决策','本次模型API调用：0','生成结果HTML与执行收据'],995,601,820,243,C.orange,35);
 tx(s,'replay-caption','录制时运行现成record_demo.command，\n再打开它打印的新结果路径。',999,889,810,82,28,C.gray);
}

// 08: one continuous visual timeline, with separate periods and metrics.
{
 const s=slide(8,'全时段结果与固定组合','全国Q9加权中位数，原始模拟与历史组合分别检验',
 'A82_personal_T0.csv、B11_latest_Core_and_Normal.csv；固定λ从A早48月MSE拟合，后34月及B不重拟。2021旧原名单MAE0.822126，新0.577424；同名单旧值另有0.825607。不同输入阶段不合并MAE，后段曾用于探索，区间跨零，不称独立盲测或统计显著胜出。');
 const ax=D.A.map(r=>year(r.month)),bx=D.B.map(r=>year(r.month)),truth=[...D.A.map(r=>+r.truth_pp),...D.B.map(r=>+r.truth_pp)],xx=[...ax,...bx];
 const later=D.A.filter(r=>r.month>='2023-01');const cx=[...later.map(r=>year(r.month)),...bx];
 const cv=[...later.map(r=>+r.anchor_pp+D.combination.simulation_weight*(+r.sim_pp-+r.anchor_pp)),...D.B.map(r=>+r.Core_blend_pp)];
 tx(s,'path-unit','通胀预期（%）',84,275,710,43,25,C.gray);
 chart(s,'scatter',{position:{left:62,top:330,width:1250,height:535},scatterOptions:{style:'line'},
 series:[{...series('真实SCE',truth,C.ink),xValues:xx},{...series('原始模拟 A',D.A.map(r=>+r.sim_pp),C.blue),xValues:ax},{...series('原始模拟 B',D.B.map(r=>+r.Core_pp),C.blue,true),xValues:bx},{...series('固定组合',cv,C.orange),xValues:cx},{name:'A/B分界',xValues:[2025+10/12,2025+10/12],values:[2,8.2],line:{fill:C.gray,width:1.3,style:'dash'},marker:{symbol:'none'}}],
 xAxis:{...common.xAxis,min:2019,max:2026.75,majorUnit:1,numberFormatCode:'0'},yAxis:{...common.yAxis,min:2,max:8.2,majorUnit:1,numberFormatCode:'0.0'},legend:{position:'bottom',overlay:false,textStyle:{fontSize:22,fill:C.ink}}},CN);
 tx(s,'A-label','A：历史重建',85,890,530,45,28,C.blue,true);tx(s,'B-label','B：近期回顾性检验',963,890,640,45,28,C.purple,true);
 vl(s,'metrics-divider',1340,286,660);
 block(s,'A-metrics','A82  原始MAE',['模拟0.298pp ／ 历史参照0.223pp','2021：旧0.822 → 新0.577pp'],1400,291,440,142,C.blue,29);
 block(s,'holdout-metrics','后34个月  固定组合',['组合0.184pp ／ 参照0.194pp','早48个月定权，后段检查'],1400,486,440,140,C.orange,29);
 block(s,'B-metrics','B11  固定组合',['组合0.144pp ／ 参照0.173pp','原始模拟0.349pp'],1400,683,440,140,C.purple,29);
 tx(s,'micro-summary','同支持历史微观：跨人IQR为模拟2.248／真人5.261pp，W1为2.219pp。',82,932,1750,35,23,C.gray);
 tx(s,'blend-definition','固定组合：13.4%模拟 ＋ 86.6%已公布历史值；主图采用512人加权直接模拟口径。',82,970,1750,32,23,C.gray);
}

// 09: weekly evidence is dominant, monthly drift and downstream are supporting findings.
{
 const s=slide(9,'连续更新与经济用途','固定家庭传递自身模拟信念，新的历史SCE公布后再校准先验',
 'weekly47_path.csv、weekly47_monthly11_primary.csv；47周固定300户，月末11点原始MAE0.151581，历史0.172727，5/11改善。月度链后5期MAE0.500486。下游8.17%来自历史月度Core+Normal原始模拟相对同结构官方SCE回归的循环信贷2月RMSE降幅；不是周度结果，历史均值仍强，其他结局无一致改善。');
 const excel=r=>Math.round((Date.parse(r.cutoff.slice(0,10)+'T00:00:00Z')-Date.UTC(1899,11,30))/86400000);
 const wm=new Map(D.weekly_monthly.map(r=>[r.month,r]));
 const last=D.weekly.filter((r,i)=>i===D.weekly.length-1||D.weekly[i+1].month!==r.month),reset=D.weekly.filter(r=>r.reset_required==='True');
 tx(s,'weekly-unit','通胀预期（%）',83,273,650,44,25,C.gray);
 chart(s,'scatter',{position:{left:64,top:331,width:1255,height:523},scatterOptions:{style:'lineWithMarkers'},
 series:[{...series('周度原始模拟',D.weekly.map(r=>+r.q9_median_pp),C.blue),xValues:D.weekly.map(excel)},{name:'月度真实SCE',xValues:last.map(excel),values:last.map(r=>+wm.get(r.month).truth_pp),line:{fill:'none',width:0},marker:{symbol:'diamond',size:13,fill:C.ink}},{name:'历史值公布后校准',xValues:reset.map(excel),values:reset.map(r=>+r.q9_median_pp),line:{fill:'none',width:0},marker:{symbol:'circle',size:9,fill:C.orange}}],
 xAxis:{...common.xAxis,min:excel(D.weekly[0]),max:excel(D.weekly.at(-1)),majorUnit:56,numberFormatCode:'yy-mm-dd'},yAxis:{...common.yAxis,min:2.8,max:4.2,majorUnit:.2,numberFormatCode:'0.0'}},CN);
 tx(s,'weekly-main','月末原始MAE 0.152pp，历史参照0.173pp',84,890,1190,56,34,C.blue,true);
 tx(s,'weekly-note','输出端未作线性组合；5/11个月改善，9月仍漏判上行。',85,951,1200,42,26,C.gray);
 vl(s,'extensions-divider',1340,286,666);
 block(s,'monthly-drift','月度自主链',['固定512户，后月不重置全国先验','后5期MAE为0.500pp','后段出现持续高估'],1400,294,440,192,C.purple,29);
 line(s,'extension-rule',1400,559,435);
 block(s,'credit','循环信贷用途',['未来2个月RMSE降低8.17%','相对同结构官方SCE回归','来自历史月度模拟指标'],1400,602,440,196,C.orange,29);
 tx(s,'extension-limits','其他用途未一致改善。\n研究包提供代码与复算入口。',1403,868,435,94,27,C.gray);
}

// Reuse approved sample visuals and replace their notes with the separate current script.
for(const n of [2,4,5])note(order[n],n,'原已验收samples_v02的同页原生内容和图表，图形与数值不重写；真实样本A01贯穿。');
p.slides.reorder(Array.from({length:9},(_,i)=>'sl/'+order[i+1].id));
await fs.mkdir(path.join(OUT,'slides'),{recursive:true});await fs.mkdir(path.join(BUILD,'validated'),{recursive:true});
const candidate=path.join(BUILD,`candidate_${iteration}.pptx`);await(await PresentationFile.exportPptx(p)).save(candidate);
execFileSync(PY,[path.join(ROOT,'studies/sce_inflation_expectations/reports/video_complete_v03/preserve_sample_charts.py'),path.join(BUILD,'source_charts_approved.pptx'),candidate,path.join(BUILD,`preserved_charts_${iteration}.json`)],{stdio:'pipe'});
const finalPath=path.join(BUILD,'validated',`video_complete_${iteration}.pptx`),receipt=path.join(BUILD,`validation_${iteration}.json`);
await finalizePresentation({workspaceDir:BUILD,candidatePath:candidate,finalPath,pythonExecutable:PY,
 integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','18288000,10287000','--validate-bullet-geometry','--validate-heading-fit'],explicitTotalSlideCount:9,requiredNativeChartOwnerSlides:[2,3,5,8,9],
 materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'user_request',families:[CN,EN]},verifyArtifactToolImport:true,receiptPath:receipt});
await fs.copyFile(finalPath,path.join(OUT,'SCE_video_complete_v03.pptx'));
const final=await PresentationFile.importPptx(await FileBlob.load(finalPath));
for(let i=0;i<9;i++){
 const blob=await final.export({slide:final.slides.items[i],format:'png',scale:1});await fs.writeFile(path.join(OUT,'slides',`page_${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await blob.arrayBuffer()));
 const layout=await final.slides.items[i].export({format:'layout'});await fs.writeFile(path.join(BUILD,`slide_${i+1}.layout.json`),await layout.text());
}
await fs.writeFile(path.join(BUILD,'latest_build.json'),JSON.stringify({finalPath,receipt,iteration,slides:9},null,2));
console.log(JSON.stringify({slides:9,finalPath,receipt}));
