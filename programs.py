from nmigen import *

from isa import *
from rom import *

#####################################
# ROM images for CPU test programs: #
#####################################

# "Infinite Loop" program: I think this is the simplest error-free
# application that you could write, equivalent to "while(1){};".
loop_rom = rom_img( [ JAL( 1, 0x00000 ) ] )

# "Run from RAM" program: Make sure that the CPU can jump between
# RAM and ROM memory spaces.
ram_rom = rom_img ( [
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
] )

# "Quick Test" program: this application contains at least one of
# each supported machine code instruction, but it does not perform
# exhaustive tests for any particular instruction.
# (TODO: It doesn't contain at least one of each instruction yet)
quick_rom = rom_img( [
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
] )

# "LED Test" program: cycle through RGB LED colors.
led_rom = rom_img( [
  # r15 will hold the LED colors, r14 the loopback address.
  ADDI( 15, 0, 1 ), ADDI( 13, 0, 8 ), AUIPC( 14, 0 ),
  # Increment r15, reset to 0 if > 7.
  ADDI( 15, 15, 1 ), BLT( 15, 13, 0x004 ), ADDI( 15, 0, 1 ),
  # Delay for 100000 instructions.
  #ADDI( 4, 0, 0 ), LI( 5, 100000 ),
  #ADDI( 4, 0, 1 ), BLT( 4, 5, -4 ),
  # Set LED color, loop back.
  LED( 15 ), JALR( 16, 14, 0 )
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

# LED test program 'expected' values; just a stub to simulate it.
led_exp = {
  0:  [ { 'r': 'pc', 'e': 0x00000000 } ],
  'end': 100
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
led_test     = [ 'led test', 'cpu_led',
                 led_rom, [], led_exp ]

# Multiplexed ROM image for the collected RV32I compliance tests.
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
from tests.test_roms.rv32i_delay_slots import *
from tests.test_roms.rv32i_ebreak import *
from tests.test_roms.rv32i_ecall import *
from tests.test_roms.rv32i_io import *
from tests.test_roms.rv32i_jal import *
from tests.test_roms.rv32i_jalr import *
from tests.test_roms.rv32i_lb import *
from tests.test_roms.rv32i_lbu import *
from tests.test_roms.rv32i_lh import *
from tests.test_roms.rv32i_lhu import *
from tests.test_roms.rv32i_lw import *
from tests.test_roms.rv32i_lui import *
from tests.test_roms.rv32i_nop import *
from tests.test_roms.rv32i_misalign_jmp import *
from tests.test_roms.rv32i_misalign_ldst import *
from tests.test_roms.rv32i_or import *
from tests.test_roms.rv32i_ori import *
from tests.test_roms.rv32i_rf_size import *
from tests.test_roms.rv32i_rf_width import *
from tests.test_roms.rv32i_rf_x0 import *
from tests.test_roms.rv32i_sb import *
from tests.test_roms.rv32i_sh import *
from tests.test_roms.rv32i_sw import *
from tests.test_roms.rv32i_sll import *
from tests.test_roms.rv32i_slli import *
from tests.test_roms.rv32i_slt import *
from tests.test_roms.rv32i_slti import *
from tests.test_roms.rv32i_sltiu import *
from tests.test_roms.rv32i_sltu import *
from tests.test_roms.rv32i_sra import *
from tests.test_roms.rv32i_srai import *
from tests.test_roms.rv32i_srl import *
from tests.test_roms.rv32i_srli import *
from tests.test_roms.rv32i_sub import *
from tests.test_roms.rv32i_xor import *
from tests.test_roms.rv32i_xori import *
rv32i_compliance = [ 'RV32I compliance tests', 'rv32i_compliance',
  [
    add_test, addi_test, and_test, andi_test, auipc_test,
    beq_test, bge_test, bgeu_test, blt_test, bltu_test,
    bne_test, delay_slots_test, ebreak_test, ecall_test,
    io_test, jal_test, jalr_test, lb_test, lbu_test,
    lh_test, lhu_test, lw_test, lui_test, nop_test,
    misalign_jmp_test, misalign_ldst_test, or_test, ori_test,
    rf_size_test, rf_width_test, rf_x0_test, sb_test,
    sh_test, sw_test, sll_test, slli_test, slt_test,
    slti_test, sltiu_test, sltu_test, sra_test, srai_test,
    srl_test, srli_test, sub_test, xor_test, xori_test
  ]
]

# Non-standard compiled test programs.
from tests.test_roms.rv32i_mcycle import *
from tests.test_roms.rv32i_minstret import *
