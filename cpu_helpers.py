from isa import *

####################################################
# 'CPU Helper Methods' file. This contains logic   #
# for long or repetitive bits of CPU logic.        #
# There is no testbench associated with this file. #
####################################################

# Helper method to define shared logic for 'Rc = Ra ? Rb' ALU
# operations such as 'ADD', 'AND', 'SLT', etc.
def alu_reg_op( self, cpu ):
  # Set the ALU 'function select' bits.
  with cpu.If( self.f == F_ADD ):
    with cpu.If( self.ff == FF_SUB ):
      cpu.d.comb += self.alu.f.eq( ALU_SUB )
    with cpu.Else():
      cpu.d.comb += self.alu.f.eq( ALU_ADD )
  with cpu.Elif( self.f == F_SLL ):
    cpu.d.comb += self.alu.f.eq( ALU_SLL )
  with cpu.Elif( self.f == F_SLT ):
    cpu.d.comb += self.alu.f.eq( ALU_SLT )
  with cpu.Elif( self.f == F_SLTU ):
    cpu.d.comb += self.alu.f.eq( ALU_SLTU )
  with cpu.Elif( self.f == F_XOR ):
    cpu.d.comb += self.alu.f.eq( ALU_XOR )
  with cpu.Elif( self.f == F_OR ):
    cpu.d.comb += self.alu.f.eq( ALU_OR )
  with cpu.Elif( self.f == F_AND ):
    cpu.d.comb += self.alu.f.eq( ALU_AND )
  with cpu.Elif( self.f == F_SRL ):
    with cpu.If( self.ff == FF_SRA ):
      cpu.d.comb += self.alu.f.eq( ALU_SRA )
    with cpu.Else():
      cpu.d.comb += self.alu.f.eq( ALU_SRL )
  # Set the ALU 'start' bit and connect appropriate
  # registers to the ALU inputs and output.
  cpu.d.comb += [
    self.alu.start.eq( 1 ),
    self.alu.a.eq( self.ra.data ),
    self.alu.b.eq( self.rb.data )
  ]

# Helper method to define shared logic for 'Rc = Ra ? Immediate'
# ALU operations such as 'ADDI', 'ANDI', 'SLTI', etc.
def alu_imm_op( self, cpu ):
  # Set the ALU 'function select' bits.
  with cpu.If( self.f == F_ADDI ):
    cpu.d.comb += self.alu.f.eq( ALU_ADD )
  with cpu.Elif( self.f == F_SLTI ):
    cpu.d.comb += self.alu.f.eq( ALU_SLT )
  with cpu.Elif( self.f == F_SLTIU ):
    cpu.d.comb += self.alu.f.eq( ALU_SLTU )
  with cpu.Elif( self.f == F_XORI ):
    cpu.d.comb += self.alu.f.eq( ALU_XOR )
  with cpu.Elif( self.f == F_ORI ):
    cpu.d.comb += self.alu.f.eq( ALU_OR )
  with cpu.Elif( self.f == F_ANDI ):
    cpu.d.comb += self.alu.f.eq( ALU_AND )
  with cpu.Elif( self.f == F_SLLI ):
    cpu.d.comb += self.alu.f.eq( ALU_SLL )
  with cpu.Elif( self.f == F_SRAI ):
    with cpu.If( self.ff == FF_SRAI ):
      cpu.d.comb += self.alu.f.eq( ALU_SRA )
    with cpu.Else():
      cpu.d.comb += self.alu.f.eq( ALU_SRL )
  # Set the ALU 'start' bit, and the constant 'immediate' value.
  cpu.d.comb += [
    self.alu.a.eq( self.ra.data ),
    self.alu.b.eq( self.imm ),
    self.alu.start.eq( 1 )
  ]

