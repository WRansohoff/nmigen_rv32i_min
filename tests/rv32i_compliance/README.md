# RV32I compliance test suites

These assembly tests files were copied from the [`riscv-compliance` repository](https://github.com/riscv/riscv-compliance), commit #5a978cfd444d5e640150d46703deda99057b2bbb.

The `Makefile` builds the assembly files using GCC, so that the `gen_tests.py` script one directory up can create testbench simulations out of the compiled machine code. And that was written by me, so don't blame the authors of the `riscv-compliance` repository if it doesn't build things properly :)
