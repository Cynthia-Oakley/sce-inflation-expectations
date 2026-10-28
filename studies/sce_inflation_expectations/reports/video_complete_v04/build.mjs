import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {Presentation,PresentationFile,FileBlob} from '@oai/artifact-tool';

const ROOT=process.env.SCE_PROJECT_ROOT||process.cwd(),BUILD=path.join(ROOT,'tmp/video_complete_v04'),OUT=path.join(ROOT,'deliverables/video/v04');
const SKILL='/Users/wushuyue/.codex/plugins/cache/openai-primary-runtime/presentations/26.1022.11436/skills/presentations';
const PY='/Users/wushuyue/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
process.env.RUNTIME_NODE_MODULES??='/Users/wushuyue/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const {finalizePresentation,applyPresentationChartFont}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')));
const req=createRequire(createRequire(import.meta.url).resolve('@oai/artifact-tool'));
const {FontLibrary}=await import(pathToFileURL(req.resolve('skia-canvas')));
FontLibrary.use('Kaiti SC',[process.env.SCE_KAITI_FONT||path.join(ROOT,'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf')]);
const D=JSON.parse(await fs.readFile(path.join(BUILD,'data.json'),'utf8')),story=JSON.parse(await fs.readFile(path.join(OUT,'storyboard.json'),'utf8'));
const CN='Kaiti SC',EN='Times New Roman',C={ink:'#203447',blue:'#2B5E87',purple:'#79578D',orange:'#B55823',gray:'#637481',rule:'#D9E2E8'};
const stamp=new Date().toISOString().replace(/\D/g,'');
const p=Presentation.create({slideSize:{width:1920,height:1080}});p.theme.defaultFont=CN;
const s=p.slides.add();s.background.fill='#FFFFFF';
function tx(name,text,x,y,w,h,size=28,color=C.ink,bold=false){
 const sh=s.shapes.add({geometry:'textbox',name,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 sh.text.style={typeface:CN,fontSize:size,color,bold,verticalAlignment:'top',wrap:'square',autoFit:'none',insets:{left:0,right:0,top:0,bottom:0}};
 sh.text=text.split('\n').map(t=>({spaceAfter:Math.round(size*.15),runs:(t.match(/[\x00-\x7F]+|[^\x00-\x7F]+/g)||[]).map(run=>({run,style:{typeface:/^[\x00-\x7F]+$/.test(run)?EN:CN,fontSize:`${size}px`,color,bold}}))}));return sh;
}
function line(name,x,y,w,h=0,color=C.rule){return s.shapes.add({geometry:'connector',kind:'straight',name,position:{left:x,top:y,width:w,height:h},line:{fill:color,width:1.5}});}
const axis={line:{fill:C.rule,width:1},textStyle:{fontSize:22,fill:C.gray}};
function chart(type,config,font=CN){
 config={...config,series:config.series.map(v=>({...v,values:v.values.map(n=>+n.toFixed(8)),...(v.xValues?{xValues:v.xValues.map(n=>+n.toFixed(8))}:{})}))};
 const ch=s.charts.add(type,{chartFill:'none',plotAreaFill:'none',chartLine:{fill:'none',width:0},plotAreaLine:{fill:'none',width:0},
  hasLegend:true,legend:{position:'bottom',overlay:false,textStyle:{fontSize:22,fill:C.ink}},
  xAxis:axis,yAxis:{...axis,line:{fill:'none',width:0},majorGridlines:{fill:'#E7EDF1',width:1}},...config});
 applyPresentationChartFont(ch,{fontFamily:font});return ch;
}
const serial=date=>Math.round((Date.parse(date+'T00:00:00Z')-Date.UTC(1899,11,30))/86400000);
const wdate=r=>serial(r.cutoff.slice(0,10));
const seq=(name,values,xValues,color,width=3.4)=>({name,values,xValues,line:{fill:color,width},marker:{symbol:'none'},smooth:false});
tx('title','连续信念更新与下游指标预测',75,55,1770,82,55,C.ink,true);
tx('subtitle','固定家庭的月度、周度信念传递，以及模拟指标的经济用途',78,150,1740,58,29,C.gray);
line('header-rule',78,230,1764);
line('weekly-monthly-divider',960,280,0,683);line('monthly-downstream-divider',1400,280,0,683);
tx('weekly-title','周度个人信念连续更新',80,287,850,62,38,C.blue,true);
tx('weekly-explanation','固定300户逐周更新，共47周\n新SCE公开后校准，期间沿用自身模拟值',82,362,850,88,28,C.ink);
tx('weekly-unit','通胀预期（%）',83,459,780,38,24,C.gray);
const monthmap=new Map(D.weekly_monthly.map(r=>[r.month,r]));
const last=D.weekly.filter((r,i)=>i===D.weekly.length-1||D.weekly[i+1].month!==r.month),reset=D.weekly.filter(r=>r.reset_required==='True');
chart('scatter',{position:{left:64,top:504,width:880,height:347},scatterOptions:{style:'lineWithMarkers'},
 series:[seq('周度原始模拟',D.weekly.map(r=>+r.q9_median_pp),D.weekly.map(wdate),C.blue),
 {name:'月度真实SCE',xValues:last.map(wdate),values:last.map(r=>+monthmap.get(r.month).truth_pp),line:{fill:'none',width:0},marker:{symbol:'diamond',size:10,fill:C.ink}},
 {name:'发布后校准',xValues:reset.map(wdate),values:reset.map(r=>+r.q9_median_pp),line:{fill:'none',width:0},marker:{symbol:'circle',size:7,fill:C.orange}}],
 xAxis:{...axis,min:wdate(D.weekly[0]),max:wdate(D.weekly.at(-1)),majorUnit:70,numberFormatCode:'yy-mm'},
 yAxis:{...axis,min:2.8,max:4.2,majorUnit:.4,numberFormatCode:'0.0',majorGridlines:{fill:'#E7EDF1',width:1}}});
tx('weekly-result','月末原始MAE 0.152pp，基线0.173pp',82,885,850,53,33,C.blue,true);
tx('weekly-limit','输出未做线性组合，5/11个月改善；9月仍漏判上行。',83,943,850,45,25,C.gray);

tx('monthly-title','月度个人模拟信念\n连续传递',990,288,390,94,33,C.purple,true);
tx('monthly-explanation','固定512户，传递本人上月模拟值\n后月不再按新的全国值校准',992,401,385,88,25,C.ink);
const md=D.monthly.map(r=>serial(r.month.slice(0,4)+'-'+r.month.slice(4,6)+'-01'));
tx('monthly-unit','通胀预期（%）',993,496,380,35,23,C.gray);
chart('scatter',{position:{left:972,top:544,width:415,height:307},scatterOptions:{style:'line'},
 series:[seq('月度递推',D.monthly.map(r=>+r.recursive_pp),md,C.purple),seq('真实SCE',D.monthly.map(r=>+r.truth_pp),md,C.ink,2.8)],
 xAxis:{...axis,min:md[0],max:md.at(-1),majorUnit:122,numberFormatCode:'yy-mm'},
 yAxis:{...axis,min:3,max:4.5,majorUnit:.5,numberFormatCode:'0.0',majorGridlines:{fill:'#E7EDF1',width:1}},
 legend:{position:'bottom',overlay:false,textStyle:{fontSize:22,fill:C.ink}}});
tx('monthly-result','后5期MAE 0.500pp',993,886,385,53,31,C.purple,true);
tx('monthly-limit','5月起持续高估，出现漂移。',993,944,385,44,25,C.gray);

tx('downstream-title','下游指标预测',1430,287,410,62,37,C.orange,true);
tx('downstream-explanation','例：循环消费信贷\n如信用卡，可在额度内循环借还\n考察余额未来1—3个月变化',1432,362,405,117,25,C.ink);
tx('credit-unit','预测RMSE降幅（%）',1432,496,405,35,23,C.gray);
chart('bar',{position:{left:1410,top:544,width:440,height:307},hasLegend:false,categories:['1个月','2个月','3个月'],
 series:[{name:'相对同结构官方SCE回归的RMSE降幅',values:D.credit.map(r=>+((+r.rmse_improvement*100).toFixed(8))),fill:C.orange,line:{fill:'none',width:0}}],
 barOptions:{direction:'column',grouping:'clustered',gapWidth:100},
 xAxis:{...axis},yAxis:{...axis,min:0,max:10,majorUnit:4,numberFormatCode:'0"%"',majorGridlines:{fill:'#E7EDF1',width:1}},
 dataLabels:{showValue:true,showCategoryName:false,showSeriesName:false,showLegendKey:false,position:'outEnd',numberFormatCode:'0.00"%"',textStyle:{fontSize:24,fill:C.orange}}});
tx('credit-result','2个月RMSE降低8.17%',1433,886,400,53,31,C.orange,true);
tx('credit-limit','对照：同结构官方SCE回归\n其他指标未见一致改善。',1433,943,405,61,23,C.gray);
tx('footer','家庭与已有信念  →  个人可见信息  →  问卷回答  →  指标与评价',80,1007,1570,40,23,C.gray);
tx('page-number','09',1760,1006,90,42,27,C.blue);
s.speakerNotes.text=story.slides[8].narration+'\n\n来源：正式研究包v05 reproduction_data/weekly47_path.csv、weekly47_monthly11_primary.csv、monthly_autonomous_recursion.csv、downstream_contrasts.csv。47周对应11个月末真值点，周度没有输出线性组合，但在公开历史SCE发布后校准先验。月度为固定512户，后月不重置全国先验。下游图为历史A段Core+Normal原始模拟替代官方SCE的同结构回归，预测循环消费信贷余额未来1/2/3个月对数变化，RMSE下降3.55/8.17/1.69%；不是周度输出的下游检验，也未胜过所有简单基线。其他指标无一致改善。\n录制：'+story.slides[8].operation+'\n计划约45秒。';

await fs.mkdir(path.join(BUILD,'validated'),{recursive:true});await fs.mkdir(path.join(OUT,'slides'),{recursive:true});
const candidate=path.join(BUILD,'page9_'+stamp+'.pptx');await(await PresentationFile.exportPptx(p)).save(candidate);
const stage9=path.join(BUILD,'validated','page9_'+stamp+'.pptx');
const validators={pythonExecutable:PY,integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','18288000,10287000','--validate-bullet-geometry','--validate-heading-fit'],fontPolicy:{basis:'user_request',families:[CN,EN]},verifyArtifactToolImport:true};
await finalizePresentation({...validators,workspaceDir:BUILD,candidatePath:candidate,finalPath:stage9,explicitTotalSlideCount:1,requiredNativeChartOwnerSlides:[1],materializeLiteralChartWorkbooks:true,receiptPath:path.join(BUILD,'page9_validation_'+stamp+'.json')});
const merged=path.join(BUILD,'merged_'+stamp+'.pptx'),preservation=path.join(BUILD,'preservation_'+stamp+'.json');
execFileSync(PY,[path.join(ROOT,'studies/sce_inflation_expectations/reports/video_complete_v04/replace_slide9.py'),path.join(BUILD,'author_deck.pptx'),stage9,merged,preservation],{stdio:'pipe'});
const finalPath=path.join(BUILD,'validated','complete_'+stamp+'.pptx'),receipt=path.join(BUILD,'validation_'+stamp+'.json');
await finalizePresentation({...validators,workspaceDir:BUILD,candidatePath:merged,finalPath,explicitTotalSlideCount:9,requiredNativeChartOwnerSlides:[2,3,4,8,9],materializeLiteralChartWorkbooks:false,receiptPath:receipt});
await fs.copyFile(finalPath,path.join(OUT,'SCE_video_complete_v04.pptx'));
const previewPath=path.join(BUILD,'render_only_'+stamp+'.pptx');
execFileSync(PY,[path.join(ROOT,'studies/sce_inflation_expectations/reports/video_complete_v04/render_copy.py'),finalPath,previewPath,path.join(BUILD,'preview_compatibility_'+stamp+'.json')],{stdio:'pipe'});
const final=await PresentationFile.importPptx(await FileBlob.load(previewPath));
for(let i=0;i<9;i++){
 const b=await final.export({slide:final.slides.items[i],format:'png',scale:1});await fs.writeFile(path.join(OUT,'slides','page_'+String(i+1).padStart(2,'0')+'.png'),new Uint8Array(await b.arrayBuffer()));
}
const l=await final.slides.items[8].export({format:'layout'});await fs.writeFile(path.join(BUILD,'page9.layout.json'),await l.text());
await fs.writeFile(path.join(BUILD,'latest_build.json'),JSON.stringify({finalPath,receipt,preservation,stamp,slides:9},null,2));
console.log(JSON.stringify({finalPath,slides:9,edited_slide:9,preserved_slides:8}));
