#!/usr/bin/env python3
"""taskstats_listen.py — exit-time process accounting via the kernel's taskstats netlink
interface: every process leaves a receipt when it dies.

Why this exists: the 2 Hz per-PID sampler cannot see processes shorter than its sampling
interval, and faster polling was measured to buy coverage but not accuracy (2 Hz -> 10 Hz:
jq coverage 12% -> 25%, error 7.7 pt -> 7.7 pt). The exact fix is not faster photography but
exit-time accounting: on every task exit the kernel emits that task's precise lifetime CPU
(ac_utime/ac_stime in microseconds) plus comm/pid/ppid/uid/btime/etime. This listener banks
those receipts.

The registration is per-CPU-mask and MACHINE-WIDE (genl TASKSTATS, REGISTER_CPUMASK): the
stream contains every exit on the machine, not just the container's. Fence attribution
happens OFFLINE: each receipt carries ppid, so the parent graph reconstructs after the fact
and order of death does not matter. Consumers must lineage-filter to the tool cgroup's pid
set (cmdlog/pidcpu pids as roots); the raw file never leaves the run dir.

Needs CAP_NET_ADMIN on this kernel — run under sudo. `--probe` tests capability and exits.

Output TSV, one row per receipt:
  epoch \t kind \t pid \t ppid \t uid \t comm \t utime_us \t stime_us \t etime_us \t btime
kind G = whole-process aggregate (AGGR_TGID; kernel sums all threads; USE THESE),
kind P = single task exit (AGGR_PID; per-thread, double-counts with G; kept for debugging),
kind LOST = the kernel dropped receipts because our socket buffer was full (see below); the
  4th column carries the running count of drop events. A run whose file contains LOST rows is
  INCOMPLETE by exactly an unknown amount — treat its receipt-derived numbers as lower bounds.

RECEIPT LOSS (defect found 2026-08-20, 23 of 300 replays affected). netlink delivers into a
fixed-size kernel-side socket buffer. A `go build ./...` forks thousands of short-lived
children per second, and if we do not drain fast enough the kernel DROPS receipts (they are
never resent) and reports ENOBUFS on the next read. The original loop caught only
socket.timeout, so ENOBUFS escaped and killed the listener mid-episode — prometheus-9248 banked
11,279 receipts and then recorded nothing for the rest of the run (coverage 52%). Three
mitigations, in order of importance: (1) a 64 MB receive buffer via SO_RCVBUFFORCE (root
bypasses net.core.rmem_max); (2) ENOBUFS is caught, counted and written as a LOST row — loss
becomes data instead of silence; (3) the receive loop only appends raw buffers to a queue, a
second thread decodes them, so the socket is drained as fast as the kernel can fill it.
"""
import collections
import errno
import os
import socket
import struct
import sys
import threading
import time

RCVBUF_BYTES = int(os.environ.get("TASKSTATS_RCVBUF", 64 << 20))  # shrink it to test the loss path
SO_RCVBUFFORCE = 33      # linux/socket.h; python's socket module does not export it
LOST = object()          # queue sentinel: the kernel dropped receipts (ENOBUFS)

NETLINK_GENERIC = 16
GENL_ID_CTRL = 0x10
CTRL_CMD_GETFAMILY = 3
CTRL_ATTR_FAMILY_ID = 1
CTRL_ATTR_FAMILY_NAME = 2
TASKSTATS_CMD_GET = 1
ATTR_REGISTER_CPUMASK = 3
ATTR_DEREGISTER_CPUMASK = 4
T_STATS, T_AGGR_PID, T_AGGR_TGID = 3, 4, 5
NLMSG_ERROR = 2

# struct taskstats fixed prefix (stable since v1; later versions only append):
#   comm at 80 (32 bytes), uid at 120, gid 124, pid 128, ppid 132, btime 136,
#   etime 144, utime 152, stime 160 — utime/stime/etime in MICROSECONDS.
O_COMM, O_UID, O_PID, O_PPID, O_BTIME, O_ETIME, O_UTIME, O_STIME = \
    80, 120, 128, 132, 136, 144, 152, 160


def nlattr(t, payload):
    ln = 4 + len(payload)
    return struct.pack("=HH", ln, t) + payload + b"\0" * ((4 - ln % 4) % 4)


def genlmsg(family, cmd, attrs, seq):
    payload = struct.pack("=BBH", cmd, 1, 0) + attrs
    return struct.pack("=IHHII", 16 + len(payload), family, 1, seq, 0) + payload


def parse_attrs(buf):
    out, off = [], 0
    while off + 4 <= len(buf):
        ln, t = struct.unpack_from("=HH", buf, off)
        if ln < 4:
            break
        out.append((t, buf[off + 4:off + ln]))
        off += (ln + 3) & ~3
    return out


def resolve_family(sk):
    sk.send(genlmsg(GENL_ID_CTRL, CTRL_CMD_GETFAMILY,
                    nlattr(CTRL_ATTR_FAMILY_NAME, b"TASKSTATS\0"), 1))
    buf = sk.recv(65536)
    for t, v in parse_attrs(buf[20:]):
        if t == CTRL_ATTR_FAMILY_ID:
            return struct.unpack("=H", v[:2])[0]
    raise RuntimeError("TASKSTATS genl family not found (kernel support missing?)")


