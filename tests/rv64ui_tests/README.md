# RV32I test suites

These assembly tests files were copied from the [`riscv-tests` repository](https://github.com/riscv/riscv-tests), commit #272093f3281b54cbf0a14c3ccdd3c0cb47a28fb5.

The assembly and header files come from the `isa/rv64ui_tests` and `env/` directories.

The `Makefile` builds the assembly files using GCC, so that the `gen_tests.py` script one directory up can create testbench simulations out of the compiled machine code. And that was written by me, so don't blame the authors of the `riscv-tests` repository if it doesn't build things properly :)
