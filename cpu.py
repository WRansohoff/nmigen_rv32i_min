from nmigen import *
from nmigen.back.pysim import *
from nmigen_boards.upduino_v2 import *

from alu import *
from csr import *
from isa import *
from mux_rom import *
from spi_rom import *
from rom import *
from rvmem import *
from cpu_helpers import *

import os
import sys
import warnings

# Optional: Enable verbose output for debugging.
#os.environ["NMIGEN_verbose"] = "Yes"

# CPU module.
class CPU( Elaboratable ):
  def __init__( self, rom_module ):
    # CPU signals:
    # 'Reset' signal for clock domains.
    self.clk_rst = Signal( reset = 0b0, reset_less = True )
    # Program Counter register.
    self.pc = Signal( 32, reset = 0x00000000 )
    # The main 32 CPU registers.
    self.r      = Memory( width = 32, depth = 32,
                          init = ( 0x00000000 for i in range( 32 ) ) )

    # CPU submodules:
    # Memory access ports for rs1 (ra), rs2 (rb), and rd (rc).
    self.ra     = self.r.read_port()
    self.rb     = self.r.read_port()
    self.rc     = self.r.write_port()
    # The ALU submodule which performs logical operations.
    self.alu    = ALU()
    # CSR 'system registers'.
    self.csr    = CSR()
    # Memory module to hold peripherals and ROM / RAM module(s)
    # (4KB of RAM = 1024 words)
    self.mem    = RV_Memory( rom_module, 1024 )

  # CPU object's 'elaborate' method to generate the hardware logic.
  def elaborate( self, platform ):
    # Core CPU module.
    m = Module()
    # Register the ALU, CSR, and memory submodules.
    m.submodules.alu = self.alu
    m.submodules.csr = self.csr
    m.submodules.mem = self.mem
    # Register the CPU register read/write ports.
    m.submodules.ra  = self.ra
    m.submodules.rb  = self.rb
    m.submodules.rc  = self.rc

    # Wait-state counter to let internal memories load.
    iws = Signal( 2, reset = 0 )

    # Top-level combinatorial logic.
    m.d.comb += [
      # Set CPU register access addresses.
      self.ra.addr.eq( self.mem.imux.bus.dat_r[ 15 : 20 ] ),
      self.rb.addr.eq( self.mem.imux.bus.dat_r[ 20 : 25 ] ),
      self.rc.addr.eq( self.mem.imux.bus.dat_r[ 7  : 12 ] ),
      # Instruction bus address is always set to the program counter.
      self.mem.imux.bus.adr.eq( self.pc ),
      # The CSR inputs are always wired the same.
      self.csr.dat_w.eq(
        Mux( self.mem.imux.bus.dat_r[ 14 ] == 0,
             self.ra.data,
             Cat( self.ra.addr,
                  Repl( self.ra.addr[ 4 ], 27 ) ) ) ),
      self.csr.f.eq( self.mem.imux.bus.dat_r[ 12 : 15 ] ),
      self.csr.adr.eq( self.mem.imux.bus.dat_r[ 20 : 32 ] ),
      # Store data and width are always wired the same.
      self.mem.ram.dw.eq( self.mem.imux.bus.dat_r[ 12 : 15 ] ),
      self.mem.dmux.bus.dat_w.eq( self.rb.data ),
      # The ALU's 'a' input can always be set to the 'ra' register.
      self.alu.a.eq( self.ra.data )
    ]

    # Trigger an 'instruction mis-aligned' trap if necessary.
    with m.If( self.pc[ :2 ] != 0 ):
      m.d.sync += self.csr.mtval_einfo.eq( self.pc )
      trigger_trap( self, m, TRAP_IMIS )
    with m.Else():
      # I-bus is active until it completes a transaction.
      m.d.comb += self.mem.imux.bus.cyc.eq( iws == 0 )

    # Wait a cycle after 'ack' to load the appropriate CPU registers.
    with m.If( self.mem.imux.bus.ack ):
      # Increment the wait-state counter.
      # (This also lets the instruction bus' 'cyc' signal fall.)
      m.d.sync += iws.eq( 1 )
      with m.If( iws == 0 ):
        # Increment the MINSTRET counter CSR. TODO: obo
        minstret_incr( self, m )

    # Execute the current instruction, once it loads.
    with m.If( iws != 0 ):
      # Increment the PC unless otherwise specified.
      m.d.sync += self.pc.eq( self.pc + 4 )
      # Reset the wait-state counter.
      # (This also causes the I-bus 'cyc' signal to be re-asserted)
      m.d.sync += iws.eq( 0 )

      # Decoder switch case:
      with m.Switch( self.mem.imux.bus.dat_r[ 0 : 7 ] ):
        # LUI, AUIPC, R-type, and I-type instructions:
        # write to the destination register unless it's x0.
        with m.Case( '0-10-11' ):
          m.d.comb += self.rc.en.eq( self.rc.addr != 0 )

        # JAL / JALR instructions: jump to a new address and place
        # the 'return PC' in the destination register (rc).
        with m.Case( '110-111' ):
          m.d.sync += self.pc.eq(
            Mux( self.mem.imux.bus.dat_r[ 3 ],
                 self.pc + Cat(
                   Repl( 0, 1 ),
                   self.mem.imux.bus.dat_r[ 21: 31 ],
                   self.mem.imux.bus.dat_r[ 20 ],
                   self.mem.imux.bus.dat_r[ 12 : 20 ],
                   Repl( self.mem.imux.bus.dat_r[ 31 ], 12 ) ),
                 self.ra.data + Cat(
                   self.mem.imux.bus.dat_r[ 20 : 32 ],
                   Repl( self.mem.imux.bus.dat_r[ 31 ], 20 ) ) ),
          )
          m.d.comb += self.rc.en.eq( self.rc.addr != 0 )

        # Conditional branch instructions: similar to JAL / JALR,
        # but only take the branch if the condition is met.
        with m.Case( OP_BRANCH ):
          # Check the ALU result. If it is zero, then:
          # a == b for BEQ/BNE, or a >= b for BLT[U]/BGE[U].
          with m.If( ( ( self.alu.y == 0 ) ^
                         self.mem.imux.bus.dat_r[ 12 ] ) !=
                       self.mem.imux.bus.dat_r[ 14 ] ):
            # Branch only if the condition is met.
            m.d.sync += self.pc.eq( self.pc + Cat(
              Repl( 0, 1 ),
              self.mem.imux.bus.dat_r[ 8 : 12 ],
              self.mem.imux.bus.dat_r[ 25 : 31 ],
              self.mem.imux.bus.dat_r[ 7 ],
              Repl( self.mem.imux.bus.dat_r[ 31 ], 20 ) ) )

        # LB / LBU / LH / LHU / LW "load from memory" instructions:
        # load a value from memory into a register.
        with m.Case( OP_LOAD ):
          # Trigger a trap if the load address is mis-aligned.
          # * Byte accesses are never mis-aligned.
          # * Word-aligned accesses are never mis-aligned.
          # * Halfword accesses are only mis-aligned when both of
          #   the address' LSbits are 1s.
          # Since this logic only depends on 4 bits as inputs, I think
          # it should fit in one LUT4. (adr[0], adr[1], f[0], f[1])
          with m.If( ( ( self.mem.dmux.bus.adr[ :2 ] == 0 ) |
                       ( self.mem.imux.bus.dat_r[ 12 : 14 ] == 0 ) |
                       ( ~( self.mem.dmux.bus.adr[ 0 ] &
                            self.mem.dmux.bus.adr[ 1 ] &
                            self.mem.imux.bus.dat_r[ 12 ] ) ) ) == 0 ):
            trigger_trap( self, m, TRAP_LMIS )
          # Wait for the memory operation to complete.
          with m.Elif( self.mem.dmux.bus.ack == 0 ):
            m.d.comb += self.mem.dmux.bus.cyc.eq( 1 )
            m.d.sync += [
              self.pc.eq( self.pc ),
              iws.eq( 1 )
            ]
          # Put the loaded value into the destination register.
          with m.Else():
            m.d.comb += [
              self.rc.en.eq( self.rc.addr != 0 ),
              self.mem.dmux.bus.cyc.eq( 1 )
            ]
            with m.Switch( self.mem.imux.bus.dat_r[ 12 : 15 ] ):
              with m.Case( F_LW ):
                m.d.comb += self.rc.data.eq(
                  self.mem.dmux.bus.dat_r )
              with m.Case( F_LHU ):
                m.d.comb += self.rc.data.eq(
                  self.mem.dmux.bus.dat_r[ :16 ] )
              with m.Case( F_LBU ):
                m.d.comb += self.rc.data.eq(
                  self.mem.dmux.bus.dat_r[ :8 ] )
              with m.Case( F_LH ):
                m.d.comb += self.rc.data.eq( Cat(
                  self.mem.dmux.bus.dat_r[ :16 ],
                  Repl( self.mem.dmux.bus.dat_r[ 15 ], 16 ) ) )
              with m.Case( F_LB ):
                m.d.comb += self.rc.data.eq( Cat(
                  self.mem.dmux.bus.dat_r[ :8 ],
                  Repl( self.mem.dmux.bus.dat_r[ 7 ], 24 ) ) )

        # SB / SH / SW instructions: store a value from a
        # register into memory.
        with m.Case( OP_STORE ):
          # Trigger a trap if the store address is mis-aligned.
          # (Same logic as checking for mis-aligned loads.)
          with m.If( ( ( self.mem.dmux.bus.adr[ :2 ] == 0 ) |
                       ( self.mem.imux.bus.dat_r[ 12 : 14 ] == 0 ) |
                       ( ~( self.mem.dmux.bus.adr[ 0 ] &
                            self.mem.dmux.bus.adr[ 1 ] &
                            self.mem.imux.bus.dat_r[ 12 ] ) ) ) == 0 ):
            trigger_trap( self, m, TRAP_SMIS )
          # Store the requested value in memory.
          with m.Else():
            m.d.comb += [
              self.mem.dmux.bus.we.eq( 1 ),
              self.mem.dmux.bus.cyc.eq( 1 )
            ]
            # Don't proceed until the operation completes.
            with m.If( self.mem.dmux.bus.ack == 0 ):
              m.d.sync += [
                self.pc.eq( self.pc ),
                iws.eq( 1 )
              ]

        # System call instruction: ECALL, EBREAK, MRET,
        # and atomic CSR operations.
        with m.Case( OP_SYSTEM ):
          with m.If( self.mem.imux.bus.dat_r[ 12 : 15 ] == 0 ):
            with m.Switch( self.mem.imux.bus.dat_r[ 20 : 22 ] ):
              # An 'empty' ECALL instruction should raise an
              # 'environment-call-from-M-mode" exception.
              with m.Case( 0 ):
                trigger_trap( self, m, TRAP_ECALL )
              # "EBREAK" instruction: enter the interrupt context
              # with 'breakpoint' as the cause of the exception.
              with m.Case( 1 ):
                trigger_trap( self, m, TRAP_BREAK )
              # 'MRET' jumps to the stored 'pre-trap' PC in the
              # 30 MSbits of the MEPC CSR.
              with m.Case( 2 ):
                m.d.sync += self.pc.eq( Cat( Repl( 0, 2 ),
                                             self.csr.mepc_mepc ) )
          # Defer to the CSR module for atomic CSR reads/writes.
          # 'CSRR[WSC]': Write/Set/Clear CSR value from a register.
          # 'CSRR[WSC]I': Write/Set/Clear CSR value from immediate.
          with m.Else():
            m.d.comb += [
              self.rc.data.eq( self.csr.dat_r ),
              self.rc.en.eq( self.rc.addr != 0 ),
              self.csr.we.eq( 1 )
            ]

        # FENCE instruction: clear any I-caches and ensure all
        # memory operations are applied. There is no I-cache,
        # and there is no caching of memory operations.
        # There is also no pipelining. So...this is a nop.
        with m.Case( OP_FENCE ):
          pass

    # 'Always-on' decode/execute logic:
    with m.Switch( self.mem.imux.bus.dat_r[ 0 : 7 ] ):
      # LUI / AUIPC instructions: set destination register to
      # 20 upper bits, +pc for AUIPC.
      with m.Case( '0-10111' ):
        m.d.comb += self.rc.data.eq(
          Mux( self.mem.imux.bus.dat_r[ 5 ], 0, self.pc ) +
          Cat( Repl( 0, 12 ),
               self.mem.imux.bus.dat_r[ 12 : 32 ] ) )

      # JAL / JALR instructions: set destination register to
      # the 'return PC' value.
      with m.Case( '110-111' ):
        m.d.comb += self.rc.data.eq( self.pc + 4 )

      # Conditional branch instructions:
      # set us up the ALU for the condition check.
      with m.Case( OP_BRANCH ):
        # BEQ / BNE: use SUB ALU operation to check equality.
        # BLT / BGE / BLTU / BGEU: use SLT or SLTU ALU operation.
        m.d.comb += [
          self.alu.b.eq( self.rb.data ),
          self.alu.f.eq( Mux(
            self.mem.imux.bus.dat_r[ 14 ],
            Cat( self.mem.imux.bus.dat_r[ 13 ], 0b001 ),
            0b1000 ) )
        ]

      # Load / Store instructions: Set the memory address.
      with m.Case( '0-00011' ):
        m.d.comb += self.mem.dmux.bus.adr.eq( self.ra.data + Cat(
          Mux( self.mem.imux.bus.dat_r[ 5 ],
               Cat( self.mem.imux.bus.dat_r[ 7 : 12 ],
                    self.mem.imux.bus.dat_r[ 25 : 32 ] ),
               self.mem.imux.bus.dat_r[ 20 : 32 ] ),
          Repl( self.mem.imux.bus.dat_r[ 31 ], 20 ) ) )

      # R-type ALU operation: set inputs for rc = ra ? rb
      with m.Case( OP_REG ):
        m.d.comb += [
          self.alu.b.eq( self.rb.data ),
          self.alu.f.eq( Cat(
            self.mem.imux.bus.dat_r[ 12 : 15 ],
            self.mem.imux.bus.dat_r[ 30 ] ) ),
          self.rc.data.eq( self.alu.y )
        ]

      # I-type ALU operation: set inputs for rc = ra ? immediate
      with m.Case( OP_IMM ):
        m.d.comb += [
          self.alu.b.eq( Cat( self.mem.imux.bus.dat_r[ 20 : 32 ],
            Repl( self.mem.imux.bus.dat_r[ 31 ], 20 ) ) ),
          self.alu.f.eq( Cat(
            self.mem.imux.bus.dat_r[ 12 : 15 ],
            Mux( self.mem.imux.bus.dat_r[ 12 : 14 ] == 0b00,
                 0,
                 self.mem.imux.bus.dat_r[ 30 ] ) ) ),
          self.rc.data.eq( self.alu.y )
        ]

    # End of CPU module definition.
    return m

