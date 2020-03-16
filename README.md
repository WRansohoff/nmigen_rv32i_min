# Minimal `RISC-V` CPU

This is a work-in-progress implementation of [the core `RV32I` `RISC-V` instruction set](https://riscv.org/specifications/isa-spec-pdf/), written with nMigen.

Currently it only runs in the simulator, but I'm planning to add a module to read program data from SPI Flash and get it running on an iCE40 FPGA once the implementation is more complete.

Know that I'm still learning how to use nMigen, and I wasn't experienced with digital logic design to begin with. So on the off chance that anybody stumbles across this, suggestions are always welcome!

# Prerequisites

This project uses [nMigen](https://github.com/nmigen/nmigen), which is a super cool Python 3.x library that lets you describe digital logic circuits. So you'll need to install a recent version of Python, and then you can either build nMigen from source or install it with Pip:

    pip3 install nmigen

# Testbenches

The ALU, RAM, and ROM Python files each have their own testbench to run some basic unit tests.

The CPU module's testbench runs the standard `rv32ui` [`RISC-V` instruction set tests](https://github.com/riscv/riscv-tests) for each operation, compiled with GCC.

Not all of the `RV32I` tests pass, and some of them even crash the simulated CPU. but that's expected; I haven't implemented loads, stores, memory fences, system calls, or traps yet. I had to comment out some of the startup code in `riscv_test.h`, or the simulation wouldn't even make it to the start of the tests...

The `tests/rv64ui_tests/` directory contains assembly code for those test cases, copied [from the `isa/` directory of the `riscv-tests` repository](https://github.com/riscv/riscv-tests/tree/master/isa). And the `tests/test_roms/` directory contains auto-generated Python files containing the corresponding machine code instructions in a format that the CPU testbenches can interpret, and they are generated by the `tests/gen_tests.py` script.

So, before running the CPU tests, you'll need to run:

    python3 tests/gen_tests.py

To run a module's tests, just run the corresponding `.py` file, like:

    python3 cpu.py

Each test suite also creates a `.vcd` file containing the waveform results, so you can check how each signal changes over time. The CPU tests produce multiple `.vcd` files; one for each test program.

# Test Coverage

| Instruction | Pass / Fail? |
|:-----------:|:------------:|
| `ADD`       |:green_heart: |
| `ADDI`      |:green_heart: |
| `AND`       |:green_heart: |
| `ANDI`      |:green_heart: |
| `AUIPC`     |:broken_heart:|
| `BEQ`       |:green_heart: |
| `BGE`       |:broken_heart:|
| `BGEU`      |:broken_heart:|
| `BLT`       |:broken_heart:|
| `BLTU`      |:broken_heart:|
| `BNE`       |:green_heart: |
| `FENCE`     |:broken_heart:|
| `JAL`       |:broken_heart:|
| `JALR`      |:broken_heart:|
| `LB`        |:broken_heart:|
| `LBU`       |:broken_heart:|
| `LH`        |:broken_heart:|
| `LHU`       |:broken_heart:|
| `LW`        |:broken_heart:|
| `LUI`       |:green_heart: |
| `OR`        |:green_heart: |
| `ORI`       |:green_heart: |
| `SB`        |:broken_heart:|
| `SH`        |:broken_heart:|
| `SW`        |:broken_heart:|
| `SLL`       |:broken_heart:|
| `SLLI`      |:green_heart: |
| `SLT`       |:green_heart: |
| `SLTI`      |:green_heart: |
| `SLTU`      |:green_heart: |
| `SLTUI`     |:green_heart: |
| `SRL`       |:broken_heart:|
| `SRLI`      |:green_heart: |
| `SRA`       |:broken_heart:|
| `SRAI`      |:green_heart: |
| `SUB`       |:green_heart: |
| `XOR`       |:green_heart: |
| `XORI`      |:green_heart: |

# Notes to Self

- The RISC-V spec says that any instruction ending in `0x0000` is illegal; I should build that into the CPU, but I haven't yet.

- I haven't implemented traps (interrupts / exceptions) yet.

- `ECALL` and `EBREAK` System calls are currently implemented as "hard faults" which act as an infinite loop.

- `FENCE` instructions are not implemented yet.

- The spec does not define behavior when an unspecified opcode is encountered. For now, I'll just skip to incrementing the PC if that happens. But once I implement traps, it might merit raising an exception.
