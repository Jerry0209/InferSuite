/* dryload.c — self-contained microkernels for the zero-multiplexing dry-run gate.
 *
 * The InferSuite kit used numpy for these; SPEC's kit should not depend on a conda
 * environment, so the same three semantic probes are compiled from source here.
 *
 *   mixed  : dense FP (vector) + a dependent integer chain. Generic "busy scope"
 *            used to prove every counter group counts at 100% enabled time.
 *   div    : CACHE-RESIDENT divides. Must light up arith.div_active and must NOT
 *            look DRAM-bound — the negative control for the dram_bw group.
 *   stream : ~2 GB sequential sum, guaranteed DRAM-resident. Must light up
 *            offcore_requests.data_rd and must NOT look divider-bound.
 *
 * Each runs for the number of seconds given as argv[2] and prints a checksum so
 * the optimiser cannot delete the work.
 *
 * Build: gcc -O2 -march=native -o dryload dryload.c -lm
 */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static double now_s(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

/* ---- mixed: vector FP over a cache-resident tile + dependent integer chain ---- */
static void k_mixed(double secs) {
    enum { N = 256 };                       /* 3 x 512 KB -> L2/L3 resident */
    static double a[N * N], b[N * N], c[N * N];
    for (int i = 0; i < N * N; i++) { a[i] = i * 1e-3 + 1.0; b[i] = (N * N - i) * 1e-3 + 1.0; }
    unsigned long x = 12345;
    double t0 = now_s();
    while (now_s() - t0 < secs) {
        for (int i = 0; i < N; i++)
            for (int k = 0; k < N; k++) {
                double aik = a[i * N + k];
                for (int j = 0; j < N; j++) c[i * N + j] += aik * b[k * N + j];
            }
        for (int i = 0; i < 2000000; i++) x = (x * 2654435761u + 1) ^ (x >> 13);
    }
    double s = 0; for (int i = 0; i < N * N; i += 977) s += c[i];
    printf("mixed checksum %.6e %lu\n", s, x);
}

/* ---- div: cache-resident divides; negative control for DRAM bandwidth -------- */
static void k_div(double secs) {
    enum { N = 32768 };                     /* 3 x 256 KB -> L2 resident */
    static double a[N], b[N], c[N];
    for (int i = 0; i < N; i++) { a[i] = 1.0 + i * 1e-6; b[i] = 1.0 + (N - i) * 1e-6; }
    double t0 = now_s();
    while (now_s() - t0 < secs)
        for (int rep = 0; rep < 64; rep++)
            for (int i = 0; i < N; i++) c[i] = a[i] / b[i];
    double s = 0; for (int i = 0; i < N; i += 97) s += c[i];
    printf("div checksum %.6e\n", s);
}

/* ---- stream: ~2 GB sequential read; negative control for the divider --------- */
static void k_stream(double secs) {
    size_t n = 256UL * 1024 * 1024;         /* 2 GB of doubles */
    double *x = malloc(n * sizeof(double));
    if (!x) { fprintf(stderr, "stream: out of memory\n"); exit(2); }
    for (size_t i = 0; i < n; i++) x[i] = (double)(i & 1023);
    double s = 0, t0 = now_s();
    while (now_s() - t0 < secs) { double acc = 0; for (size_t i = 0; i < n; i++) acc += x[i]; s += acc; }
    printf("stream checksum %.6e\n", s);
    free(x);
}

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "usage: %s {mixed|div|stream} <seconds>\n", argv[0]); return 1; }
    double secs = atof(argv[2]);
    if      (!strcmp(argv[1], "mixed"))  k_mixed(secs);
    else if (!strcmp(argv[1], "div"))    k_div(secs);
    else if (!strcmp(argv[1], "stream")) k_stream(secs);
    else { fprintf(stderr, "unknown kernel %s\n", argv[1]); return 1; }
    return 0;
}
