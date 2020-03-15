# Minimal `RISC-V` CPU

This is a work-in-progress implementation of [the core `RV32I` `RISC-V` instruction set](https://riscv.org/specifications/isa-spec-pdf/), written with nMigen.

Currently it only runs in the simulator, but I'm planning to add a module to read program data from SPI Flash and get it running on an iCE40 FPGA once the implementation is more complete.

Know that I'm still learning how to use nMigen, and I wasn't experienced with digital logic design to begin with. So on the off chance that anybody stumbles across this, suggestions are always welcome!

# Prerequisites

This project uses [nMigen](https://github.com/nmigen/nmigen), which is a super cool Python 3.x library that lets you describe digital logic circuits. So you'll need to install a recent version of Python, and then you can either build nMigen from source or install it with Pip:

    pip3 install nmigen

# Testbenches

The ALU, RAM, and ROM Python files each have their own testbench to run some basic unit tests.

The CPU module's testbench will eventually run a series of test programs with assembly instructions that match the `rv32ui` [`RISC-V` instruction set tests](https://github.com/riscv/riscv-tests) for each operation. But I'm not even done with a first draft of the CPU, so I haven't implemented those tests yet.

Still, I think the raw assembly code for those test cases can be found [under the `isa/` directory of the `riscv-tests` repository](https://github.com/riscv/riscv-tests/tree/master/isa). The simulated ROM images which match those assembly files will be located in `programs.py` when I write them, but for now there are only a handful of very basic operation tests.

The helper methods which generate machine code instructions are located in `isa.py`, but that file does not contain any tests of its own.

To run a module's tests, just run the corresponding `.py` file, like:

    python3 cpu.py

Each test suite also creates a `.vcd` file containing the waveform results, so you can check how each signal changes over time. The CPU tests produce multiple `.vcd` files; one for each test program.

# Notes to Self

- The RISC-V spec says that any instruction ending in `0x0000` is illegal; I should build that into the CPU, but I haven't yet.

- I haven't implemented traps (interrupts / exceptions) yet.

- The spec does not define behavior when an unspecified opcode is encountered. For now, I'll just skip to incrementing the PC if that happens. But once I implement traps, it might merit raising an exception.

- `FENCE`, `ECALL`, and `EBREAK` instructions will probably be implemented last. And the specification implies that simple designs can get away with combining `ECALL` and `EBREAK` into a single `SYSTEM` instruction, so I might do that.
