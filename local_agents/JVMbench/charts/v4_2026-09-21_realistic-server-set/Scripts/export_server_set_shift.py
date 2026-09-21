#!/usr/bin/env python3
"""export_server_set_shift.py — two small CSVs that make the study replottable by anyone,
from runtime_votes.csv alone (no access to the raw captures needed).

  workload_index.csv     one row per profiled workload: which family it belongs to, which side
                         of the three-violin comparison it sits on (SPEC / Server / Agentic),
                         whether it is in the SUITE server set, the REALISTIC server set, or
                         both, which workload it pairs with in the toy-vs-realistic figure, and
                         a one-line note on its dataset. This is the mapping a replotter needs:
                         runtime_votes.csv gives the values, this says how to group them.

  server_set_shift.csv   per metric, the Server median under the suite set and under the
                         realistic set, their ratio, and the SPEC and agentic medians for scale
                         — the table behind local_agents/RealData/README.md §7.

    PY=~/miniforge3/envs/infersuite-full/bin/python3
    $PY local_agents/kit/plot/export_server_set_shift.py [--votes FILE] [--out DIR]
"""
from __future__ import annotations

import argparse
import csv
import os
import statistics as st
import sys

REPO = os.path.expanduser("~/InferSuite")

# suite benchmark -> its realistic re-characterisation (local_agents/RealData/README.md)
PAIRS = {
    "neo4j-analytics": "neo4j-livejournal",
    "cassandra": "cassandra-ycsb20m",
    "kafka": "kafka-20g",
    "page-rank": "pagerank-livejournal",
    "naive-bayes": "naivebayes-rcv1",
    "video_transcode": "video-4k",
}
DATASETS = {
    "feedsim": "synthetic ranking graph, graph_scale=21, 3.5 GB resident (generated at start-up)",
    "video_transcode": "six 51-frame 1080p shots cut from Xiph in_to_tree / park_joy, 908 MB",
    "video-4k": "two Netflix 4K sequences from Xiph (Boat 301 frames, FoodMarket 601), 11.1 GB",
    "finagle-http": "none by design: 12 000 small HTTP requests per iteration, in-process client",
    "finagle-chirper": "5 000 simulated users, tweet text from a 486 KB CSV, in-process client",
    "page-rank": "SNAP web-BerkStan, 7.6 M edges (20 MB zipped)",
    "pagerank-livejournal": "SNAP soc-LiveJournal1, 69 M edges (1.03 GB edge list)",
    "naive-bayes": "Spark's 100-row sample_libsvm_data.txt (105 KB) replicated 8 000x",
    "naivebayes-rcv1": "RCV1-v2 Reuters corpus, 518 571 documents x 47 236 features (777 MB)",
    "neo4j-analytics": "embedded Neo4j movie database, 70 MB of JSON, in-process queries",
    "neo4j-livejournal": "SNAP soc-LiveJournal1 in a standalone Neo4j 5.26 server, 2.9 GB store",
    "cassandra": "DaCapo YCSB workload-default: 10 000 rows x 1 KB, in-process client",
    "cassandra-ycsb20m": "YCSB CoreWorkload A on 20 M rows x 1 KB, 21 GB store, external client",
    "kafka": "DaCapo Trogdor produce bench: 1 M messages into an empty broker, in-process",
    "kafka-20g": "Kafka 4.3 broker, 21 GB retention window, 120 MB/s ingest, 6 backlog consumers",
    "tomcat": "Tomcat's bundled sample web applications, 14 MB, in-process client",
}
SIDE = {"spec26": "SPEC", "agentic36": "Agentic",
        "dcperf": "Server", "renaissance": "Server", "dacapo": "Server", "realdata": "Server"}
DISPLAY = ["IPC", "Branch MPKI", "Branch-direction MPKI", "BTB MPKI (BAClears)",
           "L1I MPKI (code-read)", "uop-cache (DSB) MPKI", "DSB coverage (%)", "L1D-load MPKI",
           "L2-load MPKI", "LLC MPKI", "DRAM read (GB/s)", "Context switches (/CPU-s)"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--votes", default=f"{REPO}/local_agents/JVMbench/data/l3_study/runtime_votes.csv")
    ap.add_argument("--out", default=f"{REPO}/local_agents/RealData/data/l3_study")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rows = list(csv.DictReader(open(a.votes)))
    if not rows:
        print("no rows in", a.votes, file=sys.stderr)
        return 1
    rev = {v: k for k, v in PAIRS.items()}

    # ---- workload_index.csv
    seen = {}
    for r in rows:
        seen.setdefault((r["family"], r["subgroup"], r["workload"]), 0)
        seen[(r["family"], r["subgroup"], r["workload"])] += 1
    with open(f"{a.out}/workload_index.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["workload", "family", "subgroup", "side", "in_suite_server_set",
                    "in_realistic_server_set", "pairs_with", "pair_role", "dataset"])
        for (fam, sub, wl), _n in sorted(seen.items()):
            side = SIDE.get(fam, "")
            suite_set = side == "Server" and fam != "realdata"
            real_set = side == "Server" and (fam == "realdata" and wl in PAIRS.values()
                                             or fam != "realdata" and wl not in PAIRS)
            pair = PAIRS.get(wl) or rev.get(wl) or ""
            role = "suite (toy)" if wl in PAIRS else ("realistic" if wl in rev else "")
            w.writerow([wl, fam, sub, side, int(suite_set), int(real_set), pair, role,
                        DATASETS.get(wl, "")])
    print(f"wrote {a.out}/workload_index.csv: {len(seen)} workloads")

    # ---- server_set_shift.csv
    by = {}
    for r in rows:
        by.setdefault(r["metric"], {}).setdefault(r["family"], []).append((r["workload"], float(r["value"])))
    with open(f"{a.out}/server_set_shift.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "server_suite_median", "server_realistic_median", "ratio_realistic_over_suite",
                    "agentic_median", "spec_median", "n_server", "n_agentic", "n_spec"])
        for m in DISPLAY:
            d = by.get(m, {})
            suite = [v for f in ("dcperf", "renaissance", "dacapo") for _w, v in d.get(f, [])]
            real = [v for f in ("dcperf", "renaissance", "dacapo") for _w, v in d.get(f, []) if _w not in PAIRS] \
                + [v for _w, v in d.get("realdata", []) if _w in PAIRS.values()]
            ag = [v for _w, v in d.get("agentic36", [])]
            sp = [v for _w, v in d.get("spec26", [])]
            if not (suite and real and ag and sp):
                continue
            a_, b_ = st.median(suite), st.median(real)
            w.writerow([m, f"{a_:.6g}", f"{b_:.6g}", f"{b_ / a_:.4f}" if a_ else "",
                        f"{st.median(ag):.6g}", f"{st.median(sp):.6g}", len(real), len(ag), len(sp)])
    print(f"wrote {a.out}/server_set_shift.csv: {len(DISPLAY)} metrics")
    return 0


if __name__ == "__main__":
    sys.exit(main())
