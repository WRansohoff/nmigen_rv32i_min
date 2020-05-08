from nmigen import *
from nmigen.lib.io import *
from nmigen.back.pysim import *

from nmigen_soc.wishbone import *
from nmigen_soc.memory import *

from isa import *

#################################################
# WS2812B / SK6812 "NeoPixel" peripheral        #
# Drives a string of addressable RGB LEDs with  #
# a standard 800KHz single-wire communication.  #
# Add more of these peripherals to the bus in   #
# rvmem.py to run multiple strings in parallel. #
#################################################

# Peripheral registers by offset, in bytes:
# * 0x00: Colors array address. Points to the start of an area
#         of memory which contains the sequence of 24-bit colors
#         to send. Color format: 0xggrrbb
# * 0x04: 'control register'. Bits by index:
# ** 0:     'Start transfer': Send colors to the string of LEDs.
#           Cleared by hardware after the latching period finishes.
# ** 1:     'Transfer complete interrupt enable': Trigger an
#           interrupt whenever a color transfer finishes.
# ** 2-7:   Reserved.
# ** 8-20:  Number of LEDs in the string. The peripheral will access
#           memory starting at the 'colors array address' register,
#           and continuing for (3 * 'num_leds') bytes.
NPX_COL = 0
NPX_CR  = 4

