// RISC-V Compliance Test Header File

#ifndef _COMPLIANCE_TEST_H
#define _COMPLIANCE_TEST_H

#include "riscv_test.h"

// Just use the 'TEST_PASSFAIL' macro from
// the 'riscv-tests' repository for now.
#undef RVTEST_PASS
#define RVTEST_PASS              \
        fence;                   \
        li TESTNUM, 1;           \
        li a7, 93;               \
        li a0, 0;                \
        ecall

#undef RVTEST_FAIL
#define RVTEST_FAIL              \
        fence;                   \
1:      beqz TESTNUM, 1b;        \
        sll TESTNUM, TESTNUM, 1; \
        or TESTNUM, TESTNUM, 1;  \
        li a7, 93;               \
        addi a0, TESTNUM, 0;     \
        ecall

#define RV_COMPLIANCE_HALT       \
  bne x0, TESTNUM, pass;         \
  fail:                          \
    RVTEST_FAIL;                 \
  pass:                          \
    RVTEST_PASS                  \

#define RV_COMPLIANCE_RV32M      \
  RVTEST_RV32M                   \

#define RV_COMPLIANCE_CODE_BEGIN \
  RVTEST_CODE_BEGIN              \

#define RV_COMPLIANCE_CODE_END   \
  RVTEST_CODE_END                \

#define RV_COMPLIANCE_DATA_BEGIN \
  RVTEST_DATA_BEGIN              \

#define RV_COMPLIANCE_DATA_END   \
  RVTEST_DATA_END                \

#endif
