/*
 * IpadCastle shim: boots Corellium's Sandcastle kernel from palera1n's
 * pongoOS (which works on iPadOS 15-17 but no longer has a Linux loader).
 *
 * Payload layout (built by tools/mkpayload.py):
 *   0x00000  this shim
 *   0x0ff00  struct payload_hdr
 *   0x10000  device tree (with placeholder cells, patched here)
 *   0x20000  uncompressed arm64 Image, followed by zero padding
 *   rd_off   optional initramfs overlay (gzip cpio), past the room the
 *            kernel needs, unpacked by the kernel over its built-in ramdisk
 *
 * Runs with MMU off, so memory is Device-type: every access must be
 * naturally aligned (built with -mstrict-align, 8-byte copies only).
 */
#include <stdint.h>

#define DTB_OFF   0x10000
#define IMG_OFF   0x20000
#define HDR_OFF   0x0ff00
#define HDR_MAGIC 0x4c534349 /* "ICSL" */
#define DRAM_BASE 0x800000000ULL
#define SZ_2M     0x200000ULL

/* Placeholder cells in the DTB, see dts/J71b-palera1n.dts */
#define PH_MEM_HI   0x1ca50001
#define PH_MEM_LO   0x1ca50002
#define PH_FB_HI    0x1ca50003
#define PH_FB_LO    0x1ca50004
#define PH_FBSZ_HI  0x1ca50005
#define PH_FBSZ_LO  0x1ca50006
#define PH_WIDTH    0x1ca50007
#define PH_HEIGHT   0x1ca50008
#define PH_STRIDE   0x1ca50009
#define PH_RD_HI    0x1ca5000a
#define PH_RD_LO    0x1ca5000b
#define PH_RDEND_HI 0x1ca5000c
#define PH_RDEND_LO 0x1ca5000d
#define PH_TOUCHGEN 0x1ca5000e
#define PH_FORMAT   "ICFMT______" /* 11 chars + NUL, 4-byte aligned in the DTB */

struct payload_hdr {
	uint32_t magic;
	uint32_t dtb_size;
	uint64_t img_file_size;
	uint64_t total_size;
	uint32_t rd_size; /* 0: no overlay, initrd-start = initrd-end = 0 */
	uint32_t rd_off;
	uint32_t touch_gen; /* hx,touch "generation"; 0 means 2 */
	uint32_t reserved;
};

/* iBoot boot_args (packed), offsets as in pongoOS src/kernel/pongo.h */
#define BA_PHYSBASE 16
#define BA_MEMSIZE  24
#define BA_VBASE    40
#define BA_VSTRIDE  56
#define BA_VWIDTH   64
#define BA_VHEIGHT  72
#define BA_VDEPTH   80

static inline uint64_t rd64(uint64_t a) { return *(volatile uint64_t *)a; }
static inline uint32_t be32(uint32_t v) { return __builtin_bswap32(v); }

struct fixup { uint32_t ph; uint32_t val; };

static void patch_cells(uint64_t dtb, uint32_t size, const struct fixup *f, int n)
{
	for (uint64_t p = dtb; p + 4 <= dtb + size; p += 4) {
		volatile uint32_t *w = (volatile uint32_t *)p;
		uint32_t v = be32(*w);
		for (int i = 0; i < n; i++)
			if (v == f[i].ph)
				*w = be32(f[i].val);
	}
}

static void patch_format(uint64_t dtb, uint32_t size, const char *fmt)
{
	static const char ph[] = PH_FORMAT;
	for (uint64_t p = dtb; p + sizeof(ph) <= dtb + size; p += 4) {
		volatile char *s = (volatile char *)p;
		int i = 0;
		while (i < (int)sizeof(ph) && s[i] == ph[i])
			i++;
		if (i != (int)sizeof(ph))
			continue;
		for (i = 0; i < (int)sizeof(ph); i++)
			s[i] = 0;
		for (i = 0; fmt[i]; i++)
			s[i] = fmt[i];
	}
}

