#!/usr/bin/env python3
"""sim_v1_lbr.py — offline self-test of the V1 pipeline (analyzer + check_v1.py) with no capture.

Replays the V1 program's taken-branch sequence (built from the design and the binary's own
addresses) and samples it like LBR: every PERIOD-th taken branch, emit the 32 most recent
entries newest first, in `perf script -F pid,brstack --show-mmap-events` format. Feeding this
to lbr_footprint and then check_v1.py must PASS; --break-k16 swaps one K=16 target for
another in the replayed schedule and must FAIL (T=15 at that site, one target `ret` never
executes). --kernel-noise adds a syscall-like far entry plus kernel entries to every 10th
sample, to exercise the far-transfer and kernel paths.

  sim_v1_lbr.py --binary v1_synth [--samples 50000] [--period 1009] [--break-k16] [--kernel-noise] > sim.txt
"""
import argparse
import os
import re
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_v1 import load_segments, read_va, sh  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    ap.add_argument("--samples", type=int, default=50000)
    ap.add_argument("--period", type=int, default=1009)
    ap.add_argument("--break-k16", action="store_true")
    ap.add_argument("--kernel-noise", action="store_true")
    a = ap.parse_args()
    b = a.binary
    syms = {}
    for ln in sh("nm", b).splitlines():
        p = ln.split()
        if len(p) == 3:
            syms[p[2]] = int(p[0], 16)
    segs = load_segments(b)
    dis = sh("objdump", "-d", "--insn-width=16", b)
    ins = []
    for ln in dis.splitlines():
        m = re.match(r"^\s+([0-9a-f]+):\t((?:[0-9a-f]{2} )+)\s*\t(\S+)\s*(.*)$", ln)
        if m:
            ins.append((int(m.group(1), 16), len(m.group(2).split()), m.group(3), m.group(4)))
    idx = {i[0]: i for i in ins}

    def branches(lo, hi):
        return [i for i in ins if lo <= i[0] < hi and (i[2] in ("call", "ret") or i[2].startswith("j"))]

    def tgt(i):
        return int(i[3].split()[0], 16)

    it = branches(syms["ffv1_iter"], syms["ffv1_a"])
    call_a, call_b, jnz_it, call_c, ret_it = it
    blks = [syms[f"ffv1_a_blk{k}"] for k in range(8)]
    a_br = branches(syms["ffv1_a"], syms["ffv1_b"])
    bb = branches(syms["ffv1_b"], syms["ffv1_t1_0"])
    call1, jnz1, call4, call16, jnz16, ret_b = bb
    c_br = branches(syms["ffv1_c"], syms["ffv1_end"])
    main_call = next(i for i in ins if i[2] == "call" and "<ffv1_iter>" in i[3])
    main_jne = next(i for i in ins if i[0] > main_call[0] and i[2].startswith("j"))
    repb = int(re.search(r"\$0x([0-9a-f]+),%r9d", next(i for i in ins if i[0] == call_a[0] + 5)[3]).group(1), 16)
    r8 = [int(m.group(1), 16) for i in ins if syms["ffv1_b"] <= i[0] < syms["ffv1_t1_0"]
          for m in [re.search(r"\$0x([0-9a-f]+),%r8d", i[3])] if m]
    s1, s16 = r8
    names = {v: k for k, v in syms.items()}

    def table(name, n):
        base = syms[name]
        return [base + o for o in struct.unpack(f"<{n}i", read_va(b, segs, base, 4 * n))]

    sched4, sched16 = table("ffv1_sched4", 8), table("ffv1_sched16", 32)
    t1 = syms["ffv1_t1_0"]
    if a.break_k16:
        sched16 = [syms["ffv1_t16_0"] if x == syms["ffv1_t16_15"] else x for x in sched16]

    trace = []
    E = lambda f, t, ty: trace.append((f, t, ty))
    ctr4 = ctr16 = 0
    for _ in range(2):  # the whole sequence repeats every 2 iterations (K=16 schedule = 32 calls)
        E(main_call[0], syms["ffv1_iter"], "CALL")
        E(call_a[0], tgt(call_a), "CALL")
        for k, br in enumerate(a_br):
            E(br[0], blks[k + 1] if br[2] == "jmp" else call_a[0] + call_a[1], "UNCOND" if br[2] == "jmp" else "RET")
        for r in range(repb):
            E(call_b[0], tgt(call_b), "CALL")
            for k in range(s1):
                E(call1[0], t1, "IND_CALL"); E(t1, call1[0] + call1[1], "RET")
                if k < s1 - 1:
                    E(jnz1[0], tgt(jnz1), "COND")
            t = sched4[ctr4 % 8]; ctr4 += 1
            E(call4[0], t, "IND_CALL"); E(t, call4[0] + call4[1], "RET")
            for k in range(s16):
                t = sched16[ctr16 % 32]; ctr16 += 1
                E(call16[0], t, "IND_CALL"); E(t, call16[0] + call16[1], "RET")
                if k < s16 - 1:
                    E(jnz16[0], tgt(jnz16), "COND")
            E(ret_b[0], call_b[0] + call_b[1], "RET")
            if r < repb - 1:
                E(jnz_it[0], tgt(jnz_it), "COND")
        E(call_c[0], tgt(call_c), "CALL")
        for br in c_br:
            E(br[0], tgt(br) if br[2] != "ret" else call_c[0] + call_c[1], "COND" if br[2] != "ret" else "RET")
        E(ret_it[0], main_call[0] + main_call[1], "RET")
        E(main_jne[0], tgt(main_jne), "COND")

    base = 0x555555554000
    ex = next(s for s in segs if s[0] <= syms["ffv1_begin"] < s[0] + s[1])
    mstart, mlen, pgoff = base + (ex[0] & ~0xfff), ((ex[0] + ex[1] + 0xfff) & ~0xfff) - (ex[0] & ~0xfff), ex[2] & ~0xfff
    path, ino, pid = os.path.realpath(b), os.stat(b).st_ino, 4242
    out = sys.stdout
    K = 0xffffffff81000000
    out.write(f"      0 PERF_RECORD_MMAP -1/0: [{K:#x}(0x2000000) @ {K:#x}]: x [kernel.kallsyms]_text\n")
    out.write(f"      0 PERF_RECORD_FORK({pid}:{pid}):(1:1)\n")
    out.write(f"      0 PERF_RECORD_COMM: v1_synth:{pid}/{pid}\n")
    out.write(f"{pid} PERF_RECORD_COMM exec: v1_synth:{pid}/{pid}\n")
    out.write(f"{pid} PERF_RECORD_MMAP2 {pid}/{pid}: [{mstart:#x}({mlen:#x}) @ {pgoff:#x} 103:02 {ino} 0]: r-xp {path}\n")
    L = len(trace)
    for k in range(1, a.samples + 1):
        pos = k * a.period
        ents = [trace[(pos - j) % L] for j in range(32)]  # newest first
        cols = []
        if a.kernel_noise and k % 10 == 0:
            # a syscall right after the newest user branch: far entry, then 3 kernel branches
            f0 = ents[0][1]
            ents = ents[:28]
            kern = [(K + 0x1000, K + 0x1040, "COND"), (K + 0x1050, K + 0x2000, "CALL"), (K + 0x2010, K + 0x1055, "RET")]
            cols += [f"{f - 0 + 0:#x}/{t:#x}/P/-/-/1/{ty}/-" for f, t, ty in reversed(kern)]
            cols.append(f"{base + f0:#x}/{K:#x}/P/-/-/1/SYSCALL/-")
        cols += [f"{base + f:#x}/{base + t:#x}/P/-/-/1/{ty}/-" for f, t, ty in ents]
        out.write(f"{pid:7d}  " + "  ".join(cols) + "\n")
    out.write(f"{pid} PERF_RECORD_EXIT({pid}:{pid}):(1:1)\n")
    print(f"sim_v1_lbr: {L} branches per 2 iterations, {a.samples} samples at period {a.period}"
          f"{' [K16 target dropped]' if a.break_k16 else ''}{' [+kernel noise]' if a.kernel_noise else ''}", file=sys.stderr)


if __name__ == "__main__":
    main()
