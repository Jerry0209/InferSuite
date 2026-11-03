// lbr_footprint.cpp — front-end footprint analyzer for the 2026-11 front-end study.
//
// Implements §4 "Analyzer rules" of docs/handoff/execution/frontend_footprint_method.md:
// reads `perf script` text on stdin and computes, from LBR samples (--mode lbr) or from an
// exact Intel PT branch trace (--mode pt, the V2 reference), the three metrics
//   1. instruction footprint   = 64 B x |unique 64 B lines executed|
//   2. unique taken branches   = |distinct canonical `from` of near taken branches|
//   3. weighted avg targets    = sum(C_b*T_b) / sum(C_b) (all / no-returns / indirect only)
// on CANONICAL addresses, so a shared library mapped in many processes is counted once and
// ASLR does not matter. Both modes share the canonicalization and the outputs, so a PT run is
// directly comparable with an LBR run of the same program (compare_v2.py).
//
// Inputs:
//   lbr: perf script -F pid,brstack --show-mmap-events --show-task-events --show-lost-events
//   pt : perf script --itrace=be -F pid,tid,ip,addr,flags --show-mmap-events --show-task-events
// Outputs: --summary (JSON), --objects/--edges/--lines (TSV tables from which every metric can
// be recomputed without the perf.data). See README.md for the schema.
//
// One pass, streaming, single-threaded. Speed matters (perf script emits ~110 k LBR samples/s
// of 32 entries), so hot paths use flat open-addressing tables keyed by 64-bit packed
// canonical addresses: key = obj_id << 47 | offset. User VAs and kernel VAs minus
// 0xffff800000000000 both fit in 47 bits, so a canonical key is one integer and the 64 B
// line of a key is simply key & ~63 (objects are page aligned in canonical space).

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cinttypes>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <sys/auxv.h>
#include <sys/stat.h>
#include <unistd.h>
#include <unordered_map>
#include <vector>

#ifndef SRC_SHA256
#define SRC_SHA256 "unknown"
#endif
static const char* kVersion = "1.0";

// ---------------------------------------------------------------------------------------------
// Canonical key packing
static const int kOffBits = 47;
static const uint64_t kOffMask = (1ULL << kOffBits) - 1;
static const uint64_t kMaxObj = (1ULL << (64 - kOffBits)) - 1;  // 131071 objects
static const uint64_t kKernBase = 0xffff800000000000ULL;          // contract §4.2 threshold
static const uint64_t kVsyscall = 0xffffffffff600000ULL;          // fixed legacy page
static inline uint64_t pack(uint32_t obj, uint64_t off) { return ((uint64_t)obj << kOffBits) | (off & kOffMask); }
static inline uint32_t key_obj(uint64_t k) { return (uint32_t)(k >> kOffBits); }
static inline uint64_t key_off(uint64_t k) { return k & kOffMask; }

// ---------------------------------------------------------------------------------------------
// Branch types. 0..5 are the contract's near taken branches; 6/7 only occur in PT mode when the
// instruction bytes could not be read (PT does not say direct vs indirect); 8+ are far/other
// transfers named by perf (SYSCALL, SYSRET, IRQ, ERET, "-", ...), added as they appear.
enum : uint8_t { T_COND = 0, T_UNCOND, T_CALL, T_IND_CALL, T_IND, T_RET, T_JMP_UNK, T_CALL_UNK, T_FAR0 };
static std::vector<std::string> g_type_names = {"COND", "UNCOND", "CALL", "IND_CALL", "IND", "RET",
                                                "JMP_UNK", "CALL_UNK"};
static inline bool is_near(uint8_t t) { return t < T_FAR0; }
static inline bool is_indirect(uint8_t t) { return t == T_IND || t == T_IND_CALL; }

static uint8_t type_from_name(const char* s, size_t n) {
  switch (n) {
    case 3:
      if (!memcmp(s, "IND", 3)) return T_IND;
      if (!memcmp(s, "RET", 3)) return T_RET;
      break;
    case 4:
      if (!memcmp(s, "COND", 4)) return T_COND;
      if (!memcmp(s, "CALL", 4)) return T_CALL;
      break;
    case 6:
      if (!memcmp(s, "UNCOND", 6)) return T_UNCOND;
      break;
    case 8:
      if (!memcmp(s, "IND_CALL", 8)) return T_IND_CALL;
      break;
  }
  for (size_t i = T_FAR0; i < g_type_names.size(); i++)
    if (g_type_names[i].size() == n && !memcmp(g_type_names[i].data(), s, n)) return (uint8_t)i;
  if (g_type_names.size() >= 255) return 254;  // absurd input; lump the rest
  g_type_names.emplace_back(s, n);
  return (uint8_t)(g_type_names.size() - 1);
}

// ---------------------------------------------------------------------------------------------
// Flat open-addressing tables (linear probing, power-of-two capacity, <= 50 % load).
static inline uint64_t hash64(uint64_t x) {
  x ^= x >> 33; x *= 0xff51afd7ed558ccdULL; x ^= x >> 33; x *= 0xc4ceb9fe1a85ec53ULL; x ^= x >> 33;
  return x;
}

// Set of line keys (never 0: obj ids start at 1) with the first-seen sample of each.
struct LineSet {
  std::vector<uint64_t> keys, first;
  size_t n = 0, mask = 0;
  LineSet() { rehash(1 << 16); }
  void rehash(size_t cap) {
    std::vector<uint64_t> ok, of;
    ok.swap(keys); of.swap(first);
    keys.assign(cap, 0); first.assign(cap, 0); mask = cap - 1; n = 0;
    for (size_t i = 0; i < ok.size(); i++) if (ok[i]) insert(ok[i], of[i]);
  }
  inline void prefetch(uint64_t k) const { __builtin_prefetch(&keys[hash64(k) & mask]); }
  inline bool insert(uint64_t k, uint64_t seen) {
    size_t i = hash64(k) & mask;
    for (;;) {
      uint64_t c = keys[i];
      if (c == k) return false;
      if (c == 0) {
        keys[i] = k; first[i] = seen;
        if (++n * 2 > keys.size()) rehash(keys.size() * 2);
        return true;
      }
      i = (i + 1) & mask;
    }
  }
};

// last_to/last_edge cache the most recent edge of this branch: most branches are
// monomorphic, so the common case needs one hash probe per entry instead of two.
struct BrSlot { uint64_t key, C, first, last_to; uint32_t T, last_edge; uint8_t type; };
struct BranchMap {
  std::vector<BrSlot> s;
  size_t n = 0, mask = 0;
  BranchMap() { rehash(1 << 15); }
  void rehash(size_t cap) {
    std::vector<BrSlot> o; o.swap(s);
    s.assign(cap, BrSlot{0, 0, 0, 0, 0, 0, 0}); mask = cap - 1; n = 0;
    for (auto& x : o) if (x.key) { bool ins; *find(x.key, ins) = x; }
  }
  inline void prefetch(uint64_t k) const { __builtin_prefetch(&s[hash64(k) & mask]); }
  // Returns the slot; `ins` tells whether it was created (key already stored, rest zero).
  inline BrSlot* find(uint64_t k, bool& ins) {
    size_t i = hash64(k) & mask;
    for (;;) {
      BrSlot& c = s[i];
      if (c.key == k) { ins = false; return &c; }
      if (c.key == 0) {
        if ((n + 1) * 2 > s.size()) { rehash(s.size() * 2); return find(k, ins); }
        c.key = k; n++; ins = true; return &c;
      }
      i = (i + 1) & mask;
    }
  }
};

struct EdgeSlot { uint64_t from, to, count, first; uint8_t type; };
struct EdgeMap {
  std::vector<EdgeSlot> s;
  size_t n = 0, mask = 0;
  uint64_t gen = 0;  // bumped on rehash: invalidates slot indexes cached in BrSlot
  EdgeMap() { rehash(1 << 15); }
  void rehash(size_t cap) {
    gen++;
    std::vector<EdgeSlot> o; o.swap(s);
    s.assign(cap, EdgeSlot{0, 0, 0, 0, 0}); mask = cap - 1; n = 0;
    for (auto& x : o) if (x.from) { bool ins; *find(x.from, x.to, ins) = x; }
  }
  inline EdgeSlot* find(uint64_t f, uint64_t t, bool& ins) {
    size_t i = hash64(f ^ (t * 0x9E3779B97F4A7C15ULL)) & mask;
    for (;;) {
      EdgeSlot& c = s[i];
      if (c.from == f && c.to == t) { ins = false; return &c; }
      if (c.from == 0) {
        if ((n + 1) * 2 > s.size()) { rehash(s.size() * 2); return find(f, t, ins); }
        c.from = f; c.to = t; n++; ins = true; return &c;
      }
      i = (i + 1) & mask;
    }
  }
};

// ---------------------------------------------------------------------------------------------
// Objects and mappings
enum : uint8_t { K_FILE = 0, K_KERNEL, K_ANON, K_SPECIAL };
static const char* kKindName[] = {"file", "kernel", "anon", "special"};

