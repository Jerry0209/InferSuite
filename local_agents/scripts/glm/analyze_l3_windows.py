#!/usr/bin/env python3
"""analyze_l3_windows.py — per-window metric DISTRIBUTIONS from dedicated-group replays.

Inputs (per replay pass produced by replay_l3_profile.sh):
  run_N/l3group.txt      which counter group this pass dedicated
  run_N/windows.tsv      win  group  t_start  t_end  alive   (epoch seconds)
  run_N/group_<g>_wNNN.txt   exact per-fence counts for that window
  run_N/cmdlog.tsv       epoch \t pid \t argv   (2 Hz host-side tool-cgroup poll)
  run_N/tma_cont.csv     10 s interval series of the topdown census (L1+L2)

Outputs under <DATA>/l3_study/:
  all_windows.csv        LONG format: one row per (pass, window, fence, metric) with value,
                         window epoch, duration, instructions, and the command tag.
  tma_intervals.csv      per-10s-interval TMA L1/L2 shares per fence (another distribution).
  plots/ (only when --plot): box_<metric>.png, tags_<task>_<metric>.png, timeline_<task>_<metric>.png

Usage: analyze_l3_windows.py <data_root> <task_short> [--plot]
"""
import sys, os, re, glob, csv, json, math

DATA = sys.argv[1]; SHORT = sys.argv[2]
DO_PLOT = "--plot" in sys.argv
BASE = f"{DATA}/glm_replay_swe_{SHORT}"
OUTD = f"{DATA}/l3_study"; os.makedirs(OUTD, exist_ok=True)

FENCES = {"harness": "glm-rep", "tool": "docker-"}

# ---- command tagging: argv -> category (taxonomy: build/test, vcs, pkg/compile, agent-tools,
# shell, python-other; aligned with the internal-tools classes + Fig-10-style buckets) ----
def tag_of(argv):
    a = argv.lower()
    if "pytest" in a or "py.test" in a or "runtests" in a or "testbed" in a and " -m " in a and "test" in a:
        return "tests(pytest)"
    if re.search(r"\bcc1\b|\bgcc\b|\bg\+\+|\bld\b|cythonize|build_ext", a): return "compile"
    if re.search(r"\bpip3?\b|setup\.py|\bninja\b|\bmake\b", a): return "pkg/build"
    if re.search(r"\bgit\b", a): return "git"
    if "str_replace" in a or "swerex" in a or "registry" in a or "_state" in a: return "agent-tool"
    if re.search(r"/bin/(ba)?sh\b|^sh |^bash ", a): return "shell"
    if "python" in a: return "python-other"
    return "other"

def window_tags(cmdlog):
    """returns sorted [(t, tag)] samples"""
    out = []
    if not os.path.exists(cmdlog): return out
    for ln in open(cmdlog):
        p = ln.rstrip("\n").split("\t", 2)
        if len(p) < 3: continue
        try: t = float(p[0])
        except: continue
        out.append((t, tag_of(p[2])))
    out.sort()
    return out

# priority: the most specific FOREGROUND activity wins the window. Persistent plumbing
# (swerex server, session shell) is present in every poll and must not dilute the tag.
TAG_PRIORITY = ["tests(pytest)", "compile", "pkg/build", "git", "python-other",
                "shell", "other", "agent-tool"]
def tag_for(win_a, win_b, samples):
    """highest-priority tag observed in [a,b); 'idle' if no samples"""
    seen = set(g for t, g in samples if win_a <= t < win_b)
    if not seen: return "idle"
    for t in TAG_PRIORITY:
        if t in seen: return t
    return "other"

# ---- per-window counter parsing ----
EVRE = re.compile(r"\s*([\d,]+|<not counted>|<not supported>)\s+([\w.:/,=-]+)\s+(\S+)")
def counts(path):
    per = {f: {} for f in FENCES}
    if not os.path.exists(path): return per
    for ln in open(path):
        m = EVRE.match(ln)
        if not m or m.group(1).startswith("<"): continue
        v, ev, cg = float(m.group(1).replace(",", "")), m.group(2), m.group(3)
        for f, tagstr in FENCES.items():
            if tagstr in cg: per[f][ev] = per[f].get(ev, 0.0) + v
    return per

