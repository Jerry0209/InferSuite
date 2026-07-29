#!/usr/bin/env python3
"""All-runs TMA L1 comparison figure from tma_allruns.json."""
import json, os, glob, subprocess
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SP="/home/thu/InferSuite/local_agents/superseded_40min/data/l3_study"
OUT="/home/thu/InferSuite/local_agents/superseded_40min/plots/compare"
D=json.load(open(f"{SP}/tma_allruns.json"))
TASKS=["scikit-learn","astropy","sympy","django"]
EXTRA_NEW=["django-t06"]
SHORT={"scikit-learn":"sk","astropy":"as","sympy":"sy","django":"dj","django-t06":"dj.6"}
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
                xs.append(pos);xt.append(f"{SHORT[t]}{r}")
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