struct Obj {
  uint8_t kind;
  std::string path;
  uint64_t inode;
  int pid;            // anon only
  uint64_t entries;   // entries whose `from` is in this object (near + far)
};
static std::vector<Obj> g_objs(1);  // id 0 = invalid (keeps keys non-zero)
static std::unordered_map<std::string, uint32_t> g_obj_index;

static uint32_t new_obj(uint8_t kind, const std::string& path, uint64_t inode, int pid) {
  if (g_objs.size() > kMaxObj) {
    fprintf(stderr, "lbr_footprint: FATAL more than %" PRIu64 " canonical objects\n", kMaxObj);
    exit(3);
  }
  g_objs.push_back(Obj{kind, path, inode, pid, 0});
  return (uint32_t)(g_objs.size() - 1);
}
static uint32_t intern_obj(uint8_t kind, const std::string& path, uint64_t inode) {
  std::string k = std::to_string(kind) + '\x01' + path + '\x01' + std::to_string(inode);
  auto it = g_obj_index.find(k);
  if (it != g_obj_index.end()) return it->second;
  uint32_t id = new_obj(kind, path, inode, -1);
  g_obj_index.emplace(std::move(k), id);
  return id;
}
static uint32_t g_kernel_obj = 0, g_vsyscall_obj = 0;

struct Map { uint64_t start, end, pgoff; uint32_t obj; uint8_t kind; };

// Insert into a start-sorted, non-overlapping list; a new mapping replaces whatever it
// overlaps (the kernel did the same), trimming partially covered neighbours.
static void map_insert(std::vector<Map>& v, const Map& m) {
  std::vector<Map> out;
  out.reserve(v.size() + 2);
  for (const Map& o : v) {
    if (o.end <= m.start || o.start >= m.end) { out.push_back(o); continue; }
    if (o.start < m.start) { Map l = o; l.end = m.start; out.push_back(l); }
    if (o.end > m.end) { Map r = o; r.pgoff += m.end - o.start; r.start = m.end; out.push_back(r); }
  }
  out.push_back(m);
  std::sort(out.begin(), out.end(), [](const Map& a, const Map& b) { return a.start < b.start; });
  v.swap(out);
}
static inline const Map* map_find(const std::vector<Map>& v, uint64_t a, uint32_t& hint) {
  if (hint < v.size() && a >= v[hint].start && a < v[hint].end) return &v[hint];
  size_t lo = 0, hi = v.size();
  while (lo < hi) { size_t mid = (lo + hi) / 2; if (v[mid].start <= a) lo = mid + 1; else hi = mid; }
  if (lo == 0) return nullptr;
  const Map& m = v[lo - 1];
  if (a < m.end) { hint = (uint32_t)(lo - 1); return &m; }
  return nullptr;
}

struct PidState {
  std::vector<Map> maps;
  uint32_t anon_obj = 0;  // (anon, pid) object of the current image; renewed on fork/exec
  uint32_t hint = 0;
  uint64_t units = 0;     // samples (lbr) / branch records (pt) attributed to this pid
  std::string comm;       // last command name seen for the pid (diagnostic only)
};
static std::unordered_map<int, PidState> g_pids;
static std::vector<Map> g_kmaps;
static uint32_t g_khint = 0;

static PidState& pid_state(int pid) { return g_pids[pid]; }

// ---------------------------------------------------------------------------------------------
// Resolution of one address to its canonical key
struct Res {
  uint64_t key;    // 0 = zero address
  uint64_t mapid;  // identity of the containing mapping (0 = none) for the same-mapping rule
  uint8_t kern;    // 1 = kernel object
  uint8_t unmapped;
};

struct Stats {
  uint64_t samples = 0, samples_empty = 0, entries = 0, near_entries = 0, far_entries = 0;
  uint64_t zero_entries = 0, unmapped_entries = 0, kernel_unmapped_entries = 0;
  uint64_t candidate_ranges = 0, disc_cross_map = 0, disc_negative = 0, disc_too_long = 0,
           disc_unmapped = 0, range_lines = 0;
  uint64_t lost_events = 0, lost_samples = 0, lost_records = 0, lost_unparsed = 0;
  uint64_t unparsed = 0, mmap_events = 0, mmap_kernel = 0, mmap_nonexec = 0, comm_exec = 0,
           fork_proc = 0, fork_thread = 0, exit_events = 0, other_events = 0;
  uint64_t type_conflicts = 0, offset_overflow = 0, input_bytes = 0, input_lines = 0;
  // PT only
  uint64_t pt_branches = 0, pt_trace_errors = 0, pt_trace_start = 0, pt_trace_end = 0,
           pt_no_resume = 0, pt_near_no_target = 0, pt_classified = 0, pt_class_unreadable = 0,
           pt_class_mismatch = 0;
  std::vector<std::string> unparsed_examples;
};
static Stats S;

static std::unordered_map<int, uint32_t> g_unmapped_pid_anon;  // pids never seen in events

static inline uint32_t anon_obj_for(int pid, PidState* ps) {
  if (ps) {
    if (!ps->anon_obj) ps->anon_obj = new_obj(K_ANON, "//anon", 0, pid);
    return ps->anon_obj;
  }
  auto it = g_unmapped_pid_anon.find(pid);
  if (it != g_unmapped_pid_anon.end()) return it->second;
  uint32_t id = new_obj(K_ANON, "//anon", 0, pid);
  g_unmapped_pid_anon.emplace(pid, id);
  return id;
}

static inline Res resolve(uint64_t a, int pid, PidState* ps) {
  Res r{0, 0, 0, 0};
  if (a == 0) return r;
  if (a >= kKernBase) {
    if (a - kVsyscall < 0x1000) {  // legacy vsyscall page: same code in every process
      r.key = pack(g_vsyscall_obj, a - kVsyscall); r.mapid = kVsyscall; return r;
    }
    r.kern = 1;
    r.key = pack(g_kernel_obj, a - kKernBase);
    const Map* m = map_find(g_kmaps, a, g_khint);
    if (m) r.mapid = m->start; else r.unmapped = 1;
    return r;
  }
  const Map* m = ps ? map_find(ps->maps, a, ps->hint) : nullptr;
  if (!m) {
    r.unmapped = 1;
    r.key = pack(anon_obj_for(pid, ps), a);
    return r;
  }
  r.mapid = m->start;
  if (m->kind == K_ANON) {
    r.key = pack(anon_obj_for(pid, ps), a);
  } else {
    uint64_t off = a - m->start + m->pgoff;
    if (off > kOffMask) S.offset_overflow++;
    r.key = pack(m->obj, off);
  }
  return r;
}

// ---------------------------------------------------------------------------------------------
// Metric state
static LineSet g_lines;
static BranchMap g_br;
static EdgeMap g_edges, g_far_edges;
static LineSet g_far_from;  // unique far `from`s (set semantics; first-seen unused)
static uint64_t g_sumCT = 0, g_sumC = 0;
static uint64_t g_lines_user = 0, g_lines_kern = 0, g_br_user = 0, g_br_kern = 0;
static uint64_t g_cur = 0;  // current sample ordinal (lbr) / branch ordinal (pt), 1-based
static std::vector<uint64_t> g_far_by_type;

static inline bool is_kernel_key(uint64_t k) { return key_obj(k) == g_kernel_obj; }

static uint64_t g_last_line = 0;
static inline void add_line(uint64_t key) {
  uint64_t lk = key & ~63ULL;
  if (lk == g_last_line) return;  // consecutive entries very often touch the same line
  g_last_line = lk;
  if (g_lines.insert(lk, g_cur)) {
    if (is_kernel_key(lk)) g_lines_kern++; else g_lines_user++;
  }
}

// Straight-line range [a, b] (inclusive, raw VAs; ka = canonical key of a). With
// ends_done the two end lines were already added (LBR adds line(from)/line(to) of every
// entry), so only the interior is inserted.
static inline void add_range(uint64_t ka, uint64_t a, uint64_t b, bool ends_done) {
  uint64_t l0 = ka & ~63ULL, l1 = (ka + (b - a)) & ~63ULL;
  S.range_lines += (l1 - l0) / 64 + 1;
  if (ends_done) { for (uint64_t l = l0 + 64; l < l1; l += 64) add_line(l); return; }
  for (uint64_t l = l0; l <= l1; l += 64) add_line(l);
}

static inline void add_near(uint64_t fk, uint64_t tk, uint8_t type) {
  bool new_edge = false, new_br;
  BrSlot* b = g_br.find(fk, new_br);
  if (new_br) {
    b->type = type; b->first = g_cur;
    if (is_kernel_key(fk)) g_br_kern++; else g_br_user++;
  } else if (b->type != type) S.type_conflicts++;
  EdgeSlot* e;
  if (!new_br && b->last_to == tk && (g_edges.gen & 0xff) == (b->last_edge >> 24)) {
    e = &g_edges.s[b->last_edge & 0xffffff];
  } else {
    e = g_edges.find(fk, tk, new_edge);
    if (new_edge) { e->type = type; e->first = g_cur; }
    size_t idx = (size_t)(e - g_edges.s.data());
    b->last_to = tk;
    // pack (generation, slot) into 32 bits; tables beyond 16 M slots simply skip the cache
    b->last_edge = idx < (1u << 24) ? (uint32_t)(((g_edges.gen & 0xff) << 24) | idx) : 0xffffffffu;
  }
  e->count++;
  uint64_t C = b->C, T = b->T, T2 = T + (new_edge ? 1 : 0);
  g_sumCT += (C + 1) * T2 - C * T;  // keeps sum(C_b*T_b) exact and O(1) per entry
  g_sumC++;
  b->C = C + 1; b->T = (uint32_t)T2;
}

