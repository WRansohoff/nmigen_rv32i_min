################################################
# RISC-V RV32I definitions and helper methods. #
################################################

from nmigen import *

from alu import *

# ALU operation definitions. These implement the logic behind math
# instructions, e.g. 'ADD' covers 'ADD', 'ADDI', 'SUB', and 'SUBI'.
ALU_ADD   = 0b0001
ALU_SLT   = 0b0010
ALU_SLTU  = 0b0011
ALU_XOR   = 0b0100
ALU_OR    = 0b0101
ALU_AND   = 0b0110
ALU_SLL   = 0b0111
ALU_SRL   = 0b1000
ALU_SRA   = 0b1001
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

##############################################################
# Helper methods to generate machine code for instructions.  #
# I'm using 'Ra, Rb, Rc' for the 'R1, R2, Rd' register names #
# so that it's easier to name variables.                     #
##############################################################

# R-type operation: Rc = Ra ? Rb
# The '?' operation depends on the opcode, funct3, and funct7 bits.
def RV32I_R( rop, c, a, b ):
  op = rop[ 0 ]
  f  = rop[ 1 ]
  ff = rop[ 2 ]
  return ( ( op & 0x7C ) |
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
  return ( ( op & 0x7C  ) |
         ( ( c  & 0x1F  ) << 7  ) |
         ( ( f  & 0x07  ) << 12 ) |
         ( ( a  & 0x1F  ) << 15 ) |
         ( ( i  & 0xFFF ) << 20 ) )

# S-type operation: Store Rb in Memory[ Ra + Immediate ]
# The funct3 bits select whether to store a byte, half-word, or word.
def RV32I_S( sop, a, b, i ):
  op = sop[ 0 ]
  f  = sop[ 1 ]
  return ( ( op & 0x7C ) |
         ( ( i  & 0x1F ) << 7  ) |
         ( ( f  & 0x07 ) << 12 ) |
         ( ( a  & 0x1F ) << 15 ) |
         ( ( b  & 0x1F ) << 20 ) |
         ( ( ( i >> 5 ) & 0x7C ) ) )

# B-type operation: Branch to (PC + Immediate) if Ra ? Rb.
# The '?' compare operation depends on the funct3 bits.
# Note: the 12-bit immediate represents a 13-bit value with LSb = 0.
# This function accepts the 13-bit representation as an argument.
def RV32I_B( bop, a, b, i ):
  op = bop[ 0 ]
  f  = bop[ 1 ]
  return ( ( op & 0x7C ) |
         ( ( ( i >> 11 ) & 0x01 ) << 7  ) |
         ( ( ( i >> 1  ) & 0x0F ) << 8  ) |
         ( ( f  & 0x07 ) << 12 ) |
         ( ( a  & 0x1F ) << 15 ) |
         ( ( b  & 0x1F ) << 20 ) |
         ( ( ( i >> 5  ) & 0x3F ) << 25 ) |
         ( ( ( i >> 12 ) & 0x01 ) << 31 ) )

# U-type operation: Load the 20-bit immediate into the most
# significant bits of Rc, setting the 12 least significant bits to 0.
# The opcode selects between LUI and AUIPC; AUIPC also adds the
# current PC address to the result which is stored in Rc.
def RV32I_U( op, c, i ):
  return ( ( op & 0x7C ) |
         ( ( c  & 0x1F ) << 5 ) |
         ( i << 20 ) )

# J-type operation: In the base RV32I spec, this is only used by JAL.
# Jumps to (PC + Immediate) and stores (PC + 4) in Rc. The 20-bit
# immediate value represents a 21-bit value with LSb = 0; this
# function takes the 21-bit representation as an argument.
def RV32I_J( op, c, i ):
  return ( ( op & 0x7C ) |
         ( ( c  & 0x1F ) << 5 ) |
         ( ( ( i >> 12 ) & 0xFF  ) << 12 ) |
         ( ( ( i >> 11 ) & 0x01  ) << 20 ) |
         ( ( ( i >> 1  ) & 0x3FF ) << 21 ) |
         ( ( ( i >> 20 ) & 0x01  ) << 31 ) )

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

# Helper method to pretty-print a 2s-complement 32-bit hex string.
def hexs( h ):
  if h >= 0:
    return "0x%08X"%( h )
  else:
    return "0x%08X"%( ( h + ( 1 << 32 ) ) % ( 1 << 32 ) )
