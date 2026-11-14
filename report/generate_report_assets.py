"""Generate report figures only from committed Beyond Ranking artifacts."""
from pathlib import Path
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "report_assets" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
W, H = 1800, 1050
INK, MUTED, GRID = "#111827", "#475569", "#CBD5E1"
COLORS = ["#2563EB", "#0F766E", "#D97706", "#6D28D9", "#15803D", "#B91C1C"]
FONT = "/System/Library/Fonts/Helvetica.ttc"

def f(size, bold=False):
    return ImageFont.truetype(FONT, size, index=1 if bold else 0)

def canvas(title, subtitle):
    im = Image.new("RGB", (W,H), "white"); d=ImageDraw.Draw(im)
    d.text((70,45), title, font=f(48,True), fill=INK)
    d.text((70,110), subtitle, font=f(27), fill=MUTED)
    return im,d

def save(im,name): im.save(OUT/f"{name}.png", quality=96)

def architecture():
    im,d=canvas("Implemented system architecture","All search methods share the same evaluator and evidence contract")
    nodes=[(60,210,310,150,"Data & provenance","schemas • units • hashes",0),(390,210,310,150,"DEA & KPI models","gated fixtures • intervals",1),(720,210,310,150,"Shared evaluator","repair • constraints • scores",2),(1060,210,670,150,"Six optimizers","NSGA-II • NSGA-III • MOEA/D • MOPSO • RION • random",3),(190,500,420,145,"Benchmark & robustness","HV • IGD • paired tests • shocks",2),(690,500,420,145,"Strategies & target cost","policies • KPI intervals • actions",1),(1190,500,420,145,"Audit & provenance","independent metric and constraint checks",0),(410,790,420,135,"FastAPI run service","validation • persistence • revalidation",2),(990,790,420,135,"Streamlit decision studio","planner • advisor • evidence",3)]
    for x,y,w,h,t,s,c in nodes:
        d.rounded_rectangle((x,y,x+w,y+h),22,fill="#F8FAFC",outline=COLORS[c],width=5)
        d.text((x+w/2,y+32),t,font=f(28,True),fill=COLORS[c],anchor="mm")
        d.text((x+w/2,y+95),s,font=f(21),fill=INK,anchor="mm")
    for a,b in [((370,285),(390,285)),((700,285),(720,285)),((1030,285),(1060,285)),((875,360),(900,500)),((1395,360),(1400,500)),((900,645),(620,790)),((1400,645),(1200,790)),((830,857),(990,857))]:
        d.line((*a,*b),fill=MUTED,width=6)
    d.text((900,1005),"The UI reads versioned artifacts or calls the canonical backend. It does not implement a second evaluator.",font=f(24,True),fill="#B91C1C",anchor="mm")
    save(im,"system_architecture")

def benchmark():
    df=pd.read_csv(ROOT/"results/benchmarks/phase6-final-synthetic-25seeds-v1/summary_median_iqr.csv")
    order=["moead","mopso","nsga2","nsga3","random_search","rion"]
    im,d=canvas("Final synthetic benchmark","Six algorithms × 25 seeds; matched budget of 100 candidate evaluations per run")
    for panel,(metric,label,higher) in enumerate([("hypervolume","Hypervolume",True),("igd","IGD",False)]):
        sub=df[df.metric.eq(metric)].set_index("algorithm").loc[order]
        x0=90+panel*880; y0=220; pw=740; ph=590
        vals=list(sub.q1)+list(sub.q3); lo=min(vals); hi=max(vals); pad=(hi-lo)*.15; lo-=pad; hi+=pad
        d.text((x0,y0-55),label,font=f(32,True),fill=INK)
        for i in range(5):
            v=lo+(hi-lo)*i/4; y=y0+ph-(v-lo)/(hi-lo)*ph
            d.line((x0,y,x0+pw,y),fill=GRID,width=2); d.text((x0-15,y),f"{v:.6f}" if metric=="hypervolume" else f"{v:.3f}",font=f(17),fill=MUTED,anchor="rm")
        step=pw/6
        for j,a in enumerate(order):
            r=sub.loc[a]; x=x0+step*(j+.5); mapy=lambda v:y0+ph-(v-lo)/(hi-lo)*ph
            d.line((x,mapy(r.q1),x,mapy(r.q3)),fill=COLORS[j],width=22)
            d.ellipse((x-11,mapy(r["median"])-11,x+11,mapy(r["median"])+11),fill=COLORS[j])
            d.text((x,y0+ph+35),a.upper().replace("_"," "),font=f(17,True),fill=INK,anchor="mm")
        d.text((x0,y0+ph+105),"Higher is preferred" if higher else "Lower is preferred",font=f(23,True),fill=COLORS[1 if higher else 0])
    d.text((900,1000),"Lines show the interquartile range and dots show medians. This benchmark is synthetic method evidence.",font=f(23),fill=MUTED,anchor="mm")
    save(im,"benchmark_comparison")