static inline void add_far(uint64_t fk, uint64_t tk, uint8_t type) {
  bool ins;
  EdgeSlot* e = g_far_edges.find(fk, tk ? tk : 1, ins);  // to may be 0 only in PT mode
  if (ins) { e->type = type; e->first = g_cur; }
  e->count++;
  g_far_from.insert(fk, g_cur);
  if (g_far_by_type.size() <= type) g_far_by_type.resize(type + 1, 0);
  g_far_by_type[type]++;
}

// Convergence snapshots
struct Snap { uint64_t unit, lines, lines_user, br, br_user, sumCT, sumC; };
static std::vector<Snap> g_snaps;
static uint64_t g_snap_every = 0;
static inline void snapshot() {
  g_snaps.push_back(Snap{g_cur, g_lines.n, g_lines_user, g_br.n, g_br_user, g_sumCT, g_sumC});
}

// ---------------------------------------------------------------------------------------------
// Text parsing helpers
static int8_t g_hexv[256];
static void init_hex() {
  memset(g_hexv, -1, sizeof g_hexv);
  for (int i = 0; i < 10; i++) g_hexv['0' + i] = (int8_t)i;
  for (int i = 0; i < 6; i++) { g_hexv['a' + i] = (int8_t)(10 + i); g_hexv['A' + i] = (int8_t)(10 + i); }
}
// Parses [0x]hex at p; returns pointer after it (== p if no digit).
static inline const char* parse_hex(const char* p, const char* e, uint64_t& v) {
  if (e - p > 2 && p[0] == '0' && (p[1] == 'x' || p[1] == 'X')) p += 2;
  uint64_t x = 0;
  const char* s = p;
  while (p < e) { int8_t d = g_hexv[(uint8_t)*p]; if (d < 0) break; x = (x << 4) | (uint64_t)d; p++; }
  v = x;
  return p == s ? s : p;
}
static inline const char* parse_dec(const char* p, const char* e, long long& v, bool& ok) {
  bool neg = false;
  if (p < e && *p == '-') { neg = true; p++; }
  const char* s = p;
  long long x = 0;
  while (p < e && *p >= '0' && *p <= '9') { x = x * 10 + (*p - '0'); p++; }
  ok = p > s;
  v = neg ? -x : x;
  return p;
}
static inline const char* skip_ws(const char* p, const char* e) { while (p < e && (*p == ' ' || *p == '\t')) p++; return p; }
static const char* find_str(const char* p, const char* e, const char* needle) {
  size_t n = strlen(needle);
  if ((size_t)(e - p) < n) return nullptr;
  const char* last = e - n;
  for (const char* q = p; q <= last; q++) {
    q = (const char*)memchr(q, needle[0], (size_t)(last - q + 1));
    if (!q) return nullptr;
    if (!memcmp(q, needle, n)) return q;
  }
  return nullptr;
}

static void note_unparsed(const char* p, const char* e) {
  S.unparsed++;
  if (S.unparsed_examples.size() < 5) S.unparsed_examples.emplace_back(p, (size_t)std::min<ptrdiff_t>(e - p, 200));
}

// ---- PERF_RECORD_* side-band events (same in both modes) -------------------------------------
static void on_mmap(const char* p, const char* e, bool v2) {
  // " 2370326/2370326: [0x5f4c39dd2000(0xef000) @ 0x30000 103:02 1311278 0]: r-xp /usr/bin/bash"
  // MMAP (v1): " -1/0: [0xffffffff8da00000(0x2a86380) @ 0xffffffff8da00000]: x [kernel.kallsyms]_text"
  long long pid; bool ok;
  p = skip_ws(p, e);
  p = parse_dec(p, e, pid, ok);
  if (!ok) { note_unparsed(p, e); return; }
  const char* lb = (const char*)memchr(p, '[', (size_t)(e - p));
  if (!lb) { note_unparsed(p, e); return; }
  uint64_t start, len, pgoff = 0, inode = 0;
  const char* q = parse_hex(lb + 1, e, start);
  if (q >= e || *q != '(') { note_unparsed(p, e); return; }
  q = parse_hex(q + 1, e, len);
  const char* at = find_str(q, e, " @ ");
  if (!at) { note_unparsed(p, e); return; }
  q = parse_hex(at + 3, e, pgoff);
  const char* rb = (const char*)memchr(q, ']', (size_t)(e - q));
  if (!rb) { note_unparsed(p, e); return; }
  if (v2) {  // " maj:min ino gen" (or a build id: then no inode)
    const char* t = skip_ws(q, rb);
    const char* sp = (const char*)memchr(t, ' ', (size_t)(rb - t));
    if (sp && memchr(t, ':', (size_t)(sp - t))) {
      long long ino; bool ok2;
      parse_dec(skip_ws(sp, rb), rb, ino, ok2);
      if (ok2) inode = (uint64_t)ino;
    }
  }
  const char* r = rb + 1;
  if (r < e && *r == ':') r++;
  r = skip_ws(r, e);
  const char* prot = r;
  while (r < e && *r != ' ') r++;
  bool exec = memchr(prot, 'x', (size_t)(r - prot)) != nullptr;
  r = skip_ws(r, e);
  std::string path(r, (size_t)(e - r));
  S.mmap_events++;
  if (pid == -1 || start >= kKernBase) {  // kernel image and modules
    S.mmap_kernel++;
    if (start >= kKernBase && start != kVsyscall) map_insert(g_kmaps, Map{start, start + len, pgoff, g_kernel_obj, K_KERNEL});
    return;
  }
  if (!exec) { S.mmap_nonexec++; return; }  // only code matters
  uint8_t kind;
  uint32_t obj = 0;
  if (path == "[vdso]" || path == "[uprobes]" || path == "[vsyscall]") {
    kind = K_SPECIAL; obj = intern_obj(K_SPECIAL, path, 0);
  } else if (path.empty() || path.compare(0, 2, "//") == 0 || path.compare(0, 5, "[anon") == 0 ||
             path == "[heap]" || path == "[stack]") {
    kind = K_ANON;  // JIT code and other anonymous text: keyed (pid, addr)
  } else {
    kind = K_FILE; obj = intern_obj(K_FILE, path, inode);
  }
  map_insert(pid_state((int)pid).maps, Map{start, start + len, pgoff, obj, kind});
}

static void on_event(const char* line, const char* ev, const char* e) {
  const char* p = ev + 12;  // after "PERF_RECORD_"
  if (e - p >= 5 && !memcmp(p, "MMAP2", 5)) { on_mmap(p + 5, e, true); return; }
  if (e - p >= 4 && !memcmp(p, "MMAP", 4)) { on_mmap(p + 4, e, false); return; }
  if (e - p >= 4 && !memcmp(p, "COMM", 4)) {
    {  // "COMM[ exec]: name:pid/tid" -> remember the process name (name may contain ':')
      const char* c = e;
      while (c > p && *(c - 1) != ':') c--;
      const char* colon = (const char*)memchr(p, ':', (size_t)(e - p));
      long long cpid, ctid; bool ok1, ok2;
      const char* sl = parse_dec(c, e, cpid, ok1);
      if (ok1 && colon && c - 1 > colon && sl < e && *sl == '/') {
        parse_dec(sl + 1, e, ctid, ok2);
        const char* nb = skip_ws(colon + 1, e);
        if (ok2 && cpid == ctid && c - 1 > nb) pid_state((int)cpid).comm.assign(nb, (size_t)(c - 1 - nb));
      }
    }
    if (e - p >= 10 && !memcmp(p + 4, " exec:", 6)) {
      // "PERF_RECORD_COMM exec: python3:2371057/2371057" -> the pid's old image is gone
      const char* c = e;
      while (c > p && *(c - 1) != ':') c--;
      long long pid; bool ok;
      parse_dec(c, e, pid, ok);
      if (!ok) { note_unparsed(line, e); return; }
      PidState& ps = pid_state((int)pid);
      ps.maps.clear(); ps.anon_obj = 0; ps.hint = 0;
      S.comm_exec++;
    }
    return;
  }
  if (e - p >= 4 && (!memcmp(p, "FORK", 4) || !memcmp(p, "EXIT", 4))) {
    // "PERF_RECORD_FORK(child:ctid):(parent:ptid)"
    bool fork = p[0] == 'F';
    long long cp, ct, pp, pt; bool ok1, ok2, ok3, ok4;
    const char* q = (const char*)memchr(p, '(', (size_t)(e - p));
    if (!q) { note_unparsed(line, e); return; }
    q = parse_dec(q + 1, e, cp, ok1); q = parse_dec(q + 1, e, ct, ok2);
    q = (const char*)memchr(q, '(', (size_t)(e - q));
    if (!q) { note_unparsed(line, e); return; }
    q = parse_dec(q + 1, e, pp, ok3); parse_dec(q + 1, e, pt, ok4);
    if (!(ok1 && ok2 && ok3 && ok4)) { note_unparsed(line, e); return; }
    if (!fork) { S.exit_events++; return; }  // maps kept: PT prints a thread's branches before its EXIT
    if (cp == pp) { S.fork_thread++; return; }
    S.fork_proc++;
    // A synthesized FORK (leading sample pid 0, emitted by perf for pre-existing tasks) is
    // followed by the child's own synthesized MMAPs, so start empty; a real fork inherits a
    // copy of the parent's mappings (until exec).
    long long lead; bool okl;
    parse_dec(skip_ws(line, e), e, lead, okl);
    PidState& child = pid_state((int)cp);
    child.anon_obj = 0; child.hint = 0;
    if (okl && lead == 0) { child.maps.clear(); return; }
    auto it = g_pids.find((int)pp);
    if (it != g_pids.end()) child.maps = it->second.maps; else child.maps.clear();
    return;
  }
  if (e - p >= 4 && !memcmp(p, "LOST", 4)) {
    // "PERF_RECORD_LOST lost 123" / "PERF_RECORD_LOST_SAMPLES lost 123": take the last integer
    bool samples_rec = (e - p >= 12 && !memcmp(p, "LOST_SAMPLES", 12));
    const char* c = e;
    while (c > p && !(*(c - 1) >= '0' && *(c - 1) <= '9')) c--;
    const char* d = c;
    while (d > p && *(d - 1) >= '0' && *(d - 1) <= '9') d--;
    S.lost_records++;
    if (d < c && (d - 1 > p) && *(d - 1) == ' ') {
      long long v; bool ok; parse_dec(d, c, v, ok);
      if (samples_rec) S.lost_samples += (uint64_t)v; else S.lost_events += (uint64_t)v;
    } else {
      S.lost_unparsed++;
    }
    return;
  }
  S.other_events++;
}

