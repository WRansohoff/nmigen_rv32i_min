// RISC-V Compliance IO Test Header File
// Target: 'Tubul' RV32I microcontroller core.

#ifndef _COMPLIANCE_IO_H
#define _COMPLIANCE_IO_H

// No I/O is available yet.
#define RVTEST_IO_WRITE_STR( _R, _STR )
#define RVTEST_IO_CHECK()
// No floating point units are available.
#define RVTEST_IO_ASSERT_SFPR_EQ( _F, _R, _I )
#define RVTEST_IO_ASSERT_DFPR_EQ( _D, _R, _I )

// Ensure that 'testnum' is at least 1.
#define RVTEST_IO_INIT \
  li TESTNUM, 1

// Assert that a general-purpose register has a specified value.
// Use the 'TEST_CASE' logic from 'riscv-tests'.
// 'Scratch' input register is not used.
#define RVTEST_IO_ASSERT_GPR_EQ( _G, _R, _I ) \
  li  x7, MASK_XLEN( _I );                    \
  bne _R, x7, fail;

#endif
