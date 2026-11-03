/* v1_regions.S — hand-placed code with a known layout for gate V1 (synthetic truth) of the
 * front-end footprint contract (docs/handoff/execution/frontend_footprint_method.md §5).
 *
 * Everything between ffv1_begin and ffv1_end runs once per call of ffv1_iter (the C driver
 * calls it N times), so every executed line, every taken-branch site, its taken count per
 * iteration and its distinct-target count follow from this file plus the built binary's
 * layout (objdump/nm), independently of the analyzer. check_v1.py derives them.
 *
 *   ffv1_iter  driver: call a; call b (REPB times, loop); call c; ret
 *   (a) ffv1_a_blk0..7  straight-line region: NBLK blocks of BLK_LINES full 64 B lines of
 *       single-byte nops, each ending in a 5-byte `jmp` to the next block (the last in `ret`),
 *       so each straight-line run is BLK_LINES*64-5 = 2555 B < 4096 B and no branch
 *       straddles a line.
 *   (b) ffv1_b  three indirect call sites with KNOWN schedules (tables in .rodata, entries
 *       are 32-bit offsets from the table so the code stays position independent):
 *         site K=1  : 3 calls per ffv1_b call (loop), always ffv1_t1_0
 *         site K=4  : 1 call, 8-entry schedule {0,0,0,0,1,1,2,3}       (non-uniform)
 *         site K=16 : 2 calls (loop), 32-entry schedule {0 x17, 1..15} (non-uniform)
 *       every target is a lone `ret` in its own 64 B line.
 *   (c) ffv1_c  500 distinct always-taken conditional branches: ZF is set once, then
 *       500 x { jz over a never-executed int3 }.
 * Only caller-saved registers are used, so the C caller needs no special care.
 */
#define NBLK 8
#define BLK_LINES 40
#define BLK_BYTES (BLK_LINES * 64)
#define REPB 8
#define NCOND 500

	.text
	.balign 4096
	.globl ffv1_begin
ffv1_begin:

	.globl ffv1_iter
	.type ffv1_iter, @function
ffv1_iter:
	call ffv1_a
	mov $REPB, %r9d
.Lb_loop:
	call ffv1_b
	dec %r9d
	jnz .Lb_loop
	call ffv1_c
	ret

/* ---- (a) straight-line blocks ---------------------------------------------------------- */
	.balign 64
	.globl ffv1_a
ffv1_a:
.macro BLOCK cur, next
\cur:
	.fill BLK_BYTES - 5, 1, 0x90
	.byte 0xe9			/* jmp rel32: always 5 bytes, ends exactly at a line edge */
	.long \next - . - 4
.endm
	BLOCK ffv1_a_blk0, ffv1_a_blk1
	BLOCK ffv1_a_blk1, ffv1_a_blk2
	BLOCK ffv1_a_blk2, ffv1_a_blk3
	BLOCK ffv1_a_blk3, ffv1_a_blk4
	BLOCK ffv1_a_blk4, ffv1_a_blk5
	BLOCK ffv1_a_blk5, ffv1_a_blk6
	BLOCK ffv1_a_blk6, ffv1_a_blk7
ffv1_a_blk7:
	.fill BLK_BYTES - 1, 1, 0x90
	ret

/* ---- (b) indirect call sites ------------------------------------------------------------ */
	.balign 64
	.globl ffv1_b
ffv1_b:
	mov $3, %r8d			/* site K=1: 3 calls */
.Ls1_loop:
	lea ffv1_t1_0(%rip), %rcx
	call *%rcx
	dec %r8d
	jnz .Ls1_loop

	mov ffv1_ctr4(%rip), %edx	/* site K=4: 1 call, schedule index = ctr4++ & 7 */
	lea 1(%rdx), %eax
	mov %eax, ffv1_ctr4(%rip)
	and $7, %edx
	lea ffv1_sched4(%rip), %rcx
	movslq (%rcx,%rdx,4), %rax
	add %rcx, %rax
	call *%rax

	mov $2, %r8d			/* site K=16: 2 calls, schedule index = ctr16++ & 31 */
.Ls16_loop:
	mov ffv1_ctr16(%rip), %edx
	lea 1(%rdx), %eax
	mov %eax, ffv1_ctr16(%rip)
	and $31, %edx
	lea ffv1_sched16(%rip), %rcx
	movslq (%rcx,%rdx,4), %rax
	add %rcx, %rax
	call *%rax
	dec %r8d
	jnz .Ls16_loop
	ret

.macro TARGET name
	.balign 64
\name:
	ret
.endm
	TARGET ffv1_t1_0
	TARGET ffv1_t4_0
	TARGET ffv1_t4_1
	TARGET ffv1_t4_2
	TARGET ffv1_t4_3
	TARGET ffv1_t16_0
	TARGET ffv1_t16_1
	TARGET ffv1_t16_2
	TARGET ffv1_t16_3
	TARGET ffv1_t16_4
	TARGET ffv1_t16_5
	TARGET ffv1_t16_6
	TARGET ffv1_t16_7
	TARGET ffv1_t16_8
	TARGET ffv1_t16_9
	TARGET ffv1_t16_10
	TARGET ffv1_t16_11
	TARGET ffv1_t16_12
	TARGET ffv1_t16_13
	TARGET ffv1_t16_14
	TARGET ffv1_t16_15

/* ---- (c) always-taken conditional branches --------------------------------------------- */
	.balign 64
	.globl ffv1_c
ffv1_c:
	xor %eax, %eax			/* ZF = 1 for every jz below (jz does not touch flags) */
	.rept NCOND
	jz 1f
	int3				/* never executed */
1:
	.endr
	ret
	.globl ffv1_end
ffv1_end:

/* ---- schedules and counters ------------------------------------------------------------ */
	.section .rodata
	.balign 64
	.globl ffv1_sched4
ffv1_sched4:
	.long ffv1_t4_0 - ffv1_sched4, ffv1_t4_0 - ffv1_sched4, ffv1_t4_0 - ffv1_sched4, ffv1_t4_0 - ffv1_sched4
	.long ffv1_t4_1 - ffv1_sched4, ffv1_t4_1 - ffv1_sched4, ffv1_t4_2 - ffv1_sched4, ffv1_t4_3 - ffv1_sched4
	.size ffv1_sched4, 32
	.balign 64
	.globl ffv1_sched16
ffv1_sched16:
	.rept 17
	.long ffv1_t16_0 - ffv1_sched16
	.endr
	.long ffv1_t16_1 - ffv1_sched16, ffv1_t16_2 - ffv1_sched16, ffv1_t16_3 - ffv1_sched16
	.long ffv1_t16_4 - ffv1_sched16, ffv1_t16_5 - ffv1_sched16, ffv1_t16_6 - ffv1_sched16
	.long ffv1_t16_7 - ffv1_sched16, ffv1_t16_8 - ffv1_sched16, ffv1_t16_9 - ffv1_sched16
	.long ffv1_t16_10 - ffv1_sched16, ffv1_t16_11 - ffv1_sched16, ffv1_t16_12 - ffv1_sched16
	.long ffv1_t16_13 - ffv1_sched16, ffv1_t16_14 - ffv1_sched16, ffv1_t16_15 - ffv1_sched16
	.size ffv1_sched16, 128

	.data
	.balign 64
ffv1_ctr4:	.long 0
ffv1_ctr16:	.long 0

	.section .note.GNU-stack, "", @progbits
