from nmigen import *
from nmigen.lib.io import *
from nmigen.back.pysim import *

from nmigen_soc.wishbone import *
from nmigen_soc.memory import *

from gpio import *
from isa import *

##########################################
# GPIO multiplexer interface:            #
# Map I/O pins to different peripherals. #
# Each pin gets 4 bits:                  #
# * 0x0: GPIO (default)                  #
# * 0x1: Neopixel peripheral #1          #
# * 0x2: Neopixel peripheral #2          #
# * 0x3: Neopixel peripheral #3          #
# * 0x4: Neopixel peripheral #4          #
# * 0x5: PWM peripheral #1               #
# * 0x6: PWM peripheral #2               #
# * 0x7: PWM peripheral #3               #
# * 0x8: PWM peripheral #4               #
##########################################

# Dummy GPIO pin class for simulations.
class DummyGPIO():
  def __init__( self, name ):
    self.o  = Signal( name = "%s_o"%name )
    self.i  = Signal( name = "%s_i"%name )
    self.oe = Signal( name = "%s_oe"%name )

class GPIO_Mux( Elaboratable, Interface ):
  def __init__( self, periphs ):
    # Wishbone interface: address <=64 pins, 4 bits per pin.
    # The bus is 32 bits wide for compatibility, so 8 pins per word.
    Interface.__init__( self, addr_width = 6, data_width = 32 )
    self.memory_map = MemoryMap( addr_width = self.addr_width,
                                 data_width = self.data_width,
                                 alignment = 0 )
    # Backing data store for QFN48 pins. A 'Memory' would be more
    # efficient, but the module must access each field in parallel.
    self.pin_mux = Array(
      Signal( 4, reset = 0, name = "pin_func_%d"%i ) if i in PINS else None
      for i in range( 49 ) )

    # Unpack peripheral modules (passed in from 'rvmem.py' module).
    self.gpio = periphs[ 0 ]
    self.npx1 = periphs[ 1 ]
    self.npx2 = periphs[ 2 ]
    self.npx3 = periphs[ 3 ]
    self.npx4 = periphs[ 4 ]
    self.pwm1 = periphs[ 5 ]
    self.pwm2 = periphs[ 6 ]
    self.pwm3 = periphs[ 7 ]
    self.pwm4 = periphs[ 8 ]

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
      self.stb.eq( self.cyc ),
    ]
    m.d.sync +=  self.ack.eq( self.cyc )

    # Switch case to read/write the currently-addressed register.
    # This peripheral must be accessed with a word-aligned address.
    with m.Switch( self.adr ):
      # 49 pin addresses (0-48), 8 pins per register, so 7 registers.
      for i in range( 7 ):
        with m.Case( i * 4 ):
          # Read logic for valid pins (each has 4 bits).
          for j in range( 8 ):
            pnum = ( i * 8 ) + j
            if pnum in PINS:
              m.d.comb += self.dat_r.bit_select( j * 4, 4 ).eq(
                self.pin_mux[ pnum ] )
              # Write logic for valid pins (again, 4 bits each).
              with m.If( ( self.cyc == 1 ) &
                         ( self.we == 1 ) ):
                m.d.sync += self.pin_mux[ pnum ].eq(
                  self.dat_w.bit_select( j * 4, 4 ) )

    # Pin multiplexing logic.
    for i in range( 49 ):
      if i in PINS:
        # Each valid pin gets its own switch case, which ferries
        # signals between the selected peripheral and the actual pin.
        with m.Switch( self.pin_mux[ i ] ):
          # GPIO
          with m.Case( 0x0 ):
            # Apply 'value' and 'direction' bits.
            m.d.sync += self.p[ i ].oe.eq( self.gpio.p[ i ][ 1 ] )
            # Read or write, depending on the 'direction' bit.
            with m.If( self.gpio.p[ i ][ 1 ] == 0 ):
              m.d.sync += self.gpio.p[ i ].bit_select( 0, 1 ) \
                .eq( self.p[ i ].i )
            with m.Else():
              m.d.sync += self.p[ i ].o.eq( self.gpio.p[ i ][ 0 ] )
          # Neopixel peripheral #1
          with m.Case( 0x1 ):
            # Set pin to output mode, and set its current value.
            m.d.sync += [
              self.p[ i ].oe.eq( 1 ),
              self.p[ i ].o.eq( self.npx1.px )
            ]
          # Neopixel peripheral #2
          with m.Case( 0x2 ):
            # Set pin to output mode, and set its current value.
            m.d.sync += [
              self.p[ i ].oe.eq( 1 ),
              self.p[ i ].o.eq( self.npx2.px )
            ]
          # Neopixel peripheral #3
          with m.Case( 0x3 ):
            # Set pin to output mode, and set its current value.
            m.d.sync += [
              self.p[ i ].oe.eq( 1 ),
              self.p[ i ].o.eq( self.npx3.px )
            ]
          # Neopixel peripheral #4
          with m.Case( 0x4 ):
            # Set pin to output mode, and set its current value.
            m.d.sync += [
              self.p[ i ].oe.eq( 1 ),
              self.p[ i ].o.eq( self.npx4.px )
            ]
          # PWM peripheral #1
          with m.Case( 0x5 ):
            # Set pin to output mode, and set its current value.
            m.d.sync += [
              self.p[ i ].oe.eq( 1 ),
              self.p[ i ].o.eq( self.pwm1.o )
            ]
          # PWM peripheral #2
          with m.Case( 0x6 ):
            # Set pin to output mode, and set its current value.
            m.d.sync += [
              self.p[ i ].oe.eq( 1 ),
              self.p[ i ].o.eq( self.pwm2.o )
            ]
          # PWM peripheral #3
          with m.Case( 0x7 ):
            # Set pin to output mode, and set its current value.
            m.d.sync += [
              self.p[ i ].oe.eq( 1 ),
              self.p[ i ].o.eq( self.pwm3.o )
            ]
          # PWM peripheral #4
          with m.Case( 0x8 ):
            # Set pin to output mode, and set its current value.
            m.d.sync += [
              self.p[ i ].oe.eq( 1 ),
              self.p[ i ].o.eq( self.pwm4.o )
            ]

    # (End of GPIO multiplexer module)
    return m

# TODO: Write a testbench >_>
