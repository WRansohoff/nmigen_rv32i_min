from nmigen import *
from nmigen.back.pysim import *

from alu import *
from isa import *
from rom import *
from ram import *

###############
# CPU module: #
###############

# FSM state definitions. TODO: Remove after figuring out how to
# access the internal FSM from tests. Also, consolidate these steps...
CPU_PC_LOAD      = 0
CPU_PC_ROM_FETCH = 1
CPU_PC_DECODE    = 2
CPU_LD           = 4
CPU_ST           = 5
CPU_STATES_MAX   = 5

# CPU module.
class CPU( Elaboratable ):
  def __init__( self, rom_module ):
    # Program Counter register.
    self.pc = Signal( 32, reset = 0x00000000 )
    # Intermediate load/store memory pointer.
    self.mp = Signal( 32, reset = 0x00000000 )
    # The main 32 CPU registers.
    self.r  = [
      Signal( 32, reset = 0x00000000, name = "r%d"%i )
      for i in range( 32 )
    ]
    # The ALU submodule which performs logical operations.
    self.alu = ALU()
    # The ROM submodule which acts as simulated program data storage.
    self.rom = rom_module
    # The RAM submodule which simulates re-writable data storage.
    # (512 bytes of RAM = 128 words)
    self.ram = RAM( 128 )

    # Debugging signal(s):
    # Track FSM state. TODO: There must be a way to access this
    # from the Module's FSM object, but I don't know how.
    self.fsms = Signal( range( CPU_STATES_MAX ),
                        reset = CPU_PC_ROM_FETCH )

  # Helper method to define shared logic for 'Rc = Ra ? Rb' ALU
  # operations such as 'ADD', 'AND', 'SLT', etc.
  def alu_reg_op( self, cpu, rc, ra, rb, ff, f ):
    # Set the ALU 'function select' bits.
    with cpu.If( f == F_ADD ):
      with cpu.If( ff == FF_SUB ):
        cpu.d.comb += self.alu.f.eq( ALU_SUB )
      with cpu.Else():
        cpu.d.comb += self.alu.f.eq( ALU_ADD )
    with cpu.Elif( f == F_SLL ):
      cpu.d.comb += self.alu.f.eq( ALU_SLL )
    with cpu.Elif( f == F_SLT ):
      cpu.d.comb += self.alu.f.eq( ALU_SLT )
    with cpu.Elif( f == F_SLTU ):
      cpu.d.comb += self.alu.f.eq( ALU_SLTU )
    with cpu.Elif( f == F_XOR ):
      cpu.d.comb += self.alu.f.eq( ALU_XOR )
    with cpu.Elif( f == F_SRL ):
      with cpu.If( ff == FF_SRA ):
        cpu.d.comb += self.alu.f.eq( ALU_SRA )
      with cpu.Else():
        cpu.d.comb += self.alu.f.eq( ALU_SRL )
    with cpu.Elif( f == F_OR ):
      cpu.d.comb += self.alu.f.eq( ALU_OR )
    with cpu.Elif( f == F_AND ):
      cpu.d.comb += self.alu.f.eq( ALU_AND )
    # (No 'Else' is needed; all 8 'funct3' options are accounted for)
    # Set the ALU 'start' bit.
    cpu.d.comb += self.alu.start.eq( 1 )
    # Connect appropriate registers to the ALU inputs and output.
    for i in range( 32 ):
      with cpu.If( ra == i ):
        cpu.d.comb += self.alu.a.eq( self.r[ i ] )
      with cpu.If( rb == i ):
        cpu.d.comb += self.alu.b.eq( self.r[ i ] )
      with cpu.If( rc == i ):
        if i > 0:
          cpu.d.sync += self.r[ i ].eq( self.alu.y )

  # Helper method to define shared logic for 'Rc = Ra ? Immediate'
  # ALU operations such as 'ADDI', 'ANDI', 'SLTI', etc.
  def alu_imm_op( self, cpu, rc, ra, imm, ff, f ):
    # Set the ALU 'function select' bits.
    with cpu.If( f == F_ADDI ):
      cpu.d.comb += self.alu.f.eq( ALU_ADD )
    with cpu.Elif( f == F_SLTI ):
      cpu.d.comb += self.alu.f.eq( ALU_SLT )
    with cpu.Elif( f == F_SLTIU ):
      cpu.d.comb += self.alu.f.eq( ALU_SLTU )
    with cpu.Elif( f == F_XORI ):
      cpu.d.comb += self.alu.f.eq( ALU_XOR )
    with cpu.Elif( f == F_ORI ):
      cpu.d.comb += self.alu.f.eq( ALU_OR )
    with cpu.Elif( f == F_ANDI ):
      cpu.d.comb += self.alu.f.eq( ALU_AND )
    with cpu.Elif( f == F_SLLI ):
      cpu.d.comb += self.alu.f.eq( ALU_SLL )
    with cpu.Elif( f == F_SRLI ):
      with cpu.If( ff == FF_SRAI ):
        cpu.d.comb += self.alu.f.eq( ALU_SRA )
      with cpu.Else():
        cpu.d.comb += self.alu.f.eq( ALU_SRL )
    # Set the ALU 'start' bit, and the constant 'immediate' value.
    cpu.d.comb += [
      self.alu.b.eq( imm ),
      self.alu.start.eq( 1 )
    ]
    # Connect appropriate registers to the ALU inputs and output.
    for i in range( 32 ):
      with cpu.If( ra == i ):
        cpu.d.comb += self.alu.a.eq( self.r[ i ] )
      if i > 0:
        with cpu.If( rc == i ):
          cpu.d.sync += self.r[ i ].eq( self.alu.y )

  def elaborate( self, platform ):
    # Core CPU module.
    m = Module()
    # Register the ALU, ROM and RAM submodules.
    m.submodules.alu = self.alu
    m.submodules.rom = self.rom
    m.submodules.ram = self.ram

    # Intermediate instruction and PC storage.
    opcode = Signal( 7, reset = 0b0000000 )
    f   = Signal( 3, reset = 0b000 )
    ff  = Signal( 7, reset = 0b0000000 )
    ra  = Signal( 5, reset = 0b00000 )
    rb  = Signal( 5, reset = 0b00000 )
    rc  = Signal( 5, reset = 0b00000 )
    imm = Signal( shape = Shape( width = 32, signed = True ),
                  reset = 0x00000000 )
    ipc = Signal( 32, reset = 0x00000000 )

    # r0 is hard-wired to 0.
    m.d.comb += self.r[ 0 ].eq( 0x00000000 )
    # Set the program counter to the simulated ROM address by default.
    # (Load operations can temporarily override this)
    m.d.comb += self.rom.addr.eq( self.pc )

    # Set the simulated RAM address to 0 by default, and set
    # the RAM's read/write enable bits to 0 by default.
    m.d.comb += [
      self.ram.addr.eq( 0 ),
      self.ram.ren.eq( 0 ),
      self.ram.wen.eq( 0 )
    ]

    # Main CPU FSM.
    with m.FSM() as fsm:
      # "ROM Fetch": Wait for the instruction to load from ROM, and
      #              populate register fields to prepare for decoding.
      with m.State( "CPU_PC_ROM_FETCH" ):
        m.d.comb += self.fsms.eq( CPU_PC_ROM_FETCH ) #TODO: Remove
        # I-type operations have one cohesive 12-bit immediate.
        with m.If( self.rom.out.bit_select( 0, 7 ) == OP_IMM ):
          # ...But shift operations are a special case with a 5-bit
          # unsigned immediate and 'funct7' bits in the MSbs.
          with m.If( ( self.rom.out.bit_select( 12, 3 ) == F_SLLI ) |
                     ( self.rom.out.bit_select( 12, 3 ) == F_SRLI ) ):
            m.d.sync += imm.eq( self.rom.out.bit_select( 20, 5 ) )
          with m.Else():
            with m.If( self.rom.out[ 31 ] ):
              m.d.sync += imm.eq( 0xFFFFF000 |
                                  self.rom.out.bit_select( 20, 12 ) )
            with m.Else():
              m.d.sync += imm.eq( self.rom.out.bit_select( 20, 12 ) )
        # S-type instructions have 12-bit immediates in two fields.
        with m.Elif( self.rom.out.bit_select( 0, 7 ) == OP_STORE ):
          with m.If( self.rom.out[ 31 ] ):
            m.d.sync += imm.eq( 0xFFFFF000 |
              self.rom.out.bit_select( 7, 4 ) |
              ( self.rom.out.bit_select( 25, 7 ) << 5 ) )
          with m.Else():
            m.d.sync += imm.eq(
              ( self.rom.out.bit_select( 7,  4 ) ) |
              ( self.rom.out.bit_select( 25, 7 ) << 5 ) )
        # U-type instructions just have a single 20-bit immediate,
        # with the register's remaining 12 LSbs padded with 0s.
        with m.Elif( ( self.rom.out.bit_select( 0, 7 ) == OP_LUI ) |
                     ( self.rom.out.bit_select( 0, 7 ) == OP_AUIPC ) ):
          m.d.sync += imm.eq( self.rom.out & 0xFFFFF000 )
        # J-type instructions have a 20-bit immediate encoding a
        # 21-bit value, with its bits scattered to the four winds.
        with m.Elif( self.rom.out.bit_select( 0, 7 ) == OP_JAL ):
          with m.If( self.rom.out[ 31 ] ):
            m.d.sync += imm.eq( 0xFFF00000 |
              ( self.rom.out.bit_select( 21, 10 ) << 1 ) |
              ( self.rom.out.bit_select( 20, 1 ) << 11 ) |
              ( self.rom.out.bit_select( 12, 8 ) << 12 ) |
              ( self.rom.out.bit_select( 31, 1 ) << 20 ) )
          with m.Else():
            m.d.sync += imm.eq(
              ( self.rom.out.bit_select( 21, 10 ) << 1 ) |
              ( self.rom.out.bit_select( 20, 1  ) << 11 ) |
              ( self.rom.out.bit_select( 12, 8  ) << 12 ) |
              ( self.rom.out.bit_select( 31, 1  ) << 20 ) )
        # B-type instructions have a 12-bit immediate encoding a
        # 13-bit value, with bits scattered around the instruction.
        with m.Elif( self.rom.out.bit_select( 0, 7 ) == OP_BRANCH ):
          with m.If( self.rom.out[ 31 ] ):
            m.d.sync += imm.eq( 0xFFFFE000 |
              ( self.rom.out.bit_select( 8,  4 ) << 1 ) |
              ( self.rom.out.bit_select( 25, 6 ) << 5 ) |
              ( self.rom.out.bit_select( 7,  1 ) << 11 ) |
              ( self.rom.out.bit_select( 31, 1 ) << 12 ) )
          with m.Else():
            m.d.sync += imm.eq(
              ( self.rom.out.bit_select( 8,  4 ) << 1 ) |
              ( self.rom.out.bit_select( 25, 6 ) << 5 ) |
              ( self.rom.out.bit_select( 7,  1 ) << 11 ) |
              ( self.rom.out.bit_select( 31, 1 ) << 12 ) )
        # R-type operations have no immediates.
        with m.Elif( self.rom.out.bit_select( 0, 7 ) == OP_REG ):
          m.d.sync += imm.eq( 0x00000000 )
        # TODO: support 'FENCE' and 'SYSTEM' instructions.
        # Unrecognized opcodes set the immediate value to 0.
        with m.Else():
          m.d.sync += imm.eq( 0x00000000 )
        # Populate "opcode, funct3, funct7, r1, r2, rd". I call them
        # "opcode, f, ff, ra, rb, rc", respectively. Why? Because
        # I can't name a variable '1' for 'r1'; 'a' is easier.
        # Not every type of operation uses every value, but at least
        # they're placed in consistent locations when they are used.
        m.d.sync += [
          opcode.eq( self.rom.out.bit_select( 0, 7 ) ),
          rc.eq( self.rom.out.bit_select( 7,  5 ) ),
          f.eq( self.rom.out.bit_select( 12, 3 ) ),
          ra.eq( self.rom.out.bit_select( 15, 5 ) ),
          rb.eq( self.rom.out.bit_select( 20, 5 ) ),
          ff.eq( self.rom.out.bit_select( 25, 7 ) ),
          ipc.eq( self.pc )
        ]
        m.next = "CPU_PC_DECODE"
      # "Decode PC": Figure out what sort of instruction to execute,
      #              and prepare associated registers.
      with m.State( "CPU_PC_DECODE" ):
        m.d.comb += self.fsms.eq( CPU_PC_DECODE ) #TODO: Remove
        # "Load Upper Immediate" instruction:
        with m.If( opcode == OP_LUI ):
          for i in range( 1, 32 ):
            with m.If( rc == i ):
              m.d.sync += self.r[ i ].eq( imm )
          m.next = "CPU_PC_LOAD"
        # "Add Upper Immediate to PC" instruction:
        with m.Elif( opcode == OP_AUIPC ):
          for i in range( 1, 32 ):
            with m.If( ra == i ):
              m.d.sync += self.r[ i ].eq( imm + self.pc )
          m.next = "CPU_PC_LOAD"
        # "Jump And Link" instruction:
        with m.Elif( opcode == OP_JAL ):
          for i in range( 1, 32 ):
            with m.If( rc == i ):
              m.d.sync += self.r[ i ].eq( ipc + 4 )
          m.d.nsync += self.pc.eq( self.pc + imm )
          m.next = "CPU_PC_ROM_FETCH"
        # "Jump And Link from Register" instruction:
        # TODO: verify that funct3 bits == 0b000?
        with m.Elif( opcode == OP_JALR ):
          for i in range( 32 ):
            with m.If( ra == i ):
              m.d.nsync += self.pc.eq( ( self.r[ i ] + imm ) &
                                       ( 0xFFFFFFFE ) )
            if i > 0:
              with m.If( rc == i ):
                m.d.sync += self.r[ i ].eq( ipc + 4 )
          m.next = "CPU_PC_ROM_FETCH"
        # "Conditional Branch" instructions:
        with m.Elif( opcode == OP_BRANCH ):
          for i in range( 32 ):
            for j in range( 32 ):
              with m.If( ( ra == i ) & ( rb == j ) ):
                # "Branch if EQual" operation:
                with m.If( ( f == F_BEQ ) &
                           ( self.r[ i ] == self.r[ j ] ) ):
                    m.d.nsync += self.pc.eq( self.pc + imm )
                    m.next = "CPU_PC_ROM_FETCH"
                # "Branch if Not Equal" operation:
                with m.Elif( ( f == F_BNE ) &
                             ( self.r[ i ] != self.r[ j ] ) ):
                    m.d.nsync += self.pc.eq( self.pc + imm )
                    m.next = "CPU_PC_ROM_FETCH"
                # "Branch if Less Than" operation:
                # TODO: Currently performs unsigned comparison...
                with m.Elif( f == F_BLT ):
                  with m.If( self.r[ i ] < self.r[ j ] ):
                    m.d.nsync += self.pc.eq( self.pc + imm )
                    m.next = "CPU_PC_ROM_FETCH"
                # "Branch if Greater or Equal" operation:
                # TODO: Currently performs unsigned comparison...
                with m.Elif( f == F_BGE ):
                  with m.If( self.r[ j ] < self.r[ i ] ):
                    m.d.nsync += self.pc.eq( self.pc + imm )
                    m.next = "CPU_PC_ROM_FETCH"
                # "Branch if Less Than (Unsigned)" operation:
                with m.Elif( f == F_BLTU ):
                  with m.If( self.r[ i ] < self.r[ j ] ):
                    m.d.nsync += self.pc.eq( self.pc + imm )
                    m.next = "CPU_PC_ROM_FETCH"
                # "Branch if Greater or Equal (Unsigned)" operation:
                with m.Elif( f == F_BGEU ):
                  with m.If( self.r[ j ] < self.r[ i ] ):
                    m.d.nsync += self.pc.eq( self.pc + imm )
                    m.next = "CPU_PC_ROM_FETCH"
                with m.Else():
                  m.next = "CPU_PC_LOAD"
        # TODO: "Load from Memory" instructions:
        with m.Elif( opcode == OP_LOAD ):
          # "Load Byte" operation:
          with m.If( f == F_LB ):
            m.next = "CPU_PC_LOAD"
          # "Load Halfword" operation:
          with m.Elif( f == F_LH ):
            m.next = "CPU_PC_LOAD"
          # "Load Word" operation:
          with m.Elif( f == F_LW ):
            m.next = "CPU_PC_LOAD"
          # "Load Byte" (without sign extension) operation:
          with m.Elif( f == F_LBU ):
            m.next = "CPU_PC_LOAD"
          # "Load Halfword" (without sign extension) operation:
          with m.Elif( f == F_LHU ):
            m.next = "CPU_PC_LOAD"
        # TODO: "Store to Memory" instructions:
        with m.Elif( opcode == OP_STORE ):
          # "Store Byte" operation:
          with m.If( f == F_SB ):
            m.next = "CPU_PC_LOAD"
          # "Store Halfword" operation:
          with m.Elif( f == F_SH ):
            m.next = "CPU_PC_LOAD"
          # "Store Word" operation:
          with m.Elif( f == F_SW ):
            m.next = "CPU_PC_LOAD"
        # "Register-Based" instructions:
        with m.Elif( opcode == OP_REG ):
          self.alu_reg_op( m, rc, ra, rb, ff, f )
          m.next = "CPU_PC_LOAD"
        # "Immediate-Based" instructions:
        with m.Elif( opcode == OP_IMM ):
          self.alu_imm_op( m, rc, ra, imm, ff, f )
          m.next = "CPU_PC_LOAD"
        # TODO: "System / Exception" instructions:
        with m.Elif( opcode == OP_SYSTEM ):
          m.next = "CPU_PC_LOAD"
        # TODO: "Memory Fence" instruction:
        with m.Elif( opcode == OP_FENCE ):
          m.next = "CPU_PC_LOAD"
        # Unrecognized operations skip to loading the next
        # PC value, although the RISC-V spec says that this
        # should trigger an error.
        with m.Else():
          m.next = "CPU_PC_LOAD"
      with m.State( "CPU_PC_LOAD" ):
        m.d.comb += self.fsms.eq( CPU_PC_LOAD ) # TODO: Remove
        m.d.nsync += self.pc.eq( self.pc + 4 )
        m.next = "CPU_PC_ROM_FETCH"

    # End of CPU module definition.
    return m

