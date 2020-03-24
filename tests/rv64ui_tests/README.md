# RV32I test suites

These assembly tests files were copied from the [`riscv-tests` repository](https://github.com/riscv/riscv-tests), commit #272093f3281b54cbf0a14c3ccdd3c0cb47a28fb5.

The assembly and header files come from the `isa/rv64ui_tests` and `env/` directories. `csr.S` comes from `isa/rv64si_tests` instead of `isa/rv64ui_tests`.

The `Makefile` builds the assembly files using GCC, so that the `gen_tests.py` script one directory up can create testbench simulations out of the compiled machine code. And that was written by me, so don't blame the authors of the `riscv-tests` repository if it doesn't build things properly :)

There are also a few tests which are not part of the standard `riscv-tests` files. These perform supplementary tests around things like specific CSR functionality, but they are based on my reading of the specifications and they might not be accurate:

* mcycle.S

* minstret.S

* mie.S

Finally, I changed the last `ecall` instructions to `ebreak`s in `riscv_test.h`, because it looks like the tests disable all interrupts before they run. I could be reading the specification wrong, though.