// ---- LBR samples -------------------------------------------------------------------------------
struct Entry { uint64_t from, to; uint8_t type; Res rf, rt; };

static void on_lbr_sample(int pid, const char* p, const char* e) {
  static Entry ent[64];
  int n = 0;
  for (;;) {
    p = skip_ws(p, e);
    if (p >= e) break;
    // "0xFROM/0xTO/P/-/-/1/TYPE/-", parsed in one left-to-right pass
    const char* tok = p;
    uint64_t f, t;
    const char* q = parse_hex(p, e, f);
    bool ok = q != p && q < e && *q == '/';
    const char* q2 = ok ? parse_hex(q + 1, e, t) : q;
    ok = ok && q2 != q + 1 && q2 < e && *q2 == '/';
    const char* ts = nullptr;
    const char* r = q2 + 1;
    if (ok) {  // skip pred, in_tx, abort, cycles: the type is the 7th '/'-field
      int k = 0;
      while (r < e && k < 4 && *r != ' ') { if (*r == '/') k++; r++; }
      ok = k == 4;
      ts = r;
      while (r < e && *r != '/' && *r != ' ' && *r != '\t') r++;
    }
    const char* tend = r;
    while (r < e && *r != ' ' && *r != '\t') r++;
    p = r;
    if (!ok || n == 64) { note_unparsed(tok, r); continue; }
    ent[n].from = f; ent[n].to = t; ent[n].type = type_from_name(ts, (size_t)(tend - ts));
    n++;
  }
  g_cur = ++S.samples;
  if (n == 0) { S.samples_empty++; if (g_snap_every && S.samples % g_snap_every == 0) snapshot(); return; }
  PidState* ps = pid > 0 ? &pid_state(pid) : nullptr;
  if (ps) ps->units++;
  // Resolve all entries first and prefetch their table slots, so the (for large footprints,
  // cache-missing) probes of the 32 entries overlap instead of being paid one by one.
  for (int i = 0; i < n; i++) {
    Entry& x = ent[i];
    if (x.from == 0 || x.to == 0) { x.rf.key = 0; x.rt.key = 0; continue; }
    x.rf = resolve(x.from, pid, ps);
    x.rt = resolve(x.to, pid, ps);
    g_lines.prefetch(x.rf.key & ~63ULL);
    g_lines.prefetch(x.rt.key & ~63ULL);
    if (is_near(x.type)) g_br.prefetch(x.rf.key);
  }
  for (int i = 0; i < n; i++) {
    Entry& x = ent[i];
    if (!x.rf.key) { S.zero_entries++; continue; }
    S.entries++;
    if ((x.rf.unmapped && !x.rf.kern) || (x.rt.unmapped && !x.rt.kern)) S.unmapped_entries++;
    if ((x.rf.unmapped && x.rf.kern) || (x.rt.unmapped && x.rt.kern)) S.kernel_unmapped_entries++;
    g_objs[key_obj(x.rf.key)].entries++;
    add_line(x.rf.key);
    add_line(x.rt.key);
    if (is_near(x.type)) { S.near_entries++; add_near(x.rf.key, x.rt.key, x.type); }
    else { S.far_entries++; add_far(x.rf.key, x.rt.key, x.type); }
  }
  // Entries are newest first: the code between e[i+1].to (older) and e[i].from (newer) ran
  // straight through (§4.3), if it is short and inside one mapping.
  for (int i = 0; i + 1 < n; i++) {
    const Entry& older = ent[i + 1];
    const Entry& newer = ent[i];
    if (!older.rt.key || !newer.rf.key) continue;
    S.candidate_ranges++;
    uint64_t a = older.to, b = newer.from;
    if (older.rt.unmapped || newer.rf.unmapped) { S.disc_unmapped++; continue; }
    if (older.rt.mapid != newer.rf.mapid || key_obj(older.rt.key) != key_obj(newer.rf.key)) { S.disc_cross_map++; continue; }
    if (b < a) { S.disc_negative++; continue; }
    if (b - a > 4096) { S.disc_too_long++; continue; }
    add_range(older.rt.key, a, b, true);
  }
  if (g_snap_every && S.samples % g_snap_every == 0) snapshot();
}

// ---- Intel PT branches -------------------------------------------------------------------------
struct ThreadState { uint64_t resume; bool valid; };
static std::unordered_map<long long, ThreadState> g_threads;

static void pt_range(int pid, PidState* ps, uint64_t a, uint64_t b) {
  // [a, b] inclusive; same-mapping check; exact (no 4096 cap) but with a 1 MiB sanity bound
  S.candidate_ranges++;
  Res ra = resolve(a, pid, ps), rb = resolve(b, pid, ps);
  if (ra.unmapped || rb.unmapped) { S.disc_unmapped++; return; }
  if (ra.mapid != rb.mapid || key_obj(ra.key) != key_obj(rb.key)) { S.disc_cross_map++; return; }
  if (b < a) { S.disc_negative++; return; }
  if (b - a > (1u << 20)) { S.disc_too_long++; return; }
  add_range(ra.key, a, b, false);
}

