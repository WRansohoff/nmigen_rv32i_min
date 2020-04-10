from nmigen.hdl.ast import Past

from isa import *

# Helper method to increment the 'minstret' CSR.
def minstret_incr( self, cpu ):
  # Increment 64-bit 'MINSTRET' counter unless it is inhibited.
  with cpu.If( self.csr.mcountinhibit_im == 0 ):
    cpu.d.sync += \
      self.csr.minstret_instrs.eq( self.csr.minstret_instrs + 1 )
    with cpu.If( self.csr.minstret_instrs == 0xFFFFFFFF ):
      cpu.d.sync += \
        self.csr.minstreth_instrs.eq( self.csr.minstreth_instrs + 1 )

# Helper method to enter the trap handler and jump to the
# appropriate address.
def trigger_trap( self, cpu, trap_num ):
  # Set mcause, mepc, interrupt context flag.
  cpu.d.sync += [
    self.csr.mcause_interrupt.eq( 0 ),
    self.csr.mcause_ecode.eq( trap_num ),
    self.csr.mepc_mepc.eq( Past( self.pc ) >> 2 ),
    self.irq.eq( 1 )
  ]
  # Set PC to the interrupt handler address.
  with cpu.If( ( self.csr.mtvec_mode ) == MTVEC_MODE_DIRECT ):
    # "Direct" interrupt mode: use a common handler.
    cpu.d.sync += self.pc.eq( self.csr.mtvec_base << 2 )
  with cpu.Else():
    # "Vecotred" interrupt mode: each trap has its own handler.
    cpu.d.sync += self.pc.eq(
      ( self.csr.mtvec_base + trap_num ) << 2 )
  # Move back to instruction-fetch FSM state.
  cpu.next = "CPU_IFETCH"
