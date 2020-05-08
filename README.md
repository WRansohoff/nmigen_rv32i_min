# Minimal `RISC-V` Microcontroller for LEDs.

This is a work-in-progress implementation of [the core `RV32I` `RISC-V` instruction set](https://riscv.org/specifications/isa-spec-pdf/), written with nMigen.

The project's goal is to create an affordable and easy-to-use microcontroller softcore with a focus on lighting applications. The target hardware is an `iCE40UP5K-SG48` FPGA, because of its low cost and hobbyist-friendly QFN packaging. The RV32I `RISC-V` architecture was chosen for its open license and extensive compiler support.

The current design is fairly simple, with no I-cache or timers. It also omits some of the core `RISC-V` "Control and Status Registers" to save space, so it does not strictly comply with the specification. But it works with GCC, it can read programs out of SPI Flash, and it has a few LED-related peripherals.

There's a basic GPIO peripheral, four 'neopixel' LED drivers, and four simple PWM outputs. There's also an I/O multiplexer to configure which peripherals are assigned to which pins.

It uses almost all of the logic cells in an `iCE40UP5K`, but a lot of that comes from the peripherals, and you can configure how many of those are included in the `gpio_mux.py` file. Eventually, I'd like to add other options such as a debugging interface and `SPI` / `UART` / etc.

Know that I'm still learning how to use nMigen, and I wasn't experienced with digital logic design to begin with. So on the off chance that anybody stumbles across this, suggestions are always welcome!

# Prerequisites

This project uses [nMigen](https://github.com/nmigen/nmigen), which is a super cool Python 3.x library that lets you describe digital logic circuits. So you'll need to install a recent version of Python, and then you can either build nMigen from source or install it with Pip:

    pip3 install nmigen

It also requires the [`nmigen-boards`](https://github.com/nmigen/nmigen-boards) and [`nmigen-soc`](https://github.com/nmigen/nmigen-soc) libraries.

To build the design, you'll also need [`yosys`](https://github.com/YosysHQ/yosys) and [`nextpnr-ice40`](https://github.com/YosysHQ/nextpnr). And the [`icestorm`](https://github.com/cliffordwolf/icestorm) toolchain is used to flash the synthesized bitstream onto a development board.

# Testbenches

The ALU, CSR, RAM, and ROM Python files each have their own testbench to run some basic unit tests.

The CPU module's testbench runs the standard `rv32i` [`RISC-V` compliance tests](https://github.com/riscv/riscv-compliance), and it can also be configured to simulate compiled C programs or simple assembly ROM images.

The `tests/test_roms/` directory contains auto-generated Python files with corresponding machine code instructions in a format that the CPU testbenches can interpret. The generated files are not included in the repository, so you'll need to run the `tests/gen_tests.py` script to create them before you run the CPU testbenches:

    python3 tests/gen_tests.py

To run a module's testbench, just run the corresponding `.py` file:

    python3 cpu.py

Each test simulation also creates a `.vcd` file containing the waveform results, so you can check how each signal changes over time.

The compliance tests don't generate a `.vcd` file by default, because they are run in one simulation instance and the resulting waveform file is large (almost 500MB). But you can swap in the commented `with Simulator(...)` line in `cpu.py`'s `cpu_mux_sim` method to change that.

# Test Coverage

The RISC-V RV32I compliance tests are simulated as part of the CPU testbench. They probably all pass except for some CSR-related ones which rely on CSRs that I disabled to save space. I try to run the full test suite regularly as I make changes, but sometimes a broken commit slips through.

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
| `MISALIGN_JMP`  |:x:|
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

This microcontroller CPU does not implement User mode, Supervisor mode, or Hypervisor mode. That means all of the code will run in the top-level Machine mode, which still requires a basic subset of the `RISC-V` "Control and Status Registers" (CSRs).

The `MIE`, `MIP`, `MTIME`, and `MTIMECMP` CSRs are not currently implemented. Interrupts and exceptions also use identical "trap" logic, which is not quite in line with the specification.

Some CSRs which are unlikely to be used in the context of a small microcontroller have also been disabled to save space by commenting them out in `isa.py` (:no_entry:). They will act like other unrecognized CSRs, as read-only registers which always return 0.

Also, the `MSTATUS` CSR also does not implement the `MPP` field, and the `MINSTRET` counter is only 16 bits long. Again, this is to save space.

|    CSR Name     | Logic Implemented? |
|:---------------:|:------------------:|
| `MARCHID`       |     :no_entry:     |
| `MIMPID`        |     :no_entry:     |
| `MHARTID`       |     :no_entry:     |
| `MVENDORID`     |     :no_entry:     |
| `MISA`          |     :no_entry:     |
| `MSTATUS`       | :heavy_check_mark: |
| `MSTATUSH`      |     :no_entry:     |
| `MTVEC`         | :heavy_check_mark: |
| `MIE`           |         :x:        |
| `MIP`           |         :x:        |
| `MCAUSE`        |     :no_entry:     |
| `MSCRATCH`      |     :no_entry:     |
| `MEPC`          | :heavy_check_mark: |
| `MTVAL`         | :heavy_check_mark: |
| `MTIME`         |         :x:        |
| `MTIMECMP`      |         :x:        |
| `MCYCLE`        |     :no_entry:     |
| `MCYCLEH`       |     :no_entry:     |
| `MINSTRET`      | :heavy_check_mark: |
| `MINSTRETH`     |     :no_entry:     |
| `MCOUNTINHIBIT` |     :no_entry:     |

# Building

You can build the design for an "Upduino V2" board by passing `-b` to the `cpu.py` file:

    python3 cpu.py -b

And you can program the resulting design with `iceprog`:

    iceprog build/top.bin

Currently the design will not run faster than 10-12MHz, so you'll need to set `hfosc_div` to either 2 or 3 in the board file if you use the internal oscillator, depending on how the bees arrange the design.

# Programming

This design should be able to run C programs compiled by GCC for the RV32I architecture; just flash the binary image to a 2MByte offset in the board's SPI Flash. See `tests/hw_tests` for some minimal examples.

The timing analysis hovers around 11-13MHz without optimizations, so I've been running the core at a sluggish 6MHz for testing. There's also no instruction cache, so programs that run from NVM will spend most of their time waiting for the SPI Flash to return data.

Loading code into RAM and running it there should work, but I've only tested that in the simulator.

# Notes to Self

- Illegal instructions are currently ignored instead of raising an exception.

- Initialized data sections don't work properly, probably because the RAM module does not perform little-endian conversions.
