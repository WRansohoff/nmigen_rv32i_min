# Minimal `RISC-V` CPU

This is a work-in-progress implementation of [the core `RV32I` `RISC-V` instruction set](https://riscv.org/specifications/isa-spec-pdf/), written with nMigen.

Currently it only runs in the simulator, but I'm planning to add a module to read program data from SPI Flash and get it running on an iCE40 FPGA once the implementation is more complete.

Know that I'm still learning how to use nMigen, and I wasn't experienced with digital logic design to begin with. So on the off chance that anybody stumbles across this, suggestions are always welcome!

# Prerequisites

This project uses [nMigen](https://github.com/nmigen/nmigen), which is a super cool Python 3.x library that lets you describe digital logic circuits. So you'll need to install a recent version of Python, and then you can either build nMigen from source or install it with Pip:

    pip3 install nmigen

# Testbenches

The ALU, CSR, RAM, and ROM Python files each have their own testbench to run some basic unit tests.

The CPU module's testbench runs the standard `rv32ui` [`RISC-V` instruction set tests](https://github.com/riscv/riscv-tests) for each operation, compiled with GCC. These tests cover most of the basic `RV32I` instructions, with the exception of `ECALL` and `EBREAK`.

To test `ECALL`, I also included the `RV32SI` `CSR` tests for the most basic 'machine mode' implementation. Even though they currently pass, I haven't implemented all of the core 'machine mode' registers, and the 'ECALL' instruction is incomplete.

The `tests/rv64ui_tests/` directory contains assembly code for those test cases, copied [from the `isa/` directory of the `riscv-tests` repository](https://github.com/riscv/riscv-tests/tree/master/isa). And the `tests/test_roms/` directory contains auto-generated Python files with corresponding machine code instructions in a format that the CPU testbenches can interpret.

The nMigen-compatible tests are generated by the `tests/gen_tests.py` script, which you'll need to run before you run the CPU testbenches:

    python3 tests/gen_tests.py

To run a module's testbench, just run the corresponding `.py` file:

    python3 cpu.py

Each test simulation also creates a `.vcd` file containing the waveform results, so you can check how each signal changes over time.

# Test Coverage

Note: `EBREAK` instructions currently halt or crash the program, depending on your perspective. And `ECALL` instructions are incomplete, but the basic `CSRRx` and `CSRRxI` operations work well enough to run these 'first stage' tests.

I also haven't implemented traps (interrupts and exceptions) yet, and I'll need to implement some buses before I can add any peripherals. Fortunately, [the `nmigen-soc` repository](https://github.com/nmigen/nmigen-soc) contains a [Wishbone bus implementation](https://opencores.org/howto/wishbone), but I need to do some reading to figure out how that works.

So even though this table of test coverage looks okay, there's plenty more work to do before this CPU can blink an LED.

| Instruction |   Pass / Fail?   |
|:-----------:|:----------------:|
| `ADD`       |:heavy_check_mark:|
| `ADDI`      |:heavy_check_mark:|
| `AND`       |:heavy_check_mark:|
| `ANDI`      |:heavy_check_mark:|
| `AUIPC`     |:heavy_check_mark:|
| `BEQ`       |:heavy_check_mark:|
| `BGE`       |:heavy_check_mark:|
| `BGEU`      |:heavy_check_mark:|
| `BLT`       |:heavy_check_mark:|
| `BLTU`      |:heavy_check_mark:|
| `BNE`       |:heavy_check_mark:|
| `CSR`       |:heavy_check_mark:|
| `FENCE`     |:heavy_check_mark:|
| `JAL`       |:heavy_check_mark:|
| `JALR`      |:heavy_check_mark:|
| `LB`        |:heavy_check_mark:|
| `LBU`       |:heavy_check_mark:|
| `LH`        |:heavy_check_mark:|
| `LHU`       |:heavy_check_mark:|
| `LW`        |:heavy_check_mark:|
| `LUI`       |:heavy_check_mark:|
| `OR`        |:heavy_check_mark:|
| `ORI`       |:heavy_check_mark:|
| `SB`        |:heavy_check_mark:|
| `SH`        |:heavy_check_mark:|
| `SW`        |:heavy_check_mark:|
| `SLL`       |:heavy_check_mark:|
| `SLLI`      |:heavy_check_mark:|
| `SLT`       |:heavy_check_mark:|
| `SLTI`      |:heavy_check_mark:|
| `SLTU`      |:heavy_check_mark:|
| `SLTUI`     |:heavy_check_mark:|
| `SRL`       |:heavy_check_mark:|
| `SRLI`      |:heavy_check_mark:|
| `SRA`       |:heavy_check_mark:|
| `SRAI`      |:heavy_check_mark:|
| `SUB`       |:heavy_check_mark:|
| `XOR`       |:heavy_check_mark:|
| `XORI`      |:heavy_check_mark:|

# Control and Status Registers

This CPU does not implement User mode, Supervisor mode, or Hypervisor mode. That means all of the code will run in the top-level Machine mode, which still requires a basic subset of the `RISC-V` "Control and Status Registers" (CSRs):

Some CSRs don't actually need any logic in a very minimal implementation like this one, even though they usually control parts of the CPU. `MISA` is one example of this; since only the core `RV32I` ISA is supported, it doesn't need to be able to enable different extensions or switch between 32-bit and 64-bit modes.

Other CSRs behave as defined in the specification, but they won't really function properly until I implement traps in the CPU. `MIP` and `MEPC` are examples of this.

|    CSR Name     | Logic Implemented? |
|:---------------:|:------------------:|
| `MISA`          | :heavy_check_mark: |
| `MSTATUS`       |         :x:        |
| `MTVEC`         |         :x:        |
| `MIE`           |         :x:        |
| `MIP`           |         :x:        |
| `MCAUSE`        |         :x:        |
| `MSCRATCH`      | :heavy_check_mark: |
| `MEPC`          |         :x:        |
| `MTVAL`         |         :x:        |
| `MCYCLE`        | :heavy_check_mark: |
| `MINSTRET`      | :heavy_check_mark: |
| `MHPMCOUNTERx`  |         :x:        |
| `MHPMCOUNTERxH` |         :x:        |
| `MCOUNTINHIBIT` | :heavy_check_mark: |
| `MHPEVENT`      |         :x:        |

# Notes to Self

- The RISC-V spec says that any instruction ending in `0x0000` is illegal; I should build that into the CPU, but I haven't yet.

- I haven't implemented traps (interrupts / exceptions) yet.

- `ECALL` and `EBREAK` System calls aren't quite working properly yet.

- The spec does not define behavior when an unspecified opcode is encountered. For now, I'll just skip to incrementing the PC if that happens. But once I implement traps, it might merit raising an exception.

- I should use `signal.to_signed()` instead of if/else checks for sign extension.

- There's a `Mux(...)` expression which might be able to replace some more of the repetitive 'if/else' logic.

- Instead of using positive and negative clock edges of the 'sync' domain, I should own up when logic takes more than one tick and split it up between multiple clock cycles.
