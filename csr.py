from isa import *

#########################################
# 'Control and Status Registers' file.  #
# This contains logic for handling the  #
# 'ECALL' instruction, which is used to #
# read/write CSRs in the base ISA.      #
# CSR named constants are in `isa.py`.  #
#########################################

# Helper methods for individual CSR read/write/set/clear operations.
# CSRRW: Write a CSR value, and read it back if the destination
# register is not r0. If dest. is r0, no read side effects occur.
# Returns the next CPU FSM state.
def handle_csrrw( self, cpu ):
  return "CPU_PC_LOAD"

# CSRRS: Set specified bits in a CSR and read it back, unless the
# the source register is r0. If source is r0, don't write to the CSR.
# Returns the next CPU FSM state.
def handle_csrrs( self, cpu ):
  return "CPU_PC_LOAD"

# CSRRC: Clear specified bits in a CSR and read it back, unless the
# the source register is r0. If source is r0, don't write to the CSR.
# Returns the next CPU FSM state.
def handle_csrrc( self, cpu ):
  return "CPU_PC_LOAD"

# CSRRWI: Write a 5-bit immediate to a CSR, and read it back if the
# destination register is not r0. If dest. is r0, no read occurs.
# Returns the next CPU FSM state.
def handle_csrrwi( self, cpu ):
  return "CPU_PC_LOAD"

# CSRRSI: Set specified bits in a CSR and read it back, unless the
# the immediate value equals 0. If it does, don't write to the CSR.
# Returns the next CPU FSM state.
def handle_csrrsi( self, cpu ):
  return "CPU_PC_LOAD"

# CSRRCI: Clear specified bits in a CSR and read it back, unless the
# the immediate value equals 0. If it does, don't write to the CSR.
# Returns the next CPU FSM state.
def handle_csrrci( self, cpu ):
  return "CPU_PC_LOAD"