# ---- metric derivations per group (value dict per fence-window) ----
def derive(group, d):
    I = d.get("instructions", 0); C = d.get("cycles", 0)
    g = lambda e: d.get(e, 0.0)
    out = {}
    if I < 5e5 or C <= 0: return out          # too little activity for a stable ratio
    if group == "fpbr":
        out["IPC"] = I / C
        out["branch_MPKI"] = 1000 * g("branches") and 1000 * g("branch-misses") / I
        sc, vec = g("fp_arith_inst_retired.scalar"), g("fp_arith_inst_retired.vector")
        if sc + vec > 1e4: out["vecFP_pct"] = 100 * vec / (sc + vec)
    elif group == "cache":
        l1, l2 = g("mem_load_retired.l1_hit"), g("mem_load_retired.l2_hit")
        l3, lm = g("mem_load_retired.l3_hit"), g("mem_load_retired.l3_miss")
        loads = l1 + l2 + l3 + lm
        out["L1D_MPKI"] = 1000 * (l2 + l3 + lm) / I
        out["L2_MPKI"] = 1000 * (l3 + lm) / I
        out["LLC_MPKI"] = 1000 * lm / I
        if loads > 1e4: out["AMAT_cyc"] = (5*l1 + 15*l2 + 50*l3 + 250*lm) / loads
    elif group == "mlp":
        pc = g("l1d_pend_miss.pending_cycles")
        if pc > 1e4: out["MLP"] = g("l1d_pend_miss.pending") / pc
    elif group == "fe":
        dsb, mite, ms, lsd = g("idq.dsb_uops"), g("idq.mite_uops"), g("idq.ms_uops"), g("lsd.uops")
        ut = dsb + mite + ms + lsd
        if ut > 1e5:
            out["DSB_pct"] = 100 * dsb / ut; out["MITE_pct"] = 100 * mite / ut
            out["MS_pct"] = 100 * ms / ut
    elif group == "fe_lat":
        out["codeRead_MPKI_L1I"] = 1000 * g("l2_rqsts.all_code_rd") / I
        out["icache_data_stall_pct"] = 100 * g("icache_data.stalls") / C
        out["itlb_tag_stall_pct"] = 100 * g("icache_tag.stalls") / C
        out["branch_resteer_pct"] = 100 * g("int_misc.clear_resteer_cycles") / C
    elif group == "core_ports":
        out["divider_pct"] = 100 * g("arith.div_active") / C
        out["ports0_pct"] = 100 * g("exe_activity.exe_bound_0_ports") / C
        out["ports1_pct"] = 100 * g("exe_activity.1_ports_util") / C
        out["ports2_pct"] = 100 * g("exe_activity.2_ports_util") / C
    elif group == "dram_bw":
        cm4 = g("cpu/offcore_requests_outstanding.data_rd,cmask=4/")
        out["dram_bw_bound_pct"] = 100 * cm4 / C
        out["dram_read_occ_pct"] = 100 * g("offcore_requests_outstanding.cycles_with_data_rd") / C
    elif group == "mem_bound":     # exact SPR TMA-L3 memory ladder (perf's own formulas)
        bol = g("exe_activity.bound_on_loads")
        s1, s2, s3 = (g("memory_activity.stalls_l1d_miss"),
                      g("memory_activity.stalls_l2_miss"), g("memory_activity.stalls_l3_miss"))
        out["tma_l1_bound_pct"] = 100 * max(bol - s1, 0) / C
        out["tma_l2_bound_pct"] = 100 * max(s1 - s2, 0) / C
        out["tma_l3_bound_pct"] = 100 * max(s2 - s3, 0) / C
        out["tma_dram_bound_pct"] = 100 * s3 / C
    elif group == "fe_l3x":        # TMA-L3 frontend children + store bound
        out["tma_dsb_switches_pct"] = 100 * g("dsb2mite_switches.penalty_cycles") / C
        out["ms_switches_PKI"] = 1000 * g("idq.ms_switches") / I
        out["tma_store_bound_pct"] = 100 * g("exe_activity.bound_on_stores") / C
        out["itlb_walk_pct"] = 100 * g("itlb_misses.walk_active") / C
    elif group == "fe_miss":       # BTB / uop-cache / branch-direction split
        out["BTB_MPKI"] = 1000 * g("baclears.any") / I
        out["uopCache_MPKI"] = 1000 * g("frontend_retired.any_dsb_miss") / I
        out["branchDir_MPKI"] = 1000 * g("br_misp_retired.cond") / I
        out["branchInd_MPKI"] = 1000 * g("br_misp_retired.indirect") / I
    elif group == "priv":
        ck, cu = g("cycles:k"), g("cycles:u")
        if ck + cu > 1e5: out["kernel_pct"] = 100 * ck / (ck + cu)
    return out

