#!/usr/bin/env python3
"""build_spec_deck.py — assemble the SPEC CPU 2026 baseline deck as ONE self-contained HTML
file with every figure inlined as a base64 data URI.

    DECK_OUT=/tmp/spec_deck.html /home/thu/miniforge3/envs/infersuite-full/bin/python \
        spec26/kit/plot/build_spec_deck.py        # then publish it as an Artifact

Same shell as local_agents/kit/plot/build_deck.py (scroll-snap slides, keyboard nav, progress
bar, light/dark) with the accent moved from the agent green to the SPEC blue, so the two decks
are recognisably siblings and never mistaken for each other. Figures are referenced BY PATH,
so re-running picks up regenerated PNGs automatically — regenerate them first with
plot_spec_results.py.

Every number quoted in the prose comes from spec26/plots/values_dump.json or from the capture
kit's own validator output; nothing is typed from memory.
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from spec_common import OUT as PLOTS  # noqa: E402

P = pathlib.Path(PLOTS)
OUTP = pathlib.Path(os.environ.get("DECK_OUT", "/tmp/spec_deck.html"))
V = json.load(open(P / "values_dump.json"))


def uri(name: str) -> str:
    p = pathlib.Path(name) if str(name).startswith("/") else (P / name)
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


IMG = {k: uri(f"spec_{k}.png") for k in
       ("suite_overview", "instrument", "tma_l1", "tma_l2", "signature", "uop_supply",
        "memory_ladder", "landscape", "vs_agentic_metrics", "vs_agentic_tma",
        "vs_agentic_frontend", "window_grid", "phase_timelines")}

C = V["comparison"]
def legacy_ratio(key: str) -> float:
    """agent/SPEC on the LEGACY (SMT-ON, 2 s) replays — the configuration control, used where a
    slide contrasts the two captures."""
    c = C[key]
    return c["agentic_legacy_median"] / c["spec_median"]
F = V["frontend"]
T = V["tma_compare"]
TS, TM = T["spec"], T["agentic_matched"]
TL = T["agentic_legacy_replay"] or TM
IV = V["int_vs_fp"]
ABC = V["capture"]["729.abc_r"]


def n(key: str, field: str = "ratio_replay_over_spec", d: int = 2) -> str:
    return f"{C[key][field]:.{d}f}"


CSS = """
:root{
  --bg:#f4f7fa; --panel:#ffffff; --ink:#101d28; --muted:#5a6b78;
  --line:#dbe4ec; --spec:#1b6ca8; --agent:#159f77; --proxy:#cf6a1f;
  --wait:#9aa8b2; --accent:var(--spec);
  --shadow:0 1px 2px rgba(16,29,40,.06),0 8px 30px rgba(16,29,40,.08);
  --sans:"Segoe UI",system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SF Mono","Cascadia Mono","Roboto Mono",Menlo,monospace;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#0d1319; --panel:#151f28; --ink:#e6eef5; --muted:#93a4b2;
    --line:#243240; --spec:#5fb0e8; --agent:#2fc294; --proxy:#e79a4f; --wait:#7d8c99;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 34px rgba(0,0,0,.45);
  }
}
:root[data-theme="light"]{
  --bg:#f4f7fa; --panel:#ffffff; --ink:#101d28; --muted:#5a6b78;
  --line:#dbe4ec; --spec:#1b6ca8; --agent:#159f77; --proxy:#cf6a1f; --wait:#9aa8b2;
  --shadow:0 1px 2px rgba(16,29,40,.06),0 8px 30px rgba(16,29,40,.08);
}
:root[data-theme="dark"]{
  --bg:#0d1319; --panel:#151f28; --ink:#e6eef5; --muted:#93a4b2;
  --line:#243240; --spec:#5fb0e8; --agent:#2fc294; --proxy:#e79a4f; --wait:#7d8c99;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 34px rgba(0,0,0,.45);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);
  -webkit-font-smoothing:antialiased}
.deck{scroll-snap-type:y mandatory;height:100dvh;overflow-y:auto}
.slide{min-height:100dvh;scroll-snap-align:start;display:flex;flex-direction:column;
  justify-content:center;padding:clamp(24px,5vw,80px);position:relative}
.wrap{width:100%;max-width:1120px;margin:0 auto}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--accent);margin:0 0 14px;display:flex;gap:10px;align-items:center}
.eyebrow::before{content:"";width:26px;height:2px;background:var(--accent);display:inline-block}
h1{font-size:clamp(34px,6vw,68px);line-height:1.02;letter-spacing:-.02em;margin:0;
  text-wrap:balance;font-weight:700}
h2{font-size:clamp(24px,3.4vw,38px);line-height:1.08;letter-spacing:-.015em;margin:0 0 6px;
  text-wrap:balance;font-weight:650}
.lead{font-size:clamp(15px,1.5vw,17.5px);color:var(--muted);line-height:1.6;max-width:66ch;
  margin:16px 0 0}
.figcard{background:var(--panel);border:1px solid var(--line);border-radius:14px;
  box-shadow:var(--shadow);padding:clamp(10px,1.6vw,18px);margin-top:18px}
.figcard img{display:block;width:100%;height:auto;border-radius:6px}
.take{display:flex;flex-wrap:wrap;gap:12px;margin-top:18px}
.chip{font-size:14px;line-height:1.45;background:var(--panel);border:1px solid var(--line);
  border-left:3px solid var(--accent);border-radius:8px;padding:10px 14px;flex:1 1 240px;
  color:var(--ink)}
