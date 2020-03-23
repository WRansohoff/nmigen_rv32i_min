#
# Test that the 'MINSTRET' CSR is writable, and ticks up once per
# instruction. Some tests just test that the value is in the right
# range, in the hopes of accounting for assembler differences.
#
# Note: This is not part of the standard `riscv-tests`, and it
# may not be an accurate reflection of the specification.
#

#include "riscv_test.h"
#include "test_macros.h"

RVTEST_RV64U
RVTEST_CODE_BEGIN

  # Make sure that MINSTRET reflects that a number of instructions
  # ran during the startup code sequence.
  TEST_CASE(2, a3, 0, csrr a2, minstret; slti a3, a2, 5)

  # Clear MINSTRET, and make sure that it equals 1 after the
  # following 'CSR read' instruction.
  li a1, 0xFFFFFFFF
  csrc minstret, a1
  TEST_CASE(3, a3, 1, csrr a3, minstret)

  # Clear MINSTRET, and make sure that it equals 1 after the
  # following 'CSR read and clear' instruction.
  csrc minstret, a1
  TEST_CASE(4, a3, 1, csrrc a3, minstret, a1)

  # Ensure that MINSTRET ticks up with the number of instructions
  # which have been execut- uh, "retired". They're on a farm upstate.
  li a4, 7
  csrc minstret, a1
  TEST_INSERT_NOPS_2
  TEST_CASE(5, a3, 3, csrr a3, minstret)
  # Note: the 'TEST_CASE' macro adds a few instructions, including
  # 'LI' pseudo-ops. So just make sure it's greater than 3 + 4 = 7.
  TEST_INSERT_NOPS_3
  TEST_CASE(6, a3, 1, csrr a2, minstret; slt a3, a4, a2)

  TEST_PASSFAIL

RVTEST_CODE_END

  .data
RVTEST_DATA_BEGIN

  TEST_DATA

RVTEST_DATA_END
