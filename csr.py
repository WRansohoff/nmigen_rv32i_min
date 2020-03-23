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

# Helper method to perform CSR write/set/clear logic on a whole
# 32-bit register.
def csr_w32( self, csr, reg ):
  # Apply writes on the next rising clock edge.
  with csr.If( ( self.f & 0b11 ) == 0b01 ):
    # 'Write' - set the register to the input value.
    csr.d.sync += reg.eq( self.rin )
  with csr.Elif( ( self.f & 0b11 ) == 0b10 ):
    # 'Set' - set bits which are set in the input value.
    csr.d.sync += reg.eq( reg | self.rin )
  with csr.Elif( ( self.f & 0b11 ) == 0b11 ):
    # 'Clear' - reset bits which are set in the input value.
    csr.d.sync += reg.eq( reg & ~( self.rin ) )

# Helper method to perform CSR write/set/clear logic on the
# lower 32 bits of a 64-bit register.
def csr_w64l( self, csr, reg ):
  # Apply writes on the next rising clock edge.
  with csr.If( ( self.f & 0b11 ) == 0b01 ):
    # 'Write' - set the register to the input value.
    csr.d.sync += reg.eq( ( reg & 0xFFFFFFFF00000000 ) | self.rin )
  with csr.Elif( ( self.f & 0b11 ) == 0b10 ):
    # 'Set' - set bits which are set in the input value.
    csr.d.sync += reg.eq( reg | self.rin )
  with csr.Elif( ( self.f & 0b11 ) == 0b11 ):
    # 'Clear' - reset bits which are set in the input value.
    csr.d.sync += reg.eq( reg & ~( self.rin ) )