static void on_pt_line(const char* line, const char* e) {
  // "PID  TID   FLAGS...   IP =>   ADDR"  (TID optional); hex without 0x
  const char* tok[24]; const char* tend[24];
  int nt = 0;
  const char* p = line;
  while (nt < 24) {
    p = skip_ws(p, e);
    if (p >= e) break;
    tok[nt] = p;
    while (p < e && *p != ' ' && *p != '\t') p++;
    tend[nt++] = p;
  }
  int arrow = -1;
  for (int i = 0; i < nt; i++) if (tend[i] - tok[i] == 2 && tok[i][0] == '=' && tok[i][1] == '>') { arrow = i; break; }
  if (arrow < 2 || arrow + 1 >= nt) { note_unparsed(line, e); return; }
  long long pid, tid; bool ok;
  parse_dec(tok[0], tend[0], pid, ok);
  if (!ok) { note_unparsed(line, e); return; }
  int fi = 1;
  bool ok2;
  parse_dec(tok[1], tend[1], tid, ok2);
  if (ok2 && tend[1] - tok[1] > 0 && (tok[1][0] == '-' || (tok[1][0] >= '0' && tok[1][0] <= '9')) && arrow > 2) fi = 2; else tid = pid;
  uint64_t ip, addr;
  if (parse_hex(tok[arrow - 1], tend[arrow - 1], ip) != tend[arrow - 1] ||
      parse_hex(tok[arrow + 1], tend[arrow + 1], addr) != tend[arrow + 1]) { note_unparsed(line, e); return; }
  bool tr_strt = false, tr_end = false;
  int kind = -1;  // 0 jcc, 1 jmp, 2 call, 3 return, 4 async/hw int (ip not executed), 5 other far
  std::string farname;
  for (int i = fi; i < arrow - 1; i++) {
    const char* s = tok[i]; size_t n = (size_t)(tend[i] - tok[i]);
    if (n == 2 && !memcmp(s, "tr", 2)) {
      if (i + 1 < arrow - 1) {
        const char* s2 = tok[i + 1]; size_t n2 = (size_t)(tend[i + 1] - tok[i + 1]);
        if (n2 == 4 && !memcmp(s2, "strt", 4)) tr_strt = true;
        else if (n2 == 3 && !memcmp(s2, "end", 3)) tr_end = true;
        i++;
      }
      continue;
    }
    if (s[0] == '(') continue;  // "(x)" transaction state
    if (n == 3 && !memcmp(s, "jcc", 3)) kind = 0;
    else if (n == 3 && !memcmp(s, "jmp", 3)) kind = 1;
    else if (n == 4 && !memcmp(s, "call", 4)) kind = 2;
    else if (n == 6 && !memcmp(s, "return", 6)) kind = 3;
    else if ((n == 5 && !memcmp(s, "async", 5)) || (n == 2 && !memcmp(s, "hw", 2))) { kind = 4; farname = "async"; if (n == 2) { farname = "hw_int"; i++; } }
    else { kind = 5; if (!farname.empty()) farname += "_"; farname.append(s, n); }
  }
  S.pt_branches++;
  g_cur = S.pt_branches;
  long long tkey = ((long long)pid << 32) ^ (tid & 0xffffffffLL);
  ThreadState& th = g_threads[tkey];
  PidState* ps = pid > 0 ? &pid_state((int)pid) : nullptr;
  if (ps) ps->units++;
  if (tr_strt) {  // "tr strt 0 => X": tracing (re)starts at X
    S.pt_trace_start++;
    th.resume = addr; th.valid = addr != 0;
  } else if (tr_end) {  // "tr end <why> X => 0": tracing stops at X
    S.pt_trace_end++;
    if (ip) {
      // async/interrupt: X is the next instruction, NOT executed; syscall & co: X executed
      bool executed = kind != 4;
      if (th.valid) {
        if (executed) pt_range((int)pid, ps, th.resume, ip);
        else if (ip > th.resume) pt_range((int)pid, ps, th.resume, ip - 1);
      }
      if (executed) add_line(resolve(ip, (int)pid, ps).key);
      if (kind >= 0 && kind <= 3) S.pt_near_no_target++;
      else if (kind == 5) { S.far_entries++; add_far(resolve(ip, (int)pid, ps).key, 0, type_from_name(farname.data(), farname.size())); }
    }
    th.valid = false;
  } else if (ip) {
    if (th.valid) pt_range((int)pid, ps, th.resume, ip); else S.pt_no_resume++;
    Res rf = resolve(ip, (int)pid, ps);
    if (rf.unmapped && !rf.kern) S.unmapped_entries++;
    g_objs[key_obj(rf.key)].entries++;
    S.entries++;
    add_line(rf.key);
    if (addr) {
      Res rt = resolve(addr, (int)pid, ps);
      if (rt.unmapped && !rt.kern) S.unmapped_entries++;
      add_line(rt.key);
      if (kind >= 0 && kind <= 3) {
        static const uint8_t kmap[4] = {T_COND, T_JMP_UNK, T_CALL_UNK, T_RET};
        S.near_entries++;
        add_near(rf.key, rt.key, kmap[kind]);
      } else {
        S.far_entries++;
        if (farname.empty()) farname = "other";
        add_far(rf.key, rt.key, type_from_name(farname.data(), farname.size()));
      }
      th.resume = addr; th.valid = true;
    } else {
      S.zero_entries++;
      th.valid = false;
    }
  } else {
    S.zero_entries++;
  }
  if (g_snap_every && S.pt_branches % g_snap_every == 0) snapshot();
}

static void on_pt_error(const char* line, const char* e) {
  // " instruction trace error type 1 time ... cpu 3 pid 123 tid 123 ip 0x... code 6: ..."
  S.pt_trace_errors++;
  const char* pp = find_str(line, e, " pid ");
  const char* tp = find_str(line, e, " tid ");
  if (pp && tp) {
    long long pid, tid; bool a, b;
    parse_dec(pp + 5, e, pid, a); parse_dec(tp + 5, e, tid, b);
    if (a && b) { auto it = g_threads.find(((long long)pid << 32) ^ (tid & 0xffffffffLL)); if (it != g_threads.end()) it->second.valid = false; return; }
  }
  for (auto& kv : g_threads) kv.second.valid = false;  // unknown thread: distrust every resume point
}

// ---- PT post-processing: direct vs indirect from the instruction bytes ------------------------
// PT reports "jmp"/"call" without saying whether they were indirect. For file-backed code the
// canonical offset IS the file offset, so the branch's own bytes can be read from the file
// (inode checked) and decoded; [vdso] is read from this process's own vdso (same kernel).
static int decode_branch(const uint8_t* b, int n) {
  int i = 0;
  while (i < n && (b[i] == 0x26 || b[i] == 0x2e || b[i] == 0x36 || b[i] == 0x3e || b[i] == 0x64 || b[i] == 0x65 ||
                   b[i] == 0x66 || b[i] == 0x67 || b[i] == 0xf0 || b[i] == 0xf2 || b[i] == 0xf3)) i++;
  if (i < n && (b[i] & 0xf0) == 0x40) i++;  // REX
  if (i >= n) return -1;
  uint8_t op = b[i];
  if (op == 0xe8) return T_CALL;
  if (op == 0xe9 || op == 0xeb) return T_UNCOND;
  if (op == 0xff && i + 1 < n) {
    int reg = (b[i + 1] >> 3) & 7;
    if (reg == 2) return T_IND_CALL;
    if (reg == 4) return T_IND;
  }
  return -1;
}

static void pt_classify() {
  struct Src { int fd = -1; bool tried = false; const uint8_t* mem = nullptr; uint64_t memlen = 0; };
  std::vector<Src> src(g_objs.size());
  uint64_t vdso_base = getauxval(AT_SYSINFO_EHDR), vdso_len = 0;
  if (vdso_base) {
    FILE* f = fopen("/proc/self/maps", "r");
    char buf[512];
    while (f && fgets(buf, sizeof buf, f)) {
      if (strstr(buf, "[vdso]")) { unsigned long long s, e2; if (sscanf(buf, "%llx-%llx", &s, &e2) == 2 && s == vdso_base) vdso_len = e2 - s; }
    }
    if (f) fclose(f);
  }
  for (auto& b : g_br.s) {
    if (!b.key || (b.type != T_JMP_UNK && b.type != T_CALL_UNK)) continue;
    uint32_t o = key_obj(b.key);
    Obj& ob = g_objs[o];
    Src& s = src[o];
    if (!s.tried) {
      s.tried = true;
      if (ob.kind == K_FILE) {
        struct stat st;
        if (stat(ob.path.c_str(), &st) == 0 && (ob.inode == 0 || (uint64_t)st.st_ino == ob.inode)) s.fd = open(ob.path.c_str(), O_RDONLY);
      } else if (ob.kind == K_SPECIAL && ob.path == "[vdso]" && vdso_len) {
        s.mem = (const uint8_t*)vdso_base; s.memlen = vdso_len;
      }
    }
    uint8_t bytes[16]; int n = 0;
    uint64_t off = key_off(b.key);
    if (s.fd >= 0) { ssize_t r = pread(s.fd, bytes, sizeof bytes, (off_t)off); n = r > 0 ? (int)r : 0; }
    else if (s.mem && off < s.memlen) { n = (int)std::min<uint64_t>(16, s.memlen - off); memcpy(bytes, s.mem + off, (size_t)n); }
    if (!n) { S.pt_class_unreadable++; continue; }
    int t = decode_branch(bytes, n);
    bool fits = (b.type == T_JMP_UNK && (t == T_UNCOND || t == T_IND)) || (b.type == T_CALL_UNK && (t == T_CALL || t == T_IND_CALL));
    if (!fits) { S.pt_class_mismatch++; continue; }
    b.type = (uint8_t)t;
    S.pt_classified++;
  }
  for (auto& s : src) if (s.fd >= 0) close(s.fd);
  for (auto& e : g_edges.s) {
    if (!e.from || (e.type != T_JMP_UNK && e.type != T_CALL_UNK)) continue;
    bool ins; BrSlot* b = g_br.find(e.from, ins);
    e.type = b->type;
  }
}

// ---------------------------------------------------------------------------------------------
// Output
struct JW {  // minimal JSON writer
  std::string s;
  bool need_comma = false;
  void raw(const std::string& x) { s += x; }
  void comma() { if (need_comma) s += ","; need_comma = false; }
  static std::string esc(const std::string& x) {
    std::string o = "\"";
    for (unsigned char c : x) {
      if (c == '"' || c == '\\') { o += '\\'; o += (char)c; }
      else if (c < 0x20) { char b[8]; snprintf(b, sizeof b, "\\u%04x", c); o += b; }
      else o += (char)c;
    }
    return o + "\"";
  }
  void key(const std::string& k) { comma(); s += "\n" + esc(k) + ": "; }
  void kv(const std::string& k, const std::string& v) { key(k); s += esc(v); need_comma = true; }
  void kvn(const std::string& k, uint64_t v) { key(k); s += std::to_string(v); need_comma = true; }
  void kvi(const std::string& k, long long v) { key(k); s += std::to_string(v); need_comma = true; }
  void kvd(const std::string& k, double v) { key(k); s += num(v); need_comma = true; }
  void kvnull(const std::string& k) { key(k); s += "null"; need_comma = true; }
  static std::string num(double v) {
    if (!std::isfinite(v)) return "null";
    char b[64]; snprintf(b, sizeof b, "%.10g", v); return b;
  }
  void open(const std::string& k) { key(k); s += "{"; need_comma = false; }
  void close() { s += "}"; need_comma = true; }
};