/* Paint a band across the top of the screen so a failed boot shows how far
 * it got: blue = shim started, green = about to jump into Linux. */
static void band(uint64_t fb, uint64_t stride, uint64_t rows, uint32_t px)
{
	for (uint64_t a = fb; a < fb + stride * rows; a += 4)
		*(volatile uint32_t *)a = px;
}

/* Returned in x0 (kernel entry) and x1 (DTB) per AAPCS64. */
struct ret { uint64_t entry, dtb; };

struct ret shim_main(uint64_t ba, uint64_t base);

struct ret shim_main(uint64_t ba, uint64_t base)
{
	const struct payload_hdr *hdr = (const struct payload_hdr *)(base + HDR_OFF);
	uint64_t dtb = base + DTB_OFF;
	uint64_t src = base + IMG_OFF;

	uint64_t fb = rd64(ba + BA_VBASE);
	uint64_t stride = rd64(ba + BA_VSTRIDE);
	uint64_t width = rd64(ba + BA_VWIDTH);
	uint64_t height = rd64(ba + BA_VHEIGHT);
	uint64_t depth = rd64(ba + BA_VDEPTH) & 0xff;
	uint64_t fbsize = stride * height;
	/* 30-bit color: 0x3ff blue. 32-bit: 0xff blue. */
	uint32_t blue = depth == 30 ? 0x3ff : 0xff;
	uint32_t green = depth == 30 ? 0x3ff << 10 : 0xff << 8;

	band(fb, stride, 24, blue);

	if (hdr->magic != HDR_MAGIC)
		for (;;)
			;

	uint64_t mem = rd64(ba + BA_PHYSBASE) + rd64(ba + BA_MEMSIZE) - DRAM_BASE;
	uint64_t rd = hdr->rd_size ? base + hdr->rd_off : 0;
	uint64_t rd_end = rd + hdr->rd_size;
	const struct fixup f[] = {
		{ PH_TOUCHGEN, hdr->touch_gen ? hdr->touch_gen : 2 },
		{ PH_RD_HI, rd >> 32 },     { PH_RD_LO, (uint32_t)rd },
		{ PH_RDEND_HI, rd_end >> 32 }, { PH_RDEND_LO, (uint32_t)rd_end },
		{ PH_MEM_HI, mem >> 32 },   { PH_MEM_LO, (uint32_t)mem },
		{ PH_FB_HI, fb >> 32 },     { PH_FB_LO, (uint32_t)fb },
		{ PH_FBSZ_HI, fbsize >> 32 }, { PH_FBSZ_LO, (uint32_t)fbsize },
		{ PH_WIDTH, width },        { PH_HEIGHT, height },
		{ PH_STRIDE, stride },
	};
	patch_cells(dtb, hdr->dtb_size, f, sizeof(f) / sizeof(f[0]));
	patch_format(dtb, hdr->dtb_size, depth == 30 ? "x2r10g10b10" : "a8r8g8b8");

	/* arm64 Image header: text_offset at +8, image_size at +16. The kernel
	 * must sit text_offset above a 2 MiB aligned base; move it up (never
	 * down, so the shim and DTB below it are never overwritten). */
	uint64_t text_offset = rd64(src + 8);
	uint64_t image_size = rd64(src + 16);
	uint64_t dst = ((src - text_offset + SZ_2M - 1) & ~(SZ_2M - 1)) + text_offset;
	uint64_t limit = base + (hdr->rd_size ? hdr->rd_off : hdr->total_size);
	if (dst + image_size > limit)
		for (;;)
			;

	uint64_t len = (hdr->img_file_size + 7) & ~7ULL;
	if (dst != src)
		for (uint64_t off = len; off; off -= 8)
			*(volatile uint64_t *)(dst + off - 8) = *(volatile uint64_t *)(src + off - 8);

	band(fb, stride, 24, green);
	return (struct ret){ dst, dtb };
}
