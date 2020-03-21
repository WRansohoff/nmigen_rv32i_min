from nmigen import *

from isa import *
from rom import *
from cpu import *

#####################################
# ROM images for CPU test programs: #
#####################################

# "Infinite Loop" program: I think this is the simplest error-free
# application that you could write, equivalent to "while(1){};".
loop_rom = ROM( rom_img( [ JAL( 1, 0x00000 ) ] ) )

# "Run from RAM" program: Make sure that the CPU can jump between
# RAM and ROM memory spaces.
ram_rom = ROM( rom_img ( [
  # Load the starting address of the 'RAM program' into r1.
  LI( 1, 0x20000004 ),
  # Initialize the 'RAM program'.
  LI( 2, 0x20000000 ),
  LI( 3, 0xDEADBEEF ), SW( 2, 3, 0x000 ),
  LI( 3, LITTLE_END( ADDI( 7, 0, 0x0CA ) ) ), SW( 2, 3, 0x004 ),
  LI( 3, LITTLE_END( SLLI( 8, 7, 15 ) ) ), SW( 2, 3, 0x008 ),
  LI( 3, LITTLE_END( JALR( 5, 4, 0x000 ) ) ), SW( 2, 3, 0x00C ),
  # Jump to RAM.
  JALR( 4, 1, 0x000 ),
  # (This is where the program should jump back to.)
  ADDI( 9, 0, 0x123 ),
  # Done; infinite loop.
  JAL( 1, 0x00000 )
] ) )

# "Quick Test" program: this application contains at least one of
# each supported machine code instruction, but it does not perform
# exhaustive tests for any particular instruction.
# (TODO: It doesn't contain at least one of each instruction yet)
quick_rom = ROM( rom_img( [
  # ADDI, ADD (expect r1 = 0x0000123, r2 = 0x0000246)
  ADDI( 1, 0, 0x123 ), ADD( 2, 1, 1 ),
  # BNE (PC should skip over the following dummy data)
  BNE( 0, 1, 0x00A ),
  0xDEADBEEF, 0xDEADBEEF, 0xDEADBEEF, 0xDEADBEEF,
  # BEQ (PC should skip again)
  BEQ( 1, 1, 0x006 ), 0xDEADBEEF, 0xDEADBEEF,
  # BEQ, BNE (PC should not skip ahead.)
  BEQ( 0, 1, 0x0006 ), BNE( 0, 0, 0x0006 ),
  # ANDI, AND (expect r3 = 0x00000101, r4 = 0x00000002)
  ANDI( 3, 1, 0x94D ), AND( 4, 1, 2 ),
  # Jump over some dummy data.
  JAL( 31, 0x00006 ), 0xDEADBEEF, 0xDEADBEEF,
  # ADDI, SUB (expect r5 = -2, r6 = 0x0000125)
  ADDI( 5, 0, 0xFFE ), SUB( 6, 1, 5 ),
  # Done; infinite loop.
  JAL( 1, 0x00000 )
] ) )

#####################################################################
# RISC-V test cases. The assembly files for the 'rv32ui' tests are  #
# identical to the 'rv64ui' ones; 64-bit values are just truncated. #
# They are structured as C preprocessor macro calls; for example,   #
# most immediate test files are a series of `TEST_IMM_OP(...)`s,    #
# which translate to "LI, <operation>, LI, LI, BNE", where the      #
# final "LI / BNE" branches to a "fail" label if the result         #
# doesn't match. I'm going to reduce that to just the first two     #
# "LI, <operation>" instructions, then I'll inspect the result      #
# in the testbench without running the final `TEST_CASE(...)`       #
# macro instructions. I think this is an adequate way to            #
# run the test cases before the CPU can actually run in an FPGA.    #
# Note that "LI" is not an instruction; it is an assembly pseudo-op #
# which translates into multiple instructions that load an entire   #
# 32-bit constant into a register. See the definition in `isa.py`.  #
#####################################################################

