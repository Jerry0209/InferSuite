/* v1_synth.c — driver for gate V1: calls the hand-placed region ffv1_iter (v1_regions.S)
 * N times. N defaults to a count that runs ~4 s on P7, so every branch site in the regions
 * is sampled thousands of times at the contract period (20011).
 *   ./v1_synth [iterations]
 * N is rounded up to a multiple of 4 so that both schedules (8 and 32 calls long; the K=16
 * site runs 16x per iteration) complete whole periods and the per-site target frequencies
 * are exactly the designed ones.
 */
#include <stdio.h>
#include <stdlib.h>

void ffv1_iter(void);

int main(int argc, char **argv) {
	long n = argc > 1 ? atol(argv[1]) : 1800000;
	n = (n + 3) / 4 * 4;
	for (long i = 0; i < n; i++)
		ffv1_iter();
	printf("v1_synth: %ld iterations\n", n);
	return 0;
}
