################################################
# RISC-V RV32I definitions and helper methods. #
################################################

from nmigen import *

from alu import *

# Flag to enable or disable the CSR module.
# Since I'm so bad at HDL design, this CPU won't actually fit in
# an iCE40UP5K unless CSR functionality is removed (~3000 gates saved!)
# Note: Traps do not work with CSRs disabled.
# TODO: remove this once I come up with a more efficient design.
CSR_EN = True

# ALU operation definitions. These implement the logic behind math
# instructions, e.g. 'ADD' covers 'ADD', 'ADDI', etc.
ALU_ADD   = 0b0001
ALU_SUB   = 0b0010
ALU_SLT   = 0b0011
ALU_SLTU  = 0b0100
ALU_XOR   = 0b0101
ALU_OR    = 0b0110
ALU_AND   = 0b0111
ALU_SLL   = 0b1000
ALU_SRL   = 0b1001
ALU_SRA   = 0b1010
# Instruction field definitions.
# RV32I opcode definitions:
OP_LUI    = 0b0110111
OP_AUIPC  = 0b0010111
OP_JAL    = 0b1101111
OP_JALR   = 0b1100111
OP_BRANCH = 0b1100011
OP_LOAD   = 0b0000011
OP_STORE  = 0b0100011
OP_REG    = 0b0110011
OP_IMM    = 0b0010011
OP_SYSTEM = 0b1110011
OP_FENCE  = 0b0001111
# Non-standard opcodes and bits, for preliminary hardware testing:
OP_LED    = 0b1110110
R_RED     = 0b001
R_GRN     = 0b010
R_BLU     = 0b100
# RV32I "funct3" bits. These select different functions with
# R-type, I-type, S-type, and B-type instructions.
F_JALR    = 0b000
F_BEQ     = 0b000
F_BNE     = 0b001
F_BLT     = 0b100
F_BGE     = 0b101
F_BLTU    = 0b110
F_BGEU    = 0b111
F_LB      = 0b000
F_LH      = 0b001
F_LW      = 0b010
F_LBU     = 0b100
F_LHU     = 0b101
F_SB      = 0b000
F_SH      = 0b001
F_SW      = 0b010
F_ADDI    = 0b000
F_SLTI    = 0b010
F_SLTIU   = 0b011
F_XORI    = 0b100
F_ORI     = 0b110
F_ANDI    = 0b111
F_SLLI    = 0b001
F_SRLI    = 0b101
F_SRAI    = 0b101
F_ADD     = 0b000
F_SUB     = 0b000
F_SLL     = 0b001
F_SLT     = 0b010
F_SLTU    = 0b011
F_XOR     = 0b100
F_SRL     = 0b101
F_SRA     = 0b101
F_OR      = 0b110
F_AND     = 0b111
# RV32I "funct7" bits. Along with the "funct3" bits, these select
# different functions with R-type instructions.
FF_SLLI   = 0b0000000
FF_SRLI   = 0b0000000
FF_SRAI   = 0b0100000
FF_ADD    = 0b0000000
FF_SUB    = 0b0100000
FF_SLL    = 0b0000000
FF_SLT    = 0b0000000
FF_SLTU   = 0b0000000
FF_XOR    = 0b0000000
FF_SRL    = 0b0000000
FF_SRA    = 0b0100000
FF_OR     = 0b0000000
FF_AND    = 0b0000000
# String mappings for opcodes, function bits, etc.
ALU_STRS = {
  ALU_ADD:  "&", ALU_SLT:  "<", ALU_SLTU: "<",
  ALU_XOR:  "^", ALU_OR:   "|", ALU_AND:  "&",
  ALU_SLL: "<<", ALU_SRL: ">>", ALU_SRA: ">>"
}