# 'ADD' rv32ui tests. (Same as rv64ui tests, with truncated values)
add_img = [
  # Test #2. For some reason, RISC-V test numbering starts at 2.
  # Maybe I'm missing a couple of common shared 'startup' tests?
  LI( 1, 0x00000000 ), LI( 2, 0x00000000 ), ADD( 14, 1, 2 ),
  # Test #3
  LI( 1, 0x00000001 ), LI( 2, 0x00000001 ), ADD( 14, 1, 2 ),
  # Test #4
  LI( 1, 3 ), LI( 2, 7 ), ADD( 14, 1, 2 ),
  # Test #5
  LI( 1, 0x00000000 ), LI( 2, 0xFFFF8000 ), ADD( 14, 1, 2 ),
  # Test #6
  LI( 1, 0x80000000 ), LI( 2, 0x00000000 ), ADD( 14, 1, 2 ),
  # Test #7
  LI( 1, 0x80000000 ), LI( 2, 0xFFFF8000 ), ADD( 14, 1, 2 ),
  # Test #8
  LI( 1, 0x00000000 ), LI( 2, 0x00007FFF ), ADD( 14, 1, 2 ),
  # Test #9
  LI( 1, 0x7FFFFFFF ), LI( 2, 0x00000000 ), ADD( 14, 1, 2 ),
  # Test #10
  LI( 1, 0x7FFFFFFF ), LI( 2, 0x00007FFF ), ADD( 14, 1, 2 ),
  # Test #11
  LI( 1, 0x80000000 ), LI( 2, 0x00007FFF ), ADD( 14, 1, 2 ),
  # Test #12
  LI( 1, 0x7FFFFFFF ), LI( 2, 0xFFFF8000 ), ADD( 14, 1, 2 ),
  # Test #13
  LI( 1, 0x00000000 ), LI( 2, 0xFFFFFFFF ), ADD( 14, 1, 2 ),
  # Test #14
  LI( 1, 0xFFFFFFFF ), LI( 2, 0x00000001 ), ADD( 14, 1, 2 ),
  # Test #15
  LI( 1, 0xFFFFFFFF ), LI( 2, 0xFFFFFFFF ), ADD( 14, 1, 2 ),
  # Test #16
  LI( 1, 0x00000001 ), LI( 2, 0x7FFFFFFF ), ADD( 14, 1, 2 ),
  # Test #17
  LI( 1, 13 ), LI( 2, 11 ), ADD( 1, 1, 2 ),
  # Test #18
  LI( 1, 14 ), LI( 2, 11 ), ADD( 2, 1, 2 ),
  # Test #19
  LI( 1, 13 ), ADD( 1, 1, 1 ),
  # The extra iteration over these 'bypass' tests looks odd,
  # but I think it's supposed to check for data hazards when
  # instructions are pipelined. I haven't implemented anything
  # fancy like that yet, but there you go.
  # Test #20
  LI( 4, 0 ), LI( 1, 13 ), LI( 2, 11 ), ADD( 14, 1, 2 ),
  ADDI( 6, 14, 0 ), ADDI( 4, 4, 1 ), LI( 5, 2 ), BNE( 4, 5, -18 ),
  # Test #21
  LI( 4, 0 ), LI( 1, 14 ), LI( 2, 11 ), ADD( 14, 1, 2 ),
  NOP(),
  ADDI( 6, 14, 0 ), ADDI( 4, 4, 1 ), LI( 5, 2 ), BNE( 4, 5, -20 ),
  # Test #22
  LI( 4, 0 ), LI( 1, 15 ), LI( 2, 11 ), ADD( 14, 1, 2 ),
  NOP(), NOP(),
  ADDI( 6, 14, 0 ), ADDI( 4, 4, 1 ), LI( 5, 2 ), BNE( 4, 5, -22 ),
  # Test #23
  LI( 4, 0 ), LI( 1, 13 ), LI( 2, 11 ),
  ADD( 14, 1, 2 ), ADDI( 4, 4, 1 ), LI( 5, 2 ), BNE( 4, 5, -16 ),
  # Test #24
  LI( 4, 0 ), LI( 1, 14 ), LI( 2, 11 ), NOP(),
  ADD( 14, 1, 2 ), ADDI( 4, 4, 1 ), LI( 5, 2 ), BNE( 4, 5, -18 ),
  # Test #25
  LI( 4, 0 ), LI( 1, 15 ), LI( 2, 11 ), NOP(), NOP(),
  ADD( 14, 1, 2 ), ADDI( 4, 4, 1 ), LI( 5, 2 ), BNE( 4, 5, -20 ),
  # Test #26
  LI( 4, 0 ), LI( 1, 13 ), NOP(), LI( 2, 11 ),
  ADD( 14, 1, 2 ), ADDI( 4, 4, 1 ), LI( 5, 2 ), BNE( 4, 5, -18 ),
  # Test #27
  LI( 4, 0 ), LI( 1, 14 ), NOP(), LI( 2, 11 ), NOP(),
  ADD( 14, 1, 2 ), ADDI( 4, 4, 1 ), LI( 5, 2 ), BNE( 4, 5, -20 ),
  # Test #28
  LI( 4, 0 ), LI( 1, 15 ), NOP(), NOP(), LI( 2, 11 ),
  ADD( 14, 1, 2 ), ADDI( 4, 4, 1 ), LI( 5, 2 ), BNE( 4, 5, -20 ),
  # Test #29
  LI( 4, 0 ), LI( 2, 11 ), LI( 1, 13 ),
  ADD( 14, 1, 2 ), ADDI( 4, 4, 1 ), LI( 5, 2 ), BNE( 4, 5, -16 ),
  # Test #30
  LI( 4, 0 ), LI( 2, 11 ), LI( 1, 14 ), NOP(),
  ADD( 14, 1, 2 ), ADDI( 4, 4, 1 ), LI( 5, 2 ), BNE( 4, 5, -18 ),
  # Test #31
  LI( 4, 0 ), LI( 2, 11 ), LI( 1, 15 ), NOP(), NOP(),
  ADD( 14, 1, 2 ), ADDI( 4, 4, 1 ), LI( 5, 2 ), BNE( 4, 5, -20 ),
  # Test #32
  LI( 4, 0 ), LI( 2, 11 ), NOP(), LI( 1, 13 ),
  ADD( 14, 1, 2 ), ADDI( 4, 4, 1 ), LI( 5, 2 ), BNE( 4, 5, -18 ),
  # Test #33
  LI( 4, 0 ), LI( 2, 11 ), NOP(), LI( 1, 14 ), NOP(),
  ADD( 14, 1, 2 ), ADDI( 4, 4, 1 ), LI( 5, 2 ), BNE( 4, 5, -20 ),
  # Test #34
  LI( 4, 0 ), LI( 2, 11 ), NOP(), NOP(), LI( 1, 15 ),
  ADD( 14, 1, 2 ), ADDI( 4, 4, 1 ), LI( 5, 2 ), BNE( 4, 5, -20 ),
  # Test #35
  LI( 1, 15 ), ADD( 2, 0, 1 ),
  # Test #36
  LI( 1, 32 ), ADD( 2, 1, 0 ),
  # Test #37
  ADD( 1, 0, 0 ),
  # Test #38
  LI( 1, 16 ), LI( 2, 30 ), ADD( 0, 1, 2 ),
  # Done; infinite loop.
  JAL( 1, 0x00000 )
]
add_rom = ROM( rom_img( add_img ) )

