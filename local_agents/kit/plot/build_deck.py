#!/usr/bin/env python3
"""build_deck.py — assemble the team deck ("Agent CPU profiling — GLM-5.2 SWE-agent") as ONE
self-contained HTML file with every figure inlined as a base64 data URI.

Promoted out of a session scratchpad 2026-07-29: the deck is linked from Report 14 and from the
per-study reports, but the builder existed only in a chat session, so nobody else could rebuild
it after a figure changed. Figures are referenced by PATH (see IMG below), so re-running picks up
regenerated PNGs automatically — that is how the corrected language labels and the re-tagged
babel figures reached the published deck.

    DECK_OUT=/tmp/deck.html python3 build_deck.py      # then publish deck.html as an Artifact

Plotting/render deps (matplotlib is NOT needed here, only base64+pathlib) — but the figures it
inlines must already exist; regenerate them first with the plotters in this directory.
"""
import base64, os, pathlib

PLOTS = pathlib.Path("/home/thu/InferSuite/local_agents/superseded_40min/plots")
OUT = pathlib.Path(os.environ.get("DECK_OUT", "/tmp/deck.html"))

def uri(name):
    pth = pathlib.Path(name) if str(name).startswith("/") else (PLOTS / name)
    b = pth.read_bytes()
    return "data:image/png;base64," + base64.b64encode(b).decode()

IMG = {k: uri(v) for k, v in {
    "split": "/home/thu/InferSuite/local_agents/cross_campaign/plots_5t/glm_time_split.png",          # mentor 2026-07-30: no django, + babel/fmt
    "cpu": "/home/thu/InferSuite/local_agents/cross_campaign/plots_5t/glm_cpu_work.png",
    "timeline": "glm_timeline.png",
    "calls": "/home/thu/InferSuite/local_agents/cross_campaign/plots_calls6t/glm_tool_calls.png",     # django@0.6 out, looped @0 stays
    "cmp_wall": "compare/cmp_wall_split.png",
    "cmp_cpu": "compare/cmp_cpu_work.png",
    "cmp_tl_moh": "compare/cmp_timeline_moh.png",
    "cmp_tl_new": "compare/cmp_timeline_new.png",
    "cmp_abs": "compare/cmp_absolute.png",
    "cmp_calls": "compare/cmp_callstruct.png",
    "cmp_heavy": "compare/cmp_whats_heavy.png",
    "tma_moh": "compare/moh_featured/glm_tma_l1.png",
    "tma_new": "/home/thu/InferSuite/local_agents/cross_campaign/plots_5t/glm_tma_l1.png",
    "sig_moh": "compare/moh_featured/glm_signature.png",
    "sig_new": "glm_signature.png",
    "tma_all": "compare/cmp_tma_l1_allruns.png",
    "l2_moh": "compare/moh_featured/glm_tma_l2.png",
    "l2_new": "glm_tma_l2.png",
    "w_ipc": "/home/thu/InferSuite/local_agents/superseded_40min/data/l3_study/plots/box_scikit-learn_IPC.png",
    "w_l1i": "/home/thu/InferSuite/local_agents/superseded_40min/data/l3_study/plots/box_scikit-learn_codeRead_MPKI_L1I.png",
    "w_tl": "/home/thu/InferSuite/local_agents/superseded_40min/data/l3_study/plots/timeline_scikit-learn_codeRead_MPKI_L1I.png",
    # grid16_*: the mentor's 4x4 rearrangement (2026-07-31) with the cache miss-rate row —
    # same frozen task population per slide; the original 12-panel files remain on disk.
    "w_x": "/home/thu/InferSuite/local_agents/superseded_40min/data/l3_study/plots/cross_task_grid16_tool_py3.png",
    "w_xh": "/home/thu/InferSuite/local_agents/superseded_40min/data/l3_study/plots/cross_task_grid16_harness_py3.png",
    "w_dur": "/home/thu/InferSuite/local_agents/superseded_40min/data/l3_study/plots/cross_task_calldur_py3.png",
    "ml_grid": "/home/thu/InferSuite/local_agents/superseded_40min/data/l3_study/plots/cross_task_grid16_tool_5t.png",
    "ml_gridh": "/home/thu/InferSuite/local_agents/superseded_40min/data/l3_study/plots/cross_task_grid16_harness_5t.png",
    # _12t = the slide's frozen 12-workload population; an unsuffixed grid16 run would now
    # absorb the 13th task (phpoffice-bT) under a caption that says "twelve".
    "ml_grid12": "/home/thu/InferSuite/local_agents/superseded_40min/data/l3_study/plots/cross_task_grid16_tool_12t.png",
    # 2026-08-10: the matched-configuration re-capture and the SPEC baseline comparison.
    "grid_iso8": "/home/thu/InferSuite/local_agents/SWE_iso8/plots/plots/cross_task_grid16_tool_iso8.png",
    "tma_fences": "/home/thu/InferSuite/local_agents/SWE_iso8/plots/agentic_tma_l1_fences.png",
    "cfg_effect": "/home/thu/InferSuite/local_agents/SWE_iso8/plots/agentic_config_effect.png",
    "spec_cmp": "/home/thu/InferSuite/spec26/plots/spec_vs_agentic_metrics.png",
    "spec_tma": "/home/thu/InferSuite/spec26/plots/spec_vs_agentic_tma.png",
    "go_uop_tl": "/home/thu/InferSuite/local_agents/ML_multiling/data/l3_study/plots/timeline_prometheus_uopCache_MPKI.png",
    "ml_tl_babel": "/home/thu/InferSuite/local_agents/SWE_clean/data/l3_study/plots/timeline_babel_codeRead_MPKI_L1I.png",
    "ml_tl_fmt": "/home/thu/InferSuite/local_agents/SWE_clean/data/l3_study/plots/timeline_fmtlib_codeRead_MPKI_L1I.png",
}.items()}