# ID numbers for different types of traps.
TRAP_IMIS  = 1
TRAP_BREAK = 3
TRAP_ECALL = 11
# CSR definitions, for 'ECALL' system instructions.
# Like with other "I-type" instructions, the 'funct3' bits select
# between different types of environment calls.
F_TRAPS  = 0b000
F_CSRRW  = 0b001
F_CSRRS  = 0b010
F_CSRRC  = 0b011
F_CSRRWI = 0b101
F_CSRRSI = 0b110
F_CSRRCI = 0b111
# Definitions for non-CSR 'ECALL' system instructions. These seem to
# use the whole 12-bit immediate to encode their functionality.
IMM_MRET = 0x302
IMM_WFI  = 0x105
# CSR Addresses for the supported subste of 'Machine-Level ISA' CSRs.
# (Supervisor and Hypervisor CSRs are not implemented.)
# Machine information registers:
CSRA_MVENDORID  = 0xF11
CSRA_MARCHID    = 0xF12
CSRA_MIMPID     = 0xF13
CSRA_MHARTID    = 0xF14
# Machine trap setup (Note - traps are not implemented yet):
CSRA_MSTATUS    = 0x300
CSRA_MISA       = 0x301
CSRA_MIE        = 0x304
CSRA_MTVEC      = 0x305
CSRA_MSTATUSH   = 0x310
# Machine trap handling (Note - traps are not implemented yet):
CSRA_MSCRATCH   = 0x340
CSRA_MEPC       = 0x341
CSRA_MCAUSE     = 0x342
CSRA_MTVAL      = 0x343
CSRA_MIP        = 0x344
CSRA_MTINST     = 0x34A
CSRA_MTVAL2     = 0x34B
# Machine memory protection: not impemented
# Machine counter / timers:
CSRA_MCYCLE           = 0xB00
# TODO: Have the tests check CSRA_MINSTRET and remove 'cpu.fsms'?
CSRA_MINSTRET         = 0xB02
# Machine counter setup:
CSRA_MCOUNTINHIBIT    = 0x320
# Note: HPM counters are not implemented.
# Range of 29 'MHPCOUNTERx' registers (32 low bits).
CSRA_MHPMCOUNTER_MIN  = 0xB03
CSRA_MHPMCOUNTER_MAX  = 0xB1F
CSRA_MCYCLEH          = 0xB80
CSRA_MINSTRETH        = 0xB82
# Range of 29 'MHPCOUNTERxH' registers (32 high bits).
CSRA_MHPMCOUNTERH_MIN = 0xB83
CSRA_MHPMCOUNTERH_MAX = 0xB9F
# Range of 29 'MHPEVENTx' registers.
CSRA_MHPMEVENT_MIN    = 0x323
CSRA_MHPMEVENT_MAX    = 0x33F
# Debug / trace registers (Note - no debugging interface exists yet):
CSRA_TSELECT    = 0x7A0
CSRA_TDATA1     = 0x7A1
CSRA_TDATA2     = 0x7A2
CSRA_TDATA3     = 0x7A3
# Debug mode registers (Note - no debugging interface exists yet):
CSRA_DCSR       = 0x7B0
CSRA_DPC        = 0x7B1
CSRA_DSCRATCH0  = 0x7B2
CSRA_DSCRATCH1  = 0x7B3
# Constants and initial values for CSRs.
# MISA 'MSL' value: determines XLEN of the CPU. This
# implementation only supports 32-bit (MISA_MSL_32).
MISA_MSL_32     = 0b01
MISA_MSL_64     = 0b10
MISA_MSL_128    = 0b11
# Encoded JEDEC manufacturer ID. If you don't have one (I don't),
# it is okay to return 0 for non-commercial applications or
# CPUs where the users won't care that the Vendor ID is not populated.
VENDOR_ID       = 0x00000000
# Architecture ID. This looks like it is an arbitrary value which
# the chip designer (you) gets to choose. Fun!
ARCH_ID         = 0x0C0FFEE0
# "Machine Implementation" ID. This should be a version number
# which is associated with your architecture ID.
MIMP_ID         = 0x00000001
# MSTATUS mask value:
MSTATUS_MASK    = 0x0000
# MSTATUS 'MPP' values: determines the previous privilege
# mode when an interrupt is called.
MSTATUS_MPP_U   = 0b00
MSTATUS_MPP_S   = 0b01
MSTATUS_MPP_H   = 0b10
MSTATUS_MPP_M   = 0b11
# MSTATUS(H) 'MBE' values: determines memory access endianness.
MSTATUS_MBE_LIT = 0b0
MSTATUS_MBE_BIG = 0b1
# MTVEC 'MODE' values: determines whether each interrupt uses its
# own handler (vectored), or one common handler is used.
# This is a two-bit field, but values >= 2 are reserved.
MTVEC_MODE_VECTORED = 0b1
MTVEC_MODE_DIRECT   = 0b0
# CSR memory map definitions.
CSRS = {
  'mhartid': {
    'c_addr': CSRA_MHARTID,
    'bits': { 'id': [ 0, 31, 'r', 0x00000000 ] }
  },
  'mvendorid': {
    'c_addr': CSRA_MVENDORID,
    'bits': {
      'offset': [ 7, 31, 'r', ( VENDOR_ID & 0xFFFFFF80 ) >> 7 ],
      'bank':   [ 0, 6,  'r', ( VENDOR_ID & 0x7F ) ]
    }
  },
  'marchid': {
    'c_addr': CSRA_MARCHID,
    'bits': { 'imp': [ 0, 31, 'r', ARCH_ID ] }
  },
  'mimpid': {
    'c_addr': CSRA_MIMPID,
    'bits': { 'imp': [ 0, 31, 'r', MIMP_ID ] }
  },
  'misa': {
    'c_addr': CSRA_MISA,
    'bits': {
      'mxl': [ 30, 31, 'r', MISA_MSL_32 ],
      'ext': [ 0,  29, 'r', 0x00000100 ]
    }
  },
  'mstatus': {
    'c_addr': CSRA_MSTATUS,
    'bits': {
      'mie':  [ 3,  3,  'rw', 0 ],
      'mpie': [ 7,  7,  'r',  0 ],
      'mpp':  [ 11, 12, 'r',  0b11 ],
    }
  },
  'mstatush': {
    'c_addr': CSRA_MSTATUSH,
    'bits': {
      'mbe':  [ 5, 5, 'r',  0 ]
    }
  },
  'mcycle': {
    'c_addr': CSRA_MCYCLE,
    'bits': { 'cycles': [ 0, 31, 'rw', 0 ] }
  },
  'mcycleh': {
    'c_addr': CSRA_MCYCLEH,
    'bits': { 'cycles': [ 0, 31, 'rw', 0 ] }
  },
  'minstret': {
    'c_addr': CSRA_MINSTRET,
    'bits': { 'instrs': [ 0, 31, 'rw', 0 ] }
  },
  'minstreth': {
    'c_addr': CSRA_MINSTRETH,
    'bits': { 'instrs': [ 0, 31, 'rw', 0 ] }
  },
  'mie': {
    'c_addr': CSRA_MIE,
    'bits': {
      'ms': [ 3,  3,  'rw', 0 ],
      'mt': [ 7,  7,  'rw', 0 ],
      'me': [ 11, 11, 'rw', 0 ]
    }
  },
  'mip': {
    'c_addr': CSRA_MIP,
    'bits': {
      'ms': [ 3,  3,  'rc', 0 ],
      'mt': [ 7,  7,  'rc', 0 ],
      'me': [ 11, 11, 'rc', 0 ]
    }
  },
  'mtvec': {
    'c_addr': CSRA_MTVEC,
    'bits': {
      'mode': [ 0, 0,  'rw', 0 ],
      'res1': [ 1, 1,  'r',  0 ],
      'base': [ 2, 31, 'rw', 0 ]
    }
  },
  'mcause': {
    'c_addr': CSRA_MCAUSE,
    'bits': {
      'interrupt': [ 31, 31, 'rw', 0 ],
      'ecode':     [ 0, 30, 'rw', 0 ]
    }
  },
  'mscratch': {
    'c_addr': CSRA_MSCRATCH,
    'bits': { 'scratch': [ 0, 31, 'rw', 0 ] }
  },
  'mepc': {
    'c_addr': CSRA_MEPC,
    'bits': {
      'res1': [ 0, 1,  'r', 0 ],
      'mepc': [ 2, 31, 'rw', 0 ]
    }
  },
  'mtval': {
    'c_addr': CSRA_MTVAL,
    'bits': { 'einfo': [ 0, 31, 'rw', 0 ] }
  },
  'mcountinhibit': {
    'c_addr': CSRA_MCOUNTINHIBIT,
    'bits': {
      'cy':   [ 0, 0, 'rw', 0 ],
      'res1': [ 1, 1, 'r',  0 ],
      'im':   [ 2, 2, 'rw', 0 ],
      # Hardware performance monitors not implemented.
      'res2': [ 3, 31, 'r', 0 ]
    }
  }
}
# Calculate 'read', 'read-only', 'set', and 'clear' bitmasks,
# and assign mutiplexer-local addresses to each CSR.
bus_addr = 0
for k, v in CSRS.items():
  mask_r, mask_ro, mask_s, mask_c, rst = 0, 0, 0, 0, 0
  for name, field in v[ 'bits' ].items():
    if 'r' in field[ 2 ]:
      for i in range( field[ 0 ], ( field[ 1 ] + 1 ) ):
        mask_r |= ( 1 << i )
        if ( not 'w' in field[ 2 ] ) & \
           ( not 's' in field[ 2 ] ) & \
           ( not 'c' in field[ 2 ] ):
          mask_ro |= ( 1 << i )
    if 'w' in field[ 2 ]:
      for i in range( field[ 0 ], ( field[ 1 ] + 1 ) ):
        mask_c |= ( 1 << i )
        mask_s |= ( 1 << i )
    if 'c' in field[ 2 ]:
      for i in range( field[ 0 ], ( field[ 1 ] + 1 ) ):
        mask_c |= ( 1 << i )
    if 's' in field[ 2 ]:
      for i in range( field[ 0 ], ( field[ 1 ] + 1 ) ):
        mask_s |= ( 1 << i )
    rst |= ( field[ 3 ] << field[ 0 ] )
  v[ 'b_addr' ]  = bus_addr
  bus_addr += 1
  v[ 'mask_r' ]  = mask_r
  v[ 'mask_ro' ] = mask_ro
  v[ 'mask_s' ]  = mask_s
  v[ 'mask_c' ]  = mask_c
  v[ 'rst' ]     = rst

