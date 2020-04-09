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

import sys
import warnings

# CPU module.
class CPU( Elaboratable ):
  def __init__( self, rom_module ):
    # 'Reset' signal for clock domains.
    self.clk_rst = Signal( reset = 0b0, reset_less = True )
    # Program Counter register.
    self.pc = Signal( 32, reset = 0x00000000 )
    # Intermediary program counter storage.
    self.ipc = Signal( 32, reset = 0x00000000 )
    # The main 32 CPU registers for 'normal' and 'interrupt' contexts.
    # I don't think that the base specification includes priority
    # levels, so for now, we only need one extra set of registers
    # to handle context-switching in hardware.
    self.r      = Memory( width = 32, depth = 64,
                          init = ( 0x00000000 for i in range( 64 ) ) )
    # Read ports for rs1 (ra), rs2 (rb), and rd (rc).
    self.ra     = self.r.read_port()
    self.rb     = self.r.read_port()
    self.rc     = self.r.write_port()
    # 'Function select' and 'opcode' bits
    # (load/stores need to remember these across memory accesses)
    self.op     = Signal( 7, reset = 0b0000000 )
    self.f      = Signal( 3, reset = 0b000 )
    # CPU context flag; toggles 'normal' and 'interrupt' registers.
    self.irq    = Signal( 1, reset = 0b0 )
    # The ALU submodule which performs logical operations.
    self.alu    = ALU()
    # CSR 'system registers'.
    self.csr    = CSR()
    # Memory module to hold the ROM and RAM module(s)
    # (1KB of RAM = 256 words)
    self.mem    = RV_Memory( rom_module, 256 )
    # RGB LED signals for debugging.
    self.red_on = Signal( 1, reset = 0b0 )
    self.grn_on = Signal( 1, reset = 0b0 )
    self.blu_on = Signal( 1, reset = 0b0 )

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

    # LED pins, for testing.
    if platform != None:
      rled = platform.request( 'led_r', 0 )
      gled = platform.request( 'led_g', 0 )
      bled = platform.request( 'led_b', 0 )
      m.d.comb += [
        rled.o.eq( self.red_on ),
        gled.o.eq( self.grn_on ),
        bled.o.eq( self.blu_on )
      ]

    # Generic wait-state counter for multi-cycle instructions.
    iws = Signal( 2, reset = 0 )

    # Main CPU FSM.
    with m.FSM() as fsm:
      # "ROM Fetch": Wait for the instruction to load from ROM, and
      #              populate register fields to prepare for decoding.
      with m.State( "CPU_IFETCH" ):
        # Instruction addresses must be word-aligned.
        with m.If( self.pc[ :2 ] == 0 ):
          m.d.sync += [
            self.mem.addr.eq( self.pc ),
            self.mem.mux.bus.cyc.eq( 1 )
          ]
          # Wait for memory access.
          with m.If( ( self.mem.mux.bus.ack == 0 ) |
                     ( self.mem.mux.bus.cyc == 0 ) ):
            m.next = "CPU_IFETCH"
          with m.Else():
            # Increment 'instructions retired' counter. TODO: obo
            minstret_incr( self, m )
            # Move on to the 'decode instruction' state.
            m.d.sync += iws.eq( 0 )
            m.d.sync += self.mem.mux.bus.cyc.eq( 0 )
            m.next = "CPU_DECODE"
        # If the instruction address is misaligned, trigger a trap.
        with m.Else():
          m.d.sync += self.csr.mtval.shadow.eq( self.pc )
          trigger_trap( self, m, TRAP_IMIS )

      # "Decode instruction": Set CPU register addresses etc.
      with m.State( "CPU_DECODE" ):
        # Set CPU register access addresses.
        m.d.sync += [
          self.ra.addr.eq( Cat(
            self.mem.mux.bus.dat_r[ 15 : 20 ], self.irq ) ),
          self.rb.addr.eq( Cat(
            self.mem.mux.bus.dat_r[ 20 : 25 ], self.irq ) ),
          self.rc.addr.eq( Cat(
            self.mem.mux.bus.dat_r[ 7  : 12 ], self.irq ) ),
          self.f.eq( self.mem.mux.bus.dat_r[ 12 : 15 ] ),
          self.op.eq( self.mem.mux.bus.dat_r[ 0 : 7 ] ),
          self.ipc.eq( self.pc )
        ]
        # Wait a tick to let the register data load.
        with m.If( iws == 0 ):
          m.d.sync += iws.eq( 1 )
          m.next = "CPU_DECODE"
        with m.Else():
          m.d.sync += iws.eq( 0 )
          m.next = "CPU_EXECUTE"

      # "Execute instruction": Run the currently-loaded instruction.
      with m.State( "CPU_EXECUTE" ):
        # Unless otherwise required, increment the PC and move on.
        m.d.sync += [
          self.pc.eq( self.pc + 4 ),
          self.mem.mux.bus.cyc.eq( 0 )
        ]
        m.next = "CPU_IFETCH"

        # Switch case for opcodes.
        with m.Switch( self.op ):
          # LUI instruction: set destination register to 20 upper bits.
          with m.Case( OP_LUI ):
            m.d.comb += [
              self.rc.data.eq( self.mem.mux.bus.dat_r & 0xFFFFF000 ),
              self.rc.en.eq( self.rc.addr[ :5 ] != 0 )
            ]

          # AUIPC instruction: set destination register to 20
          # upper bits plus the current PC.
          with m.Case( OP_AUIPC ):
            m.d.comb += [
              self.rc.data.eq( self.ipc +
                ( self.mem.mux.bus.dat_r & 0xFFFFF000 ) ),
              self.rc.en.eq( self.rc.addr[ :5 ] != 0 )
            ]

          # JAL instruction: jump to an offset address (or trap if
          # the address is invalid), and put the next PC in rc.
          with m.Case( OP_JAL ):
            m.d.sync += self.pc.eq( self.ipc + Cat(
              Repl( 0, 1 ),
              self.mem.mux.bus.dat_r[ 21: 31 ],
              self.mem.mux.bus.dat_r[ 20 ],
              self.mem.mux.bus.dat_r[ 12 : 20 ],
              Repl( self.mem.mux.bus.dat_r[ 31 ], 12 ) ) ),
            m.d.comb += [
              self.rc.data.eq( self.ipc + 4 ),
              self.rc.en.eq( self.rc.addr[ :5 ] != 0 )
            ]

          # JALR instruction: jump to a new address from a register
          # (or trap if the address is invalid), and put the
          # next PC in the destination register.
          with m.Case( OP_JALR ):
            m.d.sync += self.pc.eq( self.ra.data + Cat(
              self.mem.mux.bus.dat_r[ 20 : 32 ],
              Repl( self.mem.mux.bus.dat_r[ 31 ], 20 ) ) ),
            m.d.comb += [
              self.rc.data.eq( self.ipc + 4 ),
              self.rc.en.eq( self.rc.addr[ :5 ] != 0 )
            ]

          # BEQ / BNE / BLT / BGE / BLTU / BGEU instructions:
          # same as JAL, but only if conditions are met.
          with m.Case( OP_BRANCH ):
            # BEQ / BNE.
            with m.If( self.f[ 2 ] == 0 ):
              with m.If( ( self.ra.data != self.rb.data ) == self.f[ 0 ] ):
                m.d.sync += self.pc.eq( self.ipc + Cat(
                  Repl( 0, 1 ),
                  self.mem.mux.bus.dat_r[ 8 : 12 ],
                  self.mem.mux.bus.dat_r[ 25 : 31 ],
                  self.mem.mux.bus.dat_r[ 7 ],
                  Repl( self.mem.mux.bus.dat_r[ 31 ], 20 ) ) )
            # BLT / BGE / BLTU / BGEU. (Use SLT/SLTU ALU ops)
            with m.Else():
              m.d.comb += [
                self.alu.a.eq( self.ra.data ),
                self.alu.b.eq( self.rb.data ),
                self.alu.f.eq( self.f[ 1: ] )
              ]
              with m.If( self.alu.y != self.f[ 0 ] ):
                m.d.sync += self.pc.eq( self.ipc + Cat(
                  Repl( 0, 1 ),
                  self.mem.mux.bus.dat_r[ 8 : 12 ],
                  self.mem.mux.bus.dat_r[ 25 : 31 ],
                  self.mem.mux.bus.dat_r[ 7 ],
                  Repl( self.mem.mux.bus.dat_r[ 31 ], 20 ) ) )

          # LB / LBU / LH / LHU / LW instructions: load a value
          # from memory into a register.
          with m.Case( OP_LOAD ):
            # Set the memory address to load from.
            with m.If( self.mem.mux.bus.cyc == 0 ):
              m.d.sync += self.mem.addr.eq( self.ra.data + Cat(
                self.mem.mux.bus.dat_r[ 20 : 32 ],
                Repl( self.mem.mux.bus.dat_r[ 31 ], 20 ) ) )
            # Trigger a trap if the load address is mis-aligned.
            with m.If( ( self.mem.addr <<
                       ( 2 - self.f[ :2 ] ) )[ :2 ] != 0 ):
              trigger_trap( self, m, TRAP_LMIS )
            # Wait for the memory operation to complete.
            with m.Elif( ( self.mem.mux.bus.ack == 0 ) |
                         ( self.mem.mux.bus.cyc == 0 ) ):
              m.d.sync += [
                self.pc.eq( self.pc ),
                self.mem.mux.bus.cyc.eq( 1 )
              ]
              m.next = "CPU_EXECUTE"
            # Then store the value in the destination register.
            with m.Else():
              m.d.comb += self.rc.en.eq( self.rc.addr[ :5 ] != 0 )
              with m.Switch( self.f ):
                with m.Case( F_LW ):
                  m.d.comb += self.rc.data.eq(
                    self.mem.mux.bus.dat_r )
                with m.Case( F_LHU ):
                  m.d.comb += self.rc.data.eq(
                    self.mem.mux.bus.dat_r[ :16 ] )
                with m.Case( F_LBU ):
                  m.d.comb += self.rc.data.eq(
                    self.mem.mux.bus.dat_r[ :8 ] )
                with m.Case( F_LH ):
                  m.d.comb += self.rc.data.eq( Cat(
                    self.mem.mux.bus.dat_r[ :16 ],
                    Repl( self.mem.mux.bus.dat_r[ 15 ], 16 ) ) )
                with m.Case( F_LB ):
                  m.d.comb += self.rc.data.eq( Cat(
                    self.mem.mux.bus.dat_r[ :8 ],
                    Repl( self.mem.mux.bus.dat_r[ 7 ], 24 ) ) )

          # SB / SH / SW instructions: store a value from a
          # register into memory.
          with m.Case( OP_STORE ):
            # Wait for memory R/W to finish before moving on.
            with m.If( ( self.mem.mux.bus.ack == 0 ) |
                       ( self.mem.mux.bus.we  == 0 ) |
                       ( self.mem.mux.bus.cyc == 0 ) ):
              m.d.sync += [
                self.pc.eq( self.pc ),
                self.mem.mux.bus.cyc.eq( 1 )
              ]
              m.next = "CPU_EXECUTE"
            # Set the memory address to store to.
            # (Writes to read-only memory are silently ignored)
            with m.If( self.mem.mux.bus.cyc == 0 ):
              m.d.sync += self.mem.addr.eq( self.ra.data + Cat(
                self.mem.mux.bus.dat_r[ 7 : 12 ],
                self.mem.mux.bus.dat_r[ 25 : 32 ],
                Repl( self.mem.mux.bus.dat_r[ 31 ], 20 ) ) )
            with m.Else():
              # Trigger a trap if the store address is mis-aligned.
              with m.If( ( self.mem.addr <<
                         ( 2 - self.f[ :2 ] ) )[ :2 ] != 0 ):
                trigger_trap( self, m, TRAP_SMIS )
              with m.Else():
                m.d.comb += [
                  self.mem.mux.bus.dat_w.eq( self.rb.data ),
                  self.mem.mux.bus.we.eq( self.mem.mux.bus.ack )
                ]
                with m.Switch( self.f ):
                  with m.Case( F_SB ):
                    m.d.comb += self.mem.ram.dw.eq( RAM_DW_8 )
                  with m.Case( F_SH ):
                    m.d.comb += self.mem.ram.dw.eq( RAM_DW_16 )
                  with m.Case( F_SW ):
                    m.d.comb += self.mem.ram.dw.eq( RAM_DW_32 )

          # R-type ALU operation: rc = ra ? rb
          with m.Case( OP_REG ):
            m.d.comb += [
              self.alu.a.eq( self.ra.data ),
              self.alu.b.eq( self.rb.data ),
              self.alu.f.eq( Cat(
                self.mem.mux.bus.dat_r[ 12 : 15 ],
                self.mem.mux.bus.dat_r[ 30 ] ) ),
              self.rc.data.eq( self.alu.y ),
              self.rc.en.eq( self.rc.addr[ :5 ] != 0 )
            ]

          # I-type ALU operation: rc = ra ? immediate
          # (Immediate is truncated for SLLI, SRLI, SRAI)
          with m.Case( OP_IMM ):
            m.d.comb += [
              self.alu.a.eq( self.ra.data ),
              self.alu.b.eq(
                Mux( self.mem.mux.bus.dat_r[ 12 : 14 ] == 0b01,
                     self.mem.mux.bus.dat_r[ 20 : 25 ],
                     Cat( self.mem.mux.bus.dat_r[ 20 : 32 ],
                       Repl( self.mem.mux.bus.dat_r[ 31 ], 20 ) ) ) ),
              self.alu.f.eq( Cat(
                self.mem.mux.bus.dat_r[ 12 : 15 ],
                Mux( self.mem.mux.bus.dat_r[ 12 : 14 ] == 0b01,
                     self.mem.mux.bus.dat_r[ 30 ],
                     0 ) ) ),
              self.rc.data.eq( self.alu.y ),
              self.rc.en.eq( self.rc.addr[ :5 ] != 0 )
            ]

          # System call instruction: ECALL, EBREAK, MRET, WFI,
          # and atomic CSR operations.
          with m.Case( OP_SYSTEM ):
            # "EBREAK" instruction: enter the interrupt context
            # with 'breakpoint' as the cause of the exception.
            with m.If( ( self.ra.addr[ :5 ] == 0 )
                     & ( self.rc.addr[ :5 ] == 0 )
                     & ( self.f   == 0 )
                     & ( self.mem.mux.bus.dat_r[ 20 : 32 ] == 1 ) ):
              trigger_trap( self, m, TRAP_BREAK )
            # Other trap-related system call instructions:
            with m.Elif( self.f == F_TRAPS ):
              # An 'empty' ECALL instruction should raise an
              # 'environment-call-from-M-mode" exception.
              with m.If( ( self.ra.addr[ :5 ] == 0 ) &
                         ( self.rc.addr[ :5 ] == 0 ) &
                         ( self.mem.mux.bus.dat_r[ 20 : 32 ] == 0 ) ):
                trigger_trap( self, m, TRAP_ECALL )
              # 'MTRET' should return from an interrupt context.
              # This is a nop if it occurs outside of an interrupt.
              with m.Elif( self.mem.mux.bus.dat_r[ 20 : 32 ] == IMM_MRET ):
                with m.If( self.irq == 1 ):
                  m.d.sync += [
                    self.pc.eq( self.csr.mepc.shadow ),
                    self.irq.eq( 0 )
                  ]
            # Defer to the CSR module for atomic CSR reads/writes.
            # 'CSRR[WSC]': Write/Set/Clear CSR value from a register.
            # 'CSRR[WSC]I': Write/Set/Clear CSR value from immediate.
            with m.Else():
              m.d.comb += [
                self.csr.rin.eq(
                  Mux( self.f[ 2 ] == 0,
                       self.ra.data,
                       Cat( self.ra.addr[ :5 ],
                            Repl( self.ra.addr[ 4 ], 27 ) ) ) ),
                self.csr.rsel.eq( self.mem.mux.bus.dat_r[ 20 : 32 ] ),
                self.csr.f.eq( self.f )
              ]
              # Wait a cycle to let CSR values propagate.
              with m.If( iws == 0 ):
                m.d.sync += self.csr.rw.eq( 1 )
                m.d.sync += [
                  iws.eq( 1 ),
                  self.pc.eq( self.pc )
                ]
                m.next = "CPU_EXECUTE"
              with m.Else():
                m.d.sync += self.csr.rw.eq( 0 )
                m.d.comb += [
                  self.rc.data.eq( self.csr.csrs.bus.r_data ),
                  self.rc.en.eq( self.rc.addr[ :5 ] != 0 )
                ]

          # FENCE instruction: clear any I-caches and ensure all
          # memory operations are applied. There is no I-cache,
          # and there is no caching of memory operations. So...nop.
          with m.Case( OP_FENCE ):
            m.next = "CPU_IFETCH"

          # LED instruction: Non-standard, but good for testing.
          with m.Case( OP_LED ):
            m.d.sync += [
              self.red_on.eq( ( self.ra.data & R_RED ) != 0 ),
              self.grn_on.eq( ( self.ra.data & R_GRN ) != 0 ),
              self.blu_on.eq( ( self.ra.data & R_BLU ) != 0 ),
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
          if hexs( LITTLE_END( cpd ) ) == hexs( ex[ 'e' ] ):
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
    ninstret = yield cpu.csr.minstret.shadow
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
    sim.add_clock( 1e-6 )
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
        yield cpu.mem.ram.data[ i ].eq( test[ 3 ][ i ] )
      # Run the program and print pass/fail for individual tests.
      yield from cpu_run( cpu, test[ 4 ] )
      print( "\033[35mDONE\033[0m running %s: executed %d instructions"
             %( test[ 0 ], test[ 4 ][ 'end' ] ) )
    sim.add_clock( 1e-6 )
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
          yield cpu.mem.ram.data[ j ].eq( tests[ 2 ][ i ][ 3 ][ j ] )
        yield from cpu_run( cpu, tests[ 2 ][ i ][ 4 ] )
        print( "  \033[34mDONE\033[0m running '%s' ROM image:"
               " executed %d instructions"
               %( tests[ 2 ][ i ][ 0 ], tests[ 2 ][ i ][ 4 ][ 'end' ] ) )
      print( "\033[35mDONE\033[0m running %s: executed %d instructions"
             %( tests[ 0 ], num_i ) )
    sim.add_clock( 1e-6 )
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
      #sopts += '-noflatten'
      #cpu = CPU( ROM( led_rom ) )
      prog_start = ( 2 * 1024 * 1024 )
      cpu = CPU( SPI_ROM( prog_start, prog_start + 1024, None ) )
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
      cpu_sim( misalign_ldst_test )
      cpu_sim( sw_test )
      cpu_sim( lb_test )
      cpu_sim( lbu_test )
      cpu_sim( lh_test )
      cpu_sim( sh_test )
      cpu_sim( lhu_test )
      cpu_sim( lw_test )
      cpu_sim( sb_test )
      cpu_sim( mcycle_test )
      cpu_sim( minstret_test )
      cpu_spi_sim( ram_pc_test )
      cpu_sim( quick_test )
      cpu_spi_sim( quick_test )
      # Run auto-generated RV32I compliance tests with a multiplexed
      # ROM module containing a different program for each one.
      # (The CPU gets reset between each program.)
      cpu_mux_sim( rv32i_compliance )
      # Run non-standard CSR tests individually.
      cpu_sim( mcycle_test )
      cpu_sim( minstret_test )

      # Miscellaneous tests which are not part of the RV32I test suite.
      # Simulate the 'run from RAM' test ROM.
      cpu_sim( ram_pc_test )
      # Simulate a basic 'quick test' ROM.
      cpu_sim( quick_test )
      # Simulate the LED test ROM.
      cpu_sim( led_test )

      # Done; print results.
      print( "CPU Tests: %d Passed, %d Failed"%( p, f ) )
