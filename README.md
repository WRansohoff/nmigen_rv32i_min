# Minimal `RISC-V` CPU

This is a work-in-progress implementation of [the core `RV32I` `RISC-V` instruction set](https://riscv.org/specifications/isa-spec-pdf/), written with nMigen.

Currently it only runs in the simulator, but I'm planning to add a module to read program data from SPI Flash and get it running on an iCE40 FPGA once the implementation is more complete.

Know that I'm still learning how to use nMigen, and I wasn't experienced with digital logic design to begin with. So on the off chance that anybody stumbles across this, suggestions are always welcome!

# Prerequisites

This project uses [nMigen](https://github.com/nmigen/nmigen), which is a super cool Python 3.x library that lets you describe digital logic circuits. So you'll need to install a recent version of Python, and then you can either build nMigen from source or install it with Pip:

    pip3 install nmigen

# Testbenches

The ALU, CSR, RAM, and ROM Python files each have their own testbench to run some basic unit tests.

The CPU module's testbench runs the standard `rv32i` [`RISC-V` compliance tests](https://github.com/riscv/riscv-compliance).

The `tests/test_roms/` directory contains auto-generated Python files with corresponding machine code instructions in a format that the CPU testbenches can interpret. The auto-generated files are not included in the repository, so you'll need to run the `tests/gen_tests.py` script before you run the CPU testbenches:

    python3 tests/gen_tests.py

To run a module's testbench, just run the corresponding `.py` file:

    python3 cpu.py

Each test simulation also creates a `.vcd` file containing the waveform results, so you can check how each signal changes over time.

# Test Coverage

Note that I've only implemented the most basic exceptions, interrupts don't work, and I'll need to implement some buses before I can add any peripherals. Fortunately, [the `nmigen-soc` repository](https://github.com/nmigen/nmigen-soc) contains a [Wishbone bus implementation](https://opencores.org/howto/wishbone), but I need to do some reading to figure out how that works.

So even though this table of test coverage looks okay, there's plenty more work to do before this CPU can blink an LED.

## Compliance Tests

The remaining failures are down to timing issues caused by some re-writes that were necessary to remove simulator-only syntax.

|   Test Suite    |   Pass / Fail?   |
|:---------------:|:----------------:|
| `ADD`           |:heavy_check_mark:|
| `ADDI`          |:heavy_check_mark:|
| `AND`           |:heavy_check_mark:|
| `ANDI`          |:heavy_check_mark:|
| `AUIPC`         |:heavy_check_mark:|
| `BEQ`           |:heavy_check_mark:|
| `BGE`           |:heavy_check_mark:|
| `BGEU`          |:heavy_check_mark:|
| `BLT`           |:heavy_check_mark:|
| `BLTU`          |:heavy_check_mark:|
| `BNE`           |:heavy_check_mark:|
| `DELAY_SLOTS`   |:heavy_check_mark:|
| `EBREAK`        |:heavy_check_mark:|
| `ECALL`         |:heavy_check_mark:|
| `IO`            |        :x:       |
| `JAL`           |:heavy_check_mark:|
| `JALR`          |:heavy_check_mark:|
| `LB`            |:x:|
| `LBU`           |:x:|
| `LH`            |:x:|
| `LHU`           |:x:|
| `LW`            |:x:|
| `LUI`           |:heavy_check_mark:|
| `MISALIGN_JMP`  |:heavy_check_mark:|
| `MISALIGN_LDST` |:heavy_check_mark:|
| `NOP`           |:x:|
| `OR`            |:heavy_check_mark:|
| `ORI`           |:heavy_check_mark:|
| `RF_SIZE`       |:x:|
| `RF_WIDTH`      |:heavy_check_mark:|
| `RF_X0`         |:heavy_check_mark:|
| `SB`            |:x:|
| `SH`            |:heavy_check_mark:|
| `SW`            |:x:|
| `SLL`           |:heavy_check_mark:|
| `SLLI`          |:heavy_check_mark:|
| `SLT`           |:heavy_check_mark:|
| `SLTI`          |:heavy_check_mark:|
| `SLTIU`         |:heavy_check_mark:|
| `SLTU`          |:heavy_check_mark:|
| `SRA`           |:heavy_check_mark:|
| `SRAI`          |:heavy_check_mark:|
| `SRL`           |:heavy_check_mark:|
| `SRLI`          |:heavy_check_mark:|
| `SUB`           |:heavy_check_mark:|
| `XOR`           |:heavy_check_mark:|
| `XORI`          |:heavy_check_mark:|

# Control and Status Registers

This CPU does not implement User mode, Supervisor mode, or Hypervisor mode. That means all of the code will run in the top-level Machine mode, which still requires a basic subset of the `RISC-V` "Control and Status Registers" (CSRs):

The `MIE` and `MIP` CSRs won't really function properly until I finish implementing interrupts in the CPU.

|    CSR Name     | Logic Implemented? |
|:---------------:|:------------------:|
| `MISA`          | :heavy_check_mark: |
| `MSTATUS`       | :heavy_check_mark: |
| `MTVEC`         | :heavy_check_mark: |
| `MIE`           |         :x:        |
| `MIP`           |         :x:        |
| `MCAUSE`        | :heavy_check_mark: |
| `MSCRATCH`      | :heavy_check_mark: |
| `MEPC`          | :heavy_check_mark: |
| `MTVAL`         | :heavy_check_mark: |
| `MCYCLE`        | :heavy_check_mark: |
| `MINSTRET`      | :heavy_check_mark: |
| `MCOUNTINHIBIT` | :heavy_check_mark: |

# Notes to Self

- The RISC-V spec says that any instruction ending in `0x0000` is illegal; I should build that into the CPU, but I haven't yet.

- I haven't implemented interrupts yet; only some basic exceptions.

- The spec does not define behavior when an unspecified opcode is encountered. For now, I'll just skip to incrementing the PC if that happens. But once I implement traps, it might merit raising an exception.

- I should use `signal.to_signed()` instead of if/else checks for sign extension.

- There's a `Mux(...)` expression which might be able to replace some more of the repetitive 'if/else' logic.