##############################################################
# Helper methods to generate machine code for instructions.  #
# I'm using 'Ra, Rb, Rc' for the 'R1, R2, Rd' register names #
# so that it's easier to name variables.                     #
##############################################################

# Convert a 32-bit word to little-endian byte format.
# 0x1234ABCD -> 0xCDAB3412
def LITTLE_END( v ):
  return ( ( ( v & 0x000000FF ) << 24 ) |
           ( ( v & 0x0000FF00 ) << 8  ) |
           ( ( v & 0x00FF0000 ) >> 8  ) |
           ( ( v & 0xFF000000 ) >> 24 ) )

# R-type operation: Rc = Ra ? Rb
# The '?' operation depends on the opcode, funct3, and funct7 bits.
def RV32I_R( rop, c, a, b ):
  op = rop[ 0 ]
  f  = rop[ 1 ]
  ff = rop[ 2 ]
  return LITTLE_END( ( op & 0x7F ) |
         ( ( c  & 0x1F ) << 7  ) |
         ( ( f  & 0x07 ) << 12 ) |
         ( ( a  & 0x1F ) << 15 ) |
         ( ( b  & 0x1F ) << 20 ) |
         ( ( ff & 0x7C ) << 25 ) )

# I-type operation: Rc = Ra ? Immediate
# The '?' operation depends on the opcode and funct3 bits.
def RV32I_I( iop, c, a, i ):
  op = iop[ 0 ]
  f  = iop[ 1 ]
  return LITTLE_END( ( op & 0x7F  ) |
         ( ( c  & 0x1F  ) << 7  ) |
         ( ( f  & 0x07  ) << 12 ) |
         ( ( a  & 0x1F  ) << 15 ) |
         ( ( i  & 0xFFF ) << 20 ) )

