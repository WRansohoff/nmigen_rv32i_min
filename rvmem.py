from nmigen import *
from nmigen.back.pysim import *
from nmigen_soc.csr import *
from nmigen_soc.csr.bus import *
from nmigen_soc.csr.wishbone import *
from nmigen_soc.wishbone import *
from nmigen_soc.memory import *

from ram import *

#############################################################
# "RISC-V Memories" module.                                 #
# This directs memory accesses to the appropriate submodule #
# based on the memory space defined by the 3 MSbs.          #
# (None of this is actually part of the RISC-V spec)        #
# Current memory spaces:                                    #
# * 0x0------- = ROM                                        #
# * 0x2------- = RAM                                        #
# Planned memory spaces:                                    #
# * 0x4------- = Peripheral buses                           #
#############################################################

class RV_Memory( Elaboratable ):
  def __init__( self, rom_module, ram_words ):
    # Input memory address.
    self.addr = Signal( 32, reset = 0x00000000 )
    # Memory multiplexer.
    self.mux = Multiplexer( addr_width = 3,
                            data_width = 32,
                            alignment = 0 )
    # Add ROM and RAM submodules to the multiplexer.
    self.rom = rom_module
    self.ram = RAM( ram_words )
    self.mux.add( self.rom, addr = 0 )
    self.mux.add( self.ram, addr = 1 )

  def elaborate( self, platform ):
    m = Module()
    # Register the multiplexer and memory submodules.
    m.submodules.mux = self.mux
    m.submodules.rom = self.rom
    m.submodules.ram = self.ram

    # The multiplexer address is the 3 most significant bits of
    # the memory space address.
    m.d.comb += [
      self.mux.bus.addr.eq( self.addr[ 29: 32 ] ),
      self.mux.bus.r_stb.eq( 1 ),
      self.ram.addr.eq( self.addr & 0x1FFFFFFF ),
      self.rom.addr.eq( self.addr )
    ]

    return m