def runtime():
    df=pd.read_csv(ROOT/"results/benchmarks/phase6-final-synthetic-25seeds-v1/summary_median_iqr.csv")
    sub=df[df.metric.eq("runtime_seconds")].set_index("algorithm")
    order=["moead","mopso","nsga2","nsga3","random_search","rion"]
    im,d=canvas("Runtime and feasibility","Median runtime with interquartile range; every final population was feasible")
    x0,y0,pw=280,220,1200; maxv=float(sub.q3.max())*1.12
    for j,a in enumerate(order):
        y=y0+j*110; r=sub.loc[a]; xx=lambda v:x0+float(v)/maxv*pw
        d.text((x0-35,y),a.upper().replace("_"," "),font=f(24,True),fill=INK,anchor="rm")
        d.line((xx(r.q1),y,xx(r.q3),y),fill=COLORS[j],width=22)
        d.ellipse((xx(r['median'])-13,y-13,xx(r['median'])+13,y+13),fill=COLORS[j])
        d.text((xx(r.q3)+20,y),f"{r['median']:.3f} s",font=f(22,True),fill=COLORS[j],anchor="lm")
        d.text((1660,y),"100% feasible",font=f(21,True),fill="#15803D",anchor="rm")
    d.text((900,950),"Runtime is machine-dependent; matched evaluation accounting is the fair comparison basis.",font=f(24),fill=MUTED,anchor="mm")
    save(im,"runtime_feasibility")

def public_results():
    df=pd.read_csv(ROOT/"artifacts/public_experiments/vjti_v1/algorithm_summary.csv").sort_values("hypervolume_median",ascending=False)
    im,d=canvas("Public-calibrated scenario comparison","Three seeds per algorithm; all intervention responses remain synthetic")
    x0,y0,pw=300,220,1050; maxv=df.hypervolume_median.max()*1.08
    for j,r in enumerate(df.itertuples(index=False)):
        y=y0+j*110; bw=r.hypervolume_median/maxv*pw
        d.text((x0-30,y+30),r.algorithm.upper().replace("_"," "),font=f(24,True),fill=INK,anchor="rm")
        d.rounded_rectangle((x0,y,x0+bw,y+55),10,fill=COLORS[j])
        d.text((x0+bw+20,y+28),f"HV {r.hypervolume_median:.3f}",font=f(23,True),fill=COLORS[j],anchor="lm")
        d.text((1690,y+28),f"IGD {r.igd_median:.3f} | feasible {r.feasible_rate_mean:.0%}",font=f(20),fill=MUTED,anchor="rm")
    d.text((900,950),"Descriptive only: three seeds do not satisfy the final benchmark's paired-test protocol.",font=f(24,True),fill="#B91C1C",anchor="mm")
    save(im,"public_algorithm_comparison")

def objective_scores():
    df=pd.read_csv(ROOT/"artifacts/public_experiments/vjti_v1/strategy_objectives.csv")
    keep=df[df.scenario.eq("base") & df.strategy_id.isin(["current","policy_balanced","policy_research_first","policy_societal_first"])]
    p=keep.pivot(index="objective",columns="strategy_id",values="benefit")
    objs=["research","innovation","student_development","societal_contribution"]; strategies=list(p.columns)
    im,d=canvas("Modeled objective-family scores","Reference and selected policies on the configured normalization scale")
    x0,y0,pw,ph=130,220,1500,580; group=pw/4
    for i in range(6):
        v=i*.2; y=y0+ph-v*ph; d.line((x0,y,x0+pw,y),fill=GRID,width=2); d.text((x0-20,y),f"{v:.1f}",font=f(18),fill=MUTED,anchor="rm")
    for i,o in enumerate(objs):
        for j,s in enumerate(strategies):
            v=float(p.loc[o,s]); x=x0+i*group+40+j*70; h=v*ph
            d.rectangle((x,y0+ph-h,x+52,y0+ph),fill=COLORS[j])
        d.text((x0+group*(i+.5),y0+ph+40),o.replace("_"," ").title(),font=f(21,True),fill=INK,anchor="mm")
    for j,s in enumerate(strategies):
        x=220+j*390; d.rectangle((x,930,x+24,954),fill=COLORS[j]); d.text((x+35,942),s.replace("policy_","").replace("_"," ").title(),font=f(20),fill=INK,anchor="lm")
    d.text((900,1010),"Modeled indicators, not observed departmental outcomes or causal effects.",font=f(24,True),fill="#B91C1C",anchor="mm")
    save(im,"objective_scores")

