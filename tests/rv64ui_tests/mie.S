#
# Test that the 'MSTATUS.MIE' bit controls global trap availability,
# and that the 'MIE' CSR can enable software-triggered exceptions.
#
# Note: This is not part of the standard `riscv-tests`, and it
# is not an accurate reflection of the specification.
# In particular, it tests that the CPU saves and restores its
# registers when traps are entered and exited, which is NOT required.
#

#include "riscv_test.h"
#include "test_macros.h"

RVTEST_RV64U
RVTEST_CODE_BEGIN

  # Test that a trap cannot be triggered by software while
  # interrupts are disabled globally.
  csrw mscratch, x0
  ecall
  TEST_CASE(2, a3, 0x00000000, csrr a3, mscratch)

  # Set the 'MSTATUS.MIE' bit to enable interrupts globally.
  li a0, MSTATUS_MIE
  csrs mstatus, a0
  # Set the 'MIE.MS' bit to enable machine-mode software traps.
  li a0, 0x00000008
  csrs mie, a0
  # Test that the bits were actually set.
  TEST_CASE(3, a3, MSTATUS_MIE, csrr a3, mstatus; and a3, a3, a0)
  TEST_CASE(4, a3, 0x00000008, csrr a3, mie)

  # Write a value to 'a1' before triggering an exception.
  # The exception will write to 'a1' too, but this CPU should
  # contain logic to automatically save and restore its registers.
  # The RISC-V spec does NOT require that, but I like that ARM cores
  # do it and it's annoying how GD32Vs make you do it in software.
  li a1, 0xDEADBEEF
  # Clear MSCRATCH, then trigger a trap.
  csrw mscratch, x0
  ecall
  # Verify that the interrupt occurred by reading MSCRATCH.
  TEST_CASE(5, a3, 0x0C0FFEE0, csrr a3, mscratch)
  # Ensure that the CPU switched contexts entering/exiting the trap.
  # Again, this is NOT required by the RISC-V spec; I'm just
  # testing the behavior for this implementation.
  TEST_CASE(6, a1, 0xDEADBEEF, nop)

  TEST_PASSFAIL

  # Define a trap handler.
  # (The test code assumes this address won't be 0, so put it at the end...)
  .global mtvec_handler
  mtvec_handler:
    # Load a value into MSCRATCH for the upcoming test case.
    li a1, 0x0C0FFEE0
    csrw mscratch, a1
    # Done, return from the interrupt.
    mret

RVTEST_CODE_END

  .data
RVTEST_DATA_BEGIN

  TEST_DATA

RVTEST_DATA_END
