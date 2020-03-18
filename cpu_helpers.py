from isa import *

# Helper method to generate logic for setting the ALU operation
# associated with given 'funct3' and 'funct7' bits.
# This is a little verbose, but the extra Python logic
# shouldn't translate to a more complex generated design.
def ALU_FUNC( self, cpu, funcs ):
  first = True
  for k, v in funcs.items():
    # Start with an 'If'.
    if first:
      first = False
      with cpu.If( self.f == k ):
        if type( v ) == dict:
          ffirst = 0
          for ki, vi in v.items():
            if ffirst:
              with cpu.If( self.ff == ki ):
                cpu.d.comb += self.alu.f.eq( vi )
            else:
              with cpu.Elif( self.ff == ki ):
                cpu.d.comb += self.alu.f.eq( vi )
        else:
          cpu.d.comb += self.alu.f.eq( v )
    else:
      with cpu.Elif( self.f == k ):
        if type( v ) == dict:
          ffirst = 0
          for ki, vi in v.items():
            if ffirst:
              with cpu.If( self.ff == ki ):
                cpu.d.comb += self.alu.f.eq( vi )
            else:
              with cpu.Elif( self.ff == ki ):
                cpu.d.comb += self.alu.f.eq( vi )
        else:
          cpu.d.comb += self.alu.f.eq( v )

# Helper method to define shared logic for 'Rc = Ra ? Rb' ALU
# operations such as 'ADD', 'AND', 'SLT', etc.
def alu_reg_op( self, cpu ):
  # Set the ALU 'function select' bits.
  ALU_FUNC( self, cpu, ALU_R_FUNCS )
  # (No 'Else' is needed; all 8 'funct3' options are accounted for)
  # Set the ALU 'start' bit and connect appropriate
  # registers to the ALU inputs and output.
  cpu.d.comb += [
    self.alu.start.eq( 1 ),
    self.alu.a.eq( self.r[ self.ra ] ),
    self.alu.b.eq( self.r[ self.rb ] )
  ]
  with cpu.If( self.rc > 0 ):
    cpu.d.sync += self.r[ self.rc ].eq( self.alu.y )

# Helper method to define shared logic for 'Rc = Ra ? Immediate'
# ALU operations such as 'ADDI', 'ANDI', 'SLTI', etc.
def alu_imm_op( self, cpu ):
  # Set the ALU 'function select' bits.
  ALU_FUNC( self, cpu, ALU_I_FUNCS )
  # Set the ALU 'start' bit, and the constant 'immediate' value.
  cpu.d.comb += [
    self.alu.a.eq( self.r[ self.ra ] ),
    self.alu.b.eq( self.imm ),
    self.alu.start.eq( 1 )
  ]
  # Connect appropriate registers to the ALU inputs and output.
  with cpu.If( self.rc > 0 ):
    cpu.d.sync += self.r[ self.rc ].eq( self.alu.y )