# ================= pass 1: window rows =================
rows = []
for rd in sorted(glob.glob(f"{BASE}/run_*")):
    gfile = f"{rd}/l3group.txt"
    if not os.path.exists(gfile): continue
    group = open(gfile).read().strip()
    samples = window_tags(f"{rd}/cmdlog.tsv")
    wt = f"{rd}/windows.tsv"
    if not os.path.exists(wt): continue
    for ln in list(open(wt))[1:]:
        p = ln.split()
        if len(p) < 4: continue
        w, grp, a, b = p[0], p[1], float(p[2]), float(p[3])
        if grp != group: continue
        per = counts(f"{rd}/group_{group}_w{w}.txt")
        tg = tag_for(a, b, samples)
        for fence in FENCES:
            mets = derive(group, per[fence])
            for k, v in mets.items():
                rows.append(dict(task=SHORT, group=group, run=os.path.basename(rd),
                                 win=w, t0=round(a, 3), dur=round(b - a, 3), fence=fence,
                                 instructions=int(per[fence].get("instructions", 0)),
                                 tag=(tg if fence == "tool" else "harness"),
                                 metric=k, value=round(v, 4)))

out_csv = f"{OUTD}/all_windows_{SHORT}.csv"
with open(out_csv, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else
                       ["task","group","run","win","t0","dur","fence","instructions","tag","metric","value"])
    w.writeheader(); [w.writerow(r) for r in rows]
print(f"wrote {out_csv}: {len(rows)} window-metric rows")

# ================= pass 2: TMA interval rows (L1+L2 distributions) =================
trows = []
for rd in sorted(glob.glob(f"{BASE}/run_*")):
    f = f"{rd}/tma_cont.csv"
    if not os.path.exists(f): continue
    acc = {}
    for ln in open(f):
        if ln.startswith("#") or not ln.strip(): continue
        p = [x.strip() for x in ln.split(",")]
        if len(p) < 7 or not p[1] or p[1].startswith("<"): continue
        try: t, v = float(p[0]), float(p[1])
        except: continue
        ev, cg = p[3], p[4]
        fence = next((k for k, s in FENCES.items() if s in cg), None)
        if fence: acc.setdefault((t, fence), {})[ev] = acc.setdefault((t, fence), {}).get(ev, 0) + v
    for (t, fence), d in acc.items():
        sl = d.get("slots", 0)
        if sl < 1e6: continue
        pc = lambda e: 100 * d.get(e, 0) / sl
        r, b, fe, be = pc("topdown-retiring"), pc("topdown-bad-spec"), pc("topdown-fe-bound"), pc("topdown-be-bound")
        trows.append(dict(task=SHORT, run=os.path.basename(rd), t=t, fence=fence,
            retiring=round(r,2), bad_spec=round(b,2), fe_bound=round(fe,2), be_bound=round(be,2),
            fetch_lat=round(pc("topdown-fetch-lat"),2), fetch_bw=round(max(fe-pc("topdown-fetch-lat"),0),2),
            mem_bound=round(pc("topdown-mem-bound"),2), core_bound=round(max(be-pc("topdown-mem-bound"),0),2),
            heavy_ops=round(pc("topdown-heavy-ops"),2), br_mispred=round(pc("topdown-br-mispredict"),2)))