static std::string hex(uint64_t v) { char b[32]; snprintf(b, sizeof b, "0x%" PRIx64, v); return b; }
static uint64_t print_off(uint64_t k) {  // kernel offsets are printed as the full kernel VA
  return key_obj(k) == g_kernel_obj ? key_off(k) + kKernBase : (key_obj(k) == g_vsyscall_obj ? key_off(k) + kVsyscall : key_off(k));
}

static int usage() {
  fprintf(stderr,
          "usage: perf script ... | lbr_footprint [--mode lbr|pt] [--summary F] [--edges F] [--objects F]\n"
          "         [--lines F] [--analyzer-sha SHA] [--meta k=v]... [--snapshot-every N] [--input F]\n"
          "         [--no-pt-classify] [--version]\n");
  return 2;
}

int main(int argc, char** argv) {
  std::string mode = "lbr", f_summary, f_edges, f_objects, f_lines, analyzer_sha = "unknown", f_input;
  std::vector<std::pair<std::string, std::string>> meta;
  bool pt_classify_on = true;
  for (int i = 1; i < argc; i++) {
    std::string a = argv[i];
    auto val = [&](std::string& dst) { if (i + 1 >= argc) exit(usage()); dst = argv[++i]; };
    if (a == "--mode") val(mode);
    else if (a == "--summary") val(f_summary);
    else if (a == "--edges") val(f_edges);
    else if (a == "--objects") val(f_objects);
    else if (a == "--lines") val(f_lines);
    else if (a == "--analyzer-sha") val(analyzer_sha);
    else if (a == "--input") val(f_input);
    else if (a == "--snapshot-every") { std::string v; val(v); g_snap_every = strtoull(v.c_str(), nullptr, 10); }
    else if (a == "--no-pt-classify") pt_classify_on = false;
    else if (a == "--meta") {
      std::string v; val(v);
      size_t eq = v.find('=');
      if (eq == std::string::npos) return usage();
      meta.emplace_back(v.substr(0, eq), v.substr(eq + 1));
    } else if (a == "--version") { printf("lbr_footprint %s src_sha256 %s\n", kVersion, SRC_SHA256); return 0; }
    else return usage();
  }
  if (mode != "lbr" && mode != "pt") return usage();
  const bool pt = mode == "pt";
  if (!g_snap_every) g_snap_every = pt ? 1000000 : 1000;
  init_hex();
  g_kernel_obj = intern_obj(K_KERNEL, "[kernel]", 0);
  g_vsyscall_obj = intern_obj(K_SPECIAL, "[vsyscall]", 0);

  int fd = 0;
  if (!f_input.empty()) { fd = open(f_input.c_str(), O_RDONLY); if (fd < 0) { perror(f_input.c_str()); return 2; } }
  auto t0 = std::chrono::steady_clock::now();

  // Stream the input in large chunks; a partial last line is carried to the next chunk.
  const size_t kBuf = 8 << 20;
  std::vector<char> buf(kBuf + 1);
  size_t have = 0;
  for (;;) {
    ssize_t r = read(fd, buf.data() + have, kBuf - have);
    if (r < 0) { if (errno == EINTR) continue; perror("read"); return 2; }
    S.input_bytes += (uint64_t)r;
    size_t len = have + (size_t)r;
    const char* p = buf.data();
    const char* end = p + len;
    bool eof = r == 0;
    for (;;) {
      const char* nl = (const char*)memchr(p, '\n', (size_t)(end - p));
      if (!nl) {
        if (eof && p < end) nl = end; else break;
      }
      const char* e = nl;
      if (e > p && e[-1] == '\r') e--;
      S.input_lines++;
      const char* q = skip_ws(p, e);
      if (q < e) {
        // Side-band events can carry any prefix ("0", "pid", "pid/tid"), so look for the tag
        // in the first few tokens rather than assuming a column.
        const char* ev = nullptr;
        const char* lim = std::min(e, q + 48);
        for (const char* c = q; c + 12 <= lim; c++) if (*c == 'P' && !memcmp(c, "PERF_RECORD_", 12)) { ev = c; break; }
        if (ev) on_event(p, ev, e);
        else if (pt) {
          if (find_str(q, std::min(e, q + 64), "error")) on_pt_error(q, e);
          else on_pt_line(q, e);
        } else {
          long long pid; bool ok;
          const char* a = parse_dec(q, e, pid, ok);
          if (ok && (a == e || *a == ' ' || *a == '\t')) on_lbr_sample((int)pid, a, e);
          else note_unparsed(q, e);
        }
      }
      p = nl + (nl < end ? 1 : 0);
      if (p >= end) break;
    }
    have = (size_t)(end - p);
    if (have && p != buf.data()) memmove(buf.data(), p, have);
    if (eof) break;
    if (have == kBuf) { note_unparsed(buf.data(), buf.data() + 200); have = 0; }  // absurd line
  }
  if (fd > 0) close(fd);
  if (pt && pt_classify_on) pt_classify();
  double secs = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
  const uint64_t units = pt ? S.pt_branches : S.samples;
  if (g_snaps.empty() || g_snaps.back().unit != units) snapshot();

  // ---- final metrics ----
  // per class (0 all, 1 noret, 2 indirect) x scope (0 total, 1 user, 2 kernel)
  double sc[3][3] = {{0}}, sct[3][3] = {{0}};
  std::vector<uint64_t> by_type[3];
  for (auto& v : by_type) v.assign(g_type_names.size(), 0);
  std::vector<uint64_t> obj_br(g_objs.size(), 0), obj_lines(g_objs.size(), 0), near_by_type(T_FAR0, 0);
  for (auto& b : g_br.s) {
    if (!b.key) continue;
    int scope = is_kernel_key(b.key) ? 2 : 1;
    double C = (double)b.C, CT = (double)b.C * b.T;
    bool cls[3] = {true, b.type != T_RET, is_indirect(b.type)};
    for (int c = 0; c < 3; c++) if (cls[c]) { sc[c][0] += C; sct[c][0] += CT; sc[c][scope] += C; sct[c][scope] += CT; }
    by_type[0][b.type]++; by_type[scope][b.type]++;
    near_by_type[b.type] += b.C;  // after PT classification, so types are final
    obj_br[key_obj(b.key)]++;
  }
  for (size_t i = 0; i < g_lines.keys.size(); i++) if (g_lines.keys[i]) obj_lines[key_obj(g_lines.keys[i])]++;
  auto wavg = [&](int c, int s) { return sc[c][s] > 0 ? sct[c][s] / sc[c][s] : NAN; };

  // Sampling-robust companions of metric 3, from the per-target counts n_t of each branch's
  // edges (n = sum n_t = C_b). T_b is a unique count, so from samples it is a lower bound that
  // misses rare targets (a hot return with 100 targets showed 20 in 8 k sampled entries); both
  // companions are frequency weighted, which sampling estimates without that bias:
  //   E_b = effective number of targets (inverse Simpson) 1 / sum_t p_t^2, with the unbiased
  //         sum n_t(n_t-1) / (n(n-1)) for sum p^2 from samples (lbr) and the plug-in
  //         sum (n_t/n)^2 from exact counts (pt); E_b = 1 if n = 1; capped at T_b (which also
  //         covers an estimate of 0, i.e. every target seen once);
  //   G_b = max(1, #{t : n_t / n >= 1 %}).
  // Both are weighted by C_b like the literal metric: weff = sum C_b*E_b / sum C_b, etc.
  double sce[3][3] = {{0}}, scg[3][3] = {{0}};
  {
    std::vector<std::pair<uint64_t, uint64_t>> ev;  // (canonical from, count) of every near edge
    ev.reserve(g_edges.n);
    for (auto& e : g_edges.s) if (e.from) ev.emplace_back(e.from, e.count);
    std::sort(ev.begin(), ev.end());
    for (size_t i = 0; i < ev.size();) {
      size_t k = i;
      long double n = 0, snn1 = 0, sn2 = 0;
      uint64_t T = 0, nn = 0;
      for (; k < ev.size() && ev[k].first == ev[i].first; k++) {
        long double c = (long double)ev[k].second;
        n += c; snn1 += c * (c - 1); sn2 += c * c; T++; nn += ev[k].second;
      }
      uint64_t G = 0;
      for (size_t q = i; q < k; q++) if (ev[q].second * 100 >= nn) G++;
      if (G < 1) G = 1;
      double E;
      if (nn <= 1) E = 1;
      else {
        long double sp2 = pt ? sn2 / (n * n) : snn1 / (n * (n - 1));
        E = sp2 > 0 ? (double)(1.0L / sp2) : (double)T;
        if (E > (double)T) E = (double)T;
      }
      bool ins;
      BrSlot* b = g_br.find(ev[i].first, ins);
      int scope = is_kernel_key(b->key) ? 2 : 1;
      double C = (double)b->C;
      bool cls[3] = {true, b->type != T_RET, is_indirect(b->type)};
      for (int c = 0; c < 3; c++) if (cls[c]) {
        sce[c][0] += C * E; sce[c][scope] += C * E;
        scg[c][0] += C * (double)G; scg[c][scope] += C * (double)G;
      }
      i = k;
    }
  }
  auto weff = [&](int c, int s) { return sc[c][s] > 0 ? sce[c][s] / sc[c][s] : NAN; };
  auto wge1 = [&](int c, int s) { return sc[c][s] > 0 ? scg[c][s] / sc[c][s] : NAN; };

  JW j;
  j.raw("{");
  j.kv("analyzer", "lbr_footprint");
  j.kv("analyzer_version", kVersion);
  j.kv("analyzer_sha", analyzer_sha);
  j.kv("analyzer_src_sha256", SRC_SHA256);
  j.kv("mode", mode);
  j.open("meta");
  for (auto& m : meta) j.kv(m.first, m.second);
  j.close();
  j.kvn("footprint_bytes", 64 * g_lines.n);
  j.kvn("footprint_bytes_user", 64 * g_lines_user);
  j.kvn("footprint_bytes_kernel", 64 * g_lines_kern);
  j.kvn("footprint_lines", g_lines.n);
  j.kvn("unique_taken_branches", g_br.n);
  j.kvn("unique_taken_branches_user", g_br_user);
  j.kvn("unique_taken_branches_kernel", g_br_kern);
  const char* scope_name[3] = {"", "_user", "_kernel"};
  const char* cls_name[3] = {"wavg_targets_all", "wavg_targets_noret", "wavg_targets_indirect"};
  for (int c = 0; c < 3; c++) for (int s = 0; s < 3; s++) j.kvd(std::string(cls_name[c]) + scope_name[s], wavg(c, s));
  const char* cls_short[3] = {"all", "noret", "indirect"};
  for (int c = 0; c < 3; c++) for (int s = 0; s < 3; s++) j.kvd(std::string("weff_targets_") + cls_short[c] + scope_name[s], weff(c, s));
  for (int c = 0; c < 3; c++) for (int s = 0; s < 3; s++) j.kvd(std::string("wavg_targets_ge1pct_") + cls_short[c] + scope_name[s], wge1(c, s));
  const char* scope_key[3] = {"all", "user", "kernel"};
  j.open("unique_taken_branches_by_type");
  for (int s = 0; s < 3; s++) {
    j.open(scope_key[s]);
    for (size_t t = 0; t < T_FAR0; t++) if (by_type[s][t] || t < T_JMP_UNK) j.kvn(g_type_names[t], by_type[s][t]);
    j.close();
  }
  j.close();
  j.open("taken_entries_by_type");
  for (size_t t = 0; t < T_FAR0; t++) if (near_by_type[t] || t < T_JMP_UNK) j.kvn(g_type_names[t], near_by_type[t]);
  j.close();
  j.open("far_transfers");
  j.kvn("entries", S.far_entries);
  j.kvn("unique_from", g_far_from.n);
  j.open("entries_by_type");
  for (size_t t = T_FAR0; t < g_far_by_type.size(); t++) if (g_far_by_type[t]) j.kvn(g_type_names[t], g_far_by_type[t]);
  j.close();
  j.close();

  // convergence: exact unique counts at 25/50/75/100 % (from first-seen), wavg from the
  // nearest snapshot at or before that point
  j.open("convergence");
  j.key("points"); j.raw("["); j.need_comma = false;
  uint64_t q_at[4];
  struct QP { uint64_t lines, lu, br, bu; };
  QP qp[4] = {};
  for (int qi = 0; qi < 4; qi++) q_at[qi] = (uint64_t)std::ceil(units * (qi + 1) / 4.0);
  for (size_t i = 0; i < g_lines.keys.size(); i++) {
    uint64_t k = g_lines.keys[i]; if (!k) continue;
    bool kern = is_kernel_key(k);
    for (int qi = 0; qi < 4; qi++) if (g_lines.first[i] <= q_at[qi]) { qp[qi].lines++; if (!kern) qp[qi].lu++; }
  }
  for (auto& b : g_br.s) {
    if (!b.key) continue;
    bool kern = is_kernel_key(b.key);
    for (int qi = 0; qi < 4; qi++) if (b.first <= q_at[qi]) { qp[qi].br++; if (!kern) qp[qi].bu++; }
  }
  for (int qi = 0; qi < 4; qi++) {
    const Snap* sn = nullptr;
    for (auto& s : g_snaps) if (s.unit <= q_at[qi]) sn = &s;
    if (qi) j.raw(",");
    j.raw("{"); j.need_comma = false;
    j.kvn("pct", (uint64_t)(25 * (qi + 1)));
    j.kvn(pt ? "branches" : "samples", q_at[qi]);
    j.kvn("footprint_bytes", 64 * qp[qi].lines);
    j.kvn("footprint_bytes_user", 64 * qp[qi].lu);
    j.kvn("footprint_bytes_kernel", 64 * (qp[qi].lines - qp[qi].lu));
    j.kvn("unique_taken_branches", qp[qi].br);
    j.kvn("unique_taken_branches_user", qp[qi].bu);
    j.kvn("unique_taken_branches_kernel", qp[qi].br - qp[qi].bu);
    if (sn && sn->sumC) j.kvd("wavg_targets_all", (double)sn->sumCT / sn->sumC); else j.kvnull("wavg_targets_all");
    j.raw("}"); j.need_comma = false;
  }
  j.raw("]"); j.need_comma = true;
  auto growth = [](uint64_t a75, uint64_t a100) { return a100 ? 100.0 * (double)(a100 - a75) / (double)a100 : NAN; };
  double gl = growth(qp[2].lines, qp[3].lines), gb = growth(qp[2].br, qp[3].br);
  j.open("last_quarter_growth_pct");
  j.kvd("footprint", gl); j.kvd("unique_taken_branches", gb);
  j.kvd("footprint_user", growth(qp[2].lu, qp[3].lu)); j.kvd("unique_taken_branches_user", growth(qp[2].bu, qp[3].bu));
  j.close();
  j.kv("note", "share of the final unique count first seen in the last 25 % of the run; well above 0 means "
               "the unique counts are still rising, i.e. sampling-limited lower bounds");
  j.kv("unit", pt ? "branches" : "samples");
  j.kvn("snapshot_every", g_snap_every);
  j.key("curve_columns"); j.raw("[\"units\",\"footprint_lines\",\"footprint_lines_user\",\"unique_taken_branches\",\"unique_taken_branches_user\",\"wavg_targets_all\"]"); j.need_comma = true;
  j.key("curve"); j.raw("[");
  {
    size_t ns = g_snaps.size(), step = ns > 100 ? (ns + 99) / 100 : 1;
    bool first = true;
    for (size_t i = 0; i < ns; i++) {
      if (i % step && i + 1 != ns) continue;
      const Snap& s = g_snaps[i];
      if (!first) j.raw(",");
      first = false;
      j.raw("[" + std::to_string(s.unit) + "," + std::to_string(s.lines) + "," + std::to_string(s.lines_user) + "," +
            std::to_string(s.br) + "," + std::to_string(s.br_user) + "," + (s.sumC ? JW::num((double)s.sumCT / s.sumC) : "null") + "]");
    }
  }
  j.raw("]"); j.need_comma = true;
  j.close();

  // top objects
  auto top = [&](const char* name, bool by_lines) {
    std::vector<uint32_t> ids;
    for (uint32_t i = 1; i < g_objs.size(); i++) if (obj_lines[i] || g_objs[i].entries) ids.push_back(i);
    std::sort(ids.begin(), ids.end(), [&](uint32_t a, uint32_t b) {
      uint64_t va = by_lines ? obj_lines[a] : g_objs[a].entries, vb = by_lines ? obj_lines[b] : g_objs[b].entries;
      return va != vb ? va > vb : a < b;
    });
    if (ids.size() > 20) ids.resize(20);
    j.key(name); j.raw("["); j.need_comma = false;
    for (size_t k = 0; k < ids.size(); k++) {
      const Obj& o = g_objs[ids[k]];
      if (k) j.raw(",");
      j.raw("{"); j.need_comma = false;
      j.kvn("obj_id", ids[k]); j.kv("kind", kKindName[o.kind]); j.kv("path", o.path);
      if (o.kind == K_ANON) j.kvi("pid", o.pid);
      j.kvn("footprint_bytes", 64 * obj_lines[ids[k]]);
      j.kvd("footprint_share", g_lines.n ? (double)obj_lines[ids[k]] / g_lines.n : NAN);
      j.kvn("entries", o.entries);
      j.kvd("entries_share", S.entries ? (double)o.entries / S.entries : NAN);
      j.kvn("unique_taken_branches", obj_br[ids[k]]);
      j.raw("}"); j.need_comma = false;
    }
    j.raw("]"); j.need_comma = true;
  };
  {  // which processes the samples (branches) belong to: shows wrapper processes, and in PT
     // mode whether the decoder separated the processes at all
    std::vector<std::pair<uint64_t, int>> v;
    for (auto& kv : g_pids) if (kv.second.units) v.emplace_back(kv.second.units, kv.first);
    std::sort(v.begin(), v.end(), [](const std::pair<uint64_t, int>& a, const std::pair<uint64_t, int>& b) { return a.first != b.first ? a.first > b.first : a.second < b.second; });
    j.kvn("processes_with_samples", v.size());
    j.key("top_processes"); j.raw("["); j.need_comma = false;
    for (size_t k = 0; k < v.size() && k < 20; k++) {
      if (k) j.raw(",");
      j.raw("{"); j.need_comma = false;
      j.kvi("pid", v[k].second); j.kv("comm", g_pids[v[k].second].comm);
      j.kvn(pt ? "branches" : "samples", v[k].first);
      j.kvd("share", units ? (double)v[k].first / units : NAN);
      j.raw("}"); j.need_comma = false;
    }
    j.raw("]"); j.need_comma = true;
  }
  top("top_objects_by_footprint", true);
  top("top_objects_by_entries", false);

  uint64_t disc = S.disc_cross_map + S.disc_negative + S.disc_too_long + S.disc_unmapped;
  j.open("diagnostics");
  j.kvn("samples", pt ? S.pt_branches : S.samples);
  if (!pt) j.kvn("samples_empty", S.samples_empty);
  j.kvn("entries", S.entries);
  j.kvn("near_entries", S.near_entries);
  j.kvn("far_entries", S.far_entries);
  j.kvn("zero_address_entries", S.zero_entries);
  j.kvn("unmapped_entries", S.unmapped_entries);
  j.kvn("kernel_unmapped_entries", S.kernel_unmapped_entries);
  j.kvn("candidate_ranges", S.candidate_ranges);
  j.kvn("discontinuities", disc);
  j.kvd("discontinuity_rate", S.candidate_ranges ? (double)disc / S.candidate_ranges : NAN);
  j.open("discontinuities_by_reason");
  j.kvn("cross_mapping", S.disc_cross_map); j.kvn("negative", S.disc_negative);
  j.kvn(pt ? "over_1MiB" : "over_4096", S.disc_too_long); j.kvn("unmapped_end", S.disc_unmapped);
  j.close();
  j.kvn("range_lines_added", S.range_lines);
  j.kvn("lost_samples", S.lost_events + S.lost_samples);
  j.kvn("lost_from_PERF_RECORD_LOST", S.lost_events);
  j.kvn("lost_from_PERF_RECORD_LOST_SAMPLES", S.lost_samples);
  j.kvn("lost_records", S.lost_records);
  j.kvn("lost_records_unparsed", S.lost_unparsed);
  j.kvn("unparsed_lines", S.unparsed);
  j.key("unparsed_examples"); j.raw("["); for (size_t i = 0; i < S.unparsed_examples.size(); i++) j.raw((i ? "," : "") + JW::esc(S.unparsed_examples[i])); j.raw("]"); j.need_comma = true;
  j.kvn("type_conflicts", S.type_conflicts);
  j.kvn("offset_overflow", S.offset_overflow);
  j.kvn("mmap_events", S.mmap_events); j.kvn("mmap_kernel", S.mmap_kernel); j.kvn("mmap_nonexec_ignored", S.mmap_nonexec);
  j.kvn("comm_exec_events", S.comm_exec); j.kvn("fork_process_events", S.fork_proc); j.kvn("fork_thread_events", S.fork_thread);
  j.kvn("exit_events", S.exit_events); j.kvn("other_events", S.other_events);
  j.kvn("pids_tracked", g_pids.size());
  j.kvn("objects_total", g_objs.size() - 1);
  j.kvn("unique_edges", g_edges.n);
  j.kvn("unique_far_edges", g_far_edges.n);
  if (pt) {
    j.kvn("pt_branch_records", S.pt_branches); j.kvn("pt_trace_errors", S.pt_trace_errors);
    j.kvn("pt_trace_starts", S.pt_trace_start); j.kvn("pt_trace_ends", S.pt_trace_end);
    j.kvn("pt_branch_without_resume_point", S.pt_no_resume); j.kvn("pt_near_branch_without_target", S.pt_near_no_target);
    j.kvn("pt_jmp_call_sites_classified", S.pt_classified); j.kvn("pt_jmp_call_sites_unreadable", S.pt_class_unreadable);
    j.kvn("pt_jmp_call_sites_decode_mismatch", S.pt_class_mismatch);
  }
  j.kvn("input_bytes", S.input_bytes); j.kvn("input_lines", S.input_lines);
  j.kvd("elapsed_s", secs);
  j.kvd(pt ? "branches_per_s" : "samples_per_s", secs > 0 ? units / secs : NAN);
  j.kvd("input_MB_per_s", secs > 0 ? S.input_bytes / secs / 1e6 : NAN);
  j.close();
  j.raw("\n}\n");

  auto open_out = [](const std::string& f) -> FILE* {
    FILE* o = fopen(f.c_str(), "w");
    if (!o) { perror(f.c_str()); exit(2); }
    setvbuf(o, nullptr, _IOFBF, 1 << 20);
    return o;
  };
  if (!f_summary.empty()) { FILE* o = open_out(f_summary); fputs(j.s.c_str(), o); fclose(o); }
  if (!f_objects.empty()) {
    FILE* o = open_out(f_objects);
    fprintf(o, "obj_id\tkind\tpath\tinode\tpid\n");
    for (uint32_t i = 1; i < g_objs.size(); i++) {
      if (!obj_lines[i] && !g_objs[i].entries) continue;
      const Obj& ob = g_objs[i];
      fprintf(o, "%u\t%s\t%s\t%" PRIu64 "\t%d\n", i, kKindName[ob.kind], ob.path.c_str(), ob.inode, ob.kind == K_ANON ? ob.pid : -1);
    }
    fclose(o);
  }
  if (!f_lines.empty()) {
    std::vector<std::pair<uint64_t, uint64_t>> v;
    v.reserve(g_lines.n);
    for (size_t i = 0; i < g_lines.keys.size(); i++) if (g_lines.keys[i]) v.emplace_back(g_lines.keys[i], g_lines.first[i]);
    std::sort(v.begin(), v.end());
    FILE* o = open_out(f_lines);
    fprintf(o, "obj\tline_off\tfirst_seen\n");
    for (auto& x : v) fprintf(o, "%u\t0x%" PRIx64 "\t%" PRIu64 "\n", key_obj(x.first), print_off(x.first), x.second);
    fclose(o);
  }
  if (!f_edges.empty()) {
    std::vector<const EdgeSlot*> v;
    v.reserve(g_edges.n + g_far_edges.n);
    for (auto& e : g_edges.s) if (e.from) v.push_back(&e);
    for (auto& e : g_far_edges.s) if (e.from) v.push_back(&e);
    std::sort(v.begin(), v.end(), [](const EdgeSlot* a, const EdgeSlot* b) { return a->from != b->from ? a->from < b->from : a->to < b->to; });
    FILE* o = open_out(f_edges);
    fprintf(o, "from_obj\tfrom_off\tto_obj\tto_off\ttype\tcount\tfirst_seen\n");
    for (auto* e : v) {
      bool noto = e->to == 1;  // far transfer with no target (PT "tr end")
      fprintf(o, "%u\t0x%" PRIx64 "\t%u\t%s\t%s\t%" PRIu64 "\t%" PRIu64 "\n", key_obj(e->from), print_off(e->from),
              noto ? 0u : key_obj(e->to), noto ? "-" : hex(print_off(e->to)).c_str(), g_type_names[e->type].c_str(), e->count, e->first);
    }
    fclose(o);
  }
  fprintf(stderr,
          "lbr_footprint %s mode=%s %s=%" PRIu64 " entries=%" PRIu64 " footprint=%" PRIu64 " B (user %" PRIu64
          ", kernel %" PRIu64 ") unique_taken=%" PRIu64 " wavg_all=%.4f noret=%.4f ind=%.4f weff_all=%.4f noret=%.4f"
          " ind=%.4f ge1pct_all=%.4f noret=%.4f ind=%.4f disc_rate=%.4f unparsed=%" PRIu64
          " lost=%" PRIu64 " %.2f s (%.0f %s/s, %.0f MB/s)\n",
          kVersion, mode.c_str(), pt ? "branches" : "samples", units, S.entries, 64 * g_lines.n, 64 * g_lines_user,
          64 * g_lines_kern, g_br.n, wavg(0, 0), wavg(1, 0), wavg(2, 0), weff(0, 0), weff(1, 0), weff(2, 0),
          wge1(0, 0), wge1(1, 0), wge1(2, 0),
          S.candidate_ranges ? (double)disc / S.candidate_ranges : 0.0, S.unparsed, S.lost_events + S.lost_samples, secs,
          secs > 0 ? units / secs : 0.0, pt ? "branches" : "samples", secs > 0 ? S.input_bytes / secs / 1e6 : 0.0);
  return 0;
}