class NeoPixels( Elaboratable, Interface ):
  def __init__( self, ram_bus, index ):
    # Initialize wishbone bus interface for peripheral registers.
    Interface.__init__( self, addr_width = 3, data_width = 32 )
    self.memory_map = MemoryMap( addr_width = self.addr_width,
                                 data_width = self.data_width,
                                 alignment = 0 )
    # Peripheral signals.
    # Colors array starting address.
    self.col_adr = Signal( 32, reset = 0 )
    # Number of LEDs in the strand.
    self.col_len = Signal( 12, reset = 0 )
    # 'Ongoing transfer' / 'busy' / 'start new transfer' signal.
    self.bsy     = Signal( 1,  reset = 0 )
    # Current value to set the output pin(s) to.
    self.px      = Signal( 1,  reset = 0 )
    # 'Transfer complete' interrupt signals.
    self.irq_num = IRQ_NPX_BASE + index
    self.txie    = Signal( 1,  reset = 0 )
    self.txip    = Signal( 1,  reset = 0 )

    # RAM access Interface.
    # Currently, 'ROM' cannot be used to store NeoPixel colors,
    # because the delay in reading a word from SPI Flash may be too
    # long for the ~3MHz pulses, and the CPU is slow enough without
    # sharing the SPI Flash bus with several other peripherals.
    # Plus, the raw Wishbone Interface is cheaper than a Decoder.
    self.ram = ram_bus

  def elaborate( self, platform ):
    m = Module()

    # Read bits default to 0. Peripheral bus and memory bus signals
    # follow their respective 'cyc' signals.
    m.d.comb += [
      self.stb.eq( self.cyc ),
      self.ram.stb.eq( self.ram.cyc )
    ]
    m.d.sync += self.ack.eq( self.cyc )

    # Switch case to select the currently-addressed register.
    # This peripheral must be accessed with a word-aligned address.
    # Writes to all values - not just the 'start' / 'busy' bit -
    # are ignored while a transfer is ongoing.
    with m.Switch( self.adr ):
      # 'Colors address register':
      with m.Case( NPX_COL ):
        m.d.comb += self.dat_r.eq( self.col_adr )
        with m.If( ( self.we & self.cyc ) &
                   ( self.bsy == 0 ) ):
          m.d.sync += self.col_adr.eq( self.dat_w )
      # 'Control register':
      with m.Case( NPX_CR ):
        m.d.comb += [
          self.dat_r.bit_select( 0, 1 ).eq( self.bsy ),
          self.dat_r.bit_select( 1, 1 ).eq( self.txie ),
          self.dat_r.bit_select( 8, 12 ).eq( self.col_len )
        ]
        with m.If( ( self.we & self.cyc ) &
                   ( self.bsy == 0 ) ):
          m.d.sync += [
            self.txie.eq( self.dat_w[ 1 ] ),
            self.col_len.eq( self.dat_w[ 8 : 20 ] )
          ]
          # New transfers can't start if the colors memory
          # address is not in RAM space.
          with m.If( self.col_adr[ 29 : 32 ] == 0b001 ):
            m.d.sync += self.bsy.eq( self.dat_w[ 0 ] )

    # State machine to send colors once the peripheral is activated.
    # Each color bit consists of four 3MHz 'ticks'.
    # The first 'tick' always pulls the pin high.
    # The last 'tick' always pulls the pin low.
    # The middle two 'ticks' pull the pin to the color bit value.

    # FSM signals:
    # Color array progress tracker.
    cprog  = Signal( 16, reset = 0 )
    # Current color.
    ccol   = Signal( 8, reset = 0 )
    # Main countdown counter. For counting progress between color
    # bytes, and the latching signal's duration.
    ccount = Signal( 12, reset = 0 )
    # 6MHz->3MHz countdown.
    cdown  = Signal( 1, reset = 0 )

    # Set the memory interface's address to the current color byte.
    m.d.comb += self.ram.adr.eq( self.col_adr[ :29 ] + cprog )

    # FSM logic:
    with m.FSM():
      # 'Waiting' state: Do nothing until a new transfer is requested.
      with m.State( "NPX_WAITING" ):
        # Kick off a new data transfer once 'busy / start' is set.
        with m.If( self.bsy == 1 ):
          m.d.sync += [
            cprog.eq( 0 ),
            ccount.eq( 31 )
          ]
          m.next = "NPX_TX"

      # "Transmit colors" state: send colors, 8 bits at a time.
      with m.State( "NPX_TX" ):
        # Every 8 bits (4 3MHz 'ticks' * 8 = 32), read the next
        # color byte from memory.
        with m.If( ccount == 31 ):
          m.d.comb += self.ram.cyc.eq( 1 )
          m.d.sync += cdown.eq( 1 )
          # If we've reached the end of the colors array, move
          # to the 'latch' state to finalize the transaction.
          with m.If( cprog == ( self.col_len * 3 ) ):
            m.d.sync += ccount.eq( 0 )
            m.next = "NPX_LATCH"
          # Otherwise, read the next byte from memory. It should
          # be okay to wait for the 'ack' signal, because the LEDs
          # can tolerate up to a few microseconds' delay between
          # color bits before they 'latch'. But this only works
          # with fast internal memory like RAM.
          with m.Elif( self.ram.ack ):
            m.d.sync += [
              cprog.eq( cprog + 1 ),
              ccount.eq( 0 ),
              ccol.eq( self.ram.dat_r[ :8 ] )
            ]
        # If the current color byte is valid and we aren't done
        # with it yet, send the next bit spread out over four 3MHz
        # 'ticks' as described above.
        with m.Else():
          # 'ccount' tracks the 3MHz 'ticks'.
          # 'Tick 1': Pull pin high.
          # 'Tick 2 / 3': Pull pin to the color bit (0 or 1).
          # 'Tick 4': Pull pin low.
          m.d.comb += self.px.eq( Mux(
            ccount[ 0 ] ^ ccount[ 1 ],
            ccol[ 7 ],
            ccount[ 0 ] == 0 ) )
          # 'cdown' scales down a (3*N)MHz clock. In this case, N=2.
          m.d.sync += cdown.eq( cdown + 1 )
          with m.If( cdown == 0b1 ):
            m.d.sync += ccount.eq( ccount + 1 )
            with m.If( ccount[ :2 ] == 0b11 ):
              m.d.sync += ccol.eq( ccol << 1 )

      # "Latch" state: hold the pin low for a few dozen microseconds.
      # Exact timing may vary between different types of "neopixels";
      # SK6812s seem to tolerate shorter latches than WS2812Bs IME.
      with m.State( "NPX_LATCH" ):
        m.d.sync += ccount.eq( ccount + 1 )
        with m.If( ccount[ -1 ] ):
          m.next = "NPX_WAITING"
          m.d.sync += self.bsy.eq( 0 )
          with m.If( self.txie ):
            m.d.sync += self.txip.eq( 1 )

    # (End of 'NeoPixel peripheral' module definition.)
    return m

# TODO: Write a testbench >_>
# Until then, there's a minimal 'npx_test' CPU program to simulate.
