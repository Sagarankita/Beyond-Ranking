import fs from 'node:fs/promises';
import path from 'node:path';
import { Presentation, PresentationFile } from '/Users/biancasawant/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
import { resolvePresentationFont } from '/Users/biancasawant/.codex/plugins/cache/openai-primary-runtime/presentations/26.1112.11217/skills/presentations/container_tools/artifact_tool_utils.mjs';
import { FontLibrary } from '/Users/biancasawant/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/node_modules/skia-canvas/lib/index.mjs';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const OUT = path.join(ROOT, 'output');
const PREV = path.join(ROOT, 'output', 'presentation_previews');
await fs.mkdir(PREV,{recursive:true});
const W=1280,H=720;
const C={ink:'#14202B',navy:'#17324D',blue:'#2463A6',teal:'#087E78',gold:'#D99A28',red:'#B4493F',muted:'#526171',pale:'#F4F7FA',line:'#CAD3DC',white:'#FFFFFF',green:'#2B7A55'};
FontLibrary.use('/System/Library/Fonts/Supplemental/Arial.ttf');
const FONT=resolvePresentationFont({fontFamily:'Arial'});
const p=Presentation.create({slideSize:{width:W,height:H}});
const none={style:'solid',fill:'none',width:0};
function shape(s,x,y,w,h,fill='none',line='none',lw=0,geom='rect'){
 return s.shapes.add({geometry:geom,position:{left:x,top:y,width:w,height:h},fill,line:{style:'solid',fill:line,width:lw}});
}
function txt(s,t,x,y,w,h,size=24,color=C.ink,bold=false,opts={}){
 const q=shape(s,x,y,w,h);
 q.text=t; q.text.style={fontFamily:FONT,fontSize:size,color,bold,verticalAlignment:'middle',alignment:opts.align||'left',wrap:true,marginLeft:opts.pad??0,marginRight:opts.pad??0,marginTop:opts.pad??0,marginBottom:opts.pad??0};
 return q;
}
function line(s,x1,y1,x2,y2,color=C.line,width=2){
 const left=Math.min(x1,x2), top=Math.min(y1,y2), w=Math.max(.1,Math.abs(x2-x1)), h=Math.max(.1,Math.abs(y2-y1));
 return shape(s,left,top,w,h,'none',color,width);
}
function rect(s,x,y,w,h,fill,r=0,stroke='none',sw=0){return shape(s,x,y,w,h,fill,stroke,sw,r?'roundRect':'rect');}
function addTitle(s,title,sub='',n=''){
 txt(s,title,64,38,1140,58,36,C.ink,true);
 if(sub)txt(s,sub,66,98,1120,35,17,C.muted,false);
 line(s,64,142,1216,142,C.line,1.5);
 if(n)txt(s,String(n).padStart(2,'0'),1160,668,52,24,14,C.muted,true,{align:'right'});
}
function notes(s,text){s.speakerNotes.text=text;}
function addImage(s,file,x,y,w,h,alt){return fs.readFile(file).then(bytes=>s.images.add({blob:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),contentType:'image/png',alt,fit:'contain',position:{left:x,top:y,width:w,height:h}}));}