CSS = """
:root{
  --bg:#f5f8f6; --panel:#ffffff; --ink:#12201b; --muted:#5c6b64;
  --line:#dde6e1; --tool:#159f77; --harness:#6b4fa0; --proxy:#cf6a1f;
  --wait:#9aa8a2; --accent:var(--tool);
  --shadow:0 1px 2px rgba(18,32,27,.06),0 8px 30px rgba(18,32,27,.08);
  --sans:"Segoe UI",system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SF Mono","Cascadia Mono","Roboto Mono",Menlo,monospace;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#0e1512; --panel:#16201c; --ink:#e8efeb; --muted:#93a49c;
    --line:#26332d; --tool:#2fc294; --harness:#a68be0; --proxy:#e79a4f;
    --wait:#7d8c85;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 34px rgba(0,0,0,.45);
  }
}
:root[data-theme="light"]{
  --bg:#f5f8f6; --panel:#ffffff; --ink:#12201b; --muted:#5c6b64;
  --line:#dde6e1; --tool:#159f77; --harness:#6b4fa0; --proxy:#cf6a1f;
  --wait:#9aa8a2; --shadow:0 1px 2px rgba(18,32,27,.06),0 8px 30px rgba(18,32,27,.08);
}
:root[data-theme="dark"]{
  --bg:#0e1512; --panel:#16201c; --ink:#e8efeb; --muted:#93a49c;
  --line:#26332d; --tool:#2fc294; --harness:#a68be0; --proxy:#e79a4f;
  --wait:#7d8c85; --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 34px rgba(0,0,0,.45);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
body{
  margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);
  -webkit-font-smoothing:antialiased;
}
.deck{scroll-snap-type:y mandatory;height:100dvh;overflow-y:auto}
.slide{
  min-height:100dvh;scroll-snap-align:start;display:flex;flex-direction:column;
  justify-content:center;padding:clamp(24px,5vw,80px);position:relative;
}
.wrap{width:100%;max-width:1120px;margin:0 auto}
.eyebrow{
  font-family:var(--mono);font-size:12px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--accent);margin:0 0 14px;display:flex;gap:10px;align-items:center;
}
.eyebrow::before{content:"";width:26px;height:2px;background:var(--accent);display:inline-block}
h1{
  font-size:clamp(34px,6vw,68px);line-height:1.02;letter-spacing:-.02em;margin:0;
  text-wrap:balance;font-weight:700;
}
h2{
  font-size:clamp(26px,3.6vw,40px);line-height:1.08;letter-spacing:-.015em;margin:0 0 6px;
  text-wrap:balance;font-weight:650;
}
.lead{font-size:clamp(15px,1.5vw,18px);color:var(--muted);line-height:1.6;max-width:60ch;margin:18px 0 0}
.figcard{
  background:var(--panel);border:1px solid var(--line);border-radius:14px;
  box-shadow:var(--shadow);padding:clamp(12px,2vw,22px);margin-top:22px;
}
.figcard img{display:block;width:100%;height:auto;border-radius:6px}
.take{
  display:flex;flex-wrap:wrap;gap:12px;margin-top:20px;
}
.chip{
  font-size:14px;line-height:1.45;background:var(--panel);border:1px solid var(--line);
  border-left:3px solid var(--accent);border-radius:8px;padding:10px 14px;
  flex:1 1 240px;color:var(--ink);
}
.chip b{font-variant-numeric:tabular-nums}
.chip.tool{border-left-color:var(--tool)}
.chip.harness{border-left-color:var(--harness)}
.chip.proxy{border-left-color:var(--proxy)}
.chip.wait{border-left-color:var(--wait)}
.grid2{display:grid;grid-template-columns:1fr;gap:22px}
@media (min-width:760px){.slide.split .grid2{grid-template-columns:1.15fr .85fr;align-items:center}}
.meta{display:flex;flex-wrap:wrap;gap:10px 28px;margin-top:34px;font-family:var(--mono);font-size:13px;color:var(--muted)}
.meta span b{color:var(--ink);font-weight:600}
.legend{display:flex;flex-wrap:wrap;gap:16px;margin-top:22px;font-size:13px;color:var(--muted)}
.legend i{width:12px;height:12px;border-radius:3px;display:inline-block;margin-right:7px;vertical-align:-1px}
.tlist{margin:20px 0 0;padding:0;list-style:none;display:flex;flex-direction:column;gap:14px;max-width:70ch}
.tlist li{display:flex;gap:14px;font-size:clamp(15px,1.5vw,18px);line-height:1.5}
.tlist li::before{content:"";flex:0 0 8px;height:8px;margin-top:9px;border-radius:50%;background:var(--accent)}
.note{margin-top:26px;font-size:13.5px;color:var(--muted);border-top:1px solid var(--line);padding-top:16px;max-width:70ch;line-height:1.6}
.progress{position:fixed;top:0;left:0;height:3px;background:var(--accent);width:0;z-index:20;transition:width .2s ease}
.counter{position:fixed;bottom:18px;right:22px;font-family:var(--mono);font-size:12px;color:var(--muted);z-index:20;letter-spacing:.05em}
.hint{position:fixed;bottom:18px;left:22px;font-family:var(--mono);font-size:12px;color:var(--muted);z-index:20;letter-spacing:.05em}
@media (max-width:640px){.hint{display:none}}
"""

JS = """
const deck=document.querySelector('.deck');
const slides=[...document.querySelectorAll('.slide')];
const prog=document.querySelector('.progress');
const counter=document.querySelector('.counter');
function update(){
  const i=Math.round(deck.scrollTop/window.innerHeight);
  counter.textContent=String(Math.min(i+1,slides.length)).padStart(2,'0')+' / '+String(slides.length).padStart(2,'0');
  prog.style.width=((deck.scrollTop/(deck.scrollHeight-deck.clientHeight))*100||0)+'%';
}
deck.addEventListener('scroll',update,{passive:true});
function go(d){
  const i=Math.round(deck.scrollTop/window.innerHeight);
  const n=Math.max(0,Math.min(slides.length-1,i+d));
  slides[n].scrollIntoView({behavior:'smooth',block:'start'});
}
addEventListener('keydown',e=>{
  if(['ArrowDown','ArrowRight',' ','PageDown'].includes(e.key)){e.preventDefault();go(1);}
  if(['ArrowUp','ArrowLeft','PageUp'].includes(e.key)){e.preventDefault();go(-1);}
  if(e.key==='Home'){e.preventDefault();slides[0].scrollIntoView({behavior:'smooth'});}
  if(e.key==='End'){e.preventDefault();slides[slides.length-1].scrollIntoView({behavior:'smooth'});}
});
update();
"""

