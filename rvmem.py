from nmigen import *
from nmigen.back.pysim import *
from nmigen_soc.wishbone import *
from nmigen_soc.memory import *

from gpio import *
from ram import *

#############################################################
# "RISC-V Memories" module.                                 #
# This directs memory accesses to the appropriate submodule #
# based on the memory space defined by the 3 MSbs.          #
# (None of this is actually part of the RISC-V spec)        #
# Current memory spaces:                                    #
# *  0x0------- = ROM                                       #
# *  0x2------- = RAM                                       #
# *  0x4------- = Peripherals                               #
# ** 0x4000---- = GPIO pins                                 #
#############################################################

class RV_Memory( Elaboratable ):
  def __init__( self, rom_module, ram_words ):
    # Memory multiplexer.
    self.mux = Decoder( addr_width = 32,
                        data_width = 32,
                        alignment = 0 )
    # Add ROM and RAM submodules to the multiplexer.
    self.rom = rom_module
    self.ram = RAM( ram_words )
    self.mux.add( self.rom,  addr = 0x00000000 )
    self.mux.add( self.ram,  addr = 0x20000000 )
    # Add peripheral buses to the multiplexer.
    self.gpio = GPIO()
    self.mux.add( self.gpio, addr = 0x40000000 )

  def elaborate( self, platform ):
    m = Module()
    # Register the multiplexer and memory submodules.
    m.submodules.mux = self.mux
    m.submodules.rom = self.rom
    m.submodules.ram = self.ram
    m.submodules.gpio = self.gpio

    # Currently, all bus transactions are single-cycle.
    # So set the 'strobe' signal equal to the 'cycle' one.
    m.d.comb += self.mux.bus.stb.eq( self.mux.bus.cyc )

    return m
