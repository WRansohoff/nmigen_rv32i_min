from isa import *

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

# Core "CSR" class, which contains an instance of each
# supported CSR class. the 'ECALL' helper methods access it.
class CSR( Elaboratable ):
  def __init__( self ):
    # CSR input/output registers.
    # TODO: Use fewer bits to encode the supported CSRs.
    # It shouldn't be complicated to do with a dictionary,
    # but it looks like the 'nmigen-soc' library includes a CSR
    # wishbone interface; maybe I can use that instead?
    self.rsel = Signal( 12, reset = 0x00000000 )
    self.rin  = Signal( 32, reset = 0x00000000 )
    self.rout = Signal( 32, reset = 0x00000000 )
    self.f    = Signal( 3,  reset = F_CSRRW )
    # Individual CSR modules.
    # Read-only constants such as MVENDORID don't have modules.
    # Some registers are simple 32-bit R/W words; those are Signals.
    self.misa     = CSR_MISA()
    self.mstatus  = CSR_MSTATUS()
    self.mscratch = Signal( 32, reset = 0x00000000 )
  def elaborate( self, platform ):
    m = Module()
    # Register CSR submodules.
    m.submodules.misa    = self.misa
    m.submodules.mstatus = self.mstatus

    # Dummy 'sync' and 'nsync' logic to make the testbench happy.
    # TODO: Figure out how to run tests without this.
    bleg = Signal()
    blegh = Signal()
    m.d.sync += bleg.eq( 1 )
    m.d.nsync += blegh.eq( 1 )

    # Handle CSR logic.
    with m.If( self.rsel == CSRA_MISA ):
      # MISA is 'WARL', so ignore writes.
      m.d.comb += self.rout.eq( ( self.misa.mxl << 30 ) |
          ( self.misa.z << 25 ) | ( self.misa.y << 24 ) |
          ( self.misa.x << 23 ) | ( self.misa.w << 22 ) |
          ( self.misa.v << 21 ) | ( self.misa.u << 20 ) |
          ( self.misa.t << 19 ) | ( self.misa.s << 18 ) |
          ( self.misa.r << 17 ) | ( self.misa.q << 16 ) |
          ( self.misa.p << 15 ) | ( self.misa.o << 14 ) |
          ( self.misa.n << 13 ) | ( self.misa.m << 12 ) |
          ( self.misa.l << 11 ) | ( self.misa.k << 10 ) |
          ( self.misa.j << 9  ) | ( self.misa.i << 8  ) |
          ( self.misa.h << 7  ) | ( self.misa.g << 6  ) |
          ( self.misa.f << 5  ) | ( self.misa.e << 4  ) |
          ( self.misa.d << 3  ) | ( self.misa.c << 2  ) |
          ( self.misa.b << 1  ) | ( self.misa.a << 0  ) )
    with m.Elif( self.rsel == CSRA_MVENDORID ):
      # Vendor ID is read-only, so ignore writes.
      m.d.comb += self.rout.eq( VENDOR_ID )
    with m.Elif( self.rsel == CSRA_MARCHID ):
      # Architecture ID is read-only, so ignore writes.
      m.d.comb += self.rout.eq( ARCH_ID )
    with m.Elif( self.rsel == CSRA_MIMPID ):
      # Machine Implementation ID is read-only, so ignore writes.
      m.d.comb += self.rout.eq( MIMP_ID )
    with m.Elif( self.rsel == CSRA_MHARTID ):
      # Machine hardware thread ID; this read-only register returns
      # a unique ID representing the hart which is currently running
      # code, and there must be a hart with ID 0.
      # I only have one hart, so...
      m.d.comb += self.rout.eq( 0x00000000 )
    with m.Elif( self.rsel == CSRA_MSTATUS ):
      # Lower 32 bits of the 'MSTATUS' register.
      # TODO: Writes.
      m.d.comb += self.rout.eq(
        ( self.mstatus.sie  << 1  ) | ( self.mstatus.mie  << 3  ) |
        ( self.mstatus.spie << 5  ) | ( self.mstatus.ube  << 6  ) |
        ( self.mstatus.mpie << 7  ) | ( self.mstatus.spp  << 8  ) |
        ( self.mstatus.mpp  << 11 ) | ( self.mstatus.fs   << 13 ) |
        ( self.mstatus.xs   << 15 ) | ( self.mstatus.mprv << 17 ) |
        ( self.mstatus.sum  << 18 ) | ( self.mstatus.mxr  << 19 ) |
        ( self.mstatus.tvm  << 20 ) | ( self.mstatus.tw   << 21 ) |
        ( self.mstatus.tsr  << 22 ) | ( self.mstatus.sd   << 30 ) )
    with m.Elif( self.rsel == CSRA_MSTATUSH ):
      # Upper 32 bits of the 'MSTATUS' register.
      # TODO: Writes.
      m.d.comb += self.rout.eq(
        ( self.mstatus.sbe << 4 ) | ( self.mstatus.mbe << 5 ) )
    with m.Elif( self.rsel == CSRA_MSCRATCH ):
      # 'MSCRATCH' register, used to store a word of state.
      # Usually this is a memory address for a context to return to.
      m.d.comb += self.rout.eq( self.mscratch )
      # Apply writes on the next falling clock edge.
      with m.If( ( self.f & 0b11 ) == 0b01 ):
        # 'Write' - set the register to the input value.
        m.d.nsync += self.mscratch.eq( self.rin )
      with m.Elif( ( self.f & 0b11 ) == 0b10 ):
        # 'Set' - set bits which are set in the input value.
        m.d.nsync += self.mscratch.eq( self.mscratch | self.rin )
      with m.Elif( ( self.f & 0b11 ) == 0b11 ):
        # 'Clear' - reset bits which are set in the input value.
        m.d.nsync += self.mscratch.eq( self.mscratch & ~( self.rin ) )
    with m.Else():
      # Return 0 without action for an unrecognized CSR.
      # TODO: Am I supposed to throw an exception or something here?
      m.d.comb += self.rout.eq( 0x00000000 )
    return m

