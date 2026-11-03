#!/usr/bin/env python3
"""check_v1.py — gate V1 (synthetic truth) of the front-end footprint contract.

Derives the EXPECTED footprint, unique taken branches and weighted average targets of the
hand-placed regions in v1_synth (v1_regions.S) from the design plus the built binary
(nm/objdump/ELF headers) — never from the analyzer or from a PT run — then restricts the
analyzer's tables (objects/lines/edges.tsv) to the region's canonical offsets and judges:
  footprint within 2 lines | unique taken branches exactly | wavg all/noret/indirect within 1 %.

  check_v1.py --binary v1_synth --tables <dir with objects.tsv lines.tsv edges.tsv> [--json out.json]
  check_v1.py --binary v1_synth --expected-only      # just print the derived truth

Derivation (static, design-based):
  * executed instructions: every instruction in [ffv1_begin, ffv1_end) except int3, and except
    the alignment padding after an unconditional jmp/ret up to the next symbol or direct-branch
    target; expected lines = the 64 B lines (in file-offset space) holding any of their bytes;
  * taken-branch sites: the executed jmp/jcc/call/ret instructions whose taken count > 0;
  * taken count per ffv1_iter call: from the design's loop structure, with every constant
    (REPB, the per-site repeat counts, the schedules) read back from the binary itself;
  * targets: direct branches and returns have 1 (each function has exactly one call site);
    indirect sites have the distinct entries of their schedule table, read from .rodata.
"""
import argparse
import collections
import json
import os
import re
import struct
import subprocess
import sys

NEAR = {"COND", "UNCOND", "CALL", "IND_CALL", "IND", "RET"}