##################
# CPU testbench: #
##################

# Import test programs and expected runtime register values.
from programs import *

# Helper method to check expected CPU register / memory values
# at a specific point during a test program.
def check_vals( expected, ni, cpu ):
  if ni in expected:
    for j in range( len( expected[ ni ] ) ):
      ex = expected[ ni ][ j ]
      # Special case: program counter.
      if ex[ 'r' ] == 'pc':
        cpc = yield cpu.pc
        if hexs( cpc ) == hexs( ex[ 'e' ] ):
          print( "  \033[32mPASS:\033[0m pc  == %s"
                 " after %d operations"
                 %( hexs( ex[ 'e' ] ), ni ) )
        else:
          print( "  \033[31mFAIL:\033[0m pc  == %s"
                 " after %d operations (got: %s)"
                 %( hexs( ex[ 'e' ] ), ni, hexs( cpc ) ) )
      # Special case: RAM data.
      elif type( ex[ 'r' ] ) == str and ex[ 'r' ][ 0:3 ] == "RAM":
        rama = int( ex[ 'r' ][ 3: ] )
        if ( rama % 4 ) != 0:
          print( "  \033[31mFAIL:\033[0m RAM == %s @ 0x%08X"
                 " after %d operations (mis-aligned address)"
                 %( hexs( ex[ 'e' ] ), rama, ni ) )
        else:
          cpd = yield cpu.ram.data[ rama // 4 ]
          if hexs( cpd ) == hexs( ex[ 'e' ] ):
            print( "  \033[32mPASS:\033[0m RAM == %s @ 0x%08X"
                   " after %d operations"
                   %( hexs( ex[ 'e' ] ), rama, ni ) )
          else:
            print( "  \033[31mFAIL:\033[0m RAM == %s @ 0x%08X"
                   " after %d operations (got: %s)"
                   %( hexs( ex[ 'e' ] ), rama, ni, hexs( cpd ) ) )
      # Numbered general-purpose registers.
      elif ex[ 'r' ] >= 0 and ex[ 'r' ] < 32:
        cr = yield cpu.r[ ex[ 'r' ] ]
        if hexs( cr ) == hexs( ex[ 'e' ] ):
          print( "  \033[32mPASS:\033[0m r%02d == %s"
                 " after %d operations"
                 %( ex[ 'r' ], hexs( ex[ 'e' ] ), ni ) )
        else:
          print( "  \033[31mFAIL:\033[0m r%02d == %s"
                 " after %d operations (got: %s)"
                 %( ex[ 'r' ], hexs( ex[ 'e' ] ),
                    ni, hexs( cr ) ) )

# Helper method to run a CPU device for a given number of cycles,
# and verify its expected register values over time.
def cpu_run( cpu, expected ):
  # Record how many CPU instructions have executed.
  ni = 0
  # Check initial values, if any.
  yield from check_vals( expected, 0, cpu )
  # Let the CPU run for N ticks.
  while ni <= expected[ 'end' ]:
    # Let combinational logic settle before checking values.
    yield Settle()
    # Only check expected values once per instruction.
    fsm_state = yield cpu.fsms
    if fsm_state == CPU_PC_ROM_FETCH:
      ni += 1
      # Check expected values, if any.
      yield from check_vals( expected, ni, cpu )
    # Step the simulation.
    yield Tick()

# Helper method to simulate running a CPU with the given ROM image
# for the specified number of CPU cycles. The 'name' field is used
# for printing and generating the waveform filename: "cpu_[name].vcd".
# The 'expected' dictionary contains a series of expected register
# values at specific points in time, defined by elapsed instructions.
def cpu_sim( test ):
  print( "\033[33mSTART\033[0m running '%s' program:"%test[ 0 ] )
  # Create the CPU device.
  cpu = CPU( test[ 2 ] )

  # Run the simulation.
  sim_name = "%s.vcd"%test[ 1 ]
  with Simulator( cpu, vcd_file = open( sim_name, 'w' ) ) as sim:
    def proc():
      # Run the program and print pass/fail for individual tests.
      yield from cpu_run( cpu, test[ 3 ] )
      print( "\033[35mDONE\033[0m running %s: executed %d instructions"
             %( test[ 0 ], test[ 3 ][ 'end' ] ) )
    sim.add_clock( 24e-6 )
    sim.add_clock( 24e-6, domain = "nsync" )
    sim.add_sync_process( proc )
    sim.run()

# 'main' method to run a basic testbench.
if __name__ == "__main__":
  # RV32I operation RISC-V tests.
  # Simulate the 'ADD test' ROM.
  cpu_sim( add_test )
  # Simulate the 'ADDI test' ROM.
  cpu_sim( addi_test )

  # Miscellaneous tests which are not part of the RV32I test suite.
  # Simulate the 'quick test' ROM.
  cpu_sim( quick_test )
  # Simulate the 'infinite loop test' ROM.
  cpu_sim( loop_test )