##################
# CPU testbench: #
##################
# Keep track of test pass / fail rates.
p = 0
f = 0

# Import test programs and expected runtime register values.
from programs import *

# Helper method to check expected CPU register / memory values
# at a specific point during a test program.
def check_vals( expected, ni, cpu ):
  global p, f
  if ni in expected:
    for j in range( len( expected[ ni ] ) ):
      ex = expected[ ni ][ j ]
      # Special case: program counter.
      if ex[ 'r' ] == 'pc':
        cpc = yield cpu.pc
        if hexs( cpc ) == hexs( ex[ 'e' ] ):
          p += 1
          print( "  \033[32mPASS:\033[0m pc  == %s"
                 " after %d operations"
                 %( hexs( ex[ 'e' ] ), ni ) )
        else:
          f += 1
          print( "  \033[31mFAIL:\033[0m pc  == %s"
                 " after %d operations (got: %s)"
                 %( hexs( ex[ 'e' ] ), ni, hexs( cpc ) ) )
      # Special case: RAM data (must be word-aligned).
      elif type( ex[ 'r' ] ) == str and ex[ 'r' ][ 0:3 ] == "RAM":
        rama = int( ex[ 'r' ][ 3: ] )
        if ( rama % 4 ) != 0:
          f += 1
          print( "  \033[31mFAIL:\033[0m RAM == %s @ 0x%08X"
                 " after %d operations (mis-aligned address)"
                 %( hexs( ex[ 'e' ] ), rama, ni ) )
        else:
          cpd = yield cpu.mem.ram.data[ rama // 4 ]
          if hexs( cpd ) == hexs( ex[ 'e' ] ):
            p += 1
            print( "  \033[32mPASS:\033[0m RAM == %s @ 0x%08X"
                   " after %d operations"
                   %( hexs( ex[ 'e' ] ), rama, ni ) )
          else:
            f += 1
            print( "  \033[31mFAIL:\033[0m RAM == %s @ 0x%08X"
                   " after %d operations (got: %s)"
                   %( hexs( ex[ 'e' ] ), rama, ni, hexs( cpd ) ) )
      # Numbered general-purpose registers.
      elif ex[ 'r' ] >= 0 and ex[ 'r' ] < 64:
        cr = yield cpu.r[ ex[ 'r' ] ]
        rn = ex[ 'r' ] if ex[ 'r' ] < 32 else ( ex[ 'r' ] - 32 )
        if hexs( cr ) == hexs( ex[ 'e' ] ):
          p += 1
          print( "  \033[32mPASS:\033[0m r%02d == %s"
                 " after %d operations"
                 %( rn, hexs( ex[ 'e' ] ), ni ) )
        else:
          f += 1
          print( "  \033[31mFAIL:\033[0m r%02d == %s"
                 " after %d operations (got: %s)"
                 %( rn, hexs( ex[ 'e' ] ),
                    ni, hexs( cr ) ) )

# Helper method to run a CPU device for a given number of cycles,
# and verify its expected register values over time.
def cpu_run( cpu, expected ):
  global p, f
  # Record how many CPU instructions have executed.
  ni = -1
  # Watch for timeouts if the CPU gets into a bad state.
  timeout = 0
  instret = 0
  # Let the CPU run for N ticks.
  while ni <= expected[ 'end' ]:
    # Let combinational logic settle before checking values.
    yield Settle()
    timeout = timeout + 1
    # Only check expected values once per instruction.
    ninstret = yield cpu.csr.minstret_instrs
    if ninstret != instret:
      ni += 1
      instret = ninstret
      timeout = 0
      # Check expected values, if any.
      yield from check_vals( expected, ni, cpu )
    elif timeout > 1000:
      f += 1
      print( "\033[31mFAIL: Timeout\033[0m" )
      break
    # Step the simulation.
    yield Tick()

# Helper method to simulate running a CPU from simulated SPI
# Flash which contains a given ROM image. I hope I understood the
# W25Q datasheet well enough for this to be valid...
def cpu_spi_sim( test ):
  print( "\033[33mSTART\033[0m running '%s' program (SPI):"%test[ 0 ] )
  # Create the CPU device.
  sim_spi_off = ( 2 * 1024 * 1024 )
  dut = CPU( SPI_ROM( sim_spi_off, sim_spi_off + 1024, test[ 2 ] ) )
  cpu = ResetInserter( dut.clk_rst )( dut )

  # Run the simulation.
  sim_name = "%s_spi.vcd"%test[ 1 ]
  with Simulator( cpu, vcd_file = open( sim_name, 'w' ) ) as sim:
    def proc():
      for i in range( len( test[ 3 ] ) ):
        yield cpu.mem.ram.data[ i ].eq( test[ 3 ][ i ] )
      yield from cpu_run( cpu, test[ 4 ] )
      print( "\033[35mDONE\033[0m running %s: executed %d instructions"
             %( test[ 0 ], test[ 4 ][ 'end' ] ) )
    sim.add_clock( 1 / 6000000 )
    sim.add_sync_process( proc )
    sim.run()

# Helper method to simulate running a CPU with the given ROM image
# for the specified number of CPU cycles. The 'name' field is used
# for printing and generating the waveform filename: "cpu_[name].vcd".
# The 'expected' dictionary contains a series of expected register
# values at specific points in time, defined by elapsed instructions.
def cpu_sim( test ):
  print( "\033[33mSTART\033[0m running '%s' program:"%test[ 0 ] )
  # Create the CPU device.
  dut = CPU( ROM( test[ 2 ] ) )
  cpu = ResetInserter( dut.clk_rst )( dut )

  # Run the simulation.
  sim_name = "%s.vcd"%test[ 1 ]
  with Simulator( cpu, vcd_file = open( sim_name, 'w' ) ) as sim:
    def proc():
      # Initialize RAM values.
      for i in range( len( test[ 3 ] ) ):
        yield cpu.mem.ram.data[ i ].eq( LITTLE_END( test[ 3 ][ i ] ) )
      # Run the program and print pass/fail for individual tests.
      yield from cpu_run( cpu, test[ 4 ] )
      print( "\033[35mDONE\033[0m running %s: executed %d instructions"
             %( test[ 0 ], test[ 4 ][ 'end' ] ) )
    sim.add_clock( 1 / 6000000 )
    sim.add_sync_process( proc )
    sim.run()

# Helper method to simulate running multiple ROM modules in sequence.
def cpu_mux_sim( tests ):
  print( "\033[33mSTART\033[0m running '%s' test suite:"%tests[ 0 ] )
  # Create the CPU device.
  dut = CPU( MUXROM( Array( ROM( tests[ 2 ][ i ][ 2 ] )
             for i in range( len( tests[ 2 ] ) ) ) ) )
  cpu = ResetInserter( dut.clk_rst )( dut )
  num_i = 0
  for i in range( len( tests[ 2 ] ) ):
    num_i = num_i + tests[ 2 ][ i ][ 4 ][ 'end' ]

  # Run the simulation.
  sim_name = "%s.vcd"%tests[ 1 ]
  # (Only create vcd files if necessary; with mux ROMs, they get big)
  #with Simulator( cpu, vcd_file = open( sim_name, 'w' ) ) as sim:
  with Simulator( cpu, vcd_file = None ) as sim:
    def proc():
      # Run the programs and print pass/fail for individual tests.
      for i in range( len( tests[ 2 ] ) ):
        print( "  \033[93mSTART\033[0m running '%s' ROM image:"
               %tests[ 2 ][ i ][ 0 ] )
        yield cpu.clk_rst.eq( 1 )
        yield Tick()
        yield cpu.clk_rst.eq( 0 )
        yield Tick()
        yield cpu.mem.rom.select.eq( i )
        yield Settle()
        # Initialize RAM values.
        for j in range( len( tests[ 2 ][ i ][ 3 ] ) ):
          yield cpu.mem.ram.data[ j ].eq( LITTLE_END( tests[ 2 ][ i ][ 3 ][ j ] ) )
        yield from cpu_run( cpu, tests[ 2 ][ i ][ 4 ] )
        print( "  \033[34mDONE\033[0m running '%s' ROM image:"
               " executed %d instructions"
               %( tests[ 2 ][ i ][ 0 ], tests[ 2 ][ i ][ 4 ][ 'end' ] ) )
      print( "\033[35mDONE\033[0m running %s: executed %d instructions"
             %( tests[ 0 ], num_i ) )
    sim.add_clock( 1 / 6000000 )
    sim.add_sync_process( proc )
    sim.run()

# 'main' method to run a basic testbench.
if __name__ == "__main__":
  if ( len( sys.argv ) == 2 ) and ( sys.argv[ 1 ] == '-b' ):
    # Build the application for an iCE40UP5K FPGA.
    # Currently, this is meaningless, because it builds the CPU
    # with a hard-coded 'infinite loop' ROM. But it's a start.
    with warnings.catch_warnings():
      # (Un-comment to suppress warning messages)
      warnings.filterwarnings( "ignore", category = DriverConflict )
      warnings.filterwarnings( "ignore", category = UnusedElaboratable )
      sopts = ''
      # Optional: increases design size but provides more info.
      #sopts += '-noflatten '
      # Optional: use yosys LUT techmapping. ABC seems better tho.
      #sopts += '-noabc '
      # Optional: optimization flags seem to help a bit;
      # probably ~5% fewer gates, ~15% faster?
      #sopts += '-retime '
      #sopts += '-relut '
      #sopts += '-abc2 '
      # 'abc9' option doesn't seem to be as effective with iCE40s as
      # it is with chips that have (I think) wider LUTs, but...
      #sopts += '-abc9 '
      prog_start = ( 2 * 1024 * 1024 )
      cpu = CPU( SPI_ROM( prog_start, prog_start * 2, None ) )
      UpduinoV2Platform().build( ResetInserter( cpu.clk_rst )( cpu ),
                                 do_build = True,
                                 do_program = False,
                                 synth_opts = sopts )
  else:
    # Run testbench simulations.
    with warnings.catch_warnings():
      warnings.filterwarnings( "ignore", category = DriverConflict )

      print( '--- CPU Tests ---' )
      # Simulate the 'infinite loop' ROM to screen for syntax errors.
      cpu_sim( loop_test )
      cpu_spi_sim( loop_test )
      cpu_sim( ram_pc_test )
      cpu_spi_sim( ram_pc_test )
      cpu_sim( quick_test )
      cpu_spi_sim( quick_test )
      # Run auto-generated RV32I compliance tests with a multiplexed
      # ROM module containing a different program for each one.
      # (The CPU gets reset between each program.)
      cpu_mux_sim( rv32i_compliance )
      # Run non-standard CSR / peripheral tests individually.
      cpu_sim( minstret_test )
      cpu_sim( gpio_test )
      cpu_sim( npx_test )

      # Miscellaneous tests which are not part of the RV32I test suite.
      # Simulate the 'run from RAM' test ROM.
      cpu_sim( ram_pc_test )
      # Simulate a basic 'quick test' ROM.
      cpu_sim( quick_test )

      # Done; print results.
      print( "CPU Tests: %d Passed, %d Failed"%( p, f ) )