# S-type operation: Store Rb in Memory[ Ra + Immediate ]
# The funct3 bits select whether to store a byte, half-word, or word.
def RV32I_S( sop, a, b, i ):
  op = sop[ 0 ]
  f  = sop[ 1 ]
  return LITTLE_END( ( op & 0x7F ) |
         ( ( i  & 0x1F ) << 7  ) |
         ( ( f  & 0x07 ) << 12 ) |
         ( ( a  & 0x1F ) << 15 ) |
         ( ( b  & 0x1F ) << 20 ) |
         ( ( ( i >> 5 ) & 0x7C ) ) )

# B-type operation: Branch to (PC + Immediate) if Ra ? Rb.
# The '?' compare operation depends on the funct3 bits.
# Note: the 12-bit immediate represents a 13-bit value with LSb = 0.
# This function accepts the 12-bit representation as an argument.
def RV32I_B( bop, a, b, i ):
  op = bop[ 0 ]
  f  = bop[ 1 ]
  return LITTLE_END( ( op & 0x7F ) |
         ( ( ( i >> 10 ) & 0x01 ) << 7  ) |
         ( ( ( i ) & 0x0F ) << 8 ) |
         ( ( f  & 0x07 ) << 12 ) |
         ( ( a  & 0x1F ) << 15 ) |
         ( ( b  & 0x1F ) << 20 ) |
         ( ( ( i >> 4  ) & 0x3F ) << 25 ) |
         ( ( ( i >> 11 ) & 0x01 ) << 31 ) )

