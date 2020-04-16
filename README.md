# Minimal `RISC-V` CPU

This is a work-in-progress implementation of [the core `RV32I` `RISC-V` instruction set](https://riscv.org/specifications/isa-spec-pdf/), written with nMigen.

It is fairly simple, with no I-cache, timers, or configurable interrupts. But it can read programs out of SPI Flash, and it has a peripheral for basic GPIO and driving 'neopixel' LEDs.

Currently it takes up about 95% of an `iCE40UP5K` depending on recent changes, but it seems to work. I'm hoping to make it smaller so that it can also fit a debugging interface and some more LED peripherals.

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

The RISC-V RV32I compliance tests can be simulated, and they probably all pass. I try to run the full test suite regularly as I make changes, but sometimes a broken commit slips through.

## Compliance Tests

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
| `IO`            |:heavy_check_mark:|
| `JAL`           |:heavy_check_mark:|
| `JALR`          |:heavy_check_mark:|
| `LB`            |:heavy_check_mark:|
| `LBU`           |:heavy_check_mark:|
| `LH`            |:heavy_check_mark:|
| `LHU`           |:heavy_check_mark:|
| `LW`            |:heavy_check_mark:|
| `LUI`           |:heavy_check_mark:|
| `MISALIGN_JMP`  |:heavy_check_mark:|
| `MISALIGN_LDST` |:heavy_check_mark:|
| `NOP`           |:heavy_check_mark:|
| `OR`            |:heavy_check_mark:|
| `ORI`           |:heavy_check_mark:|
| `RF_SIZE`       |:heavy_check_mark:|
| `RF_WIDTH`      |:heavy_check_mark:|
| `RF_X0`         |:heavy_check_mark:|
| `SB`            |:heavy_check_mark:|
| `SH`            |:heavy_check_mark:|
| `SW`            |:heavy_check_mark:|
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

The `MIE` and `MIP` CSRs won't really function properly until I finish implementing interrupts in the CPU. I also haven't added the memory-mapped 'time' CSRs yet.

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
| `MTIME`         |         :x:        |
| `MTIMECMP`      |         :x:        |
| `MCYCLE`        | :heavy_check_mark: |
| `MINSTRET`      | :heavy_check_mark: |
| `MCOUNTINHIBIT` | :heavy_check_mark: |

# Programming

This should work with C programs compiled by GCC for the `RV32I` architecture; just flash the binary image to a 2MByte offset in the board's SPI Flash. See `tests/hw_tests` for a minimal example.

The timing analysis hovers around 11-13MHz without optimizations, so I've been running the core at a sluggish 6MHz for testing. There's also no instruction cache, so programs that run from NVM will spend most of their time waiting for the SPI Flash to return data.

Loading code into RAM and running it there should work, but I've only tested that in the simulator.

# Notes to Self

- The RISC-V spec says that any instruction ending in `0x0000` is illegal; I should build that into the CPU, but I haven't yet.

- I haven't implemented interrupts yet; only the most basic exceptions.

- The spec does not define behavior when an unspecified opcode is encountered. For now, I'll just skip to incrementing the PC if that happens. But it might merit raising an exception.