# 'ADDI' rv32ui tests. (Same as rv64ui tests, with truncated values)
addi_img = [
  # Test #2
  LI( 1, 0x00000000 ), ADDI( 14, 1, 0x000 ),
  # Test #3
  LI( 1, 0x00000001 ), ADDI( 14, 1, 0x001 ),
  # Test #4
  LI( 1, 0x00000003 ), ADDI( 14, 1, 0x007 ),
  # Test #5
  LI( 1, 0x00000000 ), ADDI( 14, 1, 0x800 ),
  # Test #6
  LI( 1, 0x80000000 ), ADDI( 14, 1, 0x000 ),
  # Test #7
  LI( 1, 0x80000000 ), ADDI( 14, 1, 0x800 ),
  # Test #8
  LI( 1, 0x00000000 ), ADDI( 14, 1, 0x7FF ),
  # Test #9
  LI( 1, 0x7FFFFFFF ), ADDI( 14, 1, 0x000 ),
  # Test #10
  LI( 1, 0x7FFFFFFF ), ADDI( 14, 1, 0x7FF ),
  # Test #11
  LI( 1, 0x80000000 ), ADDI( 14, 1, 0x7FF ),
  # Test #12
  LI( 1, 0x7FFFFFFF ), ADDI( 14, 1, 0x800 ),
  # Test #13
  LI( 1, 0x00000000 ), ADDI( 14, 1, 0xFFF ),
  # Test #14
  LI( 1, 0xFFFFFFFF ), ADDI( 14, 1, 0x001 ),
  # Test #15
  LI( 1, 0xFFFFFFFF ), ADDI( 14, 1, 0xFFF ),
  # Test #16
  LI( 1, 0x7FFFFFFF ), ADDI( 14, 1, 0x001 ),
  # Test #17
  LI( 1, 13 ), ADDI( 1, 1, 11 ),
  # Test #18
  LI( 4, 0 ), LI( 1, 13 ), ADDI( 14, 1, 11 ), ADDI( 6, 14, 0x000 ),
  ADDI( 4, 4, 0x001 ), LI( 5, 2 ), BNE( 4, 5, -14 ),
  # Test #19
  LI( 4, 0 ), LI( 1, 13 ), ADDI( 14, 1, 10 ), ADDI( 6, 14, 0x000 ),
  NOP(),
  ADDI( 4, 4, 0x001 ), LI( 5, 2 ), BNE( 4, 5, -16 ),
  # Test #20
  LI( 4, 0 ), LI( 1, 13 ), ADDI( 14, 1, 9 ), ADDI( 6, 14, 0x000 ),
  NOP(), NOP(),
  ADDI( 4, 4, 0x001 ), LI( 5, 2 ), BNE( 4, 5, -18 ),
  # Test #21
  LI( 4, 0 ), LI( 1, 13 ), ADDI( 14, 1, 11 ),
  ADDI( 4, 4, 0x001 ), LI( 5, 2 ), BNE( 4, 5, -12 ),
  # Test #22
  LI( 4, 0 ), LI( 1, 13 ), ADDI( 14, 1, 10 ), NOP(),
  ADDI( 4, 4, 0x001 ), LI( 5, 2 ), BNE( 4, 5, -14 ),
  # Test #23
  LI( 4, 0 ), LI( 1, 13 ), ADDI( 14, 1, 9 ), NOP(), NOP(),
  ADDI( 4, 4, 0x001 ), LI( 5, 2 ), BNE( 4, 5, -16 ),
  # Test #24
  ADDI( 1, 0, 32 ),
  # Test #25
  LI( 1, 33 ), ADDI( 0, 1, 50 ),
  # Done; infinite loop.
  JAL( 1, 0x00000 )
]
addi_rom = ROM( rom_img( addi_img ) )