# Helper method to perform CSR write/set/clear logic on the
# upper 32 bits of a 64-bit register.
def csr_w64h( self, csr, reg ):
  # Apply writes on the next rising clock edge.
  with csr.If( ( self.f & 0b11 ) == 0b01 ):
    # 'Write' - set the register to the input value.
    csr.d.sync += reg.eq(
      ( reg & 0x00000000FFFFFFFF ) | ( self.rin << 32 ) )
  with csr.Elif( ( self.f & 0b11 ) == 0b10 ):
    # 'Set' - set bits which are set in the input value.
    csr.d.sync += reg.eq( reg | ( self.rin << 32 ) )
  with csr.Elif( ( self.f & 0b11 ) == 0b11 ):
    # 'Clear' - reset bits which are set in the input value.
    csr.d.sync += reg.eq( reg & ~( self.rin << 32 ) )

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
    self.mtvec    = CSR_MTVEC()
    self.mie      = CSR_MINTS()
    self.mip      = CSR_MINTS()
    self.mcause   = CSR_MCAUSE()
    self.mscratch = Signal( 32, reset = 0x00000000 )
    self.mepc     = Signal( 32, reset = 0x00000000 )
    self.mtval    = Signal( 32, reset = 0x00000000 )
    # Timers and performance monitors. The performance monitors are
    # cool, there are 29 timers which can be configured to tick up
    # when arbitrary events occur, and your platform decides what
    # those events are; each one has a bit in the 'MHPMEVENT'
    # registers. There are no events yet, so they don't increment.
    # (Use 64-bit counters for both hi and lo bits.)
    self.mcycle        = Signal( 64, reset = 0x0000000000000000 )
    # TODO: 'MINSTRET' starts at -1 because it ticks up before
    # the first instruction is executed. Not sure if that's kosher.
    self.minstret      = Signal( 64, reset = 0xFFFFFFFFFFFFFFFF )
    self.mhpmcounter   = Array(
      Signal( 64, reset = 0x0000000000000000 ) for i in range( 29 )
    )
    self.mcountinhibit = Signal( 32, reset = 0x00000000 )
    self.mhpevent      = Array(
      Signal( 32, reset = 0x00000000 ) for i in range( 29 )
    )

  def elaborate( self, platform ):
    m = Module()
    # Register CSR submodules.
    m.submodules.misa    = self.misa
    m.submodules.mstatus = self.mstatus
    m.submodules.mtvec   = self.mtvec
    m.submodules.mie     = self.mie
    m.submodules.mip     = self.mip
    m.submodules.mcause  = self.mcause

    # The 'MCYCLE' CSR increments every clock tick.
    m.d.sync += self.mcycle.eq( self.mcycle + 1 )

    # Handle CSR read / write logic.
    with m.If( self.rsel == CSRA_MISA ):
      # MISA is 'WARL', so ignore writes.
      m.d.nsync += self.rout.eq( ( self.misa.mxl << 30 ) |
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
      m.d.nsync += self.rout.eq( VENDOR_ID )
    with m.Elif( self.rsel == CSRA_MARCHID ):
      # Architecture ID is read-only, so ignore writes.
      m.d.nsync += self.rout.eq( ARCH_ID )
    with m.Elif( self.rsel == CSRA_MIMPID ):
      # Machine Implementation ID is read-only, so ignore writes.
      m.d.nsync += self.rout.eq( MIMP_ID )
    with m.Elif( self.rsel == CSRA_MHARTID ):
      # Machine hardware thread ID; this read-only register returns
      # a unique ID representing the hart which is currently running
      # code, and there must be a hart with ID 0.
      # I only have one hart, so...
      m.d.nsync += self.rout.eq( 0x00000000 )
    with m.Elif( self.rsel == CSRA_MSTATUS ):
      # Lower 32 bits of the 'MSTATUS' register.
      # Supervisor and hypervisor modes are not currently implemented,
      # So their bits are set to zero. 'MPP' bits are also always equal.
      # User mode is also not currently implemented, so MPRV = 0.
      # Since only machine mode is supported, TW = 0.
      # Since no floating-point extension exists, FS = 0.
      # Since no user extensions exist, XS = 0.
      # Since FS = 0 and XS = 0, SD = 0. That doesn't leave many bits :)
      m.d.nsync += self.rout.eq(
        ( self.mstatus.mie  << 3  ) | ( self.mstatus.mpie << 7  ) |
        ( self.mstatus.mpp  << 11 ) )
      # Apply writes on the next rising clock edge - AFTER reads.
      # MPIE cannot be written because it is set/reset by hardware.
      with m.If( ( self.f & 0b11 ) == 0b01 ):
        # 'Write' - write writable bits from the input field.
        m.d.sync += self.mstatus.mie.eq( self.rin.bit_select( 3, 1 ) )
      with m.Elif( ( self.f & 0b11 ) == 0b10 ):
        # 'Set' - set writable bits from the input value.
        with m.If( self.rin.bit_select( 3, 1 ) != 0 ):
          m.d.sync += self.mstatus.mie.eq( 0b1 )
      with m.Elif( ( self.f & 0b11 ) == 0b11 ):
        # 'Clear' - reset writable bits from the input value.
        with m.If( self.rin.bit_select( 3, 1 ) != 0 ):
          m.d.sync += self.mstatus.mie.eq( 0b0 )
    with m.Elif( self.rsel == CSRA_MSTATUSH ):
      # Upper 32 bits of the 'MSTATUS' register.
      # Writes are ignored, since none of its fields can be modified.
      m.d.nsync += self.rout.eq( self.mstatus.mbe << 5 )
    with m.Elif( self.rsel == CSRA_MTVEC ):
      # 'MTVEC' register, used to store the vector table's
      # starting address and interrupt mode (vectored or direct).
      m.d.nsync += self.rout.eq(
        ( self.mtvec.base << 2 ) | ( self.mtvec.mode ) )
      # Apply writes on the next rising clock edge.
      with m.If( ( self.f & 0b11 ) == 0b01 ):
        # 'Write' - write writable bits from the input field.
        m.d.sync += self.mtvec.base.eq( self.rin.bit_select( 2, 30 ) )
        # Ignore modes other than 0, 1.
        with m.If( self.rin[ 1 ] == 0 ):
          m.d.sync += self.mtvec.mode.eq( self.rin[ 0 ] )
      with m.Elif( ( self.f & 0b11 ) == 0b10 ):
        # 'Set' - set writable bits from the input value.
        m.d.sync += self.mtvec.base.eq(
          ( self.rin.bit_select( 2, 30 ) ) | self.mtvec.base )
        # Ignore modes other than 0, 1.
        with m.If( ( self.rin[ 1 ] == 0 ) & ( self.rin[ 0 ] == 1 ) ):
          m.d.sync += self.mtvec.mode.eq( 1 )
      with m.Elif( ( self.f & 0b11 ) == 0b11 ):
        # 'Clear' - reset writable bits from the input value.
        m.d.sync += self.mtvec.base.eq(
          ~( self.rin.bit_select( 2, 30 ) ) & self.mtvec.base )
        # Ignore modes other than 0, 1.
        with m.If( ( self.rin[ 1 ] == 0 ) & ( self.rin[ 0 ] == 1 ) ):
          m.d.sync += self.mtvec.mode.eq( 0 )
    with m.Elif( self.rsel == CSRA_MIE ):
      # 'MIE' register, used to enable or disable interrupt channels.
      m.d.nsync += self.rout.eq( ( self.mie.ms << 3 ) |
        ( self.mie.mt << 7 ) | ( self.mie.me << 11 ) )
      # Apply writes on the next rising clock edge.
      with m.If( ( self.f & 0b11 ) == 0b01 ):
        # 'Write' - write writable bits from the input field.
        m.d.sync += [
          self.mie.ms.eq( self.rin[ 3 ] ),
          self.mie.mt.eq( self.rin[ 7 ] ),
          self.mie.me.eq( self.rin[ 11 ] )
        ]
      with m.Elif( ( self.f & 0b11 ) == 0b10 ):
        # 'Set' - set writable bits from the input value.
        with m.If( self.rin[ 3 ] == 1 ):
          m.d.sync += self.mie.ms.eq( 1 )
        with m.If( self.rin[ 7 ] == 1 ):
          m.d.sync += self.mie.mt.eq( 1 )
        with m.If( self.rin[ 11 ] == 1 ):
          m.d.sync += self.mie.me.eq( 1 )
      with m.Elif( ( self.f & 0b11 ) == 0b11 ):
        # 'Clear' - reset writable bits from the input value.
        with m.If( self.rin[ 3 ] == 1 ):
          m.d.sync += self.mie.ms.eq( 0 )
        with m.If( self.rin[ 7 ] == 1 ):
          m.d.sync += self.mie.mt.eq( 0 )
        with m.If( self.rin[ 11 ] == 1 ):
          m.d.sync += self.mie.me.eq( 0 )
    with m.Elif( self.rsel == CSRA_MIP ):
      # 'MIP' register, used to clear interrupt 'pending' bits.
      # These bits can only be cleared by software, not set.
      m.d.nsync += self.rout.eq( ( self.mip.ms << 3 ) |
        ( self.mip.mt << 7 ) | ( self.mip.me << 11 ) )
      # Apply writes on the next rising clock edge.
      with m.If( ( self.f & 0b11 ) == 0b01 ):
        # 'Write' - write writable bits from the input field.
        with m.If( self.rin[ 3 ] == 0 ):
          m.d.sync += self.mip.ms.eq( 0 )
        with m.If( self.rin[ 7 ] == 0 ):
          m.d.sync += self.mip.mt.eq( 0 )
        with m.If( self.rin[ 11 ] == 0 ):
          m.d.sync += self.mip.me.eq( 0 )
      with m.Elif( ( self.f & 0b11 ) == 0b11 ):
        # 'Clear' - reset writable bits from the input value.
        with m.If( self.rin[ 3 ] == 1 ):
          m.d.sync += self.mip.ms.eq( 0 )
        with m.If( self.rin[ 7 ] == 1 ):
          m.d.sync += self.mip.mt.eq( 0 )
        with m.If( self.rin[ 11 ] == 1 ):
          m.d.sync += self.mip.me.eq( 0 )
    with m.Elif( self.rsel == CSRA_MCAUSE ):
      # 'MCAUSE' register, holds the cause of an interrupt or exception.
      # This register can also be written to, but it is WLRL
      # so reserved bits are set to 0.
      with m.If( self.mcause.int == 0 ):
        m.d.nsync += self.rout.eq( self.mcause.imis |
          ( self.mcause.iaf  << 1  ) | ( self.mcause.ill  << 2  ) |
          ( self.mcause.brk  << 3  ) | ( self.mcause.lmis << 4  ) |
          ( self.mcause.laf  << 5  ) | ( self.mcause.smis << 6  ) |
          ( self.mcause.saf  << 7  ) | ( self.mcause.ipf  << 12 ) |
          ( self.mcause.lpf  << 13 ) | ( self.mcause.spf  << 14 ) )
      with m.Else():
        m.d.nsync += self.rout.eq( 0x80000000 |
          ( self.mcause.ms << 3  ) | ( self.mcause.mt << 7 ) |
          ( self.mcause.me << 11 ) )
      # Apply writes on the next rising clock edge.
      with m.If( ( self.f & 0b11 ) == 0b01 ):
        # 'Write' - write writable bits from the input field.
        with m.If( self.rin[ 31 ] == 0 ):
          # Accept writes to exception fields.
          m.d.sync += [
            self.mcause.int.eq( 0 ),
            self.mcause.imis.eq( self.rin[ 0 ] ),
            self.mcause.iaf.eq( self.rin[ 1 ] ),
            self.mcause.ill.eq( self.rin[ 2 ] ),
            self.mcause.brk.eq( self.rin[ 3 ] ),
            self.mcause.lmis.eq( self.rin[ 4 ] ),
            self.mcause.laf.eq( self.rin[ 5 ] ),
            self.mcause.smis.eq( self.rin[ 6 ] ),
            self.mcause.saf.eq( self.rin[ 7 ] ),
            self.mcause.ipf.eq( self.rin[ 12 ] ),
            self.mcause.lpf.eq( self.rin[ 13 ] ),
            self.mcause.spf.eq( self.rin[ 14 ] ),
          ]
        with m.Else():
          # Accept writes to interrupt fields.
          m.d.sync += [
            self.mcause.int.eq( 1 ),
            self.mcause.ms.eq( self.rin[ 3 ] ),
            self.mcause.mt.eq( self.rin[ 7 ] ),
            self.mcause.me.eq( self.rin[ 11 ] )
          ]
      with m.Elif( ( self.f & 0b11 ) == 0b10 ):
        # 'Set' - set writable bits from the input value.
        with m.If( ( self.rin[ 31 ] == 1 ) |
                   ( self.mcause.int == 1 ) ):
          # Set interrupt bits.
          m.d.sync += [
            self.mcause.int.eq( 1 ),
            self.mcause.ms.eq( self.mcause.ms | self.rin[ 3 ] ),
            self.mcause.mt.eq( self.mcause.ms | self.rin[ 7 ] ),
            self.mcause.me.eq( self.mcause.ms | self.rin[ 11 ] )
          ]
        with m.Else():
          # Set exception bits.
          m.d.sync += [
            self.mcause.imis.eq( self.mcause.imis | self.rin[ 0  ] ),
            self.mcause.iaf.eq(  self.mcause.iaf  | self.rin[ 1  ] ),
            self.mcause.ill.eq(  self.mcause.ill  | self.rin[ 2  ] ),
            self.mcause.brk.eq(  self.mcause.brk  | self.rin[ 3  ] ),
            self.mcause.lmis.eq( self.mcause.lmis | self.rin[ 4  ] ),
            self.mcause.laf.eq(  self.mcause.laf  | self.rin[ 5  ] ),
            self.mcause.smis.eq( self.mcause.smis | self.rin[ 6  ] ),
            self.mcause.saf.eq(  self.mcause.saf  | self.rin[ 7  ] ),
            self.mcause.ipf.eq(  self.mcause.ipf  | self.rin[ 12 ] ),
            self.mcause.lpf.eq(  self.mcause.lpf  | self.rin[ 13 ] ),
            self.mcause.spf.eq(  self.mcause.spf  | self.rin[ 14 ] )
          ]
      with m.Elif( ( self.f & 0b11 ) == 0b11 ):
        # 'Clear' - reset writable bits from the input value.
        with m.If( ( self.rin[ 31 ] == 1 ) |
                   ( self.mcause.int == 0 ) ):
          # Clear interrupt bits.
          m.d.sync += [
            self.mcause.int.eq( 0 ),
            self.mcause.imis.eq( self.mcause.imis & ~( self.rin[ 0  ] ) ),
            self.mcause.iaf.eq(  self.mcause.iaf  & ~( self.rin[ 1  ] ) ),
            self.mcause.ill.eq(  self.mcause.ill  & ~( self.rin[ 2  ] ) ),
            self.mcause.brk.eq(  self.mcause.brk  & ~( self.rin[ 3  ] ) ),
            self.mcause.lmis.eq( self.mcause.lmis & ~( self.rin[ 4  ] ) ),
            self.mcause.laf.eq(  self.mcause.laf  & ~( self.rin[ 5  ] ) ),
            self.mcause.smis.eq( self.mcause.smis & ~( self.rin[ 6  ] ) ),
            self.mcause.saf.eq(  self.mcause.saf  & ~( self.rin[ 7  ] ) ),
            self.mcause.ipf.eq(  self.mcause.ipf  & ~( self.rin[ 12 ] ) ),
            self.mcause.lpf.eq(  self.mcause.lpf  & ~( self.rin[ 13 ] ) ),
            self.mcause.spf.eq(  self.mcause.spf  & ~( self.rin[ 14 ] ) )
          ]
        with m.Else():
          # Clear exception bits.
          m.d.sync += [
            self.mcause.ms.eq( self.mcause.ms & ~( self.rin[ 3 ] ) ),
            self.mcause.mt.eq( self.mcause.ms & ~( self.rin[ 7 ] ) ),
            self.mcause.me.eq( self.mcause.ms & ~( self.rin[ 11 ] ) )
          ]
    with m.Elif( self.rsel == CSRA_MEPC ):
      # 'MEPC' register, holds the address which was jumped from when
      # a trap is entered. Can also be written by software.
      m.d.nsync += self.rout.eq( self.mepc & 0xFFFFFFFC )
      # Apply writes on the next rising clock edge.
      # Bits 0-1 are always zero.
      with m.If( ( self.f & 0b11 ) == 0b01 ):
        # 'Write' - write writable bits from the input field.
        m.d.sync += self.mepc.eq( self.rin & 0xFFFFFFFC )
      with m.Elif( ( self.f & 0b11 ) == 0b10 ):
        # 'Set' - set writable bits from the input value.
        m.d.sync += self.mepc.eq( self.mepc | ( self.rin & 0xFFFFFFFC ) )
      with m.Elif( ( self.f & 0b11 ) == 0b11 ):
        # 'Clear' - reset writable bits from the input value.
        m.d.sync += self.mepc.eq( self.mepc & ~( self.rin ) )
    with m.Elif( self.rsel == CSRA_MTVAL ):
      # 'MTVAL' register, holds extra information about a trap.
      # Possible values depend on the trap.
      m.d.nsync += self.rout.eq( self.mtval )
    with m.Elif( self.rsel == CSRA_MSCRATCH ):
      # 'MSCRATCH' register, used to store a word of state.
      # Usually this is a memory address for a context to return to.
      m.d.nsync += self.rout.eq( self.mscratch )
      # Apply CSR write logic for the whole register.
      csr_w32( self, m, self.mscratch )
    with m.Elif( self.rsel == CSRA_MCYCLE ):
      m.d.nsync += self.rout.eq( self.mcycle & 0xFFFFFFFF )
      # Apply CSR write logic for the lower 32 bits.
      csr_w64l( self, m, self.mcycle )
      # If 'MCYCLE' would not be changed, increment it.
      with m.If( ( ( self.f & 0b10 ) != 0 ) & ( self.rin == 0 ) ):
        m.d.sync += self.mcycle.eq( self.mcycle + 1 )
    with m.Elif( self.rsel == CSRA_MCYCLEH ):
      m.d.nsync += self.rout.eq( self.mcycle >> 32 )
      # Apply CSR write logic for the upper 32 bits.
      csr_w64h( self, m, self.mcycle )
      # If 'MCYCLE' would not be changed, increment it.
      with m.If( ( ( self.f & 0b10 ) != 0 ) & ( self.rin == 0 ) ):
        m.d.sync += self.mcycle.eq( self.mcycle + 1 )
    with m.Elif( self.rsel == CSRA_MINSTRET ):
      m.d.nsync += self.rout.eq( self.minstret & 0xFFFFFFFF )
      # Apply CSR write logic for the lower 32 bits.
      csr_w64l( self, m, self.minstret )
    with m.Elif( self.rsel == CSRA_MINSTRETH ):
      m.d.nsync += self.rout.eq( self.minstret >> 32 )
      # Apply CSR write logic for the upper 32 bits.
      csr_w64h( self, m, self.minstret )
    with m.Elif( ( self.rsel >= CSRA_MHPMCOUNTER_MIN ) &
                 ( self.rsel <= CSRA_MHPMCOUNTER_MAX ) ):
      m.d.nsync += self.rout.eq(
        ( self.mhpmcounter[ self.rsel - CSRA_MHPMCOUNTER_MIN ] ) & 0xFFFFFFFF )
      # Apply CSR write logic for the lower 32 bits.
      csr_w64l( self, m, self.mhpmcounter[ self.rsel - CSRA_MHPMCOUNTER_MIN ] )
    with m.Elif( ( self.rsel >= CSRA_MHPMCOUNTERH_MIN ) &
                 ( self.rsel <= CSRA_MHPMCOUNTERH_MAX ) ):
      m.d.nsync += self.rout.eq(
        ( self.mhpmcounter[ self.rsel - CSRA_MHPMCOUNTERH_MIN ] ) >> 32 )
      # Apply CSR write logic for the upper 32 bits.
      csr_w64h( self, m, self.mhpmcounter[ self.rsel - CSRA_MHPMCOUNTERH_MIN ] )
    with m.Elif( self.rsel == CSRA_MCOUNTINHIBIT ):
      m.d.nsync += self.rout.eq( self.mcountinhibit )
      # TODO: writes
    with m.Elif( ( self.rsel >= CSRA_MHPMEVENT_MIN ) &
                 ( self.rsel <= CSRA_MHPMEVENT_MAX ) ):
      m.d.nsync += self.rout.eq(
        self.mhpevent[ self.rsel - CSRA_MHPMEVENT_MIN ] )
      # Apply CSR write logic for the whole register.
      csr_w32( self, m, self.mhpevent[ self.rsel - CSRA_MHPMEVENT_MIN ] )
    with m.Else():
      # Return 0 without action for an unrecognized CSR.
      # TODO: Am I supposed to throw an exception or something here?
      m.d.nsync += self.rout.eq( 0x00000000 )
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
    m.d.comb += self.e.eq( ~self.i )
    return m

# 'MSTATUS' CSR. These fields actually spans two 32-bit registers on
# 32-bit platforms, with some 'WPRI' bits that are reserved for
# future use and can be hard-wired to 0.
class CSR_MSTATUS( Elaboratable ):
  def __init__( self ):
    # 'MSTATUS' fields:
    self.mie  = Signal( 1, reset = 0b0 )
    self.mpie = Signal( 1, reset = 0b0 )
    # (Currently, only machine mode is supported.)
    self.mpp  = MSTATUS_MPP_M
    # 'MSTATUSH' fields:
    # (Currently, only little-endian memory access is supported.)
    self.mbe  = MSTATUS_MBE_LIT
  def elaborate( self, platform ):
    m = Module()
    return m

# 'MTVEC' CSR. Contains the base vector table address with interrupt
# handler locations and the current interrupt handling mode.
class CSR_MTVEC( Elaboratable ):
  def __init__( self ):
    self.base = Signal( 30, reset = 0 )
    self.mode = Signal( 1,  reset = 0 )
  def elaborate( self, platform ):
    m = Module()
    return m

# 'MIE' or 'MIP' CSR. They both use the same bit
# positions to identify interrupt types.
class CSR_MINTS( Elaboratable ):
  def __init__( self ):
    # Machine software interrupt.
    self.ms = Signal( 1, reset = 0b0 )
    # Machine timer interrupt.
    self.mt = Signal( 1, reset = 0b0 )
    # Machine external interrupt.
    self.me = Signal( 1, reset = 0b0 )
  def elaborate( self, platform ):
    m = Module()
    return m

# 'MCAUSE' CSR. This uses the same interrupt bits as
# 'MIE' and 'MIP', but it has extra exception/reset causes.
class CSR_MCAUSE( Elaboratable ):
  def __init__( self ):
    # 'Interrupt or exception?' bit.
    self.int = Signal( 1, reset = 0b0 )
    # Interrupt bits (See 'CSR_MINTS')
    self.ms = Signal( 1, reset = 0b0 )
    self.mt = Signal( 1, reset = 0b0 )
    self.me = Signal( 1, reset = 0b0 )
    # Exception / reset cause bits:
    # These should not be reset with the clock domain reset signal,
    # because one of their uses is to preserve the cause of a reset.
    # Instruction address misaligned.
    self.imis = Signal( 1, reset = 0b0, reset_less = True )
    # Instruction access fault.
    self.iaf  = Signal( 1, reset = 0b0, reset_less = True )
    # Illegal instruction.
    self.ill  = Signal( 1, reset = 0b0, reset_less = True )
    # Breakpoint.
    self.brk  = Signal( 1, reset = 0b0, reset_less = True )
    # Load address misaligned.
    self.lmis = Signal( 1, reset = 0b0, reset_less = True )
    # Load access fault.
    self.laf  = Signal( 1, reset = 0b0, reset_less = True )
    # Store address misaligned.
    self.smis = Signal( 1, reset = 0b0, reset_less = True )
    # Store access fault.
    self.saf  = Signal( 1, reset = 0b0, reset_less = True )
    # Instruction page fault.
    self.ipf  = Signal( 1, reset = 0b0, reset_less = True )
    # Load page fault.
    self.lpf  = Signal( 1, reset = 0b0, reset_less = True )
    # Store page fault.
    self.spf  = Signal( 1, reset = 0b0, reset_less = True )
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
  # Reset rsel, rin, f.
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
  yield from csr_ut( csr, CSRA_MTVEC, 0xFFFFFFFF, F_CSRRCI, 0xFFFFFFFC )
  yield from csr_ut( csr, CSRA_MTVEC, 0xFFFFFFFD, F_CSRRSI, 0x00000000 )
  yield from csr_ut( csr, CSRA_MTVEC, 0x00000001, F_CSRRW,  0xFFFFFFFD )
  yield from csr_ut( csr, CSRA_MTVEC, 0x00000000, F_CSRRS,  0x00000001 )

  # Test reading / writing the 'MTVAL' CSR. (Should be read-only)
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
  yield csr.mip.ms.eq( 1 )
  yield csr.mip.mt.eq( 1 )
  yield csr.mip.me.eq( 1 )
  yield from csr_ut( csr, CSRA_MIP, 0xFFFFFFFF, F_CSRRC, 0x00000888 )
  yield from csr_ut( csr, CSRA_MIP, 0x00000000, F_CSRRS, 0x00000000 )
  # Test reading / writing the 'MCAUSE' CSR.
  yield from csr_ut( csr, CSRA_MCAUSE, 0x7FFFFFFF, F_CSRRW,  0x00000000 )
  yield from csr_ut( csr, CSRA_MCAUSE, 0xFFFFFFFF, F_CSRRWI, 0x000070FF )
  yield from csr_ut( csr, CSRA_MCAUSE, 0xFFFFFFFF, F_CSRRC,  0x80000888 )
  yield from csr_ut( csr, CSRA_MCAUSE, 0x80000000, F_CSRRS,  0x00000000 )
  yield from csr_ut( csr, CSRA_MCAUSE, 0x7FFFFFFF, F_CSRRCI, 0x80000888 )
  yield from csr_ut( csr, CSRA_MCAUSE, 0x00000000, F_CSRRSI, 0x80000000 )

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
  yield csr.mcycle.eq( 0 )
  yield from csr_ut( csr, CSRA_MCYCLE, 0x00000000, F_CSRRS,  0x00000000 )
  yield from csr_ut( csr, CSRA_MCYCLE, 0xFFFFFFFF, F_CSRRSI, 0x00000001 )
  yield from csr_ut( csr, CSRA_MCYCLE, 0x01234567, F_CSRRC,  0xFFFFFFFF )
  yield from csr_ut( csr, CSRA_MCYCLE, 0x0C0FFEE0, F_CSRRW,  0xFEDCBA98 )
  yield from csr_ut( csr, CSRA_MCYCLE, 0xFFFFFCBA, F_CSRRWI, 0x0C0FFEE0 )
  yield from csr_ut( csr, CSRA_MCYCLE, 0xFFFFFFFF, F_CSRRCI, 0xFFFFFCBA )
  yield from csr_ut( csr, CSRA_MCYCLE, 0x00000000, F_CSRRC,  0x00000000 )
  yield from csr_ut( csr, CSRA_MCYCLE, 0x00000000, F_CSRRS,  0x00000001 )
  yield from csr_ut( csr, CSRA_MCYCLE, 0x00000000, F_CSRRS,  0x00000002 )
  yield from csr_ut( csr, CSRA_MCYCLE, 0x00000000, F_CSRRS,  0x00000003 )
  # Test reading / writing the 'MCYCLEH' CSR.
  yield from csr_rw_ut( csr, CSRA_MCYCLEH )
  yield csr.mcycle.eq( 0x00000000FFFFFFFF )
  yield Tick()
  yield from csr_ut( csr, CSRA_MCYCLEH, 0x00000000, F_CSRRS,  0x00000001 )
  # Test reading / writing the 'MINSTRET' CSR after clearing it.
  yield csr.minstret.eq( 0 )
  yield from csr_rw_ut( csr, CSRA_MINSTRET )
  # Test reading / writing the 'MINSTRETH' CSR.
  yield from csr_rw_ut( csr, CSRA_MINSTRETH )
  # Test reading / writing some 'MHPMEVENTx' CSRs.
  yield from csr_rw_ut( csr, CSRA_MHPMEVENT_MIN )
  yield from csr_rw_ut( csr, CSRA_MHPMEVENT_MIN + 2 )
  yield from csr_rw_ut( csr, CSRA_MHPMEVENT_MIN + 7 )
  yield from csr_rw_ut( csr, CSRA_MHPMEVENT_MAX )
  # Test reading / writing some 'MHPMCOUNTERx' CSRs.
  yield from csr_rw_ut( csr, CSRA_MHPMCOUNTER_MIN )
  yield from csr_rw_ut( csr, CSRA_MHPMCOUNTER_MIN + 3 )
  yield from csr_rw_ut( csr, CSRA_MHPMCOUNTER_MIN + 17 )
  yield from csr_rw_ut( csr, CSRA_MHPMCOUNTER_MAX )
  # Test reading / writing some 'MHPMCOUNTERxH' CSRs.
  yield from csr_rw_ut( csr, CSRA_MHPMCOUNTERH_MIN )
  yield from csr_rw_ut( csr, CSRA_MHPMCOUNTERH_MIN + 22 )
  yield from csr_rw_ut( csr, CSRA_MHPMCOUNTERH_MAX - 2 )
  yield from csr_rw_ut( csr, CSRA_MHPMCOUNTERH_MAX )

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