BODY = """
<div class="progress"></div>
<div class="counter">01 / 33</div>
<div class="hint">↓ / space · arrow keys to navigate</div>
<div class="deck">

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">CPU profiling · agentic workloads</p>
      <h1>Where does the time go<br>during an agent episode?</h1>
      <p class="lead">GLM-5.2 driving SWE-agent on real SWE-bench repairs, captured on an isolated
      20-core partition. Harness CPU and tool CPU fenced into separate cgroups, so we can see
      exactly what the machine does while the agent works — and what it waits on.</p>
      <div class="meta">
        <span>tasks&nbsp; <b>scikit-learn · astropy · sympy · django</b> + <b>9 languages / 12 tool workloads</b> (slide 26)</span>
        <span>coverage&nbsp; <b>3 clean + django (looped @0 / submit-blocked @0.6)</b></span>
        <span>model&nbsp; <b>GLM-5.2</b></span>
        <span>status&nbsp; <b>interim</b></span>
      </div>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 1 · wall-clock</p>
      <h2>The wall clock is mostly waiting on the model</h2>
      <p class="lead">Across every task — and every language — elapsed time is dominated by the
      model round-trip: the CPU sits idle waiting for tokens. Tool execution and the agent harness
      together are the minority of wall time, from an 8-minute scikit-learn episode to a 37-minute
      astropy one. The pattern holds beyond Python: <b>babel (JavaScript)</b> waits on the model
      86 % of a 7-min episode, and <b>fmt (C++)</b> — the compile-heaviest task in the study —
      still waits 82 % of 16 min, with tools at 13 %, the highest tool share of wall measured.</p>
      <div class="figcard"><img alt="Wall-clock time split donuts: scikit-learn, astropy, sympy, babel (JavaScript), fmt (C++)" src="__SPLIT__"></div>
      <div class="take">
        <div class="chip wait">model wait&nbsp; <b>74</b> · <b>89</b> · <b>78</b> · <b>86</b> · <b>82%</b></div>
        <div class="chip tool">tools&nbsp; <b>23</b> · <b>9</b> · <b>11</b> · <b>8</b> · <b>13%</b></div>
        <div class="chip harness">harness&nbsp; <b>3</b> · <b>2</b> · <b>11</b> · <b>6</b> · <b>4.5%</b></div>
      </div>
      <p class="note">Python tasks: reproduced superseded_40min campaign (featured runs). babel +
      fmt: certified SWE_clean campaign (featured runs). One figure by request; per-task
      provenance stated here, figures rendered by the same plotter from banked data and audited
      (ALL MATCH). The django columns live in the original figure
      (superseded_40min/plots/glm_time_split.png, untouched); absolute wall minutes are episode
      draws — the split shares are the reproducible layer.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 2 · core-seconds</p>
      <h2>CPU work is tool-heavy — but not always</h2>
      <p class="lead">Flip to CPU work and model wait vanishes (≈ 0 core-seconds — pure waiting). For
      scikit-learn and astropy, tools dominate: scikit-learn's test suite alone burns 1,449 core-seconds.
      sympy inverts it (53% harness). The pattern crosses languages: fmt's compile-heavy episode is
      91% tools (296 core-s), babel's short episode splits 72/23 between tools and harness — and
      every language's litellm share stays negligible.</p>
      <div class="figcard"><img alt="CPU work in core-seconds: scikit-learn, astropy, sympy, babel, fmt" src="__CPU__"></div>
      <div class="take">
        <div class="chip tool">scikit-learn · <b>1,449</b> core-s, 100% tools</div>
        <div class="chip tool">astropy · <b>265</b> core-s, 88% tools</div>
        <div class="chip harness">sympy · <b>234</b> core-s, 53% harness</div>
        <div class="chip tool">babel · <b>53</b> core-s, 72% tools</div>
        <div class="chip tool">fmt · <b>296</b> core-s, 91% tools</div>
      </div>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 3 · orchestration</p>
      <h2>Bursty, a trickle, or a stuck loop</h2>
      <p class="lead">scikit-learn and astropy spike their tool fence to the full partition (20 and 17
      cores) during test phases. sympy never exceeds one core — a near-continuous low hum. django's
      looped run is unmistakable: 41 minutes of solid harness activity (up to 6 cores) with tools
      flatlined — an agent repeating itself until the time cap.</p>
      <div class="figcard"><img alt="Orchestration timeline across four tasks" src="__TIMELINE__"></div>
      <div class="legend">
        <span><i style="background:var(--tool)"></i>Tool-fence CPU · peaks 20 / 17 / 1 / 1 cores</span>
        <span><i style="background:var(--harness)"></i>Harness-fence CPU · ≤ 1 core (django's loop: continuous, to 6)</span>
      </div>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 4 · call structure</p>
      <h2>How the tool calls break down</h2>
      <p class="lead">Call counts and weights vary widely — across languages too. scikit-learn's fewer
      calls carry the heaviest compute; sympy issues many; fmt's C++ episode packs 58 heavy calls of
      114. django's loop stays visible — 383 calls but only 4 heavy and 2 agent-internal: a flood of
      shallow, repeated commands doing almost no real work.</p>
      <div class="figcard"><img alt="Tool-call structure: scikit-learn, astropy, sympy, django looped@0, babel, fmt" src="__CALLS__"></div>
      <div class="take">
        <div class="chip tool">scikit-learn · <b>67</b> calls, 26 heavy, <b>22.8%</b> tool-active</div>
        <div class="chip harness">django (looped) · <b>383</b> calls, 4 heavy, <b>5.1%</b> tool-active</div>
        <div class="chip tool">babel · <b>94</b> calls, 23 heavy, <b>8.0%</b> tool-active</div>
        <div class="chip tool">fmt · <b>114</b> calls, 58 heavy, <b>13.5%</b> tool-active</div>
      </div>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Takeaways · what's next</p>
      <h2>Four tasks in: the profile is task-dependent</h2>
      <ul class="tlist">
        <li>Elapsed time is dominated by model wait everywhere; CPU work is not. The two views tell opposite stories — report both.</li>
        <li>Where CPU work goes depends on the task: scikit-learn is tool-compute-bound (test suite saturates cores), sympy and django are harness-bound (never saturate a single core on tools).</li>
        <li>A stuck agent has a clear CPU signature: django's loop is 89% harness, near-zero heavy tool work, and 40 minutes of continuous harness churn — cost with nothing to show for it.</li>
      </ul>
      <p class="note"><b>On django.</b> Its panels are a real measurement, but of a <i>looped</i> episode —
      the agent degenerated into repeated commands under greedy decoding (temp 0.0) and ran to the time cap.
      Every django figure is tagged "(looped)". It shows what a failure costs, not django's steady-state
      profile; a temp-0.6 re-run is queued for a clean comparison.
      <br><br><b>Other caveats.</b> Clean tasks use one representative run each; astropy has a single clean
      run, so no dispersion band yet. Every plotted number is independently re-derived from the raw capture
      (audit: all match).</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Reproducibility · every run, both campaigns</p>
      <h2>Does the campaign reproduce? Compare all 24 runs</h2>
      <p class="lead">The same four tasks were captured twice — the original certified campaign (Mohamad)
      and this re-run — with 3 episodes each. Absolute wall-clock and core-seconds vary 2–3× run-to-run
      (greedy decoding is not deterministic across the API), so the right comparison is the <b>shares</b>.
      The next three slides show every run side by side.</p>
      <div class="take">
        <div class="chip wait">24 episodes · 12 per campaign · ⟳ marks degenerate loop runs</div>
        <div class="chip tool">clean-run shares match within and between campaigns</div>
        <div class="chip harness">loops have their own signature: harness-dominated, 40-min cap</div>
      </div>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Reproducibility 1 · wall-clock shares</p>
      <h2>Model wait dominates every single run</h2>
      <p class="lead">All 24 episodes — grey (model wait) is 65–90% of wall in both campaigns, clean or
      looped. This is the study's most robust result: no episode, in either campaign, spent the majority
      of its wall time computing.</p>
      <div class="figcard"><img alt="Wall-clock share per run, both campaigns" src="__CMPWALL__"></div>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Reproducibility 2 · CPU-work shares</p>
      <h2>Clean runs agree; loops have their own signature</h2>
      <p class="lead">Per-task shares reproduce across campaigns on clean runs: scikit-learn ≈ all-tool in
      all four clean episodes; astropy tool-heavy in all three; sympy harness-leaning in all four. Every
      looped run (⟳) shifts toward harness — most extreme in django, where all loops land at ≈ 90%.
      Absolute totals (grey numbers) swing 2–3× — that is episode luck, not campaign drift.</p>
      <div class="figcard"><img alt="CPU work share per run, both campaigns" src="__CMPCPU__"></div>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Reproducibility 3 · timelines</p>
      <h2>Same task, same shape — in both campaigns</h2>
      <p class="lead">Small multiples of all 24 episodes. scikit-learn's three 20-core test bursts appear
      in both campaigns' clean runs; astropy's spiky pattern and sympy's sub-core trickle likewise. Looped
      runs (red) are instantly recognizable: a solid harness wall running to the 40-minute cap.</p>
      <div class="grid2">
        <div class="figcard"><img alt="Timelines, Mohamad campaign, 12 runs" src="__CMPTLMOH__"></div>
        <div class="figcard"><img alt="Timelines, new campaign, 12 runs" src="__CMPTLNEW__"></div>
      </div>
      <p class="note"><b>Reading guide.</b> Rows = tasks, columns = runs 1–3; green = tool cores, purple =
      harness cores; red titles = loop episodes. Left grid: Mohamad's certified campaign. Right grid: this
      re-run. Loop rate differed by luck (5/12 vs 7/12) — django looped in 5 of 6 attempts across both
      campaigns, making it the clearest candidate for a temp-0.6 re-run.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Reproducibility 4 · absolute values</p>
      <h2>The same data un-normalized: what shares hide</h2>
      <p class="lead">Absolute wall-clock (top) and core-seconds (bottom) for all 24 runs. Here the 2–3×
      episode-to-episode spread is plain: Mohamad's scikit-learn clean runs burn 1,771 and 2,568 core-s,
      ours 1,449 and 1,389. Loop runs pile up at the 40-minute cap in both campaigns. Shares reproduce;
      absolutes are a distribution, and any single episode is one draw from it.</p>
      <div class="figcard"><img alt="Absolute wall-clock and CPU work per run, both campaigns" src="__CMPABS__"></div>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Reproducibility 5 · tool-call structure</p>
      <h2>Turns, bursts and burst length line up too</h2>
      <p class="lead">Per episode: agent turns (grey), detected tool bursts (green), heavy bursts (dark).
      Clean runs of the same task have similar structure in both campaigns — scikit-learn ≈ 60–140 turns
      with a fraction heavy; loop runs balloon to 350–460 turns of shallow calls. Median tool-burst
      duration stays in the same 0.3–0.9 s band everywhere: the per-call cost is stable even when the
      episode count is not.</p>
      <div class="figcard"><img alt="Tool-call and burst structure per run, both campaigns" src="__CMPCALLS__"></div>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Inside the fences · what is actually heavy</p>
      <h2>Tool CPU is the test suite; harness CPU is the interpreter</h2>
      <p class="lead">Attributing the CPU inside each fence (featured runs). <b>Tool fence:</b> build/test
      commands are ≈70–99% of tool CPU on every clean task in both campaigns — and scikit-learn's test-suite
      CPU is ~87% OpenBLAS (matrix math), not Python. The two django loops differ in content: Mohamad's
      repeated git (99%), ours repeated shallow bash. <b>Harness fence:</b> ~75–87% Python interpreter,
      then tokenization (tiktoken) and JSON/pydantic parsing — identical structure in both campaigns.</p>
      <div class="figcard"><img alt="What is heavy inside tool and harness fences, both campaigns" src="__CMPHEAVY__"></div>
      <div class="take">
        <div class="chip tool">tools = build/tests ≈ 70–99% (scikit: 87% OpenBLAS)</div>
        <div class="chip harness">harness = interpreter ≈ 75–87% + tiktoken + JSON</div>
        <div class="chip wait">structure identical across both campaigns</div>
      </div>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Microarchitecture 1 · TMA Level 1, side by side</p>
      <h2>Where the pipeline slots go — certified vs re-run</h2>
      <p class="lead">Top-down analysis (TMA) splits every CPU pipeline slot into four buckets:
      useful work (Retiring), waiting for instructions (Frontend-bound), thrown away on wrong
      guesses (Bad speculation), waiting for data/execution (Backend-bound). Mohamad's certified
      Python episodes (left) vs this study's featured set across three languages (right): the
      Python buckets match within 1–5 points on every clean fence — e.g. scikit-learn tool
      43/24/1/33 vs 42/23/1/34 — and babel/fmt land in the same frontend-bound family as the
      interpreters (FE 40/34, bad-spec 16/18).</p>
      <div class="grid2">
        <div class="figcard"><img alt="TMA Level 1, Mohamad certified campaign" src="__TMAMOH__"></div>
        <div class="figcard"><img alt="TMA Level 1, new campaign" src="__TMANEW__"></div>
      </div>
      <div class="take">
        <div class="chip tool">scikit tool = backend-bound — L2 says core-bound (28%) not memory (6%): execution ports/FMA, not DRAM</div>
        <div class="chip tool">astropy &amp; sympy tools = frontend-bound (31–35%) + bad-spec (11–19%): interpreter churn</div>
        <div class="chip harness">harness = same shape on every task: ≈40% retiring, ≈20% frontend, ≈25% backend</div>
      </div>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Microarchitecture 2 · per-side signatures</p>
      <h2>Signatures on absolute scales — anchored to hardware ceilings</h2>
      <p class="lead">Eight hardware metrics per fence, on absolute ranges (IPC 0–6, DSB 0–100%,
      cache miss rates…), Mohamad (top) vs re-run (bottom). Cell-by-cell the heatmaps agree:
      scikit tool IPC 0.69 vs 0.64 with DSB 82 vs 84%; harness IPC 2.4–2.9 in both; and the
      standout tool-side instruction-cache pain (L1I MPKI 19–31) appears in both campaigns.</p>
      <div class="grid2">
        <div class="figcard"><img alt="Per-side hardware signatures, Mohamad" src="__SIGMOH__"></div>
        <div class="figcard"><img alt="Per-side hardware signatures, new campaign" src="__SIGNEW__"></div>
      </div>
      <p class="note"><b>Reading guide.</b> Color = position on the absolute scale under each column
      (0 = low reference, 1 = hardware ceiling / high reference). High IPC does not mean useful work
      here — the interpreter retires many instructions per unit of progress; read IPC together with
      the TMA buckets.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Microarchitecture 3 · every run</p>
      <h2>TMA is the most reproducible metric of all</h2>
      <p class="lead">All 24 episodes. Clean runs of the same task agree within a few points across
      campaigns — and the harness fence is nearly the same bar 24 times, regardless of task or even
      looping. Microarchitecture mix is a property of the <i>code being executed</i> (pytest, OpenBLAS,
      CPython), not of the episode's length or path — which is why it survives the 2–3× swings that
      wreck absolute comparisons.</p>
      <div class="figcard"><img alt="TMA Level 1 for every run in both campaigns" src="__TMAALL__"></div>
      <div class="take">
        <div class="chip tool">clean-run task buckets: within 1–5 points across campaigns</div>
        <div class="chip harness">harness: ≈40/20/8/28 on all 24 bars — task-independent</div>
        <div class="chip wait">successful runs share the distribution — the acceptance criterion holds</div>
      </div>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Experiment · django at temperature 0.6</p>
      <h2>Higher temperature fixed the loops — and exposed a harness bug</h2>
      <p class="lead">Two fresh django episodes at temperature 0.6 (loop guard armed), as asked.
      Neither solved the task — but for a reason nobody could see before: the submit tool itself
      crashes inside this task's container.</p>
      <ul class="tlist">
        <li><b>Run 1:</b> ~126 turns of genuinely varied work (64 heavy tool bursts vs 4 in the
        temp-0 loops), then the agent tried to <b>submit 29 times</b> — every attempt bounced with
        a Python SyntaxError from the harness's submit tool, which uses modern syntax the ancient
        django-10097 container cannot parse. The loop guard ended it mid-ritual.</li>
        <li><b>Run 2:</b> a classic work-loop (repeated git inspection) caught by the guard at
        ~18 min — django remains genuinely loop-prone even at 0.6.</li>
        <li><b>Conclusion:</b> django-10097 is <b>unsolvable in this harness configuration at any
        temperature</b> — the failure is two-layered: greedy-decode loops masked an
        environment/tooling incompatibility that only surfaced once the loops were fixed.</li>
      </ul>
      <div class="take">
        <div class="chip tool">temp 0.6 → real work: 64 heavy bursts, 78 core-s</div>
        <div class="chip harness">submit tool: SyntaxError in old container → 0 patches possible</div>
        <div class="chip wait">temp-0 loops hid this bug in both campaigns</div>
      </div>
      <p class="note"><b>Method.</b> Same kit, same isolation (ISO-PROOF 0.7% quiet), loop guard
      N=12, data in a separate <i>glm-t06</i> config so the temp-0 evidence is untouched. Figures
      on slides 2–5 and 16 now include the django@0.6 column, audit-verified. "Solved" here means
      a submitted patch; formal SWE-bench resolution would additionally need its evaluation
      harness.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Microarchitecture 4 · TMA Level 2 drill</p>
      <h2>Splitting the buckets: latency vs bandwidth, core vs memory</h2>
      <p class="lead">Each Level-1 bucket split into its measured sub-cause, from the whole-episode
      PERF_METRICS census banked per run (tool fences, featured episodes; Mohamad left, re-run right).
      scikit-learn's backend is <b>core-bound 28% vs memory 6%</b> — execution ports and FMA pressure,
      <i>not</i> DRAM (LLC MPKI 0.01, AMAT at floor agree). astropy and sympy split their frontend
      almost evenly between fetch-<i>latency</i> and fetch-<i>bandwidth</i> (~17/17 and ~16/15) — the
      big-code-footprint signature — plus 14–18% branch-mispredict.</p>
      <div class="grid2">
        <div class="figcard"><img alt="TMA Level 2, Mohamad certified" src="__L2MOH__"></div>
        <div class="figcard"><img alt="TMA Level 2, new campaign" src="__L2NEW__"></div>
      </div>
      <div class="take">
        <div class="chip tool">scikit BE → core 28.3 / mem 6.1 · Ret-heavy 22% (vector/FMA)</div>
        <div class="chip tool">astropy FE → lat 17.4 / bw 17.1 · sympy FE → 16.4 / 15.3</div>
        <div class="chip harness">which commands? astropy L1I MPKI ≈ <b>28 during build/test windows</b> vs ≈ 8 in short-command windows (window↔burst join on banked logs)</div>
      </div>
      <p class="note"><b>Provenance.</b> Level-2 shares come from each episode's continuous top-down
      census (fetch-latency and memory-bound counted directly; bandwidth/core are the L1 remainders) —
      numbers in values_dump, audit-covered. The per-command attribution joins each fe_lat counter
      window (exact, zero-mux) to the tool fence's activity bursts: long bursts ≥3 s are the
      build/test executions. Function-level attribution would need a sampled-event replay
      (free, no API) — the kit's GORDER_OVERRIDE mechanism exists for exactly that.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Per-window study 1 · distributions, not averages</p>
      <h2>Every metric, per 2-second window, tagged by command</h2>
      <p class="lead">New capture method: deterministic replays (no model, no API cost) with ONE counter
      group dedicated per pass (10 passes, zero multiplexing), 2-s windows, plus a host-side 2 Hz
      process poll of the tool cgroup that tags each window with the command running. scikit-learn:
      ~57 windows × 10 groups → per-window box plots for every metric. The episode averages hid a
      3× structure: pytest windows run at IPC 0.62 (OpenBLAS, backend-bound), while pkg/build hits 1.9
      and shell 1.35; L1I pressure is the mirror image — pytest ≈0.9 MPKI, command startups 16–30.</p>
      <div class="grid2">
        <div class="figcard"><img alt="Per-window IPC box plot by command tag" src="__WIPC__"></div>
        <div class="figcard"><img alt="Per-window L1I MPKI box plot by command tag" src="__WL1I__"></div>
      </div>
      <div class="figcard"><img alt="Per-window L1I MPKI timeline colored by command" src="__WTL__"></div>
      <p class="note"><b>Reading guide.</b> "(5w)" after a label = that tag owns 5 of the episode's
      2-second windows. Box = interquartile range, orange line = median, green ▲ = mean,
      whiskers = 5th–95th percentile, ○ = windows outside them. <b>"Replay time"</b> is the
      x-axis of a <i>deterministic replay</i>: the recorded trajectory is re-executed with no model
      in the loop, so the 8-minute live episode (74 % of which was waiting for the API) compresses
      to ≈2 minutes of pure execution — same commands, same order, no wait. <b>How windows get
      their tag:</b> during profiling, a 2 Hz poller on the housekeeping cores lists the processes
      inside the tool cgroup (timestamp, pid, argv → cmdlog.tsv); at analysis time each window is
      tagged by the most specific foreground command seen in it (tests &gt; compile &gt; pkg/build &gt;
      git &gt; python &gt; shell &gt; agent-tool), so the persistent plumbing (SWE-ReX server, session
      shell) cannot dilute the tag. The window boundaries themselves are the counter windows
      (epoch-bracketed in windows.tsv); the fence boundary is the sandbox cgroup — exact kernel
      accounting, nothing name-based.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Per-window study 2 · TMA Level 3 measured</p>
      <h2>The memory ladder verdict: L1-bound, zero DRAM stall</h2>
      <p class="lead">Two counter groups were added to the kit (mem_bound, fe_l3x — perf's own SPR
      formulas, verified 100%-enabled) so TMA L1→L3 is now fully measured. scikit-learn's tool fence,
      per-window medians during pytest: <b>L1-bound 14.4%</b> of cycles, L2-bound 0.02%, L3-bound 0.3%,
      <b>DRAM-bound 0.0%</b>, store-bound 0.1%. Meanwhile DRAM read occupancy is 62% of cycles at
      MLP≈3.3 — heavy streaming that is fully prefetched/overlapped and never stalls the pipeline.
      OpenBLAS is limited by execution ports and L1 data supply, definitively not by main memory.</p>
      <div class="take">
        <div class="chip tool">TMA L3 memory: L1 14.4 / L2 0.02 / L3 0.3 / DRAM 0.0 / store 0.1 (%cyc)</div>
        <div class="chip tool">FE L3 children: DSB-switches 1.1%, iTLB-walk ~0% — frontend fine</div>
        <div class="chip wait">all values first: all_windows_*.csv (2,116 rows × every metric) + tma_intervals_*.csv — pick plots afterwards</div>
      </div>
      <p class="note"><b>Method.</b> Replay + GORDER_OVERRIDE is the kit's own dedicated-group probe;
      each pass re-runs the identical recorded trajectory, so passes are comparable. New events:
      exe_activity.bound_on_loads, memory_activity.stalls_l{1d,2,3}_miss (memory ladder);
      dsb2mite_switches.penalty_cycles, idq.ms_switches, exe_activity.bound_on_stores,
      itlb_misses.walk_active (FE children + store). LCP is the one un-captured L3 child.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Method audit · tool-call boundaries</p>
      <h2>How a "tool call" gets its boundaries — verified in code</h2>
      <ul class="tlist">
        <li><b>Spatial (what counts as tool CPU): a kernel cgroup wall.</b> The harness runs in a
        systemd scope created at launch; the sandbox container's cgroup is resolved from its init PID,
        with docker's cgroup-parent forced into the measured slice. Nothing is name-based — SWE-ReX,
        the session shell, and every spawned child are structurally inside the tool fence. Exact by
        construction (kernel accounting).</li>
        <li><b>Temporal (when a call starts/ends): an ordinal anchor join.</b> Bursts come from the
        10 Hz cpu.stat series (floors 0.005/0.02 cores, gaps &lt;0.4 s merged). Calls &gt;5 s are paired
        1:1 with bursts &gt;5 s (anchors — only test suites/builds run that long); between anchors,
        short bursts' CPU is split over short calls weighted by each call's harness-logged
        execution_time. "Coverage 100%" = every burst core-second credited to a call class.</li>
        <li><b>Guards:</b> the anchor-count diagnostic is printed per task (mismatch = visible before
        trust); no long calls → method degrades to duration-weighted and says so on the figure;
        sub-floor trickle is excluded symmetrically. The heuristic layer touches only time
        <i>attribution</i> — fence totals are always exact.</li>
      </ul>
      <p class="note"><b>Paper cross-check (arXiv 2605.26297).</b> Its Fig. 10 categories are raw
      Claude-Code tool names (Bash/Read/Edit/…); the bash-command taxonomy is its Fig. 11 (grep,
      python3, curl, git, …, Other) — and the paper reports no microarchitecture metrics at all.
      Per-command MPKI/TMA distributions, as shown on the previous slides, are new territory.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Per-window study 3 · all three tasks</p>
      <h2>Three tasks, three distribution shapes</h2>
      <p class="lead">The full metric grid, per 2-s window, tool fence (11 dedicated-group replays per
      task), arranged 4×4 by family: <b>branches</b> (IPC · branch / branch-direction / BTB MPKI),
      <b>instruction supply</b> (DSB coverage · µop-cache · L1I · L1D MPKI), then the <b>cache
      ladder</b> twice — per-instruction MPKI and per-access <b>miss rates</b> (L2 · LLC MPKI ·
      L1I-stall proxy · L1D / L2 / LLC miss rate) — closing with AMAT and MLP. The two cache rows
      answer different questions: MPKI says how often an instruction pays; the miss rate says how
      often a lookup at that level fails. The box shapes are the finding: scikit-learn is <b>bimodal</b>
      (OpenBLAS pytest at IPC 0.62 vs everything else ≥1.1); astropy is <b>wide</b> (its L1I pain is
      specifically pytest: 23.3 vs 7.9 MPKI); sympy is <b>tight</b> — the interpreter churn IS the
      workload. New-counter readings: µop-cache MPKI 63/54 for astropy/sympy vs ~20 for scikit;
      sympy's branch problem is mostly <i>direction</i> (cond. 3.7 of 5.2 total) with the highest
      BTB pressure (0.6 MPKI).</p>
      <div class="figcard"><img alt="Cross-task per-window distribution grid, 16 panels in the 4x4 family layout, tool fence" src="__WX__"></div>
      <div class="take">
        <div class="chip tool">astropy FE-latency children: iCache 6.9% + DSB-switches 6.9% + resteers ≈8% (pytest windows)</div>
        <div class="chip harness">sympy: branch MPKI 5.2, DRAM-bound 4.7% — the only task with visible memory reach</div>
        <div class="chip wait">iTLB-walk ≤0.7% everywhere — instruction-TLB ruled out as an L3 cause</div>
      </div>
      <p class="note">Data: l3_study/all_windows_{scikit-learn,astropy,sympy}.csv — 15,938 window-metric
      rows across the three tasks (miss-rate metrics added 2026-07-31); per-metric box plots and tag
      timelines regenerate from the CSVs. No banked L1I access count exists, so that panel shows the
      iCache-stall share of cycles, labelled as a proxy on the figure.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Per-window study 4 · harness fence &amp; call durations</p>
      <h2>The same grid for the harness — and the cost of one call</h2>
      <p class="lead">Mirror of the previous slide for the <b>harness fence</b> (the SWE-agent process
      itself; no command tags apply — it is one program). Its distributions are far tighter than the
      tool fence's and nearly task-independent, the per-window confirmation that the harness's
      microarchitecture profile is a property of the agent, not the task. Below: the distribution of
      individual <b>tool-call wall-clock durations</b> (from the trajectory's own per-step
      execution_time; log scale) — medians sit at fractions of a second with a long build/test tail.</p>
      <div class="figcard"><img alt="Cross-task per-window distribution grid, harness fence" src="__WXH__"></div>
      <div class="figcard"><img alt="Per-call duration distribution across tasks" src="__WDUR__"></div>
      <p class="note">All values first: every panel regenerates from l3_study CSVs
      (all_windows_*.csv, call_durations_*.csv). The complete per-metric set — 33 metrics × 3 tasks ×
      (tag-split tool box, harness box, tagged timeline), ~400 figures — is browsable per task:
      <a href="https://claude.ai/code/artifact/c12b01c1-7ac7-4f2e-8729-b1c90f5ef63b">scikit-learn gallery</a> ·
      <a href="https://claude.ai/code/artifact/3b68efd2-f9f0-49ad-b047-20ac27bb3c68">astropy gallery</a> ·
      <a href="https://claude.ai/code/artifact/704ab3b2-3b63-4c57-b087-88dcdcf968ff">sympy gallery</a>.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Multilingual · SWE-bench Multilingual</p>
      <h2>Does the profile hold outside Python?</h2>
      <p class="lead">The same per-window study extended along the <b>language</b> axis: babel
      (<b>JavaScript</b>, V8/Node) and fmt (<b>C++</b>, clang/gcc) — real SWE-bench Multilingual
      instances, profiled by deterministic replay of their certified trajectories at zero API cost.
      The instruction-supply story is <b>not</b> a CPython artifact: babel carries the
      highest L1I pressure of these five tasks (20.8 MPKI, 7.5 % iCache stall — the full
      nine-language axis later moved the maximum to Rust, slide 26) and fmt is
      comparable to the Python interpreters (16.1 / 5.3 %). Both reach main memory more than any
      Python task (DRAM-bound 7.6 % and 5.6 % vs 0.0–4.7 %), and both mispredict like the
      interpreters (branch MPKI 4.7 / 4.5, direction-dominated).</p>
      <div class="figcard"><img alt="Per-window distributions across five tasks and three languages, tool fence" src="__MLGRID__"></div>
      <div class="take">
        <div class="chip tool">JS: L1I 20.8 · µop-cache 61.5 · BTB 1.56 (highest of these five) · DRAM-bound 7.6%</div>
        <div class="chip tool">C++: L1I 16.1 · µop-cache 47.1 · compile owns 49/66 windows at IPC 1.86</div>
        <div class="chip tool">The JS toolchain owns <b>77–78 %</b> of babel's tool-fence instructions — measured two ways</div>
        <div class="chip wait">scikit-learn stays the outlier: the only vector-FP task (60%) and the only near-zero-L1I one</div>
      </div>
      <p class="note"><b>Provenance.</b> The three Python tasks come from the reproduced
      superseded_40min campaign; babel and fmt are the SWE-bench Multilingual instances banked in
      the certified SWE_clean campaign (the only place their trajectories exist) — mixing is
      acceptable because per-window microarchitecture shares are the layer that reproduces across
      campaigns (slide 16), and every figure states it. <b>Method note:</b> replaying a foreign
      campaign's trajectory needs `localize_traj.py` first — a .traj embeds the absolute
      tool-bundle paths of the machine that recorded it, and SWE_clean's point at another
      workstation, which makes run-replay die before the sandbox launches.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Multilingual · harness &amp; per-language detail</p>
      <h2>The harness is language-independent too</h2>
      <p class="lead">Same grid for the <b>harness fence</b> across all five tasks: SWE-agent's own
      Python process shows the same tight, task- <i>and language</i>-independent profile
      (IPC 2.81–2.95, DSB 83–85 %, L1I ≈ 3–4 MPKI) whether it is driving a Python, JavaScript or
      C++ repair. What changes with the language is entirely inside the tool fence. Below: the
      per-window L1I timelines, colored by the command actually running — the C++ task is the
      first in the study where <b>compilation</b> is the dominant activity class (49 of 66
      windows), while the JS task's work arrives as short shell-driven bursts.</p>
      <div class="figcard"><img alt="Per-window distributions across five tasks, harness fence" src="__MLGRIDH__"></div>
      <div class="grid2">
        <div class="figcard"><img alt="babel per-window L1I timeline by command" src="__MLTLB__"></div>
        <div class="figcard"><img alt="fmtlib per-window L1I timeline by command" src="__MLTLF__"></div>
      </div>
      <p class="note">Full per-metric sets (33 metrics × tool box · harness box · tagged timeline):
      <a href="https://claude.ai/code/artifact/18a013a4-5013-4f95-9d11-9b214ed7ffbe">babel gallery</a> ·
      <a href="https://claude.ai/code/artifact/f84723fc-9fdb-424d-8728-8fa29bf3a5e6">fmt gallery</a>.
      Data: SWE_clean/data/l3_study/all_windows_{babel,fmtlib}.csv (4,356 window-metric rows from
      22 dedicated-group replays).</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Multilingual · nine languages</p>
      <h2>Nine languages, twelve tool workloads</h2>
      <p class="lead">The axis extended with seven live episodes (Rust, C, Go, Java, TypeScript,
      Ruby, PHP — one instance each), profiled by the same per-window method. Before spending the
      11 profiling passes, every task must pass a two-part gate: <b>ownership</b> — the share of
      tool-fence instructions in windows where the language's own toolchain was actually observed
      running (bar: 50%) — and <b>adequacy</b> — at least 20 windows and 150 G instructions per
      pass. Three instances failed and were replaced or dropped; every accepted episode also
      passed the standard validity gates (isolation witness, 100% TMA coverage, action
      uniqueness, cpu.stat-vs-PMU agreement).</p>
      <div class="figcard"><img alt="Per-window distributions across twelve workloads and nine languages, tool fence" src="__MLGRID12__"></div>
      <div class="take">
        <div class="chip tool">Ownership 92–99% on all accepted tasks — the fences really measure each language's toolchain</div>
        <div class="chip wait">3 of 12 attempted instances rejected by automated gates (too-small fence · degenerate loop · unstable IPC)</div>
        <div class="chip harness">Go, Java &amp; PHP episodes ran with a harness state hook failing once per step (no python3 in those images) — disclosed; CPU data unaffected</div>
      </div>
      <p class="note"><b>Gate results</b> (ownership · windows/pass · Ginstr/pass): Java gson 99.2% · 40w/1475G —
      TypeScript vue 99.1% · 22w/788G — Ruby rubocop 98.1% · 39w/339G — C++ fmt 97.2% · 66w/1313G —
      Rust tokio 96.9% · 44w/696G — PHP php-cs-fixer 96.7% · 80w/566G — Go prometheus 95.7% · 119w/1618G —
      C jq 92.1% · 47w/398G — JavaScript babel 78.2% · 20w/189G (the floor the adequacy bar is set at).
      Rejected: gin (Go, 15w/137G despite 63% ownership), carbon (PHP, 12-identical-action loop),
      laravel (PHP, 6.4 core-s, split-half IPC unstable). Galleries:
      <a href="https://claude.ai/code/artifact/ee3c3c29-b2d0-48f0-9e84-2215435d1c85">tokio</a> ·
      <a href="https://claude.ai/code/artifact/9a6d9546-5589-4fd4-aa8d-534397b9034c">jq</a> ·
      <a href="https://claude.ai/code/artifact/43bdccbb-e539-4a97-9758-99f4c75e4f1a">prometheus</a> ·
      <a href="https://claude.ai/code/artifact/024cd36f-e98c-45c7-8595-ece33bc8c891">gson</a> ·
      <a href="https://claude.ai/code/artifact/1135e8b0-7ebf-48e9-a839-60da45099c00">rubocop</a> ·
      <a href="https://claude.ai/code/artifact/5e03855b-62db-4d1a-9522-145fff53bd2c">vue</a> ·
      <a href="https://claude.ai/code/artifact/e6a80616-9410-446f-b1d7-fc1eeac751b2">php-cs-fixer</a>.
      Data: local_agents/ML_multiling/data (episodes, replays, l3_study CSVs).</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Multilingual · what survived scrutiny</p>
      <h2>Composition reproduces; magnitude does not</h2>
      <p class="lead">Deterministic replay reproduces a live episode's tool CPU to ~1% across 11
      passes (Rust 191.6–193.8 vs live 192.3 core-s; C and Go the same; Java ~7% — the JVM's JIT
      and GC are the one genuinely nondeterministic runtime). But <b>independent live episodes of
      the same instance</b> vary hugely: babel's four episodes span 37.9–202.1 tool core-s, a
      <b>5.3×</b> spread with only the sampling seed varying. So per-window <i>composition</i> is
      the trustworthy layer; absolute magnitudes are episode noise. The cleanest confound-free
      result is <b>within one Go episode</b>: compile-tagged windows run at µop-cache 59.4 MPKI vs
      37.6 in test-execution windows — same task, same language, same run. And Java has the best
      front-end of any tool workload (µop-cache 25.9, DSB coverage 82.5%): a warmed JIT re-runs a
      small hot code set, while a compiler streams once through vast distinct code — code <i>reuse</i>,
      not compiler size, is what the front-end metrics track (V8 is also a JIT and sits at 61.3).</p>
      <div class="figcard"><img alt="Go per-window uop-cache MPKI timeline, colored by command tag" src="__GOUOPTL__"></div>
      <div class="take">
        <div class="chip tool">Within Go: compile 59.4 vs test 37.6 µop-cache MPKI — no cross-language confound</div>
        <div class="chip harness">Corrected en route: Ruby's "bundler 53%" was rubocop itself (path-collision mislabel); vue's transpile term was esbuild hiding in pkg/build; fmt-vs-gin fence gap is 9.6×, not 100×</div>
        <div class="chip wait">Command tagger rewritten to match program basenames — labels changed, counter values never did (0-value diffs on all 13 tasks)</div>
      </div>
      <p class="note">The earlier "front-end pressure orders by compiler sophistication" reading is
      retracted: it compared build-dominated tasks (C, Go, C++) against test-dominated ones (Rust,
      Java) — a type confound. The within-task split above is the version that survives.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Multilingual · sampling frame</p>
      <h2>Choosing tasks by ⟨language, type⟩</h2>
      <p class="lead">All 300 SWE-bench Multilingual instances were inventoried (Ruby 44 · Java 43 ·
      Rust 43 · PHP 43 · Go 42 · JavaScript 31 · C 30 · TypeScript 12 · C++ 12, across 41 repos) and
      categorized. Finding: if "type" means the <b>CPU mechanism</b> (build-driver, AOT-unified,
      JVM, interpreted, node-transpile), type is a function of the language in this benchmark —
      every language occupies exactly one mechanism, so the ⟨language, mechanism⟩ grid has 9
      reachable cells and the twelve profiled workloads already cover all of them. The open
      dimension is the <b>agent's behavioural mix</b> — search- vs edit- vs test-dominated episodes —
      which was expected to vary within a language. It does not. Measured with editor <i>view</i>
      counted as reading, and then <b>tested with three falsification probes</b> aimed at the
      instances most likely to break the pattern, <b>16 of 16 episodes across 9 languages and 15
      repos are search-led</b>. The decisive probe: the largest gold patch in the whole corpus
      (9 files / 534 added lines) realized <b>3% edit actions</b>. So the action mix belongs to
      this agent at temperature 0.6, not to the task — ⟨language, type⟩ cannot stratify this
      suite on either definition, and the residual structure is a search↔test gradient
      (T spans 0–47%), not four discrete types.</p>
      <div class="take">
        <div class="chip tool">Mechanism axis: saturated (9/9 cells measured)</div>
        <div class="chip harness">Behavioural axis: 16/16 episodes search-led; 3/3 probes failed to break it — sweep stopped by circuit breaker</div>
        <div class="chip wait">~17 sweep episodes (~26 h) deliberately NOT spent: premise tested with the strongest candidates and held</div>
      </div>
      <p class="note">Selection is static (patch shape, problem-statement cues, test counts from the
      instance metadata), then verified post-hoc from the realized trajectory; a cell is only
      counted as covered by its <i>realized</i> type. Inventory:
      local_agents/ML_multiling/data/multiling_inventory.csv; extractor and classifier live in
      local_agents/kit/.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Matched configuration · what the caveat was worth</p>
      <h2>The SMT caveat is now a measurement, not a footnote</h2>
      <p class="lead">Every cross-workload figure used to carry the same disclaimer: this campaign
      ran <b>SMT-ON on 20 logical CPUs at 2 s windows</b>, so cycle-normalised metrics could not be
      compared cleanly against anything captured differently. On 2026-08-07/08 the replays were
      re-captured on the reference configuration — <b>measured cores 4–11 with SMT off, 100 ms
      windows</b>, same partition, same fence, same trajectories, model never called. The disclaimer
      became a number.</p>
      <div class="figcard"><img alt="Configuration effect: same tasks, SMT-ON 2 s vs SMT-off 100 ms" src="__CFGEFFECT__"></div>
      <div class="take">
        <div class="chip tool">IPC <b>1.591 → 1.890</b> (+18.8 %) — the sibling thread was taking about a fifth of the issue slots</div>
        <div class="chip harness">every shared resource improves: L1I MPKI <b>-11.6 %</b>, L1D <b>-14.2 %</b>, LLC <b>-12.3 %</b>, DRAM <b>-13.7 %</b></div>
        <div class="chip wait">TMA shape holds: frontend-bound <b>-1.4 pp</b>, bad speculation <b>-0.4 pp</b>, backend-bound <b>+3.7 pp</b></div>
      </div>
      <p class="note"><b>Confound control.</b> The matched capture covers 12 tasks and the retired
      one covers 2, so comparing the populations wholesale would mix a configuration change with a
      task-set change. This figure uses only the two tasks present in <i>both</i> — babel and fmtlib
      — replayed from the same trajectories through the same kit, so the configuration is the only
      thing that differs.
      <br><br><b>What it means for everything before this slide.</b> The TMA conclusions never
      depended on the caveat: removing the sibling moves the shape by at most
      3.7 pp. The <i>throughput</i> ones did —
      any absolute IPC quoted from the SMT-ON capture is ~19 % low. Contention within the agent
      (harness + container on the same partition) is unchanged and remains real.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Matched configuration · the traditional-workload baseline</p>
      <h2>Against SPEC CPU 2026, on one configuration</h2>
      <p class="lead">With the agent and the baseline now captured identically, the comparison needs
      no asterisk. SPEC CPU 2026: 26 benchmarks, ref inputs, 1 copy on 1 isolated SMT-free core,
      the same eight certified counter groups and the same code computing every ratio. Agent:
      <b>96 dedicated-group replays over 12 tasks in 10 languages</b>, each giving one counter
      group 100 % duty.</p>
      <div class="figcard"><img alt="SPEC vs agentic paired medians, matched configuration" src="__SPECCMP__"></div>
      <div class="take">
        <div class="chip tool">instruction supply: L1I MPKI <b>11.7×</b>, microcode <b>13.7×</b>, MITE <b>3.2×</b></div>
        <div class="chip harness">system time: kernel <b>31.7×</b> — the largest gap of all</div>
        <div class="chip wait">the data side does not separate: AMAT <b>0.99×</b>, MLP <b>1.02×</b>, DRAM <b>0.84×</b></div>
      </div>
      <p class="note">The metrics everyone reaches for first — cache misses, memory bandwidth,
      access latency — are exactly the ones that do <i>not</i> tell the two workloads apart. What
      separates agentic work from a compute benchmark is how hard it is to <b>feed instructions to
      the core</b> and how much time it spends in the <b>kernel</b>. Each row rests on the 12
      episodes that ran its counter group, one per task; the count is printed per row, and the
      individual episode markers show the spread across languages.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Matched configuration · where the slots go</p>
      <h2>Frontend-bound — and mis-speculating</h2>
      <p class="lead">All four Level-1 buckets on one radar, so the profile is read as a shape
      rather than a stack. TMA is the safest cross-workload view available: separate continuous
      census, zero general-purpose counters, and — as the previous slide showed — almost
      insensitive to the configuration change.</p>
      <div class="figcard"><img alt="TMA radar including bad speculation, plus per-episode scatter" src="__SPECTMA__"></div>
      <div class="take">
        <div class="chip tool">frontend-bound <b>29.2 %</b> vs SPEC <b>18.3 %</b></div>
        <div class="chip proxy">bad speculation <b>14.1 %</b> vs SPEC <b>10.0 %</b> — a second, independent front-end cost</div>
        <div class="chip harness">backend-bound <b>24.2 %</b> vs SPEC <b>26.7 %</b>; retiring <b>30.9 %</b> vs <b>36.0 %</b></div>
      </div>
      <p class="note">The right panel is the honest version of the bad-speculation claim: the
      agent's 14.1 % is high but not extreme for the suite —
      729.abc_r loses 49 % of its slots to mis-speculation and six more SPEC benchmarks exceed
      20 %. What isolates agentic work is the <b>combination</b>: high frontend-bound <i>and</i>
      high bad speculation at once, a corner it shares with only two of the 26 benchmarks.
      The four axes are per-episode medians and do not sum to 100 % — read each on its own.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Matched configuration · TMA Level 1 per fence</p>
      <h2>The front-end problem belongs to the tools, not the harness</h2>
      <p class="lead">The same TMA Level 1 view as earlier in the deck, rebuilt on the matched
      capture — <b>12 tasks in 10 languages</b>, cores 4–11 with SMT off, 100 ms windows — and with
      the two fences kept apart. They are different programs doing different work, and pooling them
      hides the result.</p>
      <div class="figcard"><img alt="TMA Level 1 per fence across 12 tasks and 10 languages" src="__TMAFENCES__"></div>
      <div class="take">
        <div class="chip tool">tool fence: frontend-bound <b>32.5 %</b>, bad speculation <b>15.9 %</b>, retiring <b>29.0 %</b></div>
        <div class="chip harness">harness fence: frontend-bound <b>18.7 %</b>, bad speculation <b>11.7 %</b>, retiring <b>38.4 %</b></div>
        <div class="chip wait">the gap is <b>13.8 pp</b> of frontend-bound and <b>4.2 pp</b> of bad speculation — same machine, same episode, different fence</div>
      </div>
      <p class="note"><b>This qualifies the headline.</b> "Agentic work is frontend-bound" is really
      a statement about the <b>tool</b> fence — the commands the agent spawns. The harness (the
      SWE-agent Python process) looks much more like a conventional program: it retires more, stalls
      on the back end, and mis-speculates less. The whole-episode number is a blend of the two, so a
      figure that pools them understates how frontend-starved the tool side actually is.
      <br><br><b>The consistency across languages is the striking part.</b> Every tool fence except
      one sits at 29–37 % frontend-bound and 13–19 % bad speculation, across Python, JavaScript,
      TypeScript, C++, C, Go, Java, Rust, Ruby and PHP. The exception is <b>scikit-learn</b> at
      64 % backend-bound — its test suite is numeric (BLAS), so it behaves like SPEC's FP
      benchmarks rather than like a tool workload. That row is the control: when an agent happens
      to run genuinely numeric code, the instrument says so.
      <br><br>Source: the continuous PERF_METRICS census, read <code>--for-each-cgroup</code> and
      therefore already attributed per fence, consuming no general-purpose counter. Each task pools
      its 8 replay episodes; the per-episode spread is banked in
      <code>tma_l1_fences_values.json</code>.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Matched configuration · per-window distributions</p>
      <h2>Every metric, per 100 ms window, across ten languages</h2>
      <p class="lead">The cross-task distribution grid rebuilt on the matched capture. The earlier
      version of this figure used <b>2-second</b> windows; at <b>100 ms</b> the same episodes yield
      roughly <b>ten times</b> as many windows — <b>307–1,359</b>
      per task, <b>10,014</b> in total for the tool fence — so the tails and the outliers are
      resolved rather than averaged away.</p>
      <div class="figcard"><img alt="Per-window distribution grid, tool fence, 100 ms windows, 12 tasks" src="__GRIDISO8__"></div>
      <div class="take">
        <div class="chip tool">one campaign, one configuration: cores 4–11 SMT off, 100 ms windows, 12 tasks in 10 languages</div>
        <div class="chip harness">the harness-fence grid is the companion figure — same axes, same populations</div>
        <div class="chip wait">13 of 16 panels: BTB MPKI, µop-cache MPKI and branch-direction MPKI need the <code>fe_miss</code> counter group, which this capture does not include</div>
      </div>
      <p class="note"><b>What changed besides the window length.</b> The earlier grids drew their
      twelve tasks from <i>three different campaigns</i> — the reproduced superseded_40min run for
      Python, the certified SWE_clean run for babel and fmt, and the multilingual pilots for the
      rest — and every figure had to state that provenance in its caption. Here all twelve come
      from one tree captured under one configuration, so the caption is a statement about the
      machine rather than an apology for the data.
      <br><br><b>The three missing panels are missing on purpose, not silently.</b> This capture
      ran the eight counter groups shared with the SPEC baseline, which is what the cross-workload
      comparison needs; the three frontend-miss metrics live in a ninth group. Adding them is
      twelve more replay passes and no API spend — the earlier frozen grids
      (<code>_py3</code>, <code>_5t</code>, <code>_12t</code>) keep all sixteen and are untouched,
      so nothing that a previous slide references has moved.</p>
    </div>
  </section>

</div>
<div class="progress-spacer"></div>
"""

