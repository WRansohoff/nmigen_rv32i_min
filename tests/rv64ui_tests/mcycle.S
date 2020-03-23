#
# Test that the 'MCYCLE' CSR is writable, and ticks up more than
# once per instruction. Individual clock cycles are not counted,
# out of an effort to make the tests less fragile.
#
# Note: This is not part of the standard `riscv-tests`, and it
# may not be an accurate reflection of the specification.
#

#include "riscv_test.h"
#include "test_macros.h"

RVTEST_RV64U
RVTEST_CODE_BEGIN

  # Make sure that MCYCLE has ticked a number of times
  # over the course of the startup code.
  TEST_CASE(2, a3, 0, csrr a2, mcycle; slti a3, a2, 10 )

  # Clear MCYCLE, and make sure that it is small (<10).
  # It won't be zero, because there is more than one cycle between
  # instructions and CSR reads return the previous value.
  li a1, 0xFFFFFFFF
  csrc mcycle, a1
  TEST_CASE(3, a3, 1, csrr a2, mcycle; slti a3, a2, 10 )

  # Ensure that MCYCLE increases over time.
  csrr a1, mcycle
  TEST_INSERT_NOPS_3
  csrr a2, mcycle
  TEST_CASE(4, a3, 1, slt a3, a1, a2)

  TEST_PASSFAIL

RVTEST_CODE_END

  .data
RVTEST_DATA_BEGIN

  TEST_DATA

RVTEST_DATA_END
