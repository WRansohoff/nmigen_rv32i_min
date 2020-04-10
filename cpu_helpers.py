from isa import *

# Helper method to increment the 'minstret' CSR.
def minstret_incr( self, cpu ):
  # Increment 64-bit 'MINSTRET' counter unless it is inhibited.
  with cpu.If( self.csr.mcountinhibit.shadow[ 2 ] == 0 ):
    cpu.d.sync += \
      self.csr.minstret.shadow.eq( self.csr.minstret.shadow + 1 )
    with cpu.If( self.csr.minstret.shadow == 0xFFFFFFFF ):
      cpu.d.sync += \
        self.csr.minstreth.shadow.eq( self.csr.minstreth.shadow + 1 )

# Helper method to enter the trap handler and jump to the
# appropriate address.
def trigger_trap( self, cpu, trap_num ):
  # Set mcause, mepc, interrupt context flag.
  cpu.d.sync += [
    self.csr.mcause.shadow.eq( trap_num ),
    self.csr.mepc.shadow.eq( self.ipc ),
    self.irq.eq( 1 )
  ]
  # Set PC to the interrupt handler address.
  with cpu.If( ( self.csr.mtvec.shadow[ :2 ] ) == MTVEC_MODE_DIRECT ):
    # "Direct" interrupt mode: use a common handler.
    cpu.d.sync += self.pc.eq( self.csr.mtvec.shadow & 0xFFFFFFFC )
  with cpu.Else():
    # "Vecotred" interrupt mode: each trap has its own handler.
    cpu.d.sync += self.pc.eq(
      ( self.csr.mtvec.shadow & 0xFFFFFFFC ) + ( trap_num << 2 )
    )
  # Move back to instruction-fetch FSM state.
  cpu.next = "CPU_IFETCH"
