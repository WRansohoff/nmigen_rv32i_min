from nmigen import *
from nmigen.back.pysim import *
from nmigen_boards.upduino_v2 import *

from alu import *
from csr import *
from isa import *
from mux_rom import *
from rom import *
from ram import *
from cpu_helpers import *

import sys
import warnings

###############
# CPU module: #
###############

# FSM state definitions. TODO: Remove after figuring out how to
# access the internal FSM from tests. Also, consolidate these steps...
CPU_RESET        = 0
CPU_PC_LOAD      = 1
CPU_PC_ROM_FETCH = 2
CPU_PC_DECODE    = 3
CPU_LDST         = 4
CPU_TRAP_ENTER   = 5
CPU_TRAP_EXIT    = 6
CPU_STATES_MAX   = 6

# CPU module.
class CPU( Elaboratable ):
  def __init__( self, rom_module ):
    # 'Reset' signal for clock domains.
    self.clk_rst = Signal( reset = 0b0, reset_less = True )
    # Program Counter register.
    self.pc = Signal( 32, reset = 0x00000000 )
    # Intermediate load/store memory pointer.
    self.mp = Signal( 32, reset = 0x00000000 )
    # The main 32 CPU registers for 'normal' and 'interrupt' contexts.
    # I don't think that the base specification includes priority
    # levels, so for now, we only need one extra set of registers
    # to handle context-switching in hardware.
    self.r  = Memory( width = 32, depth = 64,
                      init = ( 0x00000000 for i in range( 32 ) ) )
    # Read ports for rs1 (ra), rs2 (rb), and rd (rc).
    self.ra      = self.r.read_port()
    self.rb      = self.r.read_port()
    self.rc      = self.r.write_port()
    # CPU context flag; toggles 'normal' and 'interrupt' registers.
    self.irq    = Signal( 1, reset = 0b0 )
    # Intermediate instruction and PC storage.
    self.opcode = Signal( 7, reset = 0b0000000 )
    self.f      = Signal( 3, reset = 0b000 )
    self.ff     = Signal( 7, reset = 0b0000000 )
    self.imm    = Signal( shape = Shape( width = 32, signed = True ),
                          reset = 0x00000000 )
    self.ipc    = Signal( 32, reset = 0x00000000 )
    # TODO: Redesign the FSM to require fewer and less scattered wait-states.
    # Memory wait states for RAM and ROM.
    self.nvmws  = Signal( 3, reset = 0b010 )
    self.ramws  = Signal( 3, reset = 0b001 )
    # CPU register access wait states.
    self.rws    = Signal( 2, reset = 0b10 )
    # CSR access wait states.
    self.cws    = Signal( 2, reset = 0b00 )
    # The ALU submodule which performs logical operations.
    self.alu    = ALU()
    # CSR 'system registers'.
    if CSR_EN:
      self.csr    = CSR()
    # The ROM submodule (or multiplexed test ROMs) which act as
    # simulated program data storage for the CPU.
    self.rom    = rom_module
    # The RAM submodule which simulates re-writable data storage.
    if CSR_EN:
      # (1KB of RAM = 256 words)
      self.ram    = RAM( 256 )
    else:
      # (Builds are smaller and faster with less simulated RAM)
      self.ram    = RAM( 4 )

    # RGB LED signals for debugging.
    self.red_on = Signal( 1, reset = 0b0 )
    self.grn_on = Signal( 1, reset = 0b0 )
    self.blu_on = Signal( 1, reset = 0b0 )

    # Debugging signal(s):
    # Track FSM state. TODO: There must be a way to access this
    # from the Module's FSM object, but I don't know how.
    self.fsms = Signal( range( CPU_STATES_MAX ),
                        reset = CPU_PC_ROM_FETCH )

  # CPU object's 'elaborate' method to generate the hardware logic.
  def elaborate( self, platform ):
    # Core CPU module.
    m = Module()
    # Register the ALU, CSR, ROM and RAM submodules.
    m.submodules.alu = self.alu
    if CSR_EN:
      m.submodules.csr = self.csr
    m.submodules.rom = self.rom
    m.submodules.ram = self.ram
    # Register the CPU register read/write ports.
    m.submodules.ra  = self.ra
    m.submodules.rb  = self.rb
    m.submodules.rc  = self.rc

    # LED pins, for testing.
    if platform != None:
      rled = platform.request( 'led_r', 0 )
      gled = platform.request( 'led_g', 0 )
      bled = platform.request( 'led_b', 0 )
      m.d.sync += [
        rled.o.eq( self.red_on ),
        gled.o.eq( self.grn_on ),
        bled.o.eq( self.blu_on )
      ]

    # Reset countdown.
    rsc = Signal( 2, reset = 0b11 )
    # Memory wait state countdowns.
    nvmws_c = Signal( 3, reset = 0b000 )
    ramws_c = Signal( 3, reset = 0b000 )
    rws_c   = Signal( 2, reset = 0b00 )

    # Disable CPU register writes by default.
    m.d.comb += self.rc.en.eq( 0 )
    # Reset memory access wait-state counters if they are not used.
    m.d.sync += [
      nvmws_c.eq( 0 ),
      ramws_c.eq( 0 ),
      rws_c.eq( 0 )
    ]
    m.d.sync += rws_c.eq( 0 )

    # Set the program counter to the simulated memory addresses
    # by default. Load operations temporarily override this.
    m.d.comb += self.rom.addr.eq( self.pc )

    # Set the simulated RAM address to 0 by default, and set
    # the RAM's read/write enable bits to 0 by default.
    m.d.comb += [
      self.ram.addr.eq( 0 ),
      self.ram.wen.eq( 0 )
    ]

    # Set CSR values to 0 by default.
    if CSR_EN:
      m.d.comb += [
        self.csr.rin.eq( 0 ),
        self.csr.rsel.eq( 0 ),
        self.csr.f.eq( 0 )
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
          m.d.comb += self.ram.addr.eq( ( self.pc ) & 0x1FFFFFFF )
          with m.If( ramws_c < self.ramws ):
            m.d.sync += ramws_c.eq( ramws_c + 1 )
          with m.Else():
            # Increment 'instructions retired' counter.
            minstret_incr( self, m )
            # Decode the fetched instruction and move on to run it.
            rv32i_decode( self, m, self.ram.dout )
            m.next = "CPU_PC_DECODE"
        # Otherwise, read from ROM.
        with m.Else():
          with m.If( nvmws_c < self.nvmws ):
            m.d.sync += nvmws_c.eq( nvmws_c + 1 )
          with m.Else():
            # Increment 'instructions retired' counter.
            minstret_incr( self, m )
            # Decode the fetched instruction and move on to run it.
            rv32i_decode( self, m, self.rom.out )
            m.next = "CPU_PC_DECODE"
      # "Decode PC": Figure out what sort of instruction to execute,
      #              and prepare associated registers.
      with m.State( "CPU_PC_DECODE" ):
        m.d.comb += self.fsms.eq( CPU_PC_DECODE ) #TODO: Remove
        # "Load Upper Immediate" instruction:
        with m.If( self.opcode == OP_LUI ):
          with m.If( ( self.rc.addr & 0x1F ) > 0 ):
            m.d.sync += self.rc.data.eq( self.imm )
            # Assert the CPU register 'write' signal.
            with m.If( self.rc.addr[ :5 ] != 0 ):
              m.d.comb += self.rc.en.eq( 1 )
          m.next = "CPU_PC_LOAD"
        # "Add Upper Immediate to PC" instruction:
        with m.Elif( self.opcode == OP_AUIPC ):
          with m.If( ( self.rc.addr & 0x1F ) > 0 ):
            m.d.sync += self.rc.data.eq( self.imm + self.ipc )
            # Assert the CPU register 'write' signal.
            with m.If( self.rc.addr[ :5 ] != 0 ):
              m.d.comb += self.rc.en.eq( 1 )
          m.next = "CPU_PC_LOAD"
        # "Jump And Link" instruction:
        with m.Elif( self.opcode == OP_JAL ):
          jump_to( self, m, ( self.ipc + self.imm ) )
          with m.If( ( self.rc.addr & 0x1F ) > 0 ):
            m.d.sync += self.rc.data.eq( self.ipc + 4 )
            # Assert the CPU register 'write' signal on the
            # last register access wait-state.
            with m.If( rws_c >= self.rws ):
              with m.If( self.rc.addr[ :5 ] != 0 ):
                m.d.comb += self.rc.en.eq( 1 )
        # "Jump And Link from Register" instruction:
        # funct3 bits should be 0b000, but for now there's no
        # need to be a stickler about that.
        with m.Elif( self.opcode == OP_JALR ):
          jump_to( self, m, ( self.ra.data + self.imm ) )
          with m.If( ( self.rc.addr & 0x1F ) > 0 ):
            m.d.sync += self.rc.data.eq( self.ipc + 4 )
            # Assert the CPU register 'write' signal on the
            # last register access wait-state.
            with m.If( rws_c >= self.rws ):
              with m.If( self.rc.addr[ :5 ] != 0 ):
                m.d.comb += self.rc.en.eq( 1 )
        # "Conditional Branch" instructions:
        with m.Elif( self.opcode == OP_BRANCH ):
          # "Branch if EQual" operation:
          with m.If( ( self.f == F_BEQ ) &
                     ( self.ra.data == self.rb.data ) ):
              jump_to( self, m, ( self.ipc + self.imm ) )
          # "Branch if Not Equal" operation:
          with m.Elif( ( self.f == F_BNE ) &
                       ( self.ra.data != self.rb.data ) ):
              jump_to( self, m, ( self.ipc + self.imm ) )
          # "Branch if Less Than" operation:
          with m.Elif( ( self.f == F_BLT ) &
                   ( ( ( self.rb.data.bit_select( 31, 1 ) ==
                         self.ra.data.bit_select( 31, 1 ) ) &
                       ( self.ra.data < self.rb.data ) ) |
                       ( self.ra.data.bit_select( 31, 1 ) >
                         self.rb.data.bit_select( 31, 1 ) ) ) ):
              jump_to( self, m, ( self.ipc + self.imm ) )
          # "Branch if Greater or Equal" operation:
          with m.Elif( ( self.f == F_BGE ) &
                   ( ( ( self.rb.data.bit_select( 31, 1 ) ==
                         self.ra.data.bit_select( 31, 1 ) ) &
                       ( self.ra.data >= self.rb.data ) ) |
                       ( self.rb.data.bit_select( 31, 1 ) >
                         self.ra.data.bit_select( 31, 1 ) ) ) ):
              jump_to( self, m, ( self.ipc + self.imm ) )
          # "Branch if Less Than (Unsigned)" operation:
          with m.Elif( ( self.f == F_BLTU ) &
                       ( self.ra.data < self.rb.data ) ):
              jump_to( self, m, ( self.ipc + self.imm ) )
          # "Branch if Greater or Equal (Unsigned)" operation:
          with m.Elif( ( self.f == F_BGEU ) &
                       ( self.ra.data >= self.rb.data ) ):
              jump_to( self, m, ( self.ipc + self.imm ) )
          with m.Else():
            m.next = "CPU_PC_LOAD"
        # "Load from Memory" instructions:
        # Addresses in 0x2xxxxxxx memory space are treated as RAM.
        # There are no alignment requirements (yet).
        with m.Elif( self.opcode == OP_LOAD ):
          # Populate 'mp' with the memory address to load from.
          m.d.comb += self.mp.eq( self.ra.data + self.imm )
          with m.If( ( self.mp & 0xE0000000 ) == 0x20000000 ):
            m.d.comb += self.ram.addr.eq( self.mp & 0x1FFFFFFF )
          with m.Else():
            m.d.comb += self.rom.addr.eq( self.mp )
          # Memory access is not instantaneous, so the next state is
          # 'CPU_LDST' which allows time for the data to arrive.
          m.next = "CPU_LDST"
        # "Store to Memory" instructions:
        # Addresses in 0x2xxxxxxx memory space are treated as RAM.
        # Writes to other addresses are ignored because,
        # surprise surprise, ROM is read-only.
        # There are no alignment requirements (yet).
        with m.Elif( self.opcode == OP_STORE ):
          # Populate 'mp' with the memory address to load from.
          m.d.comb += self.mp.eq( self.ra.data + self.imm )
          with m.If( ( self.mp & 0xE0000000 ) == 0x20000000 ):
            m.d.comb += [
              self.ram.addr.eq( self.mp & 0x1FFFFFFF ),
              self.ram.din.eq( self.rb.data )
            ]
            # Don't enable writes until the last wait-state tick.
            with m.If( rws_c >= self.rws ):
              m.d.comb += self.ram.wen.eq( 0b1 )
            # "Store Byte" operation:
            with m.If( self.f == F_SB ):
              m.d.comb += self.ram.dw.eq( RAM_DW_8 )
            # "Store Halfword" operation:
            with m.Elif( self.f == F_SH ):
              m.d.comb += self.ram.dw.eq( RAM_DW_16 )
            # "Store Word" operation:
            with m.Elif( self.f == F_SW ):
              m.d.comb += self.ram.dw.eq( RAM_DW_32 )
          m.next = "CPU_LDST"
        # "Register-Based" instructions:
        with m.Elif( self.opcode == OP_REG ):
          alu_reg_op( self, m )
          with m.If( ( self.rc.addr & 0x1F ) > 0 ):
            m.d.sync += self.rc.data.eq( self.alu.y )
          m.next = "CPU_PC_LOAD"
        # "Immediate-Based" instructions:
        with m.Elif( self.opcode == OP_IMM ):
          alu_imm_op( self, m )
          with m.If( ( self.rc.addr & 0x1F ) > 0 ):
            m.d.sync += self.rc.data.eq( self.alu.y )
          m.next = "CPU_PC_LOAD"
        with m.Elif( self.opcode == OP_SYSTEM ):
          # "EBREAK" instruction: enter the interrupt context
          # with 'breakpoint' as the cause of the exception.
          with m.If( ( ( self.ra.addr & 0x1F )  == 0 )
                   & ( ( self.rc.addr & 0x1F ) == 0 )
                   & ( self.f   == 0 )
                   & ( self.imm == 0x001 ) ):
            trigger_trap( self, m, TRAP_BREAK )
          # "Environment Call" instructions:
          with m.Elif( self.f == F_TRAPS ):
            # An 'empty' ECALL instruction should raise an
            # 'environment-call-from-M-mode" exception.
            with m.If( ( ( self.ra.addr & 0x1F ) == 0 ) &
                       ( ( self.rc.addr & 0x1F ) == 0 ) &
                       ( self.imm == 0 ) ):
              trigger_trap( self, m, TRAP_ECALL )
            # 'MTRET' should return from an interrupt context.
            # For now, just skip to the next instruction if it
            # occurs outside of an interrupt.
            with m.Elif( self.imm == IMM_MRET ):
              with m.If( self.irq == 1 ):
                m.next = "CPU_TRAP_EXIT"
              with m.Else():
                m.next = "CPU_PC_LOAD"
            with m.Else():
              m.next = "CPU_PC_LOAD"
          if CSR_EN:
            # Defer to the CSR module for valid 'CSRRx' operations.
            # 'CSRRW': Write value from register to CSR.
            with m.Elif( self.f == F_CSRRW ):
              m.d.comb += [
                self.csr.rin.eq( self.ra.data ),
                self.csr.rsel.eq( self.imm ),
                self.csr.f.eq( F_CSRRW )
              ]
              csr_rw( self, m, rws_c )
            # 'CSRRS' set specified bits in a CSR from a register.
            with m.Elif( self.f == F_CSRRS ):
              m.d.comb += [
                self.csr.rin.eq( self.ra.data ),
                self.csr.rsel.eq( self.imm ),
                self.csr.f.eq( F_CSRRS )
              ]
              csr_rw( self, m, rws_c )
            # 'CSRRC' clear specified bits in a CSR from a register.
            with m.Elif( self.f == F_CSRRC ):
              m.d.comb += [
                self.csr.rin.eq( self.ra.data ),
                self.csr.rsel.eq( self.imm ),
                self.csr.f.eq( F_CSRRC )
              ]
              csr_rw( self, m, rws_c )
            # Note: 'CSRRxI' operations treat the 'rs1' / 'ra'
            # value as a 5-bit sign-extended immediate.
            # 'CSRRWI': Write immediate value to CSR.
            with m.Elif( self.f == F_CSRRWI ):
              m.d.comb += [
                self.csr.rsel.eq( self.imm ),
                self.csr.f.eq( F_CSRRWI )
              ]
              with m.If( self.ra.addr.bit_select( 4, 1 ) != 0 ):
                m.d.comb += self.csr.rin.eq( 0xFFFFFFE0 | ( self.ra.addr & 0x1F ) )
              with m.Else():
                m.d.comb += self.csr.rin.eq( ( self.ra.addr & 0x1F ) )
              csr_rw( self, m, rws_c )
            # 'CSRRSI' set immediate bits in a CSR.
            with m.Elif( self.f == F_CSRRSI ):
              m.d.comb += [
                self.csr.rsel.eq( self.imm ),
                self.csr.f.eq( F_CSRRSI )
              ]
              with m.If( self.ra.addr.bit_select( 4, 1 ) != 0 ):
                m.d.comb += self.csr.rin.eq( 0xFFFFFFE0 | ( self.ra.addr & 0x1F ) )
              with m.Else():
                m.d.comb += self.csr.rin.eq( ( self.ra.addr & 0x1F ) )
              csr_rw( self, m, rws_c )
            # 'CSRRCI' clear immediate bits in a CSR.
            with m.Elif( self.f == F_CSRRCI ):
              m.d.comb += [
                self.csr.rsel.eq( self.imm ),
                self.csr.f.eq( F_CSRRCI )
              ]
              with m.If( self.ra.addr.bit_select( 4, 1 ) != 0 ):
                m.d.comb += self.csr.rin.eq( 0xFFFFFFE0 | ( self.ra.addr & 0x1F ) )
              with m.Else():
                m.d.comb += self.csr.rin.eq( ( self.ra.addr & 0x1F ) )
              csr_rw( self, m, rws_c )
          # Halt execution at an unrecognized 'SYSTEM' instruction.
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
        # Non-standard LED opcode. This is for testing on an FPGA
        # before I have a working GPIO peripheral. Let's be honest,
        # colorful LEDs are more important than debugging interfaces.
        with m.Elif( self.opcode == OP_LED ):
          m.d.sync += [
            self.red_on.eq( ( self.ra.data & R_RED ) != 0 ),
            self.grn_on.eq( ( self.ra.data & R_GRN ) != 0 ),
            self.blu_on.eq( ( self.ra.data & R_BLU ) != 0 )
          ]
          m.next = "CPU_PC_LOAD"
        # Unrecognized operations skip to loading the next
        # PC value, although the RISC-V spec says that this
        # should trigger an error.
        with m.Else():
          m.next = "CPU_PC_LOAD"
        # Wait until register access wait-states elapse, except
        # for traps.
        with m.If( rws_c < self.rws ):
          m.d.sync += [
            rws_c.eq( rws_c + 1 ),
            self.pc.eq( self.ipc )
          ]
          m.next = "CPU_PC_DECODE"
      # "Load / Store operation" - wait for memory access to finish.
      with m.State( "CPU_LDST" ):
        m.d.comb += self.fsms.eq( CPU_LDST ) # TODO: Remove
        # Maintain the cominatorial logic holding the memory
        # address at the 'mp' (memory pointer) value.
        m.d.comb += self.mp.eq( self.ra.data + self.imm )
        with m.If( ( self.mp & 0xE0000000 ) == 0x20000000 ):
          m.d.comb += self.ram.addr.eq( self.mp & 0x1FFFFFFF )
          with m.If( self.opcode == OP_STORE ):
            m.d.comb += [
              self.ram.wen.eq( 1 ),
              self.ram.din.eq( self.rb.data )
            ]
            # "Store Byte" operation:
            with m.If( self.f == F_SB ):
              m.d.comb += self.ram.dw.eq( RAM_DW_8 )
            # "Store Halfword" operation:
            with m.Elif( self.f == F_SH ):
              m.d.comb += self.ram.dw.eq( RAM_DW_16 )
            # "Store Word" operation:
            with m.Elif( self.f == F_SW ):
              m.d.comb += self.ram.dw.eq( RAM_DW_32 )
        with m.Else():
          m.d.comb += self.rom.addr.eq( self.mp )
        # Memory access wait-states.
        with m.If( ( ( self.mp & 0xE0000000 ) == 0x20000000 ) & ( ramws_c < self.ramws ) ):
          m.d.sync += ramws_c.eq( ramws_c + 1 )
        with m.Elif( ( ( self.mp & 0xE0000000 ) != 0x20000000 ) & ( nvmws_c < self.nvmws ) ):
          m.d.sync += nvmws_c.eq( nvmws_c + 1 )
        with m.Elif( self.opcode == OP_LOAD ):
          # Assert the CPU register 'write' signal.
          with m.If( self.rc.addr[ :5 ] != 0 ):
            m.d.comb += self.rc.en.eq( 1 )
          # "Load Byte" operation:
          with m.If( self.f == F_LB ):
            with m.If( ( self.rc.addr & 0x1F ) > 0 ):
              with m.If( ( self.mp & 0xE0000000 ) == 0x20000000 ):
                m.d.sync += self.rc.data.eq( Cat( self.ram.dout[ :8 ], Repl( self.ram.dout[ 7 ], 24 ) ) )
              with m.Else():
                m.d.sync += self.rc.data.eq( Cat( self.rom.out[ :8 ], Repl( self.ram.dout[ 7 ], 24 ) ) )
          # "Load Halfword" operation:
          with m.Elif( self.f == F_LH ):
            with m.If( ( self.rc.addr & 0x1F ) > 0 ):
              with m.If( ( self.mp & 0xE0000000 ) == 0x20000000 ):
                m.d.sync += self.rc.data.eq( Cat( self.ram.dout[ :16 ], Repl( self.ram.dout[ 15 ], 16 ) ) )
              with m.Else():
                m.d.sync += self.rc.data.eq( Cat( self.rom.out[ :16 ], Repl( self.ram.dout[ 15 ], 16 ) ) )
          # "Load Word" operation:
          with m.Elif( self.f == F_LW ):
            with m.If( ( self.rc.addr & 0x1F ) > 0 ):
              with m.If( ( self.mp & 0xE0000000 ) == 0x20000000 ):
                m.d.sync += self.rc.data.eq( self.ram.dout )
              with m.Else():
                m.d.sync += self.rc.data.eq( self.rom.out )
          # "Load Byte" (without sign extension) operation:
          with m.Elif( self.f == F_LBU ):
            with m.If( ( self.rc.addr & 0x1F ) > 0 ):
              with m.If( ( self.mp & 0xE0000000 ) == 0x20000000 ):
                m.d.sync += self.rc.data.eq( self.ram.dout & 0xFF )
              with m.Else():
                m.d.sync += self.rc.data.eq( self.rom.out & 0xFF )
          # "Load Halfword" (without sign extension) operation:
          with m.Elif( self.f == F_LHU ):
            with m.If( ( self.rc.addr & 0x1F ) > 0 ):
              with m.If( ( self.mp & 0xE0000000 ) == 0x20000000 ):
                m.d.sync += self.rc.data.eq(
                  ( self.ram.dout & 0xFFFF ) )
              with m.Else():
                m.d.sync += self.rc.data.eq(
                  ( self.rom.out & 0xFFFF ) )
          m.next = "CPU_PC_LOAD"
        with m.Else():
          m.next = "CPU_PC_LOAD"
      # "Trap Entry" - update PC and EPC CSR, and context switch.
      with m.State( "CPU_TRAP_ENTER" ):
        m.d.comb += self.fsms.eq( CPU_TRAP_ENTER ) # TODO: Delete
        if CSR_EN:
          m.d.sync += [
            self.csr.mepc.shadow.eq( self.ipc ),
            self.irq.eq( 1 )
          ]
        m.next = "CPU_PC_ROM_FETCH"
      # "Trap Exit" - update PC and context switch.
      with m.State( "CPU_TRAP_EXIT" ):
        m.d.comb += self.fsms.eq( CPU_TRAP_EXIT ) # TODO: Delete
        if CSR_EN:
          m.d.sync += [
            self.pc.eq( self.csr.mepc.shadow ),
            self.irq.eq( 0 )
          ]
        m.next = "CPU_PC_ROM_FETCH"
      # "PC Load Letter" - increment the PC.
      with m.State( "CPU_PC_LOAD" ):
        m.d.comb += self.fsms.eq( CPU_PC_LOAD ) # TODO: Remove
        # Apply CPU register results if necessary.
        with m.If( self.opcode == OP_REG ):
          alu_reg_op( self, m )
          # Assert the CPU register 'write' signal.
          with m.If( self.rc.addr[ :5 ] != 0 ):
            m.d.comb += self.rc.en.eq( 1 )
        with m.Elif( self.opcode == OP_IMM ):
          alu_imm_op( self, m )
          # Assert the CPU register 'write' signal.
          with m.If( self.rc.addr[ :5 ] != 0 ):
            m.d.comb += self.rc.en.eq( 1 )
        with m.Elif( ( self.opcode == OP_LUI ) |
                     ( self.opcode == OP_AUIPC ) ):
          # Assert the CPU register 'write' signal.
          with m.If( self.rc.addr[ :5 ] != 0 ):
            m.d.comb += self.rc.en.eq( 1 )
        if CSR_EN:
          with m.Elif( ( self.opcode == OP_SYSTEM ) & (
                     ( self.f == F_CSRRW ) | ( self.f == F_CSRRWI ) |
                     ( self.f == F_CSRRC ) | ( self.f == F_CSRRCI ) |
                     ( self.f == F_CSRRS ) | ( self.f == F_CSRRSI ) ) ):
            # Assert the CPU register 'write' signal.
            with m.If( self.rc.addr[ :5 ] != 0 ):
              m.d.comb += self.rc.en.eq( 1 )
        with m.Elif( self.opcode == OP_LOAD ):
          # Maintain the cominatorial logic holding the memory
          # address at the 'mp' (memory pointer) value.
          m.d.comb += self.mp.eq( self.ra.data + self.imm )
          with m.If( ( self.mp & 0xE0000000 ) == 0x20000000 ):
            m.d.comb += self.ram.addr.eq( self.mp & 0x1FFFFFFF )
          with m.Else():
            m.d.comb += self.rom.addr.eq( self.mp )
          # Assert the CPU register 'write' signal.
          with m.If( self.rc.addr[ :5 ] != 0 ):
            m.d.comb += self.rc.en.eq( 1 )
        # Clear the CSR r/w signal, and increment the PC.
        if CSR_EN:
          m.d.sync += self.csr.rw.eq( 0 )
        jump_to( self, m, ( self.ipc + 4 ) )

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
          cpd = yield cpu.ram.data[ rama // 4 ]
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
      f += 1
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
  dut = CPU( test[ 2 ] )
  cpu = ResetInserter( dut.clk_rst )( dut )

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
    sim.add_clock( 1e-6 )
    sim.add_sync_process( proc )
    sim.run()

# Helper method to simulate running multiple ROM modules in sequence.
# TODO: Does not currently support initialized RAM values.
def cpu_mux_sim( tests ):
  print( "\033[33mSTART\033[0m running '%s' test suite:"%tests[ 0 ] )
  # Create the CPU device.
  dut = CPU( MUXROM( Array( tests[ 2 ][ i ][ 2 ]
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
      # Set three wait states for ROM access, to allow the ROM
      # address and data to propagate through the multiplexer.
      yield cpu.nvmws.eq( 0b011 )
      # Run the programs and print pass/fail for individual tests.
      for i in range( len( tests[ 2 ] ) ):
        print( "  \033[93mSTART\033[0m running '%s' ROM image:"
               %tests[ 2 ][ i ][ 0 ] )
        yield cpu.clk_rst.eq( 1 )
        yield Tick()
        yield cpu.clk_rst.eq( 0 )
        yield Tick()
        yield cpu.rom.select.eq( i )
        yield Settle()
        # Initialize RAM values. TODO: The application should do this,
        # but I've removed a bunch of startup code from the tests to
        # skip over CSR calls which I haven't implemented yet.
        for j in range( len( tests[ 2 ][ i ][ 3 ] ) ):
          yield cpu.ram.data[ j ].eq( tests[ 2 ][ i ][ 3 ][ j ] )
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
      # Disable CSRs so the design fits in an UP5K.
      cpu = CPU( led_rom )
      UpduinoV2Platform().build( ResetInserter( cpu.clk_rst )( cpu ),
                                 do_build = True,
                                 do_program = False )
  else:
    # Run testbench simulations.
    with warnings.catch_warnings():
      warnings.filterwarnings( "ignore", category = DriverConflict )

      print( '--- CPU Tests ---' )
      cpu_sim( led_test )
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
      # Simulate the 'infinite loop test' ROM.
      cpu_sim( loop_test )

      # Done; print results.
      print( "CPU Tests: %d Passed, %d Failed"%( p, f ) )