########################################
# Expected runtime register values for #
# the CPU test programs defined above: #
########################################

# Expected runtime values for the "Infinite Loop" program.
# Since the application only contains a single 'jump' instruction,
# we can expect the PC to always equal 0 and r1 to hold 0x04 (the
# 'return PC' value) after the first 'jump' instruction is executed.
loop_exp = {
  0: [ { 'r': 'pc', 'e': 0x00000000 } ],
  1: [
       { 'r': 'pc', 'e': 0x00000000 },
       { 'r': 1,   'e': 0x00000004 }
     ],
  2: [
       { 'r': 'pc', 'e': 0x00000000 },
       { 'r': 1,   'e': 0x00000004 }
     ],
  'end': 2
}

# Expected runtime values for the "Run from RAM" test program.
ram_exp = {
  # Starting state: PC = 0 (ROM).
  0:  [ { 'r': 'pc', 'e': 0x00000000 } ],
  # The next 2 instructions should set r1 = 0x20000004
  2:  [ { 'r': 1, 'e': 0x20000004 } ],
  # The next 14 instructions load the short 'RAM program'.
  16: [
        { 'r': 2, 'e': 0x20000000 },
        { 'r': 'RAM%d'%( 0x00 ), 'e': 0xDEADBEEF },
        { 'r': 'RAM%d'%( 0x04 ),
          'e': LITTLE_END( ADDI( 7, 0, 0x0CA ) ) },
        { 'r': 'RAM%d'%( 0x08 ),
          'e': LITTLE_END( SLLI( 8, 7, 15 ) ) },
        { 'r': 'RAM%d'%( 0x0C ),
          'e': LITTLE_END( JALR( 5, 4, 0x000 ) ) }
      ],
  # The next instruction should jump to RAM.
  17: [
        { 'r': 'pc', 'e': 0x20000004 },
        { 'r': 4, 'e': 0x00000044 }
      ],
  # The next two instructions should set r7, r8.
  19: [
        { 'r': 'pc', 'e': 0x2000000C },
        { 'r': 7, 'e': 0x000000CA },
        { 'r': 8, 'e': 0x00650000 }
      ],
  # The next instruction should jump back to ROM address space.
  20: [ { 'r': 'pc', 'e': 0x00000044 } ],
  # Finally, one more instruction should set r9.
  21: [ { 'r': 9, 'e': 0x00000123 } ],
  'end': 22
}

