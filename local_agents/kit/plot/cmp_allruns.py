#!/usr/bin/env python3
"""cmp_allruns.py — run-to-run comparison of the reproduced 40-min campaign
(superseded_40min) vs the predecessor's certified campaign, every run, both campaigns.

Merged 2026-08-05 from cmp_allruns_shares.py + cmp_allruns_absolute.py + cmp_tma_allruns.py
(one --view per legacy script; figures and numbers unchanged):

  --view shares    wall-clock + CPU-work share stacks + timeline small-multiples
                   (cmp_wall_split.png, cmp_cpu_work.png, cmp_timeline_{moh,new}.png)
  --view absolute  absolute wall/CPU, call/burst structure, what's-heavy-inside-fences
                   (cmp_absolute.png, cmp_callstruct.png, cmp_whats_heavy.png)
  --view tma       TMA L1 all-runs grid from l3_study/tma_allruns.json
                   (cmp_tma_l1_allruns.png)
  --view all       everything above

The certified reference (MOH) lives OUTSIDE this repo on this workstation.
"""
import argparse, os, glob, json, subprocess
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

def core_s(us):
    d=0.0; p=None
    for u in us:
        if p is not None and u>p: d+=u-p
        p=u
    return d/1e6

def looped(d):
    tj=[t for t in glob.glob(f"{d}/traj/*/*.traj")+glob.glob(f"{d}/traj/*.traj")
        if os.path.basename(t)[0]!='r' and os.path.getsize(t)>100]
    if not tj: return "?"
    lines=subprocess.run(["grep","-oE",r'"action":\s*"[^"]{0,30}',tj[0]],
                         capture_output=True,text=True).stdout.splitlines()[-12:]
    if not lines: return "?"
    return "LOOP" if max(lines.count(x) for x in set(lines))>=8 else "ok"

# ================================================================================
# view: shares  (formerly cmp_allruns_shares.py)
# ================================================================================
def view_shares():
    FLOOR={"tool":0.005,"harn":0.02}

    def rates(ts,us):
        """returns (mid_t, cores) with reset handling"""
        t=[]; c=[]
        for i in range(1,len(ts)):
            dt=ts[i]-ts[i-1]; du=us[i]-us[i-1]
            if dt<=0 or du<0: continue
            t.append(ts[i]-ts[0]); c.append((du/1e6)/dt)
        return t,c

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
        loop=looped(d)
        turns=open(f"{d}/agent.log",errors="ignore").read().count("STEP ") if os.path.exists(f"{d}/agent.log") else 0
        return dict(task=task,r=r,wall_min=wall/60,turns=turns,loop=loop,
                    hcs=hcs,tcs=tcs,lcs=lcs,cs_tot=hcs+tcs+lcs or 1,
                    wait_w=wait_w,tool_w=tool_w,harn_w=harn_w,wall_s=wall,
                    series_tool=(rt,ct),series_harn=(rh,ch))

    def gather(root):
        return [m for t in TASKS for r in (1,2,3) if (m:=run_metrics(root,t,r))]

    MG=gather(MOH); NG=gather(MINE)

    def find(g,task,r):
        return next((x for x in g if x["task"]==task and x["r"]==r),None)

    # ---- validation against plotter values_dump (featured runs) ----
    vd=json.load(open("/home/thu/InferSuite/local_agents/superseded_40min/plots/values_dump.json"))
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
            vals={k:[] for k in keys}; loopmk=[]
            for t in TASKS:
                for r in (1,2,3):
                    m=find(g,t,r)
                    xs.append(pos); xt.append(f"{SHORT[t]}{r}")
                    if m:
                        tot=sum(m[k] for k in keys) or 1
                        for k in keys: vals[k].append(100*m[k]/tot)
                        loopmk.append(m["loop"]=="LOOP")
                    else:
                        for k in keys: vals[k].append(0)
                        loopmk.append(False)
                    pos+=1
                pos+=0.6
            xs=np.array(xs); bottoms=np.zeros(len(xs))
            for k,col,lab in zip(keys,colors,labels):
                ax.bar(xs,vals[k],bottom=bottoms,width=0.8,color=col,label=lab,edgecolor="white",linewidth=.5)
                bottoms+=np.array(vals[k])
            for i,lp in enumerate(loopmk):
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
    def stacked_cs(groups):
        fig,axes=plt.subplots(1,2,figsize=(15,5.4),sharey=True)
        keys=[("hcs",C["harn"],"Agent harness"),("tcs",C["tool"],"Tool execution"),("lcs",C["llm"],"litellm (proxy)")]
        for ax,(gname,g) in zip(axes,groups):
            xs=[];xt=[];pos=0;loopmk=[]
            vals=[[],[],[]]; tots=[]
            for t in TASKS:
                for r in (1,2,3):
                    m=find(g,t,r); xs.append(pos);xt.append(f"{SHORT[t]}{r}")
                    if m:
                        tot=m["hcs"]+m["tcs"]+m["lcs"] or 1; tots.append(tot)
                        vals[0].append(100*m["hcs"]/tot);vals[1].append(100*m["tcs"]/tot);vals[2].append(100*m["lcs"]/tot)
                        loopmk.append(m["loop"]=="LOOP")
                    else:
                        for v in vals: v.append(0)
                        tots.append(0); loopmk.append(False)
                    pos+=1
                pos+=0.6
            xs=np.array(xs);bottoms=np.zeros(len(xs))
            for (k,col,lab),v in zip(keys,vals):
                ax.bar(xs,v,bottom=bottoms,width=0.8,color=col,label=lab,edgecolor="white",linewidth=.5)
                bottoms+=np.array(v)
            for i,(lp,tt) in enumerate(zip(loopmk,tots)):
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

