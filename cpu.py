from nmigen import *
from nmigen.back.pysim import *

from alu import *
from isa import *
from mux_rom import *
from rom import *
from ram import *
from cpu_helpers import *

###############
# CPU module: #
###############

# FSM state definitions. TODO: Remove after figuring out how to
# access the internal FSM from tests. Also, consolidate these steps...
CPU_RESET        = 0
CPU_PC_LOAD      = 1
CPU_PC_ROM_FETCH = 2
CPU_PC_DECODE    = 3
CPU_LD           = 4
CPU_STATES_MAX   = 4

# CPU module.
class CPU( Elaboratable ):
  def __init__( self, rom_module ):
    # Program Counter register.
    self.pc = Signal( 32, reset = 0x00000000 )
    # Intermediate load/store memory pointer.
    self.mp = Signal( 32, reset = 0x00000000 )
    # The main 32 CPU registers.
    self.r  = Array(
      Signal( 32, reset = 0x00000000, name = "r%d"%i )
      for i in range( 32 )
    )
    # Intermediate instruction and PC storage.
    self.opcode = Signal( 7, reset = 0b0000000 )
    self.f      = Signal( 3, reset = 0b000 )
    self.ff     = Signal( 7, reset = 0b0000000 )
    self.ra     = Signal( 5, reset = 0b00000 )
    self.rb     = Signal( 5, reset = 0b00000 )
    self.rc     = Signal( 5, reset = 0b00000 )
    self.imm    = Signal( shape = Shape( width = 32, signed = True ),
                          reset = 0x00000000 )
    self.ipc    = Signal( 32, reset = 0x00000000 )
    # ROM wait states.
    self.ws     = Signal( 3, reset = 0b000 )
    # The ALU submodule which performs logical operations.
    self.alu    = ALU()
    # The ROM submodule (or multiplexed test ROMs) which act as
    # simulated program data storage for the CPU.
    self.rom    = rom_module
    # The RAM submodule which simulates re-writable data storage.
    # (1KB of RAM = 256 words)
    self.ram    = RAM( 256 )

    # Debugging signal(s):
    # Track FSM state. TODO: There must be a way to access this
    # from the Module's FSM object, but I don't know how.
    self.fsms = Signal( range( CPU_STATES_MAX ),
                        reset = CPU_PC_ROM_FETCH )

  # CPU object's 'elaborate' method to generate the hardware logic.
  def elaborate( self, platform ):
    # Core CPU module.
    m = Module()
    # Register the ALU, ROM and RAM submodules.
    m.submodules.alu = self.alu
    m.submodules.rom = self.rom
    m.submodules.ram = self.ram

    # Reset countdown.
    rsc = Signal( 2, reset = 0b11 )
    # ROM wait state countdown.
    rws = Signal( 3, reset = 0b00 )

    # r0 should always be 0.
    m.d.sync += self.r[ 0 ].eq( 0x00000000 )
    # Set the program counter to the simulated memory addresses
    # by default. Load operations temporarily override this.
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
      # "Reset state": Wait a few ticks after reset, to let ROM load.
      with m.State( "CPU_RESET" ):
        m.d.comb += self.fsms.eq( CPU_RESET ) #TODO: Remove
        with m.If( rsc > 0 ):
          m.d.sync += rsc.eq( rsc - 1 )
        with m.Else():
          m.next = "CPU_PC_ROM_FETCH"
      # "ROM Fetch": Wait for the instruction to load from ROM, and
      #              populate register fields to prepare for decoding.
      with m.State( "CPU_PC_ROM_FETCH" ):
        m.d.comb += self.fsms.eq( CPU_PC_ROM_FETCH ) #TODO: Remove
        # If the PC address is in RAM, maintain combinatorial
        # logic to read the instruction from RAM.
        with m.If( ( ( self.pc ) & 0xE0000000 ) == 0x20000000 ):
          m.d.comb += [
            self.ram.addr.eq( ( self.pc ) & 0x1FFFFFFF ),
            self.ram.ren.eq( 1 )
          ]
          # Decode the fetched instruction and move on to run it.
          rv32i_decode( self, m, self.ram.dout )
          m.next = "CPU_PC_DECODE"
        # Otherwise, read from ROM.
        with m.Else():
          with m.If( rws < self.ws ):
            m.d.sync += rws.eq( rws + 1 )
          with m.Else():
            # Reset the 'ROM wait-states' counter.
            m.d.sync += rws.eq( 0 )
            # Decode the fetched instruction and move on to run it.
            rv32i_decode( self, m, self.rom.out )
            m.next = "CPU_PC_DECODE"
      # "Decode PC": Figure out what sort of instruction to execute,
      #              and prepare associated registers.
      with m.State( "CPU_PC_DECODE" ):
        m.d.comb += self.fsms.eq( CPU_PC_DECODE ) #TODO: Remove
        # "Load Upper Immediate" instruction:
        with m.If( self.opcode == OP_LUI ):
          with m.If( self.rc > 0 ):
            m.d.sync += self.r[ self.rc ].eq( self.imm )
          m.next = "CPU_PC_LOAD"
        # "Add Upper Immediate to PC" instruction:
        with m.Elif( self.opcode == OP_AUIPC ):
          with m.If( self.rc > 0 ):
            m.d.sync += self.r[ self.rc ].eq( self.imm + self.ipc )
          m.next = "CPU_PC_LOAD"
        # "Jump And Link" instruction:
        with m.Elif( self.opcode == OP_JAL ):
          with m.If( self.rc > 0 ):
            m.d.sync += self.r[ self.rc ].eq( self.ipc + 4 )
          jump_to( self, m, ( self.ipc + self.imm ) )
          m.next = "CPU_PC_ROM_FETCH"
        # "Jump And Link from Register" instruction:
        # TODO: verify that funct3 bits == 0b000?
        with m.Elif( self.opcode == OP_JALR ):
          jump_to( self, m,
                   ( self.r[ self.ra ] + self.imm ) & 0xFFFFFFFE )
          with m.If( self.rc > 0 ):
            m.d.sync += self.r[ self.rc ].eq( self.ipc + 4 )
          m.next = "CPU_PC_ROM_FETCH"
        # "Conditional Branch" instructions:
        # TODO: Should these defer to the ALU for compare operations?
        with m.Elif( self.opcode == OP_BRANCH ):
          # "Branch if EQual" operation:
          with m.If( self.f == F_BEQ ):
            with m.If( self.r[ self.ra ] == self.r[ self.rb ] ):
              jump_to( self, m, ( self.ipc + self.imm ) )
              m.next = "CPU_PC_ROM_FETCH"
            with m.Else():
              m.next = "CPU_PC_LOAD"
          # "Branch if Not Equal" operation:
          with m.Elif( ( self.f == F_BNE ) &
                       ( self.r[ self.ra ] != self.r[ self.rb ] ) ):
              jump_to( self, m, ( self.ipc + self.imm ) )
              m.next = "CPU_PC_ROM_FETCH"
          # "Branch if Less Than" operation:
          with m.Elif( ( self.f == F_BLT ) &
                   ( ( ( self.r[ self.rb ].bit_select( 31, 1 ) ==
                         self.r[ self.ra ].bit_select( 31, 1 ) ) &
                       ( self.r[ self.ra ] < self.r[ self.rb ] ) ) |
                       ( self.r[ self.ra ].bit_select( 31, 1 ) >
                         self.r[ self.rb ].bit_select( 31, 1 ) ) ) ):
              jump_to( self, m, ( self.ipc + self.imm ) )
              m.next = "CPU_PC_ROM_FETCH"
          # "Branch if Greater or Equal" operation:
          with m.Elif( ( self.f == F_BGE ) &
                   ( ( ( self.r[ self.rb ].bit_select( 31, 1 ) ==
                         self.r[ self.ra ].bit_select( 31, 1 ) ) &
                       ( self.r[ self.ra ] >= self.r[ self.rb ] ) ) |
                       ( self.r[ self.rb ].bit_select( 31, 1 ) >
                         self.r[ self.ra ].bit_select( 31, 1 ) ) ) ):
              jump_to( self, m, ( self.ipc + self.imm ) )
              m.next = "CPU_PC_ROM_FETCH"
          # "Branch if Less Than (Unsigned)" operation:
          with m.Elif( ( self.f == F_BLTU ) &
                       ( self.r[ self.ra ] < self.r[ self.rb ] ) ):
              jump_to( self, m, ( self.ipc + self.imm ) )
              m.next = "CPU_PC_ROM_FETCH"
          # "Branch if Greater or Equal (Unsigned)" operation:
          with m.Elif( ( self.f == F_BGEU ) &
                       ( self.r[ self.ra ] >= self.r[ self.rb ] ) ):
              jump_to( self, m, ( self.ipc + self.imm ) )
              m.next = "CPU_PC_ROM_FETCH"
          with m.Else():
            m.next = "CPU_PC_LOAD"
        # "Load from Memory" instructions:
        # Addresses in 0x2xxxxxxx memory space are treated as RAM.
        # There are no alignment requirements (yet).
        with m.Elif( self.opcode == OP_LOAD ):
          # Populate 'mp' with the memory address to load from.
          m.d.comb += self.mp.eq( self.r[ self.ra ] + self.imm )
          with m.If( ( self.mp & 0xE0000000 ) == 0x20000000 ):
            m.d.comb += [
              self.ram.addr.eq( self.mp & 0x1FFFFFFF ),
              self.ram.ren.eq( 0b1 )
            ]
          with m.Else():
            m.d.comb += self.rom.addr.eq( self.mp )
          # Memory access is not instantaneous, so the next state is
          # 'CPU_LD' which allows time for the data to arrive.
          m.next = "CPU_LD"
        # "Store to Memory" instructions:
        # Addresses in 0x2xxxxxxx memory space are treated as RAM.
        # Writes to other addresses are ignored because,
        # surprise surprise, ROM is read-only.
        # There are no alignment requirements (yet).
        with m.Elif( self.opcode == OP_STORE ):
          # Populate 'mp' with the memory address to load from.
          m.d.comb += self.mp.eq( self.r[ self.ra ] + self.imm )
          with m.If( ( self.mp & 0xE0000000 ) == 0x20000000 ):
            m.d.comb += [
              self.ram.addr.eq( self.mp & 0x1FFFFFFF ),
              self.ram.wen.eq( 0b1 )
            ]
            m.d.comb += self.ram.din.eq( self.r[ self.rb ] )
            # "Store Byte" operation:
            with m.If( self.f == F_SB ):
              m.d.comb += self.ram.dw.eq( 0b00 )
            # "Store Halfword" operation:
            with m.Elif( self.f == F_SH ):
              m.d.comb += self.ram.dw.eq( 0b01 )
            # "Store Word" operation:
            with m.Elif( self.f == F_SW ):
              m.d.comb += self.ram.dw.eq( 0b11 )
          m.next = "CPU_PC_LOAD"
        # "Register-Based" instructions:
        with m.Elif( self.opcode == OP_REG ):
          alu_reg_op( self, m )
          m.next = "CPU_PC_LOAD"
        # "Immediate-Based" instructions:
        with m.Elif( self.opcode == OP_IMM ):
          alu_imm_op( self, m )
          m.next = "CPU_PC_LOAD"
        with m.Elif( self.opcode == OP_SYSTEM ):
          # "EBREAK" instruction: For now, halt execution of the
          # program. It sounds like this is usually used to hand off
          # control of the program to a debugger, but this CPU has no
          # debugging interface yet. And apparently compilers sometimes
          # use this instruction to mark invalid code paths, so...yeah.
          with m.If( ( self.ra  == 0 )
                   & ( self.rb  == 0 )
                   & ( self.f   == 0 )
                   & ( self.imm == 0x001 ) ):
            # Read PC from RAM if the address is in that memory space.
            with m.If( ( self.pc & 0xE0000000 ) == 0x20000000 ):
              m.d.comb += [
                self.ram.addr.eq( self.pc & 0x1FFFFFFF ),
                self.ram.ren.eq( 1 )
              ]
            # Loop back without moving the Program Counter.
            m.next = "CPU_PC_ROM_FETCH"
          # TODO: "Environment Call" instructions:
          with m.Else():
            m.next = "CPU_PC_ROM_FETCH"
        # "Memory Fence" instruction:
        # For now, this doesn't actually need to do anything.
        # Memory operations are globally visible as soon as they
        # complete, in both the simulated RAM and ROM modules. Also,
        # this CPU only has one 'hart' (hardware thread).
        # But if I ever implement an instruction cache, this
        # operation should empty and/or refresh it.
        with m.Elif( self.opcode == OP_FENCE ):
          m.next = "CPU_PC_LOAD"
        # Unrecognized operations skip to loading the next
        # PC value, although the RISC-V spec says that this
        # should trigger an error.
        with m.Else():
          m.next = "CPU_PC_LOAD"
      # "Load operation" - wait for a load instruction to finish
      # fetching data from memory.
      with m.State( "CPU_LD" ):
        m.d.comb += self.fsms.eq( CPU_LD ) # TODO: Remove
        # Maintain the cominatorial logic holding the memory
        # address at the 'mp' (memory pointer) value.
        m.d.comb += self.mp.eq( self.r[ self.ra ] + self.imm )
        with m.If( ( self.mp & 0xE0000000 ) == 0x20000000 ):
          m.d.comb += [
            self.ram.addr.eq( self.mp & 0x1FFFFFFF ),
            self.ram.ren.eq( 0b1 )
          ]
        with m.Else():
          m.d.comb += self.rom.addr.eq( self.mp )
        # "Load Byte" operation:
        with m.If( self.f == F_LB ):
          with m.If( self.rc > 0 ):
            with m.If( ( self.mp & 0xE0000000 ) == 0x20000000 ):
              with m.If( self.ram.dout[ 7 ] ):
                m.d.sync += self.r[ self.rc ].eq(
                  ( self.ram.dout & 0xFF ) | 0xFFFFFF00 )
              with m.Else():
                m.d.sync += self.r[ self.rc ].eq(
                  ( self.ram.dout & 0xFF ) )
            with m.Else():
              with m.If( self.rom.out[ 7 ] ):
                m.d.sync += self.r[ self.rc ].eq(
                  ( self.rom.out & 0xFF ) | 0xFFFFFF00 )
              with m.Else():
                m.d.sync += self.r[ self.rc ].eq(
                  ( self.rom.out & 0xFF ) )
        # "Load Halfword" operation:
        with m.Elif( self.f == F_LH ):
          with m.If( self.rc > 0 ):
            with m.If( ( self.mp & 0xE0000000 ) == 0x20000000 ):
              with m.If( self.ram.dout[ 15 ] ):
                m.d.sync += self.r[ self.rc ].eq(
                  ( self.ram.dout & 0xFFFF ) | 0xFFFF0000 )
              with m.Else():
                m.d.sync += self.r[ self.rc ].eq(
                  ( self.ram.dout & 0xFFFF ) )
            with m.Else():
              with m.If( self.rom.out[ 15 ] ):
                m.d.sync += self.r[ self.rc ].eq(
                  ( self.rom.out & 0xFFFF ) | 0xFFFF0000 )
              with m.Else():
                m.d.sync += self.r[ self.rc ].eq(
                  ( self.rom.out & 0xFFFF ) )
        # "Load Word" operation:
        with m.Elif( self.f == F_LW ):
          with m.If( self.rc > 0 ):
            with m.If( ( self.mp & 0xE0000000 ) == 0x20000000 ):
              m.d.sync += self.r[ self.rc ].eq( self.ram.dout )
            with m.Else():
              m.d.sync += self.r[ self.rc ].eq( self.rom.out )
        # "Load Byte" (without sign extension) operation:
        with m.Elif( self.f == F_LBU ):
          with m.If( self.rc > 0 ):
            with m.If( ( self.mp & 0xE0000000 ) == 0x20000000 ):
              m.d.sync += self.r[ self.rc ].eq( self.ram.dout & 0xFF )
            with m.Else():
              m.d.sync += self.r[ self.rc ].eq( self.rom.out & 0xFF )
        # "Load Halfword" (without sign extension) operation:
        with m.Elif( self.f == F_LHU ):
          with m.If( self.rc > 0 ):
            with m.If( ( self.mp & 0xE0000000 ) == 0x20000000 ):
              m.d.sync += self.r[ self.rc ].eq(
                ( self.ram.dout & 0xFFFF ) )
            with m.Else():
              m.d.sync += self.r[ self.rc ].eq(
                ( self.rom.out & 0xFFFF ) )
        m.next = "CPU_PC_LOAD"
      # "PC Load Letter" - increment the PC.
      with m.State( "CPU_PC_LOAD" ):
        m.d.comb += self.fsms.eq( CPU_PC_LOAD ) # TODO: Remove
        jump_to( self, m, ( self.ipc + 4 ) )
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
          cpda = yield cpu.ram.data[ rama ]
          cpdb = yield cpu.ram.data[ rama + 1 ]
          cpdc = yield cpu.ram.data[ rama + 2 ]
          cpdd = yield cpu.ram.data[ rama + 3 ]
          cpd  = ( cpda |
                 ( cpdb << 8  ) |
                 ( cpdc << 16 ) |
                 ( cpdd << 24 ) )
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
  ni = -1
  am_fetching = False
  # Watch for timeouts if the CPU gets into a bad state.
  timeout = 0
  # Let the CPU run for N ticks.
  while ni <= expected[ 'end' ]:
    # Let combinational logic settle before checking values.
    yield Settle()
    timeout = timeout + 1
    # Only check expected values once per instruction.
    fsm_state = yield cpu.fsms
    if fsm_state == CPU_PC_ROM_FETCH and not am_fetching:
      am_fetching = True
      ni += 1
      timeout = 0
      # Check expected values, if any.
      yield from check_vals( expected, ni, cpu )
    elif timeout > 1000:
      print( "\033[31mFAIL: Timeout\033[0m" )
      break
    elif fsm_state != CPU_PC_ROM_FETCH:
      am_fetching = False
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
      # Initialize RAM values. TODO: The application should do this,
      # but I've removed a bunch of startup code from the tests to
      # skip over CSR calls which I haven't implemented yet.
      for i in range( len( test[ 3 ] ) ):
        yield cpu.ram.data[ i ].eq( test[ 3 ][ i ] )
      # Run the program and print pass/fail for individual tests.
      yield from cpu_run( cpu, test[ 4 ] )
      print( "\033[35mDONE\033[0m running %s: executed %d instructions"
             %( test[ 0 ], test[ 4 ][ 'end' ] ) )
    sim.add_clock( 24e-6 )
    sim.add_clock( 24e-6, domain = "nsync" )
    sim.add_sync_process( proc )
    sim.run()