# Expected runtime values for the "Quick Test" program.
# These values are commented in the program above for each operation.
quick_exp = {
  # Starting state: PC = 0.
  0:  [ { 'r': 'pc', 'e': 0x00000000 } ],
  # After the first 'ADD' ops, r0 = 0x00000123 and r1 = 0x00000246.
  2:  [
        { 'r': 'pc', 'e': 0x00000008 },
        { 'r': 1,    'e': 0x00000123 },
        { 'r': 2,    'e': 0x00000246 }
      ],
  # After the next 'BNE' instruction, PC should jump ahead.
  3: [ { 'r': 'pc', 'e': 0x0000001C } ],
  # One more 'BEQ' instruction jumps ahead again.
  4: [ { 'r': 'pc', 'e': 0x00000028 } ],
  # Two more 'BNE/BEQ' instructions should not jump ahead.
  5: [ { 'r': 'pc', 'e': 0x0000002C } ],
  6: [ { 'r': 'pc', 'e': 0x00000030 } ],
  # Two AND operations set r3, r4.
  8: [ { 'r': 3, 'e': 0x00000101 }, { 'r': 4, 'e': 0x00000002 } ],
  # An unconditional jump skips ahead a bit more.
  9: [ { 'r': 'pc', 'e': 0x00000044 } ],
  # Two subtraction operations set r5, r6.
  11: [ { 'r': 5, 'e': -2 }, { 'r': 6, 'e': 0x0000125 } ],
  'end': 52
}