# Helper method to decode an instruction into individual fields.
def rv32i_decode( self, cpu, instr ):
  # I-type operations have one cohesive 12-bit immediate.
  # Loads, register jumps, and system instructions are also I-type.
  with cpu.If( ( instr[ 0 : 7 ] == OP_IMM    ) |
               ( instr[ 0 : 7 ] == OP_JALR   ) |
               ( instr[ 0 : 7 ] == OP_LOAD   ) |
               ( instr[ 0 : 7 ] == OP_SYSTEM ) ):
    # ...But shift operations are a special case with a 5-bit
    # unsigned immediate and 'funct7' bits in the MSbs.
    with cpu.If( ( instr[ 0 : 7 ] == OP_IMM ) &
               ( ( instr[ 12 : 15 ] == F_SLLI ) |
                 ( instr[ 12 : 15 ] == F_SRLI ) |
                 ( instr[ 12 : 15 ] == F_SRAI ) ) ):
      cpu.d.sync += self.imm.eq( instr[ 20 : 25 ] )
    with cpu.Else():
      with cpu.If( instr[ 31 ] ):
        cpu.d.sync += self.imm.eq(
          ( 0xFFFFF000 | instr[ 20 : 32 ] ) )
      with cpu.Else():
        cpu.d.sync += self.imm.eq( instr[ 20 : 32 ] )
  # S-type instructions have 12-bit immediates in two fields.
  with cpu.Elif( instr[ 0 : 7 ] == OP_STORE ):
    with cpu.If( instr[ 31 ] ):
      cpu.d.sync += self.imm.eq(
        0xFFFFF000 | instr[ 7 : 12 ] | ( instr[ 25 : 32 ] << 5 ) )
    with cpu.Else():
      cpu.d.sync += self.imm.eq( instr[ 7 : 12 ] |
                               ( instr[ 25 : 32 ] << 5 ) )
  # U-type instructions just have a single 20-bit immediate,
  # with the register's remaining 12 LSbs padded with 0s.
  with cpu.Elif( ( instr[ 0 : 7 ] == OP_LUI ) |
                 ( instr[ 0 : 7 ] == OP_AUIPC ) ):
    cpu.d.sync += self.imm.eq( instr & 0xFFFFF000 )
  # J-type instructions have a 20-bit immediate encoding a
  # 21-bit value, with its bits scattered to the four winds.
  with cpu.Elif( instr[ 0 : 7 ] == OP_JAL ):
    with cpu.If( instr[ 31 ] ):
      cpu.d.sync += self.imm.eq( 0xFFF00000  |
        ( instr[ 21 : 31 ] << 1  ) |
        ( instr[ 20 ] << 11 ) |
        ( instr[ 12 : 20 ] << 12 ) )
    with cpu.Else():
      cpu.d.sync += self.imm.eq(
        ( instr[ 21 : 31 ] << 1  ) |
        ( instr[ 20 ] << 11 ) |
        ( instr[ 12 : 20 ] << 12 ) )
  # B-type instructions have a 12-bit immediate encoding a
  # 13-bit value, with bits scattered around the instruction.
  with cpu.Elif( instr[ 0 : 7 ] == OP_BRANCH ):
    with cpu.If( instr[ 31 ] ):
      cpu.d.sync += self.imm.eq( 0xFFFFF000 |
        ( instr[ 8 : 12 ] << 1  ) |
        ( instr[ 25 : 31 ] << 5  ) |
        ( instr[ 7 ] << 11 ) )
    with cpu.Else():
      cpu.d.sync += self.imm.eq(
        ( instr[ 8 : 12 ] << 1  ) |
        ( instr[ 25 : 31 ] << 5  ) |
        ( instr[ 7 ] << 11 ) )
  # R-type operations have no immediates.
  with cpu.Elif( instr[ 0 : 7 ] == OP_REG ):
    cpu.d.sync += self.imm.eq( 0x00000000 )
  # LED-type operations have no immediates.
  with cpu.Elif( instr[ 0 : 7 ] == OP_LED ):
    cpu.d.sync += self.imm.eq( 0x00000000 )
  # Unrecognized opcodes set the immediate value to 0.
  with cpu.Else():
    cpu.d.sync += self.imm.eq( 0x00000000 )
  # Populate "opcode, funct3, funct7, r1, r2, rd". I call them
  # "opcode, f, ff, ra, rb, rc", respectively. Why? Because
  # I can't name a variable '1' for 'r1'; 'a' is easier.
  # Not every type of operation uses every value, but at least
  # they're placed in consistent locations when they are used.
  cpu.d.sync += [
    self.opcode.eq( instr[ 0 : 7 ] ),
    self.rc.addr.eq( instr[ 7 : 12 ] | ( self.irq << 5 ) ),
    self.f.eq( instr[ 12 : 15 ] ),
    self.ra.addr.eq( instr[ 15 : 20 ] | ( self.irq << 5 ) ),
    self.rb.addr.eq( instr[ 20 : 25 ] | ( self.irq << 5 ) ),
    self.ff.eq( instr[ 25 : 32 ] ),
    self.ipc.eq( self.pc ),
  ]

