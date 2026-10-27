CROSS   ?= aarch64-linux-gnu-
CFLAGS  := -Os -ffreestanding -fno-builtin -nostdlib -fpie -mstrict-align \
           -mgeneral-regs-only -fno-stack-protector -fno-tree-loop-distribute-patterns \
           -Wall -Wextra -Werror
LDFLAGS := -nostdlib -static -Wl,-Ttext=0 -Wl,-e,_start -Wl,--build-id=none

shim.bin: shim.elf
	$(CROSS)objcopy -O binary $< $@
	@size=$$(wc -c < $@); [ $$size -le 61440 ] || { echo "shim too big: $$size"; exit 1; }

shim.elf: start.S shim.c
	$(CROSS)gcc $(CFLAGS) $(LDFLAGS) -o $@ start.S shim.c

clean:
	rm -f shim.elf shim.bin
