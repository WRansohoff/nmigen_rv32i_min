from nmigen import *
from nmigen.back.pysim import *

from isa import *
from rom import *
from cpu import *

#####################################
# ROM images for CPU test programs: #
#####################################

# "Infinite Loop" program: I think this is the simplest error-free
# application that you could write, equivalent to "while(1){};".
loop_rom = ROM( [ JAL( 1, 0x00000 ) ] )

# "Quick Test" program: this application contains at least one of
# each supported machine code instruction, but it does not perform
# exhaustive tests for any particular instruction.
quick_rom = ROM( [
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
  # Done; infinite loop.
  JAL( 1, 0x00000 )
] )

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
  'end': 52
}

############################################
# Collected definitions for test programs. #
# These are just arrays with string names, #
# ROM images, and expected runtime values. #
############################################

loop_test  = [ 'inifinite loop test', 'cpu_loop', loop_rom, loop_exp ]
quick_test = [ 'quick test', 'cpu_quick', quick_rom, quick_exp ]
