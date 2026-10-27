/*
 * IpadCastle shim entry. palera1n's pongoOS "bootr" jumps here at EL1 with
 * the MMU and caches off, sp = 0, and x0 = physical address of iBoot's
 * boot_args. The shim is position independent: it runs from wherever
 * pongoOS put the upload buffer.
 */
	.section .text.start, "ax"
	.global _start
_start:
	adr	x9, _start		/* payload base */
	add	sp, x9, #0xf000		/* stack inside the shim area (below the DTB at +0x10000) */
	mov	x1, x9
	bl	shim_main		/* returns kernel entry in x0, DTB in x1 */
	mov	x30, x0
	mov	x0, x1
	mov	x1, xzr
	mov	x2, xzr
	mov	x3, xzr
	dsb	sy
	ic	iallu
	dsb	sy
	isb
	ret