# U-type operation: Load the 20-bit immediate into the most
# significant bits of Rc, setting the 12 least significant bits to 0.
# The opcode selects between LUI and AUIPC; AUIPC also adds the
# current PC address to the result which is stored in Rc.
def RV32I_U( op, c, i ):
  return LITTLE_END( ( op & 0x7F ) |
         ( ( c  & 0x1F ) << 7 ) |
         ( ( i & 0xFFFFF000 ) ) )

# J-type operation: In the base RV32I spec, this is only used by JAL.
# Jumps to (PC + Immediate) and stores (PC + 4) in Rc. The 20-bit
# immediate value represents a 21-bit value with LSb = 0; this
# function takes the 20-bit representation as an argument.
def RV32I_J( op, c, i ):
  return LITTLE_END( ( op & 0x7F ) |
         ( ( c  & 0x1F ) << 7 ) |
         ( ( ( i >> 11 ) & 0xFF ) << 12 ) |
         ( ( ( i >> 10 ) & 0x01 ) << 20 ) |
         ( ( ( i ) & 0x3FF ) << 21 ) |
         ( ( ( i >> 19 ) & 0x01 ) << 31 ) )

# Functions to assemble individual instructions.
# R-type operations:
def SLLI( c, a, i ):
  return RV32I_R( [ OP_IMM, F_SLLI, FF_SLLI ], c, a, i )
def SRLI( c, a, i ):
  return RV32I_R( [ OP_IMM, F_SRLI, FF_SRLI ], c, a, i )
def SRAI( c, a, i ):
  return RV32I_R( [ OP_IMM, F_SRAI, FF_SRAI ], c, a, i )
def ADD( c, a, b ):
  return RV32I_R( [ OP_REG, F_ADD, FF_ADD ], c, a, b )
def SUB( c, a, b ):
  return RV32I_R( [ OP_REG, F_SUB, FF_SUB ], c, a, b )
def SLL( c, a, b ):
  return RV32I_R( [ OP_REG, F_SLL, FF_SLL ], c, a, b )
def SLT( c, a, b ):
  return RV32I_R( [ OP_REG, F_SLT, FF_SLT ], c, a, b )
def SLTU( c, a, b ):
  return RV32I_R( [ OP_REG, F_SLTU, FF_SLTU ], c, a, b )
def XOR( c, a, b ):
  return RV32I_R( [ OP_REG, F_XOR, FF_XOR ], c, a, b )
def SRL( c, a, b ):
  return RV32I_R( [ OP_REG, F_SRL, FF_SRL ], c, a, b )
def SRA( c, a, b ):
  return RV32I_R( [ OP_REG, F_SRA, FF_SRA ], c, a, b )
def OR( c, a, b ):
  return RV32I_R( [ OP_REG, F_OR, FF_OR ], c, a, b )
def AND( c, a, b ):
  return RV32I_R( [ OP_REG, F_AND, FF_AND ], c, a, b )
# I-type operations:
def JALR( c, a, i ):
  return RV32I_I( [ OP_JALR, F_JALR ], c, a, i )