.chip b{font-variant-numeric:tabular-nums}
.chip.spec{border-left-color:var(--spec)}
.chip.agent{border-left-color:var(--agent)}
.chip.warn{border-left-color:var(--proxy)}
.chip.mute{border-left-color:var(--wait)}
.meta{display:flex;flex-wrap:wrap;gap:10px 28px;margin-top:32px;font-family:var(--mono);
  font-size:13px;color:var(--muted)}
.meta span b{color:var(--ink);font-weight:600}
.tlist{margin:18px 0 0;padding:0;list-style:none;display:flex;flex-direction:column;gap:13px;
  max-width:74ch}
.tlist li{display:flex;gap:14px;font-size:clamp(14.5px,1.45vw,17px);line-height:1.5}
.tlist li::before{content:"";flex:0 0 8px;height:8px;margin-top:9px;border-radius:50%;
  background:var(--accent)}
.note{margin-top:22px;font-size:13.5px;color:var(--muted);border-top:1px solid var(--line);
  padding-top:14px;max-width:78ch;line-height:1.6}
.tbl{overflow-x:auto;margin-top:18px;max-width:100%}
table.k{border-collapse:collapse;font-size:14px;width:100%;min-width:640px;max-width:900px}
table.k th,table.k td{text-align:left;padding:7px 12px;border-bottom:1px solid var(--line)}
table.k th{color:var(--muted);font-weight:600;font-size:12.5px;letter-spacing:.04em;
  text-transform:uppercase}
table.k td.num{font-family:var(--mono);font-variant-numeric:tabular-nums;text-align:right}
code{font-family:var(--mono);font-size:.92em;background:var(--panel);border:1px solid var(--line);
  border-radius:4px;padding:1px 5px}
.progress{position:fixed;top:0;left:0;height:3px;background:var(--accent);width:0;z-index:20;
  transition:width .2s ease}
.counter{position:fixed;bottom:18px;right:22px;font-family:var(--mono);font-size:12px;
  color:var(--muted);z-index:20;letter-spacing:.05em}
.hint{position:fixed;bottom:18px;left:22px;font-family:var(--mono);font-size:12px;
  color:var(--muted);z-index:20;letter-spacing:.05em}
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