def sh(*cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def load_segments(path):
    """PT_LOAD (vaddr, memsz, offset) from the ELF64 program headers."""
    with open(path, "rb") as f:
        hdr = f.read(64)
        assert hdr[:4] == b"\x7fELF" and hdr[4] == 2, "not an ELF64 file"
        phoff, = struct.unpack_from("<Q", hdr, 0x20)
        phentsize, phnum = struct.unpack_from("<HH", hdr, 0x36)
        segs = []
        for i in range(phnum):
            f.seek(phoff + i * phentsize)
            p_type, p_flags, p_offset, p_vaddr, _, p_filesz, p_memsz, _ = struct.unpack("<IIQQQQQQ", f.read(56))
            if p_type == 1:
                segs.append((p_vaddr, p_memsz, p_offset, p_filesz))
    return segs


def va_to_off(segs, va):
    # canonical offset used by the analyzer = addr - map_start + pgoff = file offset
    for v, m, o, _ in segs:
        if v <= va < v + m:
            return va - v + o
    raise ValueError(f"va {va:#x} not in any PT_LOAD")


def read_va(path, segs, va, n):
    with open(path, "rb") as f:
        f.seek(va_to_off(segs, va))
        return f.read(n)


def derive_expected(binary):
    syms = {}
    for ln in sh("nm", binary).splitlines():
        p = ln.split()
        if len(p) == 3 and p[2].startswith("ffv1_"):
            syms[p[2]] = int(p[0], 16)
    segs = load_segments(binary)
    lo, hi = syms["ffv1_begin"], syms["ffv1_end"]
    dis = sh("objdump", "-d", "--insn-width=16", f"--start-address={lo:#x}", f"--stop-address={hi:#x}", binary)
    insns, sym_at = [], {}
    cur_sym = None
    for ln in dis.splitlines():
        m = re.match(r"^([0-9a-f]+) <([^>]+)>:$", ln)
        if m:
            cur_sym = m.group(2)
            sym_at[int(m.group(1), 16)] = cur_sym
            continue
        m = re.match(r"^\s+([0-9a-f]+):\t((?:[0-9a-f]{2} )+)\s*\t(\S+)\s*(.*)$", ln)
        if m:
            insns.append({"va": int(m.group(1), 16), "len": len(m.group(2).split()), "mn": m.group(3),
                          "ops": m.group(4).strip()})
    # objdump names only one symbol per address; nm knows all (ffv1_a == ffv1_a_blk0)
    owners = sorted((a, s) for s, a in syms.items() if lo <= a < hi and s not in ("ffv1_begin", "ffv1_end"))
    starts = {a for a, _ in owners}

    # where several symbols share an address (ffv1_a == ffv1_a_blk0) the block name wins
    by_addr = {}
    for addr, s in owners:
        if addr not in by_addr or s.startswith("ffv1_a_blk"):
            by_addr[addr] = s
    owner_list = sorted(by_addr.items())

    def owner(va):
        best = None
        for addr, s in owner_list:
            if addr > va:
                break
            best = s
        return best

    def direct_target(ops):
        m = re.match(r"^([0-9a-f]+) <", ops)
        return int(m.group(1), 16) if m else None

    targets = {direct_target(i["ops"]) for i in insns if (i["mn"].startswith("j") or i["mn"] == "call")}
    live, executed = True, []
    for i in insns:
        if i["va"] in starts or i["va"] in targets:
            live = True
        if live and i["mn"] != "int3":
            executed.append(i)
        if i["mn"] in ("jmp", "ret") and live:
            live = False
    lines = set()
    for i in executed:
        for b in range(i["va"], i["va"] + i["len"]):
            lines.add(va_to_off(segs, b) & ~63)

    # ---- design constants, read back from the binary ----
    by_owner = collections.defaultdict(list)
    for i in executed:
        by_owner[owner(i["va"])].append(i)

    def imm(ins, reg):
        m = re.match(r"^\$0x([0-9a-f]+),%" + reg + "$", ins["ops"])
        return int(m.group(1), 16) if m else None

    repb = next(imm(i, "r9d") for i in by_owner["ffv1_iter"] if i["mn"] == "mov")
    r8 = [imm(i, "r8d") for i in by_owner["ffv1_b"] if i["mn"] == "mov" and imm(i, "r8d") is not None]
    s1_rep, s16_rep = r8[0], r8[1]
    t1 = [re.search(r"<(ffv1_t1_\d+)>", i["ops"]).group(1) for i in by_owner["ffv1_b"]
          if i["mn"] == "lea" and "<ffv1_t1_" in i["ops"]]

    def table(name, n):
        base = syms[name]
        offs = struct.unpack(f"<{n}i", read_va(binary, segs, base, 4 * n))
        names = {a: s for s, a in syms.items()}
        return [names[base + o] for o in offs]

    sched4, sched16 = table("ffv1_sched4", 8), table("ffv1_sched16", 32)
    sched1 = t1  # the K=1 site always calls the lea'd target

    def kind(i):
        if i["mn"] == "ret":
            return "RET"
        if i["mn"] == "call":
            return "IND_CALL" if i["ops"].startswith("*") else "CALL"
        if i["mn"] == "jmp":
            return "IND" if i["ops"].startswith("*") else "UNCOND"
        if i["mn"].startswith("j"):
            return "COND"
        return None

    # Expected per-iteration taken count C and target count T of every branch, by owner and
    # position. Region (b)'s structure is checked against the expected type sequence first.
    sites = []  # (va, type, C_per_iter, T)

    def add(i, c, t):
        if c > 0:
            sites.append((i["va"], kind(i), c, t))

    br = lambda o: [i for i in by_owner[o] if kind(i)]
    it = br("ffv1_iter")
    assert [kind(i) for i in it] == ["CALL", "CALL", "COND", "CALL", "RET"], [kind(i) for i in it]
    for i, c in zip(it, [1, repb, repb - 1, 1, 1]):
        add(i, c, 1)
    nblk = len([s for s in syms if s.startswith("ffv1_a_blk")])
    for k in range(nblk):
        b = br(f"ffv1_a_blk{k}")
        assert [kind(i) for i in b] == (["UNCOND"] if k < nblk - 1 else ["RET"]), (k, [kind(i) for i in b])
        add(b[0], 1, 1)
    bb = br("ffv1_b")
    assert [kind(i) for i in bb] == ["IND_CALL", "COND", "IND_CALL", "IND_CALL", "COND", "RET"], [kind(i) for i in bb]
    for i, c, t in zip(bb, [s1_rep, s1_rep - 1, 1, s16_rep, s16_rep - 1, 1],
                       [len(set(sched1)), 1, len(set(sched4)), len(set(sched16)), 1, 1]):
        add(i, repb * c, t)
    calls_per_iter = collections.Counter()
    for t in sched1:
        calls_per_iter[t] += repb * s1_rep
    for t in sched4:
        calls_per_iter[t] += repb * 1 / len(sched4)
    for t in sched16:
        calls_per_iter[t] += repb * s16_rep / len(sched16)
    for name in sorted(s for s in syms if s.startswith("ffv1_t")):
        b = br(name)
        assert [kind(i) for i in b] == ["RET"], name
        add(b[0], calls_per_iter[name], 1)
    cc = br("ffv1_c")
    ncond = sum(1 for i in cc if kind(i) == "COND")
    assert [kind(i) for i in cc] == ["COND"] * ncond + ["RET"]
    for i in cc:
        add(i, 1, 1)

    def wavg(pred):
        c = sum(s[2] for s in sites if pred(s[1]))
        ct = sum(s[2] * s[3] for s in sites if pred(s[1]))
        return ct / c if c else None

    exp = {
        "binary": os.path.realpath(binary), "inode": os.stat(binary).st_ino,
        "region_va": [lo, hi], "region_off": [va_to_off(segs, lo), va_to_off(segs, hi)],
        "design": {"REPB": repb, "site_K1_calls": s1_rep, "site_K16_calls": s16_rep, "blocks": nblk,
                   "conds": ncond, "K": [len(set(sched1)), len(set(sched4)), len(set(sched16))],
                   "sched4": dict(collections.Counter(sched4)), "sched16": dict(collections.Counter(sched16))},
        "lines": sorted(lines),
        "footprint_lines": len(lines),
        "branches": {va_to_off(segs, va): (t, c, k) for va, t, c, k in sites},
        "unique_taken_branches": len(sites),
        "taken_per_iteration": sum(s[2] for s in sites),
        "by_type": dict(collections.Counter(s[1] for s in sites)),
        "wavg_targets_all": wavg(lambda t: True),
        "wavg_targets_noret": wavg(lambda t: t != "RET"),
        "wavg_targets_indirect": wavg(lambda t: t in ("IND", "IND_CALL")),
    }
    return exp


def load_tables(d, exp):
    objs = [ln.rstrip("\n").split("\t") for ln in open(os.path.join(d, "objects.tsv"))][1:]
    ids = [int(o[0]) for o in objs if o[1] == "file" and os.path.realpath(o[2]) == exp["binary"]
           and int(o[3]) == exp["inode"]]
    if len(ids) != 1:
        sys.exit(f"check_v1: binary {exp['binary']} (inode {exp['inode']}) found {len(ids)} times in objects.tsv")
    oid = ids[0]
    lo, hi = exp["region_off"]
    lines = set()
    for ln in open(os.path.join(d, "lines.tsv")):
        p = ln.split("\t")
        if p[0] == "obj" or int(p[0]) != oid:
            continue
        off = int(p[1], 16)
        if lo <= off < hi or lo <= off + 63 < hi:
            lines.add(off)
    br = collections.defaultdict(lambda: {"C": 0, "T": set(), "types": set()})
    for ln in open(os.path.join(d, "edges.tsv")):
        p = ln.rstrip("\n").split("\t")
        if p[0] == "from_obj" or int(p[0]) != oid or p[4] not in NEAR:
            continue
        off = int(p[1], 16)
        if not lo <= off < hi:
            continue
        b = br[off]
        b["C"] += int(p[5])
        b["T"].add((p[2], p[3]))
        b["types"].add(p[4])
    return lines, br


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    ap.add_argument("--tables", help="directory holding objects.tsv, lines.tsv, edges.tsv")
    ap.add_argument("--json")
    ap.add_argument("--expected-only", action="store_true")
    a = ap.parse_args()
    exp = derive_expected(a.binary)
    print(f"V1 expected (from design + {exp['binary']}): footprint {exp['footprint_lines']} lines "
          f"({64 * exp['footprint_lines']} B), unique taken branches {exp['unique_taken_branches']} "
          f"{exp['by_type']}, taken/iter {exp['taken_per_iteration']:g}, wavg all {exp['wavg_targets_all']:.6f} "
          f"noret {exp['wavg_targets_noret']:.6f} indirect {exp['wavg_targets_indirect']:.6f}; design {exp['design']}")
    if a.expected_only:
        return 0
    if not a.tables:
        ap.error("--tables is required unless --expected-only")
    lines, br = load_tables(a.tables, exp)
    exp_lines = set(exp["lines"])
    eb = exp["branches"]

    def wavg(pred):
        c = sum(b["C"] for o, b in br.items() if pred(next(iter(b["types"]))))
        ct = sum(b["C"] * len(b["T"]) for o, b in br.items() if pred(next(iter(b["types"]))))
        return ct / c if c else None

    obs = {"footprint_lines": len(lines), "unique_taken_branches": len(br),
           "wavg_targets_all": wavg(lambda t: True), "wavg_targets_noret": wavg(lambda t: t != "RET"),
           "wavg_targets_indirect": wavg(lambda t: t in ("IND", "IND_CALL"))}
    missing_br = sorted(set(eb) - set(br))
    extra_br = sorted(set(br) - set(eb))
    type_mismatch = sorted(o for o in set(eb) & set(br) if br[o]["types"] != {eb[o][0]})
    t_mismatch = sorted(o for o in set(eb) & set(br) if len(br[o]["T"]) != eb[o][2])
    rel = lambda o, e: abs(o - e) / e if (o is not None and e) else None
    checks = {
        "footprint_within_2_lines": abs(len(lines) - len(exp_lines)) <= 2,
        "unique_taken_branches_exact": len(br) == exp["unique_taken_branches"],
    }
    for k in ("wavg_targets_all", "wavg_targets_noret", "wavg_targets_indirect"):
        r = rel(obs[k], exp[k])
        checks[f"{k}_within_1pct"] = r is not None and r <= 0.01
    res = {
        "gate": "V1", "pass": all(checks.values()), "checks": checks,
        "expected": {k: exp[k] for k in ("footprint_lines", "unique_taken_branches", "by_type", "wavg_targets_all",
                                          "wavg_targets_noret", "wavg_targets_indirect", "taken_per_iteration", "design")},
        "observed": obs,
        "rel_err": {k: rel(obs[k], exp[k]) for k in ("wavg_targets_all", "wavg_targets_noret", "wavg_targets_indirect")},
        "lines_missing": [hex(x) for x in sorted(exp_lines - lines)][:50],
        "lines_extra": [hex(x) for x in sorted(lines - exp_lines)][:50],
        "branches_missing": [hex(x) for x in missing_br][:50],
        "branches_extra": [hex(x) for x in extra_br][:50],
        "branches_type_mismatch": [hex(x) for x in type_mismatch][:50],
        "branches_target_count_mismatch": [(hex(x), len(br[x]["T"]), eb[x][2]) for x in t_mismatch][:50],
        "min_sampled_entries_per_site": min((b["C"] for b in br.values()), default=0),
    }
    if a.json:
        json.dump(res, open(a.json, "w"), indent=1)
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    print(f"V1 observed: footprint {obs['footprint_lines']} lines, unique taken {obs['unique_taken_branches']}, "
          + ", ".join(f"{k[13:]} {obs[k]:.6f} (err {100 * res['rel_err'][k]:.3f} %)" if obs[k] is not None else f"{k} n/a"
                      for k in ("wavg_targets_all", "wavg_targets_noret", "wavg_targets_indirect"))
          + f"; lines missing/extra {len(exp_lines - lines)}/{len(lines - exp_lines)}, branches missing/extra "
            f"{len(missing_br)}/{len(extra_br)}, type mismatches {len(type_mismatch)}, T mismatches {len(t_mismatch)}, "
            f"min sampled entries per site {res['min_sampled_entries_per_site']}")
    print(f"V1 {'PASS' if res['pass'] else 'FAIL'}")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