# 'MISA' register. Contains information about supported ISA modules.
# The application can also set bits in this register to enable or
# disable certain extensions. And it is a 'WARL' register, so any
# writes which request unsupported extensions are silently ignored.
class CSR_MISA( Elaboratable ):
  def __init__( self ):
    # TODO: Since this CPU only supports RV32I, I'm going
    # to make most of these values constants. But for supported
    # extensions, they should be writable Signal()s.
    # I did make the 'E' extension a Signal, because it is always
    # the opposite of the 'I' extension, and that's trivial.
    self.mxl = MISA_MSL_32
    self.a   = 0 # No atomic extension.
    self.b   = 0 # No bit manipulation extension.
    self.c   = 0 # No 'compressed instructions' extension.
    self.d   = 0 # No double-precision floating-point extension.
    # ('E' and 'I' extensions are mutually exclusive)
    self.e   = Signal( 1, reset = 0b0 )
    self.f   = 0 # No single-precision floating-point extension.
    self.g   = 0 # (Reserved)
    self.h   = 0 # No hypervisor mode extension.
    self.i   = 1 # Core RV32I instructions are supported.
    self.j   = 0 # No...'dynamically-translated language extension'?
    self.k   = 0 # (Reserved)
    self.l   = 0 # No decimal floating-point extension.
    self.m   = 0 # No multiply / divide extension.
    self.n   = 0 # No user-level interrupts extension.
    self.o   = 0 # (Reserved)
    self.p   = 0 # No packed SIMD extension.
    self.q   = 0 # No quad-precision floating-point extension.
    self.r   = 0 # (Reserved)
    self.s   = 0 # No supervisor mode extension.
    self.t   = 0 # No transactional memory extension.
    self.u   = 0 # No user mode extension.
    self.v   = 0 # No vector extension.
    self.w   = 0 # (Reserved)
    self.x   = 0 # No non-standard extensions.
    self.y   = 0 # (Reserved)
    self.z   = 0 # (Reserved)
  def elaborate( self, platform ):
    m = Module()
    # CPU must implement one core ISA, so 'E' = not 'I'.
    m.d.nsync += self.e.eq( ~self.i )
    return m

