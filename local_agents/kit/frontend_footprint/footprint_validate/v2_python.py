#!/usr/bin/env python3
"""v2_python.py — deterministic, branchy pure-Python workload (~1 s on P7) for gate V2.

A mix of dict/set churn, string building and formatting, json round trips, regex scanning,
sorting with key functions, small classes with dynamic dispatch, generators and exceptions,
so the interpreter visits many different code paths instead of one tight loop. Run with
PYTHONHASHSEED=0 so set/dict iteration (and so the executed code) is identical across the
PT and the LBR execution; the final digest line lets run_v2.sh check that.

  PYTHONHASHSEED=0 python3 v2_python.py [rounds]
"""
import hashlib
import json
import re
import sys


class Shape:
    def area(self):
        raise NotImplementedError


class Rect(Shape):
    def __init__(self, w, h):
        self.w, self.h = w, h

    def area(self):
        return self.w * self.h


class Circle(Shape):
    def __init__(self, r):
        self.r = r

    def area(self):
        return 3.14159 * self.r * self.r


class Tri(Shape):
    def __init__(self, b, h):
        self.b, self.h = b, h

    def area(self):
        return 0.5 * self.b * self.h


WORD = re.compile(r"[a-z]+(?:_[a-z]+)*")
NUM = re.compile(r"-?\d+(?:\.\d+)?")
KV = re.compile(r"(\w+)=(\"[^\"]*\"|\S+)")


def lcg(seed):
    x = seed
    while True:
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        yield x


def make_record(g, i):
    n = next(g)
    return {
        "id": i,
        "name": "item_%d_%s" % (i, "abcdefghij"[n % 10] * (1 + n % 5)),
        "tags": ["t%d" % ((n >> k) % 17) for k in range(n % 6)],
        "value": (n % 10007) / 7.0,
        "nested": {"a": n % 3, "b": [n % 11, n % 13], "c": None if n % 4 else "x"},
    }


def round_once(r):
    g = lcg(r + 1)
    recs = [make_record(g, i) for i in range(300)]
    # json round trip
    blob = json.dumps(recs, sort_keys=True)
    back = json.loads(blob)
    # dict / set churn
    idx = {}
    for rec in back:
        for t in rec["tags"]:
            idx.setdefault(t, set()).add(rec["id"])
    common = sorted((len(v), k) for k, v in idx.items())
    # string work + regex
    text = " ".join("%s=%s val=%.3f" % (rec["name"], rec["nested"]["b"][0], rec["value"]) for rec in back)
    words = WORD.findall(text)
    nums = [float(x) for x in NUM.findall(text)]
    kvs = dict(KV.findall(text))
    # sorting with keys, dynamic dispatch, generators, exceptions
    shapes = []
    for rec in back:
        k = rec["id"] % 3
        shapes.append(Rect(rec["id"] % 7 + 1, 2) if k == 0 else Circle(rec["id"] % 5 + 1) if k == 1 else Tri(3, rec["id"] % 9 + 1))
    total = sum(s.area() for s in sorted(shapes, key=lambda s: (type(s).__name__, s.area())))
    errs = 0
    for rec in back:
        try:
            if rec["nested"]["c"] is None:
                raise KeyError(rec["id"])
            _ = rec["nested"]["c"].upper()
        except KeyError:
            errs += 1
    folded = "".join(w.capitalize() for w in words[:200])
    return len(blob), len(common), len(words), round(sum(nums), 3), len(kvs), round(total, 3), errs, folded[:40]


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 420
    h = hashlib.sha256()
    for r in range(rounds):
        h.update(repr(round_once(r)).encode())
    print("v2_python rounds=%d digest=%s" % (rounds, h.hexdigest()[:16]))


if __name__ == "__main__":
    main()
