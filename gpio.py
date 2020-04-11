from nmigen import *
from nmigen.lib.io import *
from nmigen.back.pysim import *

from nmigen_soc.wishbone import *
from nmigen_soc.memory import *

from isa import *

##################################
# GPIO interface: allow I/O pins #
# to be written and read.        #
##################################
# TODO: I gotta figure out how 'Connector' board resources work.
# Currently requires a non-standard board file with:
#for i in PINS:
#  resources.append(Resource("gpio", i, Pins("%d"%i, dir="io"),
#                   Attrs(IO_STANDARD = "SB_LVCMOS")))

# Dummy GPIO pin class for simulations.
class DummyGPIO():
  def __init__( self, name ):
    self.o  = Signal( name = "%s_o"%name )
    self.i  = Signal( name = "%s_i"%name )
    self.oe = Signal( name = "%s_oe"%name )

# Supported pin numbers: iCE40 pins are numbered based on the
# package, so this is only valid for the iCE40UP5K-SG48.
# These pins are the ones available on 'Upduino' board headers,
# plus the LEDs on pins 39-41.
PINS = [ 2, 3, 4, 9, 11, 12, 13, 18, 19, 21, 23, 25, 26, 27, 31, 32,
         34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48 ]

class GPIO( Elaboratable, Interface ):
  def __init__( self ):
    # Initialize wishbone bus interface to support up to 64 pins.
    # Each pin has two bits, so there are 16 pins per register:
    # * 0: value. Contains the current I/O pin value. Only writable
    #      in output mode. Writes to input pins are ignored.
    #      (But they might get applied when the direction switches?)
    # * 1: direction. When set to '0', the pin is in input mode and
    #      its output is disabled. When set to '1', it is in output
    #      mode and the value in bit 0 will be reflected on the pin.
    #
    # iCE40s don't have programmable pulling resistors, and I think
    # only the LED pins have more than one drive strength.
    # So...not many options here. You get an I, and you get an O.
    Interface.__init__( self, addr_width = 5, data_width = 32 )
    self.memory_map = MemoryMap( addr_width = self.addr_width,
                                 data_width = self.data_width,
                                 alignment = 0 )

  def elaborate( self, platform ):
    m = Module()

    # Set up I/O pin resources.
    if platform is None:
      self.p = Array(
        DummyGPIO( "pin_%d"%i ) if i in PINS else None
        for i in range( max( PINS ) + 1 ) )
    else:
      self.p = Array(
        platform.request( "gpio", i ) if i in PINS else None
        for i in range( max( PINS ) + 1 ) )

    # Read bits default to 0. Bus signals follow 'cyc'.
    m.d.comb += [
      self.dat_r.eq( 0 ),
      self.stb.eq( self.cyc )
    ]
    m.d.sync += self.ack.eq( self.cyc )

    # Switch case to select the currently-addressed register.
    # This peripheral must be accessed with a word-aligned address.
    with m.Switch( self.adr ):
      for i in range( 4 ):
        with m.Case( i * 4 ):
          # Logic for each of the register's 16 possible pins,
          # ignoring ones that aren't in the 'PINS' array.
          for j in range( 16 ):
            pnum = ( i * 16 ) + j
            if pnum in PINS:
              pin = self.p[ pnum ]
              # Read logic: populate 'value' and 'direction' bits.
              m.d.comb += self.dat_r.bit_select( j * 2, 2 ).eq(
                Cat( Mux( pin.oe, pin.o, pin.i ), pin.oe ) )
              # Write logic: if this bus is selected and writes
              # are enabled, set 'value' and 'direction' bits.
              with m.If( ( self.we == 1 ) & ( self.cyc == 1 ) ):
                m.d.sync += [
                  pin.o.eq( self.dat_w.bit_select( j * 2, 1 ) ),
                  pin.oe.eq( self.dat_w.bit_select( j * 2 + 1, 1 ) )
                ]

    # (End of GPIO peripheral module definition)
    return m

# TODO: Write a testbench >_>
# Until then, there's a minimal 'gpio_test' CPU program to simulate.