# Expected runtime values for the "ADD instruction" test program.
add_exp = {
  # Standard register tests (r1 = 'a', r2 = 'b', r14 = result)
  # Testcase 2:  0 + 0 = 0
  5:   [
         { 'r': 1,  'e': 0 },
         { 'r': 2,  'e': 0 },
         { 'r': 14, 'e': 0 }
       ],
  # Testcase 3:  1 + 1 = 2
  10:  [
         { 'r': 1,  'e': 1 },
         { 'r': 2,  'e': 1 },
         { 'r': 14, 'e': 2 }
       ],
  # Testcase 4:  3 + 7 = 10
  15:  [
         { 'r': 1,  'e': 3 },
         { 'r': 2,  'e': 7 },
         { 'r': 14, 'e': 10 }
       ],
  # Testcase 5:  0 + 0xFFFF8000 = 0xFFFF8000
  20:  [
         { 'r': 1,  'e': 0x00000000 },
         { 'r': 2,  'e': 0xFFFF8000 },
         { 'r': 14, 'e': 0xFFFF8000 }
       ],
  # Testcase 6:  min + 0 = min
  25:  [
         { 'r': 1,  'e': 0x80000000 },
         { 'r': 2,  'e': 0x00000000 },
         { 'r': 14, 'e': 0x80000000 }
       ],
  # Testcase 7:  min + 0xFFFF800 = 0x7FFF8000
  30:  [
         { 'r': 1,  'e': 0x80000000 },
         { 'r': 2,  'e': 0xFFFF8000 },
         { 'r': 14, 'e': 0x7FFF8000 }
       ],
  # Testcase 8:  0 + 0x00007FFF = 0x00007FFF
  35:  [
         { 'r': 1,  'e': 0x00000000 },
         { 'r': 2,  'e': 0x00007FFF },
         { 'r': 14, 'e': 0x00007FFF }
       ],
  # Testcase 9:  max + 0 = max
  40:  [
         { 'r': 1,  'e': 0x7FFFFFFF },
         { 'r': 2,  'e': 0x00000000 },
         { 'r': 14, 'e': 0x7FFFFFFF }
       ],
  # Testcase 10: max + 0x00007FFF = 0x80007FFE
  45:  [
         { 'r': 1,  'e': 0x7FFFFFFF },
         { 'r': 2,  'e': 0x00007FFF },
         { 'r': 14, 'e': 0x80007FFE }
       ],
  # Testcase 11: min + 0x00007FFF = 0x80007FFF
  50:  [
         { 'r': 1,  'e': 0x80000000 },
         { 'r': 2,  'e': 0x00007FFF },
         { 'r': 14, 'e': 0x80007FFF }
       ],
  # Testcase 12: max + 0xFFFF8000 = 0x7FFF7FFF
  55:  [
         { 'r': 1,  'e': 0x7FFFFFFF },
         { 'r': 2,  'e': 0xFFFF8000 },
         { 'r': 14, 'e': 0x7FFF7FFF }
       ],
  # Testcase 13: 0 + (-1) = -1
  60:  [
         { 'r': 1,  'e': 0x00000000 },
         { 'r': 2,  'e': 0xFFFFFFFF },
         { 'r': 14, 'e': 0xFFFFFFFF }
       ],
  # Testcase 14: -1 + 1 = 0
  65:  [
         { 'r': 1,  'e': 0xFFFFFFFF },
         { 'r': 2,  'e': 0x00000001 },
         { 'r': 14, 'e': 0x00000000 }
       ],
  # Testcase 15: -1 + (-1) = -2
  70:  [
         { 'r': 1,  'e': 0xFFFFFFFF },
         { 'r': 2,  'e': 0xFFFFFFFF },
         { 'r': 14, 'e': 0xFFFFFFFE }
       ],
  # Testcase 16: 1 + max = min
  75:  [
         { 'r': 1,  'e': 0x00000001 },
         { 'r': 2,  'e': 0x7FFFFFFF },
         { 'r': 14, 'e': 0x80000000 }
       ],
  # Source/Destination tests (r1 or r2 double as result register)
  # Testcase 17:
  77:  [ { 'r': 1, 'e': 13 } ],
  80:  [
         { 'r': 1,  'e': 24 },
         { 'r': 2,  'e': 11 }
       ],
  # Testcase 18:
  82:  [ { 'r': 1, 'e': 14 } ],
  84:  [ { 'r': 2, 'e': 11 } ],
  85:  [ { 'r': 2, 'e': 25 } ],
  # Testcase 19:
  87:  [ { 'r': 1, 'e': 13 } ],
  88:  [ { 'r': 1, 'e': 26 } ],
  # 'Destination Bypass' tests:
  # Testcase 20:
  110: [
         { 'r': 6,  'e': 24 },
         { 'r': 14, 'e': 24 }
       ],
  # Testcase 21:
  134: [
         { 'r': 6,  'e': 25 },
         { 'r': 14, 'e': 25 }
       ],
  # Testcase 22:
  160: [
         { 'r': 6,  'e': 26 },
         { 'r': 14, 'e': 26 }
       ],
  # 'Source Bypass' tests:
  # Testcase 23:
  180: [ { 'r': 14, 'e': 24 } ],
  # Testcase 24:
  202: [ { 'r': 14, 'e': 25 } ],
  # Testcase 25:
  226: [ { 'r': 14, 'e': 26 } ],
  # Testcase 26:
  248: [ { 'r': 14, 'e': 24 } ],
  # Testcase 27:
  272: [ { 'r': 14, 'e': 25 } ],
  # Testcase 28:
  296: [ { 'r': 14, 'e': 26 } ],
  # Testcase 29:
  316: [ { 'r': 14, 'e': 24 } ],
  # Testcase 30:
  338: [ { 'r': 14, 'e': 25 } ],
  # Testcase 31:
  362: [ { 'r': 14, 'e': 26 } ],
  # Testcase 32:
  384: [ { 'r': 14, 'e': 24 } ],
  # Testcase 33:
  408: [ { 'r': 14, 'e': 25 } ],
  # Testcase 34:
  432: [ { 'r': 14, 'e': 26 } ],
  # 'Zero Source' tests:
  # Testcase 35:
  435: [ { 'r': 2, 'e': 15 } ],
  # Testcase 36:
  438: [ { 'r': 2, 'e': 32 } ],
  # Testcase 37:
  439: [ { 'r': 1, 'e': 0 } ],
  # 'Zero Destination' tests:
  444: [ { 'r': 0, 'e': 0 } ],
  # Testcase 38:
  'end': 444
}