// 1. Title
{
 const s=p.slides.add(); s.background.fill=C.white;
 rect(s,0,0,18,H,C.teal);
 txt(s,'BEYOND RANKING',72,72,900,70,48,C.navy,true);
 txt(s,'A data driven multi objective framework for VJTI CE & IT department productivity',76,151,920,76,26,C.muted,false);
 line(s,76,250,540,250,C.gold,4);
 txt(s,'Optimization Techniques Mini Project',76,278,700,38,20,C.ink,true);
 txt(s,'Veermata Jijabai Technological Institute, Mumbai',76,319,700,34,19,C.muted);
 txt(s,'Bianca Sawant  |  241071067\nAnushree Upasham  |  241071077\nAnkita Sagar  |  241071063\nSofia Abidi  |  241071075',76,405,570,156,20,C.ink,false);
 rect(s,920,220,250,250,C.pale,0,C.line,1);
 txt(s,'4',945,245,200,100,86,C.teal,true,{align:'center'});
 txt(s,'objective families',945,352,200,42,21,C.navy,true,{align:'center'});
 txt(s,'1 shared evaluator\n6 search methods',945,402,200,52,17,C.muted,false,{align:'center'});
 notes(s,'Introduce the project and team. State that this is an evidence aware decision support prototype for exploring feasible departmental resource allocations.');
}
// 2. Problem
{
 const s=p.slides.add(); s.background.fill=C.white; addTitle(s,'Department planning has competing goals','The system turns resource limits into explicit trade offs',2);
 txt(s,'Conventional ranking view',80,180,440,34,22,C.navy,true,{align:'center'});
 rect(s,105,235,390,190,C.pale,0,C.line,1);
 txt(s,'One composite score',145,270,310,38,26,C.ink,true,{align:'center'});
 txt(s,'Hides which resource choice\nproduced the change',145,320,310,70,20,C.muted,false,{align:'center'});
 txt(s,'Allocation framework',710,180,440,34,22,C.teal,true,{align:'center'});
 rect(s,735,235,390,190,'#F3F8F7',0,'#A9D1CB',1);
 txt(s,'Decisions  +  constraints',765,262,330,35,24,C.ink,true,{align:'center'});
 txt(s,'Research funding and effort\nStudent support and outreach\nFeasible trade off set',778,310,300,92,18,C.muted,false,{align:'center'});
 line(s,540,330,690,330,C.gold,4);
 txt(s,'Research',124,487,220,34,21,C.navy,true,{align:'center'});
 txt(s,'Innovation',380,487,220,34,21,C.blue,true,{align:'center'});
 txt(s,'Student development',625,487,290,34,21,C.teal,true,{align:'center'});
 txt(s,'Societal impact',940,487,230,34,21,C.gold,true,{align:'center'});
 txt(s,'Objective scores are model indicators. The reference and public calibrated response functions remain synthetic.',118,575,1040,42,17,C.red,true,{align:'center'});
 notes(s,'Explain that the system treats budget and faculty effort as controllable decisions, while the four objective families summarize modeled KPI outcomes. Ranking itself is not directly optimized.');
}
// 3. Architecture
{
 const s=p.slides.add(); s.background.fill=C.white; addTitle(s,'Evidence flows through one shared evaluation contract','DEA provides descriptive benchmarking context. It does not calculate allocation objectives.',3);
 const nodes=[
  [60,210,210,100,'Data and\nprovenance',C.navy], [310,210,220,100,'KPI models',C.blue], [590,210,230,100,'Shared\nevaluator',C.teal], [880,210,330,100,'Six optimizers',C.gold],
  [90,440,260,100,'Robustness and\nbenchmarking',C.blue], [450,440,300,100,'Strategy selection\nand recommendations',C.teal], [850,440,310,100,'FastAPI and\nStreamlit dashboard',C.navy]
 ];
 for(const [x,y,w,h,label,color] of nodes){rect(s,x,y,w,h,'#F7F9FB',0,color,2);txt(s,label,x+12,y+10,w-24,h-20,20,color,true,{align:'center'});}
 for(const [x1,y1,x2,y2] of [[270,260,310,260],[530,260,590,260],[820,260,880,260],[1035,310,225,440],[350,490,450,490],[750,490,850,490]]) line(s,x1,y1,x2,y2,C.muted,2.5);
 rect(s,60,340,250,52,'#FFF8E8',0,'#E7C77B',1);
 txt(s,'DEA: peer efficiency context',75,347,220,38,16,C.gold,true,{align:'center'});
 txt(s,'Optimization: shared evaluator returns repaired decisions, KPI intervals, objective values, feasibility and evidence flags.',390,575,820,46,17,C.muted,false,{align:'center'});
 notes(s,'Describe source traceability, evidence gates and the shared evaluator. DEA runs as a separate descriptive method. KPI models feed the evaluator, which then supports all optimizers.');
}
// 4. Optimization
{
 const s=p.slides.add(); s.background.fill=C.white; addTitle(s,'Six methods search the same feasible decision space','Every candidate is repaired and evaluated by the canonical backend',4);
 txt(s,'NSGA II',80,180,190,34,21,C.navy,true,{align:'center'}); txt(s,'NSGA III',290,180,190,34,21,C.blue,true,{align:'center'}); txt(s,'MOEA/D',500,180,190,34,21,C.teal,true,{align:'center'});
 txt(s,'MOPSO',710,180,190,34,21,C.gold,true,{align:'center'}); txt(s,'RION',920,180,140,34,21,C.red,true,{align:'center'}); txt(s,'Random',1070,180,150,34,21,C.muted,true,{align:'center'});
 rect(s,75,265,255,118,'#F6F8FA',0,C.line,1); txt(s,'Candidate allocation',95,285,215,32,21,C.navy,true,{align:'center'}); txt(s,'Budget  •  effort  •  support',95,327,215,36,17,C.muted,false,{align:'center'});
 rect(s,390,265,255,118,'#F3F8F7',0,'#A9D1CB',1); txt(s,'Repair and feasibility',410,285,215,32,21,C.teal,true,{align:'center'}); txt(s,'Bounds  •  dependencies\ncapacity  •  service floors',410,322,215,47,16,C.muted,false,{align:'center'});
 rect(s,705,265,255,118,'#F6F8FA',0,C.line,1); txt(s,'Shared evaluation',725,285,215,32,21,C.blue,true,{align:'center'}); txt(s,'KPI predictions and intervals\n4 objective families',725,322,215,47,16,C.muted,false,{align:'center'});
 rect(s,1020,265,200,118,'#FFF8E8',0,'#E7C77B',1); txt(s,'Pareto archive',1035,285,170,32,21,C.gold,true,{align:'center'}); txt(s,'Nondominated\nfeasible candidates',1035,322,170,47,16,C.muted,false,{align:'center'});
 for(const [x1,x2] of [[330,390],[645,705],[960,1020]])line(s,x1,324,x2,324,C.muted,2.5);
 txt(s,'RION combines an NSGA II outer search with a PSO coordinate mutation. Inner swarm evaluations count toward the shared budget.',130,460,1020,55,18,C.ink,false,{align:'center'});
 txt(s,'Repair is deterministic. Feasibility first dominance applies before Pareto comparison.',160,545,960,34,18,C.teal,true,{align:'center'});
 notes(s,'Name the six methods. Emphasize that algorithms differ in search operators, while repair, constraints, predictions and metrics come from a shared evaluator. RION uses inner PSO mutation with explicit evaluation accounting.');
}
// 5. Results
{
 const s=p.slides.add(); s.background.fill=C.white; addTitle(s,'MOPSO and MOEA/D lead this synthetic benchmark','25 seeds per method with 100 candidate evaluations per run',5);
 const rows=[['MOEA/D',0.0006844762,0.0070377,.505014,1],['MOPSO',.0006862869,.0052269,.663295,1],['NSGA-II',.000680,.011167,.548069,1],['NSGA-III',.000679,.012883,.538521,1],['Random',.000679,.012820,.678920,1],['RION',.000657,.034237,.995636,1]];
 txt(s,'Algorithm',74,175,200,30,17,C.muted,true); txt(s,'Median hypervolume (higher)',285,175,310,30,17,C.muted,true); txt(s,'Median IGD (lower)',635,175,255,30,17,C.muted,true); txt(s,'Median runtime',925,175,160,30,17,C.muted,true); txt(s,'Feasible',1100,175,110,30,17,C.muted,true);
 const maxHv=.00070,maxIgd=.04;
 rows.forEach((r,i)=>{const y=225+i*58;txt(s,r[0],74,y,190,30,18,C.ink,true);rect(s,285,y+4,r[1]/maxHv*250,20,i<2?C.teal:C.blue);txt(s,r[1].toFixed(6),545,y,92,27,14,C.ink);rect(s,650,y+4,r[2]/maxIgd*190,20,C.gold);txt(s,r[2].toFixed(3),852,y,70,27,14,C.ink);txt(s,r[3].toFixed(3)+' s',945,y,110,27,16,C.ink);txt(s,'100%',1120,y,70,27,16,C.green,true);});
 txt(s,'25 seeds',285,585,250,30,17,C.muted,false); txt(s,'25 seeds',650,585,220,30,17,C.muted,false);
 txt(s,'Paired Wilcoxon + Holm: MOPSO and MOEA/D were not distinguishable at 0.05. MOPSO outperformed RION on both metrics after correction.',95,620,1090,38,16,C.navy,true,{align:'center'});
 txt(s,'Synthetic fixture. Three objective families are unsupported zeros. Runtime depends on the machine.',110,664,1040,25,13,C.red,false,{align:'center'});
 notes(s,'Explain medians over 25 seeds. MOPSO medians are 0.0006862869 hypervolume and 0.0052269 IGD. MOEA/D is close at 0.0006844762 and 0.0070377. Holm adjusted paired tests did not distinguish them. The test applies only to this synthetic fixture.');
}
// 6. Dashboard
{
 const s=p.slides.add(); s.background.fill=C.white; addTitle(s,'The dashboard turns a run into reviewable actions','The advisor keeps deterministic selection separate from optional wording assistance',6);
 await addImage(s,path.join(ROOT,'report_assets/screenshots/dashboard_overview.png'),58,178,625,370,'Authentic Streamlit department overview');
 txt(s,'Live workflow',735,190,450,32,23,C.navy,true);
 txt(s,'Edit supported budget and faculty inputs\nValidate the scenario\nRun a matched budget search\nSelect a feasible candidate\nReview action cards, trade offs and uncertainty',740,240,445,200,19,C.ink,false);
 line(s,735,470,1180,470,C.line,1.5);
 txt(s,'Optional Groq explanation',735,495,445,30,21,C.teal,true);
 txt(s,'Receives verified structured facts. It cannot select strategies or change allocations. Unsafe or unavailable output falls back to deterministic wording.',740,535,440,82,17,C.muted,false);
 txt(s,'Screenshot shows the public plus synthetic reference scenario.',95,590,590,28,14,C.muted,false,{align:'center'});
 notes(s,'Describe the actual Streamlit overview and live Resource Planner. The dashboard calls FastAPI; the backend revalidates candidates. Explain the optional isolated Groq service and fallback safeguards.');
}
// 7. Innovation
{
 const s=p.slides.add(); s.background.fill=C.white; addTitle(s,'The contribution is an auditable decision workflow','Implementation choices connect optimization quality to practical review',7);
 const items=[
  ['Controllable resources','Funding, faculty effort, assistants and compute become decisions.'],
  ['One evaluator','Six algorithms share repair, constraints and outputs.'],
  ['Evidence labels','Observed public facts stay distinct from synthetic responses.'],
  ['Actionable selections','Profiles map feasible candidates to exact changes and trade offs.'],
  ['Sensitivity checks','Held fixed assessment and reoptimization remain separate.'],
  ['Grounded explanation','Optional LLM wording receives allowlisted verified facts.'],
 ];
 const left=95,top=190,row=68;
 items.forEach((it,i)=>{const y=top+i*row;txt(s,String(i+1).padStart(2,'0'),left,y,54,35,18,C.gold,true);txt(s,it[0],left+70,y,270,35,21,C.navy,true);txt(s,it[1],left+355,y,720,45,18,C.ink,false);if(i<items.length-1)line(s,left+68,y+51,1170,y+51,C.line,1);});
 notes(s,'Emphasize the joined contribution: decision variables, shared evaluation, visible evidence class, deterministic recommendations, separate robustness modes and constrained LLM use.');
}
// 8. Conclusion
{
 const s=p.slides.add(); s.background.fill=C.white; addTitle(s,'A working optimizer with a clear evidence boundary','Completed synthetic experiments support method comparison, not causal VJTI policy claims',8);
 txt(s,'150',95,190,210,78,60,C.teal,true,{align:'center'});txt(s,'synthetic benchmark jobs',95,270,210,42,18,C.muted,true,{align:'center'});
 txt(s,'18',400,190,210,78,60,C.blue,true,{align:'center'});txt(s,'public calibrated scenario runs',390,270,230,42,18,C.muted,true,{align:'center'});
 txt(s,'84 + 53',710,190,250,78,48,C.gold,true,{align:'center'});txt(s,'backend and UI tests passed',710,270,250,42,18,C.muted,true,{align:'center'});
 rect(s,1010,195,190,125,'#FDF3F1',0,'#E2B4AD',1);txt(s,'No empirical or causal\nintervention validation',1025,215,160,85,19,C.red,true,{align:'center'});
 line(s,95,385,1185,385,C.line,1.5);
 txt(s,'Beyond Ranking turns multi objective search into understandable, constraint aware departmental planning decisions.',145,445,990,100,30,C.navy,true,{align:'center'});
 txt(s,'Next evidence requirement: aligned multi year department allocations, resources and outcomes.',170,585,940,40,18,C.muted,false,{align:'center'});
 notes(s,'Close with completed benchmarks, interactive system and tests. State that observed VJTI intervention effects remain unvalidated. The current strongest use is exploring feasible scenario trade offs while gathering stronger longitudinal evidence.');
}

for(const [i,s] of p.slides.items.entries()){
 const png=await p.export({slide:s,format:'png',scale:1});
 await fs.writeFile(path.join(PREV,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
}
const pptx=await PresentationFile.exportPptx(p); await pptx.save(path.join(OUT,'Beyond_Ranking_Final_Presentation.pptx'));
const pdf=await p.export({format:'pdf'}); await fs.writeFile(path.join(OUT,'Beyond_Ranking_Final_Presentation.pdf'),new Uint8Array(await pdf.arrayBuffer()));
console.log(`Wrote ${p.slides.items.length} slides`);