# Helper method to simulate running multiple ROM modules in sequence.
# TODO: Does not currently support initialized RAM values.
def cpu_mux_sim( tests ):
  print( "\033[33mSTART\033[0m running '%s' program:"%tests[ 0 ] )
  # Create the CPU device.
  cpu = CPU( tests[ 2 ] )
  num_i = 0
  for t in tests[ 3 ]:
    num_i = num_i + t[ 'end' ]

  # Run the simulation.
  sim_name = "%s.vcd"%tests[ 1 ]
  with Simulator( cpu, vcd_file = open( sim_name, 'w' ) ) as sim:
    def proc():
      # Set one wait state for ROM access, to allow the ROM address
      # and data to propagate through the multiplexer.
      yield cpu.ws.eq( 0b001 )
      # Run the programs and print pass/fail for individual tests.
      for i in range( len( tests[ 3 ] ) ):
        yield cpu.alu.clk_rst.eq( 1 )
        yield Tick()
        yield cpu.alu.clk_rst.eq( 0 )
        yield Tick()
        yield cpu.rom.select.eq( i )
        yield Settle()
        yield from cpu_run( cpu, tests[ 3 ][ i ] )
      print( "\033[35mDONE\033[0m running %s: executed %d instructions"
             %( tests[ 0 ], num_i ) )
    sim.add_clock( 24e-6 )
    sim.add_clock( 24e-6, domain = "nsync" )
    sim.add_sync_process( proc )
    sim.run()