# Expected runtime values for the "ADDI instruction" test program.
addi_exp = {
  0:   [ { 'r': 'pc', 'e': 0x00000000 } ],
  # Standard immediate tests (r1 = 'a', r14 = result)
  # Testcase 2:  0 + 0 = 0
  3:   [ { 'r': 1, 'e': 0x00000000 }, { 'r': 14, 'e': 0x00000000 } ],
  # Testcase 3:  1 + 1 = 2
  6:   [ { 'r': 1, 'e': 0x00000001 }, { 'r': 14, 'e': 0x00000002 } ],
  # Testcase 4:  3 + 7 = 10
  9:   [ { 'r': 1, 'e': 0x00000003 }, { 'r': 14, 'e': 0x0000000a } ],
  # Testcase 5:  0 + 0x800 = 0xFFFFF800
  12:  [ { 'r': 1, 'e': 0x00000000 }, { 'r': 14, 'e': 0xFFFFF800 } ],
  # Testcase 6:  min + 0 = min
  15:  [ { 'r': 1, 'e': 0x80000000 }, { 'r': 14, 'e': 0x80000000 } ],
  # Testcase 7:  min + 0x800 = 0x7FFFF800
  18:  [ { 'r': 1, 'e': 0x80000000 }, { 'r': 14, 'e': 0x7FFFF800 } ],
  # Testcase 8:  0 + 0x7FF = 0x000007FF
  21:  [ { 'r': 1, 'e': 0x00000000 }, { 'r': 14, 'e': 0x000007FF } ],
  # Testcase 9:  max + 0 = max
  24:  [ { 'r': 1, 'e': 0x7FFFFFFF }, { 'r': 14, 'e': 0x7FFFFFFF } ],
  # Testcase 10: max + 0x7FF = 0x800007FE
  27:  [ { 'r': 1, 'e': 0x7FFFFFFF }, { 'r': 14, 'e': 0x800007FE } ],
  # Testcase 11: min + 0x7FF = 0x800007FF
  30:  [ { 'r': 1, 'e': 0x80000000 }, { 'r': 14, 'e': 0x800007FF } ],
  # Testcase 12: max + 0x800 = 0x7FFFF7FF
  33:  [ { 'r': 1, 'e': 0x7FFFFFFF }, { 'r': 14, 'e': 0x7FFFF7FF } ],
  # Testcase 13: 0 + -1 = -1
  36:  [ { 'r': 1, 'e': 0x00000000 }, { 'r': 14, 'e': 0xFFFFFFFF } ],
  # Testcase 14: -1 + 1 = 0
  39:  [ { 'r': 1, 'e': 0xFFFFFFFF }, { 'r': 14, 'e': 0x00000000 } ],
  # Testcase 15: -1 + -1 = -2
  42:  [ { 'r': 1, 'e': 0xFFFFFFFF }, { 'r': 14, 'e': 0xFFFFFFFE } ],
  # Testcase 16: max + 1 = min
  45:  [ { 'r': 1, 'e': 0x7FFFFFFF }, { 'r': 14, 'e': 0x80000000 } ],
  # Source/Destination tests (r1 = 'a', r1 = result)
  # Testcase 17: 13 + 11 = 24
  47:  [ { 'r': 1, 'e': 13 } ],
  48:  [ { 'r': 1, 'e': 24 } ],
  # 'Destination Bypass' tests with 0, 1, 2 nops:
  # Testcase 18: 13 + 11 = 24
  66:  [ { 'r': 6, 'e': 24 }, { 'r': 14, 'e': 24 } ],
  # Testcase 19: 13 + 10 = 23
  86:  [ { 'r': 6, 'e': 23 }, { 'r': 14, 'e': 23 } ],
  # Testcase 20: 13 + 9 = 22
  108: [ { 'r': 6, 'e': 22 }, { 'r': 14, 'e': 22 } ],
  # 'Source Bypass' tests with 0, 1, 2 nops:
  # Testcase 21: 13 + 11 = 24
  124: [ { 'r': 14, 'e': 24 } ],
  # Testcase 22: 13 + 10 = 23
  142: [ { 'r': 14, 'e': 23 } ],
  # Testcase 23: 13 + 9 = 22
  162: [ { 'r': 14, 'e': 22 } ],
  # 'Zero Source' tests:
  # Testcase 24: 32 + 0 = 32
  163: [ { 'r': 1, 'e': 32 } ],
  # 'Zero Destination' tests:
  166: [ { 'r': 1, 'e': 33 }, { 'r': 0, 'e': 0 } ],
  # Testcase 25: 33 + 50 = 0 (because r0 is always 0)
  'end': 170
}