# Helper method to decode an instruction into individual fields.
def rv32i_decode( self, cpu, instr ):
  # I-type operations have one cohesive 12-bit immediate.
  with cpu.If( ( instr.bit_select( 0, 7 ) == OP_IMM ) |
               ( instr.bit_select( 0, 7 ) == OP_JALR ) |
               ( instr.bit_select( 0, 7 ) == OP_LOAD ) ):
    # ...But shift operations are a special case with a 5-bit
    # unsigned immediate and 'funct7' bits in the MSbs.
    with cpu.If( ( instr.bit_select( 0, 7 ) == OP_IMM ) &
               ( ( instr.bit_select( 12, 3 ) == F_SLLI ) |
               ( instr.bit_select( 12, 3 ) == F_SRLI ) ) ):
      cpu.d.sync += self.imm.eq( instr.bit_select( 20, 5 ) )
    with cpu.Else():
      with cpu.If( instr[ 31 ] ):
        cpu.d.sync += self.imm.eq(
          ( 0xFFFFF000 | instr.bit_select( 20, 12 ) ) )
      with cpu.Else():
        cpu.d.sync += self.imm.eq( instr.bit_select( 20, 12 ) )
  # S-type instructions have 12-bit immediates in two fields.
  with cpu.Elif( instr.bit_select( 0, 7 ) == OP_STORE ):
    with cpu.If( instr[ 31 ] ):
      cpu.d.sync += self.imm.eq(
        ( 0xFFFFF000 | instr.bit_select( 7, 5 ) ) |
        ( instr.bit_select( 25, 7 ) << 5 ) )
    with cpu.Else():
      cpu.d.sync += self.imm.eq(
        ( instr.bit_select( 7,  5 ) ) |
        ( instr.bit_select( 25, 7 ) << 5 ) )
  # U-type instructions just have a single 20-bit immediate,
  # with the register's remaining 12 LSbs padded with 0s.
  with cpu.Elif( ( instr.bit_select( 0, 7 ) == OP_LUI ) |
               ( instr.bit_select( 0, 7 ) == OP_AUIPC ) ):
    cpu.d.sync += self.imm.eq( instr & 0xFFFFF000 )
  # J-type instructions have a 20-bit immediate encoding a
  # 21-bit value, with its bits scattered to the four winds.
  with cpu.Elif( instr.bit_select( 0, 7 ) == OP_JAL ):
    with cpu.If( instr[ 31 ] ):
      cpu.d.sync += self.imm.eq( 0xFFE00000 |
        ( instr.bit_select( 21, 10 ) << 1 ) |
        ( instr.bit_select( 20, 1 ) << 11 ) |
        ( instr.bit_select( 12, 8 ) << 12 ) |
        ( instr.bit_select( 31, 1 ) << 20 ) )
    with cpu.Else():
      cpu.d.sync += self.imm.eq(
        ( instr.bit_select( 21, 10 ) << 1 ) |
        ( instr.bit_select( 20, 1  ) << 11 ) |
        ( instr.bit_select( 12, 8  ) << 12 ) |
        ( instr.bit_select( 31, 1  ) << 20 ) )
  # B-type instructions have a 12-bit immediate encoding a
  # 13-bit value, with bits scattered around the instruction.
  with cpu.Elif( instr.bit_select( 0, 7 ) == OP_BRANCH ):
    with cpu.If( instr[ 31 ] ):
      cpu.d.sync += self.imm.eq( 0xFFFFE000 |
        ( instr.bit_select( 8,  4 ) << 1 ) |
        ( instr.bit_select( 25, 6 ) << 5 ) |
        ( instr.bit_select( 7,  1 ) << 11 ) |
        ( instr.bit_select( 31, 1 ) << 12 ) )
    with cpu.Else():
      cpu.d.sync += self.imm.eq(
        ( instr.bit_select( 8,  4 ) << 1 ) |
        ( instr.bit_select( 25, 6 ) << 5 ) |
        ( instr.bit_select( 7,  1 ) << 11 ) |
        ( instr.bit_select( 31, 1 ) << 12 ) )
  # R-type operations have no immediates.
  with cpu.Elif( instr.bit_select( 0, 7 ) == OP_REG ):
    cpu.d.sync += self.imm.eq( 0x00000000 )
  # TODO: support 'SYSTEM' instructions.
  # Unrecognized opcodes set the immediate value to 0.
  with cpu.Else():
    cpu.d.sync += self.imm.eq( 0x00000000 )
  # Populate "opcode, funct3, funct7, r1, r2, rd". I call them
  # "opcode, f, ff, ra, rb, rc", respectively. Why? Because
  # I can't name a variable '1' for 'r1'; 'a' is easier.
  # Not every type of operation uses every value, but at least
  # they're placed in consistent locations when they are used.
  cpu.d.sync += [
    self.opcode.eq( instr.bit_select( 0, 7 ) ),
    self.rc.eq( instr.bit_select( 7,  5 ) ),
    self.f.eq( instr.bit_select( 12, 3 ) ),
    self.ra.eq( instr.bit_select( 15, 5 ) ),
    self.rb.eq( instr.bit_select( 20, 5 ) ),
    self.ff.eq( instr.bit_select( 25, 7 ) ),
    self.ipc.eq( self.pc )
  ]