# ================================================================================
# view: absolute  (formerly cmp_allruns_absolute.py)
# ================================================================================
def view_absolute():
    def rates(ts,us):
        out=[]
        for i in range(1,len(ts)):
            dt=ts[i]-ts[i-1]; du=us[i]-us[i-1]
            if dt>0 and du>=0: out.append(((du/1e6)/dt, dt))
        return out

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

# ================================================================================
# view: tma  (formerly cmp_tma_allruns.py)
# ================================================================================
def view_tma():
    SP="/home/thu/InferSuite/local_agents/superseded_40min/data/l3_study"
    D=json.load(open(f"{SP}/tma_allruns.json"))
    EXTRA_NEW=["django-t06"]
    TSHORT=dict(SHORT, **{"django-t06":"dj.6"})
    BUCKETS=["retiring","fe","bad","be"]
    BCOL={"retiring":"#159f77","fe":"#1f77b4","bad":"#d35400","be":"#e6a817"}
    BLAB={"retiring":"Retiring","fe":"Frontend-bound","bad":"Bad speculation","be":"Backend-bound"}
    # loop status (established earlier in the session)
    LOOPS={"moh":{("scikit-learn",2),("astropy",2),("sympy",3),("django",2),("django",3)},
           "new":{("scikit-learn",3),("astropy",1),("astropy",3),("sympy",1),
                  ("django",1),("django",2),("django",3),("django-t06",1),("django-t06",2)}}

    fig,axes=plt.subplots(2,2,figsize=(15,9),sharey=True)
    for col,(camp,gname) in enumerate([("moh","Mohamad — certified"),("new","New campaign")]):
        for row,fence in enumerate([("tma_tool","tool fence"),("tma_harness","harness fence")]):
            key,fname=fence; ax=axes[row][col]
            xs=[];xt=[];pos=0;stacks=[];marks=[]
            tlist=TASKS+(EXTRA_NEW if camp=="new" else [])
            for t in tlist:
                rr=(1,2) if t=="django-t06" else (1,2,3)
                for r in rr:
                    m=D.get(f"{camp}/{t}/r{r}",{}).get(key)
                    xs.append(pos);xt.append(f"{TSHORT[t]}{r}")
                    stacks.append(m); marks.append((t,r) in LOOPS[camp])
                    pos+=1
                pos+=0.6
            xs=np.array(xs);bottoms=np.zeros(len(xs))
            for b in BUCKETS:
                v=[(s or {}).get(b,0) or 0 for s in stacks]
                ax.bar(xs,v,bottom=bottoms,width=0.8,color=BCOL[b],
                       label=BLAB[b] if (row==0 and col==0) else None,
                       edgecolor="white",linewidth=.4)
                bottoms+=np.array(v)
            for i,(lp,s) in enumerate(zip(marks,stacks)):
                if s is None: ax.text(xs[i],50,"—",ha="center",color="#bbb")
                if lp: ax.text(xs[i],101,"⟳",ha="center",va="bottom",fontsize=10,color="#b00")
            ax.set_title(f"{gname} — {fname}",fontsize=11.5,fontweight="bold")
            ax.set_xticks(xs);ax.set_xticklabels(xt,fontsize=7.5)
            ax.set_ylim(0,108)
            if col==0: ax.set_ylabel("pipeline slots (%)")
            ax.spines[['top','right']].set_visible(False)
    fig.legend(loc="lower center",ncol=4,frameon=False,fontsize=10,bbox_to_anchor=(0.5,-0.01))
    fig.suptitle("TMA Level 1 — every run, both campaigns",fontsize=15,y=0.995)
    fig.text(0.5,0.02,"Each bar = one episode's whole-episode TMA (continuous PERF_METRICS census / zero-mux windows). ⟳ = loop episode. — = no data.",
             ha="center",fontsize=9,color="#666")
    fig.tight_layout(rect=[0,0.04,1,1])
    fig.savefig(f"{OUT}/cmp_tma_l1_allruns.png",dpi=140,bbox_inches="tight");plt.close(fig)
    print("wrote cmp_tma_l1_allruns.png")

    # quick text summary for captions
    for camp in ("moh","new"):
        print(f"\n{camp} clean-run tool-fence TMA:")
        for t in TASKS:
            for r in (1,2,3):
                if (t,r) in LOOPS[camp]: continue
                m=D.get(f"{camp}/{t}/r{r}",{}).get("tma_tool")
                if m: print(f"  {t:13} r{r}: ret {m['retiring']:.0f} fe {m['fe']:.0f} bad {m['bad']:.0f} be {m['be']:.0f}")

if __name__ == "__main__":
    ap=argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--view", required=True, choices=["shares","absolute","tma","all"])
    a=ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.view in ("shares","all"):   view_shares()
    if a.view in ("absolute","all"): view_absolute()
    if a.view in ("tma","all"):      view_tma()
    print("DONE")
