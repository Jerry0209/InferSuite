#!/usr/bin/env python3
"""neo4j_client.py — closed-loop load generator for the realistic Neo4j workload (LiveJournal
follow graph), run on the HOUSEKEEPING cores while the server is profiled inside the fence.

Mix (modelled on Renaissance neo4j-analytics' short / long / mutator structure, applied to a
social graph):
  short  (90 %)  1-hop degree of a random user (40 % of shorts);
                 2-hop friends-of-friends count of a random user, bounded to 5 000 paths (60 %)
  long   ( 3 %)  bounded shortest path (<= 4 hops) between two random users (50 %);
                 3-hop reach count of a random user, bounded to 20 000 paths (50 %)
  mut    ( 7 %)  add a FOLLOWS edge between two random users / delete one edge of a random user
The mix was weighted toward traversals after the first smoke pass (2026-09-20): with the cheap
1-hop/2-hop mix the Python client cost 2.6x the server CPU per request and saturated the
housekeeping cores while the server sat at 2.7 of 8 cores.

Each process opens `--sessions` bolt sessions in threads and loops with no think time
(closed loop, YCSB style). Every second each process appends a line per query class to
<out>.p<N>.csv: t, class, count, p50_ms, p95_ms, p99_ms, errors. `--summarize <out>` merges the
per-process files into <out>.receipt.json (throughput and latency over the whole run and over
the last `--window` seconds, the capture window).

    neo4j_client.py --nodes 4847571 --duration 420 --procs 6 --sessions 4 --out /path/client
    neo4j_client.py --summarize /path/client --window 180
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import random
import signal
import sys
import threading
import time

Q_SHORT_DEG = "MATCH (u:User {id:$a})-[:FOLLOWS]->(v) RETURN count(v) AS c"
Q_SHORT_FOF = ("MATCH (u:User {id:$a})-[:FOLLOWS]->()-[:FOLLOWS]->(w) "
               "WITH w LIMIT 5000 RETURN count(DISTINCT w) AS c")
Q_LONG_SP = ("MATCH (a:User {id:$a}), (b:User {id:$b}) "
             "MATCH p = shortestPath((a)-[:FOLLOWS*..4]->(b)) RETURN length(p) AS l")
Q_LONG_REACH = ("MATCH (u:User {id:$a})-[:FOLLOWS*3]->(w) "
                "WITH w LIMIT 20000 RETURN count(DISTINCT w) AS c")
Q_MUT_ADD = "MATCH (a:User {id:$a}), (b:User {id:$b}) MERGE (a)-[:FOLLOWS]->(b)"
Q_MUT_DEL = "MATCH (a:User {id:$a})-[r:FOLLOWS]->() WITH r LIMIT 1 DELETE r"
LONG_TIMEOUT_S = 30.0


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def worker(args, pidx, tidx, stats, lock, stop):
    from neo4j import GraphDatabase, Query
    rng = random.Random(args.seed * 1000 + pidx * 100 + tidx)
    drv = GraphDatabase.driver(args.uri, max_connection_pool_size=8)
    with drv.session(database=args.database) as s:
        while not stop.is_set():
            r = rng.random()
            if r < args.p_short:
                cls = "short"
                if rng.random() < 0.40:
                    q, p = Q_SHORT_DEG, {"a": rng.randrange(args.nodes)}
                else:
                    q, p = Q_SHORT_FOF, {"a": rng.randrange(args.nodes)}
                to = None
            elif r < args.p_short + args.p_long:
                cls = "long"
                if rng.random() < 0.5:
                    q, p = Q_LONG_SP, {"a": rng.randrange(args.nodes), "b": rng.randrange(args.nodes)}
                else:
                    q, p = Q_LONG_REACH, {"a": rng.randrange(args.nodes)}
                to = LONG_TIMEOUT_S
            else:
                cls = "mut"
                if rng.random() < 0.5:
                    q, p = Q_MUT_ADD, {"a": rng.randrange(args.nodes), "b": rng.randrange(args.nodes)}
                else:
                    q, p = Q_MUT_DEL, {"a": rng.randrange(args.nodes)}
                to = None
            t0 = time.perf_counter()
            ok = 1
            try:
                # auto-commit statement: ONE round trip (RUN+PULL pipelined) instead of the
                # three of an explicit transaction (BEGIN / RUN / COMMIT), which is what a real
                # single-statement client does and what keeps the protocol overhead from
                # dominating both the client's and the server's CPU per request
                s.run(Query(q, timeout=to), **p).consume()
            except Exception:
                ok = 0
            dt = (time.perf_counter() - t0) * 1000.0
            with lock:
                stats[cls][0] += 1
                stats[cls][1].append(dt)
                stats[cls][2] += (1 - ok)
    drv.close()


def run_process(args, pidx):
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    lock = threading.Lock()
    stats = {c: [0, [], 0] for c in ("short", "long", "mut")}
    threads = [threading.Thread(target=worker, args=(args, pidx, t, stats, lock, stop), daemon=True)
               for t in range(args.sessions)]
    for t in threads:
        t.start()
    t_end = time.time() + args.duration
    with open(f"{args.out}.p{pidx}.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t", "class", "count", "p50_ms", "p95_ms", "p99_ms", "errors"])
        next_t = time.time() + 1.0
        while not stop.is_set() and time.time() < t_end:
            time.sleep(max(0.0, next_t - time.time()))
            now = time.time(); next_t += 1.0
            with lock:
                snap = {c: (v[0], v[1], v[2]) for c, v in stats.items()}
                for v in stats.values():
                    v[0] = 0; v[1] = []; v[2] = 0
            for c, (n, lat, err) in snap.items():
                if n:
                    w.writerow([f"{now:.3f}", c, n, f"{pct(lat, .5):.2f}", f"{pct(lat, .95):.2f}",
                                f"{pct(lat, .99):.2f}", err])
            fh.flush()
    stop.set()
    for t in threads:
        t.join(timeout=LONG_TIMEOUT_S + 5)


def summarize(out, window):
    rows = []
    for f in sorted(glob.glob(f"{out}.p*.csv")):
        rows += list(csv.DictReader(open(f)))
    if not rows:
        json.dump({"error": "no client rows"}, open(f"{out}.receipt.json", "w"))
        return
    t1 = max(float(r["t"]) for r in rows)
    def agg(sel):
        by = {}
        for r in sel:
            c = r["class"]; n = int(r["count"])
            d = by.setdefault(c, {"count": 0, "errors": 0, "p95_w": [], "p99_w": []})
            d["count"] += n; d["errors"] += int(r["errors"])
            d["p95_w"].append((float(r["p95_ms"]), n)); d["p99_w"].append((float(r["p99_ms"]), n))
        span = (max(float(r["t"]) for r in sel) - min(float(r["t"]) for r in sel) + 1.0) if sel else 1.0
        res = {}
        for c, d in by.items():
            tot = sum(n for _v, n in d["p95_w"]) or 1
            res[c] = {"ops": d["count"], "ops_per_s": round(d["count"] / span, 1), "errors": d["errors"],
                      "p95_ms_count_weighted": round(sum(v * n for v, n in d["p95_w"]) / tot, 2),
                      "p99_ms_count_weighted": round(sum(v * n for v, n in d["p99_w"]) / tot, 2)}
        res["all"] = {"ops_per_s": round(sum(int(r["count"]) for r in sel) / span, 1), "span_s": round(span, 1)}
        return res
    last = [r for r in rows if float(r["t"]) >= t1 - window]
    json.dump({"whole_run": agg(rows), f"last_{int(window)}s": agg(last), "processes": len(glob.glob(f"{out}.p*.csv"))},
              open(f"{out}.receipt.json", "w"), indent=1)
    print(json.dumps(json.load(open(f"{out}.receipt.json"))[f"last_{int(window)}s"]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uri", default="bolt://127.0.0.1:7687")
    ap.add_argument("--database", default="livejournal")
    ap.add_argument("--nodes", type=int, default=4847571, help="ids are drawn uniformly from [0, nodes)")
    ap.add_argument("--duration", type=float, default=300)
    ap.add_argument("--procs", type=int, default=6)
    ap.add_argument("--sessions", type=int, default=4)
    ap.add_argument("--p-short", type=float, default=0.90)
    ap.add_argument("--p-long", type=float, default=0.03)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", required=True, help="output prefix")
    ap.add_argument("--summarize", action="store_true")
    ap.add_argument("--window", type=float, default=180)
    a = ap.parse_args()
    if a.summarize:
        summarize(a.out, a.window); return 0
    import multiprocessing as mp
    procs = [mp.Process(target=run_process, args=(a, i)) for i in range(a.procs)]
    for p in procs:
        p.start()
    def fwd(sig, _f):
        for p in procs:
            if p.is_alive():
                os.kill(p.pid, signal.SIGTERM)
    signal.signal(signal.SIGTERM, fwd); signal.signal(signal.SIGINT, fwd)
    for p in procs:
        p.join()
    summarize(a.out, a.window)
    return 0


if __name__ == "__main__":
    sys.exit(main())
