/* xcheck_calib.c — known-traffic kernels that calibrate the LLC/DRAM cross-check.
 *
 * Every counter the cross-check relies on is checked against traffic we can compute by
 * hand before any SPEC number is trusted:
 *
 *   read  : sequential sum over a 2 GiB array. Every byte comes from DRAM exactly once
 *           per pass, so IMC read CAS x 64 B must equal the bytes the kernel reports and
 *           the IMC write CAS must stay at the idle floor.
 *   write : plain (non-streaming) stores over the same array. Each line is read for
 *           ownership (RFO) and written back later, so IMC reads AND writes should both
 *           track the store bandwidth, while offcore_requests.data_rd (the campaign's
 *           DRAM_read_GBs) should stay near zero: it does not count RFOs.
 *
 * After one first-touch pass over the array (page faults; THP is off) the timed region runs for
 * argv[2] seconds. It prints the region's wall-clock bounds and achieved GB/s on stdout.
 *
 * Build: gcc -O3 -march=native -fno-tree-loop-distribute-patterns -o xcheck_calib xcheck_calib.c
 */
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define N_BYTES (2ULL << 30)

static double now_rt(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "usage: %s read|write seconds\n", argv[0]); return 2; }
    const int wr = !strcmp(argv[1], "write");
    const double secs = atof(argv[2]);
    const size_t n = N_BYTES / sizeof(uint64_t);
    uint64_t *a = aligned_alloc(64, N_BYTES);
    if (!a) { perror("alloc"); return 1; }
    for (size_t i = 0; i < n; i++) a[i] = i;          /* fault every page in */

    uint64_t sum = 0, passes = 0;
    const double t0 = now_rt();
    double t1 = t0;
    while (t1 - t0 < secs) {
        if (wr) {
            const uint64_t v = passes + 1;
            for (size_t i = 0; i < n; i++) a[i] = v + i;
        } else {
            for (size_t i = 0; i < n; i++) sum += a[i];
        }
        passes++;
        t1 = now_rt();
    }
    const double gb = (double)passes * N_BYTES / 1e9;
    printf("mode=%s t_start=%.6f t_end=%.6f passes=%llu bytes=%.0f GBps=%.3f checksum=%llu\n",
           argv[1], t0, t1, (unsigned long long)passes, gb * 1e9, gb / (t1 - t0),
           (unsigned long long)(sum + a[n / 2]));
    free(a);
    return 0;
}