def stats_row(kind, st, now):
    if len(st) < O_STIME + 8:
        return None
    comm = st[O_COMM:O_COMM + 32].split(b"\0")[0].decode(errors="replace")
    uid, = struct.unpack_from("=I", st, O_UID)
    pid, = struct.unpack_from("=I", st, O_PID)
    ppid, = struct.unpack_from("=I", st, O_PPID)
    btime, = struct.unpack_from("=I", st, O_BTIME)
    etime, = struct.unpack_from("=Q", st, O_ETIME)
    utime, = struct.unpack_from("=Q", st, O_UTIME)
    stime, = struct.unpack_from("=Q", st, O_STIME)
    return f"{now:.6f}\t{kind}\t{pid}\t{ppid}\t{uid}\t{comm}\t{utime}\t{stime}\t{etime}\t{btime}\n"


def main():
    probe = "--probe" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--probe"]
    if not probe and len(args) < 2:
        sys.exit("usage: taskstats_listen.py <out.tsv> <stopfile> [cpulist] | --probe")
    cpulist = (args[2] if len(args) > 2 else
               open("/sys/devices/system/cpu/online").read().strip())

    sk = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, NETLINK_GENERIC)
    # (1) big receive buffer BEFORE binding/registering, so no burst is lost during startup.
    # SO_RCVBUFFORCE needs CAP_NET_ADMIN (we run under sudo) and ignores net.core.rmem_max.
    try:
        sk.setsockopt(socket.SOL_SOCKET, SO_RCVBUFFORCE, RCVBUF_BYTES)
    except OSError:                      # no CAP_NET_ADMIN: fall back, capped by rmem_max
        sk.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RCVBUF_BYTES)
    got = sk.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)  # kernel reports 2x the request
    print(f"taskstats: rcvbuf {got // (1 << 20)} MB", file=sys.stderr)
    sk.bind((0, 0))
    fam = resolve_family(sk)
    sk.send(genlmsg(fam, TASKSTATS_CMD_GET,
                    nlattr(ATTR_REGISTER_CPUMASK, cpulist.encode() + b"\0"), 2))
    sk.settimeout(1.0)

    if probe:
        # capability check: registration errors arrive as NLMSG_ERROR; success is receipts
        # flowing once anything exits. Spawn short children to force events.
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if os.fork() == 0:
                os._exit(0)
            os.wait()
            try:
                buf = sk.recv(65536)
            except socket.timeout:
                continue
            t = struct.unpack_from("=H", buf, 4)[0]
            if t == NLMSG_ERROR:
                err = struct.unpack_from("=i", buf, 16)[0]
                sys.exit(f"probe: NLMSG_ERROR errno={err} (need sudo?)")
            print("probe: ok (receipts flowing)")
            return
        sys.exit("probe: no events within 3s")

    out, stopfile = args[0], args[1]
    fh = open(out, "a", buffering=1)
    # the file must belong to the invoking user, not root, or the kits can't manage it
    if "SUDO_UID" in os.environ:
        os.chown(out, int(os.environ["SUDO_UID"]), int(os.environ.get("SUDO_GID", -1)))
    # (3) receive and decode are separate: the receiving thread does nothing but move bytes out
    # of the kernel buffer, so a fork storm cannot outrun us while we are parsing structs.
    q = collections.deque()                 # (epoch, raw buffer) — deque ops are atomic
    st = {"n": 0, "lost": 0, "run": True}

    def decode():
        while st["run"] or q:
            try:
                now, buf = q.popleft()
            except IndexError:
                time.sleep(0.002)
                continue
            if buf is LOST:                 # (2) drop event, written in stream order
                fh.write(f"{now:.6f}\tLOST\t{st['lost']}\t0\t0\t-\t0\t0\t0\t0\n")
                continue
            off = 0
            while off + 16 <= len(buf):
                ln, t = struct.unpack_from("=IH", buf, off)
                if ln < 16:
                    break
                if t == fam:
                    for at, av in parse_attrs(buf[off + 20:off + ln]):
                        if at in (T_AGGR_PID, T_AGGR_TGID):
                            kind = "G" if at == T_AGGR_TGID else "P"
                            for it, iv in parse_attrs(av):
                                if it == T_STATS:
                                    row = stats_row(kind, iv, now)
                                    if row:
                                        fh.write(row)
                                        st["n"] += 1
                off += (ln + 3) & ~3

    th = threading.Thread(target=decode, daemon=True)
    th.start()
    try:
        while os.path.exists(stopfile):
            try:
                buf = sk.recv(1 << 20)
            except socket.timeout:
                continue
            except OSError as e:
                if e.errno != errno.ENOBUFS:
                    raise
                # the kernel dropped an unknown number of receipts; the socket stays usable.
                # Record it and KEEP GOING — dying here is what cost us 23 episodes.
                st["lost"] += 1
                q.append((time.time(), LOST))
                continue
            q.append((time.time(), buf))
    finally:
        st["run"] = False
        th.join(timeout=15)
        try:
            sk.send(genlmsg(fam, TASKSTATS_CMD_GET,
                            nlattr(ATTR_DEREGISTER_CPUMASK, cpulist.encode() + b"\0"), 3))
        except OSError:
            pass
        fh.close()
        print(f"taskstats: {st['n']} receipts banked, {st['lost']} drop events", file=sys.stderr)


if __name__ == "__main__":
    main()
