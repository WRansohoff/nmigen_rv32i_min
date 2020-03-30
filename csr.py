from nmigen_soc.csr import *
from nmigen_soc.csr.bus import *
from nmigen_soc.csr.wishbone import *
from nmigen_soc.wishbone import *
from nmigen_soc.memory import *
from nmigen_boards.upduino_v2 import *

from isa import *

import sys
import warnings

#############################################
# 'Control and Status Registers' file.      #
# This contains logic for handling the      #
# 'ECALL' instruction, which is used to     #
# read/write CSRs in the base ISA.          #
# CSR named constants are in `isa.py`.      #
# 'WARL' = Write Anything, Read Legal.      #
# 'WLRL' = Write Legal, Read Legal.         #
# 'WPRI' = Writes Preserved, Reads Ignored. #
#############################################

# Helper method to generate CSR memory map.
def gen_csrs( self ):
  # Even though it's a 32-bit CPU, the CSR bus is 64 bits wide
  # to allow for the spec's performance counter registers, which
  # are 64 bits in every implementation.
  self.csrs = Multiplexer( addr_width = 12,
                           data_width = 32,
                           alignment  = 0 )
  for csr_name, reg in CSRS.items():
    creg = CSReg( reg )
    self.csrs.add( creg, addr = reg[ 'c_addr' ] )
    setattr( self, csr_name, creg )

# CSR register for use in the multiplexer.
class CSReg( Element, Elaboratable ):
  def __init__( self, reg ):
    csr_r, csr_w = False, False
    self.mask_r, self.mask_ro = reg[ 'mask_r' ], reg[ 'mask_ro' ]
    self.mask_s, self.mask_c = reg[ 'mask_s' ], reg[ 'mask_c' ]
    self.rst = reg[ 'rst' ]
    for name, field in reg[ 'bits' ].items():
      if 'r' in field[ 2 ]:
        csr_r = True
      if ( 'w' in field[ 2 ] ) | \
         ( 's' in field[ 2 ] ) | \
         ( 'c' in field[ 2 ] ):
        csr_w = True
    self.shadow = Signal( 32, reset = self.rst )
    self.access = "%s%s"%( ( 'r' if csr_r else '' ),
                           ( 'w' if csr_w else '' ) )
    Element.__init__( self, 32, self.access )
  def elaborate( self, platform ):
    m = Module()
    if self.access.readable():
      m.d.comb += self.r_data.eq( self.shadow & self.mask_r )
    if self.access.writable():
      with m.If( self.w_stb ):
        # New register value = (ones) & ~(zeros).
        # ones  = (old_val & read_only) | (input & set_mask)
        # zeros = ~(input) & clear_mask
        m.d.sync += self.shadow.eq( ( ( self.shadow & self.mask_ro ) |
                                    ( self.w_data & self.mask_s ) ) &
                                    ~( ~( self.w_data ) & self.mask_c ) )
    return m

