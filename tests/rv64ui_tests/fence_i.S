# See LICENSE for license details.

#*****************************************************************************
# fence_i.S
#-----------------------------------------------------------------------------
#
# Test self-modifying code and the fence.i instruction.
#
# This has been modified from the `riscv-tests` repository to place
# the self-modifying code in RAM, because the simulated CPU program
# storage is read-only. I have a PR out to apply the change upstream,
# but it may not be accepted because the `riscv-tests` repository
# needs to consider a wider range of use cases than simple MCU cores.
# Caveat emptor.
#

#include "riscv_test.h"
#include "test_macros.h"

RVTEST_RV64U
RVTEST_CODE_BEGIN

li a3, 111
lh a0, insn
lh a1, insn+2

# test I$ hit
.align 6
sh a0, 2f, t0
sh a1, 2f+2, t0
fence.i

la a5, 2f
jalr a6, a5, 0
TEST_CASE( 2, a3, 444, nop )

# test prefetcher hit
li a4, 100
1: addi a4, a4, -1
bnez a4, 1b

sh a0, 3f, t0
sh a1, 3f+2, t0
fence.i

.align 6
la a5, 3f
jalr a6, a5, 0
TEST_CASE( 3, a3, 777, nop )

TEST_PASSFAIL

RVTEST_CODE_END

  .data
RVTEST_DATA_BEGIN

  TEST_DATA

insn:
  addi a3, a3, 333

2: addi a3, a3, 222
jalr a5, a6, 0

3: addi a3, a3, 555
jalr a5, a6, 0

RVTEST_DATA_END
