from nmigen import *
from nmigen.back.pysim import *
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
    self.mux = Decoder( addr_width = 32,
                        data_width = 32,
                        alignment = 0 )
    # Add ROM and RAM submodules to the multiplexer.
    self.rom = rom_module
    self.ram = RAM( ram_words )
    self.mux.add( self.rom, addr = 0 )
    self.mux.add( self.ram, addr = 0x20000000 )

  def elaborate( self, platform ):
    m = Module()
    # Register the multiplexer and memory submodules.
    m.submodules.mux = self.mux
    m.submodules.rom = self.rom
    m.submodules.ram = self.ram

    m.d.comb += [
      self.mux.bus.cyc.eq( self.mux.bus.stb ),
      self.mux.bus.adr.eq( self.addr ),
    ]

    return m
