# V1 synthetic program. -O1 is enough: the measured code is hand-written assembly, the C
# file only loops. -g0 keeps objdump output to the regions' own symbols.
CC     ?= gcc
CFLAGS ?= -O1 -g0

v1_synth: v1_synth.c v1_regions.S Makefile
	$(CC) $(CFLAGS) -o $@ v1_synth.c v1_regions.S

clean:
	rm -f v1_synth

.PHONY: clean