# 'main' method to run a basic testbench.
if __name__ == "__main__":
  # Run auto-generated RV32I tests one-by-one.
  cpu_sim( add_test )
  cpu_sim( addi_test )
  cpu_sim( and_test )
  cpu_sim( andi_test )
  cpu_sim( auipc_test )
  cpu_sim( beq_test )
  cpu_sim( bge_test )
  cpu_sim( bgeu_test )
  cpu_sim( blt_test )
  cpu_sim( bltu_test )
  cpu_sim( bne_test )
  cpu_sim( fence_i_test )
  cpu_sim( jal_test )
  cpu_sim( jalr_test )
  cpu_sim( lb_test )
  cpu_sim( lbu_test )
  cpu_sim( lh_test )
  cpu_sim( lhu_test )
  cpu_sim( lw_test )
  cpu_sim( lui_test )
  cpu_sim( or_test )
  cpu_sim( ori_test )
  cpu_sim( sb_test )
  cpu_sim( sh_test )
  cpu_sim( sw_test )
  cpu_sim( sll_test )
  cpu_sim( slli_test )
  cpu_sim( slt_test )
  cpu_sim( slti_test )
  cpu_sim( sltu_test )
  cpu_sim( sltiu_test )
  cpu_sim( sra_test )
  cpu_sim( srai_test )
  cpu_sim( srl_test )
  cpu_sim( srli_test )
  cpu_sim( sub_test )
  cpu_sim( xor_test )
  cpu_sim( xori_test )
  # Alternate option: Run with multiplexed ROM.
  # But this doesn't seem to speed up the tests like I'd hoped :/
  #cpu_mux_sim( rv32i_tests )

  # Miscellaneous tests which are not part of the RV32I test suite.
  # Simulate the ADD and ADDI test ROMs, using a multiplexed ROM
  # module and checking every expected value along the way.
  cpu_mux_sim( add_mux_test )
  # Simulate the 'run from RAM' test ROM.
  cpu_sim( ram_pc_test )
  # Simulate a basic 'quick test' ROM.
  cpu_sim( quick_test )
  # Simulate the 'infinite loop test' ROM.
  cpu_sim( loop_test )
