#!/usr/bin/env python3
"""Run-to-run comparison figures: all runs, both campaigns, 3 categories."""
import os, glob, json
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np

MINE="/home/thu/InferSuite/local_agents/superseded_40min/data"
MOH ="/home/thu/llm-service-kernel-latest/archive/certified_glm_40min"
OUT ="/home/thu/InferSuite/local_agents/superseded_40min/plots/compare"
os.makedirs(OUT, exist_ok=True)
TASKS=["scikit-learn","astropy","sympy","django"]
SHORT={"scikit-learn":"sk","astropy":"as","sympy":"sy","django":"dj"}
FLOOR={"tool":0.005,"harn":0.02}
C=dict(wait="#9aa8a2", tool="#159f77", harn="#6b4fa0", llm="#cf6a1f")

def series(f):
    ts=[]; us=[]
    if not os.path.exists(f): return ts,us
    for ln in open(f):
        p=ln.split()
        try: ts.append(float(p[0])); us.append(float(p[2]))
        except: pass
    return ts,us

def rates(ts,us):
    """returns (mid_t, cores) with reset handling"""
    t=[]; c=[]
    for i in range(1,len(ts)):
        dt=ts[i]-ts[i-1]; du=us[i]-us[i-1]
        if dt<=0 or du<0: continue
        t.append(ts[i]-ts[0]); c.append((du/1e6)/dt)
    return t,c

def core_s(us):
    d=0.0; p=None
    for u in us:
        if p is not None and u>p: d+=u-p
        p=u
    return d/1e6

def run_metrics(root, task, r):
    d=f"{root}/glm_swe_{task}/run_{r}"
    if not os.path.isdir(d): return None
    th,uh=series(f"{d}/cpustat_scope1.tsv")   # harness
    tt,ut=series(f"{d}/cpustat_scope2.tsv")   # tool
    tl,ul=series(f"{d}/cpustat_scope3.tsv")   # litellm
    if len(th)<2: return None
    wall=(th[-1]-th[0])
    hcs,tcs,lcs=core_s(uh),core_s(ut),core_s(ul)
    # active wall (mutually exclusive: tool wins, then harness, else wait)
    rt,ct=rates(tt,ut); rh,ch=rates(th,uh)
    # align by index (same 10Hz clock, same length approx); use min length
    n=min(len(ct),len(ch))
    tool_w=harn_w=0.0
    for i in range(n):
        dt=0.1  # ~10Hz
        if ct[i]>FLOOR["tool"]: tool_w+=dt
        elif ch[i]>FLOOR["harn"]: harn_w+=dt
    wait_w=max(0.0, wall-tool_w-harn_w)
    # loop check
    tj=[t for t in glob.glob(f"{d}/traj/*/*.traj")+glob.glob(f"{d}/traj/*.traj")
        if os.path.basename(t)[0]!='r' and os.path.getsize(t)>100]
    loop="?"
    if tj:
        import subprocess
        lines=subprocess.run(["grep","-oE",r'"action":\s*"[^"]{0,30}',tj[0]],
                             capture_output=True,text=True).stdout.splitlines()[-12:]
        if lines: loop="LOOP" if max(lines.count(x) for x in set(lines))>=8 else "ok"
    turns=open(f"{d}/agent.log",errors="ignore").read().count("STEP ") if os.path.exists(f"{d}/agent.log") else 0
    return dict(task=task,r=r,wall_min=wall/60,turns=turns,loop=loop,
                hcs=hcs,tcs=tcs,lcs=lcs,cs_tot=hcs+tcs+lcs or 1,
                wait_w=wait_w,tool_w=tool_w,harn_w=harn_w,wall_s=wall,
                series_tool=(rt,ct),series_harn=(rh,ch))

def gather(root):
    out=[]
    for t in TASKS:
        for r in (1,2,3):
            m=run_metrics(root,t,r)
            if m: out.append(m)
    return out

MG=gather(MOH); NG=gather(MINE)

# ---- validation against plotter values_dump (featured runs) ----
vd=json.load(open("/home/thu/InferSuite/local_agents/superseded_40min/plots/values_dump.json"))
def find(g,task,r):
    return next((x for x in g if x["task"]==task and x["r"]==r),None)