tcsv = f"{OUTD}/tma_intervals_{SHORT}.csv"
with open(tcsv, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(trows[0].keys()) if trows else ["task"])
    w.writeheader(); [w.writerow(r) for r in trows]
print(f"wrote {tcsv}: {len(trows)} fence-interval TMA rows")

# ================= plots =================
if DO_PLOT and rows:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    PD = f"{OUTD}/plots"; os.makedirs(PD, exist_ok=True)
    TAGCOL = {"tests(pytest)":"#0b5c44","compile":"#d35400","pkg/build":"#e6a817","git":"#67c6ab",
              "agent-tool":"#c9e9df","shell":"#159f77","python-other":"#4d9e83","other":"#999999",
              "mixed":"#bbbbbb","idle":"#e8e8e8"}
    def sel(metric, fence="tool"):
        return [r for r in rows if r["metric"] == metric and r["fence"] == fence]
    metrics = sorted({r["metric"] for r in rows})
    # (a2) harness-fence boxes: single distribution per metric (no command tags apply)
    for m in metrics:
        rr = sel(m, "harness")
        if len(rr) < 5: continue
        vv = [r["value"] for r in rr]
        fig, ax = plt.subplots(figsize=(8, 1.7))
        bp = ax.boxplot([vv], vert=False, tick_labels=[f"harness ({len(vv)}w)"],
                        showmeans=True, patch_artist=True, whis=(5, 95))
        bp["boxes"][0].set_facecolor("#6b4fa0"); bp["boxes"][0].set_alpha(.7)
        ax.set_xlabel(m); ax.grid(axis="x", alpha=.3)
        ax.set_title(f"{SHORT} — harness fence — per-window {m} (whiskers 5–95%)", fontsize=10.5)
        fig.tight_layout(); fig.savefig(f"{PD}/hbox_{SHORT}_{m}.png", dpi=130); plt.close(fig)
    # (a) box per metric (tool fence) — one figure per metric with tag-split boxes
    for m in metrics:
        rr = sel(m)
        if len(rr) < 5: continue
        tags = [t for t in TAGCOL if any(r["tag"] == t for r in rr)]
        data = [[r["value"] for r in rr if r["tag"] == t] for t in tags]
        data = [d for d in data if d]; tags = [t for t, d0 in zip(tags, [ [r["value"] for r in rr if r["tag"]==t] for t in tags]) if d0]
        fig, ax = plt.subplots(figsize=(8, 0.6 + 0.55 * (len(tags) + 1)))
        allv = [r["value"] for r in rr]
        bp = ax.boxplot([allv] + data, vert=False, tick_labels=[f"ALL ({len(allv)}w)"] +
                        [f"{t} ({len(d)}w)" for t, d in zip(tags, data)],
                        showmeans=True, patch_artist=True, whis=(5, 95))
        for i, box in enumerate(bp["boxes"]):
            box.set_facecolor("#9aa8a2" if i == 0 else TAGCOL.get(tags[i-1], "#ccc")); box.set_alpha(.75)
        ax.set_xlabel(m); ax.set_title(f"{SHORT} — tool fence — per-window {m} (whiskers 5–95%)", fontsize=11)
        ax.grid(axis="x", alpha=.3)
        fig.tight_layout(); fig.savefig(f"{PD}/box_{SHORT}_{m}.png", dpi=130); plt.close(fig)
    # (b2) harness timelines
    for m in metrics:
        rr = sorted(sel(m, "harness"), key=lambda r: r["t0"])
        if len(rr) < 5: continue
        t0 = rr[0]["t0"]
        fig, ax = plt.subplots(figsize=(12, 2.6))
        for r in rr:
            ax.bar((r["t0"] - t0) / 60, r["value"], width=r["dur"]/60*0.9, color="#6b4fa0", align="edge")
        ax.set_xlabel("replay time (min)"); ax.set_ylabel(m)
        ax.set_title(f"{SHORT} — harness fence — per-window {m} over the episode", fontsize=10.5)
        fig.tight_layout(); fig.savefig(f"{PD}/htimeline_{SHORT}_{m}.png", dpi=130); plt.close(fig)
    # (b) timeline for the flagship metric with tag colors
    for m in metrics:
        rr = sorted(sel(m), key=lambda r: r["t0"])
        if len(rr) < 5: continue
        t0 = rr[0]["t0"]
        fig, ax = plt.subplots(figsize=(12, 3.2))
        for r in rr:
            ax.bar((r["t0"] - t0) / 60, r["value"], width=r["dur"]/60*0.9,
                   color=TAGCOL.get(r["tag"], "#999"), align="edge")
        ax.set_xlabel("replay time (min)"); ax.set_ylabel(m)
        ax.set_title(f"{SHORT} — per-window {m} over the episode (color = command tag)", fontsize=11)
        hs = [plt.Rectangle((0,0),1,1,fc=c) for t,c in TAGCOL.items() if any(r['tag']==t for r in rr)]
        ls = [t for t in TAGCOL if any(r['tag']==t for r in rr)]
        ax.legend(hs, ls, fontsize=7.5, ncol=min(5,len(ls)), frameon=False, loc="upper right")
        fig.tight_layout(); fig.savefig(f"{PD}/timeline_{SHORT}_{m}.png", dpi=130); plt.close(fig)
    # (c) per-CALL wall-clock durations from the trajectory (execution_time), by call class
    import json as _j
    tj = glob.glob(f"{BASE.replace('glm_replay_swe_','glm_swe_')}/run_*/traj/**/*.traj", recursive=True)
    tj = [x for x in tj if os.path.getsize(x) > 100]
    if tj:
        INTERNAL = ("str_replace_editor","open ","goto ","scroll_up","scroll_down","create ",
                    "search_file","search_dir","find_file","submit","edit ")
        BUILD = ("runtests.py","pytest","bin/test","-m django test","reproduce","jest","yarn",
                 "npm test","npm run","make","cmake","ctest","ninja","g++","gcc","cc1","node ")
        def ccls(a):
            a=(a or "").strip()
            if not a or a.startswith(INTERNAL): return "internal"
            l=a.lower()
            if any(pt in l for pt in BUILD) or ("python" in l and "test" in l): return "build/tests"
            if a.startswith("git ") or " git " in a[:30]: return "git"
            return "other bash"
        tr=_j.load(open(sorted(tj)[0]))["trajectory"]
        calls=[(ccls(st.get("action")), float(st.get("execution_time") or 0)) for st in tr]
        with open(f"{OUTD}/call_durations_{SHORT}.csv","w",newline="") as fh:
            w=csv.writer(fh); w.writerow(["task","class","execution_time_s"])
            for c,d in calls: w.writerow([SHORT,c,round(d,4)])
        CL=["build/tests","other bash","git","internal"]
        data=[[d for c,d in calls if c==k] for k in CL]
        data2=[d for d in data if d]; labs=[f"{k} ({len(d)})" for k,d in zip(CL,data) if d]
        fig,ax=plt.subplots(figsize=(8,0.6+0.55*(len(data2)+1)))
        allv=[d for c,d in calls]
        bp=ax.boxplot([allv]+data2,vert=False,tick_labels=[f"ALL ({len(allv)})"]+labs,
                      showmeans=True,patch_artist=True,whis=(5,95))
        cols=["#9aa8a2","#0b5c44","#159f77","#67c6ab","#c9e9df"]
        for b,cc in zip(bp["boxes"],cols): b.set_facecolor(cc); b.set_alpha(.75)
        ax.set_xscale("log"); ax.set_xlabel("tool-call wall-clock duration (s, log)")
        ax.set_title(f"{SHORT} — per-call duration by class (from trajectory execution_time)",fontsize=10.5)
        ax.grid(axis="x",alpha=.3)
        fig.tight_layout(); fig.savefig(f"{PD}/calldur_{SHORT}.png",dpi=130); plt.close(fig)
    print(f"plots -> {PD}")