# 'MSTATUS' CSR. These fields actually spans two 32-bit registers on
# 32-bit platforms, with some 'WPRI' bits that are reserved for
# future use and can be hard-wired to 0.
class CSR_MSTATUS( Elaboratable ):
  def __init__( self ):
    # 'MSTATUS' fields:
    self.sie  = Signal( 1, reset = 0b0 )
    self.mie  = Signal( 1, reset = 0b0 )
    self.spie = Signal( 1, reset = 0b0 )
    self.ube  = Signal( 1, reset = 0b0 )
    self.mpie = Signal( 1, reset = 0b0 )
    self.spp  = Signal( 1, reset = 0b0 )
    self.mpp  = Signal( 2, reset = 0b00 )
    self.fs   = Signal( 2, reset = 0b00 )
    self.xs   = Signal( 2, reset = 0b00 )
    self.mprv = Signal( 1, reset = 0b0 )
    self.sum  = Signal( 1, reset = 0b0 )
    self.mxr  = Signal( 1, reset = 0b0 )
    self.tvm  = Signal( 1, reset = 0b0 )
    self.tw   = Signal( 1, reset = 0b0 )
    self.tsr  = Signal( 1, reset = 0b0 )
    self.sd   = Signal( 1, reset = 0b0 )
    # 'MSTATUSH' fields:
    self.sbe  = Signal( 1, reset = 0b0 )
    self.mbe  = Signal( 1, reset = 0b0 )
  def elaborate( self, platform ):
    m = Module()
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
  # Wait a tick.
  yield Tick()
  # Done. Check the result after combinatorial logic.
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

# Top-level CSR test method.
def csr_test( csr ):
  # Let signals settle after reset.
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
  # Test reading / writing the 'MIMPID' CSR. (Should be read-only)
  yield from csr_ut( csr, CSRA_MIMPID, 0x00000000, F_CSRRW, MIMP_ID )
  yield from csr_ut( csr, CSRA_MIMPID, 0xFFFFFFFF, F_CSRRS, MIMP_ID )
  yield from csr_ut( csr, CSRA_MIMPID, 0xFFFFFFFF, F_CSRRC, MIMP_ID )
  # Test reading / writing the 'MHARTID' CSR. (Should be read-only)
  yield from csr_ut( csr, CSRA_MHARTID, 0x00000000, F_CSRRW, 0 )
  yield from csr_ut( csr, CSRA_MHARTID, 0xFFFFFFFF, F_CSRRS, 0 )
  yield from csr_ut( csr, CSRA_MHARTID, 0xFFFFFFFF, F_CSRRC, 0 )

  # TODO: Test reading / writing 'MSTATUS' CSR.

  # Test reading / writing the 'MSCRATCH' CSR. (All bits R/W)
  yield from csr_ut( csr, CSRA_MSCRATCH, 0x00000000, F_CSRRS,  0x00000000 )
  yield from csr_ut( csr, CSRA_MSCRATCH, 0xFFFFFFFF, F_CSRRSI, 0xFFFFFFFF )
  yield from csr_ut( csr, CSRA_MSCRATCH, 0x01234567, F_CSRRC,  0xFEDCBA98 )
  yield from csr_ut( csr, CSRA_MSCRATCH, 0x0C0FFEE0, F_CSRRW,  0x0C0FFEE0 )
  yield from csr_ut( csr, CSRA_MSCRATCH, 0xFFFFCBA9, F_CSRRW,  0xFFFFCBA9 )
  yield from csr_ut( csr, CSRA_MSCRATCH, 0xFFFFFFFF, F_CSRRCI, 0x00000000 )

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
  # Instantiate a CSR module.
  dut = CSR()

  # Run the tests.
  with Simulator( dut, vcd_file = open( 'csr.vcd', 'w' ) ) as sim:
    def proc():
      yield from csr_test( dut )
    sim.add_clock( 24e-6 )
    sim.add_clock( 24e-6, domain = "nsync" )
    sim.add_sync_process( proc )
    sim.run()