# Helper method to perform atomic r/w logic for CSR instructions.
def csr_rw( self, cpu, rws_c ):
  # Time CSR reads and writes for atomic access.
  with cpu.If( rws_c == ( self.rws - 1 ) ):
    cpu.d.sync += self.csr.rw.eq( 1 )
  with cpu.Elif( rws_c == self.rws ):
    with cpu.If( self.rc.addr[ :5 ] != 0 ):
      cpu.d.comb += [
        self.rc.data.eq( self.csr.csrs.bus.r_data ),
        self.rc.en.eq( 1 )
      ]
  cpu.next = "CPU_PC_LOAD"

# Helper method to enter the trap handler and jump to the
# appropriate address.
def trigger_trap( self, cpu, trap_num ):
  # Set 'mcause'.
  cpu.d.sync += self.csr.mcause.shadow.eq( trap_num )
  # Set PC to the interrupt handler address.
  with cpu.If( ( self.csr.mtvec.shadow & 0b11 ) == MTVEC_MODE_DIRECT ):
    cpu.d.sync += self.pc.eq( self.csr.mtvec.shadow & 0xFFFFFFFC )
  with cpu.Else():
    cpu.d.sync += self.pc.eq(
      ( self.csr.mtvec.shadow & 0xFFFFFFFC ) + ( trap_num << 2 )
    )
  # 'mepc' is currently populated in the 'CPU_TRAP_ENTER' FSM state.
  cpu.next = "CPU_TRAP_ENTER"

# Helper method to generate logic which moves the CPU's
# Program Counter to a different memory location.
def jump_to( self, cpu, npc ):
  # Can only jump to a word-aligned address.
  with cpu.If( npc & 0b11 != 0 ):
    # Write the bad address into the 'mtval' CSR.
    cpu.d.sync += self.csr.mtval.shadow.eq( npc )
    # Trigger an 'instruction address misaligned' trap.
    trigger_trap( self, cpu, TRAP_IMIS )
  with cpu.Else():
    # Set the new PC value at the next rising clock edge.
    cpu.d.sync += self.pc.eq( npc )
    # Read PC from RAM if the address is in that memory space.
    cpu.d.comb += self.mem.addr.eq( npc )
    cpu.next = "CPU_PC_ROM_FETCH"

# Helper method to increment the 'minstret' CSR.
def minstret_incr( self, cpu ):
  # Increment 64-bit 'MINSTRET' counter unless it is inhibited.
  with cpu.If( self.csr.mcountinhibit.shadow[ 2 ] == 0 ):
    cpu.d.sync += self.csr.minstret.shadow.eq( self.csr.minstret.shadow + 1 )
    with cpu.If( self.csr.minstret.shadow == 0xFFFFFFFF ):
      cpu.d.sync += self.csr.minstreth.shadow.eq( self.csr.minstreth.shadow + 1 )