BODY = (BODY.replace("__SPLIT__", IMG["split"]).replace("__CPU__", IMG["cpu"])
            .replace("__TIMELINE__", IMG["timeline"]).replace("__CALLS__", IMG["calls"])
            .replace("__CMPWALL__", IMG["cmp_wall"]).replace("__CMPCPU__", IMG["cmp_cpu"])
            .replace("__CMPTLMOH__", IMG["cmp_tl_moh"]).replace("__CMPTLNEW__", IMG["cmp_tl_new"])
            .replace("__CMPABS__", IMG["cmp_abs"]).replace("__CMPCALLS__", IMG["cmp_calls"])
            .replace("__CMPHEAVY__", IMG["cmp_heavy"])
            .replace("__TMAMOH__", IMG["tma_moh"]).replace("__TMANEW__", IMG["tma_new"])
            .replace("__SIGMOH__", IMG["sig_moh"]).replace("__SIGNEW__", IMG["sig_new"])
            .replace("__TMAALL__", IMG["tma_all"])
            .replace("__L2MOH__", IMG["l2_moh"]).replace("__L2NEW__", IMG["l2_new"])
            .replace("__WIPC__", IMG["w_ipc"]).replace("__WL1I__", IMG["w_l1i"]).replace("__WTL__", IMG["w_tl"])
            .replace("__WX__", IMG["w_x"]).replace("__WXH__", IMG["w_xh"]).replace("__WDUR__", IMG["w_dur"])
            .replace("__MLGRID__", IMG["ml_grid"]).replace("__MLGRIDH__", IMG["ml_gridh"])
            .replace("__MLTLB__", IMG["ml_tl_babel"]).replace("__MLTLF__", IMG["ml_tl_fmt"])
            .replace("__MLGRID12__", IMG["ml_grid12"]).replace("__GOUOPTL__", IMG["go_uop_tl"])
            .replace("__CFGEFFECT__", IMG["cfg_effect"])
            .replace("__SPECCMP__", IMG["spec_cmp"])
            .replace("__SPECTMA__", IMG["spec_tma"])
            .replace("__TMAFENCES__", IMG["tma_fences"])
            .replace("__GRIDISO8__", IMG["grid_iso8"]))

HTML = ('<title>Agent CPU profiling — GLM-5.2 SWE-agent</title>\n'
        '<style>' + CSS + '</style>\n' + BODY + '\n<script>' + JS + '</script>\n')

OUT.write_text(HTML, encoding="utf-8")
print("wrote", OUT, f"({len(HTML)/1024/1024:.2f} MB)")