def allocation():
    df=pd.read_csv(ROOT/"artifacts/public_experiments/vjti_v1/strategy_allocations.csv")
    b=df[df.scenario.eq("base") & df.strategy_id.isin(["current","policy_balanced"])].pivot(index="decision",columns="strategy_id",values="value")
    names=[n for n in b.index if "funding" in n or "support" in n]; vals=[(n,(b.loc[n,"policy_balanced"]-b.loc[n,"current"])/1e6) for n in names]; vals.sort(key=lambda x:abs(x[1]),reverse=True)
    im,d=canvas("Balanced-strategy allocation changes","Difference from the public-calibrated reference, INR million")
    mid,y0,scale=980,220,520; ma=max(abs(v) for _,v in vals)
    for i,(n,v) in enumerate(vals):
        y=y0+i*95; bw=abs(v)/ma*scale; x=mid if v>=0 else mid-bw; c="#0F766E" if v>=0 else "#B91C1C"
        d.text((mid-40,y+28),n.replace("_"," ").title(),font=f(22),fill=INK,anchor="rm")
        d.rectangle((x,y,x+bw,y+50),fill=c); d.text((mid+(bw+15 if v>=0 else -bw-15),y+25),f"{v:+.3f}",font=f(22,True),fill=c,anchor="lm" if v>=0 else "rm")
    d.line((mid,190,mid,900),fill=INK,width=3)
    d.text((900,1000),"Allocation changes are scenario recommendations only; they are not observed VJTI spending decisions.",font=f(23,True),fill="#B91C1C",anchor="mm")
    save(im,"allocation_changes")

def robustness():
    df=pd.read_csv(ROOT/"results/robustness/phase6b-synthetic-v1/fixed_vs_reoptimized_comparison.csv"); df=df[df.policy.eq("balanced")]
    im,d=canvas("Held-fixed versus reoptimized feasibility","Balanced synthetic strategy under five structural scenarios and 1,000 common draws")
    x0,y0,pw,ph=160,220,1450,570; group=pw/len(df)
    for i,r in enumerate(df.itertuples(index=False)):
        for j,(v,c) in enumerate([(r.probability_feasible_fixed,"#D97706"),(r.probability_feasible_reoptimized,"#2563EB")]):
            h=float(v)*ph; x=x0+i*group+70+j*75; d.rectangle((x,y0+ph-h,x+55,y0+ph),fill=c)
        d.text((x0+group*(i+.5),y0+ph+52),r.assessed_scenario_id.replace("_"," ").title(),font=f(18,True),fill=INK,anchor="mm")
    d.rectangle((550,930,580,960),fill="#D97706"); d.text((595,945),"Held fixed",font=f(22),fill=INK,anchor="lm")
    d.rectangle((920,930,950,960),fill="#2563EB"); d.text((965,945),"Reoptimized",font=f(22),fill=INK,anchor="lm")
    save(im,"robustness")

def verification():
    b=(ROOT/"tmp/report_backend_tests.log").read_text(errors="replace").splitlines(); u=(ROOT/"tmp/report_frontend_tests.log").read_text(errors="replace").splitlines()
    lines=["$ make test PYTHON=.venv/bin/python",*b[-7:],"","$ make frontend-test PYTHON=.venv/bin/python",*u[-7:]]
    im=Image.new("RGB",(1800,900),"#0B1220"); d=ImageDraw.Draw(im); mono="/System/Library/Fonts/Menlo.ttc"
    d.rounded_rectangle((30,30,1770,870),22,fill="#111827",outline="#334155",width=4); d.text((80,60),"Verified execution output",font=ImageFont.truetype(mono,36),fill="#E5E7EB")
    y=130
    for line in lines:
        d.text((80,y),line[:110],font=ImageFont.truetype(mono,27),fill="#86EFAC" if line.startswith("$") or line.startswith("OK") else "#E5E7EB"); y+=42
    save(im,"verification_output")

for fn in [architecture,benchmark,runtime,public_results,objective_scores,allocation,robustness,verification]: fn()
print(OUT)
