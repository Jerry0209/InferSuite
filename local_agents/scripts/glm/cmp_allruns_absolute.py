#!/usr/bin/env python3
"""Part 2: call-structure per run, absolute wall/CPU, what's-heavy inside fences."""
import os, glob, subprocess
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

MINE="/home/thu/InferSuite/local_agents/superseded_40min/data"
MOH ="/home/thu/llm-service-kernel-latest/archive/certified_glm_40min"
OUT ="/home/thu/InferSuite/local_agents/superseded_40min/plots/compare"
TASKS=["scikit-learn","astropy","sympy","django"]
SHORT={"scikit-learn":"sk","astropy":"as","sympy":"sy","django":"dj"}
C=dict(wait="#9aa8a2", tool="#159f77", harn="#6b4fa0", llm="#cf6a1f")

def series(f):
    ts,us=[],[]
    if not os.path.exists(f): return ts,us
    for ln in open(f):
        p=ln.split()
        try: ts.append(float(p[0])); us.append(float(p[2]))
        except: pass
    return ts,us
def rates(ts,us):
    out=[]
    for i in range(1,len(ts)):
        dt=ts[i]-ts[i-1]; du=us[i]-us[i-1]
        if dt>0 and du>=0: out.append(((du/1e6)/dt, dt))
    return out
def core_s(us):
    d=0.0;p=None
    for u in us:
        if p is not None and u>p: d+=u-p
        p=u
    return d/1e6
def bursts(r, floor=0.005, gap=0.4, heavy=0.3):
    """burst list [(dur_s, peak)] from rate series with gap merge"""
    out=[]; cur=None; gap_t=0.0
    for c,dt in r:
        if c>floor:
            if cur is None: cur=[dt,c]
            else: cur[0]+=gap_t+dt; cur[1]=max(cur[1],c)
            gap_t=0.0
        elif cur is not None:
            gap_t+=dt
            if gap_t>=gap: out.append(tuple(cur)); cur=None; gap_t=0.0
    if cur: out.append(tuple(cur))
    return out
def looped(d):
    tj=[t for t in glob.glob(f"{d}/traj/*/*.traj")+glob.glob(f"{d}/traj/*.traj")
        if os.path.basename(t)[0]!='r' and os.path.getsize(t)>100]
    if not tj: return "?"
    lines=subprocess.run(["grep","-oE",r'"action":\s*"[^"]{0,30}',tj[0]],
                         capture_output=True,text=True).stdout.splitlines()[-12:]
    if not lines: return "?"
    return "LOOP" if max(lines.count(x) for x in set(lines))>=8 else "ok"

def run_metrics(root,task,r):
    d=f"{root}/glm_swe_{task}/run_{r}"
    if not os.path.isdir(d): return None
    th,uh=series(f"{d}/cpustat_scope1.tsv"); tt,ut=series(f"{d}/cpustat_scope2.tsv")
    tl,ul=series(f"{d}/cpustat_scope3.tsv")
    if len(th)<2: return None
    wall=th[-1]-th[0]
    rt=rates(tt,ut); rh=rates(th,uh)
    tb=bursts(rt,0.005); hb=bursts(rh,0.02)
    tool_w=sum(c*0 + dt for c,dt in rt if c>0.005)
    harn_w=sum(dt for c,dt in rh if c>0.02)
    turns=open(f"{d}/agent.log",errors="ignore").read().count("STEP ") if os.path.exists(f"{d}/agent.log") else 0
    return dict(task=task,r=r,wall=wall,loop=looped(d),turns=turns,
        hcs=core_s(uh),tcs=core_s(ut),lcs=core_s(ul),
        tool_w=tool_w,harn_w=min(harn_w,wall-tool_w) if wall>tool_w else harn_w,
        nb=len(tb),nheavy=sum(1 for du,pk in tb if pk>0.3),
        med=float(np.median([du for du,_ in tb])) if tb else 0)

def gather(root): return [m for t in TASKS for r in (1,2,3) if (m:=run_metrics(root,t,r))]
MG=gather(MOH); NG=gather(MINE)
def find(g,t,r): return next((x for x in g if x["task"]==t and x["r"]==r),None)

def layout(ax_list_gen):
    pass

def per_run_axes(g, value_fns, ax, colors, labels, stacked=True, log=False):
    xs=[];xt=[];pos=0;loop_marks=[]
    vals=[[] for _ in value_fns]
    for t in TASKS:
        for r in (1,2,3):
            m=find(g,t,r); xs.append(pos); xt.append(f"{SHORT[t]}{r}")
            for vi,fn in enumerate(value_fns):
                vals[vi].append(fn(m) if m else 0)
            loop_marks.append(bool(m) and m["loop"]=="LOOP")
            pos+=1
        pos+=0.6
    xs=np.array(xs); bottoms=np.zeros(len(xs))
    for v,col,lab in zip(vals,colors,labels):
        if stacked:
            ax.bar(xs,v,bottom=bottoms,width=0.8,color=col,label=lab,edgecolor="white",linewidth=.4)
            bottoms+=np.array(v)
        else:
            ax.bar(xs,v,width=0.8,color=col,label=lab)
    top=bottoms if stacked else np.array(vals[0])
    pad=(top.max() if top.max()>0 else 1)*0.02
    for i,lp in enumerate(loop_marks):
        if lp: ax.text(xs[i],top[i]+pad,"⟳",ha="center",va="bottom",fontsize=10,color="#b00")
    ax.set_xticks(xs); ax.set_xticklabels(xt,fontsize=7.5)
    if log: ax.set_yscale("log")
    ax.spines[['top','right']].set_visible(False)
    return xs

