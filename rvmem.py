from nmigen import *
from nmigen.back.pysim import *
from nmigen_soc.wishbone import *
from nmigen_soc.memory import *

from gpio import *
from gpio_mux import *
from npx import *
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
# ** 0x4001---- = GPIO multiplexer                          #
# ** 0x4002---- = Neopixel peripherals                      #
# ** 0x400200-- = Neopixel peripheral #1                    #
# ** 0x400201-- = Neopixel peripheral #2                    #
#############################################################

class RV_Memory( Elaboratable ):
  def __init__( self, rom_module, ram_words ):
    # Memory multiplexer.
    self.mux = Decoder( addr_width = 32,
                        data_width = 32,
                        alignment = 0 )
    # Add ROM and RAM buses to the multiplexer.
    self.rom = rom_module
    self.ram = RAM( ram_words )
    self.rom_di = self.rom.new_bus()
    self.ram_di = self.ram.new_bus()
    self.mux.add( self.rom_di,   addr = 0x00000000 )
    self.mux.add( self.ram_di,   addr = 0x20000000 )
    # Add peripheral buses to the multiplexer.
    self.gpio = GPIO()
    self.mux.add( self.gpio,     addr = 0x40000000 )
    self.npx1 = NeoPixels( self.ram.new_bus() )
    self.mux.add( self.npx1,     addr = 0x40020000 )
    self.npx2 = NeoPixels( self.ram.new_bus() )
    self.mux.add( self.npx2,     addr = 0x40020100 )
    self.gpio_mux = GPIO_Mux( [ self.gpio, self.npx1, self.npx2 ] )
    self.mux.add( self.gpio_mux, addr = 0x40010000 )

  def elaborate( self, platform ):
    m = Module()
    # Register the multiplexer and memory submodules.
    m.submodules.mux = self.mux
    m.submodules.rom = self.rom
    m.submodules.ram = self.ram
    m.submodules.gpio = self.gpio
    m.submodules.npx1 = self.npx1
    m.submodules.gpio_mux = self.gpio_mux

    # Currently, all bus transactions are single-cycle.
    # So set the 'strobe' signal equal to the 'cycle' one.
    m.d.comb += self.mux.bus.stb.eq( self.mux.bus.cyc )

    return m