print("VALIDATION (my computed vs plotter values_dump):")
for task,r in [("scikit-learn",1),("astropy",2),("sympy",2)]:
    m=find(NG,task,r); key=f"{task} (Python)"
    if m and key in vd:
        v=vd[key]
        print(f"  {task} r{r}: tool_active {m['tool_w']:.0f}s vs {v['tool_active_s']:.0f}  "
              f"harn_active {m['harn_w']:.0f}s vs {v['harn_active_s']:.0f}  "
              f"core-s {m['cs_tot']:.0f} vs {sum(v['cs']):.0f}")

# ================= FIG 1: WALL-CLOCK SPLIT (shares, all runs) =================
def stacked_split(groups, keys, colors, labels, title, fname, note):
    fig,axes=plt.subplots(1,2,figsize=(15,5.4),sharey=True)
    for ax,(gname,g) in zip(axes,groups):
        xs=[]; xt=[]; pos=0; bottoms=None
        vals={k:[] for k in keys}; looped=[]
        for t in TASKS:
            for r in (1,2,3):
                m=find(g,t,r)
                xs.append(pos); xt.append(f"{SHORT[t]}{r}")
                if m:
                    tot=sum(m[k] for k in keys) or 1
                    for k in keys: vals[k].append(100*m[k]/tot)
                    looped.append(m["loop"]=="LOOP")
                else:
                    for k in keys: vals[k].append(0)
                    looped.append(False)
                pos+=1
            pos+=0.6
        xs=np.array(xs); bottoms=np.zeros(len(xs))
        for k,col,lab in zip(keys,colors,labels):
            ax.bar(xs,vals[k],bottom=bottoms,width=0.8,color=col,label=lab,edgecolor="white",linewidth=.5)
            bottoms+=np.array(vals[k])
        for i,lp in enumerate(looped):
            if lp: ax.text(xs[i],102,"⟳",ha="center",va="bottom",fontsize=11,color="#b00")
        ax.set_title(gname,fontsize=12,fontweight="bold")
        ax.set_xticks(xs); ax.set_xticklabels(xt,fontsize=8)
        ax.set_ylim(0,108); ax.set_ylabel("share of wall (%)")
        ax.spines[['top','right']].set_visible(False)
    axes[0].legend(loc="lower center",bbox_to_anchor=(1.05,-0.22),ncol=len(keys),frameon=False,fontsize=10)
    fig.suptitle(title,fontsize=15,y=1.02)
    fig.text(0.5,-0.06,note,ha="center",fontsize=9,color="#666")
    fig.tight_layout()
    fig.savefig(f"{OUT}/{fname}",dpi=140,bbox_inches="tight"); plt.close(fig)
    print("wrote",fname)

stacked_split([("Mohamad — certified",MG),("New campaign",NG)],
    ["wait_w","tool_w","harn_w"],[C["wait"],C["tool"],C["harn"]],
    ["Inference / model wait","Tool execution","Agent harness"],
    "Wall-clock time split — every run",
    "cmp_wall_split.png",
    "⟳ = degenerate loop episode.  Bars are % of wall; each is one run (sk/as/sy/dj × run 1–3).")

# ================= FIG 2: CPU WORK (shares, all runs) =================
stacked_split([("Mohamad — certified",MG),("New campaign",NG)],
    ["harn_cs_k","tool_cs_k","llm_cs_k"],None,None,"","",None) if False else None