def LB( c, a, i ):
  return RV32I_I( [ OP_LOAD, F_LB ], c, a, i )
def LH( c, a, i ):
  return RV32I_I( [ OP_LOAD, F_LH ], c, a, i )
def LW( c, a, i ):
  return RV32I_I( [ OP_LOAD, F_LW ], c, a, i )
def LBU( c, a, i ):
  return RV32I_I( [ OP_LOAD, F_LBU ], c, a, i )
def LHU( c, a, i ):
  return RV32I_I( [ OP_LOAD, F_LHU ], c, a, i )
def ADDI( c, a, i ):
  return RV32I_I( [ OP_IMM, F_ADDI ], c, a, i )
def SLTI( c, a, i ):
  return RV32I_I( [ OP_IMM, F_SLTI ], c, a, i )
def SLTIU( c, a, i ):
  return RV32I_I( [ OP_IMM, F_SLTIU ], c, a, i )
def XORI( c, a, i ):
  return RV32I_I( [ OP_IMM, F_XORI ], c, a, i )
def ORI( c, a, i ):
  return RV32I_I( [ OP_IMM, F_ORI ], c, a, i )
def ANDI( c, a, i ):
  return RV32I_I( [ OP_IMM, F_ANDI ], c, a, i )
# S-type operations:
def SB( a, b, i ):
  return RV32I_S( [ OP_STORE, F_SB ], a, b, i )
def SH( a, b, i ):
  return RV32I_S( [ OP_STORE, F_SH ], a, b, i )
def SW( a, b, i ):
  return RV32I_S( [ OP_STORE, F_SW ], a, b, i )
# B-type operations:
def BEQ( a, b, i ):
  return RV32I_B( [ OP_BRANCH, F_BEQ ], a, b, i )
def BNE( a, b, i ):
  return RV32I_B( [ OP_BRANCH, F_BNE ], a, b, i )
def BLT( a, b, i ):
  return RV32I_B( [ OP_BRANCH, F_BLT ], a, b, i )
def BGE( a, b, i ):
  return RV32I_B( [ OP_BRANCH, F_BGE ], a, b, i )
def BLTU( a, b, i ):
  return RV32I_B( [ OP_BRANCH, F_BLTU ], a, b, i )
def BGEU( a, b, i ):
  return RV32I_B( [ OP_BRANCH, F_BGEU ], a, b, i )
# U-type operations:
def LUI( c, i ):
  return RV32I_U( OP_LUI, c, i )
def AUIPC( c, i ):
  return RV32I_U( OP_AUIPC, c, i )
# J-type operation:
def JAL( c, i ):
  return RV32I_J( OP_JAL, c, i )
# Assembly pseudo-ops:
def LI( c, i ):
  if ( ( i & 0x0FFF ) & 0x0800 ):
    return LUI( c, ( ( i >> 12 ) + 1 ) << 12 ), \
           ADDI( c, c, ( i & 0x0FFF ) )
  else:
    return LUI( c, i ), ADDI( c, c, ( i & 0x0FFF ) )
def NOP():
  return ADDI( 0, 0, 0x000 )
def LED( a ):
  return LITTLE_END( ( OP_LED & 0x7F ) | ( a & 0x1F ) << 15 )

# Helper method to pretty-print a 2s-complement 32-bit hex string.
def hexs( h ):
  if h >= 0:
    return "0x%08X"%( h )
  else:
    return "0x%08X"%( ( h + ( 1 << 32 ) ) % ( 1 << 32 ) )

# Helper method to assemble a ROM image from a mix of instructions
# and assembly pseudo-operations.
def rom_img( arr ):
  a = []
  for i in arr:
    if type( i ) == tuple:
      for j in i:
        a.append( j )
    else:
      a.append( i )
  return a

# Helper method to assemble a little-endian RAM image with byte
# addressing. This assumes that all instructions are
# 32 bits wide, which...should be true for the RV32I ISA. Right?
def ram_img( arr ):
  a = []
  for i in arr:
    a.append( ( i & 0xFF000000 ) >> 24 )
    a.append( ( i & 0x00FF0000 ) >> 16 )
    a.append( ( i & 0x0000FF00 ) >> 8  )
    a.append( i & 0x000000FF )
  return a