# ============ FIG B/C: ABSOLUTE wall + ABSOLUTE cpu ============
fig,axes=plt.subplots(2,2,figsize=(15,9),sharey="row")
for col,(gname,g) in enumerate([("Mohamad — certified",MG),("New campaign",NG)]):
    ax=axes[0][col]
    per_run_axes(g,[lambda m:(m["wall"]-m["tool_w"]-m["harn_w"])/60,
                    lambda m:m["tool_w"]/60, lambda m:m["harn_w"]/60],
                 ax,[C["wait"],C["tool"],C["harn"]],
                 ["model wait","tool-active","harness-active"])
    ax.set_title(gname,fontsize=12,fontweight="bold")
    if col==0: ax.set_ylabel("wall-clock (minutes)")
    ax.axhline(40.8,color="#b00",lw=.7,ls=":",alpha=.6)
    if col==1: ax.text(ax.get_xlim()[1],40.8," 40-min cap",fontsize=7.5,color="#b00",va="center")
    ax=axes[1][col]
    per_run_axes(g,[lambda m:m["hcs"],lambda m:m["tcs"],lambda m:m["lcs"]],
                 ax,[C["harn"],C["tool"],C["llm"]],
                 ["harness","tool","litellm"])
    if col==0: ax.set_ylabel("CPU work (core-seconds)")
axes[0][0].legend(loc="upper left",frameon=False,fontsize=9)
axes[1][0].legend(loc="upper right",frameon=False,fontsize=9)
fig.suptitle("Absolute wall-clock (top) and CPU work (bottom) — every run",fontsize=15,y=0.995)
fig.text(0.5,0.005,"Same data as the share slides, un-normalized. ⟳ = loop episode. Dotted red = episode time cap.",
         ha="center",fontsize=9,color="#666")
fig.tight_layout()
fig.savefig(f"{OUT}/cmp_absolute.png",dpi=140,bbox_inches="tight");plt.close(fig)
print("wrote cmp_absolute.png")

# ============ FIG A: CALL / BURST STRUCTURE ============
fig,axes=plt.subplots(2,2,figsize=(15,8.5),sharey="row")
for col,(gname,g) in enumerate([("Mohamad — certified",MG),("New campaign",NG)]):
    ax=axes[0][col]
    xs=per_run_axes(g,[lambda m:m["turns"]],ax,["#5c6b64"],["agent turns"],stacked=False)
    # overlay bursts + heavy
    nb=[]; nh=[]
    for t in TASKS:
        for r in (1,2,3):
            m=find(g,t,r); nb.append(m["nb"] if m else 0); nh.append(m["nheavy"] if m else 0)
    ax.bar(xs+0.0,nb,width=0.5,color=C["tool"],alpha=.85,label="tool bursts")
    ax.bar(xs+0.0,nh,width=0.5,color="#0b5c44",label="heavy bursts (>0.3 cores)")
    ax.set_title(gname,fontsize=12,fontweight="bold")
    if col==0: ax.set_ylabel("count per episode")
    ax=axes[1][col]
    per_run_axes(g,[lambda m:m["med"]],ax,[C["tool"]],["median tool-burst duration"],stacked=False)
    if col==0: ax.set_ylabel("median burst duration (s)")
axes[0][0].legend(loc="upper left",frameon=False,fontsize=9)
fig.suptitle("Tool-call / burst structure — every run",fontsize=15,y=0.995)
fig.text(0.5,0.005,"Grey = agent turns (STEP markers). Green = detected tool bursts; dark green = heavy. ⟳ = loop episode.",
         ha="center",fontsize=9,color="#666")
fig.tight_layout()
fig.savefig(f"{OUT}/cmp_callstruct.png",dpi=140,bbox_inches="tight");plt.close(fig)
print("wrote cmp_callstruct.png")

# ============ FIG D: WHAT'S HEAVY INSIDE THE FENCES ============
# featured runs per campaign
FEAT_M={"scikit-learn":1,"astropy":1,"sympy":1,"django":2}
FEAT_N={"scikit-learn":1,"astropy":2,"sympy":2,"django":2}
# tool-fence by agent-call class (from plot_internal_tools stdout, hardcoded from captured tables)
CLS=["build/tests","other bash","git","internal"]
CLS_COL={"build/tests":"#0b5c44","other bash":"#159f77","git":"#67c6ab","internal":"#c9e9df"}
TOOL_M={"scikit-learn":{"build/tests":1747.0,"other bash":5.6,"git":0.4,"internal":7.3},
        "astropy":{"build/tests":124.6,"other bash":6.0,"git":1.6,"internal":1.9},
        "sympy":{"build/tests":32.1,"other bash":5.7,"git":1.9,"internal":5.8},
        "django":{"build/tests":0.0,"other bash":1.2,"git":141.8,"internal":0.1}}