# Core "CSR" class, which contains an instance of each
# supported CSR class. the 'ECALL' helper methods access it.
class CSR( Elaboratable ):
  def __init__( self ):
    # CSR input/output registers.
    # TODO: Use fewer bits to encode the supported CSRs.
    # It shouldn't be complicated to do with a dictionary,
    # but it looks like the 'nmigen-soc' library includes a CSR
    # wishbone interface; maybe I can use that instead?
    self.rsel = Signal( 12, reset = 0x000 )
    self.rin  = Signal( 32, reset = 0x00000000 )
    self.rout = Signal( 32, reset = 0x00000000 )
    self.rw   = Signal( 1,  reset = 0b0 )
    self.f    = Signal( 3,  reset = 0b000 )
    gen_csrs( self )

  def elaborate( self, platform ):
    m = Module()
    # Register CSR submodules.
    m.submodules.csrs          = self.csrs
    for name, reg in CSRS.items():
      setattr( m.submodules, name, getattr( self, name ) )

    # Set read strobe and address to 0 by default.
    m.d.comb += [
      self.csrs.bus.addr.eq( 0 ),
      self.csrs.bus.r_stb.eq( 0 ),
      self.csrs.bus.w_stb.eq( 0 ),
    ]

    # The 'MCYCLE' CSR increments every clock tick unless inhibited.
    with m.If( self.mcountinhibit.shadow[ 0 ] == 0 ):
      m.d.sync += self.mcycle.shadow.eq( self.mcycle.shadow + 1 )
      with m.If( self.mcycle.shadow == 0xFFFFFFFF ):
        m.d.sync += self.mcycleh.shadow.eq( self.mcycleh.shadow + 1 )

    # Handle CSR read / write logic.
    with m.If( self.f == 0b000 ):
      m.d.sync += self.rout.eq( 0x00000000 )
    with m.Else():
      # 32-bit CSR.
      m.d.comb += [
        self.csrs.bus.addr.eq( self.rsel ),
        self.csrs.bus.r_stb.eq( 1 )
      ]
      m.d.sync += self.rout.eq( self.csrs.bus.r_data )
      with m.If( self.rw != 0 ):
        m.d.comb += self.csrs.bus.r_stb.eq( 1 )
        with m.If( ( self.f & 0b11 ) == 0b01 ):
          # 'Write' - set the register to the input value.
          m.d.comb += [
            self.csrs.bus.w_stb.eq( 1 ),
            self.csrs.bus.w_data.eq( self.rin )
          ]
        with m.Elif( ( ( self.f & 0b11 ) == 0b10 ) & ( self.rin != 0 ) ):
          # 'Set' - set bits which are set in the input value.
          m.d.comb += [
            self.csrs.bus.w_stb.eq( 1 ),
            self.csrs.bus.w_data.eq( self.rin | self.csrs.bus.r_data )
          ]
        with m.Elif( ( ( self.f & 0b11 ) == 0b11 ) & ( self.rin != 0 ) ):
          # 'Clear' - reset bits which are set in the input value.
          m.d.comb += [
            self.csrs.bus.w_stb.eq( 1 ),
            self.csrs.bus.w_data.eq( ~( self.rin ) & self.csrs.bus.r_data )
          ]

    return m

##################
# CSR testbench: #
##################
# Keep track of test pass / fail rates.
p = 0
f = 0

# Perform an individual CSR unit test.
def csr_ut( csr, reg, rin, cf, expected ):
  global p, f
  # Set rsel, rin, f.
  yield csr.rsel.eq( reg )
  yield csr.rin.eq( rin )
  yield csr.f.eq( cf )
  yield csr.rw.eq( 0 )
  # Wait two ticks.
  yield Tick()
  yield Tick()
  # Check the result after combinatorial logic.
  yield Settle()
  actual = yield csr.rout
  if hexs( expected ) != hexs( actual ):
    f += 1
    print( "\033[31mFAIL:\033[0m CSR 0x%03X = %s (got: %s)"
           %( reg, hexs( expected ), hexs( actual ) ) )
  else:
    p += 1
    print( "\033[32mPASS:\033[0m CSR 0x%03X = %s"
           %( reg, hexs( expected ) ) )
  # Set 'rw' and wait another two ticks.
  yield csr.rw.eq( 1 )
  yield Tick()
  yield Tick()
  yield Settle()
  # Done. Reset rsel, rin, f, rw.
  yield csr.rsel.eq( 0 )
  yield csr.rin.eq( 0 )
  yield csr.f.eq( 0 )

# Perform some basic CSR operation tests on a fully re-writable CSR.
def csr_rw_ut( csr, reg ):
  # 'Set' with rin == 0 reads the value without writing.
  yield from csr_ut( csr, reg, 0x00000000, F_CSRRS,  0x00000000 )
  # 'Set Immediate' to set all bits.
  yield from csr_ut( csr, reg, 0xFFFFFFFF, F_CSRRSI, 0x00000000 )
  # 'Clear' to reset some bits.
  yield from csr_ut( csr, reg, 0x01234567, F_CSRRC,  0xFFFFFFFF )
  # 'Write' to set some bits and reset others.
  yield from csr_ut( csr, reg, 0x0C0FFEE0, F_CSRRW,  0xFEDCBA98 )
  # 'Write Immediate' to do the same thing.
  yield from csr_ut( csr, reg, 0xFFFFFCBA, F_CSRRWI, 0x0C0FFEE0 )
  # 'Clear Immediate' to clear all bits.
  yield from csr_ut( csr, reg, 0xFFFFFFFF, F_CSRRCI, 0xFFFFFCBA )
  # 'Clear' with rin == 0 reads the value without writing.
  yield from csr_ut( csr, reg, 0x00000000, F_CSRRC,  0x00000000 )

