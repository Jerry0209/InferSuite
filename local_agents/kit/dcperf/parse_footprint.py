#!/usr/bin/env python3
"""parse_footprint.py — summarise measure_footprint.sh output: cgroup peak, number of GCs,
median and max LIVE heap after GC (second half of the run), and the heap cap the collector chose.
    python3 local_agents/kit/dcperf/parse_footprint.py <outdir>
"""
import glob, os, re, statistics as st
import sys
OUT=sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
pat=re.compile(r'(\d+)M->(\d+)M\((\d+)M\)')
print(f"{'benchmark':24s} {'cgroup peak':>12s} {'GCs':>5s} {'live after GC: median':>22s} {'max':>8s} {'heap cap':>9s}")
for mem in sorted(glob.glob(f'{OUT}/*.mem')):
    name=os.path.basename(mem)[:-4]
    kv=dict(x.split('=') for x in open(mem).read().split())
    peak=int(kv.get('peak_bytes') or 0)/2**30
    gl=f'{OUT}/gc-{name}.log'
    if os.path.exists(gl):
        after=[int(m.group(2)) for m in pat.finditer(open(gl,errors='replace').read())]
        caps=[int(m.group(3)) for m in pat.finditer(open(gl,errors='replace').read())]
        if after:
            half=after[len(after)//2:]
            print(f"{name:24s} {peak:9.2f} GB {len(after):5d} {st.median(half)/1024:19.2f} GB {max(after)/1024:5.2f} GB {max(caps)/1024:6.2f} GB")
            continue
    print(f"{name:24s} {peak:9.2f} GB {'-':>5s} {'(no GC log: native process, RSS = peak)':>22s}")