BODY = f"""
<div class="progress"></div>
<div class="counter">01 / 21</div>
<div class="hint">↓ / space · arrow keys to navigate</div>
<div class="deck">

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">CPU profiling · the traditional-workload baseline</p>
      <h1>What the machine does<br>when the work is <i>not</i> agentic</h1>
      <p class="lead">SPEC CPU 2026 measured with the <b>same instrument, the same counter
      groups and the same formulas</b> as the SWE-agent × GLM-5.2 campaign, on the same
      workstation. Two jobs in one capture: prove the method reproduces microarchitectural
      behaviour that is already known, and give the agentic numbers a baseline they can be
      compared against without an asterisk.</p>
      <div class="meta">
        <span>suite&nbsp; <b>SPEC CPU 2026 v1.0.1</b> · 14 intrate + 12 fprate</span>
        <span>input&nbsp; <b>ref</b> (refrate), 1 copy, 1 thread</span>
        <span>windows&nbsp; <b>{sum(c['windows_launched'] for c in V['capture'].values()):,}</b> × 100 ms</span>
        <span>validation&nbsp; <b>26/26 pass every evaluable gate</b></span>
      </div>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 1 · why this exists</p>
      <h2>A baseline has to do two jobs, not one</h2>
      <p class="lead">The agentic campaign produced numbers nobody has a reference for. Is an
      L1I MPKI of 12 high? Is 11 % kernel time unusual? Without a workload whose behaviour is
      already documented in the literature, every agentic finding is an unanchored number.</p>
      <ul class="tlist">
        <li><b>Validate the method.</b> Point the instrument at benchmarks whose behaviour is
        known — a memory-bound stencil must come out memory-bound, an interpreter must come out
        instruction-supply-starved. If it does not, the agentic numbers are not trustworthy either.</li>
        <li><b>Anchor the comparison.</b> Same machine, same fence, same 8 certified counter
        groups, same code computing every ratio. A difference between the two campaigns is then
        a difference between the workloads, and not between two people's idea of what brMPKI means.</li>
      </ul>
      <p class="note">The capture kit is a sibling of the agentic one, not a rewrite:
      <code>~/spec26-infra/infra/scripts/run_spec_campaign.sh</code>. The eight shared counter
      groups are byte-identical to the agentic campaign's, and every SPEC-vs-agentic number on
      this deck is computed by the agentic kit's own <code>extract_metrics.py</code> running over
      both sides' raw window files.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 2 · the machine</p>
      <h2>One program, one core, nothing else on it</h2>
      <p class="lead">A Xeon w5-3425 partitioned so that the measured cores do nothing but the
      benchmark. The benchmark runs inside a transient systemd scope under a top-level slice, so
      the fence is a <b>cgroup</b> — never a PID list, which loses every child the program forks.</p>
      <div class="tbl"><table class="k">
        <tr><th>Knob</th><th>Setting</th><th>Why</th></tr>
        <tr><td>measured CPUs</td><td class="num">4–11</td>
            <td>8 physical cores with their SMT siblings <b>offlined</b> — no sibling can steal issue slots</td></tr>
        <tr><td>housekeeping CPUs</td><td class="num">0–3, 12–15</td>
            <td>IRQs, workqueues and every system slice steered here at boot</td></tr>
        <tr><td>governor / turbo</td><td class="num">performance / no_turbo=1</td>
            <td>fixed clock, so cycles mean the same thing in every window</td></tr>
        <tr><td>THP</td><td class="num">never</td><td>page-size policy cannot drift between episodes</td></tr>
        <tr><td>copies / threads</td><td class="num">1 / 1</td>
            <td>one runnable thread; mean fence occupancy is gated at ≤1.05 cores</td></tr>
      </table></div>
      <p class="note">Every episode carries an <b>ISO-PROOF</b> record: measured cores sampled
      before launch and required to be under 2 % non-idle. All 26 recorded <i>max busy 0.0 % —
      silent</i>. A <code>/proc/stat</code> witness then bounds what the cgroup could not see
      (kernel threads belong to no cgroup): worst case across the suite, <b>0.03 %</b> of
      partition capacity unaccounted for.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 3 · the instrument</p>
      <h2>Never multiplex. Rotate instead.</h2>
      <p class="lead">A modern core has ~4 general-purpose counters per thread. Asking for 40
      events makes perf time-share them and scale the results up — every number becomes an
      extrapolation. So we never ask for 40. Exactly <b>one group of ≤4 GP events</b> is
      installed per 100 ms window, and the group changes every window.</p>
      <ul class="tlist">
        <li><b>11 groups, shuffled every cycle.</b> A full rotation is 1.32 s, so even the
        shortest ref command line completes dozens of them. Across the suite: <b>2,026 complete
        rotations, 2,026 distinct orders</b> — no group ever sits at a fixed phase of the program.</li>
        <li><b>Four instruments at once.</b> Windowed groups; a continuous TMA census (PERF_METRICS
        needs zero GP counters, so it runs at 100 % duty alongside); a 10 Hz <code>cpu.stat</code>
        poller; a 99 Hz sampler. They share no counter, so they can check each other.</li>
        <li><b>Zero multiplexing, measured not assumed.</b> Across all
        {sum(c['windows_launched'] for c in V['capture'].values()):,} launched windows, perf emitted
        a scaling annotation <b>zero</b> times.
        {sum(c['windows_launched'] for c in V['capture'].values()) - sum(c['windows'] for c in V['capture'].values())}
        windows produced no counter output at all and 35 more (0.16 %) had a single event
        unscheduled in a counter-setup race — those drop out of both the numerator and its own
        denominator, never one side alone.</li>
      </ul>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 4 · the trap</p>
      <h2>The co-counted denominator — an 11× error waiting to happen</h2>
      <p class="lead">If only one group is live per window, an event is counted in only ~1/11 of
      the episode. Divide that numerator by instructions summed over <i>all</i> windows and the
      denominator is 11× too large — every MPKI comes out 11× too small, and it looks perfectly
      plausible.</p>
      <p class="lead">So every ratio uses <b>co-counted</b> denominators: instructions (or cycles)
      summed over exactly the windows in which that event itself was counted, accumulated
      <b>per window</b> — a window where the event was unscheduled contributes to neither side.</p>
      <div class="take">
        <div class="chip warn">This bug was found for real in the agentic campaign (2026-07-15) at ~8× with 8 groups. Here it would be ~11×.</div>
        <div class="chip spec">Verified per episode by gate S5: the 37 single-group events use denominators <b>10.9–11.1×</b> smaller than the episode total. Exact match, all 26.</div>
      </div>
      <p class="note">A second consequence, stated because it belongs in the method section: a
      metric whose group never got a window is reported as <b>undefined</b>, never as 0.0. An
      early version returned 0.0 and inverted a DRAM finding — "SPEC moves no DRAM traffic"
      instead of "we never measured it".</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 5 · what was captured</p>
      <h2>26 benchmarks, ref inputs, one command line each</h2>
      <p class="lead">Every benchmark ran its <b>ref</b> (refrate) input at a single copy. Where a
      benchmark defines several ref command lines, exactly one runs — index 0 — and all of them are
      banked alongside the episode. At 100 ms windows even the 9.7 s episode clears the
      55-window floor by 30×. <b>Ordering, here and on the next five figures:</b> the SPECrate
      integer block first, then floating-point, each by SPEC number — the two categories have
      genuinely different profiles, and a figure sorted by measured value hides that.</p>
      <p class="lead"><b>Why the counts are not wall ÷ 100 ms</b> (the grey ghost bar). A 100 ms
      window occupies about <b>122 ms</b> of wall clock: perf is torn down and re-armed between
      windows at a fixed ~22 ms, and that cost sits between windows, not inside them. Each
      episode also has a lead-in before the first window is armed and a teardown after the
      benchmark exits — flushing the continuous TMA census, stopping the pollers and the 99 Hz
      record, stopping the scope — during which no window runs.</p>
      <div class="figcard"><img alt="Per-benchmark wall time and window count" src="__SUITE__"></div>
      <div class="take">
        <div class="chip spec">longest <b>765.roms_r</b> 330 s · <b>2,658</b> windows</div>
        <div class="chip spec">shortest <b>736.ocio_r</b> 9.7 s · <b>70</b> windows</div>
        <div class="chip warn"><b>729.abc_r worked through:</b> (11.74 s wall − {ABC['lead_in_s']:.2f} lead-in − {ABC['teardown_s']:.2f} teardown) ÷ {ABC['pitch_s']:.3f} s pitch = <b>{ABC['windows']}</b> windows, where wall ÷ 0.1 would suggest {ABC['naive_windows']:.0f}</div>
        <div class="chip mute">every episode lands at <b>72–82 %</b> of wall ÷ 100 ms (median 80 %). Short episodes pay the fixed ~1–1.5 s teardown out of a small budget, so they sit lowest</div>
        <div class="chip mute">total <b>{sum(c['windows'] for c in V['capture'].values()):,}</b> windows carrying counters ({sum(c['windows_launched'] for c in V['capture'].values()):,} launched) over <b>{sum(c['wall_s'] for c in V['capture'].values())/60:.0f}</b> minutes of benchmark time</div>
      </div>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 6 · the instrument checks itself</p>
      <h2>Three statements that use no metric value at all</h2>
      <p class="lead">Before believing anything the counters say about the programs, make them say
      something about the <i>machine</i> — something whose right answer is known in advance.</p>
      <div class="figcard"><img alt="slots per cycle, counting duty, rotation balance" src="__INSTR__"></div>
      <div class="take">
        <div class="chip spec">(a) TMA slots ÷ windowed cycles = <b>{V['instrument']['slots_per_cycle_range'][0]:.2f}–{V['instrument']['slots_per_cycle_range'][1]:.2f}</b> on all 26. Two instruments that share no counter both land on the Golden Cove issue width of <b>6</b>.</div>
        <div class="chip warn">(b) Counting duty <b>{100*V['instrument']['duty_median']:.1f}%</b>. Re-arming perf costs a fixed ~20 ms per window, so 100 ms windows run 120 ms wall. The dead time sits <i>between</i> windows and is uncorrelated with program phase.</div>
        <div class="chip spec">(c) Every group lands on <b>9.1 %</b> of windows ± noise — no metric is sampled from a systematically different part of the program than its neighbours.</div>
      </div>
      <p class="note">The duty cycle is measured from perf's own <i>seconds time elapsed</i>, not
      from our window timestamps — those are taken before launching and after reaping perf, so
      they include the setup gap and sum to ~100 % by construction. That version read 97.3 % and
      told us nothing.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 7 · the validation ledger</p>
      <h2>What passed, and what could not be proved</h2>
      <p class="lead">Thirteen gates per episode. A gate that cannot be evaluated reports
      <b>NO PROOF</b> and is never counted as a pass — absence of evidence is not evidence.</p>
      <div class="tbl"><table class="k">
        <tr><th>Gate</th><th>Result across 26 episodes</th></tr>
        <tr><td>S1 zero multiplexing</td><td>0 scaled windows; 35 unscheduled events total (0.16 %)</td></tr>
        <tr><td>S2 run correctness</td><td><b>23 pass</b> via SPEC's own specdiff · <b>3 NO PROOF</b> (vpr, gem5, marian)</td></tr>
        <tr><td>S3 single-thread occupancy</td><td>mean fence occupancy 1.000 cores</td></tr>
        <tr><td>S4 shuffled rotation</td><td>2,026 distinct orders over 2,026 complete cycles</td></tr>
        <tr><td>S5 co-counted denominators</td><td>exact match, 10.9–11.1× smaller than the episode total</td></tr>
        <tr><td>S6 isolation proof</td><td>max busy 0.0 % on measured cores, all 26</td></tr>
        <tr><td>E3 cpu.stat vs PMU</td><td>median |ΔCPUs| ≤ <b>0.005</b> — two independent subsystems agree</td></tr>
        <tr><td>E11 partition witness</td><td>unfenced residual ≤ <b>0.03 %</b> of partition capacity</td></tr>
      </table></div>
      <p class="note"><b>Why three NO PROOFs.</b> vpr, gem5 and marian build their specdiff targets
      in a post-processing step that lives outside every ref command line. Running one command line
      directly — which is the whole design — means those targets are never produced, so output
      correctness is <i>untestable</i>, not failed. Their exit status was 0 and their counters are
      as clean as the rest; only the independent correctness check is missing, and it is reported
      as missing.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 8 · where the slots go</p>
      <h2>TMA Level 1 across the suite</h2>
      <p class="lead">The continuous census, running the whole episode at 100 % duty on zero
      general-purpose counters. This is the least SMT-sensitive view in the whole study, which
      makes it the safest thing to carry across to the agentic comparison.</p>
      <div class="figcard"><img alt="TMA level 1 stacked bars, 26 benchmarks" src="__TMA1__"></div>
      <div class="take">
        <div class="chip warn"><b>INT vs FP — bad speculation {IV['tma_bad_spec']['int_median']:.1f} % vs {IV['tma_bad_spec']['fp_median']:.1f} %</b> ({IV['tma_bad_spec']['int_over_fp']:.1f}×). {IV['n_badspec_over_10pct']['int']}/14 integer benchmarks lose more than 10 % of slots to it; only {IV['n_badspec_over_10pct']['fp']}/12 FP ones do</div>
        <div class="chip spec"><b>INT vs FP — backend-bound {IV['tma_be_bound']['int_median']:.1f} % vs {IV['tma_be_bound']['fp_median']:.1f} %</b>. The categories stall in different places, and the block ordering shows it before a number is read</div>
        <div class="chip spec">most stalled: <b>749.fotonik3d_r</b> 80 % backend-bound, <b>765.roms_r</b> 70 %</div>
        <div class="chip spec">most frontend-bound: <b>723.llvm_r</b> 40 %, <b>714.cpython_r</b> 39 %, <b>709.cactus_r</b> 37 %</div>
        <div class="chip warn">most speculation-bound: <b>729.abc_r</b> 49 % bad speculation, <b>707.ntest_r</b> 24 %</div>
      </div>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 9 · which half of the stall</p>
      <h2>TMA Level 2 — latency or bandwidth, memory or core</h2>
      <p class="lead">Level 1 says "backend-bound". Level 2 says whether that is the memory
      hierarchy or the execution units, and whether a frontend stall is a fetch <i>latency</i>
      problem or a fetch <i>bandwidth</i> problem. The two have different fixes and different
      meanings.</p>
      <div class="figcard"><img alt="TMA level 2 stacked bars, 26 benchmarks" src="__TMA2__"></div>
      <div class="take">
        <div class="chip spec"><b>749.fotonik3d_r</b> 55 % memory-bound vs 25 % core-bound — the stall is DRAM</div>
        <div class="chip spec"><b>782.lbm_r</b> 8 % memory-bound but 45 % core-bound — streaming that the prefetcher already solved</div>
        <div class="chip spec"><b>723.llvm_r</b> 22 % fetch-latency vs 18 % fetch-bandwidth; <b>709.cactus_r</b> 29 % fetch-latency — instruction supply, two different ways</div>
      </div>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 10 · instruction supply</p>
      <h2>SPEC runs almost entirely out of the uop cache</h2>
      <p class="lead">The decoded-uop cache (DSB) covers a median <b>{C['DSB_pct']['spec_median']:.1f} %</b>
      of delivered uops across the suite. Legacy decode (MITE) is a rounding error for most
      benchmarks — and the exceptions are exactly the ones you would predict: compilers, a
      simulator, and an interpreter.</p>
      <div class="figcard"><img alt="uop delivery shares and L1I MPKI, 26 benchmarks" src="__UOP__"></div>
      <div class="take">
        <div class="chip spec"><b>INT vs FP — L1I MPKI {IV['L1I_MPKI']['int_median']:.1f} vs {IV['L1I_MPKI']['fp_median']:.2f}</b> ({IV['L1I_MPKI']['int_over_fp']:.1f}×) and frontend-bound {IV['tma_fe_bound']['int_median']:.1f} % vs {IV['tma_fe_bound']['fp_median']:.1f} %. Integer code is the harder instruction-supply problem — with two loud FP exceptions</div>
        <div class="chip spec"><b>782.lbm_r, 729.abc_r, 765.roms_r, 767.nest_r</b>: 99–100 % DSB, L1I MPKI ≈ 0.03–0.15 — tight loops that fit</div>
        <div class="chip warn"><b>709.cactus_r</b> (FP): 86 % MITE, L1I MPKI <b>93.3</b> — a code footprint that overruns everything</div>
        <div class="chip warn"><b>714.cpython_r</b>: 55 % MITE, L1I MPKI 26.9 — the interpreter dispatch loop, and the closest thing in SPEC to what an agent harness runs. <b>735.gem5_r</b> (36.8) and <b>748.flightdm_r</b> (22.1) are the other footprint-heavy cases</div>
      </div>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 11 · memory</p>
      <h2>The memory ladder — and one rung that lies</h2>
      <p class="lead">L1D → L2 → LLC demand misses, the modelled access latency, memory-level
      parallelism, and real DRAM traffic. The four panels disagree with each other, and the
      disagreement is the lesson. The block ordering adds a second one: <b>DRAM read bandwidth is
      an FP phenomenon</b> — median {IV['DRAM_read_GBs']['fp_median']:.2f} GB/s against
      {IV['DRAM_read_GBs']['int_median']:.2f} for integer, and {IV['n_dram_over_4GBs']['int']} of 14
      integer benchmarks exceed 4 GB/s against {IV['n_dram_over_4GBs']['fp']} of 12 FP ones.</p>
      <div class="figcard"><img alt="memory ladder: L1D, LLC, DRAM bandwidth, MLP" src="__MEM__"></div>
      <p class="note"><b>LLC_MPKI is not a memory-boundedness metric.</b> It counts <i>retired
      demand loads</i> that missed L3. <b>782.lbm_r</b> reads 0.01 LLC MPKI while streaming <b>4.3 GB/s</b>
      from DRAM — the hardware prefetcher fetched every line before the load retired, so the
      demand counter never fires. Read LLC_MPKI as "how often the prefetcher failed", and use
      <code>DRAM_read_GBs</code> or TMA <code>mem_bound</code> for memory pressure. This one
      distinction reverses the ranking of the suite's most memory-intensive members.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 12 · the signature</p>
      <h2>Every benchmark on absolute reference scales</h2>
      <p class="lead">Shading is position on a <b>fixed</b> domain range — IPC 0–6 is the core's
      retire width, MLP 1–16 is the fill-buffer count, L1I MPKI 0–20 is the datacenter
      "instruction-footprint wall". A cell means the same thing here as it does in the agentic
      signature figure, which is the point of using fixed scales instead of per-column min–max.</p>
      <div class="figcard"><img alt="26-benchmark signature heatmap on absolute scales" src="__SIG__"></div>
      <p class="note">The printed number is always the truth; the shade is a reading aid. Built by
      the same construction as <code>glm_signature.png</code> in the agentic campaign.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 13 · does the method work?</p>
      <h2>Known behaviour comes out as known behaviour</h2>
      <p class="lead">This is the slide the whole baseline exists for. If the instrument is sound,
      benchmarks with documented characters must display those characters — without anyone tuning
      anything to make it happen.</p>
      <div class="tbl"><table class="k">
        <tr><th>Benchmark</th><th>Expected character</th><th>Measured</th></tr>
        <tr><td>749.fotonik3d_r</td><td>memory-bound stencil</td>
            <td class="num">IPC 0.77 · 80 % be-bound · 55 % mem-bound · 11.3 GB/s · LLC MPKI 18.0</td></tr>
        <tr><td>765.roms_r</td><td>memory-bound ocean model</td>
            <td class="num">IPC 1.28 · 70 % be-bound · 11.3 GB/s</td></tr>
        <tr><td>782.lbm_r</td><td>streaming, prefetch-friendly</td>
            <td class="num">4.3 GB/s but LLC MPKI 0.01 · 45 % core-bound · 100 % DSB</td></tr>
        <tr><td>723.llvm_r / 721.gcc_r</td><td>large-footprint compiler</td>
            <td class="num">L1I MPKI 21.7 / 15.1 · fe-bound 40 % / 35 % · bad-spec 16 %</td></tr>
        <tr><td>714.cpython_r</td><td>interpreter dispatch</td>
            <td class="num">55 % MITE · L1I MPKI 26.9 · fe-bound 39 % · be-bound 3 %</td></tr>
        <tr><td>750.sealcrypto_r</td><td>compute-dense crypto</td>
            <td class="num">IPC 4.15 · 74 % retiring · LLC MPKI 0.00</td></tr>
        <tr><td>729.abc_r</td><td>branchy logic synthesis</td>
            <td class="num">49 % bad speculation</td></tr>
      </table></div>
      <p class="note">Nothing in this table was targeted. Each row is the first ref command line
      of that benchmark at index 0, measured by the same rotation as every other row.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 14 · the layer underneath</p>
      <h2>Every metric, per 100 ms window, per benchmark</h2>
      <p class="lead">Everything so far has been an episode sum. Underneath each of those numbers
      is a distribution over hundreds of windows — and a benchmark that averages 1.6 IPC because
      it alternates between 0.5 and 2.1 is a very different object from one that sits at 1.6.
      Read down the <b>brMPKI</b> panel: the integer block sits one to three decades above the
      floating-point block, median <b>{IV['brMPKI']['int_median']:.2f} vs {IV['brMPKI']['fp_median']:.3f}</b>
      mispredicts per 1000 instructions — a <b>{IV['brMPKI']['int_over_fp']:.0f}×</b> gap that is the
      single sharpest INT/FP separation in the whole capture.</p>
      <div class="figcard"><img alt="per-window distributions across the suite" src="__GRID__"></div>
      <p class="note">Box = IQR, orange = median, whiskers = 5–95 %. Each metric's distribution is
      over the windows that carried <i>its</i> counter group — about 1/11 of the episode, scattered
      across the whole run by the shuffled rotation, never a contiguous slice. IPC is the exception:
      cycles and instructions ride in every group, so IPC has every window. The full per-benchmark
      set — 36 metrics, distribution plus timeline — is the per-window gallery.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 15 · phases</p>
      <h2>The episode number is a sum over states, not a description of one</h2>
      <p class="lead">Some benchmarks are one steady state. Others walk through several, and their
      episode value describes none of them.</p>
      <div class="figcard"><img alt="per-window IPC timelines for six benchmarks" src="__PHASE__"></div>
      <div class="take">
        <div class="chip warn"><b>723.llvm_r</b> episode IPC {V['phases']['723.llvm_r']['episode_IPC']:.2f}, windows span {V['phases']['723.llvm_r']['window_min']:.2f}–{V['phases']['723.llvm_r']['window_max']:.2f}</div>
        <div class="chip warn"><b>749.fotonik3d_r</b> episode IPC {V['phases']['749.fotonik3d_r']['episode_IPC']:.2f}, windows span {V['phases']['749.fotonik3d_r']['window_min']:.2f}–{V['phases']['749.fotonik3d_r']['window_max']:.2f}</div>
        <div class="chip spec"><b>782.lbm_r</b> episode IPC {V['phases']['782.lbm_r']['episode_IPC']:.2f}, windows span {V['phases']['782.lbm_r']['window_min']:.2f}–{V['phases']['782.lbm_r']['window_max']:.2f} — genuinely one state</div>
      </div>
      <p class="note">This is also why a per-window median is <i>not</i> the episode value: the
      episode value is a ratio of sums, weighted by where the cycles actually went. Both are
      correct and they answer different questions.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 16 · the comparison</p>
      <h2>Where the agent sits in the landscape</h2>
      <p class="lead">26 SPEC benchmarks on IPC against total stalled slots, with the agentic
      median dropped into the same space. The agent is not off the chart — it lands in the middle
      of the suite on the axes everyone quotes, which is exactly why the axes everyone quotes are
      not the interesting ones.</p>
      <div class="figcard"><img alt="IPC vs stalled slots landscape with agentic median" src="__LAND__"></div>
      <p class="note">Agentic point: median of the {V['n_agentic_replay']} SWE-agent × GLM-5.2
      dedicated-group replays captured under the SPEC configuration (cores 4–11, SMT off, 100 ms
      windows). Read on for the metrics where the two workloads genuinely separate.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 17 · the comparison</p>
      <h2>Same instrument, same formulas, same machine</h2>
      <p class="lead"><b>What the green bar is.</b> A <b>dedicated-group replay</b>: SWE-agent
      re-executes a recorded trajectory in a fresh sandbox with the model never called, and the
      whole episode counts <b>one</b> counter group at 2 s windows. Commands genuinely re-run, so
      the microarchitecture is real; only the <i>choice</i> of commands is frozen. Each task was
      replayed <b>11 times, once per counter group</b>; the eight shared with SPEC appear here.</p>
      <p class="lead"><b>Why compare against that.</b> Three reasons, all about removing doubt
      from the agentic side rather than from SPEC. The group is live at <b>100 % duty</b> for the
      episode instead of 1/8 of it, so the metric is not a sample. The episode is
      <b>deterministic</b> and free of API cost, so it can be repeated. And no model latency sits
      inside the measured interval. What it buys in cleanliness it pays for in breadth — see the
      caveat below.</p>
      <div class="figcard"><img alt="SPEC vs agentic-replay paired medians on the shared 8 groups" src="__CMP__"></div>
      <div class="take">
        <div class="chip agent">instruction supply: L1I MPKI <b>{n('L1I_MPKI')}×</b>, MITE <b>{n('MITE_pct')}×</b>, microcode <b>{n('MS_pct')}×</b>, branch MPKI <b>{n('brMPKI')}×</b></div>
        <div class="chip agent">system time: kernel <b>{n('kernel_pct')}×</b> — the largest gap on the slide</div>
        <div class="chip mute">the data side does not separate at all: AMAT <b>{n('AMAT_cyc')}×</b>, L1D MPKI <b>{n('L1D_MPKI')}×</b>, MLP <b>{n('MLP')}×</b>, DRAM read <b>{n('DRAM_read_GBs')}×</b></div>
      </div>
      <p class="note"><b>Reading the two counts.</b> <b>n = {V['n_agentic_replay']}</b> is the
      dedicated-group replay population — 8 shared groups × 2 tasks. <b>n = 7</b> (used on
      slides 18–19) is the other agentic instrument: episodes that shuffled all 8 groups the way
      SPEC does, so one episode yields a full metric card. They are not interchangeable and are
      never merged. <b>The per-row number on the right is the one that matters here:</b> a replay
      measures one group, so each metric rests on the <b>2</b> episodes that ran <i>its</i> group
      — never on all {V['n_agentic_replay']}. IPC is the exception ({C['IPC']['agentic_replay_n']}),
      because cycles and instructions ride in every group.
      <br><br><b>Why the whisker is only on the SPEC bar.</b> With 26 benchmarks a range means
      something — it says whether the gap is the whole suite or one outlier. With 2 episodes a
      "range" is just the two points, so the figure plots them instead, marked by task. Read them:
      kernel time is <b>20.7 %</b> on babel against <b>5.0 %</b> on fmtlib, a 4× spread inside a
      2-point median.
      <br><br><b>A correction to the version shown on 2026-08-06.</b> That figure selected the
      replay population by counter-group count, which also swept in three <i>live</i> single-group
      probe episodes — model in the loop, not replays. Selecting by provenance drops them and
      moves two rows: L1I MPKI 18.00× → <b>{n('L1I_MPKI')}×</b>, and DRAM read bandwidth
      0.52× → <b>{n('DRAM_read_GBs')}×</b>, i.e. from "SPEC reads 1.9× more" to near parity.
      Every other row is unchanged.
      <br><br><b>The cost of this choice.</b> The replays cover <b>2 tasks — babel (JavaScript)
      and fmtlib (C++)</b>. Both Python tasks (django, sympy) are absent, and the rotation
      population covers 4. Switching to replays therefore <i>strengthens</i> the instruction-supply
      result (L1I 11.96× → {n('L1I_MPKI')}×, kernel 23.18× → {n('kernel_pct')}×) and
      <i>erases</i> the DRAM one (0.07× → {n('DRAM_read_GBs')}×) — and that second move is a
      task-composition effect, not an instrument effect: fmtlib compiles C++ and moves real memory
      traffic where the Python tasks do not.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 18 · the comparison</p>
      <h2>SPEC stalls on the back end. The agent stalls on the front end — and mis-speculates.</h2>
      <p class="lead">All four Level-1 buckets on one radar, because the question is the
      <i>shape</i> of the profile rather than its composition. TMA is the cleanest cross-campaign
      view available: it comes from a separate continuous census and needs no general-purpose
      counters. Bad speculation is on the radar at the mentor's request — and it earns its axis.</p>
      <div class="figcard"><img alt="TMA radar and per-episode bad speculation" src="__CMPTMA__"></div>
      <div class="take">
        <div class="chip agent">frontend-bound <b>{TM['fe_bound']:.1f} %</b> vs SPEC <b>{TS['fe_bound']:.1f} %</b> — the agent's defining stall</div>
        <div class="chip warn">bad speculation <b>{TM['bad_spec']:.1f} %</b> vs SPEC <b>{TS['bad_spec']:.1f} %</b> ({TM['bad_spec']/TS['bad_spec']:.1f}×) — a second, independent front-end cost</div>
        <div class="chip spec">backend-bound <b>{TM['be_bound']:.1f} %</b> vs SPEC <b>{TS['be_bound']:.1f} %</b>; retiring <b>{TM['retiring']:.1f} %</b> vs <b>{TS['retiring']:.1f} %</b></div>
      </div>
      <p class="note">The four axes are <b>per-episode medians</b>, so they do not sum to 100 %
      (SPEC: 91.1). Read each axis on its own.
      <br><br><b>The right-hand panel is the honest version of the bad-speculation claim.</b> The
      agent's 15.4 % is high but not extreme for the suite: <b>729.abc_r</b> loses 49 % of its
      slots to mis-speculation and six more SPEC benchmarks exceed 20 %. What separates the agent
      is the <i>combination</i> — it sits in the top-right region, high on frontend-bound
      <b>and</b> high on bad speculation, where only 706.stockfish_r and 723.llvm_r keep it
      company. SPEC's speculation-heavy members (777.zstd_r, 707.ntest_r, 731.astcenc_r) pay it
      while feeding the front end comfortably.
      <br><br><b>The dashed grey outline is the retired configuration</b> — the same replays under
      SMT-ON on 20 logical CPUs at 2 s windows. It sits almost on top of the matched one
      (frontend {TL['fe_bound']:.1f} vs {TM['fe_bound']:.1f}, bad-spec {TL['bad_spec']:.1f} vs
      {TM['bad_spec']:.1f}), which is the evidence that the TMA conclusions never depended on the
      SMT caveat.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Slide 19 · how strong is the claim?</p>
      <h2>The agent sits in the suite's tail, not outside it</h2>
      <p class="lead">A ratio against a median can flatter. The honest question is where the agent
      falls in the <i>distribution</i> — and SPEC's spread is enormous (L1I MPKI runs 0.03 to 93).
      So: not "beyond the suite", but "in the corner of it that nobody optimises for".</p>
      <div class="figcard"><img alt="SPEC distributions with agentic episodes overlaid" src="__CMPFE__"></div>
      <div class="take">
        <div class="chip spec">L1I MPKI: agentic median = SPEC <b>p{F['L1I_MPKI']['spec_percentile_of_agentic_median']:.0f}</b> — <b>{F['L1I_MPKI']['n_spec_more_extreme']}/26</b> SPEC benchmarks are worse (llvm, gcc, cactus, cpython …)</div>
        <div class="chip spec">MITE: agentic = SPEC <b>p{F['MITE_pct']['spec_percentile_of_agentic_median']:.0f}</b> · DSB: SPEC <b>p{F['DSB_pct']['spec_percentile_of_agentic_median']:.0f}</b></div>
        <div class="chip agent">kernel time: agentic = SPEC <b>p{F['kernel_pct']['spec_percentile_of_agentic_median']:.0f}</b> — only <b>{F['kernel_pct']['n_spec_more_extreme']}/26</b> is higher. This one genuinely leaves the suite.</div>
      </div>
      <p class="note">Which sharpens the finding rather than weakening it. SPEC <i>does</i> contain
      instruction-supply-starved members — compilers and an interpreter — but they are the minority
      and they are frontend-bound only in phases. The agent is there on every task, in every
      episode, for the whole episode.</p>
    </div>
  </section>

  <section class="slide">
    <div class="wrap">
      <p class="eyebrow">Takeaways · and what not to over-read</p>
      <h2>What the baseline established</h2>
      <ul class="tlist">
        <li><b>The method is sound.</b> Two instruments that share no counter agree on the core's
        issue width to within 0.3 % on all 26 episodes; the cgroup accounting and the PMU agree to
        0.005 CPUs; zero windows were multiplexed; known benchmark characters came out as known
        benchmark characters without anyone aiming at them.</li>
        <li><b>The workloads separate on instruction supply and system time, not on the data side.</b>
        Against the median SPEC benchmark, agentic work costs {n('L1I_MPKI')}× the instruction-cache
        pressure, {n('MITE_pct')}× the legacy decode and {n('kernel_pct')}× the kernel time — while
        AMAT ({n('AMAT_cyc')}×), L1D MPKI ({n('L1D_MPKI')}×) and MLP ({n('MLP')}×) are
        indistinguishable. The metrics everyone reaches for first are the ones that do not separate.
        DRAM read bandwidth no longer separates them at all once the configuration matches:
        {n('DRAM_read_GBs')}× (it read {legacy_ratio('DRAM_read_GBs'):.2f}× under the retired
        SMT-ON capture). The apparent DRAM gap was configuration and task composition, not a
        property of agentic work.</li>
        <li><b>Agentic behaviour is uniform where SPEC is diverse.</b> Every agentic episode lands
        in one small region of the TMA plane; the SPEC suite covers it entirely.</li>
      </ul>
      <p class="note"><b>Carry these caveats with every cross-campaign number.</b>
      <b>SMT:</b> the agentic runs are SMT-ON on 20 logical CPUs, SPEC is SMT-OFF on 8 physical
      cores. Cycle-normalised metrics — IPC, port utilisation, frontend bandwidth shares — cross
      that boundary badly; per-instruction rates survive it far better.
      <b>Contention:</b> SPEC runs one copy on one core with L3 and DRAM to itself; the agentic
      workload ran many concurrent processes and did contend.
      <b>SMT and contention — no longer a caveat, a measurement.</b> The agentic replays were
      re-captured on 2026-08-07 under the SPEC configuration exactly: measured cores <b>4–11 with
      SMT off</b>, <b>100 ms</b> windows, same partition, same fence. Every comparison figure now
      uses that matched capture, so IPC and the frontend-bandwidth shares no longer cross an SMT
      boundary. Putting the two captures side by side prices the old caveat: agentic IPC rises
      from <b>1.591</b> (SMT-ON, sibling stealing issue slots) to <b>1.890</b> (SMT-off), a
      <b>+18.8 %</b> move — while the TMA shape barely shifts. Contention remains: SPEC runs one
      copy alone, the agent runs a harness and a container.
      <br><br><b>Population.</b> Two agentic instruments, never merged. <b>Slide 17</b> uses the
      <b>dedicated-group replays</b> at the matched configuration: {V['n_agentic_replay']} episodes
      over <b>2 tasks</b> (babel, fmtlib), each giving one counter group 100 % duty — so every
      metric there rests on the 2 episodes that ran its group. Slides 18–19 add the
      <b>{V['n_agentic_legacy_replay']} legacy replays</b> (SMT-ON, 2 s) as the configuration
      control. The population is small and covers 2 tasks, both non-Python; the
      {V['n_agentic_legacy_rotation']} live 8-group rotation episodes over 4 tasks remain the
      broader-but-noisier cross-check.
      <b>LLC_MPKI</b> is a demand-miss metric, not a memory-boundedness metric.</p>
    </div>
  </section>

</div>
"""

BODY = (BODY.replace("__SUITE__", IMG["suite_overview"]).replace("__INSTR__", IMG["instrument"])
            .replace("__TMA1__", IMG["tma_l1"]).replace("__TMA2__", IMG["tma_l2"])
            .replace("__UOP__", IMG["uop_supply"]).replace("__MEM__", IMG["memory_ladder"])
            .replace("__SIG__", IMG["signature"]).replace("__GRID__", IMG["window_grid"])
            .replace("__PHASE__", IMG["phase_timelines"]).replace("__LAND__", IMG["landscape"])
            .replace("__CMP__", IMG["vs_agentic_metrics"])
            .replace("__CMPTMA__", IMG["vs_agentic_tma"])
            .replace("__CMPFE__", IMG["vs_agentic_frontend"]))

HTML = ('<title>SPEC CPU 2026 — the traditional-workload baseline</title>\n'
        '<style>' + CSS + '</style>\n' + BODY + '\n<script>' + JS + '</script>\n')

OUTP.write_text(HTML, encoding="utf-8")
print("wrote", OUTP, f"({len(HTML)/1024/1024:.2f} MB)")