# Top-level CSR test method.
def csr_test( csr ):
  # Wait a tick and let signals settle after reset.
  yield Settle()

  # Print a test header.
  print( "--- CSR Tests ---" )

  # Test reading the 'MISA' CSR. XLEN = 32, RV32I = 1, others = 0.
  yield from csr_ut( csr, CSRA_MISA, 0x00000000, F_CSRRSI, 0x40000100 )
  # Test writing the 'MISA' CSR. No bits should change, since
  # only one ISA configuration is supported.
  yield from csr_ut( csr, CSRA_MISA, 0xC3FFFFFF, F_CSRRW,  0x40000100 )
  yield from csr_ut( csr, CSRA_MISA, 0x00001234, F_CSRRWI, 0x40000100 )

  # Test reading / writing the 'MVENDORID' CSR. (Should be read-only)
  yield from csr_ut( csr, CSRA_MVENDORID, 0x00000000, F_CSRRW, VENDOR_ID )
  yield from csr_ut( csr, CSRA_MVENDORID, 0xFFFFFFFF, F_CSRRS, VENDOR_ID )
  yield from csr_ut( csr, CSRA_MVENDORID, 0xFFFFFFFF, F_CSRRC, VENDOR_ID )
  # Test reading / writing the 'MARCHID' CSR. (Should be read-only)
  yield from csr_ut( csr, CSRA_MARCHID, 0x00000000, F_CSRRW, ARCH_ID )
  yield from csr_ut( csr, CSRA_MARCHID, 0xFFFFFFFF, F_CSRRS, ARCH_ID )
  yield from csr_ut( csr, CSRA_MARCHID, 0xFFFFFFFF, F_CSRRC, ARCH_ID )
  yield from csr_ut( csr, CSRA_MARCHID, 0x00000000, F_CSRRW, ARCH_ID )
  # Test reading / writing the 'MIMPID' CSR. (Should be read-only)
  yield from csr_ut( csr, CSRA_MIMPID, 0x00000000, F_CSRRW, MIMP_ID )
  yield from csr_ut( csr, CSRA_MIMPID, 0xFFFFFFFF, F_CSRRS, MIMP_ID )
  yield from csr_ut( csr, CSRA_MIMPID, 0xFFFFFFFF, F_CSRRC, MIMP_ID )
  # Test reading / writing the 'MHARTID' CSR. (Should be read-only)
  yield from csr_ut( csr, CSRA_MHARTID, 0x00000000, F_CSRRW, 0 )
  yield from csr_ut( csr, CSRA_MHARTID, 0xFFFFFFFF, F_CSRRS, 0 )
  yield from csr_ut( csr, CSRA_MHARTID, 0xFFFFFFFF, F_CSRRC, 0 )

  # Test reading / writing 'MSTATUS' CSR. (Only 'MIE' can be written)
  yield from csr_ut( csr, CSRA_MSTATUS, 0xFFFFFFFF, F_CSRRWI, 0x00001800 )
  yield from csr_ut( csr, CSRA_MSTATUS, 0xFFFFFFFF, F_CSRRCI, 0x00001808 )
  yield from csr_ut( csr, CSRA_MSTATUS, 0xFFFFFFFF, F_CSRRSI, 0x00001800 )
  yield from csr_ut( csr, CSRA_MSTATUS, 0x00000000, F_CSRRW,  0x00001808 )
  yield from csr_ut( csr, CSRA_MSTATUS, 0x00000000, F_CSRRS,  0x00001800 )
  # Test reading / writing 'MSTATUSH' CSR.
  yield from csr_ut( csr, CSRA_MSTATUSH, 0x00000000,
                     F_CSRRWI, ( MSTATUS_MBE_LIT << 5 ) )
  yield from csr_ut( csr, CSRA_MSTATUSH, 0xFFFFFFFF,
                     F_CSRRSI, ( MSTATUS_MBE_LIT << 5 ) )
  yield from csr_ut( csr, CSRA_MSTATUSH, 0xFFFFFFFF,
                     F_CSRRCI, ( MSTATUS_MBE_LIT << 5 ) )

  # Test reading / writing 'MTVEC' CSR. (R/W except 'MODE' >= 2)
  yield from csr_ut( csr, CSRA_MTVEC, 0xFFFFFFFF, F_CSRRWI, 0x00000000 )
  yield from csr_ut( csr, CSRA_MTVEC, 0xFFFFFFFF, F_CSRRCI, 0xFFFFFFFD )
  yield from csr_ut( csr, CSRA_MTVEC, 0xFFFFFFFE, F_CSRRSI, 0x00000000 )
  yield from csr_ut( csr, CSRA_MTVEC, 0x00000003, F_CSRRW,  0xFFFFFFFC )
  yield from csr_ut( csr, CSRA_MTVEC, 0x00000000, F_CSRRS,  0x00000001 )

  # Test reading / writing the 'MHARTID' CSR. (Should be read-only)
  yield from csr_ut( csr, CSRA_MHARTID, 0x00000000, F_CSRRW, 0 )
  yield from csr_ut( csr, CSRA_MHARTID, 0xFFFFFFFF, F_CSRRS, 0 )
  yield from csr_ut( csr, CSRA_MHARTID, 0xFFFFFFFF, F_CSRRC, 0 )

  # Test reading / writing the 'MIE' CSR.
  yield from csr_ut( csr, CSRA_MIE, 0xFFFFFFFF, F_CSRRWI, 0x00000000 )
  yield from csr_ut( csr, CSRA_MIE, 0xFFFFFFFF, F_CSRRCI, 0x00000888 )
  yield from csr_ut( csr, CSRA_MIE, 0x00000000, F_CSRRSI, 0x00000000 )
  # Test reading / writing the 'MIP' CSR. (Bits can only be cleared)
  yield from csr_ut( csr, CSRA_MIP, 0x00000000, F_CSRRW, 0x00000000 )
  yield from csr_ut( csr, CSRA_MIP, 0xFFFFFFFF, F_CSRRS, 0x00000000 )
  yield from csr_ut( csr, CSRA_MIP, 0xFFFFFFFF, F_CSRRC, 0x00000000 )
  yield csr.mip.shadow.eq( 0x00000888 )
  yield from csr_ut( csr, CSRA_MIP, 0xFFFFFFFF, F_CSRRC, 0x00000888 )
  yield from csr_ut( csr, CSRA_MIP, 0x00000000, F_CSRRS, 0x00000000 )
  # Test reading / writing the 'MCAUSE' CSR.
  yield from csr_rw_ut( csr, CSRA_MCAUSE )

  # Test reading / writing the 'MTVAL' CSR.
  yield from csr_rw_ut( csr, CSRA_MTVAL )

  # Test reading / writing the 'MEPC' CSR. All bits except 0-1 R/W.
  yield from csr_ut( csr, CSRA_MEPC, 0x00000000, F_CSRRS,  0x00000000 )
  yield from csr_ut( csr, CSRA_MEPC, 0xFFFFFFFF, F_CSRRSI, 0x00000000 )
  yield from csr_ut( csr, CSRA_MEPC, 0x01234567, F_CSRRC,  0xFFFFFFFC )
  yield from csr_ut( csr, CSRA_MEPC, 0x0C0FFEE0, F_CSRRW,  0xFEDCBA98 )
  yield from csr_ut( csr, CSRA_MEPC, 0xFFFFCBA9, F_CSRRW,  0x0C0FFEE0 )
  yield from csr_ut( csr, CSRA_MEPC, 0xFFFFFFFF, F_CSRRCI, 0xFFFFCBA8 )
  yield from csr_ut( csr, CSRA_MEPC, 0x00000000, F_CSRRS,  0x00000000 )
  # Test reading / writing the 'MSCRATCH' CSR.
  # All bits R/W, and reads reflect the previous state.
  yield from csr_rw_ut( csr, CSRA_MSCRATCH )

  # Test reading / writing the 'MCYCLE' CSR, after resetting it.
  # Verify that the it counts up every cycle unless it is written to.
  cyc_start = ( yield csr.mcycle.shadow ) & 0xFFFFFFFF
  yield from csr_ut( csr, CSRA_MCYCLE, 0x00000000, F_CSRRS,  cyc_start )
  yield from csr_ut( csr, CSRA_MCYCLE, 0xFFFFFFFF, F_CSRRSI, cyc_start + 4 )
  yield from csr_ut( csr, CSRA_MCYCLE, 0x01234567, F_CSRRC,  0xFFFFFFFF )
  yield from csr_ut( csr, CSRA_MCYCLE, 0x0C0FFEE0, F_CSRRW,  0xFEDCBA98 )
  yield from csr_ut( csr, CSRA_MCYCLE, 0xFFFFFCBA, F_CSRRWI, 0x0C0FFEE0 )
  yield from csr_ut( csr, CSRA_MCYCLE, 0xFFFFFFFF, F_CSRRCI, 0xFFFFFCBA )
  yield from csr_ut( csr, CSRA_MCYCLE, 0x00000000, F_CSRRC,  0x00000000 )
  yield from csr_ut( csr, CSRA_MCYCLE, 0x00000000, F_CSRRS,  0x00000003 )
  yield from csr_ut( csr, CSRA_MCYCLE, 0x00000000, F_CSRRS,  0x00000007 )
  yield from csr_ut( csr, CSRA_MCYCLE, 0x00000000, F_CSRRS,  0x0000000B )
  # Test reading / writing the 'MCYCLEH' CSR.
  # (It's a 64-bit hi/lo value, so it increments whenever
  #  MCYCLE == 0xFFFFFFFF. That happens twice above.)
  yield from csr_ut( csr, CSRA_MCYCLEH, 0xFFFFFFFF, F_CSRRCI, 0x00000002 )
  yield from csr_rw_ut( csr, CSRA_MCYCLEH )
  # Test reading / writing the 'MINSTRET' CSR after clearing it.
  yield from csr_rw_ut( csr, CSRA_MINSTRET )
  # Test reading / writing the 'MINSTRETH' CSR.
  yield from csr_rw_ut( csr, CSRA_MINSTRETH )
  # Test reading / writing the 'MCOUNTINHIBIT' CSR.
  # Only 'mcycle' and 'minstret' counters are implemented.
  yield from csr_ut( csr, CSRA_MCOUNTINHIBIT, 0xFFFFFFFF, F_CSRRC,  0x00000000 )
  yield from csr_ut( csr, CSRA_MCOUNTINHIBIT, 0xFFFFFFFF, F_CSRRSI, 0x00000000 )
  yield from csr_ut( csr, CSRA_MCOUNTINHIBIT, 0x01234567, F_CSRRC,  0x00000005 )
  yield from csr_ut( csr, CSRA_MCOUNTINHIBIT, 0x0C0FFEE0, F_CSRRW,  0x00000000 )

  # Test an unrecognized CSR.
  yield from csr_ut( csr, 0x101, 0x89ABCDEF, F_CSRRW,  0x00000000 )
  yield from csr_ut( csr, 0x101, 0x89ABCDEF, F_CSRRC,  0x00000000 )
  yield from csr_ut( csr, 0x101, 0x89ABCDEF, F_CSRRS,  0x00000000 )
  yield from csr_ut( csr, 0x101, 0xFFFFCDEF, F_CSRRWI, 0x00000000 )
  yield from csr_ut( csr, 0x101, 0xFFFFCDEF, F_CSRRCI, 0x00000000 )
  yield from csr_ut( csr, 0x101, 0xFFFFCDEF, F_CSRRSI, 0x00000000 )

  # Done.
  yield Tick()
  print( "CSR Tests: %d Passed, %d Failed"%( p, f ) )

# 'main' method to run a basic testbench.
if __name__ == "__main__":
  if ( len( sys.argv ) == 2 ) and ( sys.argv[ 1 ] == '-b' ):
    # Test building the module.
    UpduinoV2Platform().build( CSR(),
                               do_build = True,
                               do_program = False )
  else:
    with warnings.catch_warnings():
      warnings.filterwarnings( "ignore", category = DriverConflict )

      # Instantiate a CSR module.
      dut = CSR()

      # Run the tests.
      with Simulator( dut, vcd_file = open( 'csr.vcd', 'w' ) ) as sim:
        def proc():
          yield from csr_test( dut )
        sim.add_clock( 1e-6 )
        sim.add_sync_process( proc )
        sim.run()
