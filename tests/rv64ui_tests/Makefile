# GCC toolchain programs.
CC = riscv32-unknown-elf-gcc
OD = riscv32-unknown-elf-objdump

# Assembly directives.
# Don't perform optimizations.
ASFLAGS += -O0
# Report all warnings.
ASFLAGS += -Wall
# Just the core RV32I ISA.
ASFLAGS += -march=rv32i
# No extra startup code.
ASFLAGS += -nostartfiles
ASFLAGS += -nostdlib
ASFLAGS += --specs=nosys.specs
ASFLAGS += -Wl,-Ttubul.ld
# Compilation flags.
ASFLAGS += -D__MACHINE_MODE

# Source files.
SRC  = ./add.S
SRC += ./addi.S
SRC += ./and.S
SRC += ./andi.S
SRC += ./auipc.S
SRC += ./beq.S
SRC += ./bge.S
SRC += ./bgeu.S
SRC += ./blt.S # Mmmm...BLT...
SRC += ./bltu.S
SRC += ./bne.S
SRC += ./csr.S
SRC += ./fence_i.S
SRC += ./jal.S
SRC += ./jalr.S
SRC += ./lb.S
SRC += ./lbu.S
SRC += ./lh.S
SRC += ./lhu.S
SRC += ./lui.S
SRC += ./lw.S
SRC += ./or.S
SRC += ./ori.S
SRC += ./sb.S
SRC += ./sh.S
SRC += ./sll.S
SRC += ./slli.S
SRC += ./slt.S
SRC += ./slti.S
SRC += ./sltu.S
SRC += ./sltiu.S
SRC += ./sra.S
SRC += ./srai.S
SRC += ./srl.S
SRC += ./srli.S
SRC += ./sub.S
SRC += ./sw.S
SRC += ./xor.S
SRC += ./xori.S

# Binary images to build.
OBJS = $(SRC:.S=.o)

# Default rule to build all test files.
.PHONY: all
all: $(OBJS)

# Rule to assemble assembly files.
%.o: %.S
	$(CC) -x assembler-with-cpp $(ASFLAGS) $< -o $@

# Rule to clear out generated build files.
.PHONY: clean
clean:
	rm -f $(OBJS)