############################################
# Collected definitions for test programs. #
# These are just arrays with string names, #
# ROM images, and expected runtime values. #
############################################

loop_test    = [ 'inifinite loop test', 'cpu_loop',
                 loop_rom, [], loop_exp ]
ram_pc_test  = [ 'run from RAM test', 'cpu_ram',
                 ram_rom, [], ram_exp ]
quick_test   = [ 'quick test', 'cpu_quick',
                 quick_rom, [], quick_exp ]
addu_test    = [ 'ADD test cases', 'cpu_addu',
                 add_rom, [], add_exp ]
addiu_test   = [ 'ADDI test cases', 'cpu_addiu',
                 addi_rom, [], addi_exp ]
add_mux_test = [ 'ADD/ADDI test cases', 'cpu_mux_add',
                  [ addu_test, addiu_test ] ]

# Multiplexed ROM image for the collected RV32I instruction tests.
from tests.test_roms.rv32i_add import *
from tests.test_roms.rv32i_addi import *
from tests.test_roms.rv32i_and import *
from tests.test_roms.rv32i_andi import *
from tests.test_roms.rv32i_auipc import *
from tests.test_roms.rv32i_beq import *
from tests.test_roms.rv32i_bge import *
from tests.test_roms.rv32i_bgeu import *
from tests.test_roms.rv32i_blt import *
from tests.test_roms.rv32i_bltu import *
from tests.test_roms.rv32i_bne import *
from tests.test_roms.rv32i_csr import *
from tests.test_roms.rv32i_fence_i import *
from tests.test_roms.rv32i_jal import *
from tests.test_roms.rv32i_jalr import *
from tests.test_roms.rv32i_lb import *
from tests.test_roms.rv32i_lbu import *
from tests.test_roms.rv32i_lh import *
from tests.test_roms.rv32i_lhu import *
from tests.test_roms.rv32i_lw import *
from tests.test_roms.rv32i_lui import *
from tests.test_roms.rv32i_or import *
from tests.test_roms.rv32i_ori import *
from tests.test_roms.rv32i_sb import *
from tests.test_roms.rv32i_sh import *
from tests.test_roms.rv32i_sw import *
from tests.test_roms.rv32i_sll import *
from tests.test_roms.rv32i_slli import *
from tests.test_roms.rv32i_slt import *
from tests.test_roms.rv32i_slti import *
from tests.test_roms.rv32i_sltu import *
from tests.test_roms.rv32i_sltiu import *
from tests.test_roms.rv32i_sra import *
from tests.test_roms.rv32i_srai import *
from tests.test_roms.rv32i_srl import *
from tests.test_roms.rv32i_srli import *
from tests.test_roms.rv32i_sub import *
from tests.test_roms.rv32i_xor import *
from tests.test_roms.rv32i_xori import *
rv32i_tests = [ 'RV32I instructions', 'rv32i_tests',
  [
    add_test, addi_test, and_test, andi_test, auipc_test, beq_test,
    bge_test, bgeu_test, blt_test, bltu_test, bne_test, csr_test,
    fence_i_test, jal_test, jalr_test, lb_test, lbu_test, lh_test,
    lhu_test, lw_test, lui_test, or_test, ori_test, sb_test,
    sh_test, sw_test, sll_test, slli_test, slt_test, slti_test,
    sltiu_test, sltu_test, sra_test, srai_test, srl_test, srli_test,
    sub_test, xor_test, xori_test
  ]
]
