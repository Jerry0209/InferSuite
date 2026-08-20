#!/usr/bin/env python3
"""procconn_listen.py — kernel proc connector: fork / exec / exit events as they happen.

Why this exists (2026-08-20). The taskstats receipts answer "who burned how much CPU", and
that is all the time-weighted matrix needs. They cannot answer two questions the COUNT-weighted
column depends on:

  1. Is this receipt a process or a THREAD? taskstats emits one receipt per *task*, and a
     thread is a task. The receipt carries pid/ppid but not tgid, so `typeid_cpu_matrix.py`
     falls back to guessing from the name shape (THREADISH): tokio-runtime-w, GC Thread#0,
     ThreadPoolForeg... That heuristic was audited (201 of 39,186 confirmed processes wrongly
     dropped, 0.5%) but the opposite direction — threads counted as commands — is unmeasurable
     from receipts alone.
  2. How many COMMANDS ran? A process that execs leaves one receipt naming its final program,
     so receipts count processes, not exec() calls.

The proc connector answers both from the kernel directly:
  FORK gives parent_pid/parent_tgid/child_pid/child_tgid — `child_pid != child_tgid` IS the
       kernel's definition of a thread, no name guessing;
  EXEC gives one event per exec() — the literal command count;
  EXIT closes the lineage.

Machine-wide, like taskstats; fence attribution stays an offline lineage filter. Same loss
discipline as taskstats_listen.py: 64 MB receive buffer, ENOBUFS is recorded as a LOST row and
never kills the listener, receive and decode run in separate threads.

Needs CAP_NET_ADMIN (run under sudo). `--probe` tests capability and exits.

Output TSV, one row per event:
  epoch \t kind \t pid \t tgid \t ppid \t ptgid
  kind FORK  — pid/tgid = child, ppid/ptgid = parent.  pid != tgid means a THREAD was created.
  kind EXEC  — pid/tgid = the process that replaced its image; ppid/ptgid = 0.
  kind EXIT  — pid/tgid of the dying task; ppid = exit_code.
  kind LOST  — kernel dropped events (buffer full); pid = running count of drop events.
"""
import collections
import errno
import os
import socket
import struct
import sys
import threading
import time

NETLINK_CONNECTOR = 11
CN_IDX_PROC = 1
CN_VAL_PROC = 1
PROC_CN_MCAST_LISTEN = 1
PROC_CN_MCAST_IGNORE = 2
# enum proc_cn_event
EV_FORK, EV_EXEC, EV_EXIT = 0x00000001, 0x00000002, 0x80000000
# struct proc_event: what u32 @0, cpu u32 @4, timestamp_ns u64 @8, event_data @16
O_EVENT = 16
RCVBUF_BYTES = int(os.environ.get("PROCCONN_RCVBUF", 64 << 20))
SO_RCVBUFFORCE = 33
LOST = object()


def mcast_msg(op, seq):
    """nlmsghdr + cn_msg + u32 op — subscribe to (CN_IDX_PROC, CN_VAL_PROC)."""
    data = struct.pack("=I", op)
    cn = struct.pack("=IIIIHH", CN_IDX_PROC, CN_VAL_PROC, seq, 0, len(data), 0) + data
    return struct.pack("=IHHII", 16 + len(cn), 0x03, 0, seq, os.getpid()) + cn  # NLMSG_DONE


def decode_events(buf, now, out):
    """Append TSV rows for every proc_event in one datagram."""
    off = 0
    while off + 16 <= len(buf):
        ln, = struct.unpack_from("=I", buf, off)
        if ln < 16 or off + ln > len(buf):
            break
        body = buf[off + 16:off + ln]          # skip nlmsghdr
        if len(body) >= 20 + O_EVENT:
            what, = struct.unpack_from("=I", body, 20)          # cn_msg header is 20 bytes
            ev = body[20 + O_EVENT:]
            if what == EV_FORK and len(ev) >= 16:
                ppid, ptgid, pid, tgid = struct.unpack_from("=IIII", ev, 0)
                out.append(f"{now:.6f}\tFORK\t{pid}\t{tgid}\t{ppid}\t{ptgid}\n")
            elif what == EV_EXEC and len(ev) >= 8:
                pid, tgid = struct.unpack_from("=II", ev, 0)
                out.append(f"{now:.6f}\tEXEC\t{pid}\t{tgid}\t0\t0\n")
            elif what == EV_EXIT and len(ev) >= 12:
                pid, tgid, code = struct.unpack_from("=III", ev, 0)
                out.append(f"{now:.6f}\tEXIT\t{pid}\t{tgid}\t{code}\t0\n")
        off += (ln + 3) & ~3


def main():
    probe = "--probe" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--probe"]
    if not probe and len(args) < 2:
        sys.exit("usage: procconn_listen.py <out.tsv> <stopfile> | --probe")

    sk = socket.socket(socket.AF_NETLINK, socket.SOCK_DGRAM, NETLINK_CONNECTOR)
    try:
        sk.setsockopt(socket.SOL_SOCKET, SO_RCVBUFFORCE, RCVBUF_BYTES)
    except OSError:
        sk.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RCVBUF_BYTES)
    try:
        sk.bind((os.getpid(), CN_IDX_PROC))        # binding the multicast group needs root
    except OSError as e:
        sys.exit(f"probe: bind failed ({e}) — need sudo?")
    sk.send(mcast_msg(PROC_CN_MCAST_LISTEN, 1))
    sk.settimeout(1.0)

    if probe:
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if os.fork() == 0:
                os._exit(0)
            os.wait()
            try:
                buf = sk.recv(1 << 16)
            except socket.timeout:
                continue
            rows = []
            decode_events(buf, time.time(), rows)
            if rows:
                print(f"probe: ok ({len(rows)} events, first: {rows[0].strip()})")
                return
        sys.exit("probe: no events within 3s")

    out, stopfile = args[0], args[1]
    fh = open(out, "a", buffering=1 << 16)
    if "SUDO_UID" in os.environ:
        os.chown(out, int(os.environ["SUDO_UID"]), int(os.environ.get("SUDO_GID", -1)))
    q = collections.deque()
    st = {"n": 0, "lost": 0, "run": True}

    def decode():
        while st["run"] or q:
            try:
                now, buf = q.popleft()
            except IndexError:
                time.sleep(0.002)
                continue
            if buf is LOST:
                fh.write(f"{now:.6f}\tLOST\t{st['lost']}\t0\t0\t0\n")
                continue
            rows = []
            decode_events(buf, now, rows)
            if rows:
                fh.write("".join(rows))
                st["n"] += len(rows)

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
                st["lost"] += 1
                q.append((time.time(), LOST))
                continue
            q.append((time.time(), buf))
    finally:
        st["run"] = False
        th.join(timeout=15)
        try:
            sk.send(mcast_msg(PROC_CN_MCAST_IGNORE, 2))
        except OSError:
            pass
        fh.flush()
        fh.close()
        print(f"procconn: {st['n']} events banked, {st['lost']} drop events", file=sys.stderr)


if __name__ == "__main__":
    main()
