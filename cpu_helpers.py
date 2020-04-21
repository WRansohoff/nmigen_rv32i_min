from nmigen.hdl.ast import Past

from isa import *

# Helper method to increment the 'minstret' CSR.
def minstret_incr( self, cpu ):
  # Increment pared-down 32-bit MINSTRET counter.
  # I'd remove the whole MINSTRET CSR to save space, but the
  # test harnesses depend on it to count instructions.
  cpu.d.sync += \
    self.csr.minstret_instrs.eq( self.csr.minstret_instrs + 1 )

# Helper method to enter the trap handler and jump to the
# appropriate address.
def trigger_trap( self, cpu, trap_num ):
  cpu.d.sync += [
    # Set mcause, mepc, interrupt context flag.
    self.csr.mcause_interrupt.eq( 0 ),
    self.csr.mcause_ecode.eq( trap_num ),
    self.csr.mepc_mepc.eq( Past( self.pc ).bit_select( 2, 30 ) ),
    # Set PC to the interrupt handler address.
    self.pc.eq( Cat( Repl( 0, 2 ),
                    ( self.csr.mtvec_base +
                      Mux( self.csr.mtvec_mode, trap_num, 0 ) ) ) )
  ]
