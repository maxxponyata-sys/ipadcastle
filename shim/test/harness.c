/*
 * Runs shim_main from a real payload under qemu-aarch64 with a fake iPad 6
 * boot_args, then checks what it did. Built and run by shim/test/run.sh.
 *
 *   harness <payload> <shim_main offset> <patched-dtb-out>
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>

#define SZ_2M 0x200000UL

struct ret { uint64_t entry, dtb; };

int main(int argc, char **argv)
{
	if (argc != 4)
		return 2;
	FILE *f = fopen(argv[1], "rb");
	fseek(f, 0, SEEK_END);
	long size = ftell(f);
	rewind(f);

	/* Deliberately 16K- but not 2M-aligned, like a pongoOS alloc_contig. */
	uint8_t *region = mmap(NULL, size + 4 * SZ_2M, PROT_READ | PROT_WRITE | PROT_EXEC,
			       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	uint8_t *base = (uint8_t *)((((uintptr_t)region + SZ_2M - 1) & ~(SZ_2M - 1)) + 0x4000);
	if (fread(base, 1, size, f) != (size_t)size)
		return 2;
	fclose(f);

	uint64_t img_file = *(uint64_t *)(base + 0xff00 + 8);
	uint8_t *orig = malloc(img_file);
	memcpy(orig, base + 0x20000, img_file);

	uint32_t w = 1536, h = 2048, stride = 1536 * 4;
	uint8_t *fb = calloc(1, (size_t)stride * h);
	uint8_t ba[0x400] = { 0 };
	*(uint64_t *)(ba + 16) = 0x804000000ULL;          /* physBase */
	*(uint64_t *)(ba + 24) = 0x7a000000ULL;           /* memSize -> mem = 0x7e000000 */
	*(uint64_t *)(ba + 40) = (uintptr_t)fb;
	*(uint64_t *)(ba + 56) = stride;
	*(uint64_t *)(ba + 64) = w;
	*(uint64_t *)(ba + 72) = h;
	*(uint64_t *)(ba + 80) = 0x10000 | 30;            /* 30-bit + flag bits */

	struct ret (*shim_main)(uint64_t, uint64_t) =
		(struct ret (*)(uint64_t, uint64_t))(base + strtoul(argv[2], NULL, 0));
	__builtin___clear_cache((char *)base, (char *)base + 0x10000);
	struct ret r = shim_main((uintptr_t)ba, (uintptr_t)base);

	int fail = 0;
#define CHECK(c, ...) do { if (!(c)) { printf("FAIL: " __VA_ARGS__); puts(""); fail = 1; } else { printf("ok:   " __VA_ARGS__); puts(""); } } while (0)
	CHECK(r.dtb == (uintptr_t)base + 0x10000, "DTB pointer = payload+0x10000");
	CHECK((r.entry & (SZ_2M - 1)) == 0x80000, "kernel at 2 MiB base + 0x80000 (entry %#lx)", (unsigned long)r.entry);
	CHECK(r.entry >= (uintptr_t)base + 0x20000, "kernel moved up, not down");
	CHECK(!memcmp((void *)r.entry, orig, img_file), "kernel bytes intact after move (%lu bytes)", (unsigned long)img_file);	CHECK(*(uint32_t *)fb == 0x3ff << 10, "green band painted (30-bit)");
	CHECK(*(uint32_t *)(fb + (size_t)stride * 24) == 0, "band only 24 rows");

	uint32_t rd_size = *(uint32_t *)(base + 0xff00 + 24);
	uint32_t rd_off = *(uint32_t *)(base + 0xff00 + 28);
	uint64_t rd = rd_size ? (uintptr_t)base + rd_off : 0;
	if (rd_size) {
		CHECK(!memcmp((void *)rd, "\x1f\x8b", 2), "gzip overlay at payload+%#x (%u bytes)", rd_off, rd_size);
		CHECK(r.entry + *(uint64_t *)(orig + 16) <= rd, "kernel (with BSS) ends below the overlay");
	}

	FILE *o = fopen(argv[3], "wb");
	fwrite((void *)r.dtb, 1, *(uint32_t *)(base + 0xff00 + 4), o);
	fclose(o);
	printf("fb=%#lx\n", (unsigned long)(uintptr_t)fb);
	printf("rd=%016lx\n", (unsigned long)rd);
	printf("rdend=%016lx\n", (unsigned long)(rd + rd_size));
	return fail;
}