# reuse with cs keys — adapt: build a small wrapper
def stacked_cs(groups):
    fig,axes=plt.subplots(1,2,figsize=(15,5.4),sharey=True)
    keys=[("hcs",C["harn"],"Agent harness"),("tcs",C["tool"],"Tool execution"),("lcs",C["llm"],"litellm (proxy)")]
    for ax,(gname,g) in zip(axes,groups):
        xs=[];xt=[];pos=0;looped=[]
        vals=[[],[],[]]; tots=[]
        for t in TASKS:
            for r in (1,2,3):
                m=find(g,t,r); xs.append(pos);xt.append(f"{SHORT[t]}{r}")
                if m:
                    tot=m["hcs"]+m["tcs"]+m["lcs"] or 1; tots.append(tot)
                    vals[0].append(100*m["hcs"]/tot);vals[1].append(100*m["tcs"]/tot);vals[2].append(100*m["lcs"]/tot)
                    looped.append(m["loop"]=="LOOP")
                else:
                    for v in vals: v.append(0)
                    tots.append(0); looped.append(False)
                pos+=1
            pos+=0.6
        xs=np.array(xs);bottoms=np.zeros(len(xs))
        for (k,col,lab),v in zip(keys,vals):
            ax.bar(xs,v,bottom=bottoms,width=0.8,color=col,label=lab,edgecolor="white",linewidth=.5)
            bottoms+=np.array(v)
        for i,(lp,tt) in enumerate(zip(looped,tots)):
            if lp: ax.text(xs[i],102,"⟳",ha="center",va="bottom",fontsize=11,color="#b00")
            if tt: ax.text(xs[i],-6,f"{tt:.0f}",ha="center",va="top",fontsize=6.5,color="#888",rotation=0)
        ax.set_title(gname,fontsize=12,fontweight="bold")
        ax.set_xticks(xs);ax.set_xticklabels(xt,fontsize=8)
        ax.set_ylim(0,108);ax.set_ylabel("share of CPU work (%)")
        ax.spines[['top','right']].set_visible(False)
    axes[0].legend(loc="lower center",bbox_to_anchor=(1.05,-0.24),ncol=3,frameon=False,fontsize=10)
    fig.suptitle("CPU work split (core-seconds) — every run",fontsize=15,y=1.02)
    fig.text(0.5,-0.08,"⟳ = loop episode.  Grey number under each bar = total core-seconds (absolute).",ha="center",fontsize=9,color="#666")
    fig.tight_layout()
    fig.savefig(f"{OUT}/cmp_cpu_work.png",dpi=140,bbox_inches="tight");plt.close(fig)
    print("wrote cmp_cpu_work.png")
stacked_cs([("Mohamad — certified",MG),("New campaign",NG)])

# ================= FIG 3: ORCHESTRATION TIMELINE small-multiples =================
def timeline_grid(gname,g,fname):
    fig,axes=plt.subplots(4,3,figsize=(14,9),sharex=False)
    for ti,t in enumerate(TASKS):
        for ri,r in enumerate((1,2,3)):
            ax=axes[ti][ri]; m=find(g,t,r)
            if m:
                tt,ct=m["series_tool"]; th,ch=m["series_harn"]
                if tt: ax.fill_between([x/60 for x in tt],ct,color=C["tool"],lw=0,alpha=.9)
                if th: ax.plot([x/60 for x in th],ch,color=C["harn"],lw=.4,alpha=.7)
                tag=" ⟳" if m["loop"]=="LOOP" else ""
                ax.set_title(f"{SHORT[t]} run{r}  ({m['wall_min']:.0f}m{tag})",fontsize=8.5,
                             color="#b00" if m["loop"]=="LOOP" else "#222")
                ax.set_ylim(0,max(1,max(ct) if ct else 1)*1.1)
            else:
                ax.text(.5,.5,"—",ha="center",va="center",transform=ax.transAxes,color="#bbb")
                ax.set_title(f"{SHORT[t]} run{r}",fontsize=8.5,color="#bbb")
            ax.tick_params(labelsize=6.5); ax.spines[['top','right']].set_visible(False)
            if ri==0: ax.set_ylabel(t,fontsize=8)
    fig.suptitle(f"Orchestration timeline — {gname}  (green = tool cores, purple = harness cores; x = minutes)",fontsize=13,y=1.0)
    fig.tight_layout()
    fig.savefig(f"{OUT}/{fname}",dpi=130,bbox_inches="tight");plt.close(fig)
    print("wrote",fname)
timeline_grid("Mohamad (certified)",MG,"cmp_timeline_moh.png")
timeline_grid("New campaign",NG,"cmp_timeline_new.png")
print("DONE")