TOOL_N={"scikit-learn":{"build/tests":1429.2,"other bash":4.8,"git":0.9,"internal":6.6},
        "astropy":{"build/tests":168.1,"other bash":57.9,"git":2.7,"internal":2.2},
        "sympy":{"build/tests":73.4,"other bash":11.9,"git":1.1,"internal":7.4},
        "django":{"build/tests":0.2,"other bash":14.6,"git":0.9,"internal":0.0}}
def dso_cat(path):
    p=path.lower()
    if "openblas" in p or "libgomp" in p or "lapack" in p: return "BLAS/OpenMP"
    if "/bin/python" in p or "python3." in p and ".so" not in p: return "python interpreter"
    if "tiktoken" in p: return "tiktoken"
    if "_json" in p or "pydantic" in p or "multidict" in p: return "JSON/pydantic"
    if "kernel" in p: return "OS kernel"
    if "libc" in p or "ld-linux" in p or "libm" in p: return "libc/loader"
    return "other"
HD_CATS=["python interpreter","tiktoken","JSON/pydantic","libc/loader","OS kernel","other"]
HD_COL={"python interpreter":"#6b4fa0","tiktoken":"#9b7fd4","JSON/pydantic":"#c4b0ec",
        "libc/loader":"#8a8f9c","OS kernel":"#d05555","other":"#dddddd"}
def harness_dso(root,task,r):
    f=f"{root}/glm_swe_{task}/run_{r}/scope1_dso.txt"
    out={k:0.0 for k in HD_CATS}
    if not os.path.exists(f): return out
    for ln in open(f):
        try: pct,path=ln.split(None,1)
        except: continue
        try: v=float(pct.rstrip("%"))
        except: continue
        c=dso_cat(path.strip())
        out[c if c in out else "other"]+=v
    return out

fig,axes=plt.subplots(2,2,figsize=(15,9))
for col,(gname,TOOL,root,FEAT) in enumerate([("Mohamad — certified",TOOL_M,MOH,FEAT_M),
                                              ("New campaign",TOOL_N,MINE,FEAT_N)]):
    ax=axes[0][col]; xs=np.arange(len(TASKS))
    bottoms=np.zeros(len(TASKS))
    for cl in CLS:
        v=[100*TOOL[t][cl]/max(1e-9,sum(TOOL[t].values())) for t in TASKS]
        ax.bar(xs,v,bottom=bottoms,color=CLS_COL[cl],label=cl,width=0.66,edgecolor="white")
        bottoms+=np.array(v)
    for i,t in enumerate(TASKS):
        ax.text(xs[i],103,f"{sum(TOOL[t].values()):.0f} cs",ha="center",fontsize=8,color="#666")
        if t=="django": ax.text(xs[i],-8,"(looped)",ha="center",fontsize=7.5,color="#b00")
    ax.set_xticks(xs);ax.set_xticklabels(TASKS,fontsize=9);ax.set_ylim(0,112)
    ax.set_title(f"{gname} — tool fence by agent-call class",fontsize=11,fontweight="bold")
    if col==0: ax.set_ylabel("share of tool-fence CPU (%)")
    ax.spines[['top','right']].set_visible(False)
    ax=axes[1][col]; bottoms=np.zeros(len(TASKS))
    for cat in HD_CATS:
        v=[harness_dso(root,t,FEAT[t])[cat] for t in TASKS]
        ax.bar(xs,v,bottom=bottoms,color=HD_COL[cat],label=cat,width=0.66,edgecolor="white")
        bottoms+=np.array(v)
    ax.set_xticks(xs);ax.set_xticklabels(TASKS,fontsize=9);ax.set_ylim(0,112)
    ax.set_title(f"{gname} — harness fence by library (perf DSO)",fontsize=11,fontweight="bold")
    if col==0: ax.set_ylabel("share of harness samples (%)")
    ax.spines[['top','right']].set_visible(False)
axes[0][0].legend(loc="lower left",frameon=False,fontsize=8.5)
axes[1][0].legend(loc="lower left",frameon=False,fontsize=8.5,ncol=2)
fig.suptitle("What is actually heavy inside each fence (featured runs)",fontsize=15,y=0.995)
fig.text(0.5,0.005,"Top: tool-fence core-seconds attributed to agent-call classes (traj-anchored; totals above bars). "
         "Bottom: harness-fence perf-record samples by library.",ha="center",fontsize=9,color="#666")
fig.tight_layout()
fig.savefig(f"{OUT}/cmp_whats_heavy.png",dpi=140,bbox_inches="tight");plt.close(fig)
print("wrote cmp_whats_heavy.png")
print("DONE")
